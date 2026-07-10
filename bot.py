# -*- coding: utf-8 -*-
"""
Premium Referral Bot (Koyeb & Cloud Ready)
=====================
Requires:
    pip install python-telegram-bot[job-queue] aiohttp sqlalchemy qrcode[pil] psycopg2-binary
"""

import os
import io
import csv
import re
import logging
import random
from datetime import datetime, time as dtime
from typing import Dict, Any, Optional

import aiohttp
from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, Index, func
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

try:
    import qrcode
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False


# ─────────────────────────── Config & Proxies ───────────────────────────

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = {
    int(x) for x in os.environ.get("ADMIN_IDS", "5888777479").replace(" ", "").split(",") if x.isdigit()
}

# Proxy List (Sigma Proxy / Owl Proxy)
PROXIES = [
    "http://IuNuqCIbey30_custom_zone_IN_st__city_sid_12875651_time_5:4104539@change4.owlproxy.com:7778",
    "http://ua9SUpz8S530_custom_zone_IN_st__city_sid_30862984_time_5:4104556@change4.owlproxy.com:7778",
    "http://p4o8jyZbuK90_custom_zone_IN_st__city_sid_39585662_time_5:4104557@change4.owlproxy.com:7778"
]

HOLWIN_INVITE_CODE = "WLRPSY"
REX_INVITE_CODE = "O6NVYX"

HOLWIN_BASE = "https://www.holwin123.top"
HOLWIN_DI = "88dd52c70e7b377527be01c39f5a0a4f"
HOLWIN_VTOKEN = "18667bd921478af5fe5f6506865e4f8a"

REX_BASE = "https://rcapi.rexproearn.com"
REX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://rch5.rexproearn.com",
    "Referer": "https://rch5.rexproearn.com/",
}

# Fix for Cloud PostgreSQL URLs
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///registrations.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

logging.basicConfig(
    format="[%(asctime)s] %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Engine configuration (Postgres uses different connect_args than SQLite)
if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30})
else:
    engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)

Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# ─────────────────────────── DB Models ───────────────────────────

class Registration(Base):
    __tablename__ = "registrations"
    id = Column(Integer, primary_key=True)
    mobile = Column(String(20), nullable=False)
    platform = Column(String(20), nullable=False)
    invite_used = Column(String(20), nullable=False)
    telegram_id = Column(Integer, nullable=False)
    registered_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_platform", "platform"),
        Index("idx_telegram_id", "telegram_id"),
        Index("idx_registered_at", "registered_at"),
    )


