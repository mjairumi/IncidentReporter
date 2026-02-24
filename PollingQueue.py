import asyncio
from typing import Optional
from PollingInterface import *
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from Logger import logger
from PublisherSubscriber import IncidentEvent, IncidentEventPublisher


class PollingObject:

    def __init__(self, polling: PollingInterface):
        self.polling = polling
        self.pollingFrequency: int = polling.getPollingFrequency()
        self.lastPolled: Optional[datetime] = None

    def is_due(self) -> bool:
        if self.lastPolled is None:
            return True
        return datetime.now() >= self.lastPolled + timedelta(seconds=self.pollingFrequency)


class PollingQueue():

    def __init__(self, publisher: IncidentEventPublisher):
        self.queue: list[PollingObject] = []
        self.publisher = publisher
        self._scheduler_task: Optional[asyncio.Task] = None
        self._executing: set[PollingObject] = set()
        self._active_tasks: set[asyncio.Task] = set()  # Track all spawned tasks
    
    def add(self, poll: PollingInterface):
        self.queue.append(PollingObject(poll))

    async def start(self):
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info(f"[PollingQueue] Started with {len(self.queue)} pollers.")

    async def stop(self):
        # 1. Stop the scheduler from spawning new tasks
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

        # 2. Cancel all in-flight poll tasks
        if self._active_tasks:
            logger.info(f"[PollingQueue] Cancelling {len(self._active_tasks)} active poll tasks...")
            for task in list(self._active_tasks):
                task.cancel()

            # Wait for all of them to finish cancelling
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
            self._active_tasks.clear()

        logger.info("[PollingQueue] Stopped cleanly.")

    async def _scheduler_loop(self):
        try:
            while True:
                due = [
                    obj for obj in self.queue
                    if obj.is_due() and obj not in self._executing
                ]

                for obj in due:
                    self._executing.add(obj)
                    task = asyncio.create_task(self._run_poll(obj))
                    self._active_tasks.add(task)                        # Track it
                    task.add_done_callback(self._active_tasks.discard)  # Auto-remove when done

                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("[PollingQueue] Scheduler loop cancelled — shutting down.")
            raise  # CRITICAL — must re-raise so the task is marked as cancelled

    async def _run_poll(self, obj: PollingObject):
        try:
            logger.info("Why are you not stopping")
            result: PollResult = await obj.polling.poll()
                
            obj.lastPolled = datetime.now()  # Only update AFTER completion now
            await self._handle_result(obj, result)
        except asyncio.CancelledError:
            logger.info(f"[{obj.polling.__class__.__name__}] Poll cancelled during shutdown.")
        except asyncio.TimeoutError:
            logger.error(f"[{obj.polling.__class__.__name__}] Timed out.")
        except Exception as e:
            logger.error(f"[{obj.polling.__class__.__name__}] Error: {e}")
        finally:
            self._executing.discard(obj)
    
    async def _handle_result(self, obj: PollingObject, result: PollResult):
        # if result.new_frequency is not None:
        #     logger.info(
        #         f"[{obj.polling.__class__.__name__}] "
        #         f"Frequency updated: {obj.pollingFrequency}s -> {result.new_frequency}s"
        #     )
        #     obj.pollingFrequency = result.new_frequency

        if result.incident is not None:
            event = IncidentEvent(
                incident=result.incident,
                source=obj.polling.__class__.__name__
            )
            # task = asyncio.create_task(
            #     self.publisher.publish(event)
            # )
            # task.add_done_callback(PollingQueue._on_publish_error)
            await self.publisher.publish(event)
