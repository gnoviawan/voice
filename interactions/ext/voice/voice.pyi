import interactions
from interactions.api.models.misc import MISSING, DictSerializerMixin, Snowflake
from typing import Optional, Union, Tuple, Dict
from datetime import datetime
from interactions.api.models.member import Member
from interactions.api.gateway import WebSocketClient
from interactions.api.cache import Cache, Storage
from interactions.api.http.client import HTTPClient
# currently import error, fixed when the http-PR is merged. Because of this, required will be v4.1.1 and not v4.1.0

class VoiceCache(Cache):
    def __init__(self): ...
    voice_states: Storage

class VoiceWebSocketClient(WebSocketClient):
    def __init__(
        self,
        token,
        intents,
        session_id=MISSING,
        sequence=MISSING,
    ) -> None: ...
    __voice_connect_data: Dict[int, dict]
    def __contextualize(self, data: dict) -> object: ...
    def __sub_command_context(
            self, data: Union[dict, Option], context: object
    ) -> Union[Tuple[str], dict]: ...
    def __option_type_context(self, context: object, type: int) -> dict: ...
    def _dispatch_event(self, event: str, data: dict) -> None: ...
    async def _connect(
            self,
            guild_id: int,
            channel_id: int,
            self_mute: bool = False,
            self_deaf: bool = False,
    ): ...

class VoiceState(DictSerializerMixin):
    _client: HTTPClient
    _json: dict
    channel_id: Optional[Snowflake]
    guild_id: Optional[Snowflake]
    user_id: Snowflake
    member: Optional[Member]
    mute: bool
    deaf: bool
    self_video: bool
    self_mute: bool
    self_deaf: bool
    self_stream: Optional[bool]
    suppress: bool
    session_id: str
    request_to_speak_timestamp: Optional[datetime]

    @property
    def before(self) -> VoiceState: ...

def setup(client: interactions.Client, voice_client: bool = False): ...
