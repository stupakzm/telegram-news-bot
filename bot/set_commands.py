"""Register the bot's command menu with Telegram.

Run once after deploy (or whenever the command list changes):

    python -m bot.set_commands

The list here is the single source of truth for user-facing commands — /help
renders from the same PUBLIC_COMMANDS list so the menu and help never drift.
Admin-only commands (/admin) are intentionally omitted from the public menu.
"""
import logging

import bot.telegram as tg

logger = logging.getLogger(__name__)

# (command, description) — order is preserved in the Telegram menu.
PUBLIC_COMMANDS = [
    ("start", "Get started / welcome"),
    ("help", "Show all commands"),
    ("keywords", "Manage your filter keywords"),
    ("addurl", "Manage your RSS feeds"),
    ("settings", "View your plan, feeds & keywords"),
    ("timezone", "Set your local timezone"),
    ("plan", "Buy, renew, or switch plan"),
    ("clear", "Clear the bot's messages"),
]


def register() -> dict:
    payload = [{"command": c, "description": d} for c, d in PUBLIC_COMMANDS]
    return tg.set_my_commands(payload)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    result = register()
    logger.info("setMyCommands result: %s", result)
    print("Registered %d commands." % len(PUBLIC_COMMANDS))
