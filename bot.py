import asyncio
import logging
import re
from collections import defaultdict
from typing import List

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, KeyboardButton, ReplyKeyboardMarkup,
    InputMediaPhoto, InputMediaVideo
)

from config import (
    TOKEN, ADMIN_CHAT_ID, TOPIC_MATERIAL, TOPIC_QUESTION,
    TEXT_BACK_BTN, TEXT_MENU_TITLE
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

bot = Bot(TOKEN)
dp = Dispatcher()

menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📷 Отправить материал")],
        [KeyboardButton(text="❓ Задать вопрос")]
    ],
    resize_keyboard=True
)
back_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=TEXT_BACK_BTN)]],
    resize_keyboard=True
)

user_mode = defaultdict(lambda: None)
albums = {}
topic_link = {}
ID_RE = re.compile(r"\(id=(\d+)\)")

def user_tag(m: Message) -> str:
    uname = f"@{m.from_user.username}" if m.from_user.username else m.from_user.full_name
    return f"{uname} (id={m.from_user.id})"

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_mode[message.from_user.id] = None
    await message.answer("👋 Привет! Выбери, что хочешь сделать:", reply_markup=menu_kb)

@dp.message(F.text == "📷 Отправить материал")
async def choose_material(message: Message):
    user_mode[message.from_user.id] = "material"
    await message.answer("📸 Прикрепи фото или видео материал, можешь добавить описание.", reply_markup=back_kb)

@dp.message(F.text == "❓ Задать вопрос")
async def choose_question(message: Message):
    user_mode[message.from_user.id] = "question"
    await message.answer("💬 Напиши любой вопрос по урокам физкультуры и спорту в школе. И тебе ответят здесь в ближайшее время.", reply_markup=back_kb)

@dp.message(F.text == TEXT_BACK_BTN)
async def back_to_menu(message: Message):
    user_mode[message.from_user.id] = None
    await message.answer(TEXT_MENU_TITLE, reply_markup=menu_kb)

# ======== ОБРАБОТКА СООБЩЕНИЙ ПОЛЬЗОВАТЕЛЕЙ ========
@dp.message(F.chat.type == "private")
async def handle_user_message(message: Message):
    mode = user_mode.get(message.from_user.id)
    uid = message.from_user.id
    tag = user_tag(message)

    # ---- ВОПРОС ----
    if mode == "question":
        msg = await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            message_thread_id=TOPIC_QUESTION,
            text=f"❓ Вопрос от {tag}:\n{message.text or ''}"
        )
        topic_link[msg.message_id] = uid
        await message.answer("✅ Вопрос отправлен! Ожидай ответ.", reply_markup=menu_kb)
        user_mode[uid] = None
        return

    # ---- МАТЕРИАЛ ----
    if mode == "material":
        key = (uid, message.media_group_id or message.message_id)

        if message.media_group_id and (message.photo or message.video):
            bucket = albums.setdefault(key, [])
            if message.photo:
                bucket.append(InputMediaPhoto(media=message.photo[-1].file_id))
            elif message.video:
                bucket.append(InputMediaVideo(media=message.video.file_id))

            await asyncio.sleep(2)  # ждём, пока придут все части альбома

            if key in albums and bucket is albums[key]:
                sent_media = await bot.send_media_group(
                    chat_id=ADMIN_CHAT_ID,
                    message_thread_id=TOPIC_MATERIAL,
                    media=bucket
                )

                caption_msg = await bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    message_thread_id=TOPIC_MATERIAL,
                    text=f"📩 Материал от {tag}"
                )
                topic_link[caption_msg.message_id] = uid

                await message.answer("✅ Материал доставлен!", reply_markup=menu_kb)
                user_mode[uid] = None
                albums.pop(key, None)
            return

        # одиночное медиа
        if message.photo or message.video or message.document:
            if message.photo:
                await bot.send_photo(ADMIN_CHAT_ID, message.photo[-1].file_id, message_thread_id=TOPIC_MATERIAL)
            elif message.video:
                await bot.send_video(ADMIN_CHAT_ID, message.video.file_id, message_thread_id=TOPIC_MATERIAL)
            elif message.document:
                await bot.send_document(ADMIN_CHAT_ID, message.document.file_id, message_thread_id=TOPIC_MATERIAL)

            sent = await bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                message_thread_id=TOPIC_MATERIAL,
                text=f"📩 Материал от {tag}"
            )
            topic_link[sent.message_id] = uid

            await message.answer("✅ Материал доставлен!", reply_markup=menu_kb)
            user_mode[uid] = None
            return

        await message.answer("📸 Прикрепи фото или видео материал, можешь добавить описание.", reply_markup=back_kb)
        return

    await message.answer(TEXT_MENU_TITLE, reply_markup=menu_kb)

# ======== ОТВЕТ АДМИНА ========
@dp.message(F.chat.id == ADMIN_CHAT_ID)
async def handle_admin_reply(message: Message):
    if not message.reply_to_message:
        return

    user_id = topic_link.get(message.reply_to_message.message_id)
    if not user_id:
        src = message.reply_to_message.text or message.reply_to_message.caption or ""
        match = ID_RE.search(src)
        if match:
            try:
                user_id = int(match.group(1))
            except ValueError:
                user_id = None

    if not user_id:
        return

    try:
        if message.text:
            await bot.send_message(user_id, f"💬 Ответ от учителя:\n\n{message.text}")
        elif message.photo:
            await bot.send_photo(user_id, message.photo[-1].file_id, caption="💬 Ответ от учителя")
        elif message.video:
            await bot.send_video(user_id, message.video.file_id, caption="💬 Ответ от учителя")
        elif message.document:
            await bot.send_document(user_id, message.document.file_id, caption="💬 Ответ от учителя")
    except Exception as e:
        log.error(f"Ошибка при пересылке ответа: {e}")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("[BOT] Запуск…")
    await dp.start_polling(bot, allowed_updates=None)

if __name__ == "__main__":
    asyncio.run(main())
