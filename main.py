from collections import deque
from contextlib import asynccontextmanager
from typing import Deque
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
# import uvicorn
from DummyServicePoller import *
from CustomHttpClientPool import CustomHttpClientPool
from PollingQueue import *
from OpenAIPoller import OpenAIPoller
from PublisherSubscriber import IncidentEventPublisher, LoggerSubscriber
from UIPublisherSubscriber import UIPublisherSubscriber
import sys
import signal

incidentArr: deque = deque(maxlen=10)

# ---- Setup ----

publisher = IncidentEventPublisher()
# publisher.subscribe(LoggerSubscriber())
ui_publisher = UIPublisherSubscriber()
publisher.subscribe(ui_publisher)

polling_queue = PollingQueue(publisher=publisher)
polling_queue.add(OpenAIPoller())
polling_queue.add(DummyServicePoller())

def setup_signal_handlers(loop: asyncio.AbstractEventLoop):
    """Intercept shutdown signals and close SSE connections FIRST."""

    def handle_shutdown():
        logger.info("[Main] Shutdown signal received — closing SSE connections first.")
        ui_publisher.shutdown()  # Unblocks all SSE generators immediately

        if sys.platform == "win32":
            # Windows doesn't support add_signal_handler
            
            signal.signal(signal.SIGINT, lambda s, f: ui_publisher.shutdown())
            signal.signal(signal.SIGTERM, lambda s, f: ui_publisher.shutdown())
        else:
            loop.add_signal_handler(signal.SIGINT, handle_shutdown)
            loop.add_signal_handler(signal.SIGTERM, handle_shutdown)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await CustomHttpClientPool.startup(
        max_connections=100,  # 1 per poller at peak
        max_keepalive=20      # Keep 20 warm connections ready
    )
    await polling_queue.start()
    loop = asyncio.get_event_loop()
    setup_signal_handlers(loop)
    yield
    
    await polling_queue.stop()
    await CustomHttpClientPool.shutdown()

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

# SSE endpoint — browser connects here
@app.get("/stream/incidents")
async def stream_incidents():
    queue = ui_publisher.connect()

    async def event_generator():
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(
                        ui_publisher.wait_for_event(queue),
                        timeout=15
                    )

                    if payload is None:  # Shutdown signal
                        yield "event: shutdown\ndata: {}\n\n"
                        break            # Exit the loop cleanly

                    yield f"event: incident\ndata: {payload}\n\n"

                except asyncio.TimeoutError:
                    yield "event: heartbeat\ndata: {}\n\n"

        except asyncio.CancelledError:
            logger.info("[UI] SSE connection cancelled.")
            raise
        finally:
            ui_publisher.disconnect(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

# Serve the UI
@app.get("/ui", response_class=HTMLResponse)
async def serve_ui():
    with open("ui.html") as f:
        return f.read()
    
# if __name__ == "__main__":
#     # run uvicorn server when this module is executed directly
#     uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)