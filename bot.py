import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
ORDERS_DIR = DATA_DIR / "orders"
USERS_FILE = DATA_DIR / "users.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ORDERS_DIR.mkdir(parents=True, exist_ok=True)
if not USERS_FILE.exists():
    USERS_FILE.write_text("{}", encoding="utf-8")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPERATOR_CHAT_ID = (
    os.getenv("OPERATOR_CHAT_ID", "").strip()
    or os.getenv("ADMIN_CHAT_ID", "").strip()
)
TRACKING_BASE_URL = os.getenv("TRACKING_BASE_URL", "https://example.com/track").strip()
MAX_PHOTOS = int(os.getenv("MAX_PHOTOS", "5"))
MAX_DELIVERY_PHOTOS = int(os.getenv("MAX_DELIVERY_PHOTOS", "10"))

CONTACT_PHONE = os.getenv("CONTACT_PHONE", "+358413285659").strip()
CONTACT_WHATSAPP = os.getenv("CONTACT_WHATSAPP", "https://wa.me/358413285659").strip()
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "").strip() or "-"
CONTACT_WEBSITE = os.getenv("CONTACT_WEBSITE", "https://kotitonttu-palvelut.netlify.app/").strip()

PRICE_TEXT_FI = os.getenv("PRICE_TEXT_FI", "").strip()
PRICE_TEXT_EN = os.getenv("PRICE_TEXT_EN", "").strip()
PRICE_TEXT_RU = os.getenv("PRICE_TEXT_RU", "").strip()

DEFAULT_PRICE_TEXT = {
    "fi": "Toimituksen hinta:\n\n• 0–3 km → 5 €\n• Yli 3 km → +0.78 €/km\n\nLisämaksut:\n• Kiireellinen toimitus +2 €\n• Ilta / viikonloppu +2 €",
    "en": "Delivery price:\n\n• 0–3 km → 5 €\n• Over 3 km → +0.78 €/km\n\nExtras:\n• Urgent delivery +2 €\n• Evening / weekend +2 €",
    "ru": "Стоимость доставки:\n\n• 0–3 км → 5 €\n• Свыше 3 км → +0.78 €/км\n\nДоплаты:\n• Срочная доставка +2 €\n• Вечер / выходные +2 €",
}


class OrderType(str, Enum):
    NOW = "now"
    LATER = "later"


class OrderStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    GOING_TO_PICKUP = "going_to_pickup"
    PICKED_UP = "picked_up"
    GOING_TO_DELIVERY = "going_to_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


STATUS_LABELS = {
    "fi": {
        OrderStatus.PENDING_APPROVAL.value: "Odottaa vahvistusta",
        OrderStatus.APPROVED.value: "Tilaus hyväksytty",
        OrderStatus.GOING_TO_PICKUP.value: "Kuljettaja on matkalla noutopaikkaan",
        OrderStatus.PICKED_UP.value: "Tilaus on noudettu",
        OrderStatus.GOING_TO_DELIVERY.value: "Kuljettaja on matkalla toimitusosoitteeseen",
        OrderStatus.DELIVERED.value: "Toimitettu",
        OrderStatus.CANCELLED.value: "Peruttu",
    },
    "en": {
        OrderStatus.PENDING_APPROVAL.value: "Awaiting confirmation",
        OrderStatus.APPROVED.value: "Order accepted",
        OrderStatus.GOING_TO_PICKUP.value: "Driver is going to the pickup location",
        OrderStatus.PICKED_UP.value: "Order has been picked up",
        OrderStatus.GOING_TO_DELIVERY.value: "Driver is going to the delivery location",
        OrderStatus.DELIVERED.value: "Delivered",
        OrderStatus.CANCELLED.value: "Cancelled",
    },
    "ru": {
        OrderStatus.PENDING_APPROVAL.value: "Ожидает подтверждения",
        OrderStatus.APPROVED.value: "Заказ принят",
        OrderStatus.GOING_TO_PICKUP.value: "Курьер едет к месту забора",
        OrderStatus.PICKED_UP.value: "Заказ забран",
        OrderStatus.GOING_TO_DELIVERY.value: "Курьер едет к месту доставки",
        OrderStatus.DELIVERED.value: "Доставлено",
        OrderStatus.CANCELLED.value: "Отменено",
    },
}

