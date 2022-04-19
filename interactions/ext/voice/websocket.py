from asyncio import Event
from typing import Any, Dict, List, Optional, Tuple, Union

from aiohttp import WSMessage, WSMsgType
from aiohttp.http import WS_CLOSED_MESSAGE, WS_CLOSING_MESSAGE
from interactions.api.cache import Cache, Item, Storage
from interactions.api.enums import OpCodeType
from interactions.api.gateway.client import WebSocketClient
from interactions.api.models.misc import MISSING
from interactions.api.models.presence import ClientPresence
from interactions.base import get_logger

from .state import VoiceState
from .voice import VoiceConnectionWebSocketClient

log = get_logger("voice")


class VoiceCache(Cache):
    """
    A modified cache to store VoiceState data.
    """

    def __init__(self):
        super().__init__()
        self.voice_states: Storage = Storage()


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
        me=MISSING,
    ) -> None:
        super().__init__(token, intents, session_id, sequence)
        self._http.cache = VoiceCache()
        self._voice_connect_data: Dict[str, dict] = {}
        self._voice_connections: Dict[str, VoiceConnectionWebSocketClient] = {}
        self.user = me

    @property
    async def __receive_packet_stream(self) -> Optional[Dict[str, Any]]:
        """
        Receives a stream of packets sent from the Gateway.

        :return: The packet stream.
        :rtype: Optional[Dict[str, Any]]
        """

        packet: WSMessage = await self._client.receive()

        if packet == WSMsgType.CLOSE:
            await self._disconnect_all()
            await self._client.close()
            return packet

        elif packet == WS_CLOSED_MESSAGE:
            return packet

        elif packet == WS_CLOSING_MESSAGE:
            await self._client.close()
            return WS_CLOSED_MESSAGE

    async def _handle_connection(
        self,
        stream: Dict[str, Any],
        shard: Optional[List[Tuple[int]]] = MISSING,
        presence: Optional[ClientPresence] = MISSING,
    ) -> None:
        op: Optional[int] = stream.get("op")
        event: Optional[str] = stream.get("t")
        data: Optional[Dict[str, Any]] = stream.get("d")

        if op != OpCodeType.DISPATCH or event not in {
            "VOICE_STATE_UPDATE",
            "VOICE_SERVER_UPDATE",
        }:
            return await super()._handle_connection(stream, shard, presence)

        log.debug(f"{event}: {data}")
        await self._dispatch_voice_event(event, data, stream)

    async def _dispatch_voice_event(self, event: str, data: dict) -> None:
        if event == "VOICE_STATE_UPDATE":
            if data["user_id"] == self.user.id:  # TODO: check if user joined.
                if data["guild_id"] not in self._voice_connect_data:
                    self._voice_connect_data[data["guild_id"]] = {}

                self._voice_connect_data[data["guild_id"]].update(
                    session_id=data["session_id"],
                    user_id=int(data["user_id"]),
                )

            _item = Item(id=data["user_id"], value=[data])

            # Fix this :P
            # this isn't a problem, actually. It actually makes the list per user.
            # Also an user can only have one voice state

            if _item.id in self._http.cache.voice_states.values.keys():
                if len(self._http.cache.voice_states.values[_item.id]) >= 2:
                    self._http.cache.voice_states.values[_item.id].pop(0)
                self._http.cache.voice_states.values[_item.id].extend(_item.value)
                # doing it manually since the update meth is broken.
            else:
                self._http.cache.voice_states.add(_item)

            data["_client"] = self._http

            name: str = event.lower()
            self._dispatch.dispatch(f"on_{name}", VoiceState(**data))  # noqa
        else:
            if data["guild_id"] not in self._voice_connect_data:
                self._voice_connect_data[data["guild_id"]] = {}

            self._voice_connect_data[data["guild_id"]].update(
                token=data["token"], endpoint=data["endpoint"]
            )
            self._voice_connect_data[data["guild_id"]]["can_return"].set()
            await self._voice_connect(data["guild_id"])

        self._dispatch.dispatch("raw_socket_create", data)

    async def _connect_vc(
        self,
        guild_id: Union[int, str],
        channel_id: Union[int, str],
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
        guild_id, channel_id = str(guild_id), str(channel_id)
        payload: dict = {
            "op": OpCodeType.VOICE_STATE,
            "d": {
                "channel_id": channel_id,
                "guild_id": guild_id,
                "self_deaf": self_deaf,
                "self_mute": self_mute,
            },
        }
        self._voice_connect_data[guild_id] = {}
        self._voice_connect_data[guild_id]["can_return"] = Event()
        await self._send_packet(data=payload)
        await self._voice_connect_data[guild_id]["can_return"].wait()

    async def _voice_connect(self, guild_id: str) -> None:
        voice_client = VoiceConnectionWebSocketClient(
            guild_id=int(guild_id),
            data=self._voice_connect_data[guild_id],
            _http=self._http,
        )
        self._voice_connections[guild_id] = voice_client
        return await voice_client._connect()

    async def _disconnect_vc(self, guild_id: str) -> None:
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

    async def _disconnect_all_vc(self) -> None:
        """
        Closes all existing voice connections.
        """

        for guild_id in self._voice_connections:
            await self._disconnect_vc(guild_id)
