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
    TEXT_WELCOME, TEXT_MATERIAL_INSTR, TEXT_QUESTION_INSTR,
    TEXT_BACK_BTN, TEXT_MENU_TITLE, TEXT_THANKS_MATERIAL, TEXT_THANKS_QUESTION,
    ALBUM_CHUNK
)

# ---------- ЛОГИ ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("bot")

# ---------- BOT / DP ----------
bot = Bot(TOKEN)
dp = Dispatcher()

# ---------- КЛАВИАТУРЫ ----------
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

# ---------- ПРОСТЕЙШЕЕ СОСТОЯНИЕ ПОЛЬЗОВАТЕЛЯ ----------
# user_mode[user_id] = "material" | "question" | None
user_mode: dict[int, str | None] = defaultdict(lambda: None)

# Копим элементы альбомов по ключу (user_id, media_group_id)
albums: dict[tuple[int, str], List[InputMediaPhoto | InputMediaVideo]] = {}

# Привязка msg_id в теме -> user_id, чтобы админ мог ответить реплаем
topic_link: dict[int, int] = {}

# ---------- ВСПОМОГАТЕЛЬНОЕ ----------
ID_RE = re.compile(r"\(id=(\d+)\)")

def user_tag(m: Message) -> str:
    uname = f"@{m.from_user.username}" if m.from_user.username else m.from_user.full_name
    return f"{uname} (id={m.from_user.id})"

async def send_album_in_chunks(chat_id: int, thread_id: int, media_list: List[InputMediaPhoto | InputMediaVideo]):
    """Отправляем альбом пачками по 10, если медиа больше лимита."""
    if not media_list:
        return []
    chunks = [media_list[i:i+ALBUM_CHUNK] for i in range(0, len(media_list), ALBUM_CHUNK)]
    sent_msgs = []
    for chunk in chunks:
        sent = await bot.send_media_group(chat_id=chat_id, message_thread_id=thread_id, media=chunk)
        sent_msgs.extend(sent)
        await asyncio.sleep(0.2)  # лёгкая пауза, чтобы не задирать CPU и не ловить flood
    return sent_msgs

# ---------- ХЭНДЛЕРЫ ----------
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_mode[message.from_user.id] = None
    await message.answer(TEXT_WELCOME, reply_markup=menu_kb)

@dp.message(F.text == "📷 Отправить материал")
async def choose_material(message: Message):
    user_mode[message.from_user.id] = "material"
    await message.answer(TEXT_MATERIAL_INSTR, reply_markup=back_kb)

@dp.message(F.text == "❓ Задать вопрос")
async def choose_question(message: Message):
    user_mode[message.from_user.id] = "question"
    await message.answer(TEXT_QUESTION_INSTR, reply_markup=back_kb)

@dp.message(F.text == TEXT_BACK_BTN)
async def back_to_menu(message: Message):
    user_mode[message.from_user.id] = None
    await message.answer(TEXT_MENU_TITLE, reply_markup=menu_kb)

# --- Основной обработчик лички пользователя ---
@dp.message(F.chat.type == "private")
async def handle_user_private(message: Message):
    mode = user_mode.get(message.from_user.id)

    # 1) Режим ВОПРОС
    if mode == "question":
        if message.text:
            header = f"❓ Вопрос от {user_tag(message)}:\n\n{message.text}"
        else:
            header = f"❓ Вопрос от {user_tag(message)}"
        sent = await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            message_thread_id=TOPIC_QUESTION,
            text=header
        )
        topic_link[sent.message_id] = message.from_user.id
        await message.answer(TEXT_THANKS_QUESTION, reply_markup=menu_kb)
        user_mode[message.from_user.id] = None
        return

    # 2) Режим МАТЕРИАЛ
    if mode == "material":
        # --- альбомы ---
        if message.media_group_id and (message.photo or message.video):
            key = (message.from_user.id, message.media_group_id)
            bucket = albums.setdefault(key, [])
            if message.photo:
                bucket.append(InputMediaPhoto(media=message.photo[-1].file_id))
            elif message.video:
                bucket.append(InputMediaVideo(media=message.video.file_id))

            # «дебаунс» — ждём ещё немного элементов этого же альбома
            await asyncio.sleep(1.2)
            if key in albums and bucket is albums[key]:
                # отправляем заголовок один раз
                caption_msg = await bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    message_thread_id=TOPIC_MATERIAL,
                    text=f"📩 Материал от {user_tag(message)}:"
                )
                topic_link[caption_msg.message_id] = message.from_user.id

                # отправляем сам альбом батчами
                await send_album_in_chunks(ADMIN_CHAT_ID, TOPIC_MATERIAL, bucket)

                # чистим память
                albums.pop(key, None)

                # подтверждение пользователю
                await message.answer(TEXT_THANKS_MATERIAL, reply_markup=menu_kb)
                user_mode[message.from_user.id] = None
            return

        # одиночные медиа / документы
        if message.photo or message.video or message.document:
            header = await bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                message_thread_id=TOPIC_MATERIAL,
                text=f"📩 Материал от {user_tag(message)}:"
            )
            topic_link[header.message_id] = message.from_user.id

            if message.photo:
                await bot.send_photo(ADMIN_CHAT_ID, message.photo[-1].file_id, message_thread_id=TOPIC_MATERIAL)
            elif message.video:
                await bot.send_video(ADMIN_CHAT_ID, message.video.file_id, message_thread_id=TOPIC_MATERIAL)
            elif message.document:
                await bot.send_document(ADMIN_CHAT_ID, message.document.file_id, message_thread_id=TOPIC_MATERIAL)

            await message.answer(TEXT_THANKS_MATERIAL, reply_markup=menu_kb)
            user_mode[message.from_user.id] = None
            return

        # текст не в тему — напомним инструкцию
        await message.answer(TEXT_MATERIAL_INSTR, reply_markup=back_kb)
        return

    # вне режима — покажем меню
    await message.answer(TEXT_MENU_TITLE, reply_markup=menu_kb)

# --- Ответы админа в темах группы ---
@dp.message(F.chat.id == ADMIN_CHAT_ID)
async def relay_admin_reply(message: Message):
    # работаем только если это реплай на сообщение бота в теме
    if not message.reply_to_message:
        return

    # 1) пробуем найти user_id из нашей карты
    user_id = topic_link.get(message.reply_to_message.message_id)

    # 2) если нет — пробуем распарсить из текста "(id=12345)"
    if not user_id:
        src = message.reply_to_message.text or message.reply_to_message.caption or ""
        m = ID_RE.search(src)
        if m:
            try:
                user_id = int(m.group(1))
            except ValueError:
                user_id = None

    if not user_id:
        return  # не нашли адресата

    try:
        if message.text:
            await bot.send_message(user_id, f"💬 Ответ администратора:\n\n{message.text}")
        elif message.photo:
            await bot.send_photo(user_id, message.photo[-1].file_id, caption="💬 Ответ администратора")
        elif message.video:
            await bot.send_video(user_id, message.video.file_id, caption="💬 Ответ администратора")
        elif message.document:
            await bot.send_document(user_id, message.document.file_id, caption="💬 Ответ администратора")
    except Exception as e:
        log.error(f"Не удалось отправить ответ пользователю {user_id}: {e}")

# ---------- ЗАПУСК ----------
async def main():
    log.info("[BOT] Запуск…")
    # на всякий случай удалим вебхук и отбросим старые апдейты
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass
    await dp.start_polling(bot, allowed_updates=None)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("[BOT] Остановлен.")