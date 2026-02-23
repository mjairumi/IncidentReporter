
import asyncio
from typing import Optional

from PollingInterface import *

import asyncio
from abc import ABC, abstractmethod
from collections import deque
from contextlib import asynccontextmanager

from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field
from DummyServicePoller import *
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
        self._task: Optional[asyncio.Task] = None
        self._executing: set[PollingObject] = set()
    
    def add(self, poll: PollingInterface):
        self.queue.append(PollingObject(poll))

    async def start(self):
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Polling pipeline started.")

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Polling pipeline stopped.")

    async def _scheduler_loop(self):
        while True:
            due = [
                obj for obj in self.queue
                if obj.is_due() and obj not in self._executing  # Check both conditions
            ]

            if due:
                for obj in due:
                    self._executing.add(obj)

                await asyncio.gather(*[
                    self._run_poll(obj) for obj in due
                ], return_exceptions=True)

            await asyncio.sleep(1)

    

    async def _run_poll(self, obj: PollingObject):
        try:
            result: PollResult = await obj.polling.poll()
            obj.lastPolled = datetime.now()  # Only update AFTER completion now
            await self._handle_result(obj, result)
        except Exception as e:
            logger.error(f"Error polling {obj.polling.__class__.__name__}: {e}")
        finally:
            self._executing.discard(obj)
    
    async def _handle_result(self, obj: PollingObject, result: PollResult):
        if result.new_frequency is not None:
            logger.info(
                f"[{obj.polling.__class__.__name__}] "
                f"Frequency updated: {obj.pollingFrequency}s -> {result.new_frequency}s"
            )
            obj.pollingFrequency = result.new_frequency

        if result.incident is not None:
            event = IncidentEvent(
                incident=result.incident,
                source=obj.polling.__class__.__name__
            )
            await self.publisher.publish(event)