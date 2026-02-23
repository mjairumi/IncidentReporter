from abc import ABC, abstractmethod
import asyncio

from Logger import logger
from dataclasses import dataclass, field
from DummyServicePoller import DummyServiceIncident
from datetime import datetime

@dataclass
class IncidentEvent:
    incident: DummyServiceIncident
    source: str
    detected_at: datetime = field(default_factory=datetime.now)
    
class IncidentSubscriber(ABC):

    @abstractmethod
    async def on_incident(self, event: IncidentEvent):
        pass

class IncidentEventPublisher:
    def __init__(self):
        self._subscribers: list[IncidentSubscriber] = []

    def subscribe(self, subscriber: IncidentSubscriber):
        self._subscribers.append(subscriber)

    def unsubscribe(self, subscriber: IncidentSubscriber):
        self._subscribers.remove(subscriber)

    async def publish(self, event: IncidentEvent):
        await asyncio.gather(*[
            self._notify(subscriber, event)
            for subscriber in self._subscribers
        ])

    async def _notify(self, subscriber: IncidentSubscriber, event: IncidentEvent):
        try:
            await subscriber.on_incident(event)
        except Exception as e:
            logger.error(f"Error notifying {subscriber.__class__.__name__}: {e}")




class LoggerSubscriber(IncidentSubscriber):
    async def on_incident(self, event: IncidentEvent):
        logger.warning(
            f"[{event.source}] Incident at {event.detected_at} "
            f"| Status: {event.incident.status} "
            f"| Message: {event.incident.message}"
        )

