from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
import asyncio

# === НАСТРОЙКИ ===
TOKEN = "8404546108:AAHM0CcJzk-7Mvrmk0K2tnnAD_-lUT19aI4"
ADMIN_CHAT_ID = -1002629914250
TOPIC_WORK = 3
TOPIC_QUESTIONS = 2

bot = Bot(token=TOKEN)
dp = Dispatcher()

user_state = {}       # {user_id: "work" или "question"}
message_links = {}    # {group_msg_id: user_id}

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📤 Отправить материал")],
        [KeyboardButton(text="❓ Задать вопрос")]
    ],
    resize_keyboard=True
)

back_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="⬅️ Назад")]],
    resize_keyboard=True
)

# /start
@dp.message(CommandStart())
async def start_cmd(message: Message):
    print(f"[INFO] Пользователь {message.from_user.id} ({message.from_user.full_name}) нажал /start")
    await message.answer("Привет! 👋 Выберите действие:", reply_markup=main_kb)
    user_state.pop(message.from_user.id, None)

# Назад
@dp.message(F.text == "⬅️ Назад")
async def go_back(message: Message):
    print(f"[INFO] Пользователь {message.from_user.id} вернулся в меню")
    user_state.pop(message.from_user.id, None)
    await message.answer("Главное меню 👇", reply_markup=main_kb)

# Отправить материал
@dp.message(F.text == "📤 Отправить материал")
async def send_material(message: Message):
    user_state[message.from_user.id] = "work"
    print(f"[STATE] Пользователь {message.from_user.id} теперь в режиме 'Материал'")
    await message.answer("Прикрепи фото или видео + дай краткое описание", reply_markup=back_kb)

# Задать вопрос
@dp.message(F.text == "❓ Задать вопрос")
async def ask_question(message: Message):
    user_state[message.from_user.id] = "question"
    print(f"[STATE] Пользователь {message.from_user.id} теперь в режиме 'Вопрос'")
    await message.answer("Задай любой вопрос касаемо урока физкультуры и спорта в школе, а я тебе отвечу в ближайшее время", reply_markup=back_kb)

# Пересылка сообщений пользователя в группу
@dp.message(F.chat.type == "private")
async def forward_to_group(message: Message):
    state = user_state.get(message.from_user.id)
    if state not in ["work", "question"]:
        return

    user_name = f"{message.from_user.full_name} (@{message.from_user.username})" if message.from_user.username else message.from_user.full_name
    prefix = "📤 Материал" if state == "work" else "❓ Вопрос"
    thread_id = TOPIC_WORK if state == "work" else TOPIC_QUESTIONS

    # Текст
    if message.text:
        content = f"{prefix} от {user_name} (id={message.from_user.id}):\n{message.text}"
        sent = await bot.send_message(chat_id=ADMIN_CHAT_ID, text=content, message_thread_id=thread_id)
        message_links[sent.message_id] = message.from_user.id
        print(f"[FORWARD] Переслан текст от {message.from_user.id} → группа (msg_id={sent.message_id})")
    else:
        # Вложения
        header = f"{prefix} от {user_name} (id={message.from_user.id}):"
        await bot.send_message(chat_id=ADMIN_CHAT_ID, text=header, message_thread_id=thread_id)
        copy = await message.send_copy(chat_id=ADMIN_CHAT_ID, message_thread_id=thread_id)
        message_links[copy.message_id] = message.from_user.id
        print(f"[FORWARD] Переслан файл от {message.from_user.id} → группа (msg_id={copy.message_id})")

# Ответ администратора → пользователю
@dp.message(F.chat.id == ADMIN_CHAT_ID)
async def admin_reply(message: Message):
    if not message.reply_to_message:
        return

    orig_msg_id = message.reply_to_message.message_id
    user_id = message_links.get(orig_msg_id)

    if not user_id:
        print(f"[WARN] Reply не найден: msg_id={orig_msg_id}")
        return

    text = f"📩 Ответ от учителя:\n\n{message.text or ''}"

    if message.text:
        await bot.send_message(chat_id=user_id, text=text)
        print(f"[REPLY] Ответ с текстом от админа → {user_id}")

    if message.photo or message.document or message.video or message.audio or message.voice:
        await message.send_copy(chat_id=user_id)
        print(f"[REPLY] Ответ с вложением от админа → {user_id}")

# Запуск
async def main():
    print("[BOT] Запуск...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
