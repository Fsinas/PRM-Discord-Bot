import time
from collections import Counter

class Metrics:
    def __init__(self):
        self.counters = Counter()
        self.start_time = time.time()

    def incr(self, key:str, n:int=1):
        self.counters[key]+=n

    def snapshot(self):
        return dict(self.counters)

metrics = Metrics()