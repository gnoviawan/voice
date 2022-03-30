try:
    from orjson import dumps, loads
except ImportError:
    from json import dumps, loads

from asyncio import Event, Task, ensure_future, sleep
from datetime import datetime
from logging import Logger
from typing import Any, Dict, List, Optional, Tuple

from aiohttp import WSMessage, WSMsgType
from aiohttp.http import WS_CLOSED_MESSAGE, WS_CLOSING_MESSAGE
from nacl.secret import SecretBox

from interactions.api.cache import Cache, Item, Storage
from interactions.api.enums import OpCodeType
from interactions.api.gateway import WebSocketClient, _Heartbeat
from interactions.api.http.client import HTTPClient
from interactions.api.models.channel import Channel
from interactions.api.models.guild import Guild
from interactions.api.models.member import Member
from interactions.api.models.misc import MISSING, DictSerializerMixin, Snowflake
from interactions.api.models.presence import ClientPresence
from interactions.base import get_logger
from interactions.client import Client

from .client import VoiceClient
from .enums import VoiceOpCodeType
from .error import VoiceException

log: Logger = get_logger("voice")


# TODO: switch to new cache once merged.


class VoiceCache(Cache):
    """
    A modified cache to store VoiceState data.
    """

    def __init__(self):
        super().__init__()
        self.voice_states: Storage = Storage()


