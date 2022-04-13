# voice
_______

Hello! If you came across this library, you probably tried to implement voice functions with [interactions.py](https://github.com/interactions-py/library), but that was not possible, since it natively does not support voice.
But don't worry! With `voice` you can do exactly that! We not only add the `VOICE_STATE_UPDATE` event but also the ability to connect to voice channels and transmit audio.

This will be a basic guide on how to install and use this library.

## Installation
_________________________________________________________

```bash
pip install -U interactions-voice
```

## But what exactly is this library and what does it do?
_________________________________________________________

This library is an extension for `interactions.py`, what gives it the ability to connect to voice and send data and to
listen to the ``voice_state_update`` event.

## Example usage:
__________________

```python
from interactions import CommandContext, Channel
from interactions.ext.voice import VoiceState, VoiceClient

bot: VoiceClient = VoiceClient(token="...")

@bot.event
async def on_voice_state_update(vs: VoiceState):
    print(vs.self_mute)
    ...

@bot.command(name="connect", description="...", options=[...])
async def connect(ctx: CommandContext, channel: Channel):
    await bot.connect_vc(channel_id=int(channel.id), guild_id=int(ctx.guild_id), self_deaf=True, self_mute=False)
    await bot.play(file="C:/...")
```