class BotUser(Base):
    __tablename__ = "bot_users"
    telegram_id = Column(Integer, primary_key=True)
    username = Column(String(64), nullable=True)
    language = Column(String(5), default="en", nullable=False)
    is_banned = Column(Boolean, default=False, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_active = Column(DateTime, default=datetime.utcnow, nullable=False)


Base.metadata.create_all(engine)

MOBILE, OTP, PASSWORD, CONFIRM = range(4)


# ─────────────────────────── i18n ───────────────────────────

STRINGS = {
    "main_title": {
        "en": "💎  R E F E R R A L   B O T  💎",
        "hi": "💎  र े फ र ल   ब ॉ ट  💎",
    },
    "select_platform": {
        "en": "🚀 *Select your platform:*",
        "hi": "🚀 *अपना प्लेटफ़ॉर्म चुनें:*",
    },
    "features": {
        "en": "🛡️ *Features:* OTP resend • Change mobile • Stats • Referral QR • Multi\\-language",
        "hi": "🛡️ *सुविधाएं:* OTP दोबारा भेजें • मोबाइल बदलें • आँकड़े • रेफ़रल QR • बहुभाषी",
    },
    "help": {
        "en": (
            "❓ *Help Center*\n\n"
            "1\\. Choose a platform from the main menu\\.\n"
            "2\\. Enter your mobile number \\(10\\-15 digits\\)\\.\n"
            "3\\. Enter the OTP you receive\\.\n"
            "4\\. Set a password or type `skip`\\.\n"
            "5\\. Confirm and register\\.\n\n"
            "📊 /stats \\- global stats\n"
            "📋 /my \\- your registrations\n"
            "🔗 /referral \\- your referral link \\+ QR\n"
            "🌐 /language \\- switch language\n"
            "🆘 /support \\- quick answers\n"
            "🔄 /start \\- main menu\n"
            "❌ /cancel \\- abort current action"
        ),
        "hi": (
            "❓ *सहायता केंद्र*\n\n"
            "1\\. मुख्य मेनू से एक प्लेटफ़ॉर्म चुनें\\.\n"
            "2\\. अपना मोबाइल नंबर \\(10\\-15 अंक\\) दर्ज करें\\.\n"
            "3\\. प्राप्त OTP दर्ज करें\\.\n"
            "4\\. पासवर्ड सेट करें या `skip` टाइप करें\\.\n"
            "5\\. पुष्टि करें और रजिस्टर करें\\.\n\n"
            "📊 /stats \\- वैश्विक आँकड़े\n"
            "📋 /my \\- आपके पंजीकरण\n"
            "🔗 /referral \\- आपका रेफ़रल लिंक \\+ QR\n"
            "🌐 /language \\- भाषा बदलें\n"
            "🆘 /support \\- त्वरित उत्तर\n"
            "🔄 /start \\- मुख्य मेनू\n"
            "❌ /cancel \\- रद्द करें"
        ),
    },
    "lang_prompt": {
        "en": "🌐 Choose your language:",
        "hi": "🌐 अपनी भाषा चुनें:",
    },
    "lang_set": {
        "en": "✅ Language set to English.",
        "hi": "✅ भाषा हिंदी में सेट हो गई।",
    },
    "enter_mobile": {
        "en": "📱 Enter your mobile number \\(10\\-15 digits\\):",
        "hi": "📱 अपना मोबाइल नंबर \\(10\\-15 अंक\\) दर्ज करें:",
    },
    "invalid_mobile": {
        "en": "❌ Invalid. Enter 10-15 digits:",
        "hi": "❌ अमान्य। 10-15 अंक दर्ज करें:",
    },
    "banned": {
        "en": "🚫 Your access has been restricted. Contact the admin.",
        "hi": "🚫 आपकी पहुँच प्रतिबंधित कर दी गई है। एडमिन से संपर्क करें।",
    },
}


def L(key: str, lang: str) -> str:
    entry = STRINGS.get(key, {})
    return entry.get(lang, entry.get("en", key))


# ─────────────────────────── Markdown escaping ───────────────────────────

_MDV2_SPECIAL = re.compile(r'([_*\[\]()~`>#+\-=|{}.!\\])')


def esc(text: str) -> str:
    return _MDV2_SPECIAL.sub(r'\\\1', str(text))


# ─────────────────────────── Keyboards ───────────────────────────

def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏠 Holwin", callback_data="platform_holwin"),
            InlineKeyboardButton("📈 Rexproearn", callback_data="platform_rex"),
        ],
        [
            InlineKeyboardButton("📊 Stats", callback_data="stats_btn"),
            InlineKeyboardButton("📋 My Registrations", callback_data="my_btn"),
        ],
        [
            InlineKeyboardButton("🔗 Referral QR", callback_data="referral_btn"),
            InlineKeyboardButton("🌐 Language", callback_data="lang_btn"),
        ],
        [
            InlineKeyboardButton("🆘 Support", callback_data="support_btn"),
            InlineKeyboardButton("❓ Help", callback_data="help_btn"),
        ],
    ])


def back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main", callback_data="main_menu")]])


def otp_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Resend OTP", callback_data="resend_otp")],
        [InlineKeyboardButton("✏️ Change Mobile", callback_data="change_mobile")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="main_menu")],
    ])


def confirm_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm", callback_data="confirm_reg")],
        [InlineKeyboardButton("✏️ Change Mobile", callback_data="change_mobile")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_reg")],
    ])


def language_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("English", callback_data="setlang_en"),
            InlineKeyboardButton("हिंदी", callback_data="setlang_hi"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
    ])


# ─────────────────────────── DB helpers ───────────────────────────

def db_session():
    return SessionLocal()


def get_or_create_user(telegram_id: int, username: Optional[str]) -> "BotUser":
    db = db_session()
    try:
        user = db.query(BotUser).filter(BotUser.telegram_id == telegram_id).first()
        if user is None:
            user = BotUser(telegram_id=telegram_id, username=username, language="en")
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            user.last_active = datetime.utcnow()
            if username and user.username != username:
                user.username = username
            db.commit()
        return {"telegram_id": user.telegram_id, "language": user.language, "is_banned": user.is_banned}
    finally:
        db.close()


