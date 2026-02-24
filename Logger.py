import logging

# Terminal only — captures everything (uvicorn, app logs, etc.)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

logging.getLogger("watchfiles").setLevel(logging.WARNING)
logging.getLogger("uvicorn.reload").setLevel(logging.WARNING)

# General app logger (terminal only)
logger = logging.getLogger(__name__)

# Incident-only logger (file only)
incident_logger = logging.getLogger("incident")
incident_logger.propagate = False  # Don't bubble up to root logger / terminal
incident_logger.setLevel(logging.WARNING)
# incident_logger.addHandler(
#     logging.FileHandler("incidents.log")
# )