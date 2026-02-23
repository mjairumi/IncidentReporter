import logging


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),          # Terminal
        logging.FileHandler("incidents.log")  # File
    ]
)
logger = logging.getLogger(__name__)