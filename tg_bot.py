# tg_bot.py

"""Телеграм-бот, принимающий Excel-файл (.xlsx) со списком товаров и
распределяющий товары по категориям и подкатегориям.

Перед запуском:
1. Создайте в Telegram нового бота у @BotFather и скопируйте токен.
2. Поместите токен в переменную ``TOKEN`` ниже или передайте через переменную
   окружения ``TG_BOT_TOKEN``.
3. Установите зависимости: ``pip install -r requirements.txt``.
4. Запустите: ``python tg_bot.py``.
"""

import os
import tempfile
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ---------------------------------------------------------------------------
# Замените значение переменной на ваш токен или установите переменную
# окружения TG_BOT_TOKEN, чтобы токен подтянулся автоматически.
# ---------------------------------------------------------------------------
TOKEN: str | None = os.getenv("TG_BOT_TOKEN")
# ID администратора, которому разрешено отправлять файлы
ADMIN_USER_ID = 6413686861

# Файл для постоянного хранения загруженного каталога
CATALOG_FILE = "catalog_data.json"

# Названия кнопок главного меню
BTN_CHOOSE_CATEGORY = "Выбор категории"
BTN_CONTACT_MANAGER = "Связаться с менеджером"
BTN_SUBSCRIBE = "Подписаться"   

# Ссылки для связи с менеджером
MANAGER_TELEGRAM_LINK = "https://t.me/tanya_chilikova"
# Замените номер на актуальный формат для WhatsApp chat link
MANAGER_WHATSAPP_LINK = "https://wa.me/79278783209"

MAIN_MENU_MARKUP = ReplyKeyboardMarkup(
    [[BTN_CHOOSE_CATEGORY, BTN_CONTACT_MANAGER, BTN_SUBSCRIBE]],
    resize_keyboard=True,
)


