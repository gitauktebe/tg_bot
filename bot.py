import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InputMediaPhoto, InputMediaVideo
)

# 🔧 Настройки
TOKEN = "ТВОЙ_ТОКЕН"
ADMIN_CHAT_ID = -1002404070892  # ID группы с темами
TOPIC_MATERIAL = 12              # ID топика «В работе»
TOPIC_QUESTION = 10              # ID топика «Вопросы»

# 🔧 Инструкции (можно менять)
TEXT_MATERIAL = "📸 Отправь сюда фото или видео. Всё, что ты пришлёшь, попадёт в тему 'В работе'."
TEXT_QUESTION = "💬 Напиши свой вопрос, и он появится в теме 'Вопросы'."
TEXT_BACK = "↩️ Назад в главное меню"

# Логирование
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Словарь для хранения связи {message_id_в_топике: user_id}
message_links = {}

# Главное меню
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📸 Отправить материал")],
        [KeyboardButton(text="💬 Задать вопрос")]
    ],
    resize_keyboard=True
)

# Меню с кнопкой "Назад"
back_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=TEXT_BACK)]],
    resize_keyboard=True
)

# /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("👋 Привет! Выбери, что хочешь сделать:", reply_markup=main_menu)

# Обработка кнопки "Материал"
@dp.message(lambda m: m.text == "📸 Отправить материал")
async def send_material_info(message: Message):
    await message.answer(TEXT_MATERIAL, reply_markup=back_menu)

# Обработка кнопки "Вопрос"
@dp.message(lambda m: m.text == "💬 Задать вопрос")
async def send_question_info(message: Message):
    await message.answer(TEXT_QUESTION, reply_markup=back_menu)

# Кнопка "Назад"
@dp.message(lambda m: m.text == TEXT_BACK)
async def go_back(message: Message):
    await message.answer("Главное меню:", reply_markup=main_menu)

# Получение медиа/текста от пользователя
@dp.message()
async def handle_user_message(message: Message):
    user_info = f"{message.from_user.full_name} (@{message.from_user.username or 'без_username'}) (id={message.from_user.id})"

    # Если фото или видео
    if message.photo or message.video:
        media_group = []
        if message.photo:
            media_group.append(InputMediaPhoto(media=message.photo[-1].file_id))
        elif message.video:
            media_group.append(InputMediaVideo(media=message.video.file_id))

        sent_messages = await bot.send_media_group(
            chat_id=ADMIN_CHAT_ID,
            message_thread_id=TOPIC_MATERIAL,
            media=media_group
        )
        # Отправим подпись отдельно
        msg = await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"📸 Материал от {user_info}",
            message_thread_id=TOPIC_MATERIAL
        )
        message_links[msg.message_id] = message.from_user.id

    # Если текст (вопрос)
    elif message.text:
        msg = await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"❓ Вопрос от {user_info}:\n{message.text}",
            message_thread_id=TOPIC_QUESTION
        )
        message_links[msg.message_id] = message.from_user.id

# 🔹 Ответы админа в топиках
@dp.message(lambda m: m.chat.id == ADMIN_CHAT_ID)
async def admin_reply(message: Message):
    if message.reply_to_message and message.reply_to_message.message_id in message_links:
        user_id = message_links[message.reply_to_message.message_id]
        try:
            if message.text:
                await bot.send_message(user_id, f"📩 Ответ от администрации:\n{message.text}")
            elif message.photo:
                await bot.send_photo(user_id, message.photo[-1].file_id, caption="📩 Ответ от администрации")
            elif message.video:
                await bot.send_video(user_id, message.video.file_id, caption="📩 Ответ от администрации")
        except Exception as e:
            logging.error(f"Ошибка при отправке ответа пользователю: {e}")

# 🔹 Запуск
async def main():
    logging.info("[BOT] Запуск...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
