"""Factory for creating message instances based on topic patterns.

Usage:
    from mqtt.factory import create_message
    msg = create_message(topic)
"""
from .message import Message
from .dba_message import DBAMessage


def create_message(topic: str, value) -> Message:
    """Return a Message subclass instance appropriate for `topic`.

    Currently supports `DBAMessage` for `db_sentry/...` topics and
    falls back to the generic `Message` for unknown topics.
    """
    if DBAMessage.owns_topic(topic):
        return DBAMessage(topic, value)
    return Message(topic, value)