def set_user_language(telegram_id: int, lang: str):
    db = db_session()
    try:
        user = db.query(BotUser).filter(BotUser.telegram_id == telegram_id).first()
        if user:
            user.language = lang
            db.commit()
    finally:
        db.close()


def is_user_banned(telegram_id: int) -> bool:
    db = db_session()
    try:
        user = db.query(BotUser).filter(BotUser.telegram_id == telegram_id).first()
        return bool(user and user.is_banned)
    finally:
        db.close()


def set_ban_status(telegram_id: int, banned: bool) -> bool:
    db = db_session()
    try:
        user = db.query(BotUser).filter(BotUser.telegram_id == telegram_id).first()
        if not user:
            return False
        user.is_banned = banned
        db.commit()
        return True
    finally:
        db.close()


def get_all_user_ids():
    db = db_session()
    try:
        return [u.telegram_id for u in db.query(BotUser).filter(BotUser.is_banned == False).all()]  # noqa: E712
    finally:
        db.close()


def save_registration(mobile: str, platform: str, invite: str, telegram_id: int):
    db: Session = db_session()
    try:
        db.add(Registration(mobile=mobile, platform=platform, invite_used=invite, telegram_id=telegram_id))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"DB save error: {e}")
        raise
    finally:
        db.close()


def get_stats():
    db = db_session()
    try:
        total = db.query(func.count(Registration.id)).scalar() or 0
        holwin = db.query(func.count(Registration.id)).filter(Registration.platform == "holwin").scalar() or 0
        rex = db.query(func.count(Registration.id)).filter(Registration.platform == "rex").scalar() or 0
        recent = db.query(Registration).order_by(Registration.registered_at.desc()).limit(10).all()
        return total, holwin, rex, recent
    finally:
        db.close()


def get_user_stats(user_id: int):
    db = db_session()
    try:
        total = db.query(func.count(Registration.id)).filter(Registration.telegram_id == user_id).scalar() or 0
        holwin = db.query(func.count(Registration.id)).filter(
            Registration.telegram_id == user_id, Registration.platform == "holwin"
        ).scalar() or 0
        rex = db.query(func.count(Registration.id)).filter(
            Registration.telegram_id == user_id, Registration.platform == "rex"
        ).scalar() or 0
        return total, holwin, rex
    finally:
        db.close()


def export_registrations_csv() -> io.BytesIO:
    db = db_session()
    try:
        rows = db.query(Registration).order_by(Registration.registered_at.desc()).all()
    finally:
        db.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "mobile", "platform", "invite_used", "telegram_id", "registered_at"])
    for r in rows:
        writer.writerow([r.id, r.mobile, r.platform, r.invite_used, r.telegram_id, r.registered_at.isoformat()])

    byte_buf = io.BytesIO(buf.getvalue().encode("utf-8"))
    byte_buf.name = f"registrations_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
    return byte_buf


# ─────────────────────────── API Clients (With Proxy Rotation) ───────────────────────────

class HolwinClient:
    def __init__(self):
        self.session = None
        self.proxy = random.choice(PROXIES)

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=20)
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://www.holwin123.top",
            "Referer": "https://www.holwin123.top/userRegister",
            "di": HOLWIN_DI,
            "vtoken": HOLWIN_VTOKEN,
        }
        self.session = aiohttp.ClientSession(headers=headers, timeout=timeout)
        logger.info(f"HolwinClient initialized with proxy: {self.proxy.split('@')[1]}")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.session:
            await self.session.close()

    async def post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            async with self.session.post(f"{HOLWIN_BASE}{path}", json=payload, proxy=self.proxy) as resp:
                data = await resp.json(content_type=None)
                return data if isinstance(data, dict) else {"code": -1, "msg": "Unexpected response format"}
        except Exception as e:
            logger.error(f"Holwin Request Error/Proxy Error: {e}")
            return {"code": -1, "msg": f"Network or Proxy Error: {str(e)}"}