class VoiceConnectionWebSocketClient:
    """
    A class representing the clients voice channel connection.
    todo doc?
    """

    def __init__(self, guild_id: int, data: dict, _http: HTTPClient):
        self.guild_id = guild_id
        self.session_id = data.get("session_id")
        self.endpoint = f"wss://{data.get('endpoint')}?v=4"
        self.token = data.get("token")
        self.user_id = data.get("user_id")
        self.sequence = data.get("sequence")
        self._http = _http
        self.__task = None
        self.__box: SecretBox = None
        self._port = None
        self._ip = None
        self._mode = None
        self._closed = False
        self._close = (
            False  # determines whether closing of the connection is wanted or not -> disconnect
        )
        self._media_session_id = None
        self.__heartbeater: _Heartbeat = _Heartbeat(loop=None)
        self.ready = Event()

    @property
    async def __receive_packet_stream(self) -> Optional[Dict[str, Any]]:
        """
        Receives a stream of packets sent from the Gateway.

        :return: The packet stream.
        :rtype: Optional[Dict[str, Any]]
        """

        packet: WSMessage = await self._client.receive()

        if packet == WSMsgType.CLOSE:
            await self._client.close()
            return packet

        elif packet == WS_CLOSED_MESSAGE:
            return packet

        elif packet == WS_CLOSING_MESSAGE:
            await self._client.close()
            return WS_CLOSED_MESSAGE

        return loads(str(packet.data)) if packet and isinstance(packet.data, (str, int)) else None

    async def _connect(
        self,
        shard: Optional[List[Tuple[int]]] = MISSING,
    ) -> None:
        """
        Establishes a client connection with the Gateway.

        :param shard?: The shards to establish a connection with. Defaults to ``None``.
        :type shard: Optional[List[Tuple[int]]]
        """
        self._client = None
        self.__heartbeater.delay = 0.0
        self._closed = False

        async with self._http._req._session.ws_connect(self.endpoint) as self._client:
            self._closed = self._client.closed

            if self._closed:
                await self._connect()

            while not self._closed:
                stream = await self.__receive_packet_stream

                if stream is None:
                    continue

                if self._client is None or stream == WS_CLOSED_MESSAGE or stream == WSMsgType.CLOSE:
                    await self._connect()
                    break

                if (
                    self._client.close_code in range(4001, 4006)
                    or self._client.close_code
                    in (
                        4009,
                        4011,
                        4012,
                        4014,
                        4016,
                    )
                ) or isinstance(stream, int):
                    if self.__task:
                        self.__task.cancel()  # to be sure it stops
                    self._closed = True
                    if self._close and stream == 4014:
                        log.debug("Closing Voice Connection.")
                        break
                    else:
                        code = self._client.close_code or stream
                        raise VoiceException(code)

                await self._handle_connection(stream, shard)

    async def __heartbeat(self):
        payload: dict = {
            "op": VoiceOpCodeType.HEARTBEAT,
            "d": self.sequence,
        }
        await self._send_packet(payload)
        log.debug("HEARTBEAT")

    async def _manage_heartbeat(self) -> None:
        """Manages the heartbeat loop."""
        while True:
            if self._closed:
                await self.__restart()
            if self.__heartbeater.event.is_set():
                await self.__heartbeat()
                self.__heartbeater.event.clear()
                await sleep(self.__heartbeater.delay / 1000)
            else:
                log.debug("HEARTBEAT_ACK missing, reconnecting...")
                await self.__restart()
                break

    async def _connect_to_udp(self):

        payload = {
            "op": VoiceOpCodeType.SELECT_PROTOCOL,
            "d": {
                "protocol": "udp",
                "data": {
                    "address": self._ip,
                    "port": self._port,
                    "mode": "xsalsa20_poly1305",
                },
            },
        }
        log.debug(f"CONNECTING TO UDP: {payload}")
        await self._send_packet(payload)

    async def _handle_connection(
        self,
        stream: Dict[str, Any],
        shard: Optional[List[Tuple[int]]] = MISSING,
    ) -> None:
        """
        Handles the client's connection with the Gateway.

        :param stream: The packet stream to handle.
        :type stream: Dict[str, Any]
        :param shard?: The shards to establish a connection with. Defaults to ``None``.
        :type shard: Optional[List[Tuple[int]]]
        """
        op: Optional[int] = stream.get("op")
        data: Optional[Dict[str, Any]] = stream.get("d")

        if op == VoiceOpCodeType.HELLO:
            self.__heartbeater.delay = data["heartbeat_interval"]
            self.__heartbeater.event.set()

            if self.__task:
                self.__task.cancel()  # so we can reduce redundant heartbeat bg tasks.

            self.__task = ensure_future(self._manage_heartbeat())

            await self.__identify(shard)

        if op == VoiceOpCodeType.READY:
            self._ip = data.get("ip")
            self._port = data.get("port")
            self.ssrc = data.get("ssrc")
            await self._connect_to_udp()
            self._ready = data
            log.debug(f"READY (session_id: {self.session_id}, sequence: {self.sequence})")
            self.ready.set()

        if op == VoiceOpCodeType.HEARTBEAT:
            await self.__heartbeat()

        if op == VoiceOpCodeType.HEARTBEAT_ACK:
            log.debug("HEARTBEAT_ACK")
            self.__heartbeater.event.set()

        if op == VoiceOpCodeType.SESSION_DESCRIPTION:
            self.__box = SecretBox(bytes(data["secret_key"]))
            self._media_session_id = data["media_session_id"]
            self._mode = data["mode"]

        if op == VoiceOpCodeType.RESUME:
            await self.__resume()

        if op == VoiceOpCodeType.RESUMED:
            log.debug(f"RESUMED (session_id: {self.session_id}, seq: {self.sequence})")

        # TODO: other opcodes

    async def __start_speaking(self) -> None:
        payload = {
            "op": VoiceOpCodeType.SPEAKING,
            "d": {"speaking": 1 << 0, "delay": 0, "ssrc": self.ssrc},
        }
        log.debug(f"SPEAKING: {payload}")
        await self._send_packet(payload)

    async def __stop_speaking(self) -> None:
        payload = {
            "op": VoiceOpCodeType.SPEAKING,
            "d": {"speaking": 0, "delay": 0, "ssrc": self.ssrc},
        }
        log.debug(f"SPEAKING: {payload}")
        await self._send_packet(payload)

    async def __restart(self):
        """Restart the client's connection and heartbeat with the Gateway."""
        if self.__task:
            self.__task: Task
            self.__task.cancel()
        self._closed = True
        self._client = None  # clear pending waits
        self.__heartbeater.event.clear()
        await self._connect()

    async def __resume(self) -> None:
        """Sends a ``RESUME`` packet to the gateway."""
        payload: dict = {
            "op": VoiceOpCodeType.RESUME,
            "d": {"token": self.token, "session_id": self.session_id, "server_id": self.guild_id},
        }
        log.debug(f"RESUMING: {payload}")
        await self._send_packet(payload)
        log.debug("RESUME")

    async def __identify(self, shard: Optional[List[Tuple[int]]] = None) -> None:
        """
        Sends an ``IDENTIFY`` packet to the gateway.

        :param shard?: The shard ID to identify under.
        :type shard: Optional[List[Tuple[int]]]
        """

        self.__shard = shard
        payload: dict = {
            "op": VoiceOpCodeType.IDENTIFY,
            "d": {
                "token": self.token,
                "server_id": self.guild_id,
                "session_id": self.session_id,
                "user_id": self.user_id,
            },
        }

        if isinstance(shard, List) and len(shard) >= 1:
            payload["d"]["shard"] = shard

        log.debug(f"IDENTIFYING: {payload}")
        await self._send_packet(payload)
        log.debug("IDENTIFY")

    async def _send_packet(self, data: Dict[str, Any]) -> None:
        """
        Sends a packet to the Gateway.

        :param data: The data to send to the Gateway.
        :type data: Dict[str, Any]
        """
        _data = dumps(data) if isinstance(data, dict) else data
        packet: str = _data.decode("utf-8") if isinstance(_data, bytes) else _data
        await self._client.send_str(packet)
        log.debug(packet)


