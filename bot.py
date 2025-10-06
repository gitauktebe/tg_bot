import asyncio
import logging
from datetime import datetime
from typing import Dict, List
from collections import defaultdict

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, KeyboardButton, ReplyKeyboardMarkup,
    InputMediaPhoto, InputMediaVideo, InputMediaDocument
)

from config import (
    TOKEN, ADMIN_CHAT_ID, TOPIC_MATERIAL, TOPIC_QUESTION,
    TEXT_BACK_BTN, TEXT_MENU_TITLE
)

# ==============================
# НАСТРОЙКИ
# ==============================
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# режим пользователя: "material", "question" или None
user_mode: Dict[int, str] = defaultdict(lambda: None)
topic_link: Dict[int, int] = {}
pending_uploads: Dict[int, dict] = {}

# ==============================
# КНОПКИ
# ==============================
menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📸 Отправить материал")],
        [KeyboardButton(text="❓ Задать вопрос")]
    ],
    resize_keyboard=True
)

back_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=TEXT_BACK_BTN)]],
    resize_keyboard=True
)


# ==============================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================
def user_tag(message: Message) -> str:
    username = message.from_user.username
    uid = message.from_user.id
    tag = f"@{username}" if username else f"ID: {uid}"
    return f"{tag} (id={uid})"


async def finalize_upload(uid: int, tag: str):
    """Ждём паузу 5 сек и пересылаем все накопленные файлы администратору."""
    await asyncio.sleep(5)
    store = pending_uploads.get(uid)
    if not store:
        return

    # если за последние 5 сек ничего не прилетало — считаем, что пользователь закончил
    if (datetime.now() - store["last_time"]).total_seconds() >= 5:
        files = store["files"]
        desc = store.get("desc", "").strip()
        if not files:
            pending_uploads.pop(uid, None)
            return

        # 1️⃣ сообщение "от кого"
        info_text = f"📩 Материал от {tag}"
        if desc:
            info_text += f"\n\n📝 Описание:\n{desc}"

        info_msg = await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            message_thread_id=TOPIC_MATERIAL,
            text=info_text
        )
        topic_link[info_msg.message_id] = uid

        # 2️⃣ файлы батчами по 10
        for i in range(0, len(files), 10):
            batch = files[i:i + 10]
            await bot.send_media_group(
                chat_id=ADMIN_CHAT_ID,
                message_thread_id=TOPIC_MATERIAL,
                media=batch
            )
            await asyncio.sleep(0.7)

        # 3️⃣ уведомляем пользователя
        await bot.send_message(uid, "✅ Материал доставлен!", reply_markup=menu_kb)

        pending_uploads.pop(uid, None)
        user_mode[uid] = None


# ==============================
# ХЕНДЛЕРЫ
# ==============================
@dp.message(CommandStart())
async def start_handler(message: Message):
    user_mode[message.from_user.id] = None
    await message.answer(TEXT_MENU_TITLE, reply_markup=menu_kb)


@dp.message(F.text == "📸 Отправить материал")
async def send_material(message: Message):
    user_mode[message.from_user.id] = "material"
    await message.answer(
        "📸 Прикрепи фото или видео материал, можешь добавить описание.",
        reply_markup=back_kb
    )


@dp.message(F.text == "❓ Задать вопрос")
async def ask_question(message: Message):
    user_mode[message.from_user.id] = "question"
    await message.answer(
        "✍️ Напиши любой вопрос по урокам физкультуры и спорту в школе.\n"
        "Тебе ответят здесь в ближайшее время.",
        reply_markup=back_kb
    )


@dp.message(F.text == TEXT_BACK_BTN)
async def back_to_menu(message: Message):
    user_mode[message.from_user.id] = None
    await message.answer(TEXT_MENU_TITLE, reply_markup=menu_kb)


@dp.message()
async def handle_user_message(message: Message):
    mode = user_mode.get(message.from_user.id)
    tag = user_tag(message)

    # ---- МАТЕРИАЛ ----
    if mode == "material":
        uid = message.from_user.id
        store = pending_uploads.setdefault(uid, {"last_time": datetime.now(), "files": [], "desc": ""})
        updated = False

        if message.photo:
            store["files"].append(InputMediaPhoto(media=message.photo[-1].file_id))
            updated = True
        elif message.video:
            store["files"].append(InputMediaVideo(media=message.video.file_id))
            updated = True
        elif message.document:
            store["files"].append(InputMediaDocument(media=message.document.file_id))
            updated = True
        elif message.text:
            if store["files"]:
                store["desc"] = (store["desc"] + "\n" + message.text).strip()
                updated = True
            else:
                await message.answer(
                    "📸 Прикрепи фото или видео материал, можешь добавить описание.",
                    reply_markup=back_kb
                )
                return

        if updated:
            store["last_time"] = datetime.now()
            asyncio.create_task(finalize_upload(uid, tag))
            return

        await message.answer(
            "📸 Прикрепи фото или видео материал, можешь добавить описание.",
            reply_markup=back_kb
        )
        return

    # ---- ВОПРОС ----
    elif mode == "question":
        info_text = f"❓ Вопрос от {tag}\n\n{message.text}"
        msg = await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            message_thread_id=TOPIC_QUESTION,
            text=info_text
        )
        topic_link[msg.message_id] = message.from_user.id
        await message.answer("✅ Вопрос отправлен! Ожидай ответ.", reply_markup=menu_kb)
        user_mode[message.from_user.id] = None
        return

    # ---- ДЕФОЛТ ----
    await message.answer(TEXT_MENU_TITLE, reply_markup=menu_kb)


# ==============================
# ОБРАБОТКА ОТВЕТА ОТ УЧИТЕЛЯ
# ==============================
@dp.message(F.chat.id == ADMIN_CHAT_ID)
async def handle_admin_reply(message: Message):
    if message.reply_to_message:
        ref = topic_link.get(message.reply_to_message.message_id)
        if ref:
            await bot.send_message(ref, f"💬 Ответ от учителя:\n\n{message.text}")
            return


# ==============================
# ЗАПУСК
# ==============================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
