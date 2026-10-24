"""System-wide structured logging for FairScope."""
import logging
from logging.handlers import RotatingFileHandler

from secure_storage import data_directory

# Setup paths
LOG_DIR = data_directory() / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

# Configuration
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_LEVEL = logging.INFO

logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    handlers=[
        # Rotated so a long-running install cannot grow the log without bound.
        RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=2, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

def get_logger(name: str):
    """Returns a logger instance for the specified component."""
    return logging.getLogger(name)

# Global shortcut for the main app logger
logger = get_logger("FairScope")
