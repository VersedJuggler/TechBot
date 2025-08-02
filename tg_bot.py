# tg_bot.py
import os
import asyncio
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
# Файл для хранения списка администраторов
ADMINS_FILE = "admins.json"

def _load_admins() -> set[int]:
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(map(int, data.get("admins", [])))
        except Exception:
            pass
    # Если файла нет, возвращаем дефолтный набор (старые id)
    return {6413686861, 728567535, 510202114, 7548453140}

def _save_admins(admins: set[int]) -> None:
    try:
        with open(ADMINS_FILE, "w", encoding="utf-8") as f:
            json.dump({"admins": list(admins)}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def is_admin(user_id: int) -> bool:
    return user_id in _load_admins()


# Основные файлы для хранения
CATALOG_FILE = "catalog_data.json"
LATEST_EXCEL_FILE = "latest_catalog.xlsx"
MANUAL_CATEGORIES_FILE = "manual_categories.json"
def _load_manual_categories() -> dict:
    if os.path.exists(MANUAL_CATEGORIES_FILE):
        try:
            with open(MANUAL_CATEGORIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_manual_categories(manual_cats: dict) -> None:
    try:
        with open(MANUAL_CATEGORIES_FILE, "w", encoding="utf-8") as f:
            json.dump(manual_cats, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

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

def get_full_catalog(context) -> dict:
    """Объединяет основной каталог и manual_categories для вывода и поиска."""
    catalog = context.application.bot_data.get("catalog") or {}
    manual = context.application.bot_data.get("manual_categories") or {}
    # Глубокое копирование, чтобы не портить оригиналы
    import copy
    full = copy.deepcopy(catalog)
    for cat, brands in manual.items():
        for brand, items in brands.items():
            full.setdefault(cat, {}).setdefault(brand, []).extend(items)
    return full


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
    # Используем объединённый каталог
    full_catalog = get_full_catalog(context)
    if full_catalog:
        buttons = []
        for cat_name in _sort_categories(list(full_catalog.keys())):
            subdict = full_catalog[cat_name]
            count = sum(len(items) for items in subdict.values())
            buttons.append([InlineKeyboardButton(text=f"{cat_name} ({count})", callback_data=f"cat|{cat_name}")])
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
    "digma linx": "Digma Linx",
    "blackview": "Blackview",
    "doogee": "DOOGEE",
    "hotwav": "Hotwav",
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



# --- Новая команда: /add_catalog ---
async def add_catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /add_catalog — загрузить новый Excel-файл с каталогом (только админ)."""
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_admin(user_id):
        await update.message.reply_text("Извините, команда доступна только администратору.")
        return
    context.user_data["awaiting_file"] = True
    await update.message.reply_text("Отправьте Excel-файл (.xlsx) с обновлённой базой товаров.")



# --- Новая команда: /edit_category ---
async def edit_category_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /edit_category — управление вручную добавленными категориями (только админ)."""
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_admin(user_id):
        await update.message.reply_text("Извините, команда доступна только администратору.")
        return
    # Загружаем вручную добавленные категории
    manual_cats = context.application.bot_data.get("manual_categories")
    if manual_cats is None:
        manual_cats = _load_manual_categories()
        context.application.bot_data["manual_categories"] = manual_cats
    if not manual_cats:
        msg = "Вручную добавленных категорий нет."
    else:
        lines = []
        for cat, brands in manual_cats.items():
            for brand, items in brands.items():
                lines.append(f"<b>{cat}</b> / <i>{brand}</i>: {len(items)} позиций")
        msg = "Вручную добавленные категории:\n" + "\n".join(lines)
    buttons = [
        [InlineKeyboardButton("Добавить", callback_data="manualcat_add")],
        [InlineKeyboardButton("Удалить", callback_data="manualcat_remove")],
    ]
    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(msg, reply_markup=markup, parse_mode="HTML")
    return

# --- Новая команда: /edit_admins ---
async def edit_admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /edit_admins — управление списком администраторов (только админ)."""
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_admin(user_id):
        await update.message.reply_text("Извините, команда доступна только администратору.")
        return
    # Показываем список админов и две кнопки: Добавить, Удалить
    admins = _load_admins()
    admin_lines = []
    for admin_id in admins:
        try:
            user = await context.bot.get_chat(admin_id)
            username = f"@{user.username}" if getattr(user, "username", None) else ""
        except Exception:
            username = ""
        admin_lines.append(f"{admin_id} {username}")
    msg = (
        "Текущие администраторы:\n"
        + "\n".join(admin_lines)
    )
    buttons = [
        [InlineKeyboardButton("Добавить", callback_data="admin_add")],
        [InlineKeyboardButton("Удалить", callback_data="admin_remove")],
    ]
    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(msg, reply_markup=markup)
    return


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help — выводит информацию о связи с менеджером."""
    help_text = (
        "📦 Как оформить заказ:\n\n"
        "Нажмите «💬 Заказать товар у менеджера»\n\n"
        "В сообщении укажите точную модель товара, который вас интересует (например:  (скопировать один вариант из ассортимента типа MacBook Pro 16 M4, 24/512, Black)\n\n"
        "Мы подтвердим наличие и зарезервируем товар за вами\n\n"
        "🚚 Доставка по Москве:\n\n"
        "В пределах МКАД — от 1 000 ₽\n"
        "За МКАД (до 30 км) — по договорённости\n\n"
        "🛍 Самовывоз — бесплатно:\n\n"
        "Заказы, оформленные до 13:00, можно получить в тот же день\n"
        "После 13:00 — на следующий день\n\n"
        "🕒 Выдача заказов:\n"
        "⏰ Ежедневно с 15:00 до 16:00\n"
        "📍 Адрес: ТЦ Рубин, Багратионовский проезд, 7к2\n"
        "(5 минут пешком от метро Багратионовская)"
    )
    back_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text="← Назад", callback_data="back|root")]])
    await update.message.reply_text(help_text, reply_markup=back_markup)


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


    # --- 4. Фен-стайлеры (Dyson, Supersonic, Airwrap и др.) ---
    if re.search(r"фен|стайлер|hair dryer|styler|airwrap|supersonic|hd08|hd-08|hd16|hd-16|hs08|hs-08|ht01|ht-01", desc_low):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Фен-стайлер", brand
        return "Фен-стайлер", "Общее"

    # --- 5. Пылесосы (все бренды, любые слова) ---
    # Паттерн: пылесос, vacuum, cleaner, робот-пылесос, robot vacuum, robot cleaner, робот vacuum, робот cleaner, dreame, dyson, submarine
    if re.search(r"пылесос|vacuum|cleaner|робот-пылесос|robot vacuum|robot cleaner|робот vacuum|робот cleaner|dreame|dyson|submarine", desc_low):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Пылесосы", brand
        return "Пылесосы", "Общее"

    # --- 5. Часы и браслеты (Garmin, Band, Instinct и др.) ---
    if re.search(r"\b(часы|watch|band|fitbit|amazfit|gtr|gt3|instinct|forerunner|fenix|coros|garmin|band)\b", desc_low):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Часы", brand
        return "Часы", "Общее"

    # --- 6. Планшеты (Pad, Tab, Tablet, кроме Notepad) ---
    if (re.search(r"\bipad\b|\btab\b|\btablet\b|\bpad\b", desc_low) or re.search(r"pad[\s\d]", desc_low)) and not re.search(r"notepad", desc_low):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Планшеты", brand
        return "Планшеты", "Общее"

    # --- 7. Ноутбуки (Apple, Matebook, CPU, дюймы, модели, book, клавиатура) ---
    # Явные признаки ноутбука: 'book' + дюймы, или 'клавиатура' (RU клавиатура и др.)
    if (re.search(r"book", desc_low) and re.search(r"\d{2}\"", desc)) or re.search(r"клавиатура", desc_low):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Ноутбуки", brand
        return "Ноутбуки", "Общее"
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


    # --- 8. Кнопочные телефоны ---
    if re.search(r"button phone|feature phone|nokia|f\+|digma linx", desc_low):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Телефоны кнопочные", brand
        return "Телефоны кнопочные", "Общее"

    # --- 9. Противоударные телефоны ---
    if re.search(r"противоударный|rugged|armor|tank|cyber|mega|blackview|doogee|hotwav|oukitel|unihertz", desc_low):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Телефоны противоударные", brand
        return "Телефоны противоударные", "Общее"

    # --- 9. Игровые консоли и VR ---
    if re.search(r"playstation|ps4|ps5|xbox|switch|steam deck|джойстик|игровая консоль|игровая приставка|oculus|quest|vr|vr headset|vr шлем|meta quest", desc_low):
        for kw, brand in BRAND_KEYWORDS.items():
            if kw in desc_low:
                return "Игровые консоли", brand
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
    if not user_id or not is_admin(user_id) or not awaiting_file:
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

    # После успешной загрузки каталога выводим сообщение с инструкцией
    await update.message.reply_text("Каталог успешно добавлен, нажмите /start, чтобы ознакомиться с категориями")

    # Удаляем временный файл
    try:
        os.remove(src_path)
        os.rmdir(tmp_dir)
    except OSError:
        pass


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка текстовых сообщений и нажатий на кнопки меню."""
    text = update.message.text

    # --- 0.1. Пошаговое добавление вручную категории/бренда/товаров ---
    if context.user_data.get("manualcat_step"):
        step = context.user_data["manualcat_step"]
        user_id = update.effective_user.id if update.effective_user else None
        if not user_id or not is_admin(user_id):
            await update.message.reply_text("Нет прав для добавления.")
            context.user_data.pop("manualcat_step", None)
            return
        if step == 1:
            # Получили название категории
            cat = text.strip()
            if not cat:
                await update.message.reply_text("Название категории не может быть пустым. Введите ещё раз:")
                return
            context.user_data["manualcat_category"] = cat
            context.user_data["manualcat_step"] = 2
            await update.message.reply_text("Введите название бренда (подкатегории):")
            return
        elif step == 2:
            # Получили название бренда
            brand = text.strip()
            if not brand:
                await update.message.reply_text("Название бренда не может быть пустым. Введите ещё раз:")
                return
            context.user_data["manualcat_brand"] = brand
            context.user_data["manualcat_step"] = 3
            await update.message.reply_text(
                "Введите описание товара и цену.\nКаждая строка: Описание;Цена\n"
            )
            context.user_data["manualcat_items"] = []
            return
        elif step == 3:
            # Получаем товары (многострочно, до 'Готово')
            if text.strip().lower() == "готово":
                await update.message.reply_text("Пожалуйста, отправьте список товаров (каждая строка: Описание;Цена). Если хотите отменить — используйте /start.")
                return
            # Ожидаем список товаров, каждая строка: Описание;Цена
            lines = [line for line in text.splitlines() if line.strip()]
            items = []
            for line in lines:
                parts = line.split(";")
                if len(parts) < 2:
                    continue  # пропускаем некорректные строки
                desc = parts[0].strip()
                price = parts[1].strip()
                if not desc or not price:
                    continue
                items.append({"desc": desc, "price": price})
            if items:
                cat = context.user_data.pop("manualcat_category")
                brand = context.user_data.pop("manualcat_brand")
                context.user_data.pop("manualcat_step", None)
                # Сохраняем в manual_categories.json
                manual_cats = context.application.bot_data.get("manual_categories")
                if manual_cats is None:
                    manual_cats = _load_manual_categories()
                manual_cats.setdefault(cat, {}).setdefault(brand, []).extend(items)
                context.application.bot_data["manual_categories"] = manual_cats
                _save_manual_categories(manual_cats)
                # Показываем обновлённый список вручную добавленных категорий
                lines = []
                for c, brands in manual_cats.items():
                    for b, its in brands.items():
                        lines.append(f"<b>{c}</b> / <i>{b}</i>: {len(its)} позиций")
                msg = "Вручную добавленные категории:\n" + "\n".join(lines)
                buttons = [
                    [InlineKeyboardButton("Добавить", callback_data="manualcat_add")],
                    [InlineKeyboardButton("Удалить", callback_data="manualcat_remove")],
                ]
                markup = InlineKeyboardMarkup(buttons)
                await update.message.reply_text(f"Добавлено в {cat} / {brand}: {len(items)} позиций.\n\n{msg}", reply_markup=markup, parse_mode="HTML")
            else:
                await update.message.reply_text(
                    "Не удалось добавить ни одного товара. Проверьте формат: Описание;Цена."
                )
            return
    # ...existing code...

    # --- 0.1. Ожидание ввода user_id для добавления/удаления админа ---
    if context.user_data.get("awaiting_admin_action"):
        action = context.user_data.pop("awaiting_admin_action")
        user_id = update.effective_user.id if update.effective_user else None
        if not user_id or not is_admin(user_id):
            await update.message.reply_text("Нет прав для изменения админов.")
            return
        try:
            target_id = int(text.strip())
        except Exception:
            await update.message.reply_text("user_id должен быть числом.")
            return
        admins = _load_admins()
        if action == "add":
            admins.add(target_id)
            _save_admins(admins)
            await update.message.reply_text(f"Пользователь {target_id} добавлен в администраторы.")
        elif action == "remove":
            if target_id in admins:
                admins.remove(target_id)
                _save_admins(admins)
                await update.message.reply_text(f"Пользователь {target_id} удалён из администраторов.")
            else:
                await update.message.reply_text("Такого пользователя нет в списке админов.")
        return

    # --- 1. Обработка режима поиска ---
    if context.user_data.get("awaiting_search"):
        # Снимаем флаг ожидания запроса
        context.user_data["awaiting_search"] = False

        query = (text or "").strip()
        if not query:
            await update.message.reply_text("Пустой запрос. Попробуйте ещё раз.")
            return

        full_catalog = get_full_catalog(context)
        if not full_catalog:
            await update.message.reply_text("Каталог пока не загружен. Пожалуйста, попробуйте позже.")
            return

        query_low = query.lower()
        results: list[tuple[str, str, dict]] = []  # (cat, sub, item)
        for cat, subdict in full_catalog.items():
            for sub, items in subdict.items():
                for item in items:
                    if query_low in str(item["desc"]).lower():
                        results.append((cat, sub, item))

        if not results:
            await update.message.reply_text("Ничего не найдено по вашему запросу.")
            return

        # Формируем текст ответа

        lines: list[str] = []
        for cat, sub, item in results:
            desc = html.escape(str(item["desc"]))
            price = str(item["price"]).strip()
            line = f"<b>{desc}</b>"
            if price:
                line += f" — <i>{html.escape(price)} ₽</i>"
            line += f"\n<i>{cat} / {sub}</i>"
            lines.append(line)
        # Добавляем пустую строку между товарами для читаемости
        lines_with_spacing = []
        for l in lines:
            lines_with_spacing.append(l)
            lines_with_spacing.append("")

        # Разбиваем длинные ответы (лимит 4096 символов)
        MAX_LENGTH = 4000
        chunks: list[str] = []
        current: list[str] = []
        cur_len = 0
        for line in lines_with_spacing:
            ln = len(line) + 1
            if cur_len + ln > MAX_LENGTH and current:
                chunks.append("\n".join(current))
                current = [line]
                cur_len = ln
            else:
                current.append(line)
                cur_len += ln
        if current:
            chunks.append("\n".join(current))

        # Показываем количество найденных позиций
        await update.message.reply_text(f"Найдено позиций: {len(results)}")

        # Кнопка "Назад" для поиска
        back_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text="← Назад", callback_data="back|root")]])

        # Сохраняем id сообщений поиска для последующего удаления (если потребуется)
        search_msg_ids = []
        for idx, chunk in enumerate(chunks):
            if idx == len(chunks) - 1:
                msg = await update.message.reply_text(chunk, parse_mode="HTML" if chunk else None, reply_markup=back_markup)
            else:
                msg = await update.message.reply_text(chunk, parse_mode="HTML" if chunk else None)
            search_msg_ids.append(msg.message_id)
        context.user_data["last_search_msg_ids"] = search_msg_ids
        return

    # --- 2. Обработка нажатий на основные кнопки ---
    if text == BTN_SEARCH_CATALOG:
        # Запрашиваем поисковый запрос
        context.user_data["awaiting_search"] = True
        await update.message.reply_text("Введите поисковый запрос по каталогу:")
        return
    if text == BTN_CHOOSE_CATEGORY:
        full_catalog = get_full_catalog(context)
        if full_catalog:
            buttons = []
            for cat_name in _sort_categories(list(full_catalog.keys())):
                subdict = full_catalog[cat_name]
                count = sum(len(items) for items in subdict.values())
                buttons.append([InlineKeyboardButton(text=f"{cat_name} ({count})", callback_data=f"cat|{cat_name}")])
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
    elif text == BTN_GET_EXCEL:
        # Формируем объединённый Excel-файл на лету
        import pandas as pd
        full_catalog = get_full_catalog(context)
        rows = []
        for cat, subdict in full_catalog.items():
            for sub, items in subdict.items():
                for item in items:
                    rows.append({
                        "Категория": cat,
                        "Бренд": sub,
                        "Описание": item.get("desc", ""),
                        "Цена": item.get("price", "")
                    })
        if not rows:
            await update.message.reply_text("Каталог пуст.")
            return
        df = pd.DataFrame(rows)
        # Сохраняем во временный файл
        import tempfile
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        df.to_excel(tmp.name, index=False)
        tmp.close()
        try:
            await update.message.reply_document(document=open(tmp.name, "rb"), filename="catalog.xlsx")
        except Exception as exc:
            await update.message.reply_text(f"Не удалось отправить файл: {exc}")
        finally:
            os.remove(tmp.name)

    elif text == BTN_SUBSCRIBE:
        subs: set[int] = context.application.bot_data.setdefault("subscribers", set())
        user_id = update.effective_user.id if update.effective_user else None
        if user_id:
            subs.add(user_id)
            await update.message.reply_text("Спасибо! Вы подписаны на обновления.")
        else:
            await update.message.reply_text("Не удалось выполнить подписку.")

    # --- 3. Обработка неизвестных сообщений ---
    else:
        # Если сообщение не распознано, отвечаем пользователю и показываем меню
        await update.message.reply_text(
            "Извините, я вас не понял. Пожалуйста, выберите действие из меню ниже.",
            reply_markup=MAIN_MENU_MARKUP,
        )



async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""
    # --- Обработка кнопок для управления вручную добавленными категориями ---
    if data == "manualcat_add":
        context.user_data["manualcat_step"] = 1
        await query.edit_message_text("Введите название категории:")
        return
    if data == "manualcat_remove":
        # Показываем список для удаления, используем mapping для точного соответствия
        import urllib.parse
        manual_cats = context.application.bot_data.get("manual_categories")
        if manual_cats is None:
            manual_cats = _load_manual_categories()
            context.application.bot_data["manual_categories"] = manual_cats
        buttons = []
        cb_map = {}  # callback_data -> (cat, brand)
        idx = 0
        for cat, brands in manual_cats.items():
            for brand in brands:
                cb_data = f"manualcat_del|{idx}"
                cb_map[cb_data] = (cat, brand)
                btn_text = f"{cat} / {brand}"
                buttons.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])
                idx += 1
        if not buttons:
            await query.edit_message_text("Нет вручную добавленных категорий для удаления.")
            return
        # Сохраняем mapping в user_data
        context.user_data["manualcat_del_map"] = cb_map
        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text("Выберите категорию/бренд для удаления:", reply_markup=markup)
        return
    if data.startswith("manualcat_del|"):
        cb_map = context.user_data.get("manualcat_del_map", {})
        # Получаем cat, brand по callback_data
        if data in cb_map:
            cat, brand = cb_map[data]
            manual_cats = context.application.bot_data.get("manual_categories")
            if manual_cats is None:
                manual_cats = _load_manual_categories()
            if cat in manual_cats and brand in manual_cats[cat]:
                del manual_cats[cat][brand]
                if not manual_cats[cat]:
                    del manual_cats[cat]
                context.application.bot_data["manual_categories"] = manual_cats
                _save_manual_categories(manual_cats)
                await query.edit_message_text(f"Удалено: {cat} / {brand}")
            else:
                await query.edit_message_text("Категория/бренд не найдены.")
        else:
            await query.edit_message_text("Категория/бренд не найдены.")
        # Очищаем mapping после использования
        context.user_data.pop("manualcat_del_map", None)
        return
    # --- Обработка кнопок для управления админами ---
    if data == "admin_add":
        context.user_data["awaiting_admin_action"] = "add"
        await query.edit_message_text("Введите user_id пользователя, которого нужно добавить в администраторы:")
        return
    if data == "admin_remove":
        # Показываем список админов с кнопками для удаления
        admins = _load_admins()
        buttons = []
        for admin_id in admins:
            try:
                user = await context.bot.get_chat(admin_id)
                username = f"@{user.username}" if getattr(user, "username", None) else ""
            except Exception:
                username = ""
            btn_text = f"{admin_id} {username}".strip()
            buttons.append([InlineKeyboardButton(btn_text, callback_data=f"admin_del|{admin_id}")])
        if not buttons:
            await query.edit_message_text("Нет администраторов для удаления.")
            return
        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text("Выберите администратора для удаления:", reply_markup=markup)
        return
    if data.startswith("admin_del|"):
        # Удаляем выбранного админа
        parts = data.split("|", 1)
        if len(parts) == 2:
            try:
                target_id = int(parts[1])
            except Exception:
                await query.edit_message_text("Некорректный user_id.")
                return
            admins = _load_admins()
            if target_id in admins:
                admins.remove(target_id)
                _save_admins(admins)
                await query.edit_message_text(f"Пользователь {target_id} удалён из администраторов.")
            else:
                await query.edit_message_text("Такого пользователя нет в списке админов.")
        return
    await query.answer()
    parts = data.split("|")
    if not parts:
        return


    full_catalog = get_full_catalog(context)
    if not full_catalog:
        await query.edit_message_text("Каталог не найден. Загрузите файл командой /add.")
        return

    if parts[0] == "cat":  # Выбрана категория
        cat = parts[1]
        # Навигационный стек: пушим текущий уровень
        nav_stack = context.user_data.get("navigation_stack", [])
        # Если пришли не из back, пушим
        if not nav_stack or nav_stack[-1] != ("cat", cat):
            nav_stack.append(("cat", cat))
        context.user_data["navigation_stack"] = nav_stack
        subcats = full_catalog.get(cat, {})
        # Кнопки подкатегорий с количеством товаров
        buttons = []
        for sub_name, items in subcats.items():
            buttons.append([InlineKeyboardButton(text=f"{sub_name} ({len(items)})", callback_data=f"sub|{cat}|{sub_name}")])
        # Кнопка назад: если стек не пуст, возвращаемся к предыдущему уровню
        if len(nav_stack) > 1:
            buttons.append([InlineKeyboardButton(text="← Назад", callback_data="back")])
        else:
            buttons.append([InlineKeyboardButton(text="← Назад", callback_data="back|root")])
        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(f"Категория: {cat}\nВыберите подкатегорию:", reply_markup=markup)
        return

    elif parts[0] == "sub":  # Выбрана подкатегория
        cat, sub = parts[1], parts[2]
        # Навигационный стек: пушим текущий уровень
        nav_stack = context.user_data.get("navigation_stack", [])
        if not nav_stack or nav_stack[-1] != ("sub", cat, sub):
            nav_stack.append(("sub", cat, sub))
        context.user_data["navigation_stack"] = nav_stack
        items = full_catalog.get(cat, {}).get(sub, [])

        text_lines: list[str] = []
        for item in items:
            desc = html.escape(str(item['desc']))
            price = str(item['price']).strip()
            line = f"<b>{desc}</b>"
            if price:
                line += f" — <i>{html.escape(price)} ₽</i>"
            text_lines.append(line)
        # Добавляем пустую строку между товарами для читаемости
        lines_with_spacing = []
        for l in text_lines:
            lines_with_spacing.append(l)
            lines_with_spacing.append("")

        MAX_LENGTH = 4000
        chunks: list[str] = []
        current_lines: list[str] = []
        current_len = 0
        for line in lines_with_spacing:
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

        # Кнопка назад: если стек не пуст, возвращаемся к предыдущему уровню
        nav_stack = context.user_data.get("navigation_stack", [])
        if len(nav_stack) > 1:
            buttons = [[InlineKeyboardButton(text="← Назад", callback_data="back")]]
        else:
            buttons = [[InlineKeyboardButton(text="← Назад", callback_data="back|root")]]
        markup = InlineKeyboardMarkup(buttons)

        # Всегда edit_message_text, без удаления сообщений
        text_to_send = f"Категория: {cat} / {sub}\n\n{chunks[0]}"
        await query.edit_message_text(text_to_send, reply_markup=markup, parse_mode="HTML")
        return

    elif parts[0] == "back":
        # Навигационный стек: pop текущий уровень
        nav_stack = context.user_data.get("navigation_stack", [])
        if nav_stack:
            nav_stack.pop()
        context.user_data["navigation_stack"] = nav_stack

        # Если стек пуст или явно back|root — показываем корень каталога

        if (len(parts) > 1 and parts[1] == "root") or not nav_stack:
            buttons = []
            for cat_name in _sort_categories(list(full_catalog.keys())):
                subdict = full_catalog[cat_name]
                count = sum(len(items) for items in subdict.values())
                buttons.append([InlineKeyboardButton(text=f"{cat_name} ({count})", callback_data=f"cat|{cat_name}")])
            markup = InlineKeyboardMarkup(buttons)
            try:
                await query.edit_message_text("Выберите категорию:", reply_markup=markup)
            except Exception as e:
                from telegram.error import BadRequest
                if isinstance(e, BadRequest):
                    await context.bot.send_message(chat_id=update.effective_chat.id, text="Выберите категорию:", reply_markup=markup)
                else:
                    raise
            return

        # Иначе — показываем предыдущий уровень
        prev = nav_stack[-1] if nav_stack else None
        if prev:
            if prev[0] == "cat":
                cat = prev[1]
                subcats = full_catalog.get(cat, {})
                buttons = []
                for sub_name, items in subcats.items():
                    buttons.append([InlineKeyboardButton(text=f"{sub_name} ({len(items)})", callback_data=f"sub|{cat}|{sub_name}")])
                if len(nav_stack) > 1:
                    buttons.append([InlineKeyboardButton(text="← Назад", callback_data="back")])
                else:
                    buttons.append([InlineKeyboardButton(text="← Назад", callback_data="back|root")])
                markup = InlineKeyboardMarkup(buttons)
                await query.edit_message_text(f"Категория: {cat}\nВыберите подкатегорию:", reply_markup=markup)
            elif prev[0] == "sub":
                cat, sub = prev[1], prev[2]
                items = full_catalog.get(cat, {}).get(sub, [])
                text_lines: list[str] = []
                for item in items:
                    desc = html.escape(str(item['desc']))
                    price = str(item['price']).strip()
                    line = f"<b>{desc}</b>"
                    if price:
                        line += f" — <i>{html.escape(price)} ₽</i>"
                    text_lines.append(line)
                # Добавляем пустую строку между товарами для читаемости
                lines_with_spacing = []
                for l in text_lines:
                    lines_with_spacing.append(l)
                    lines_with_spacing.append("")

                MAX_LENGTH = 4000
                chunks: list[str] = []
                current_lines: list[str] = []
                current_len = 0
                for line in lines_with_spacing:
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
                if len(nav_stack) > 1:
                    buttons = [[InlineKeyboardButton(text="← Назад", callback_data="back")]]
                else:
                    buttons = [[InlineKeyboardButton(text="← Назад", callback_data="back|root")]]
                markup = InlineKeyboardMarkup(buttons)
                text_to_send = f"Категория: {cat} / {sub}\n\n{chunks[0]}"
                await query.edit_message_text(text_to_send, reply_markup=markup, parse_mode="HTML")
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

    # Загружаем вручную добавленные категории с диска
    app.bot_data["manual_categories"] = _load_manual_categories()

    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add_catalog", add_catalog_command))
    app.add_handler(CommandHandler("edit_category", edit_category_command))
    app.add_handler(CommandHandler("edit_admins", edit_admins_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND) & (~filters.Document.ALL), handle_text))
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    # Запускаем бесконечный поллинг
    print("Бот запущен. Нажмите Ctrl-C для остановки.")
    app.run_polling()


if __name__ == "__main__":
    main() 