
from abc import ABC, abstractmethod
from typing import Optional
from IncidentReportDto import IncidentReportDto
class PollResult:
    def __init__(
        self,
        incident: Optional[IncidentReportDto] = None,
        new_frequency: Optional[int] = None
    ):
        self.incident = incident
        self.new_frequency = new_frequency

class PollingInterface(ABC):

    @abstractmethod
    def getPollingFrequency(self) -> int:
        """Return polling frequency in seconds."""
        pass

    @abstractmethod
    async def poll(self) -> PollResult:
        """Poll the service and return a PollResult."""
        pass
