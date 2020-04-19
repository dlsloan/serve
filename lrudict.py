import threading
import time

class LRUDict(dict):
    def __init__(self, *pargs, timeout=40, maxcount=1000, **kwargs):
        self.timeout = timeout
        self.maxcount = maxcount
        self.mtx = threading.RLock()
        super().__init__(*pargs, **kwargs)

    def __enter__(self):
        return self.mtx.__enter__()

    def __exit__(self, *pargs, **kwargs):
        return self.mtx.__exit__(*pargs, **kwargs)

    def __setitem__(self, key, val):
        with self.mtx:
            if key in self:
                del self[key]
            super().__setitem__(key, (time.time() + self.timeout, val))
            while len(self) > self.maxcount:
                del self[self.oldest()]
            while len(self) > 0 and time.time() > super().__getitem__(self.oldest())[0]:
                del self[self.oldest()]

    def __getitem__(self, key):
        with self.mtx:
            val = super().__getitem__(key)[1]
            del self[key]
            super().__setitem__(key, (time.time() + self.timeout, val))
            return val

    def oldest(self):
        with self.mtx:
            for k in self:
                return k