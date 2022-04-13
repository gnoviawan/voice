from datetime import datetime
from typing import Optional

from interactions.api.models.channel import Channel
from interactions.api.models.guild import Guild
from interactions.api.models.member import Member
from interactions.api.models.misc import DictSerializerMixin, Snowflake


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
    def joined(self) -> bool:
        """
        Whether the user joined the channel.
        :rtype: bool
        """
        return self.channel_id is not None

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
        :rtype: Member
        """
        return await self.member.modify(guild_id=int(self.guild_id), mute=True, reason=reason)

    async def deafen_member(self, reason: Optional[str]) -> Member:
        """
        Deafens the current member.
        :param reason: The reason of the deafening, optional
        :type reason: str
        :return: The modified member object
        :rtype: Member
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
        :rtype: Member
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