def _load_catalog_from_disk() -> dict | None:
    """Пытаемся загрузить каталог из файла JSON."""
    if os.path.exists(CATALOG_FILE):
        try:
            with open(CATALOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _save_catalog_to_disk(catalog: dict) -> None:
    """Сохраняем каталог в файл JSON."""
    try:
        with open(CATALOG_FILE, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start: приветствие и вывод каталога, если он загружен."""
    # Приветственное сообщение
    greet_text = (
        "Здравствуйте! Приветствуем вас в нашем каталоге. "
        "Вот что мы можем вам предложить"
    )
    await update.message.reply_text(greet_text, reply_markup=MAIN_MENU_MARKUP)

    # Показать каталог, если он уже был загружен администратором
    catalog: dict | None = context.application.bot_data.get("catalog")
    if not catalog:
        # Пробуем подгрузить с диска при первом обращении
        catalog = _load_catalog_from_disk()
        if catalog:
            context.application.bot_data["catalog"] = catalog
    if catalog:
        buttons = [[InlineKeyboardButton(text=cat, callback_data=f"cat|{cat}")] for cat in catalog.keys()]
        markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text("Выберите категорию:", reply_markup=markup)
    else:
        await update.message.reply_text("Каталог пока не загружен. Пожалуйста, попробуйте позже.")


# -------------------------------------------------------------------
# Правила классификации категорий и брендов (обновлено)
# -------------------------------------------------------------------

# Каждый элемент: (Категория, [список ключевых слов в нижнем регистре])
# Порядок — чем выше, тем выше приоритет.
CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    # Отдельные специфичные категории → приоритет выше
    ("Телефоны противоударные", [
        "blackview", "doogee", "oukitel", "unihertz", "rugged", "armor", "tank", "cyber", "mega"
    ]),
    ("Телефоны кнопочные", ["nokia", "f+", "button phone", "feature phone"]),
    ("Игровые консоли", ["playstation", "ps4", "ps5", "xbox", "switch", "steam deck", "джойстик", "игровая консоль"]),
    ("Go Pro", ["gopro", "hero"]),
    ("Пылесосы", ["пылесос", "vacuum", "робот-пылесос", "dyson", "dreame", "submarine"]),
    ("Планшеты", ["ipad", " galaxy tab", "tab ", "redmi pad", "poco pad", "tablet", "pad "]),
    ("Ноутбуки", ["ноутбук", "macbook", "magicbook", "matebook", "redmi book", "aspire", "ideapad", "ultrabook", "chromebook"]),
    ("Колонки", ["колонка", "speaker", "jbl", "marshall", "sber", "яндекс", "boombox", "partybox", "stanmore", "woburn", "макс"]),
    ("Наушники", ["наушник", "наушники", "airpods", "buds", "earphones", "earbuds", "sony wh-", "jbl tune", "marshall minor", "marshall major", "гарнитура"]),
    ("Часы", ["часы", "watch", "smart band", "galaxy fit", "fitbit", "amazfit", "gtr", "gt3"]),
    ("Телефоны", [
        "iphone", "samsung", "x.mi", "x.poco", "x.redmi", "honor", "google pixel", "zte", "realme",
        "oneplus", "asus zenfone", "смартфон", "smartphone", "galaxy"
    ]),
    ("Аксессуары", [
        "сзу", "сетевое зарядное устройство", "кабель", "переходник", "pencil", "keyboard", "mouse",
        "adapter", "magsafe", "беспроводная зарядка", "powerbank", "power bank", "чехол", "case", "cover"
    ]),
]

# Бренды, используемые как подкатегории (по ключевым словам)
BRAND_KEYWORDS: dict[str, str] = {
    # Смартфоны и электроника
    "apple": "Apple",
    "iphone": "Apple",
    "samsung": "Samsung",
    "galaxy": "Samsung",
    "xiaomi": "Xiaomi",
    "redmi": "Xiaomi",
    "poco": "Xiaomi",
    "mi ": "Xiaomi",
    "honor": "HONOR",
    "huawei": "Huawei",
    "google": "Google",
    "pixel": "Google",
    "zte": "ZTE",
    "realme": "Realme",
    "oneplus": "OnePlus",
    "asus": "ASUS",
    "zenfone": "ASUS",
    "lenovo": "Lenovo",
    "acer": "Acer",
    "gigabyte": "Gigabyte",
    "machenike": "Machenike",
    # Наушники и звук
    "jbl": "JBL",
    "marshall": "Marshall",
    "sony": "SONY",
    "sber": "Sber",
    "яндекс": "Яндекс",
    # Пылесосы и техника
    "dyson": "Dyson",
    "dreame": "Dreame",
    # Телефоны кнопочные / противоударные
    "nokia": "Nokia",
    "f+": "F+",
    "blackview": "Blackview",
    "doogee": "DOOGEE",
    "oukitel": "OUKITEL",
    "unihertz": "Unihertz",
    # Прочее
    "gopro": "GoPro",
    "garmin": "Garmin",
    "fitbit": "Fitbit",
}


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /add — загрузить новый Excel-файл с каталогом (только админ)."""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("Извините, команда доступна только администратору.")
        return

    # Помечаем, что ждём файл от администратора
    context.user_data["awaiting_file"] = True
    await update.message.reply_text(
        "Отправьте Excel-файл (.xlsx) с обновлённой базой товаров."
    )


def extract_category(description: str) -> tuple[str, str]:
    """Определяем (category, subcategory) по описанию товара."""
    desc_low = description.lower()

    # 1. Категория (по ключевым словам, приоритетно в указанном порядке)
    category = "Другое"
    for cat, keywords in CATEGORY_KEYWORDS:
        if any(kw in desc_low for kw in keywords):
            category = cat
            break

    # 2. Попытка извлечь бренд — сначала первое слово
    subcategory = "Общее"
    first_word = description.split()[0].strip(',.;:"()').lower() if description else ""
    if first_word and first_word in BRAND_KEYWORDS:
        subcategory = BRAND_KEYWORDS[first_word]
    else:
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                subcategory = brand
                break

    # Особое правило: для категории Go Pro всегда бренд GoPro
    if category == "Go Pro":
        subcategory = "GoPro"

    return category, subcategory


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """При получении документа проверяем, что это .xlsx, скачиваем и обрабатываем."""
    user_id = update.effective_user.id if update.effective_user else None
    awaiting_file = context.user_data.get("awaiting_file")

    # Принимаем файл только от администратора и только после команды /add
    if user_id != ADMIN_USER_ID or not awaiting_file:
        await update.message.reply_text(
            "Извините, сейчас бот не ожидает файл или у вас нет прав загрузки."
        )
        return

    # Сбрасываем флаг ожидания файла
    context.user_data["awaiting_file"] = False

    document = update.message.document
    if not document:
        return

    if not document.file_name.lower().endswith(".xlsx"):
        await update.message.reply_text(
            "Пожалуйста, отправьте файл в формате .xlsx. Другие форматы не поддерживаются."
        )
        return

    # Сохраняем файл во временную директорию
    tmp_dir = Path(tempfile.mkdtemp())
    src_path = tmp_dir / document.file_name
    file_obj = await document.get_file()
    await file_obj.download_to_drive(str(src_path))

    try:
        # Читаем Excel
        df = pd.read_excel(src_path)
    except Exception as exc:
        await update.message.reply_text(
            "Не удалось прочитать файл как Excel: " f"{exc}"
        )
        return

    # Строим каталог по описанию
    catalog: dict[str, dict[str, list[dict[str, str]]]] = {}
    for _, row in df.iterrows():
        desc = str(row.get("description") or row.get("desription") or "")
        price = row.get("price") or row.get("Цена") or row.get("Price") or ""
        cat, sub = extract_category(desc)
        catalog.setdefault(cat, {}).setdefault(sub, []).append({"desc": desc, "price": price})

    if not catalog:
        await update.message.reply_text("Не удалось сформировать категории по описанию.")
        return

    # Сохраняем каталог в bot_data (общий для всех пользователей)
    context.application.bot_data["catalog"] = catalog
    # А также на диск, чтобы каталог сохранялся между перезапусками бота
    _save_catalog_to_disk(catalog)

    # Отправляем пользователю выбор категорий
    buttons = [[InlineKeyboardButton(text=cat, callback_data=f"cat|{cat}")] for cat in catalog.keys()]
    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Каталог загружен! Выберите категорию:", reply_markup=markup)

    # Удаляем временный файл
    try:
        os.remove(src_path)
        os.rmdir(tmp_dir)
    except OSError:
        pass


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатий на кнопки ReplyKeyboard."""
    text = update.message.text
    if text == BTN_CHOOSE_CATEGORY:
        catalog: dict | None = context.application.bot_data.get("catalog")
        if catalog:
            buttons = [[InlineKeyboardButton(text=cat, callback_data=f"cat|{cat}")] for cat in catalog.keys()]
            markup = InlineKeyboardMarkup(buttons)
            await update.message.reply_text("Выберите категорию:", reply_markup=markup)
        else:
            await update.message.reply_text("Каталог пока не загружен. Пожалуйста, попробуйте позже.")
    elif text == BTN_CONTACT_MANAGER:
        # Кнопки с ссылками на менеджера
        link_btn_tg = InlineKeyboardButton("Написать менеджеру в Телеграм", url=MANAGER_TELEGRAM_LINK)
        link_btn_wa = InlineKeyboardButton("Написать менеджеру в WhatsApp", url=MANAGER_WHATSAPP_LINK)
        await update.message.reply_text(
            "Выберите удобный способ связи с нашим менеджером:",
            reply_markup=InlineKeyboardMarkup([[link_btn_tg], [link_btn_wa]]),
        )
    elif text == BTN_SUBSCRIBE:
        subs: set[int] = context.application.bot_data.setdefault("subscribers", set())
        user_id = update.effective_user.id if update.effective_user else None
        if user_id:
            subs.add(user_id)
            await update.message.reply_text("Спасибо! Вы подписаны на обновления.")
        else:
            await update.message.reply_text("Не удалось выполнить подписку.")


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    parts = data.split("|")
    if not parts:
        return

    catalog = context.application.bot_data.get("catalog")
    if not catalog:
        await query.edit_message_text("Каталог не найден. Загрузите файл командой /add.")
        return

    if parts[0] == "cat":  # Выбрана категория
        cat = parts[1]
        subcats = catalog.get(cat, {})
        buttons = [[InlineKeyboardButton(text=sub, callback_data=f"sub|{cat}|{sub}")]
                   for sub in subcats.keys()]
        # Кнопка назад на уровень выше отсутствует (это корень)
        buttons.append([InlineKeyboardButton(text="← Назад", callback_data="back|root")])
        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(f"Категория: {cat}\nВыберите подкатегорию:", reply_markup=markup)

    elif parts[0] == "sub":  # Выбрана подкатегория
        cat, sub = parts[1], parts[2]
        items = catalog.get(cat, {}).get(sub, [])
        text_lines = [f"{item['desc']} — {item['price']}" for item in items]
        text = "\n".join(text_lines) or "Нет товаров."
        buttons = [[InlineKeyboardButton(text="← Назад", callback_data=f"cat|{cat}")]]
        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(
            f"Категория: {cat} / {sub}\n\n{text}", reply_markup=markup
        )

    elif parts[0] == "back":
        # Назад к списку категорий
        buttons = [[InlineKeyboardButton(text=cat, callback_data=f"cat|{cat}")] for cat in catalog.keys()]
        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text("Выберите категорию:", reply_markup=markup)


def main() -> None:
    """Запуск бота."""
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise RuntimeError(
            "Необходимо задать токен Telegram-бота. "
            "Отредактируйте переменную TOKEN или задайте TG_BOT_TOKEN."
        )

    app = ApplicationBuilder().token(TOKEN).build()

    # Загружаем каталог с диска при старте и сохраняем в bot_data
    initial_catalog = _load_catalog_from_disk()
    if initial_catalog:
        app.bot_data["catalog"] = initial_catalog

    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND) & (~filters.Document.ALL), handle_text))
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    # Запускаем бесконечный поллинг
    print("Бот запущен. Нажмите Ctrl-C для остановки.")
    app.run_polling()


if __name__ == "__main__":
    main() 