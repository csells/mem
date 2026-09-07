"""Generic cache engine; policy belongs to each component."""
from collections import OrderedDict


class ResponseCache:
    def __init__(self, policy, clock):
        if policy["eviction_policy"] != "fifo":
            raise ValueError("only FIFO is implemented by this engine")
        self.policy = dict(policy)
        self.clock = clock
        self.entries = OrderedDict()

    def _purge(self):
        now = self.clock()
        for key, (created, _) in list(self.entries.items()):
            if now - created >= self.policy["ttl_seconds"]:
                del self.entries[key]

    def get(self, key, loader):
        self._purge()
        stored_key = self.policy["namespace"] + ":" + key
        if stored_key in self.entries:
            return self.entries[stored_key][1]
        value = loader()
        if value is not None or self.policy["cache_misses"]:
            while len(self.entries) >= self.policy["max_entries"]:
                self.entries.popitem(last=False)
            self.entries[stored_key] = (self.clock(), value)
        return value

    def keys(self):
        self._purge()
        return list(self.entries)
