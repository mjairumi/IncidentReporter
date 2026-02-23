from collections import deque
from contextlib import asynccontextmanager
from typing import Deque
from fastapi import FastAPI
import uvicorn
from DummyServicePoller import *
from PollingQueue import *
from OpenAIPoller import OpenAIPoller
from PublisherSubscriber import IncidentEventPublisher, LoggerSubscriber

    
incidentArr: deque = deque(maxlen=10)

# ---- Subscribers ----
class IncidentStoreSubscriber:
    async def on_incident(self, event):
        incidentArr.appendleft(event.incident)


# ---- Setup ----

publisher = IncidentEventPublisher()
publisher.subscribe(LoggerSubscriber())
publisher.subscribe(IncidentStoreSubscriber())

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