import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext

from shivu import application, user_collection, collection


@dataclass(frozen=True)
class ClaimConfig:
    main_group_id: int = -1003100468240
    main_group_link: str = "https://t.me/PICK_X_SUPPORT"
    rarities: tuple = ('🟢 Common', '🟣 Rare', '🟡 Legendary')


CONFIG = ClaimConfig()
claim_lock = set()


def format_time(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}ʜ {minutes}ᴍ {seconds}s"


async def get_unique_character(user_id: int) -> dict | None:
    try:
        user_data = await user_collection.find_one({'id': user_id})
        claimed_ids = {c.get('id') for c in user_data.get('characters', [])} if user_data else set()
        
        available = [
            char async for char in collection.find({'rarity': {'$in': CONFIG.rarities}})
            if char.get('id') not in claimed_ids
        ]
        
        return random.choice(available) if available else None
    except Exception:
        return None


def build_caption(char: dict, user_id: int, first_name: str) -> str:
    event = f"\n🎪 ᴇᴠᴇɴᴛ: <b>{char['event']['name']}</b>" if char.get('event', {}).get('name') else ""
    origin = f"\n🌍 ᴏʀɪɢɪɴ: <b>{char['origin']}</b>" if char.get('origin') else ""
    abilities = f"\n⚔️ ᴀʙɪʟɪᴛɪᴇs: <b>{char['abilities']}</b>" if char.get('abilities') else ""
    description = f"\n📝 ᴅᴇsᴄʀɪᴘᴛɪᴏɴ: <b>{char['description']}</b>" if char.get('description') else ""
    
    return (
        f"🎊 ᴅᴀɪʟʏ ᴄʟᴀɪᴍ sᴜᴄᴄᴇss\n"
        f"💫 ᴄᴏɴɢʀᴀᴛs <a href='tg://user?id={user_id}'>{first_name}</a>\n"
        f"🎴 ɴᴀᴍᴇ: <b>{char.get('name', 'Unknown')}</b>\n"
        f"⭐ ʀᴀʀɪᴛʏ: <b>{char.get('rarity', 'Unknown')}</b>\n"
        f"🎯 ᴀɴɪᴍᴇ: <b>{char.get('anime', 'Unknown')}</b>\n"
        f"🆔 ɪᴅ: <code>{char.get('id', 'N/A')}</code>{event}{origin}{abilities}{description}\n"
        f"✨ ᴄᴏᴍᴇ ʙᴀᴄᴋ ɪɴ 24 ʜᴏᴜʀs"
    )


async def hclaim(update: Update, context: CallbackContext):
    if update.effective_chat.id != CONFIG.main_group_id:
        keyboard = [[InlineKeyboardButton("🔗 ᴊᴏɪɴ ᴍᴀɪɴ ɢʀᴏᴜᴘ", url=CONFIG.main_group_link)]]
        await update.message.reply_text(
            "⚠️ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴄᴀɴ ᴏɴʟʏ ʙᴇ ᴜsᴇᴅ ɪɴ ᴛʜᴇ ᴍᴀɪɴ ɢʀᴏᴜᴘ!\n\n"
            "📍 ᴘʟᴇᴀsᴇ ᴊᴏɪɴ ᴏᴜʀ ᴍᴀɪɴ ɢʀᴏᴜᴘ ᴛᴏ ᴜsᴇ ᴛʜɪs ғᴇᴀᴛᴜʀᴇ.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    user_id = update.effective_user.id
    
    if user_id in claim_lock:
        await update.message.reply_text("⏳ ᴄʟᴀɪᴍ ɪɴ ᴘʀᴏɢʀᴇss ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ")
        return
    
    claim_lock.add(user_id)
    
    try:
        first_name = update.effective_user.first_name
        username = update.effective_user.username
        
        user_data = await user_collection.find_one({'id': user_id})
        
        if not user_data:
            user_data = {
                'id': user_id,
                'first_name': first_name,
                'username': username,
                'characters': [],
                'last_daily_claim': None
            }
            await user_collection.insert_one(user_data)
        
        if last_claimed := user_data.get('last_daily_claim'):
            if isinstance(last_claimed, datetime) and last_claimed.date() == datetime.utcnow().date():
                remaining = timedelta(days=1) - (datetime.utcnow() - last_claimed)
                await update.message.reply_text(
                    f"⏰ ᴀʟʀᴇᴀᴅʏ ᴄʟᴀɪᴍᴇᴅ ᴛᴏᴅᴀʏ\n⏳ ɴᴇxᴛ ᴄʟᴀɪᴍ ɪɴ: `{format_time(remaining)}`",
                    parse_mode='Markdown'
                )
                return
        
        if not (char := await get_unique_character(user_id)):
            await update.message.reply_text("❌ ɴᴏ ɴᴇᴡ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴀᴠᴀɪʟᴀʙʟᴇ")
            return
        
        await user_collection.update_one(
            {'id': user_id},
            {
                '$push': {'characters': char},
                '$set': {
                    'last_daily_claim': datetime.utcnow(),
                    'first_name': first_name,
                    'username': username
                }
            }
        )
        
        caption = build_caption(char, user_id, first_name)
        await update.message.reply_photo(
            photo=char.get('img_url', 'https://i.imgur.com/placeholder.png'),
            caption=caption,
            parse_mode='HTML'
        )
    
    except Exception as e:
        await update.message.reply_text(f"❌ ᴇʀʀᴏʀ: <code>{str(e)}</code>", parse_mode='HTML')
    finally:
        claim_lock.discard(user_id)


application.add_handler(CommandHandler(['hclaim', 'claim'], hclaim, block=False))