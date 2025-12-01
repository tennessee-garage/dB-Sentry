"""DBAMessage: dB-Sentry topic parsing.

DBAMessage now inherits from `mqtt.message.Message` and provides
convenience attributes for `db_sentry/$sensor/$band` topics.
"""
from typing import Optional

from .message import Message


class DBAMessage(Message):
    """Message subclass for `db_sentry/$sensor/$band` topics."""

    @staticmethod
    def owns_topic(topic: str) -> bool:
        """Check if the message topic matches the `db_sentry/$sensor/$band` pattern."""
        return topic.startswith('db_sentry/')

    def __init__(self, topic: str, value):
        super().__init__(topic, value)
        self.sensor: Optional[str] = None
        self.band: Optional[str] = None
        self._is_dba: bool = False

        if len(self.parts) >= 3 and self.parts[0] == 'db_sentry':
            self._is_dba = True
            self.sensor = self.parts[1]
            self.band = self.parts[2]

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"DBAMessage(topic={self.topic!r}, sensor={self.sensor!r}, band={self.band!r})"