TEXTS: Dict[str, Dict[str, str]] = {
    "fi": {
        "choose_language": "Valitse kieli / Choose language / Выберите язык:",
        "welcome": "Tervetuloa Kotitonttu Toimitus -bottiin. Valitse toiminto alta.",
        "menu_prompt": "Valitse toiminto:",
        "btn_now": "Tilaa heti",
        "btn_later": "Tilaa myöhemmin",
        "btn_prices": "Hinnat",
        "btn_faq": "FAQ",
        "btn_contact": "Yhteystiedot",
        "btn_language": "Kieli",
        "reuse_profile": "Käytetäänkö tallennettuja tietoja?",
        "yes": "Kyllä",
        "edit": "Muuta",
        "ask_name": "Mikä on nimesi?",
        "ask_phone": "Lähetä puhelinnumero yhteystietona tai kirjoita se viestinä.",
        "ask_date": "Anna toimituspäivä muodossa PP.KK.VVVV.",
        "ask_time": "Anna toivottu aika muodossa HH:MM.",
        "ask_pickup": "Kirjoita nouto-osoite.",
        "ask_delivery": "Kirjoita toimitusosoite.",
        "ask_description": "Mitä pitää toimittaa?",
        "ask_photos": "Voit lähettää enintään {max_photos} kuvaa. Kun olet valmis, paina Valmis. Voit myös ohittaa tämän vaiheen.",
        "skip": "Ohita",
        "done": "Valmis",
        "ask_comment": "Lisäohjeet tai kommentit? Jos ei ole, kirjoita -",
        "confirm": "Tarkista tiedot ja vahvista tilaus.",
        "confirm_btn": "Vahvista",
        "cancel_btn": "Peruuta",
        "edit_btn": "Aloita alusta",
        "order_received": "Tilauksesi on vastaanotettu. Tila: {status}",
        "request_received": "Toimituspyyntö vastaanotettu. Vahvistamme sen erikseen.",
        "order_cancelled": "Tilaus on peruttu.",
        "faq": "Voit tilata kiireellisen toimituksen heti tai toimituksen myöhemmäksi. Voit myös lisätä kuvia tilaukseen.",
        "contact": "Puhelin: {phone}\nWhatsApp: {whatsapp}\nSähköposti: {email}\nVerkkosivu: {website}",
        "invalid_date": "Virheellinen päivämäärä. Käytä muotoa PP.KK.VVVV.",
        "invalid_time": "Virheellinen aika. Käytä muotoa HH:MM.",
        "invalid_phone": "Anna puhelinnumero tekstinä tai lähetä yhteystieto.",
        "photo_saved": "Kuva lisätty ({count}/{max_photos}).",
        "photo_limit": "Kuvien enimmäismäärä on {max_photos}.",
        "no_active": "Aktiivista tilausta ei ole.",
        "status_message": "Viimeisin tilaus #{order_id}: {status}",
        "lang_changed": "Kieli vaihdettu.",
        "field_name": "Nimi",
        "field_phone": "Puhelin",
        "field_date": "Päivämäärä",
        "field_time": "Aika",
        "field_pickup": "Nouto-osoite",
        "field_delivery": "Toimitusosoite",
        "field_description": "Kuvaus",
        "field_comment": "Kommentti",
        "field_photos": "Kuvat",
        "type_now": "Kiireellinen toimitus",
        "type_later": "Toimitus myöhemmin",
    },
    "en": {
        "choose_language": "Choose language / Valitse kieli / Выберите язык:",
        "welcome": "Welcome to the Kotitonttu Toimitus bot. Choose an option below.",
        "menu_prompt": "Choose an option:",
        "btn_now": "Order now",
        "btn_later": "Order later",
        "btn_prices": "Prices",
        "btn_faq": "FAQ",
        "btn_contact": "Contact",
        "btn_language": "Language",
        "reuse_profile": "Use your saved details?",
        "yes": "Yes",
        "edit": "Edit",
        "ask_name": "What is your name?",
        "ask_phone": "Send your phone number as a contact or type it as a message.",
        "ask_date": "Enter the delivery date in DD.MM.YYYY format.",
        "ask_time": "Enter the preferred time in HH:MM format.",
        "ask_pickup": "Enter the pickup address.",
        "ask_delivery": "Enter the delivery address.",
        "ask_description": "What needs to be delivered?",
        "ask_photos": "You can send up to {max_photos} photos. When finished, press Done. You can also skip this step.",
        "skip": "Skip",
        "done": "Done",
        "ask_comment": "Any extra instructions or comments? If none, type -",
        "confirm": "Please review the details and confirm your order.",
        "confirm_btn": "Confirm",
        "cancel_btn": "Cancel",
        "edit_btn": "Start over",
        "order_received": "Your order has been received. Status: {status}",
        "request_received": "Your delivery request has been received. We will confirm it separately.",
        "order_cancelled": "The order has been cancelled.",
        "faq": "You can place an urgent order now or schedule a delivery for later. Photos can be attached to your order.",
        "contact": "Phone: {phone}\nWhatsApp: {whatsapp}\nEmail: {email}\nWebsite: {website}",
        "invalid_date": "Invalid date. Use DD.MM.YYYY.",
        "invalid_time": "Invalid time. Use HH:MM.",
        "invalid_phone": "Please send a phone number or share it as a contact.",
        "photo_saved": "Photo added ({count}/{max_photos}).",
        "photo_limit": "Maximum number of photos is {max_photos}.",
        "no_active": "There is no active order.",
        "status_message": "Latest order #{order_id}: {status}",
        "lang_changed": "Language changed.",
        "field_name": "Name",
        "field_phone": "Phone",
        "field_date": "Date",
        "field_time": "Time",
        "field_pickup": "Pickup address",
        "field_delivery": "Delivery address",
        "field_description": "Description",
        "field_comment": "Comment",
        "field_photos": "Photos",
        "type_now": "Urgent delivery",
        "type_later": "Delivery later",
    },
    "ru": {
        "choose_language": "Выберите язык / Choose language / Valitse kieli:",
        "welcome": "Добро пожаловать в бот Kotitonttu Toimitus. Выберите действие ниже.",
        "menu_prompt": "Выберите действие:",
        "btn_now": "Заказать сейчас",
        "btn_later": "Заказать на позже",
        "btn_prices": "Цены",
        "btn_faq": "FAQ",
        "btn_contact": "Контакты",
        "btn_language": "Язык",
        "reuse_profile": "Использовать сохранённые данные?",
        "yes": "Да",
        "edit": "Изменить",
        "ask_name": "Как вас зовут?",
        "ask_phone": "Отправьте номер телефона контактом или напишите его сообщением.",
        "ask_date": "Укажите дату доставки в формате ДД.ММ.ГГГГ.",
        "ask_time": "Укажите желаемое время в формате ЧЧ:ММ.",
        "ask_pickup": "Напишите адрес забора.",
        "ask_delivery": "Напишите адрес доставки.",
        "ask_description": "Что нужно доставить?",
        "ask_photos": "Можно отправить до {max_photos} фото. Когда закончите, нажмите Готово. Можно пропустить этот шаг.",
        "skip": "Пропустить",
        "done": "Готово",
        "ask_comment": "Есть дополнительные инструкции или комментарии? Если нет, напишите -",
        "confirm": "Проверьте данные и подтвердите заказ.",
        "confirm_btn": "Подтвердить",
        "cancel_btn": "Отменить",
        "edit_btn": "Начать заново",
        "order_received": "Ваш заказ получен. Статус: {status}",
        "request_received": "Запрос на доставку получен. Мы подтвердим его отдельно.",
        "order_cancelled": "Заказ отменён.",
        "faq": "Вы можете оформить срочную доставку сразу или доставку на позже. К заказу можно прикрепить фото.",
        "contact": "Телефон: {phone}\nWhatsApp: {whatsapp}\nEmail: {email}\nСайт: {website}",
        "invalid_date": "Неверная дата. Используйте формат ДД.ММ.ГГГГ.",
        "invalid_time": "Неверное время. Используйте формат ЧЧ:ММ.",
        "invalid_phone": "Отправьте номер телефона сообщением или контактом.",
        "photo_saved": "Фото добавлено ({count}/{max_photos}).",
        "photo_limit": "Максимум фото: {max_photos}.",
        "no_active": "Активного заказа нет.",
        "status_message": "Последний заказ #{order_id}: {status}",
        "lang_changed": "Язык изменён.",
        "field_name": "Имя",
        "field_phone": "Телефон",
        "field_date": "Дата",
        "field_time": "Время",
        "field_pickup": "Адрес забора",
        "field_delivery": "Адрес доставки",
        "field_description": "Описание",
        "field_comment": "Комментарий",
        "field_photos": "Фото",
        "type_now": "Срочная доставка",
        "type_later": "Доставка на позже",
    },
}

