from interactions.client import Client


class VoiceClient(Client):
    """
    A modified ``Client`` class what allows connecting to voice_channels
    """

    async def connect(
        self,
        channel_id: int,
        guild_id: int,
        self_deaf: bool = False,
        self_mute: bool = False,
    ) -> None:
        """
        Connects the bot to a voice channel.
        :param channel_id:
        :param guild_id:
        :param self_deaf:
        :param self_mute:
        :return:
        """

        await self._websocket._connect(
            guild_id=guild_id, channel_id=channel_id, self_mute=self_mute, self_deaf=self_deaf
        )

    # TODO: more methods
