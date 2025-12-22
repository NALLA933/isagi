import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext
from telegram.constants import ParseMode
from telegram.error import BadRequest

from shivu import application, user_collection, collection

@dataclass(frozen=True)
class ClaimConfig:
    # Pakka karein ki ye ID wahi hai jahan aap member ho
    MAIN_GROUP_ID: int = -1003100468240 
    MAIN_GROUP_LINK: str = "https://t.me/PICK_X_SUPPORT"
    RARITIES: tuple = ('🟢 Common', '🟣 Rare', '🟡 Legendary')
    COOLDOWN_HOURS: int = 24

CONFIG = ClaimConfig()
claim_lock = set()

def format_time(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    return f"{h}ʜ {m}ᴍ {s}s"

async def get_unique_character(user_id: int) -> dict | None:
    try:
        user_data = await user_collection.find_one({'id': user_id})
        claimed_ids = {c.get('id') for c in user_data.get('characters', [])} if user_data else set()
        
        # Performance fix: Direct MongoDB filter
        available = [
            char async for char in collection.find({
                'rarity': {'$in': CONFIG.RARITIES},
                'id': {'$nin': list(claimed_ids)}
            })
        ]
        return random.choice(available) if available else None
    except Exception:
        return None

async def hclaim(update: Update, context: CallbackContext):
    user = update.effective_user
    chat = update.effective_chat
    
    # --- 🛡️ FIX: MEMBERSHIP VERIFICATION START ---
    try:
        # Ye line check karegi ki user Main Group ka member hai ya nahi
        # Chahe wo kisi bhi group/DM mein command chalaye
        member = await context.bot.get_chat_member(chat_id=CONFIG.MAIN_GROUP_ID, user_id=user.id)
        
        if member.status in ['left', 'kicked']:
            raise ValueError("Not a member")
            
    except (BadRequest, Exception):
        # Agar bot group mein nahi hai ya user member nahi hai
        keyboard = [[InlineKeyboardButton("🔗 ᴊᴏɪɴ ᴍᴀɪɴ ɢʀᴏᴜᴘ", url=CONFIG.MAIN_GROUP_LINK)]]
        await update.message.reply_text(
            f"⚠️ <b>Access Denied!</b>\n\nHi {user.first_name}, daily claims are exclusive for our group members.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return
    # --- 🛡️ FIX END ---

    if user.id in claim_lock:
        await update.message.reply_text("⏳ ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ, ʏᴏᴜʀ ᴄʟᴀɪᴍ ɪs ʙᴇɪɴɢ ᴘʀᴏᴄᴇssᴇᴅ...")
        return
    
    claim_lock.add(user.id)
    
    try:
        # Timezone fix for accurate 24h cooldown
        now = datetime.now(timezone.utc)
        user_data = await user_collection.find_one({'id': user.id})
        
        if user_data and (last_claimed := user_data.get('last_daily_claim')):
            # Add UTC timezone if missing from DB
            if last_claimed.tzinfo is None:
                last_claimed = last_claimed.replace(tzinfo=timezone.utc)
                
            elapsed = now - last_claimed
            if elapsed < timedelta(hours=CONFIG.COOLDOWN_HOURS):
                remaining = timedelta(hours=CONFIG.COOLDOWN_HOURS) - elapsed
                await update.message.reply_text(
                    f"⏰ ᴀʟʀᴇᴀᴅʏ ᴄʟᴀɪᴍᴇᴅ ᴛᴏᴅᴀʏ\n⏳ ɴᴇxᴛ ᴄʟᴀɪᴍ ɪɴ: <code>{format_time(remaining)}</code>",
                    parse_mode=ParseMode.HTML
                )
                return

        char = await get_unique_character(user.id)
        if not char:
            await update.message.reply_text("❌ ɴᴏ ɴᴇᴡ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴀᴠᴀɪʟᴀʙʟᴇ ɪɴ ᴛʜᴇsᴇ ʀᴀʀɪᴛɪᴇs!")
            return
        
        await user_collection.update_one(
            {'id': user.id},
            {
                '$push': {'characters': char},
                '$set': {
                    'last_daily_claim': now,
                    'first_name': user.first_name,
                    'username': user.username
                }
            },
            upsert=True
        )
        
        # Caption with clean HTML
        caption = (
            f"<b>🎊 ᴅᴀɪʟʏ ᴄʟᴀɪᴍ sᴜᴄᴄᴇss</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💫 ᴄᴏɴɢʀᴀᴛs <a href='tg://user?id={user.id}'>{user.first_name}</a>\n"
            f"🎴 ɴᴀᴍᴇ: <b>{char.get('name')}</b>\n"
            f"⭐ ʀᴀʀɪᴛʏ: <b>{char.get('rarity')}</b>\n"
            f"🎯 ᴀɴɪᴍᴇ: <b>{char.get('anime')}</b>\n"
            f"🆔 ɪᴅ: <code>{char.get('id')}</code>\n\n"
            f"✨ ᴄᴏᴍᴇ ʙᴀᴄᴋ ɪɴ 24 ʜᴏᴜʀs!"
        )

        await update.message.reply_photo(
            photo=char.get('img_url', 'https://i.imgur.com/placeholder.png'),
            caption=caption,
            parse_mode=ParseMode.HTML
        )
    
    except Exception as e:
        await update.message.reply_text(f"❌ ᴇʀʀᴏʀ: <code>{str(e)}</code>", parse_mode=ParseMode.HTML)
    finally:
        claim_lock.discard(user.id)

application.add_handler(CommandHandler(['hclaim', 'claim'], hclaim, block=False))
