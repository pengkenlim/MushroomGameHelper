"""Logger module: thread-safe rotating session log for telemetry/debugging.

Python's ``logging`` module serialises handler writes with an internal lock,
so the exported :data:`logger` may be used from every thread without extra
synchronisation.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_PATH: Path = Path(__file__).resolve().parent / "bot_session.log"
LOG_FORMAT: str = "%(asctime)s - %(threadName)s - %(levelname)s - %(message)s"
MAX_BYTES: int = 5 * 1024 * 1024
BACKUP_COUNT: int = 3


def setup_logger(name: str = "MushroomHelper") -> logging.Logger:
    """Configures and returns the session logger.

    The call is idempotent: the rotating file handler is attached only once,
    so repeated imports or calls never produce duplicate log lines.

    Args:
        name: Name of the logger.

    Returns:
        The configured logger.
    """
    log = logging.getLogger(name)
    if not any(isinstance(h, RotatingFileHandler) for h in log.handlers):
        log.setLevel(logging.DEBUG)
        handler = RotatingFileHandler(
            LOG_PATH, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
            encoding="utf-8")
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        log.addHandler(handler)
        log.propagate = False
    return log


logger: logging.Logger = setup_logger()
