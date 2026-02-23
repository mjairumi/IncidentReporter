from pydantic import BaseModel, Field
from datetime import datetime

class IncidentReportDto(BaseModel):
    status: str
    message: str
    source: str
    createdAt: datetime = Field(default_factory=datetime.now)