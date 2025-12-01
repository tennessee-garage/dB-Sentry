from collections import deque
import os
import time


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
		return int(sum(self.dq) / len(self.dq))
