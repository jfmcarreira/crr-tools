import asyncio
from threading import Lock

STATE_CHANGED = 'event: state-changed\ndata: {"type":"state-changed"}\n\n'


class StateChangeEvents:
    def __init__(self, heartbeat_seconds: float = 25):
        self.heartbeat_seconds = heartbeat_seconds
        self.clients = {}
        self.lock = Lock()

    def broadcast(self) -> None:
        with self.lock:
            for queue, loop in self.clients.items():
                loop.call_soon_threadsafe(queue.put_nowait, STATE_CHANGED)

    def close(self) -> None:
        with self.lock:
            for queue, loop in self.clients.items():
                loop.call_soon_threadsafe(queue.put_nowait, None)

    async def stream(self):
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        with self.lock:
            self.clients[queue] = loop
        next_heartbeat = loop.time() + self.heartbeat_seconds
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), max(0, next_heartbeat - loop.time()))
                    if message is None:
                        return
                    yield message
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    next_heartbeat = loop.time() + self.heartbeat_seconds
        finally:
            with self.lock:
                self.clients.pop(queue, None)
