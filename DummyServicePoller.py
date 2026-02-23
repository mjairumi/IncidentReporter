import httpx
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from PollingInterface import *
from Logger import logger

class DummyServiceIncident(BaseModel):
    status: str
    message: str
    createdAt: datetime = Field(default_factory=datetime.now)
    
class DummyServicePoller(PollingInterface):

    DUMMY_SERVICE_URL = "http://localhost:8000/dummyService/getLatestIncident"

    def __init__(self):
        self.frequency = 30
        self.incident_frequency = 10
        self.is_incident_active = False
        self._last_seen_incident: Optional[DummyServiceIncident] = None  # Tracks last known incident

    def getPollingFrequency(self) -> int:
        if self.is_incident_active:
            return self.incident_frequency
        return self.frequency

    async def poll(self) -> PollResult:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.DUMMY_SERVICE_URL)
                response.raise_for_status()

                data = response.json()

            # No incidents at all
            if not data:
                self._handle_no_incident()
                return PollResult()

            # Parse the latest incident (first in deque = most recent)
            latest = DummyServiceIncident(**data[0])

            # Check if this is new or updated
            if self._is_new_or_updated(latest):
                self._last_seen_incident = latest
                self._handle_incident_active()
                return PollResult(
                    incident=latest,
                    new_frequency=self.incident_frequency  # Poll faster during incident
                )

            # Incident exists but nothing changed
            return PollResult()

        except httpx.HTTPStatusError as e:
            logger.error(f"[DummyServicePoller] HTTP error: {e.response.status_code}")
            return PollResult()
        except httpx.RequestError as e:
            logger.error(f"[DummyServicePoller] Request failed: {e}")
            return PollResult()
        except Exception as e:
            logger.error(f"[DummyServicePoller] Unexpected error: {e}")
            return PollResult()

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _is_new_or_updated(self, latest: DummyServiceIncident) -> bool:
        """Returns True if the incident is new or different from the last seen one."""
        if self._last_seen_incident is None:
            return True  # First time seeing any incident

        return (
            latest.status != self._last_seen_incident.status or
            latest.message != self._last_seen_incident.message or
            latest.createdAt != self._last_seen_incident.createdAt
        )

    def _handle_incident_active(self):
        """Switch to faster polling if not already in incident mode."""
        if not self.is_incident_active:
            logger.info("[DummyServicePoller] Incident detected — switching to fast polling.")
            self.is_incident_active = True

    def _handle_no_incident(self):
        """Switch back to normal polling if incident has resolved."""
        if self.is_incident_active:
            logger.info("[DummyServicePoller] Incident resolved — switching to normal polling.")
            self.is_incident_active = False
            self._last_seen_incident = None