from interactions.api.error import InteractionException


class VoiceException(InteractionException):
    """
    This is a derivation of InteractionException in that this is used to represent Voice closing OP codes.

    :ivar ErrorFormatter _formatter: The built-in formatter.
    :ivar dict _lookup: A dictionary containing the values from the built-in Enum.
    """

    __slots__ = ("_type", "_lookup", "__type", "_formatter", "kwargs")

    def __init__(self, __type, **kwargs):
        super().__init__(__type, **kwargs)

    @staticmethod
    def lookup() -> dict:
        return {
            4001: "Unknown opcode. Check your gateway opcode and/or payload.",
            4002: "Failed to decode payload. Check your gateway payload.",
            4003: "Not authenticated. Identify before sending a payload.",
            4004: "Authentication failed. The token used while identifying is invalid.",
            4005: "Already authenticated.",
            4006: "Session no longer valid.",
            4009: "Timed out. Reconnect and try again.",
            4011: "Voice server not found.",
            4012: "Unknown protocol.",
            4014: "Disconnected. You got removed from the channel or the channel itself was deleted. Do not reconnect.",
            4016: "Unknown encryption mode.",
        }
