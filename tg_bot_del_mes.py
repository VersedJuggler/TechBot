async def delete_all_user_messages(context, chat_id):
    msg_ids = context.user_data.pop("all_msg_ids", [])
    for msg_id in msg_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass

# tg_bot.py
import os
import tempfile
import json
import html
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
import shutil

# ---------------------------------------------------------------------------
# Замените значение переменной на ваш токен или установите переменную
# окружения TG_BOT_TOKEN, чтобы токен подтянулся автоматически.
# ---------------------------------------------------------------------------
TOKEN: str | None = os.getenv("TG_BOT_TOKEN")
# ID администраторов, которым разрешено отправлять файлы и выполнять привилегированные команды
ADMIN_USER_IDS: set[int] = {6413686861, 728567535, 510202114, 7548453140}

# Основные файлы для хранения
CATALOG_FILE = "catalog_data.json"
LATEST_EXCEL_FILE = "latest_catalog.xlsx"

# Названия кнопок главного меню
BTN_CHOOSE_CATEGORY = "🗂️ Выбор категории"
# Кнопка поиска по каталогу
BTN_CONTACT_MANAGER = "💬 Заказать товар у менеджера"
BTN_SUBSCRIBE = "✅ Подписаться"
BTN_GET_EXCEL = "💾 Получить Excel-файл"
BTN_SEARCH_CATALOG = "🔍 Поиск по каталогу"

# Добавим константу команды помощи
CMD_HELP = "help"

# Ссылки для связи с менеджером
MANAGER_TELEGRAM_LINK = "https://t.me/tanya_chilikova"
# Замените номер на актуальный формат для WhatsApp chat link
MANAGER_WHATSAPP_LINK = "https://wa.me/79278783209"

# Главное меню: первая строка – основные действия, вторая – поиск
MAIN_MENU_MARKUP = ReplyKeyboardMarkup(
    [
        [BTN_CHOOSE_CATEGORY, BTN_CONTACT_MANAGER],
        [BTN_SUBSCRIBE, BTN_GET_EXCEL],
        [BTN_SEARCH_CATALOG],
    ],
    resize_keyboard=True,
)

# Порядок отображения категорий в основном меню
PREFERRED_CATEGORY_ORDER: list[str] = [
    "Телефоны",
    "Планшеты",
    "Ноутбуки",
]


