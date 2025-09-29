import json
import logging
import os
from pathlib import Path
from typing import Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    AIORateLimiter,
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

LOGGER = logging.getLogger(__name__)


def load_env_int(name: str) -> Optional[int]:
    value = os.getenv(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer") from exc


BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = load_env_int("GROUP_ID")
WORK_TOPIC_ID = load_env_int("WORK_TOPIC_ID")
QUESTION_TOPIC_ID = load_env_int("QUESTION_TOPIC_ID")
STORE_PATH = Path(os.getenv("STORE_PATH", "data/questions.json"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")

if GROUP_ID is None:
    raise RuntimeError("GROUP_ID environment variable is required")

if WORK_TOPIC_ID is None:
    raise RuntimeError("WORK_TOPIC_ID environment variable is required")

if QUESTION_TOPIC_ID is None:
    raise RuntimeError("QUESTION_TOPIC_ID environment variable is required")


class QuestionStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                LOGGER.warning("Could not decode JSON from %s, starting with empty store", self.path)
                self._data = {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, group_message_id: int, user_id: int) -> None:
        self._data[str(group_message_id)] = user_id
        self._save()

    def get(self, group_message_id: int) -> Optional[int]:
        return self._data.get(str(group_message_id))


STORE = QuestionStore(STORE_PATH)

CHOICE_SEND_WORK = "send_work"
CHOICE_SEND_QUESTION = "send_question"
USER_STATE_KEY = "awaiting"
STATE_WORK = "work"
STATE_QUESTION = "question"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(text="Отправить фото/видео", callback_data=CHOICE_SEND_WORK),
            InlineKeyboardButton(text="Отправить вопрос", callback_data=CHOICE_SEND_QUESTION),
        ]
    ])

    await update.effective_message.reply_text(
        "Привет! Выберите действие:",
        reply_markup=keyboard,
    )


async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    await query.answer()

    choice = query.data
    if choice == CHOICE_SEND_WORK:
        context.user_data[USER_STATE_KEY] = STATE_WORK
        await query.edit_message_text(
            "Пришлите фото или видео с описанием.\n"
            "Можете добавить описание в подпись или отдельным сообщением."
        )
    elif choice == CHOICE_SEND_QUESTION:
        context.user_data[USER_STATE_KEY] = STATE_QUESTION
        await query.edit_message_text("Введите ваш вопрос текстом.")
    else:
        await query.edit_message_text("Неизвестный выбор. Нажмите /start, чтобы начать заново.")


async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    state = context.user_data.get(USER_STATE_KEY)

    if state is None:
        await message.reply_text("Нажмите /start, чтобы выбрать действие.")
        return

    sender = message.from_user

    if state == STATE_WORK:
        if not (message.photo or message.video):
            await message.reply_text("Нужно отправить фото или видео. Попробуйте снова.")
            return

        description_parts = []
        if message.caption:
            description_parts.append(message.caption)
        if message.text and not message.caption:
            description_parts.append(message.text)
        description = "\n\n".join(description_parts) if description_parts else ""

        if sender:
            header = (
                f"Запрос от {sender.full_name}"
                + (f" (@{sender.username})" if sender.username else "")
                + f"\nID: {sender.id}"
            )
        else:
            header = "Запрос от неизвестного пользователя"

        caption = f"{header}\n\n{description}" if description else header

        if message.photo:
            await message.photo[-1].copy_to(
                chat_id=GROUP_ID,
                message_thread_id=WORK_TOPIC_ID,
                caption=caption,
            )
        elif message.video:
            await message.video.copy_to(
                chat_id=GROUP_ID,
                message_thread_id=WORK_TOPIC_ID,
                caption=caption,
            )

        context.user_data.pop(USER_STATE_KEY, None)
        await message.reply_text("Спасибо! Ваше сообщение отправлено администраторам.")
    elif state == STATE_QUESTION:
        if not message.text:
            await message.reply_text("Пожалуйста, отправьте вопрос текстом.")
            return

        if sender:
            text = (
                f"Вопрос от {sender.full_name}"
                + (f" (@{sender.username})" if sender.username else "")
                + f"\nID: {sender.id}\n\n{message.text}"
            )
        else:
            text = f"Вопрос от неизвестного пользователя\n\n{message.text}"

        sent_message = await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=QUESTION_TOPIC_ID,
            text=text,
        )

        STORE.add(sent_message.message_id, message.chat_id)

        context.user_data.pop(USER_STATE_KEY, None)
        await message.reply_text("Ваш вопрос отправлен. Мы сообщим, как только появится ответ.")
    else:
        await message.reply_text("Не удалось определить ваш запрос. Нажмите /start, чтобы начать заново.")
        context.user_data.pop(USER_STATE_KEY, None)


async def handle_group_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message.reply_to_message:
        return

    if message.reply_to_message.from_user and message.reply_to_message.from_user.id != context.bot.id:
        return

    if message.is_topic_message and message.message_thread_id != QUESTION_TOPIC_ID:
        return

    user_id = STORE.get(message.reply_to_message.message_id)
    if user_id is None:
        LOGGER.debug("No user mapping for message %s", message.reply_to_message.message_id)
        return

    forward_caption = message.caption or message.text or ""

    if message.text and not message.caption:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Ответ администратора:\n\n{message.text}",
        )
    else:
        await message.copy_to(
            chat_id=user_id,
            caption=(f"Ответ администратора:\n\n{forward_caption}" if forward_caption else None),
        )


def build_application() -> Application:
    application: Application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .rate_limiter(AIORateLimiter())
        .build()
    )

    application.add_handler(CommandHandler("start", start, filters.ChatType.PRIVATE))
    application.add_handler(CallbackQueryHandler(handle_choice, pattern=f"^{CHOICE_SEND_WORK}$|^{CHOICE_SEND_QUESTION}$"))
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & (
                filters.PHOTO
                | filters.VIDEO
                | (filters.TEXT & ~filters.COMMAND)
            ),
            handle_private_message,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.ChatType.SUPERGROUP
            & filters.Chat(GROUP_ID)
            & filters.REPLY
            & (~filters.COMMAND),
            handle_group_reply,
        )
    )

    return application


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    application = build_application()
    LOGGER.info("Bot started")
    application.run_polling()


if __name__ == "__main__":
    main()