ALL_MENU_ALIASES = {
    "now": {"Tilaa heti", "Order now", "Заказать сейчас"},
    "later": {"Tilaa myöhemmin", "Order later", "Заказать на позже"},
    "prices": {"Hinnat", "Prices", "Цены"},
    "faq": {"FAQ"},
    "contact": {"Yhteystiedot", "Contact", "Контакты"},
    "language": {"Kieli", "Language", "Язык"},
}


@dataclass
class UserProfile:
    telegram_id: int
    language: str = "ru"
    name: str = ""
    phone: str = ""
    email: str = ""
    last_pickup: str = ""
    last_delivery: str = ""
    last_order_id: str = ""


@dataclass
class Order:
    order_id: str
    order_type: str
    status: str
    created_at: str
    language: str
    customer_telegram_id: int
    customer_name: str
    customer_phone: str
    preferred_date: str = ""
    preferred_time: str = ""
    pickup_address: str = ""
    delivery_address: str = ""
    description: str = ""
    comment: str = ""
    photo_file_ids: Optional[List[str]] = None
    tracking_token: str = ""
    delivery_proof_photo_ids: Optional[List[str]] = None


def tr(lang: str, key: str, **kwargs: Any) -> str:
    template = TEXTS.get(lang, TEXTS["ru"]).get(key, key)
    return template.format(**kwargs)


def prices_text(lang: str) -> str:
    mapping = {
        "fi": PRICE_TEXT_FI or DEFAULT_PRICE_TEXT["fi"],
        "en": PRICE_TEXT_EN or DEFAULT_PRICE_TEXT["en"],
        "ru": PRICE_TEXT_RU or DEFAULT_PRICE_TEXT["ru"],
    }
    return mapping.get(lang, mapping["ru"]).replace("\\n", "\n")


