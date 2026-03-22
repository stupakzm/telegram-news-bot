"""Centralized logging configuration."""
import logging

_configured = False


def setup():
    """Configure root logger. Safe to call multiple times."""
    global _configured
    if _configured:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s -- %(message)s",
    )
    _configured = True
