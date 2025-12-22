import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext

from shivu import application, user_collection, collection


@dataclass(frozen=True)
class ClaimConfig:
    main_group_id: int = -1003100468240
    main_group_link: str = "https://t.me/THE_DRAGON_SUPPORT"
    rarities: tuple = ('🟢 Common', '🟣 Rare', '🟡 Legendary')
    cooldown: timedelta = timedelta(hours=24)


CONFIG = ClaimConfig()


def format_time(td: timedelta) -> str:
    s = int(td.total_seconds())
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h}ʜ {m}ᴍ {s}s"


async def get_unique_character(claimed_ids: list[int]) -> dict | None:
    cursor = collection.find(
        {
            'rarity': {'$in': CONFIG.rarities},
            'id': {'$nin': claimed_ids}
        }
    )

    characters = await cursor.to_list(length=100)
    return random.choice(characters) if characters else None


def build_caption(char: dict, user_id: int, name: str) -> str:
    return (
        f"🎊 <b>Daily Claim Success</b>\n\n"
        f"👤 <a href='tg://user?id={user_id}'>{name}</a>\n"
        f"🎴 <b>{char['name']}</b>\n"
        f"⭐ {char['rarity']}\n"
        f"🎯 {char['anime']}\n"
        f"🆔 <code>{char['id']}</code>\n\n"
        f"⏳ Come back after 24 hours"
    )


async def hclaim(update: Update, context: CallbackContext):
    if update.effective_chat.id != CONFIG.main_group_id:
        await update.message.reply_text(
            "⚠️ Use this command in main group only.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Join Main Group", url=CONFIG.main_group_link)]
            ])
        )
        return

    user = update.effective_user
    now = datetime.now(timezone.utc)

    user_data = await user_collection.find_one({'id': user.id})

    if not user_data:
        user_data = {
            'id': user.id,
            'first_name': user.first_name,
            'username': user.username,
            'claimed_char_ids': [],
            'last_claim': None
        }
        await user_collection.insert_one(user_data)

    last_claim = user_data.get('last_claim')
    if last_claim and now - last_claim < CONFIG.cooldown:
        remaining = CONFIG.cooldown - (now - last_claim)
        await update.message.reply_text(
            f"⏰ Already claimed\n⏳ Next claim in `{format_time(remaining)}`",
            parse_mode='Markdown'
        )
        return

    char = await get_unique_character(user_data['claimed_char_ids'])
    if not char:
        await update.message.reply_text("❌ No new characters available.")
        return

    await user_collection.update_one(
        {'id': user.id},
        {
            '$push': {'claimed_char_ids': char['id']},
            '$set': {
                'last_claim': now,
                'first_name': user.first_name,
                'username': user.username
            }
        }
    )

    await update.message.reply_photo(
        photo=char.get('img_url'),
        caption=build_caption(char, user.id, user.first_name),
        parse_mode='HTML'
    )


application.add_handler(CommandHandler(['hclaim', 'claim'], hclaim, block=False))