def contact_text(lang: str) -> str:
    return tr(lang, "contact", phone=CONTACT_PHONE, whatsapp=CONTACT_WHATSAPP,
              email=CONTACT_EMAIL, website=CONTACT_WEBSITE)


def load_users() -> Dict[str, Dict[str, Any]]:
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_users(data: Dict[str, Dict[str, Any]]) -> None:
    USERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_profile(user_id: int) -> UserProfile:
    users = load_users()
    raw = users.get(str(user_id))
    if raw:
        valid_fields = set(UserProfile.__dataclass_fields__.keys())
        filtered = {k: v for k, v in raw.items() if k in valid_fields}
        return UserProfile(**filtered)
    profile = UserProfile(telegram_id=user_id)
    users[str(user_id)] = asdict(profile)
    save_users(users)
    return profile


def save_profile(profile: UserProfile) -> None:
    users = load_users()
    users[str(profile.telegram_id)] = asdict(profile)
    save_users(users)


def save_order(order: Order) -> None:
    path = ORDERS_DIR / f"{order.order_id}.json"
    path.write_text(json.dumps(asdict(order), ensure_ascii=False, indent=2), encoding="utf-8")


def load_order(order_id: str) -> Order:
    data = json.loads((ORDERS_DIR / f"{order_id}.json").read_text(encoding="utf-8"))
    return Order(**data)


def update_order(order_id: str, **fields: Any) -> Order:
    order = load_order(order_id)
    for key, value in fields.items():
        setattr(order, key, value)
    save_order(order)
    return order


def parse_date(value: str) -> bool:
    try:
        datetime.strptime(value.strip(), "%d.%m.%Y")
        return True
    except ValueError:
        return False


def parse_time(value: str) -> bool:
    try:
        datetime.strptime(value.strip(), "%H:%M")
        return True
    except ValueError:
        return False


def customer_menu(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [tr(lang, "btn_now"), tr(lang, "btn_later")],
            [tr(lang, "btn_prices"), tr(lang, "btn_faq")],
            [tr(lang, "btn_contact"), tr(lang, "btn_language")],
        ],
        resize_keyboard=True,
    )


def photo_controls(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[tr(lang, "done"), tr(lang, "skip")]], resize_keyboard=True)


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🇫🇮 Suomi", callback_data="lang:fi")],
            [InlineKeyboardButton("🇬🇧 English", callback_data="lang:en")],
            [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru")],
        ]
    )


def confirm_controls(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tr(lang, "confirm_btn"), callback_data="confirm:yes")],
            [InlineKeyboardButton(tr(lang, "edit_btn"), callback_data="confirm:restart")],
            [InlineKeyboardButton(tr(lang, "cancel_btn"), callback_data="confirm:cancel")],
        ]
    )


def operator_keyboard(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Принять", callback_data=f"op:approve:{order_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"op:reject:{order_id}"),
            ],
            [
                InlineKeyboardButton("🚗 Еду к месту забора", callback_data=f"op:pickup:{order_id}"),
                InlineKeyboardButton("📦 Заказ забран", callback_data=f"op:picked:{order_id}"),
            ],
            [
                InlineKeyboardButton("➡️ Еду к месту доставки", callback_data=f"op:delivery:{order_id}"),
                InlineKeyboardButton("✅ Доставлено", callback_data=f"op:delivered:{order_id}"),
            ],
            [InlineKeyboardButton("🛑 Отменено", callback_data=f"op:cancelled:{order_id}")],
        ]
    )


