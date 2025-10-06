"""Telegram bot entry point."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from logging.handlers import RotatingFileHandler

import config

router = Router()
message_links: Dict[int, int] = {}


def setup_logging() -> None:
    """Configure logging to console and file."""
    log_file = Path(config.LOG_FILE)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    handlers = [
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8"),
    ]

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=handlers,
    )


setup_logging()
logger = logging.getLogger(__name__)

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=config.BUTTONS.send_material)],
        [KeyboardButton(text=config.BUTTONS.ask_question)],
    ],
    resize_keyboard=True,
)

back_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=config.TEXTS.back_button)]],
    resize_keyboard=True,
)


def _format_user(message: Message) -> str:
    user = message.from_user
    if user is None:
        return "Неизвестный пользователь"

    username = f"@{user.username}" if user.username else "без username"
    return f"{user.full_name} ({username}) (id={user.id})"


async def _notify_delivery_error(message: Message) -> None:
    try:
        await message.answer(config.TEXTS.delivery_error)
    except TelegramAPIError:
        logger.exception("Failed to notify user about delivery error")


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(config.TEXTS.greeting, reply_markup=main_menu)


@router.message(F.text == config.BUTTONS.send_material)
async def send_material_info(message: Message) -> None:
    await message.answer(config.TEXTS.material_instruction, reply_markup=back_menu)


@router.message(F.text == config.BUTTONS.ask_question)
async def send_question_info(message: Message) -> None:
    await message.answer(config.TEXTS.question_instruction, reply_markup=back_menu)


@router.message(F.text == config.TEXTS.back_button)
async def go_back(message: Message) -> None:
    await message.answer(config.TEXTS.main_menu, reply_markup=main_menu)


@router.message(F.chat.type == ChatType.PRIVATE)
async def handle_user_message(message: Message) -> None:
    if message.text:
        stripped = message.text.strip()
        if not stripped or stripped.startswith("/"):
            return
        if stripped in {
            config.BUTTONS.send_material,
            config.BUTTONS.ask_question,
            config.TEXTS.back_button,
        }:
            return

    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        logger.warning("Received message without user information")
        return

    user_info = _format_user(message)
    logger.info("Received message from %s", user_info)

    if any((
        message.photo,
        message.video,
        message.document,
        message.animation,
        message.audio,
        message.voice,
    )):
        await _process_material_message(message, user_id, user_info)
    elif message.text:
        await _process_question_message(message, user_id, user_info)
    else:
        await message.answer(config.TEXTS.unsupported_content)


async def _process_material_message(message: Message, user_id: int, user_info: str) -> None:
    topic = config.TOPIC_MATERIAL
    if topic == 0:
        logger.error("Topic ID for materials is not configured")
        await _notify_delivery_error(message)
        return

    try:
        copied_message = await message.copy_to(
            chat_id=config.ADMIN_CHAT_ID,
            message_thread_id=topic,
        )
        message_links[copied_message.message_id] = user_id
        summary = await message.bot.send_message(
            chat_id=config.ADMIN_CHAT_ID,
            message_thread_id=topic,
            text=f"📸 Материал от {user_info}",
        )
        message_links[summary.message_id] = user_id
    except TelegramAPIError as exc:
        logger.exception("Failed to forward material from %s: %s", user_info, exc)
        await _notify_delivery_error(message)
        return

    logger.info("Material from %s forwarded to topic %s", user_info, topic)
    await message.answer(config.TEXTS.material_sent)


async def _process_question_message(message: Message, user_id: int, user_info: str) -> None:
    topic = config.TOPIC_QUESTION
    if topic == 0:
        logger.error("Topic ID for questions is not configured")
        await _notify_delivery_error(message)
        return

    text = message.text or ""
    try:
        admin_message = await message.bot.send_message(
            chat_id=config.ADMIN_CHAT_ID,
            message_thread_id=topic,
            text=f"❓ Вопрос от {user_info}:\n{text}",
        )
        message_links[admin_message.message_id] = user_id
    except TelegramAPIError as exc:
        logger.exception("Failed to forward question from %s: %s", user_info, exc)
        await _notify_delivery_error(message)
        return

    logger.info("Question from %s forwarded to topic %s", user_info, topic)
    await message.answer(config.TEXTS.question_sent)


@router.message(F.chat.id == config.ADMIN_CHAT_ID)
async def admin_reply(message: Message) -> None:
    reply = message.reply_to_message
    if not reply:
        return

    user_id = message_links.get(reply.message_id)
    if not user_id:
        logger.debug("No user link for message %s", reply.message_id)
        return

    try:
        await _send_admin_reply(message, user_id)
    except TelegramAPIError as exc:
        logger.exception("Failed to deliver admin reply to user %s: %s", user_id, exc)
        await message.reply("⚠️ Не удалось отправить сообщение пользователю.")
        return

    logger.info("Delivered admin reply from thread message %s to user %s", reply.message_id, user_id)


async def _send_admin_reply(message: Message, user_id: int) -> None:
    bot = message.bot
    prefix = config.TEXTS.admin_reply_prefix

    if message.text:
        await bot.send_message(user_id, f"{prefix}\n{message.text}")
        return

    caption = message.caption or ""
    caption_text = f"{prefix}\n{caption}" if caption else prefix

    if message.photo:
        await bot.send_photo(user_id, message.photo[-1].file_id, caption=caption_text)
    elif message.video:
        await bot.send_video(user_id, message.video.file_id, caption=caption_text)
    elif message.document:
        await bot.send_document(user_id, message.document.file_id, caption=caption_text)
    elif message.audio:
        await bot.send_audio(user_id, message.audio.file_id, caption=caption_text)
    elif message.voice:
        await bot.send_voice(user_id, message.voice.file_id, caption=caption_text)
    elif message.animation:
        await bot.send_animation(user_id, message.animation.file_id, caption=caption_text)
    else:
        await bot.send_message(user_id, prefix)
        await message.copy_to(user_id)


async def main() -> None:
    if not config.BOT_TOKEN or config.BOT_TOKEN == "ТВОЙ_ТОКЕН":
        raise RuntimeError("BOT_TOKEN is not configured. Set the BOT_TOKEN environment variable.")

    dp = Dispatcher()
    dp.include_router(router)

    bot = Bot(token=config.BOT_TOKEN, parse_mode="HTML")

    logger.info("Bot starting")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception:
        logger.exception("Bot stopped due to an unexpected error")
        raise
    finally:
        await bot.session.close()
        logger.info("Bot shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
