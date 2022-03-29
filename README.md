#voice
_______

Hello! If you came across this library, you probably tried to implement voice functions with [interactions.py](https://github.com/interactions-py/library), but that was not possible, since it natively does not support voice.
But don't worry! With `voice` you can do exactly that! We add not only the `VOICE_STATE_UPDATE` event but also the ability to connect to voice channels and transmit audio.

This will be a basic guide on how to install and use this library.

## Installation
_________________________________________________________

```bash
pip install -U interactions-voice
```

## But what exactly is this library and what does it do?
_________________________________________________________

This library is an extension for `interactions.py`, what gives it the ability to connect to voice and send data.

There are two ways to use this library:

- 1: Only load the library. In that case you will only get the ability to listen to the ``VOICE_STATE_UPDATE`` Event.
- 2: Load the library with the argument ``voice_client=True``. In that case, it will replace your ``Client`` with a ``VoiceClient``.
    Those are essentially the same, except the ``VoiceClient`` adds methods to connect to voice channels and send data to them.