def _sort_categories(cat_names: list[str]) -> list[str]:
    """Возвращает список категорий в желаемом порядке отображения.

    1. Категории из PREFERRED_CATEGORY_ORDER – в указанной последовательности.
    2. Остальные (кроме "Другое") – по алфавиту.
    3. "Другое" – последней, если присутствует.
    """
    order_map = {name: idx for idx, name in enumerate(PREFERRED_CATEGORY_ORDER)}

    preferred = [c for c in PREFERRED_CATEGORY_ORDER if c in cat_names]
    other = sorted([c for c in cat_names if c not in order_map and c != "Другое"])
    tail = ["Другое"] if "Другое" in cat_names else []
    return preferred + other + tail


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
    chat_id = update.effective_chat.id
    await delete_all_user_messages(context, chat_id)
    m = await context.bot.send_message(chat_id=chat_id, text=greet_text, reply_markup=MAIN_MENU_MARKUP)
    context.user_data["all_msg_ids"] = [m.message_id]
    # Показать каталог, если он уже был загружен администратором
    catalog: dict | None = context.application.bot_data.get("catalog")
    if not catalog:
        catalog = _load_catalog_from_disk()
        if catalog:
            context.application.bot_data["catalog"] = catalog
    if catalog:
        buttons = []
        for cat_name in _sort_categories(list(catalog.keys())):
            subdict = catalog[cat_name]
            count = sum(len(items) for items in subdict.values())
            buttons.append([InlineKeyboardButton(text=f"{cat_name} ({count})", callback_data=f"cat|{cat_name}")])
        markup = InlineKeyboardMarkup(buttons)
        m2 = await context.bot.send_message(chat_id=chat_id, text="Выберите категорию:", reply_markup=markup)
        context.user_data["all_msg_ids"] = [m.message_id, m2.message_id]
    else:
        m2 = await context.bot.send_message(chat_id=chat_id, text="Каталог пока не загружен. Пожалуйста, попробуйте позже.", reply_markup=MAIN_MENU_MARKUP)
        context.user_data["all_msg_ids"] = [m.message_id, m2.message_id]


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
    ("Игровые консоли", [
        "playstation", "ps4", "ps5", "xbox", "switch", "steam deck",
        "джойстик", "игровая консоль", "игровая приставка",
        # VR-устройства
        "oculus", "quest", "vr", "vr headset", "vr шлем", "meta quest"
    ]),
    (
        "Экшен-камеры",
        [
            # GoPro
            "gopro", "go pro", "hero", "gopro hero", "gopro hero 10", "gopro hero 11", "gopro hero 12",
            "gopro hero 13", "gopro hero 14", "gopro hero 15", "gopro hero 16", "gopro hero 17", "gopro hero 18", "gopro hero 19", "gopro hero 20",
            # DJI Osmo Action
            "dji", "osmo action", "action 5", "action5", "osmo action 5", "osmoaction",
            # Insta360
            "insta", "insta360", "insta 360"
        ],
    ),
    # Новая категория: Фен-стайлер (фены, стайлеры для волос)
    (
        "Фен-стайлер",
        [
            "фен",
            "стайлер",
            "фен-стайлер",
            "hair dryer",
            "styler",
            "airwrap",
            "supersonic",
            "hd08",
            "hd-08",
            "hd16",
            "hd-16",
            "hs08",
            "hs-08",
            "ht01",
            "ht-01",
        ],
    ),
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
    # Экшен-камеры
    "dji": "DJI",
    "osmo": "DJI",
    "insta": "Insta360",
    "insta360": "Insta360",
    # VR / Игровые консоли
    "oculus": "Oculus",
    "quest": "Oculus",
}


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /add — загрузить новый Excel-файл с каталогом (только админ)."""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text("Извините, команда доступна только администратору.")
        return

    # Помечаем, что ждём файл от администратора
    context.user_data["awaiting_file"] = True
    await update.message.reply_text(
        "Отправьте Excel-файл (.xlsx) с обновлённой базой товаров."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help — выводит информацию о связи с менеджером."""
    link_btn_tg = InlineKeyboardButton("Написать менеджеру в Телеграм", url=MANAGER_TELEGRAM_LINK)
    link_btn_wa = InlineKeyboardButton("Написать менеджеру в WhatsApp", url=MANAGER_WHATSAPP_LINK)
    await update.message.reply_text(
        "Выберите удобный способ связи с нашим менеджером:",
        reply_markup=InlineKeyboardMarkup([[link_btn_tg], [link_btn_wa]]),
    )


import re

