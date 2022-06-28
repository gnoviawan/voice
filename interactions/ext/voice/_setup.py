from typing import Coroutine

from interactions.client.bot import Client

from ._dummy import _VoiceClient
from .websocket import VoiceWebSocketClient

__all__ = "setup"


def setup(_client: Client):
    _websocket = VoiceWebSocketClient(token=_client._token, intents=_client._intents, me=_client.me)
    _voice_client = _VoiceClient()

    for attrib in _client._websocket.__slots__:
        if attrib != "_http":
            if attrib.startswith("__"):
                attrib = f"_WebSocketClient{attrib}"
            setattr(_websocket, attrib, getattr(_client._websocket, attrib))
        else:
            for _attrib in _client._websocket._http.__slots__:
                if _attrib != "cache":
                    setattr(_websocket._http, _attrib, getattr(_client._websocket._http, attrib))
                else:
                    for __attrib in _client._websocket._http.cache:
                        setattr(
                            _websocket._http.cache,
                            __attrib,
                            getattr(_client._websocket._http.cache, __attrib),
                        )

    _dir = dir(_client)
    for attrib in dir(_voice_client):
        if (
            not attrib.startswith("_")
            and not attrib.endswith("_")
            and isinstance(getattr(_voice_client, attrib), Coroutine)
            and attrib not in _dir
        ):
            setattr(_client, attrib, getattr(_voice_client, attrib))
