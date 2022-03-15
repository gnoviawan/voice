try:
    from orjson import dumps, loads
except ImportError:
    from json import dumps, loads

from asyncio import *  # noqa # isort and black battling on this,
from datetime import datetime
from logging import Logger
from sys import version_info
from time import perf_counter
from typing import Any, Dict, List, Optional, Tuple, Union

from aiohttp import WSMessage

import interactions
from interactions import Member, Option
from interactions.api.cache import Cache, Item, Storage
from interactions.api.enums import OpCodeType
from interactions.api.error import GatewayException
from interactions.api.gateway import WebSocketClient, _Heartbeat
from interactions.api.http import HTTPClient  # TODO: change to new HTTP
from interactions.api.models.misc import (MISSING, DictSerializerMixin,
                                          Snowflake)
from interactions.base import get_logger

from .client import VoiceClient
from .enums import VoiceOpCodeType

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
    """

    def __init__(self, guild_id: int, data: dict, _http: HTTPClient):
        self.guild_id = guild_id
        self.session_id = data.get("session_id")
        self.endpoint = f"wss://{data.get('endpoint')}"
        self.token = data.get("token")
        self.user_id = data.get("user_id")
        self._http = _http
        try:
            self._loop = get_event_loop() if version_info < (3, 10) else get_running_loop()  # noqa
        except RuntimeError:
            self._loop = new_event_loop()  # noqa
        self.__heartbeater: _Heartbeat = _Heartbeat(
            loop=self._loop if version_info < (3, 10) else None
        )

    @property
    async def __receive_packet_stream(self) -> Optional[Dict[str, Any]]:
        """
        Receives a stream of packets sent from the Gateway.

        :return: The packet stream.
        :rtype: Optional[Dict[str, Any]]
        """

        packet: WSMessage = await self._client.receive()
        return loads(packet.data) if packet and isinstance(packet.data, str) else None

    async def _connect(
        self,
        shard: Optional[List[Tuple[int]]] = MISSING,
    ) -> None:
        """
        Establishes a client connection with the Gateway.

        :param shard?: The shards to establish a connection with. Defaults to ``None``.
        :type shard: Optional[List[Tuple[int]]]
        :param presence: The presence to carry with. Defaults to ``None``.
        :type presence: Optional[ClientPresence]
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
                print(stream)

                if stream is None:
                    continue
                if self._client is None:
                    await self._connect()
                    break

                if self._client.close_code in range(4010, 4014) or self._client.close_code == 4004:
                    raise GatewayException(self._client.close_code)

                await self._handle_connection(stream, shard)

    async def _manage_heartbeat(self) -> None:
        """Manages the heartbeat loop."""
        while True:
            if self._closed:
                await self.__restart()
            if self.__heartbeater.event.is_set():
                await self.__heartbeat()
                self.__heartbeater.event.clear()
                await sleep(self.__heartbeater.delay / 1000)  # noqa
            else:
                log.debug("HEARTBEAT_ACK missing, reconnecting...")
                await self.__restart()
                break

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
        :param presence: The presence to carry with. Defaults to ``None``.
        :type presence: Optional[ClientPresence]
        """
        op: Optional[int] = stream.get("op")
        data: Optional[Dict[str, Any]] = stream.get("d")

        log.debug(data)

        if op == VoiceOpCodeType.HELLO:
            self.__heartbeater.delay = data["heartbeat_interval"]
            self.__heartbeater.event.set()

            # if self.__task:
            #   self.__task.cancel()  # so we can reduce redundant heartbeat bg tasks.

            self.__task = ensure_future(self._manage_heartbeat())  # noqa

            await self.__identify(shard)

        # TODO: other opcode

    async def __identify(self, shard: Optional[List[Tuple[int]]] = None) -> None:
        """
        Sends an ``IDENTIFY`` packet to the gateway.

        :param shard?: The shard ID to identify under.
        :type shard: Optional[List[Tuple[int]]]
        :param presence?: The presence to change the bot to on identify.
        :type presence: Optional[ClientPresence]
        """
        print("run")
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
        self._last_send = perf_counter()
        _data = dumps(data) if isinstance(data, dict) else data
        packet: str = _data.decode("utf-8") if isinstance(_data, bytes) else _data
        await self._client.send_str(packet)
        log.debug(packet)


class VoiceWebSocketClient(WebSocketClient):
    """
    A modified WebSocketClient for Voice Events.
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

    # Note: calling a "private" function of WebSocketClient will have to be super()-ed like below
    def __contextualize(self, data: dict) -> object:
        return super()._WebSocketClient__contextualize(data)

    def __sub_command_context(
        self, data: Union[dict, Option], context: object
    ) -> Union[Tuple[str], dict]:
        return super()._WebSocketClient__sub_command_context(data, context)

    def __option_type_context(self, context: object, type: int) -> dict:
        return super()._WebSocketClient__option_type_context(context, type)

    def _dispatch_event(self, event: str, data: dict) -> None:
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

        self._dispatch.dispatch("raw_socket_create", data)

    async def _connect(
        self,
        guild_id: int,
        channel_id: int,
        self_mute: bool = False,
        self_deaf: bool = False,
    ):
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
        await sleep(2)  # noqa
        voice_client = VoiceConnectionWebSocketClient(
            guild_id=int(guild_id), data=self.__voice_connect_data[int(guild_id)], _http=self._http
        )
        await voice_client._connect()


class VoiceState(DictSerializerMixin):
    """
    A class object representing the gateway event ``VOICE_STATE_UPDATE``

    TODO: document
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
        self.member = Member(**self.member) if self._json.get("member") else None
        self.channel_id = Snowflake(self.channel_id) if self._json.get("channel_id") else None
        self.guild_id = Snowflake(self.guild_id) if self._json.get("guild_id") else None
        self.user_id = Snowflake(self.user_id) if self._json.get("user_id") else None
        self.request_to_speak_timestamp = (
            datetime.fromisoformat(self.request_to_speak_timestamp)
            if self._json.get("request_to_speak_timestamp")
            else None
        )

    @property
    def before(self) -> "VoiceState":
        return VoiceState(**self._client.cache.voice_states.get(str(self.user_id))[0])

    # TODO: Helpers


WebSocketClient = VoiceWebSocketClient


def _update_instances(client: interactions.Client):
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
        new_websocket.last_ack = old_websocket._last_ack

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


def setup(client: interactions.Client, voice_client: bool = False):
    """
    Sets up the voice ext. If `voice_client` is set to true, the client will be modified, so it can connect to a
    voice channel. Otherwise, this ext will only dispatch voice state updates.
    """
    _update_instances(client)
    if voice_client:
        client.__class__ = VoiceClient
