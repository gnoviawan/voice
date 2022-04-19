# -*- coding: utf-8 -*-
from setuptools import setup

packages = ["voice"]

package_data = {"": ["*"]}

install_requires = [
    "PyNaCl>=1.5.0,<2.0.0",
    "discord-py-interactions @ " "git+https://github.com/interactions-py/library.git@4.1.1-rc.1",
]

setup_kwargs = {
    "name": "interactions-voice",
    "version": "1.0.0",
    "description": "A voice-capable client for interactions.py",
    "long_description": "# voice\n_______\n\nHello! If you came across this library, you probably tried to implement "
    "voice functions with [interactions.py](https://github.com/interactions-py/library), "
    "but that was not possible, since it natively does not support voice.\nBut don't worry! With "
    "`voice` you can do exactly that! We not only add the `VOICE_STATE_UPDATE` event but also the "
    "ability to connect to voice channels and transmit audio.\n\nThis will be a basic guide on "
    "how to install and use this library.\n\n## "
    "Installation\n_________________________________________________________\n\n```bash\npip "
    "install -U interactions-voice\n```\n\n## But what exactly is this library and what does it "
    "do?\n_________________________________________________________\n\nThis library is an "
    "extension for `interactions.py`, what gives it the ability to connect to voice and send data "
    "and to \nlisten to the ``voice_state_update`` event.\n\n## Example "
    "usage:\n__________________\n\n```python\nfrom interactions import CommandContext, "
    "Channel\nfrom interactions.ext.voice import VoiceState, VoiceClient\n\nbot: VoiceClient = "
    'VoiceClient(token="...")\n\n@bot.event\nasync def on_voice_state_update(vs: VoiceState):\n   '
    ' print(vs.self_mute)\n    ...\n\n@bot.command(name="connect", description="...", '
    "options=[...])\nasync def connect(ctx: CommandContext, channel: Channel):\n    await "
    "bot.connect_vc(channel_id=int(channel.id), guild_id=int(ctx.guild_id), self_deaf=True, "
    'self_mute=False)\n    await bot.play(file="C:/...")\n```\n',
    "author": "EdVraz",
    "author_email": "edvraz12@gmail.com",
    "maintainer": None,
    "maintainer_email": None,
    "url": "https://github.com/interactions-py/voice",
    "packages": packages,
    "package_data": package_data,
    "install_requires": install_requires,
    "python_requires": ">=3.8.6,<4.0.0",
}

setup(**setup_kwargs)