def delivery_proof_done_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """Keyboard shown to operator while collecting delivery proof photos."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Готово — отправить клиенту", callback_data=f"proof:done:{order_id}")],
            [InlineKeyboardButton("⏭ Пропустить (без фото)", callback_data=f"proof:skip:{order_id}")],
        ]
    )


def state_of(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("state", "menu")


def set_state(context: ContextTypes.DEFAULT_TYPE, state: str) -> None:
    context.user_data["state"] = state


def clear_form(context: ContextTypes.DEFAULT_TYPE, keep_lang: Optional[str] = None) -> None:
    lang = keep_lang or context.user_data.get("lang")
    context.user_data.clear()
    if lang:
        context.user_data["lang"] = lang
    context.user_data["state"] = "menu"


def normalize_menu_action(text: str) -> Optional[str]:
    cleaned = (text or "").strip()
    for action, variants in ALL_MENU_ALIASES.items():
        if cleaned in variants:
            return action
    return None


def build_summary(lang: str, form: dict, order_type: str, photos: list) -> str:
    order_label = tr(lang, "type_now" if order_type == OrderType.NOW.value else "type_later")
    lines = [f"<b>{order_label}</b>"]
    lines.append(f"{tr(lang, 'field_name')}: {form.get('name', '')}")
    lines.append(f"{tr(lang, 'field_phone')}: {form.get('phone', '')}")
    if order_type == OrderType.LATER.value:
        lines.append(f"{tr(lang, 'field_date')}: {form.get('date', '')}")
        lines.append(f"{tr(lang, 'field_time')}: {form.get('time', '')}")
    lines.append(f"{tr(lang, 'field_pickup')}: {form.get('pickup', '')}")
    lines.append(f"{tr(lang, 'field_delivery')}: {form.get('delivery', '')}")
    lines.append(f"{tr(lang, 'field_description')}: {form.get('description', '')}")
    lines.append(f"{tr(lang, 'field_comment')}: {form.get('comment', '') or '-'}")
    lines.append(f"{tr(lang, 'field_photos')}: {len(photos)}")
    lines.append("")
    lines.append(tr(lang, "confirm"))
    return "\n".join(lines)


async def send_main_menu(message, lang: str) -> None:
    await message.reply_text(tr(lang, "menu_prompt"), reply_markup=customer_menu(lang))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payload = context.args[0].strip().lower() if context.args else ""
    lang_before = context.user_data.get("lang")
    clear_form(context, keep_lang=lang_before)
    context.user_data["entry_payload"] = payload
    await update.effective_message.reply_text(
        TEXTS["ru"]["choose_language"], reply_markup=language_keyboard()
    )
    set_state(context, "choose_language")


async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = query.data.split(":", 1)[1]
    profile = get_profile(query.from_user.id)
    profile.language = lang
    save_profile(profile)
    context.user_data["lang"] = lang
    set_state(context, "menu")
    await query.message.reply_text(tr(lang, "welcome"), reply_markup=customer_menu(lang))
    payload = context.user_data.get("entry_payload", "")
    if payload == "now":
        await begin_order(query.message, context, OrderType.NOW.value)
    elif payload == "later":
        await begin_order(query.message, context, OrderType.LATER.value)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = get_profile(update.effective_user.id)
    lang = context.user_data.get("lang", profile.language)
    text = (
        "/start — меню\n"
        "/new — срочная доставка\n"
        "/later — доставка на позже\n"
        "/status — статус последнего заказа\n"
        "/cancel — отменить заполнение\n"
        "/language — выбрать язык\n"
        "/myid — узнать свой Telegram ID"
    )
    await update.effective_message.reply_text(text, reply_markup=customer_menu(lang))


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    await update.effective_message.reply_text(
        f"Ваш Telegram ID: <code>{uid}</code>", parse_mode=ParseMode.HTML
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = get_profile(update.effective_user.id)
    lang = context.user_data.get("lang", profile.language)
    if not profile.last_order_id:
        await update.effective_message.reply_text(tr(lang, "no_active"))
        return
    try:
        order = load_order(profile.last_order_id)
    except FileNotFoundError:
        await update.effective_message.reply_text(tr(lang, "no_active"))
        return
    status_label = STATUS_LABELS[lang].get(order.status, order.status)
    await update.effective_message.reply_text(
        tr(lang, "status_message", order_id=order.order_id, status=status_label)
    )


async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        TEXTS["ru"]["choose_language"], reply_markup=language_keyboard()
    )
    set_state(context, "choose_language")


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await begin_order(update.effective_message, context, OrderType.NOW.value)


async def cmd_later(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await begin_order(update.effective_message, context, OrderType.LATER.value)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = get_profile(update.effective_user.id)
    lang = context.user_data.get("lang", profile.language)
    clear_form(context, keep_lang=lang)
    await update.effective_message.reply_text(
        tr(lang, "order_cancelled"), reply_markup=customer_menu(lang)
    )


async def begin_order(message, context: ContextTypes.DEFAULT_TYPE, order_type: str) -> None:
    user_id = message.chat.id
    profile = get_profile(user_id)
    lang = context.user_data.get("lang", profile.language)
    context.user_data["lang"] = lang
    context.user_data["order_type"] = order_type
    context.user_data["photos"] = []
    context.user_data["form"] = {
        "name": profile.name,
        "phone": profile.phone,
        "pickup": profile.last_pickup,
        "delivery": profile.last_delivery,
        "date": "",
        "time": "",
        "description": "",
        "comment": "",
    }
    if profile.name or profile.phone:
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(tr(lang, "yes"), callback_data="reuse:yes")],
                [InlineKeyboardButton(tr(lang, "edit"), callback_data="reuse:no")],
            ]
        )
        await message.reply_text(tr(lang, "reuse_profile"), reply_markup=keyboard)
        set_state(context, "reuse_profile")
        return
    await message.reply_text(tr(lang, "ask_name"), reply_markup=ReplyKeyboardRemove())
    set_state(context, "ask_name")


async def handle_reuse(query, context: ContextTypes.DEFAULT_TYPE, reuse_yes: bool) -> None:
    lang = context.user_data.get("lang", "ru")
    if reuse_yes:
        if context.user_data.get("order_type") == OrderType.LATER.value:
            await query.message.reply_text(tr(lang, "ask_date"), reply_markup=ReplyKeyboardRemove())
            set_state(context, "ask_date")
        else:
            await query.message.reply_text(tr(lang, "ask_pickup"), reply_markup=ReplyKeyboardRemove())
            set_state(context, "ask_pickup")
    else:
        context.user_data.setdefault("form", {}).update({"name": "", "phone": ""})
        await query.message.reply_text(tr(lang, "ask_name"), reply_markup=ReplyKeyboardRemove())
        set_state(context, "ask_name")


async def handle_confirm(query, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    lang = context.user_data.get("lang", "ru")
    if action == "restart":
        context.user_data["photos"] = []
        context.user_data["form"] = {
            "name": "", "phone": "", "pickup": "", "delivery": "",
            "date": "", "time": "", "description": "", "comment": "",
        }
        await query.message.reply_text(tr(lang, "ask_name"), reply_markup=ReplyKeyboardRemove())
        set_state(context, "ask_name")
        return
    if action == "cancel":
        clear_form(context, keep_lang=lang)
        await query.message.reply_text(tr(lang, "order_cancelled"), reply_markup=customer_menu(lang))
        return

    form = context.user_data.get("form", {})
    order_type = context.user_data.get("order_type", OrderType.NOW.value)
    order_id = datetime.now().strftime("%y%m%d%H%M%S") + uuid4().hex[:4]
    tracking_token = uuid4().hex
    order = Order(
        order_id=order_id,
        order_type=order_type,
        status=OrderStatus.PENDING_APPROVAL.value,
        created_at=datetime.utcnow().isoformat(),
        language=lang,
        customer_telegram_id=query.from_user.id,
        customer_name=form.get("name", ""),
        customer_phone=form.get("phone", ""),
        preferred_date=form.get("date", ""),
        preferred_time=form.get("time", ""),
        pickup_address=form.get("pickup", ""),
        delivery_address=form.get("delivery", ""),
        description=form.get("description", ""),
        comment=form.get("comment", ""),
        photo_file_ids=context.user_data.get("photos", []),
        tracking_token=tracking_token,
    )
    save_order(order)

    profile = get_profile(query.from_user.id)
    profile.language = lang
    profile.name = form.get("name", "")
    profile.phone = form.get("phone", "")
    profile.last_pickup = form.get("pickup", "")
    profile.last_delivery = form.get("delivery", "")
    profile.last_order_id = order_id
    save_profile(profile)

    await send_order_to_operator(context, order)

    status_label = STATUS_LABELS[lang][OrderStatus.PENDING_APPROVAL.value]
    customer_text = (
        tr(lang, "order_received", status=status_label)
        if order_type == OrderType.NOW.value
        else tr(lang, "request_received")
    )
    clear_form(context, keep_lang=lang)
    await query.message.reply_text(customer_text, reply_markup=customer_menu(lang))


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""

    if data.startswith("lang:"):
        await choose_language(update, context)
        return
    if data.startswith("reuse:"):
        await query.answer()
        await handle_reuse(query, context, data == "reuse:yes")
        return
    if data.startswith("confirm:"):
        await query.answer()
        await handle_confirm(query, context, data.split(":", 1)[1])
        return
    if data.startswith("op:"):
        await operator_action(update, context)
        return
    if data.startswith("proof:"):
        await handle_proof_callback(update, context)
        return
    await query.answer()


async def operator_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    # Check permissions BEFORE answering so alert works correctly
    if str(query.from_user.id) != str(OPERATOR_CHAT_ID):
        await query.answer("⛔ Недостаточно прав", show_alert=True)
        return

    await query.answer()

    parts = query.data.split(":", 2)
    if len(parts) != 3:
        logger.warning("Malformed operator callback: %s", query.data)
        return
    _, action, order_id = parts

    # Special case: "delivered" starts proof photo collection flow
    if action == "delivered":
        context.user_data["op_proof_order_id"] = order_id
        context.user_data["op_proof_photos"] = []
        context.user_data["op_state"] = "collecting_proof"
        await query.message.reply_text(
            f"📸 Заказ #{order_id}\n\n"
            f"Пришлите фото подтверждения доставки (до {MAX_DELIVERY_PHOTOS} фото).\n"
            f"Когда закончите — нажмите «Готово».",
            reply_markup=delivery_proof_done_keyboard(order_id),
        )
        return

    mapping = {
        "approve": OrderStatus.APPROVED,
        "reject": OrderStatus.CANCELLED,
        "pickup": OrderStatus.GOING_TO_PICKUP,
        "picked": OrderStatus.PICKED_UP,
        "delivery": OrderStatus.GOING_TO_DELIVERY,
        "cancelled": OrderStatus.CANCELLED,
    }
    status = mapping.get(action)
    if not status:
        logger.warning("Unknown operator action: %s", action)
        return

    try:
        order = update_order(order_id, status=status.value)
    except FileNotFoundError:
        await query.message.reply_text(f"Заказ #{order_id} не найден.")
        return

    lang = order.language
    status_label = STATUS_LABELS[lang][status.value]

    try:
        await context.bot.send_message(
            chat_id=order.customer_telegram_id,
            text=f"📦 {status_label}",
        )
    except Exception as e:
        logger.warning("Could not notify customer %s: %s", order.customer_telegram_id, e)

    await query.message.reply_text(f"Заказ #{order_id}: {status_label}")


async def handle_proof_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle proof:done and proof:skip callbacks from operator."""
    query = update.callback_query

    if str(query.from_user.id) != str(OPERATOR_CHAT_ID):
        await query.answer("⛔ Недостаточно прав", show_alert=True)
        return

    await query.answer()

    parts = query.data.split(":", 2)
    if len(parts) != 3:
        return
    _, action, order_id = parts

    proof_photos: List[str] = context.user_data.pop("op_proof_photos", [])
    context.user_data.pop("op_proof_order_id", None)
    context.user_data.pop("op_state", None)

    try:
        order = update_order(
            order_id,
            status=OrderStatus.DELIVERED.value,
            delivery_proof_photo_ids=proof_photos,
        )
    except FileNotFoundError:
        await query.message.reply_text(f"Заказ #{order_id} не найден.")
        return

    lang = order.language
    status_label = STATUS_LABELS[lang][OrderStatus.DELIVERED.value]

    # Notify customer
    try:
        await context.bot.send_message(
            chat_id=order.customer_telegram_id,
            text=f"✅ {status_label}",
        )
        if proof_photos:
            # Send proof photos to customer as a media group or one by one
            if len(proof_photos) == 1:
                await context.bot.send_photo(
                    chat_id=order.customer_telegram_id,
                    photo=proof_photos[0],
                    caption="📷 Фото подтверждения доставки",
                )
            else:
                from telegram import InputMediaPhoto
                media = [InputMediaPhoto(media=fid) for fid in proof_photos]
                media[0] = InputMediaPhoto(
                    media=proof_photos[0],
                    caption=f"📷 Фото подтверждения доставки ({len(proof_photos)} шт.)",
                )
                await context.bot.send_media_group(
                    chat_id=order.customer_telegram_id,
                    media=media,
                )
    except Exception as e:
        logger.warning("Could not notify customer %s: %s", order.customer_telegram_id, e)

    photo_note = f" + {len(proof_photos)} фото" if proof_photos else " (без фото)"
    await query.message.reply_text(f"✅ Заказ #{order_id}: {status_label}{photo_note}")


