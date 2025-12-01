"""Generic message base class for MQTT topic representations within the `mqtt` package."""
from typing import List


class Message:
	"""A minimal generic message representation.

	Attributes:
		topic: original topic string
		parts: list of topic path segments
	"""

	# Determines if this class can parse the given topic
	@staticmethod
	def owns_topic(topic: str) -> bool:
		return False

	def __init__(self, topic: str, value):
		self.topic: str = topic or ""
		self.parts: List[str] = self.topic.split('/') if self.topic else []
		self.value = value

	def is_dba_message(self) -> bool:
		"""Override in subclasses for pattern checks. Defaults to False."""
		return False

	def __repr__(self) -> str:  # pragma: no cover - trivial
		return f"Message(topic={self.topic!r}, value={self.value!r})"