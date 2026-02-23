import asyncio
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Deque, List

from fastapi import FastAPI
from pydantic import BaseModel, Field
import uvicorn

from DummyServicePoller import *
from PollingQueue import *

from OpenAIPoller import OpenAIPoller
from Logger import logger

    
incidentArr: deque = deque(maxlen=10)
# Configure logging to both terminal and file



publisher = PollingQueue.IncidentEventPublisher()
publisher.subscribe(PollingQueue.LoggerSubscriber())
publisher.subscribe(PollingQueue.IncidentStoreSubscriber())

polling_queue = PollingQueue(publisher=publisher)
polling_queue.add(OpenAIPoller())
polling_queue.add(DummyServicePoller())

@asynccontextmanager
async def lifespan(app: FastAPI):

    await polling_queue.start()
    yield
    await polling_queue.stop()

# create application instance
app = FastAPI(title="Incident Reporter", lifespan=lifespan)






@app.get("/")
def read_root():
    """Root endpoint returns a simple welcome message."""
    return {"message": "Incident Reporter API"}


# additional endpoints can be added here, for example:
# @app.post("/incidents")
# def create_incident(incident: IncidentReportDto):
#     # handle new incident report
#     return {"status": "received"}

# Dummy Service: GetAnyNewIncident API, CreateNewIncident
@app.get("/dummyService/getLatestIncident")
def getLatestIncident() -> Deque[DummyServiceIncident]:
    return incidentArr

@app.post("/dummyService/createDummyIncident")
def createDummyIncident(data: DummyServiceIncident):
    incidentArr.appendleft(data)
    return {"status": "received"} 

if __name__ == "__main__":
    # run uvicorn server when this module is executed directly
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)