async def send_order_to_operator(context: ContextTypes.DEFAULT_TYPE, order: Order) -> None:
    if not OPERATOR_CHAT_ID:
        logger.warning(
            "OPERATOR_CHAT_ID / ADMIN_CHAT_ID not set. Order %s not forwarded.", order.order_id
        )
        return
    order_label = "Срочная доставка" if order.order_type == OrderType.NOW.value else "Доставка на позже"
    text = (
        f"<b>🆕 Новый заказ #{order.order_id}</b>\n"
        f"Тип: {order_label}\n"
        f"Клиент: {order.customer_name}\n"
        f"Телефон: {order.customer_phone}\n"
        f"Язык: {order.language}\n"
    )
    if order.preferred_date:
        text += f"Дата: {order.preferred_date}\n"
    if order.preferred_time:
        text += f"Время: {order.preferred_time}\n"
    text += (
        f"Забор: {order.pickup_address}\n"
        f"Доставка: {order.delivery_address}\n"
        f"Описание: {order.description}\n"
        f"Комментарий: {order.comment or '-'}\n"
        f"Фото: {len(order.photo_file_ids or [])}\n"
        f"🔗 Track: {TRACKING_BASE_URL}/{order.tracking_token}"
    )
    await context.bot.send_message(
        chat_id=int(OPERATOR_CHAT_ID),
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=operator_keyboard(order.order_id),
    )
    for file_id in order.photo_file_ids or []:
        try:
            await context.bot.send_photo(chat_id=int(OPERATOR_CHAT_ID), photo=file_id)
        except Exception as e:
            logger.warning("Could not send photo %s to operator: %s", file_id, e)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    profile = get_profile(update.effective_user.id)
    lang = context.user_data.get("lang", profile.language)
    text = (message.text or "").strip()

    # Operator proof photo collection mode
    if (
        str(update.effective_user.id) == str(OPERATOR_CHAT_ID)
        and context.user_data.get("op_state") == "collecting_proof"
    ):
        order_id = context.user_data.get("op_proof_order_id", "")
        proof_photos: List[str] = context.user_data.setdefault("op_proof_photos", [])
        if message.photo:
            if len(proof_photos) >= MAX_DELIVERY_PHOTOS:
                await message.reply_text(
                    f"⚠️ Максимум {MAX_DELIVERY_PHOTOS} фото. Нажмите «Готово» для завершения.",
                    reply_markup=delivery_proof_done_keyboard(order_id),
                )
                return
            proof_photos.append(message.photo[-1].file_id)
            count = len(proof_photos)
            await message.reply_text(
                f"✅ Фото {count}/{MAX_DELIVERY_PHOTOS} добавлено.",
                reply_markup=delivery_proof_done_keyboard(order_id),
            )
            return
        # Any text while in proof mode — remind operator
        await message.reply_text(
            f"📸 Пришлите фото подтверждения доставки для заказа #{order_id}.\n"
            f"Добавлено: {len(proof_photos)}/{MAX_DELIVERY_PHOTOS}",
            reply_markup=delivery_proof_done_keyboard(order_id),
        )
        return

    action = normalize_menu_action(text)
    if action == "now":
        await begin_order(message, context, OrderType.NOW.value)
        return
    if action == "later":
        await begin_order(message, context, OrderType.LATER.value)
        return
    if action == "prices":
        await message.reply_text(prices_text(lang), reply_markup=customer_menu(lang))
        set_state(context, "menu")
        return
    if action == "faq":
        await message.reply_text(tr(lang, "faq"), reply_markup=customer_menu(lang))
        set_state(context, "menu")
        return
    if action == "contact":
        await message.reply_text(contact_text(lang), reply_markup=customer_menu(lang))
        set_state(context, "menu")
        return
    if action == "language":
        await message.reply_text(TEXTS["ru"]["choose_language"], reply_markup=language_keyboard())
        set_state(context, "choose_language")
        return

    state = state_of(context)
    form = context.user_data.setdefault("form", {})
    photos = context.user_data.setdefault("photos", [])

    if state == "choose_language":
        await message.reply_text(TEXTS["ru"]["choose_language"], reply_markup=language_keyboard())
        return

    if state == "menu":
        await send_main_menu(message, lang)
        return

    if state == "ask_name":
        if not text:
            await message.reply_text(tr(lang, "ask_name"))
            return
        form["name"] = text
        contact_button = KeyboardButton(tr(lang, "ask_phone"), request_contact=True)
        keyboard = ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True)
        await message.reply_text(tr(lang, "ask_phone"), reply_markup=keyboard)
        set_state(context, "ask_phone")
        return

    if state == "ask_phone":
        phone = message.contact.phone_number if message.contact else text
        if len(phone) < 5:
            await message.reply_text(tr(lang, "invalid_phone"))
            return
        form["phone"] = phone
        if context.user_data.get("order_type") == OrderType.LATER.value:
            await message.reply_text(tr(lang, "ask_date"), reply_markup=ReplyKeyboardRemove())
            set_state(context, "ask_date")
        else:
            await message.reply_text(tr(lang, "ask_pickup"), reply_markup=ReplyKeyboardRemove())
            set_state(context, "ask_pickup")
        return

    if state == "ask_date":
        if not parse_date(text):
            await message.reply_text(tr(lang, "invalid_date"))
            return
        form["date"] = text.strip()
        await message.reply_text(tr(lang, "ask_time"))
        set_state(context, "ask_time")
        return

    if state == "ask_time":
        if not parse_time(text):
            await message.reply_text(tr(lang, "invalid_time"))
            return
        form["time"] = text.strip()
        await message.reply_text(tr(lang, "ask_pickup"))
        set_state(context, "ask_pickup")
        return

    if state == "ask_pickup":
        form["pickup"] = text
        await message.reply_text(tr(lang, "ask_delivery"))
        set_state(context, "ask_delivery")
        return

    if state == "ask_delivery":
        form["delivery"] = text
        await message.reply_text(tr(lang, "ask_description"))
        set_state(context, "ask_description")
        return

    if state == "ask_description":
        form["description"] = text
        await message.reply_text(
            tr(lang, "ask_photos", max_photos=MAX_PHOTOS),
            reply_markup=photo_controls(lang),
        )
        set_state(context, "ask_photos")
        return

    if state == "ask_photos":
        if message.photo:
            if len(photos) >= MAX_PHOTOS:
                await message.reply_text(tr(lang, "photo_limit", max_photos=MAX_PHOTOS))
                return
            photos.append(message.photo[-1].file_id)
            await message.reply_text(
                tr(lang, "photo_saved", count=len(photos), max_photos=MAX_PHOTOS),
                reply_markup=photo_controls(lang),
            )
            return
        if text in (tr(lang, "skip"), tr(lang, "done")):
            await message.reply_text(tr(lang, "ask_comment"), reply_markup=ReplyKeyboardRemove())
            set_state(context, "ask_comment")
            return
        await message.reply_text(
            tr(lang, "ask_photos", max_photos=MAX_PHOTOS),
            reply_markup=photo_controls(lang),
        )
        return

    if state == "ask_comment":
        form["comment"] = text
        order_type = context.user_data.get("order_type", OrderType.NOW.value)
        summary = build_summary(lang, form, order_type, photos)
        await message.reply_text(summary, parse_mode=ParseMode.HTML, reply_markup=confirm_controls(lang))
        set_state(context, "confirm")
        return

    if state == "confirm":
        order_type = context.user_data.get("order_type", OrderType.NOW.value)
        summary = build_summary(lang, form, order_type, photos)
        await message.reply_text(summary, parse_mode=ParseMode.HTML, reply_markup=confirm_controls(lang))
        return

    await send_main_menu(message, lang)


def build_app() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is required")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("later", cmd_later))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("language", cmd_language))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CONTACT | filters.PHOTO) & ~filters.COMMAND,
            handle_message,
        )
    )
    return app


def main() -> None:
    app = build_app()
    logger.info("Bot started. Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