def extract_category(description: str) -> tuple[str, str]:
    """
    Категоризация товара по описанию с учетом приоритетов, перекрестных признаков и гибких правил.
    """
    desc = description or ""
    desc_low = desc.lower()
    category = "Другое"
    subcategory = "Общее"


    # --- 1. Наушники (приоритет: явное слово, AirPods, EarPods, Buds, Earphones, Earbuds, гарнитура, даже если есть type-c, usb-c и т.д.) ---
    headphones_pattern = r"\b(наушник|наушники|airpods|air pods|air pod|earpods|ear pods|ear pod|earphones|earphone|earbuds|earbud|buds|гарнитура)\b"
    if re.search(headphones_pattern, desc_low):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Наушники", brand
        return "Наушники", "Общее"


    # --- 2. Планшеты (Pad, Tab, Tablet, кроме Notepad) ---
    # Гибкий паттерн: tab, tablet, pad, galaxy tab, redmi pad, poco pad, ipad, и т.д.
    tablet_pattern = r"(ipad|\btab\b|tablet|pad(?![a-z]))"
    if (re.search(tablet_pattern, desc_low) or re.search(r"pad[\s\d]", desc_low)) and not re.search(r"notepad", desc_low):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Планшеты", brand
        return "Планшеты", "Общее"

    # --- 3. Явные аксессуары (расширено) ---
    accessories_kw = [
        "аксессуар", "чехол", "стекло", "кабель", "шнур", "переходник", "adapter", "зарядка", "powerbank", "power bank", "magsafe", "pencil", "cover", "case", "screen protector", "беспроводная зарядка", "сетевое зарядное устройство", "сзу", "блок", "адаптер", "блок питания", "usb", "type-c", "lightning", "micro-usb", "магнитный кабель", "стекло защитное", "защитное стекло", "док-станция", "док станция", "док", "hub", "разветвитель", "splitter", "держатель", "mount", "подставка", "ремешок", "strap", "ремень", "пленка", "film", "наклейка", "наклейки", "stylus", "стилус"
    ]
    if any(re.search(rf"(?<![а-яa-z0-9]){re.escape(kw)}(?![а-яa-z0-9])", desc_low) for kw in accessories_kw):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Аксессуары", brand
        return "Аксессуары", "Общее"

    # --- 3. Колонки (исключая наушники) ---
    if re.search(r"\b(колонка|speaker|boombox|partybox|stanmore|woburn)\b", desc_low) and not re.search(r"наушник|наушники|buds|earbuds|гарнитура", desc_low):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Колонки", brand
        return "Колонки", "Общее"

    # --- 4. Часы и браслеты (Garmin, Band, Instinct и др.) ---
    if re.search(r"\b(часы|watch|band|fitbit|amazfit|gtr|gt3|instinct|forerunner|fenix|coros|garmin|band)\b", desc_low):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Часы", brand
        return "Часы", "Общее"

    # --- 5. Планшеты (Pad, Tab, Tablet, кроме Notepad) ---
    if (re.search(r"\bipad\b|\btab\b|\btablet\b|\bpad\b", desc_low) or re.search(r"pad[\s\d]", desc_low)) and not re.search(r"notepad", desc_low):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Планшеты", brand
        return "Планшеты", "Общее"

    # --- 6. Ноутбуки (Apple, Matebook, CPU, дюймы, модели) ---
    # Apple MacBook: Air/Pro + 13"/14"/15"/16"/M1/M2/M3/M4
    if (re.search(r"macbook|air|pro", desc_low) and (re.search(r"\d{2}\"", desc) or re.search(r"\bm[1-4]\b", desc_low))) or re.search(r"macbook", desc_low):
        return "Ноутбуки", "Apple"
    # Matebook, ноутбуки других брендов
    if re.search(r"matebook|notebook|ultrabook|chromebook|magicbook|aspire|ideapad|thinkpad|vivobook|zenbook|legion|gigabyte|machenike|lenovo|acer|asus|hp|dell|msi|huawei", desc_low):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Ноутбуки", brand
        return "Ноутбуки", "Общее"
    # Intel/AMD CPU + 13"/14"/15"/16"
    if re.search(r"(intel|amd|ryzen|core i[3579]|pentium|celeron)", desc_low) and re.search(r"\d{2}\"", desc):
        return "Ноутбуки", "Общее"

    # --- 7. Телефоны (Mate X, бренды, явные признаки) ---
    # Huawei Mate X6 — телефон, Matebook — ноутбук
    if re.search(r"matebook", desc_low):
        return "Ноутбуки", "Huawei"
    if re.search(r"mate", desc_low) and not re.search(r"matebook", desc_low):
        return "Телефоны", "Huawei"
    # Смартфоны по брендам и ключевым словам
    phone_kw = ["iphone", "смартфон", "smartphone", "galaxy", "pixel", "zenfone", "oneplus", "realme", "zte", "redmi", "poco", "xiaomi", "samsung", "huawei", "honor"]
    if any(re.search(rf"(?<![а-яa-z0-9]){re.escape(kw)}(?![а-яa-z0-9])", desc_low) for kw in phone_kw):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Телефоны", brand
        return "Телефоны", "Общее"

    # --- 8. Кнопочные и противоударные телефоны ---
    if re.search(r"button phone|feature phone|противоударный|rugged|armor|tank|cyber|mega|nokia|f\+|blackview|doogee|oukitel|unihertz", desc_low):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Телефоны противоударные", brand
        return "Телефоны противоударные", "Общее"

    # --- 9. Игровые консоли и VR ---
    if re.search(r"playstation|ps4|ps5|xbox|switch|steam deck|джойстик|игровая консоль|игровая приставка|oculus|quest|vr|vr headset|vr шлем|meta quest", desc_low):
        return "Игровые консоли", "Общее"

    # --- 10. Экшен-камеры ---
    if re.search(r"gopro|osmo action|insta360|insta 360|dji|hero", desc_low):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Экшен-камеры", brand
        return "Экшен-камеры", "Общее"

    # --- 11. Фен-стайлеры ---
    if re.search(r"фен|стайлер|hair dryer|styler|airwrap|supersonic|hd08|hd-08|hd16|hd-16|hs08|hs-08|ht01|ht-01", desc_low):
        return "Фен-стайлер", "Общее"

    # --- 12. Пылесосы ---
    if re.search(r"пылесос|vacuum|робот-пылесос|dyson|dreame|submarine", desc_low):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Пылесосы", brand
        return "Пылесосы", "Общее"

    # --- 13. Категория по ключевым словам (fallback) ---
    for cat, keywords in CATEGORY_KEYWORDS:
        if any(kw in desc_low for kw in keywords):
            category = cat
            break

    # --- 14. Бренд по ключевым словам (fallback) ---
    first_word = desc.split()[0].strip(',.;:"()').lower() if desc else ""
    if first_word and first_word in BRAND_KEYWORDS:
        subcategory = BRAND_KEYWORDS[first_word]
    else:
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                subcategory = brand
                break

    # --- 15. Особое правило: для категории Go Pro всегда бренд GoPro ---
    if category == "Go Pro":
        subcategory = "GoPro"

    return category, subcategory


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """При получении документа проверяем, что это .xlsx, скачиваем и обрабатываем."""
    user_id = update.effective_user.id if update.effective_user else None
    awaiting_file = context.user_data.get("awaiting_file")

    # Принимаем файл только от администратора и только после команды /add
    if user_id not in ADMIN_USER_IDS or not awaiting_file:
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

    # Сохраняем копию файла, чтобы пользователи могли скачивать актуальную версию
    try:
        shutil.copy(src_path, LATEST_EXCEL_FILE)
    except Exception:
        pass

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

    # Отправляем пользователю выбор категорий с количеством товаров
    buttons = []
    for cat in _sort_categories(list(catalog.keys())):
        subdict = catalog[cat]
        count = sum(len(items) for items in subdict.values())
        buttons.append([InlineKeyboardButton(text=f"{cat} ({count})", callback_data=f"cat|{cat}")])
    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Каталог загружен! Выберите категорию:", reply_markup=markup)

    # Удаляем временный файл
    try:
        os.remove(src_path)
        os.rmdir(tmp_dir)
    except OSError:
        pass


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка текстовых сообщений и нажатий на кнопки меню."""

    chat_id = update.effective_chat.id
    text = update.message.text
    # Удаляем все старые сообщения пользователя перед новым действием
    await delete_all_user_messages(context, chat_id)
    # Удаляем последнее сообщение пользователя (если оно не команда)
    if update.message and not update.message.text.startswith("/"):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
        except Exception:
            pass

    # --- 1. Обработка режима поиска ---
    if context.user_data.get("awaiting_search"):
        context.user_data["awaiting_search"] = False
        query = (text or "").strip()
        if not query:
            m = await context.bot.send_message(chat_id=chat_id, text="Пустой запрос. Попробуйте ещё раз.", reply_markup=MAIN_MENU_MARKUP)
            context.user_data["all_msg_ids"] = [m.message_id]
            return
        catalog: dict | None = context.application.bot_data.get("catalog")
        if not catalog:
            m = await context.bot.send_message(chat_id=chat_id, text="Каталог пока не загружен. Пожалуйста, попробуйте позже.", reply_markup=MAIN_MENU_MARKUP)
            context.user_data["all_msg_ids"] = [m.message_id]
            return
        query_low = query.lower()
        results: list[tuple[str, str, dict]] = []
        for cat, subdict in catalog.items():
            for sub, items in subdict.items():
                for item in items:
                    if query_low in str(item["desc"]).lower():
                        results.append((cat, sub, item))
        if not results:
            m = await context.bot.send_message(chat_id=chat_id, text="Ничего не найдено по вашему запросу.", reply_markup=MAIN_MENU_MARKUP)
            context.user_data["all_msg_ids"] = [m.message_id]
            return
        lines: list[str] = []
        for cat, sub, item in results:
            desc = html.escape(str(item["desc"]))
            price = str(item["price"]).strip()
            line = f"<b>{desc}</b>"
            if price:
                line += f" — <i>{html.escape(price)} ₽</i>"
            line += f"\n<i>{cat} / {sub}</i>"
            lines.append(line)
        MAX_LENGTH = 4000
        chunks: list[str] = []
        current: list[str] = []
        cur_len = 0
        for line in lines:
            ln = len(line) + 1
            if cur_len + ln > MAX_LENGTH and current:
                chunks.append("\n\n".join(current))
                current = [line]
                cur_len = ln
            else:
                current.append(line)
                cur_len += ln
        if current:
            chunks.append("\n\n".join(current))
        msg_ids = []
        m = await context.bot.send_message(chat_id=chat_id, text=f"Найдено позиций: {len(results)}", reply_markup=MAIN_MENU_MARKUP)
        msg_ids.append(m.message_id)
        back_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text="← Назад", callback_data="back|root")]])
        for idx, chunk in enumerate(chunks):
            if idx == len(chunks) - 1:
                msg = await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="HTML" if chunk else None, reply_markup=back_markup)
            else:
                msg = await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="HTML" if chunk else None)
            msg_ids.append(msg.message_id)
        context.user_data["all_msg_ids"] = msg_ids
        return

    # --- 2. Обработка нажатий на основные кнопки ---
    if text == BTN_SEARCH_CATALOG:
        context.user_data["awaiting_search"] = True
        m = await context.bot.send_message(chat_id=chat_id, text="Введите поисковый запрос по каталогу:", reply_markup=MAIN_MENU_MARKUP)
        context.user_data["all_msg_ids"] = [m.message_id]
        return
    if text == BTN_CHOOSE_CATEGORY:
        catalog: dict | None = context.application.bot_data.get("catalog")
        if catalog:
            buttons = []
            for cat_name in _sort_categories(list(catalog.keys())):
                subdict = catalog[cat_name]
                count = sum(len(items) for items in subdict.values())
                buttons.append([InlineKeyboardButton(text=f"{cat_name} ({count})", callback_data=f"cat|{cat_name}")])
            markup = InlineKeyboardMarkup(buttons)
            m = await context.bot.send_message(chat_id=chat_id, text="Выберите категорию:", reply_markup=markup)
            context.user_data["all_msg_ids"] = [m.message_id]
        else:
            m = await context.bot.send_message(chat_id=chat_id, text="Каталог пока не загружен. Пожалуйста, попробуйте позже.", reply_markup=MAIN_MENU_MARKUP)
            context.user_data["all_msg_ids"] = [m.message_id]
    elif text == BTN_CONTACT_MANAGER:
        link_btn_tg = InlineKeyboardButton("Написать менеджеру в Телеграм", url=MANAGER_TELEGRAM_LINK)
        link_btn_wa = InlineKeyboardButton("Написать менеджеру в WhatsApp", url=MANAGER_WHATSAPP_LINK)
        m = await context.bot.send_message(
            chat_id=chat_id,
            text="Выберите удобный способ связи с нашим менеджером:",
            reply_markup=MAIN_MENU_MARKUP
        )
        # Отправим также инлайн-кнопки отдельным сообщением, чтобы не терять функционал
        m2 = await context.bot.send_message(
            chat_id=chat_id,
            text="Быстрые ссылки:",
            reply_markup=InlineKeyboardMarkup([[link_btn_tg], [link_btn_wa]])
        )
        context.user_data["all_msg_ids"] = [m.message_id, m2.message_id]
    elif text == BTN_GET_EXCEL:
        if os.path.exists(LATEST_EXCEL_FILE):
            try:
                m = await context.bot.send_document(chat_id=chat_id, document=open(LATEST_EXCEL_FILE, "rb"), filename="catalog.xlsx", reply_markup=MAIN_MENU_MARKUP)
                context.user_data["all_msg_ids"] = [m.message_id]
            except Exception as exc:
                m = await context.bot.send_message(chat_id=chat_id, text=f"Не удалось отправить файл: {exc}", reply_markup=MAIN_MENU_MARKUP)
                context.user_data["all_msg_ids"] = [m.message_id]
        else:
            m = await context.bot.send_message(chat_id=chat_id, text="Файл каталога пока не загружен.", reply_markup=MAIN_MENU_MARKUP)
            context.user_data["all_msg_ids"] = [m.message_id]

    elif text == BTN_SUBSCRIBE:
        subs: set[int] = context.application.bot_data.setdefault("subscribers", set())
        user_id = update.effective_user.id if update.effective_user else None
        if user_id:
            subs.add(user_id)
            m = await context.bot.send_message(chat_id=chat_id, text="Спасибо! Вы подписаны на обновления.", reply_markup=MAIN_MENU_MARKUP)
            context.user_data["all_msg_ids"] = [m.message_id]
        else:
            m = await context.bot.send_message(chat_id=chat_id, text="Не удалось выполнить подписку.", reply_markup=MAIN_MENU_MARKUP)
            context.user_data["all_msg_ids"] = [m.message_id]

    # --- 3. Обработка неизвестных сообщений ---
    else:
        m = await context.bot.send_message(chat_id=chat_id, text="Извините, я вас не понял. Пожалуйста, выберите действие из меню ниже.", reply_markup=MAIN_MENU_MARKUP)
        context.user_data["all_msg_ids"] = [m.message_id]


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    # Удаляем все старые сообщения пользователя перед новым действием
    await delete_all_user_messages(context, chat_id)
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
        buttons = []
        for sub_name, items in subcats.items():
            buttons.append([InlineKeyboardButton(text=f"{sub_name} ({len(items)})", callback_data=f"sub|{cat}|{sub_name}")])
        buttons.append([InlineKeyboardButton(text="← Назад", callback_data="back|root")])
        markup = InlineKeyboardMarkup(buttons)
        m = await context.bot.send_message(chat_id=chat_id, text=f"Категория: {cat}\nВыберите подкатегорию:", reply_markup=markup)
        context.user_data["all_msg_ids"] = [m.message_id]

    elif parts[0] == "sub":  # Выбрана подкатегория
        cat, sub = parts[1], parts[2]
        items = catalog.get(cat, {}).get(sub, [])
        text_lines: list[str] = []
        for item in items:
            desc = html.escape(str(item['desc']))
            price = str(item['price']).strip()
            line = f"<b>{desc}</b>"
            if price:
                line += f" — <i>{html.escape(price)} ₽</i>"
            text_lines.append(line)

        MAX_LENGTH = 4000
        chunks: list[str] = []
        current_lines: list[str] = []
        current_len = 0
        for line in text_lines:
            line_len = len(line) + 1
            if current_len + line_len > MAX_LENGTH and current_lines:
                chunks.append("\n".join(current_lines))
                current_lines = [line]
                current_len = line_len
            else:
                current_lines.append(line)
                current_len += line_len
        if current_lines:
            chunks.append("\n".join(current_lines))

        if not chunks:
            chunks = ["Нет товаров."]

        buttons = [[InlineKeyboardButton(text="← Назад", callback_data=f"cat|{cat}")]]
        markup = InlineKeyboardMarkup(buttons)

        msg_ids = []
        if len(chunks) == 1:
            text_to_send = f"Категория: {cat} / {sub}\n\n{chunks[0]}"
            m = await context.bot.send_message(chat_id=chat_id, text=text_to_send, reply_markup=markup, parse_mode="HTML")
            msg_ids.append(m.message_id)
        else:
            first_text = f"Категория: {cat} / {sub}\n\n{chunks[0]}"
            m = await context.bot.send_message(chat_id=chat_id, text=first_text, reply_markup=None, parse_mode="HTML")
            msg_ids.append(m.message_id)
            for chunk in chunks[1:-1]:
                mm = await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="HTML")
                msg_ids.append(mm.message_id)
            mm = await context.bot.send_message(chat_id=chat_id, text=chunks[-1], reply_markup=markup, parse_mode="HTML")
            msg_ids.append(mm.message_id)
        context.user_data["all_msg_ids"] = msg_ids
        return

    elif parts[0] == "back":
        # Просто показываем главное меню (все старые сообщения уже удалены)
        m = await context.bot.send_message(chat_id=chat_id, text="Выберите действие:", reply_markup=MAIN_MENU_MARKUP)
        context.user_data["all_msg_ids"] = [m.message_id]
        return


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
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND) & (~filters.Document.ALL), handle_text))
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    # Запускаем бесконечный поллинг
    print("Бот запущен. Нажмите Ctrl-C для остановки.")
    app.run_polling()


if __name__ == "__main__":
    main() 