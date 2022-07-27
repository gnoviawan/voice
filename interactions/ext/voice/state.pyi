from datetime import datetime
from typing import Optional

from interactions.api.models.channel import Channel
from interactions.api.models.guild import Guild
from interactions.api.models.member import Member
from interactions.api.models.misc import Snowflake
from interactions.api.models.attrs_utils import ClientSerializerMixin, define

@define()
class VoiceState(ClientSerializerMixin):

    channel_id: Optional[Snowflake]
    guild_id: Optional[Snowflake]
    user_id: Optional[Snowflake]
    member: Optional[Member]
    request_to_speak_timestamp: Optional[datetime]
    def __init__(self, **kwargs): ...
    @property
    def joined(self) -> bool: ...
    @property
    def before(self) -> "VoiceState": ...
    async def mute_member(self, reason: Optional[str]) -> Member: ...
    async def deafen_member(self, reason: Optional[str]) -> Member: ...
    async def move_member(self, channel_id: int, *, reason: Optional[str]) -> Member: ...
    async def get_channel(self) -> Channel: ...
    async def get_guild(self) -> Guild: ...
