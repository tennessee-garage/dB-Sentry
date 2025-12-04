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
		
	def append(self, value):
		now = time.time()
		self.dq.append((now, value))

		# prune old samples outside the averaging window
		while self.dq and (now - self.dq[0][0]) > self.window_seconds:
			self.dq.popleft()

	def average(self) -> int:
		if not self.dq:
			return 0
		
		average = sum(value for _, value in self.dq) / len(self.dq)
		logger.debug(f"Average: {average:.2f}; items: {[value for _, value in self.dq]}")
		return int(average)