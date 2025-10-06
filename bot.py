import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo
from aiogram.utils import executor
import asyncio

# -------------------------------
# 🔧 НАСТРОЙКИ
# -------------------------------
TOKEN = "8404546108:AAHM0CcJzk-7Mvrmk0K2tnnAD_-lUT19aI4"

# ID чата и топиков
CHAT_ID = -1002629914250
TOPIC_MATERIAL = 3   # "В работе"
TOPIC_QUESTION = 2   # "Вопросы"

# Инструкции (можно редактировать прямо здесь)
INSTRUCTION_MATERIAL = (
    "📸 Пришлите одно или несколько фото/видео.\n"
    "После отправки я передам их в раздел «В работе»."
)
INSTRUCTION_QUESTION = (
    "✉️ Отправьте ваш вопрос.\n"
    "Он появится в разделе «Вопросы», и вы получите ответ прямо сюда."
)

# -------------------------------
# 🧩 НАСТРОЙКА ЛОГГИРОВАНИЯ
# -------------------------------
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# -------------------------------
# 🧠 ХРАНЕНИЕ СОСТОЯНИЙ ПОЛЬЗОВАТЕЛЕЙ
# -------------------------------
user_state = {}  # user_id: "material" / "question"

# -------------------------------
# 📋 ГЛАВНОЕ МЕНЮ
# -------------------------------
def main_menu():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("❓ Задать вопрос", callback_data="ask_question"))
    kb.add(InlineKeyboardButton("📷 Отправить материал", callback_data="send_material"))
    return kb

# -------------------------------
# 📍 СТАРТ
# -------------------------------
@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    user_state.pop(message.from_user.id, None)
    await message.answer(
        "👋 Привет!\nВыберите, что хотите сделать:",
        reply_markup=main_menu()
    )

# -------------------------------
# 📍 ОБРАБОТКА КНОПОК
# -------------------------------
@dp.callback_query_handler(lambda c: c.data in ["ask_question", "send_material", "back_to_menu"])
async def process_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    if callback.data == "ask_question":
        user_state[user_id] = "question"
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu"))
        await callback.message.edit_text(INSTRUCTION_QUESTION, reply_markup=kb)

    elif callback.data == "send_material":
        user_state[user_id] = "material"
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu"))
        await callback.message.edit_text(INSTRUCTION_MATERIAL, reply_markup=kb)

    elif callback.data == "back_to_menu":
        user_state.pop(user_id, None)
        await callback.message.edit_text("👋 Главное меню:", reply_markup=main_menu())

# -------------------------------
# 📨 ПОЛУЧЕНИЕ СООБЩЕНИЙ
# -------------------------------
@dp.message_handler(content_types=types.ContentTypes.ANY)
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name

    state = user_state.get(user_id)

    # --- ВОПРОС ---
    if state == "question":
        await bot.send_message(
            chat_id=CHAT_ID,
            message_thread_id=TOPIC_QUESTION,
            text=f"❓ Вопрос от {username} (id={user_id}):\n\n{message.text or ''}"
        )
        await message.answer("✅ Вопрос отправлен!\n⬅️ Можете вернуться в меню:", reply_markup=main_menu())

    # --- МАТЕРИАЛ (альбомы) ---
    elif state == "material":
        media_group = []
        if message.media_group_id:
            # если это часть альбома
            state_media = user_state.setdefault(f"album_{message.media_group_id}", [])
            if message.photo:
                file_id = message.photo[-1].file_id
                state_media.append(InputMediaPhoto(media=file_id))
            elif message.video:
                file_id = message.video.file_id
                state_media.append(InputMediaVideo(media=file_id))

            # ждём 1 секунду, чтобы собрать все файлы
            await asyncio.sleep(1.5)
            if len(state_media) > 0 and state_media == user_state.get(f"album_{message.media_group_id}"):
                await bot.send_message(
                    chat_id=CHAT_ID,
                    message_thread_id=TOPIC_MATERIAL,
                    text=f"📩 Материал от {username} (id={user_id}):"
                )
                await bot.send_media_group(
                    chat_id=CHAT_ID,
                    message_thread_id=TOPIC_MATERIAL,
                    media=state_media
                )
                del user_state[f"album_{message.media_group_id}"]

        else:
            # одиночное фото или видео
            await bot.send_message(
                chat_id=CHAT_ID,
                message_thread_id=TOPIC_MATERIAL,
                text=f"📩 Материал от {username} (id={user_id}):"
            )
            if message.photo:
                await bot.send_photo(chat_id=CHAT_ID, message_thread_id=TOPIC_MATERIAL, photo=message.photo[-1].file_id)
            elif message.video:
                await bot.send_video(chat_id=CHAT_ID, message_thread_id=TOPIC_MATERIAL, video=message.video.file_id)
            elif message.document:
                await bot.send_document(chat_id=CHAT_ID, message_thread_id=TOPIC_MATERIAL, document=message.document.file_id)

        await message.answer("✅ Материал отправлен!\n⬅️ Можете вернуться в меню:", reply_markup=main_menu())

# -------------------------------
# 🔁 ОТВЕТ АДМИНА
# -------------------------------
@dp.message_handler(lambda msg: msg.chat.id == CHAT_ID and msg.is_reply)
async def handle_admin_reply(message: types.Message):
    try:
        text = message.reply_to_message.text
        if not text:
            return

        user_id = None
        for part in text.split():
            if part.startswith("(id="):
                user_id = int(part[4:-2])
                break

        if user_id:
            reply_text = f"💬 Ответ от администратора:\n\n{message.text}"
            await bot.send_message(chat_id=user_id, text=reply_text)
            logging.info(f"[BOT] Ответ отправлен пользователю {user_id}")

    except Exception as e:
        logging.error(f"[ERROR] Ошибка при пересылке ответа: {e}")

# -------------------------------
# 🚀 ЗАПУСК
# -------------------------------
if __name__ == "__main__":
    logging.info("[BOT] Запуск...")
    executor.start_polling(dp, skip_updates=True)
