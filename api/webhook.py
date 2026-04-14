# api/webhook.py
"""Vercel serverless entry point for Telegram webhook."""
import json
import sys
import os
import hmac
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from bot.logging_config import setup as setup_logging
setup_logging()

import logging
logger = logging.getLogger(__name__)

from bot.router import handle_update

logger.info("Webhook handler loaded — version 2026-04-14-v2")
if not os.environ.get("WEBHOOK_SECRET"):
    logger.warning("WEBHOOK_SECRET not set — webhook endpoint is unauthenticated")


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Verify webhook secret if configured
        secret = os.environ.get("WEBHOOK_SECRET", "")
        if secret:
            header_token = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if not hmac.compare_digest(secret, header_token):
                self.send_response(403)
                self.end_headers()
                return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            update = json.loads(body)
            handle_update(update)
        except Exception as e:
            logger.error("Webhook handler error: %s", e)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args):
        pass  # suppress default HTTP logging
