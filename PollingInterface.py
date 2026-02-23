
from abc import ABC, abstractmethod
from typing import Optional
from DummyServicePoller import DummyServiceIncident

class PollResult:
    def __init__(
        self,
        incident: Optional[DummyServiceIncident] = None,
        new_frequency: Optional[int] = None
    ):
        self.incident = incident        # None = no incident
        self.new_frequency = new_frequency  # None = no frequency change

class PollingInterface(ABC):

    @abstractmethod
    def getPollingFrequency(self) -> int:
        """Return polling frequency in seconds."""
        pass

    @abstractmethod
    async def poll(self) -> PollResult:
        """Poll the service and return a PollResult."""
        pass
