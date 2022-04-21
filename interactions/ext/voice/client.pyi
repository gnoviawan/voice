from interactions.client.bot import Client

from .websocket import VoiceWebSocketClient


class VoiceClient(Client):
    _websocket: VoiceWebSocketClient
    def __init__(self, token: str, **kwargs) -> None: ...
    async def connect_vc(
        self,
        channel_id: int,
        guild_id: int,
        self_deaf: bool = False,
        self_mute: bool = False,
    ) -> None: ...
    async def play(self, guild_id: int) -> None: ...
    async def disconnect_vc(
        self,
        guild_id: int,
    ) -> None: ...
    async def disconnect_all_vc(self) -> None: ...