class VoiceWebSocketClient(WebSocketClient):
    """
    A modified WebSocketClient for Voice Events.

    todo: doc
    """

    def __init__(
        self,
        token,
        intents,
        session_id=MISSING,
        sequence=MISSING,
    ) -> None:
        super().__init__(token, intents, session_id, sequence)
        self.__voice_connect_data: Dict[int, dict] = {}
        self._voice_connections: Dict[int, VoiceConnectionWebSocketClient] = {}

    async def _handle_connection(
        self,
        stream: Dict[str, Any],
        shard: Optional[List[Tuple[int]]] = MISSING,
        presence: Optional[ClientPresence] = MISSING,
    ) -> None:
        op: Optional[int] = stream.get("op")
        event: Optional[str] = stream.get("t")
        data: Optional[Dict[str, Any]] = stream.get("d")

        if op != OpCodeType.DISPATCH:
            await super()._handle_connection(stream, shard, presence)

        elif event and "voice" not in event.lower():
            await super()._handle_connection(stream, shard, presence)

        else:
            log.debug(f"{event}: {data}")
            self._dispatch_event(event, data, stream)  # to get the nonce stream is needed.

    def _dispatch_event(self, event: str, data: dict, stream: Optional[dict] = MISSING) -> None:
        if event != "VOICE_STATE_UPDATE" and event != "VOICE_SERVER_UPDATE":
            super()._dispatch_event(event, data)
        else:
            name: str = event.lower()
            if event == "VOICE_STATE_UPDATE":
                self.__voice_connect_data[int(data["guild_id"])] = {
                    "session_id": data["session_id"],
                    "user_id": int(data["user_id"]),
                }
                __obj: object = VoiceState
                _item = Item(id=str(data["user_id"]), value=[data])
                if _item.id in self._http.cache.voice_states.values.keys():
                    if len(self._http.cache.voice_states.values[_item.id]) >= 2:
                        self._http.cache.voice_states.values[_item.id].pop(0)
                    self._http.cache.voice_states.values[_item.id].extend(_item.value)
                    # doing it manually since the update meth is broken.
                else:
                    self._http.cache.voice_states.add(_item)
                data["_client"] = self._http

                self._dispatch.dispatch(f"on_{name}", __obj(**data))  # noqa
            elif event == "VOICE_SERVER_UPDATE":
                self.__voice_connect_data[int(data["guild_id"])]["token"] = data["token"]
                self.__voice_connect_data[int(data["guild_id"])]["endpoint"] = data["endpoint"]
                self.__voice_connect_data[int(data["guild_id"])]["sequence"] = stream.get("s")

        self._dispatch.dispatch("raw_socket_create", data)

    async def _connect(
        self,
        guild_id: int,
        channel_id: int,
        self_mute: bool = False,
        self_deaf: bool = False,
    ) -> None:
        """

        :param guild_id:
        :param channel_id:
        :param self_mute:
        :param self_deaf:
        :return:
        """
        payload: dict = {
            "op": OpCodeType.VOICE_STATE,
            "d": {
                "channel_id": f"{channel_id}",
                "guild_id": f"{guild_id}",
                "self_deaf": self_deaf,
                "self_mute": self_mute,
            },
        }
        await self._send_packet(data=payload)
        await sleep(2)
        voice_client = VoiceConnectionWebSocketClient(
            guild_id=int(guild_id),
            data=self.__voice_connect_data[int(guild_id)],
            _http=self._http,
        )
        self._voice_connections[int(guild_id)] = voice_client
        await voice_client._connect()

    async def _disconnect(self, guild_id: int) -> None:
        """
        Closes an existing voice connection on a guild.

        :param guild_id: The id of the guild to close the connection of
        :type guild_id: int
        """

        self._voice_connections[guild_id]._close = True
        payload = {
            "op": OpCodeType.VOICE_STATE,
            "d": {
                "guild_id": guild_id,
                "channel_id": None,
            },
        }

        await self._send_packet(data=payload)
        del self._voice_connections[guild_id]


