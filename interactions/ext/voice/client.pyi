from interactions.client import Client
from .voice import VoiceWebSocketClient, VoiceCache

class VoiceClient(Client):
    _websocket: VoiceWebSocketClient
    _cache: VoiceCache

    async def connect(
        self,
        channel_id: int,
        guild_id: int,
        self_deaf: bool = False,
        self_mute: bool = False,
    ) -> None: ...
