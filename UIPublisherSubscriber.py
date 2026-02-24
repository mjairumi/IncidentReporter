# UIPublisherSubscriber.py
import asyncio
import json
from PublisherSubscriber import IncidentSubscriber, IncidentEvent
from Logger import logger


class UIPublisherSubscriber(IncidentSubscriber):
    def __init__(self):
        self._clients: set[asyncio.Queue] = set()
        self._shutdown_event = asyncio.Event()  # Signals all generators to stop

    def connect(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self._clients.add(queue)
        logger.info(f"[UI] Client connected — total: {len(self._clients)}")
        return queue

    def disconnect(self, queue: asyncio.Queue):
        self._clients.discard(queue)
        logger.info(f"[UI] Client disconnected — total: {len(self._clients)}")

    def shutdown(self):
        """Called during FastAPI shutdown — unblocks all waiting generators."""
        logger.info(f"[UI] Shutting down — disconnecting {len(self._clients)} client(s).")
        self._shutdown_event.set()

    async def on_incident(self, event: IncidentEvent):
        if not self._clients:
            return
        payload = json.dumps({
            "source":     event.source,
            "status":     event.incident.status,
            "message":    event.incident.message,
            "detectedAt": event.detected_at.isoformat(),
        })
        await asyncio.gather(*[client.put(payload) for client in self._clients])

    async def wait_for_event(self, queue: asyncio.Queue) -> str | None:
        """
        Waits for either a new incident OR shutdown.
        Returns payload string, or None if shutting down.
        """
        incident_task = asyncio.create_task(queue.get())
        shutdown_task = asyncio.create_task(self._shutdown_event.wait())

        try:
            done, pending = await asyncio.wait(
                [incident_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel the loser
            for task in pending:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

            if shutdown_task in done:
                return None  # Shutdown signal received

            return incident_task.result()

        except asyncio.CancelledError:
            incident_task.cancel()
            shutdown_task.cancel()
            raise
    async def wait_for_all_disconnected(self, timeout: int = 5):
        """Wait until all SSE clients have disconnected or timeout expires."""
        deadline = asyncio.get_event_loop().time() + timeout

        while self._clients:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                logger.warning(
                    f"[UI] Shutdown timeout — force disconnecting "
                    f"{len(self._clients)} remaining client(s)."
                )
                self._clients.clear()
                break

            logger.info(f"[UI] Waiting for {len(self._clients)} client(s) to disconnect...")
            await asyncio.sleep(0.1)

        logger.info("[UI] All clients disconnected.")