"""Configuration module for the Telegram bot."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer, got: {value}") from exc


@dataclass(frozen=True)
class Texts:
    greeting: str = "👋 Привет! Выбери, что хочешь сделать:"
    main_menu: str = "Главное меню:"
    material_instruction: str = (
        "📸 Отправь сюда фото или видео. Всё, что ты пришлёшь, попадёт в тему 'В работе'."
    )
    question_instruction: str = "💬 Напиши свой вопрос, и он появится в теме 'Вопросы'."
    back_button: str = "↩️ Назад"
    admin_reply_prefix: str = "📩 Ответ от администрации"
    material_sent: str = "✅ Материал отправлен. Мы сообщим, когда его посмотрят."
    question_sent: str = "✅ Вопрос отправлен. Мы ответим в ближайшее время."
    unsupported_content: str = (
        "⚠️ Можно отправлять только текст, фото или видео. Пожалуйста, попробуй ещё раз."
    )
    delivery_error: str = "⚠️ Не удалось доставить сообщение. Попробуйте чуть позже."


@dataclass(frozen=True)
class Buttons:
    send_material: str = "📸 Отправить материал"
    ask_question: str = "💬 Задать вопрос"


BOT_TOKEN: Final[str] = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН")
ADMIN_CHAT_ID: Final[int] = _env_int("ADMIN_CHAT_ID", -1002404070892)
TOPIC_MATERIAL: Final[int] = _env_int("TOPIC_MATERIAL", 12)
TOPIC_QUESTION: Final[int] = _env_int("TOPIC_QUESTION", 10)
LOG_FILE: Final[str] = os.getenv("LOG_FILE", "bot.log")
TEXTS: Final[Texts] = Texts()
BUTTONS: Final[Buttons] = Buttons()


__all__ = [
    "BOT_TOKEN",
    "ADMIN_CHAT_ID",
    "TOPIC_MATERIAL",
    "TOPIC_QUESTION",
    "LOG_FILE",
    "TEXTS",
    "BUTTONS",
]
