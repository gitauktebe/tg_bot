import asyncio
import time
from collections import defaultdict
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InputMediaPhoto, InputMediaVideo
)
from aiogram.filters import CommandStart

# === КОНФИГ ===
TOKEN = "8404546108:AAHM0CcJzk-7Mvrmk0K2tnnAD_-lUT19aI4"
ADMIN_CHAT_ID = -1002629914250     # супергруппа админов
TOPIC_WORK = 3                     # тема "В работе"
TOPIC_QUESTIONS = 2                # тема "Вопросы"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# === ХРАНИЛКИ СОСТОЯНИЙ ===
user_state: dict[int, str | None] = {}       # {user_id: "work"|"question"|None}
message_links: dict[int, int] = {}           # {group_message_id: user_id} — для reply на любое сообщение
album_buffer: dict[str, list[Message]] = defaultdict(list)  # {media_group_id: [messages]}
header_sessions: dict[int, dict] = {}        # {user_id: {"expires": ts, "thread_id": int, "header_msg_id": int}}
header_links: dict[int, int] = {}            # {header_message_id: user_id} — чтобы reply по заголовку тоже работал

HEADER_TTL = 60  # сек; сколько времени считаем «одной сессией» для единичного заголовка

# === КЛАВИАТУРЫ ===
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

# ===== ВСПОМОГАТЕЛЬНОЕ =====
def user_label(m: Message) -> str:
    return f"{m.from_user.full_name} (@{m.from_user.username})" if m.from_user.username else m.from_user.full_name

async def ensure_header(user_id: int, thread_id: int, prefix_text: str) -> int | None:
    """
    Гарантирует, что заголовок отправлен один раз в начале «сессии».
    Возвращает message_id заголовка (если был отправлен сейчас), иначе None.
    """
    now = time.time()
    sess = header_sessions.get(user_id)
    need_header = (
        not sess or
        now > sess.get("expires", 0) or
        sess.get("thread_id") != thread_id
    )
    if need_header:
        msg = await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=prefix_text,
            message_thread_id=thread_id
        )
        header_sessions[user_id] = {
            "expires": now + HEADER_TTL,
            "thread_id": thread_id,
            "header_msg_id": msg.message_id
        }
        header_links[msg.message_id] = user_id  # чтобы можно было ответить прямо на заголовок
        return msg.message_id
    return None

def thread_and_prefix(state: str, m: Message) -> tuple[int, str]:
    """Возвращает (thread_id, header_text) по состоянию пользователя."""
    uname = user_label(m)
    if state == "question":
        return (TOPIC_QUESTIONS, f"❓ Вопрос от {uname} (id={m.from_user.id}):")
    else:
        return (TOPIC_WORK, f"📤 Материал от {uname} (id={m.from_user.id}):")

# ===== ОБРАБОТЧИКИ ПОЛЬЗОВАТЕЛЯ =====
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_state[message.from_user.id] = None
    await message.answer("Привет 👋 Выберите действие:", reply_markup=main_kb)

@dp.message(F.text == "📤 Отправить материал")
async def set_work(message: Message):
    user_state[message.from_user.id] = "work"
    await message.answer("Прикрепи фото или видео + дай краткое описание", reply_markup=back_kb)

@dp.message(F.text == "❓ Задать вопрос")
async def set_question(message: Message):
    user_state[message.from_user.id] = "question"
    await message.answer("Задай любой вопрос по уроку физкультуры и спорту в школе. Я отвечу позже.", reply_markup=back_kb)

@dp.message(F.text.in_(["⬅️ Назад", "⬅ Назад"]))
async def go_back(message: Message):
    user_state[message.from_user.id] = None
    await message.answer("Выберите действие:", reply_markup=main_kb)

# --- АЛЬБОМЫ (media_group) ---
@dp.message(F.media_group_id, F.chat.type == "private")
async def handle_album(message: Message):
    state = user_state.get(message.from_user.id)
    if state not in ["work", "question"]:
        return

    mgid = message.media_group_id
    album_buffer[mgid].append(message)

    # Небольшая задержка, чтобы собрать все части альбома
    await asyncio.sleep(1.1)

    # Только один из обработчиков «выгребает» пакет
    messages = album_buffer.pop(mgid, None)
    if not messages:
        return

    thread_id, header_text = thread_and_prefix(state, message)

    # Заголовок — ОДИН РАЗ в начале (на первую пачку, а дальше в течение HEADER_TTL не повторяем)
    await ensure_header(message.from_user.id, thread_id, header_text)

    # Готовим медиа-группу (фото/видео). Telegram принимает до 10 в одном вызове.
    media: list[InputMediaPhoto | InputMediaVideo] = []
    for m in messages:
        if m.photo:
            # Берём самое большое фото
            media.append(InputMediaPhoto(media=m.photo[-1].file_id))
        elif m.video:
            media.append(InputMediaVideo(media=m.video.file_id))
        # NOTE: документы в альбом не входят — если надо, присылаются отдельно и обработаются нижним хэндлером

    # Отправляем пачкой
    sent_msgs = await bot.send_media_group(chat_id=ADMIN_CHAT_ID, media=media, message_thread_id=thread_id)

    # Любой reply на ЛЮБОЕ из сообщений пачки должен вернуться пользователю
    for s in sent_msgs:
        message_links[s.message_id] = message.from_user.id

# --- ОДИНОЧНЫЕ СООБЩЕНИЯ ИЗ ЛИЧКИ ---
@dp.message(F.chat.type == "private")
async def handle_single(message: Message):
    state = user_state.get(message.from_user.id)
    if state not in ["work", "question"]:
        return

    thread_id, header_text = thread_and_prefix(state, message)

    if message.text:
        # Для текста удобнее отправить одной строкой с подписью
        sent = await bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"{header_text}\n{message.text}",
            message_thread_id=thread_id
        )
        message_links[sent.message_id] = message.from_user.id
    else:
        # Для медиа/файлов — выводим заголовок один раз на сессию,
        # затем копируем само сообщение в тему
        await ensure_header(message.from_user.id, thread_id, header_text)
        copy = await message.send_copy(chat_id=ADMIN_CHAT_ID, message_thread_id=thread_id)
        message_links[copy.message_id] = message.from_user.id

# ===== ОТВЕТЫ АДМИНОВ ИЗ ГРУППЫ =====
@dp.message(F.chat.id == ADMIN_CHAT_ID)
async def admin_reply(message: Message):
    if not message.reply_to_message:
        return

    # Смотрим, на что ответил админ: на заголовок или на конкретное сообщение медиа/текста
    orig_id = message.reply_to_message.message_id
    user_id = message_links.get(orig_id) or header_links.get(orig_id)

    if not user_id:
        return  # не нашли связь — пропускаем

    # Отправляем пользователю с подписью
    if message.text:
        await bot.send_message(chat_id=user_id, text=f"📩 Ответ от учителя:\n\n{message.text}")

    # Если у админа вложения — пересылаем как есть
    if any([message.photo, message.document, message.video, message.audio, message.voice, message.sticker, message.animation]):
        await message.send_copy(chat_id=user_id)

# ===== ЗАПУСК =====
async def main():
    print("[BOT] Запуск...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