class RexClient:
    def __init__(self):
        self.session = None
        self.proxy = random.choice(PROXIES)

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=20)
        self.session = aiohttp.ClientSession(headers=REX_HEADERS, timeout=timeout)
        logger.info(f"RexClient initialized with proxy: {self.proxy.split('@')[1]}")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.session:
            await self.session.close()

    async def post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            async with self.session.post(f"{REX_BASE}{path}", json=payload, proxy=self.proxy) as resp:
                data = await resp.json(content_type=None)
                return data if isinstance(data, dict) else {"code": -1, "msg": "Unexpected response format"}
        except Exception as e:
            logger.error(f"Rex Request Error/Proxy Error: {e}")
            return {"code": -1, "msg": f"Network or Proxy Error: {str(e)}"}


# ─────────────────────────── Core handlers ───────────────────────────

async def touch_user_and_check_ban(update: Update) -> Dict[str, Any]:
    user = update.effective_user
    info = get_or_create_user(user.id, user.username)
    return info


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    info = await touch_user_and_check_ban(update)
    lang = info["language"]

    if info["is_banned"]:
        text = L("banned", lang)
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return

    msg = (
        "╔═══════════════════════════════╗\n"
        f"║   {L('main_title', lang)}   ║\n"
        "╚═══════════════════════════════╝\n\n"
        f"{L('select_platform', lang)}\n\n"
        "┌─────────────────────────────┐\n"
        "│  🏠 *Holwin* │\n"
        f"│  Invite: `{esc(HOLWIN_INVITE_CODE)}`   │\n"
        "├─────────────────────────────┤\n"
        "│  📈 *Rexproearn* │\n"
        f"│  Invite: `{esc(REX_INVITE_CODE)}`      │\n"
        "└─────────────────────────────┘\n\n"
        f"{L('features', lang)}\n"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            msg, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_keyboard(), disable_web_page_preview=True
        )
    else:
        await update.message.reply_text(
            msg, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=main_keyboard(), disable_web_page_preview=True
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = await touch_user_and_check_ban(update)
    text = L("help", info["language"])
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=back_keyboard())
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=back_keyboard())


async def language_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = await touch_user_and_check_ban(update)
    text = L("lang_prompt", info["language"])
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=language_keyboard())
    else:
        await update.message.reply_text(text, reply_markup=language_keyboard())


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = q.data.split("_")[1]
    set_user_language(update.effective_user.id, lang)
    await q.edit_message_text(L("lang_set", lang), reply_markup=back_keyboard())


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await touch_user_and_check_ban(update)
    total, holwin, rex, recent = get_stats()
    msg = (
        "📊 *Global Stats*\n\n"
        f"👥 Total: `{total}`\n"
        f"🏠 Holwin: `{holwin}`\n"
        f"📈 Rexproearn: `{rex}`\n\n"
        "🕒 *Last 10 Registrations:*\n"
    )
    if recent:
        for r in recent:
            msg += f"• `{esc(r.mobile)}` \\- {esc(r.platform.upper())} \\- {esc(r.registered_at.strftime('%Y-%m-%d %H:%M'))}\n"
    else:
        msg += "No registrations yet\\."

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="stats_btn")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")],
    ])
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb)
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb)


async def my_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await touch_user_and_check_ban(update)
    total, holwin, rex = get_user_stats(update.effective_user.id)
    msg = (
        "📋 *Your Registrations*\n\n"
        f"👤 Total: `{total}`\n"
        f"🏠 Holwin: `{holwin}`\n"
        f"📈 Rexproearn: `{rex}`"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]])
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb)
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb)


async def referral_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await touch_user_and_check_ban(update)
    bot_username = context.bot_data.get("bot_username")
    if not bot_username:
        me = await context.bot.get_me()
        bot_username = me.username
        context.bot_data["bot_username"] = bot_username

    link = f"https://t.me/{bot_username}"
    caption = (
        "🔗 *Your Referral Link*\n\n"
        f"`{esc(link)}`\n\n"
        "Share this link or QR code \\- anyone who opens it lands on this bot's menu\\."
    )

    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()

    if QR_AVAILABLE:
        img = qrcode.make(link)
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        bio.seek(0)
        bio.name = "referral_qr.png"
        await target.reply_photo(
            photo=InputFile(bio),
            caption=caption,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=back_keyboard(),
        )
    else:
        await target.reply_text(
            caption + "\n\n⚠️ QR image unavailable \\- install `qrcode[pil]` on the server\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=back_keyboard(),
        )


