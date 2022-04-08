from logging import Logger

from interactions.base import get_logger
from interactions.client.bot import Client

log: Logger = get_logger("client")


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

        :param channel_id: The id of the channel to connect to
        :type channel_id: int
        :param guild_id: The id of the guild the channel belongs to
        :type guild_id: int
        :param self_deaf: whether the bot is self-deafened
        :type self_deaf: bool
        :param self_mute: whether the bot is self-muted
        :type self_mute: bool
        """

        if guild_id in self._websocket._voice_connections.keys():
            if self._websocket._voice_connections[guild_id]._closed is True:
                del self._websocket._voice_connections[guild_id]

            else:
                log.warning(
                    "Already connected to a voice channel! Disconnect before creating a new connection!"
                )
                return

        return await self._websocket._connect(
            guild_id=guild_id, channel_id=channel_id, self_mute=self_mute, self_deaf=self_deaf
        )

    async def disconnect(
        self,
        guild_id: int,
    ) -> None:
        """
        Removes the bot of the channel.

        :param guild_id: The id of the guild to disconnect the bot from
        :type guild_id: int
        """

        if guild_id not in self._websocket._voice_connections.keys():
            log.warning("Not connected to a voice channel!")
            return

        return await self._websocket._disconnect(guild_id=guild_id)

    async def play(self) -> None:
        raise NotImplementedError

    # TODO: play method