class VoiceState(DictSerializerMixin):
    """
    A class object representing the gateway event ``VOICE_STATE_UPDATE``.

    This class creates an object every time the event ``VOICE_STATE_UPDATE`` is received from the discord API.
    It contains information about the user's update voice information. Additionally, the last voice state is cached,
    allowing you to see, what attributes of the user's voice information change.

    Attributes:
    -----------
    _json : dict
        All data of the object stored as dictionary

    member : Member
        The member whose VoiceState was updated

    user_id : int
        The id of the user whose VoiceState was updated. This is technically the same as the "member id",
        but it is called `user_id` because of API terminology.

    suppress : bool
        Whether the user is muted by the current user(-> bot)

    session_id : int
        The id of the session

    self_video : bool
        Whether the user's camera is enabled.

    self_mute : bool
        Whether the user is muted by themselves

    self_deaf : bool
        Whether the user is deafened by themselves

    self_stream : bool
        Whether the user is streaming in the current channel

    request_to_speak_timestamp : datetime
        Only for stage-channels; when the user requested permissions to speak in the stage channel

    mute : bool
        Whether the user's microphone is muted by the server

    guild_id : int
        The id of the guild in what the update took action

    deaf : bool
        Whether the user is deafened by the guild

    channel_id : int
        The id of the channel the update took action
    """

    __slots__ = (
        "_client",
        "_json",
        "member",
        "user_id",
        "suppress",
        "session_id",
        "self_video",
        "self_mute",
        "self_deaf",
        "self_stream",
        "request_to_speak_timestamp",
        "mute",
        "guild_id",
        "deaf",
        "channel_id",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.channel_id = Snowflake(self.channel_id) if self._json.get("channel_id") else None
        self.guild_id = Snowflake(self.guild_id) if self._json.get("guild_id") else None
        self.user_id = Snowflake(self.user_id) if self._json.get("user_id") else None
        self.member = (
            Member(**self.member, _client=self._client) if self._json.get("member") else None
        )
        self.request_to_speak_timestamp = (
            datetime.fromisoformat(self.request_to_speak_timestamp)
            if self._json.get("request_to_speak_timestamp")
            else None
        )

    @property
    def before(self) -> "VoiceState":
        """
        Returns the last voice state of the member, allowing to check what changed.

        :return: VoiceState object of the last update of that user
        :rtype: VoiceState
        """
        return VoiceState(**self._client.cache.voice_states.get(str(self.user_id))[0])

    async def mute_member(self, reason: Optional[str]) -> Member:
        """
        Mutes the current member.

        :param reason: The reason of the muting, optional
        :type reason: str
        :return: The modified member object
        :rtype: GuildMember
        """
        return await self.member.modify(guild_id=int(self.guild_id), mute=True, reason=reason)

    async def deafen_member(self, reason: Optional[str]) -> Member:
        """
        Deafens the current member.

        :param reason: The reason of the deafening, optional
        :type reason: str
        :return: The modified member object
        :rtype: GuildMember
        """
        return await self.member.modify(guild_id=int(self.guild_id), deaf=True, reason=reason)

    async def move_member(self, channel_id: int, *, reason: Optional[str]) -> Member:
        """
        Moves the member to another channel.

        :param channel_id: The ID of the channel to move the user to
        :type channel_id: int
        :param reason: The reason of the move
        :type reason: str
        :return: The modified member object
        :rtype: GuildMember
        """
        return await self.member.modify(
            guild_id=int(self.guild_id), channel_id=channel_id, reason=reason
        )

    async def get_channel(self) -> Channel:
        """
        Gets the channel in what the update took place.

        :rtype: Channel
        """
        return Channel(**await self._client.get_channel(int(self.channel_id)), _client=self._client)

    async def get_guild(self) -> Guild:
        """
        Gets the guild in what the update took place.

        :rtype: Guild
        """
        return Guild(**await self._client.get_guild(int(self.channel_id)), _client=self._client)


WebSocketClient = VoiceWebSocketClient


def _update_instances(client: Client):
    if not isinstance(client._websocket, VoiceWebSocketClient):
        old_websocket = client._websocket
        new_websocket = VoiceWebSocketClient(old_websocket._http.token, old_websocket._intents)
        new_websocket._loop = old_websocket._loop
        new_websocket._dispatch = old_websocket._dispatch
        new_websocket._http = old_websocket._http
        new_websocket._client = old_websocket._client
        new_websocket._closed = old_websocket._closed
        new_websocket._options = old_websocket._options
        new_websocket._intents = old_websocket._intents
        new_websocket._ready = old_websocket._ready if hasattr(old_websocket, "_ready") else None
        new_websocket.__heartbeater = old_websocket._WebSocketClient__heartbeater
        new_websocket.__shard = old_websocket._WebSocketClient__shard
        new_websocket.__presence = old_websocket._WebSocketClient__presence
        new_websocket.__task = old_websocket._WebSocketClient__task
        new_websocket.session_id = old_websocket.session_id
        new_websocket.sequence = old_websocket.sequence
        new_websocket.ready = old_websocket.ready
        new_websocket._last_send = old_websocket._last_send
        new_websocket._last_ack = old_websocket._last_ack

        client._websocket = new_websocket

    if not isinstance(client._http.cache, VoiceCache):
        old_cache = client._http.cache
        new_cache = VoiceCache()
        new_cache.dms = old_cache.dms
        new_cache.self_guilds = old_cache.self_guilds
        new_cache.guilds = old_cache.guilds
        new_cache.channels = old_cache.channels
        new_cache.roles = old_cache.roles
        new_cache.members = old_cache.members
        new_cache.messages = old_cache.messages
        new_cache.users = old_cache.users
        new_cache.interactions = old_cache.interactions

        client._http.cache = new_cache
        client._websocket._http.cache = new_cache


def setup(client: Client, voice_client: bool = False):
    """
    Sets up the voice ext. If `voice_client` is set to true, the client will be modified, so it can connect to a
    voice channel. Otherwise, this ext will only dispatch voice state updates.
    """
    _update_instances(client)
    if voice_client:
        client.__class__ = VoiceClient