FAQ = [
    (("otp", "code not"), "If OTP isn't arriving: check the number is correct, wait 60s, then use 🔄 Resend OTP. Some carriers delay SMS by a few minutes."),
    (("password", "pwd"), "Password must be 6+ characters, or type `skip` to use a default one for the platform."),
    (("fail", "error", "not working"), "If registration fails, the platform usually returns a reason in the error message. Common causes: number already registered, wrong OTP, or the platform is temporarily down."),
    (("referral", "link", "qr"), "Use /referral to get your shareable link and QR code."),
    (("language", "hindi", "भाषा"), "Use /language to switch between English and Hindi."),
]

async def support_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await touch_user_and_check_ban(update)
    text = (
        "🆘 *Quick Support*\n\n"
        "Type a keyword \\(e\\.g\\. `otp`, `password`, `error`\\) after /support, "
        "or just ask your question as a normal message and I'll try to match it to an FAQ\\.\n\n"
        "For anything else, an admin will need to help \\- this bot doesn't have a live AI agent connected yet\\."
    )
    args = context.args if hasattr(context, "args") else []
    if args:
        answer = match_faq(" ".join(args))
        if answer:
            text = f"🆘 {esc(answer)}"
        else:
            text = "🤔 No FAQ match found\\. Try /support with a different keyword, or ask an admin\\."

    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    await target.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=back_keyboard())

def match_faq(query: str) -> Optional[str]:
    q = query.lower()
    for keywords, answer in FAQ:
        if any(kw in q for kw in keywords):
            return answer
    return None

async def freeform_text_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    answer = match_faq(text)
    if answer:
        await update.message.reply_text(f"🆘 {esc(answer)}", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=back_keyboard())


# ─────────────────────────── Admin commands ───────────────────────────

async def require_admin(update: Update) -> bool:
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        if update.callback_query:
            await update.callback_query.answer("🚫 Admins only.", show_alert=True)
        else:
            await update.message.reply_text("🚫 This command is for admins only.")
        return False
    return True

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update): return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    text = " ".join(context.args)
    ids = get_all_user_ids()
    sent, failed = 0, 0
    for uid in ids:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 {text}")
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(f"✅ Broadcast sent to {sent} users. Failed: {failed}.")

async def admin_users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update): return
    db = db_session()
    try:
        total = db.query(func.count(BotUser.telegram_id)).scalar() or 0
        banned = db.query(func.count(BotUser.telegram_id)).filter(BotUser.is_banned == True).scalar() or 0
    finally:
        db.close()
    await update.message.reply_text(f"👥 Total bot users: {total}\n🚫 Banned: {banned}\n\nUse /ban <telegram_id> or /unban <telegram_id> to manage.")

async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update): return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /ban <telegram_id>")
        return
    ok = set_ban_status(int(context.args[0]), True)
    await update.message.reply_text("✅ User banned." if ok else "❌ User not found.")

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update): return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /unban <telegram_id>")
        return
    ok = set_ban_status(int(context.args[0]), False)
    await update.message.reply_text("✅ User unbanned." if ok else "❌ User not found.")

async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update): return
    bio = export_registrations_csv()
    await update.message.reply_document(document=InputFile(bio, filename=bio.name), caption="📄 Registrations export")

async def send_summary(context: ContextTypes.DEFAULT_TYPE, label: str):
    total, holwin, rex, _ = get_stats()
    text = (f"📈 *{label} Summary*\n\n👥 Total registrations: `{total}`\n🏠 Holwin: `{holwin}`\n📈 Rexproearn: `{rex}`")
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            pass

async def daily_summary_job(context: ContextTypes.DEFAULT_TYPE): await send_summary(context, "Daily")
async def weekly_summary_job(context: ContextTypes.DEFAULT_TYPE): await send_summary(context, "Weekly")


# ─────────────────────────── Registration flow ───────────────────────────

async def platform_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    info = await touch_user_and_check_ban(update)
    if info["is_banned"]:
        await q.edit_message_text(L("banned", info["language"]))
        return ConversationHandler.END

    platform = q.data.split("_")[1]
    context.user_data["platform"] = platform
    context.user_data["invite"] = HOLWIN_INVITE_CODE if platform == "holwin" else REX_INVITE_CODE
    await q.edit_message_text(
        f"✅ Selected: *{esc(platform.upper())}*\n"
        f"Invite: `{esc(context.user_data['invite'])}`\n\n"
        f"{L('enter_mobile', info['language'])}",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=back_keyboard(),
    )
    return MOBILE


