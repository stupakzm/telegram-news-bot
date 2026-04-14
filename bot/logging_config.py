"""Centralized logging configuration."""
import logging
import os

_configured = False
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s -- %(message)s"


def setup():
    """Configure root logger. Safe to call multiple times."""
    global _configured
    if _configured:
        return

    logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT)

    # Write ERROR+ to a local file when not running on Vercel
    if not os.environ.get("VERCEL"):
        log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "errors.log")
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.ERROR)
        fh.setFormatter(logging.Formatter(_LOG_FORMAT))
        logging.getLogger().addHandler(fh)

    _configured = True
