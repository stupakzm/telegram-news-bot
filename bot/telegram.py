# bot/telegram.py
import os
import requests

_BASE = "https://api.telegram.org/bot{token}/{method}"


def _url(method: str) -> str:
    return _BASE.format(token=os.environ["TELEGRAM_BOT_TOKEN"], method=method)


def send_message(chat_id: int, text: str, reply_markup: dict = None,
                 parse_mode: str = "Markdown") -> dict:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode,
               "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    resp = requests.post(_url("sendMessage"), json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json().get("result", {})


def edit_message_text(chat_id: int, message_id: int, text: str,
                      reply_markup: dict = None, parse_mode: str = "Markdown") -> dict:
    payload = {"chat_id": chat_id, "message_id": message_id,
               "text": text, "parse_mode": parse_mode,
               "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    resp = requests.post(_url("editMessageText"), json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json().get("result", {})


def edit_message_reply_markup(chat_id: int, message_id: int, reply_markup: dict) -> None:
    requests.post(_url("editMessageReplyMarkup"),
                  json={"chat_id": chat_id, "message_id": message_id,
                        "reply_markup": reply_markup},
                  timeout=10)


def delete_message(chat_id: int, message_id: int) -> None:
    requests.post(_url("deleteMessage"),
                  json={"chat_id": chat_id, "message_id": message_id},
                  timeout=10)


def answer_callback_query(callback_query_id: str, text: str = "") -> None:
    requests.post(_url("answerCallbackQuery"),
                  json={"callback_query_id": callback_query_id, "text": text},
                  timeout=10)


def send_invoice(chat_id: int, title: str, description: str, payload: str,
                 currency: str, prices: list[dict]) -> dict:
    """Send a Telegram Stars payment invoice. currency must be 'XTR' for Stars."""
    data = {
        "chat_id": chat_id, "title": title, "description": description,
        "payload": payload, "currency": currency, "prices": prices,
        "provider_token": "",  # empty for Stars
    }
    resp = requests.post(_url("sendInvoice"), json=data, timeout=10)
    resp.raise_for_status()
    return resp.json().get("result", {})