async def mobile_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = await touch_user_and_check_ban(update)
    mobile = update.message.text.strip()
    if not re.match(r"^\d{10,15}$", mobile):
        await update.message.reply_text(L("invalid_mobile", info["language"]), reply_markup=back_keyboard())
        return MOBILE

    context.user_data["mobile"] = mobile
    platform = context.user_data["platform"]

    try:
        if platform == "holwin":
            async with HolwinClient() as client:
                resp = await client.post("/api/system/sms/send", {"mobile": mobile, "type": "reg_code"})
        else:
            async with RexClient() as client:
                resp = await client.post("/app/user/sendSmsCode", {"mobileNo": mobile})
    except Exception as e:
        logger.error(f"OTP send error: {e}")
        await update.message.reply_text("❌ Failed to send OTP. Please check Proxy/Network.", reply_markup=back_keyboard())
        return ConversationHandler.END

    ok = (platform == "holwin" and resp.get("code") == 0) or (platform == "rex" and resp.get("code") == 200)
    if not ok:
        await update.message.reply_text(f"❌ OTP request failed: {resp.get('msg', 'Unknown')}", reply_markup=back_keyboard())
        return ConversationHandler.END

    await update.message.reply_text("✅ OTP sent! Enter the OTP:", reply_markup=otp_keyboard())
    return OTP


async def otp_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    otp_code = update.message.text.strip()
    if not otp_code.isdigit():
        await update.message.reply_text("❌ OTP must be numeric. Try again:", reply_markup=otp_keyboard())
        return OTP
    context.user_data["otp"] = otp_code
    await update.message.reply_text("🔑 Set a password, or type `skip`:", parse_mode=ParseMode.MARKDOWN_V2)
    return PASSWORD


async def password_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pwd = update.message.text.strip()
    platform = context.user_data["platform"]

    if pwd.lower() == "skip":
        pwd = "Dk12345dk" if platform == "rex" else "Password@123"
    elif len(pwd) < 6:
        await update.message.reply_text("❌ Min 6 characters. Try again or type `skip`:")
        return PASSWORD

    context.user_data["password"] = pwd
    mobile = context.user_data["mobile"]
    invite = context.user_data["invite"]
    summary = (
        "📋 *Summary*\n\n"
        f"📱 Mobile: `{esc(mobile)}`\n"
        f"🔑 Password: `{'*' * len(pwd)}`\n"
        f"🎫 Platform: `{esc(platform.upper())}`\n"
        f"🎫 Invite: `{esc(invite)}`\n\n"
        "Confirm?"
    )
    await update.message.reply_text(summary, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=confirm_keyboard())
    return CONFIRM


async def resend_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("Resending OTP...")
    mobile = context.user_data.get("mobile")
    platform = context.user_data.get("platform")
    if not mobile or not platform:
        await q.edit_message_text("❌ Session expired. Use /start again.")
        return ConversationHandler.END

    try:
        if platform == "holwin":
            async with HolwinClient() as client:
                resp = await client.post("/api/system/sms/send", {"mobile": mobile, "type": "reg_code"})
        else:
            async with RexClient() as client:
                resp = await client.post("/app/user/sendSmsCode", {"mobileNo": mobile})
    except Exception as e:
        logger.error(f"Resend OTP error: {e}")
        await q.edit_message_text("❌ Failed to resend OTP. Proxy/Network error.")
        return ConversationHandler.END

    ok = (platform == "holwin" and resp.get("code") == 0) or (platform == "rex" and resp.get("code") == 200)
    if not ok:
        await q.edit_message_text(f"❌ Resend failed: {resp.get('msg', 'Unknown')}")
        return ConversationHandler.END

    await q.edit_message_text("✅ OTP resent successfully. Enter OTP:", reply_markup=otp_keyboard())
    return OTP


async def change_mobile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("✏️ Enter your new mobile number (10-15 digits):", reply_markup=back_keyboard())
    return MOBILE


