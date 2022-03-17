from interactions.api.enums import OpCodeType
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

        return await self._websocket._connect(
            guild_id=guild_id, channel_id=channel_id, self_mute=self_mute, self_deaf=self_deaf
        )

    async def disconnect(
        self,
        guild_id: int,
    ) -> None:
        """
        Removes the bot of the channel
        :param guild_id:
        :return:
        """

        # todo error
        self._websocket._voice_connections[guild_id].close = True

        await self._websocket._send_packet(
            {
                "op": OpCodeType.VOICE_STATE,
                "d": {
                    "guild_id": guild_id,
                    "channel_id": None,
                },
            }
        )
        del self._websocket._voice_connections[guild_id]

    # TODO: more methods
