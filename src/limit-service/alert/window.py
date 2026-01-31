from collections import deque
import os
import time
import logging

logger = logging.getLogger('limit-service.alert.window')


class Window:
	DEFAULT_WINDOW_SECONDS = int(os.getenv('AVERAGE_WINDOW_SECONDS', '60'))

	def __init__(self, window_seconds=DEFAULT_WINDOW_SECONDS):
		self.window_seconds = window_seconds
		self.dq = deque()
	
	def _prune(self, now: float):
		"""Remove samples outside the current window."""
		while self.dq and (now - self.dq[0][0]) > self.window_seconds:
			self.dq.popleft()
		
	def append(self, value):
		now = time.time()
		self.dq.append((now, value))
		self._prune(now)

	def average(self) -> int:
		if not self.dq:
			return 0
		
		average = sum(value for _, value in self.dq) / len(self.dq)
		logger.debug(f"Average: {average:.2f}; items: {[value for _, value in self.dq]}")
		return int(average)
	
	def update_window(self, window_seconds: int):
		"""Update the window size, pruning samples outside the new window."""
		self.window_seconds = window_seconds
		self._prune(time.time())