async def confirm_reg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    platform = context.user_data.get("platform")
    mobile = context.user_data.get("mobile")
    otp_code = context.user_data.get("otp")
    password = context.user_data.get("password")
    invite = context.user_data.get("invite")

    if not all([platform, mobile, otp_code, password, invite]):
        await q.edit_message_text("❌ Session expired. Use /start again.")
        return ConversationHandler.END

    try:
        if platform == "holwin":
            async with HolwinClient() as client:
                payload = {
                    "mobile": mobile,
                    "authCode": otp_code,
                    "password": password,
                    "inviteCode": invite,
                    "sourceAppType": "lobby",
                    "registerHost": "www.holwin123.top",
                    "sourceUrl": "https://www.hlowin.link/",
                }
                resp = await client.post("/api/user/register", payload)
                success = resp.get("code") == 0
        else:
            async with RexClient() as client:
                payload = {"mobileNo": mobile, "password": password, "smsCode": otp_code, "inviteCode": invite}
                resp = await client.post("/app/user/register", payload)
                success = resp.get("code") == 200
    except Exception as e:
        logger.error(f"Registration error: {e}")
        await q.edit_message_text("❌ Registration failed due to network/proxy error.")
        return ConversationHandler.END

    if success:
        try:
            save_registration(mobile, platform, invite, update.effective_user.id)
        except Exception:
            await q.edit_message_text("❌ Registration succeeded but local save failed.")
            return ConversationHandler.END

        await q.edit_message_text(
            "✅ *Registration successful\\!*\n\n"
            f"Platform: {esc(platform.upper())}\n"
            f"Mobile: `{esc(mobile)}`\n"
            f"Invite used: `{esc(invite)}`\n\n"
            "Saved locally\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=back_keyboard(),
        )
        context.user_data.clear()
        return ConversationHandler.END

    await q.edit_message_text(f"❌ Registration failed: `{esc(resp.get('msg', 'Unknown error'))}`", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=back_keyboard())
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ Cancelled.")
    else:
        await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)
    return ConversationHandler.END

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled exception while processing an update", exc_info=context.error)


# ─────────────────────────── Wiring ───────────────────────────

conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(platform_selected, pattern="^platform_(holwin|rex)$")],
    states={
        MOBILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, mobile_input), CallbackQueryHandler(main_menu, pattern="^main_menu$")],
        OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, otp_input), CallbackQueryHandler(resend_otp, pattern="^resend_otp$"), CallbackQueryHandler(change_mobile, pattern="^change_mobile$"), CallbackQueryHandler(main_menu, pattern="^main_menu$")],
        PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, password_input), CallbackQueryHandler(main_menu, pattern="^main_menu$")],
        CONFIRM: [CallbackQueryHandler(confirm_reg, pattern="^confirm_reg$"), CallbackQueryHandler(change_mobile, pattern="^change_mobile$"), CallbackQueryHandler(cancel, pattern="^cancel_reg$"), CallbackQueryHandler(main_menu, pattern="^main_menu$")],
    },
    fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(main_menu, pattern="^main_menu$")],
    allow_reentry=True,
)


def main():
    if not BOT_TOKEN or BOT_TOKEN.count(":") != 1:
        raise SystemExit("BOT_TOKEN is missing or malformed. Set it via the BOT_TOKEN environment variable.")

    app = Application.builder().token(BOT_TOKEN).concurrent_updates(False).build()

    # Core
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("my", my_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("language", language_cmd))
    app.add_handler(CommandHandler("referral", referral_cmd))
    app.add_handler(CommandHandler("support", support_cmd))

    # Admin
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("adminusers", admin_users_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("export", export_cmd))

    # Conversation
    app.add_handler(conv_handler)

    # Buttons
    app.add_handler(CallbackQueryHandler(stats_cmd, pattern="^stats_btn$"))
    app.add_handler(CallbackQueryHandler(my_cmd, pattern="^my_btn$"))
    app.add_handler(CallbackQueryHandler(help_cmd, pattern="^help_btn$"))
    app.add_handler(CallbackQueryHandler(referral_cmd, pattern="^referral_btn$"))
    app.add_handler(CallbackQueryHandler(language_cmd, pattern="^lang_btn$"))
    app.add_handler(CallbackQueryHandler(set_language, pattern="^setlang_(en|hi)$"))
    app.add_handler(CallbackQueryHandler(support_cmd, pattern="^support_btn$"))
    app.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, freeform_text_fallback), group=1)

    if app.job_queue is not None:
        app.job_queue.run_daily(daily_summary_job, time=dtime(hour=9, minute=0))
        app.job_queue.run_daily(weekly_summary_job, time=dtime(hour=9, minute=15), days=(6,))

    app.add_error_handler(error_handler)

    logger.info("Koyeb Premium bot started with Proxy Rotation...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
