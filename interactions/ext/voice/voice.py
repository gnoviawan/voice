try:
    from orjson import dumps, loads
except ImportError:
    from json import dumps, loads

from asyncio import Event, Task, ensure_future, sleep
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple

from aiohttp import WSMessage, WSMsgType
from aiohttp.http import WS_CLOSED_MESSAGE, WS_CLOSING_MESSAGE
from interactions.api.error import InteractionException
from interactions.api.gateway.heartbeat import _Heartbeat
from interactions.api.http.client import HTTPClient
from interactions.api.models.misc import MISSING
from interactions.base import get_logger
from nacl.secret import SecretBox  # noqa, for now

log = get_logger("voice")


class VoiceException(InteractionException):
    """
    This is a derivation of InteractionException in that this is used to represent Voice closing OP codes.
    :ivar ErrorFormatter _formatter: The built-in formatter.
    :ivar dict _lookup: A dictionary containing the values from the built-in Enum.
    """

    __slots__ = ("_type", "_lookup", "__type", "_formatter", "kwargs")

    def __init__(self, __type, **kwargs):
        super().__init__(__type, **kwargs)

    @staticmethod
    def lookup() -> dict:
        return {
            4001: "Unknown opcode. Check your gateway opcode and/or payload.",
            4002: "Failed to decode payload. Check your gateway payload.",
            4003: "Not authenticated. Identify before sending a payload.",
            4004: "Authentication failed. The token used while identifying is invalid.",
            4005: "Already authenticated.",
            4006: "Session no longer valid.",
            4009: "Timed out. Reconnect and try again.",
            4011: "Voice server not found.",
            4012: "Unknown protocol.",
            4014: "Disconnected. You got removed from the channel or the channel itself was deleted. Do not reconnect.",
            4016: "Unknown encryption mode.",
        }


class VoiceOpCodeType(IntEnum):
    IDENTIFY = 0
    SELECT_PROTOCOL = 1
    READY = 2
    HEARTBEAT = 3
    SESSION_DESCRIPTION = 4
    SPEAKING = 5
    HEARTBEAT_ACK = 6
    RESUME = 7
    HELLO = 8
    RESUMED = 9
    CLIENT_DISCONNECT = 13


class SpeakingType(IntEnum):
    MICROPHONE = 1 << 0
    SOUND_SHARE = 1 << 1
    PRIORITY = 1 << 2


class VoiceConnectionWebSocketClient:
    def __init__(self, guild_id: int, data: dict, _http: HTTPClient):
        self.guild_id = guild_id
        self.session_id = data.get("session_id")
        self.endpoint = f"wss://{data.get('endpoint')}?v=4"
        self.token = data.get("token")
        self.user_id = data.get("user_id")
        self._http = _http
        self.__task = None
        self._secret_key: bytes = None
        self._port = None
        self._ip = None
        self._mode = None
        self._closed = False
        self._close = (
            False  # determines whether closing of the connection is wanted or not -> disconnect
        )
        self._media_session_id = None
        self.__heartbeater: _Heartbeat = _Heartbeat(loop=None)
        self._heartbeats = 0
        self.ready = Event()

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

    def _reset(self):
        self._client = None

        self._secret_key = None

        self._port: str = None
        self._ip: int = None
        self._mode: str = None

        self._closed = False
        self._close = False

        self._media_session_id = None

        self._heartbeats = 0
        self.__heartbeater.delay = 0.0

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
        self._reset()

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
                    if self._close and self._client.close_code == 4014:
                        log.debug("Closing Voice Connection.")
                        break
                    else:
                        code = self._client.close_code or stream
                        raise VoiceException(code)

                await self._handle_connection(stream, shard)

    async def __heartbeat(self):
        payload: dict = {
            "op": VoiceOpCodeType.HEARTBEAT,
            "d": self._heartbeats,
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

    async def _select_protocol(self):

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

        log.debug(f"Voice Gateway Event: {stream}")

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
            await self._select_protocol()
            self._ready = data
            log.debug(f"READY (session_id: {self.session_id})")
            self.ready.set()

        if op == VoiceOpCodeType.HEARTBEAT:
            await self.__heartbeat()

        if op == VoiceOpCodeType.HEARTBEAT_ACK:
            log.debug("HEARTBEAT_ACK")
            self._heartbeats += 1
            self.__heartbeater.event.set()

        if op == VoiceOpCodeType.SESSION_DESCRIPTION:
            self._secret_key = bytes(data["secret_key"])
            self._media_session_id = data["media_session_id"]
            self._mode = data["mode"]

        if op == VoiceOpCodeType.RESUME:
            await self.__resume()

        if op == VoiceOpCodeType.RESUMED:
            log.debug(f"RESUMED (session_id: {self.session_id})")

        # TODO: other opcodes

    async def _start_speaking(self) -> None:
        payload = {
            "op": VoiceOpCodeType.SPEAKING,
            "d": {"speaking": 1 << 0, "delay": 0, "ssrc": self.ssrc},
        }
        log.debug(f"SPEAKING: {payload}")
        await self._send_packet(payload)

    async def _stop_speaking(self) -> None:
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
            "d": {
                "token": self.token,
                "session_id": self.session_id,
                "server_id": self.guild_id,
            },
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
