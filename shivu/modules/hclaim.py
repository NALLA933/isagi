import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext
from telegram.constants import ParseMode

from shivu import application, user_collection, collection

@dataclass(frozen=True)
class ClaimConfig:
    MAIN_GROUP_ID: int = -1003100468240
    MAIN_GROUP_LINK: str = "https://t.me/THE_DRAGON_SUPPORT"
    # Isse naye rarities add karna aasan hoga
    RARITIES: tuple = ('🟢 Common', '🟣 Rare', '🟡 Legendary', '✨ Manga', '💫 Neon')
    COOLDOWN_HOURS: int = 24

CONFIG = ClaimConfig()
claim_lock = set()

def format_time(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    return f"{h:02d}ʜ {m:02d}ᴍ {s:02d}s"

async def get_random_unique_character(user_id: int) -> dict | None:
    """Uses MongoDB Aggregation for high performance fetching"""
    try:
        user_data = await user_collection.find_one({'id': user_id}, {'characters.id': 1})
        claimed_ids = [c['id'] for c in user_data.get('characters', [])] if user_data else []

        # MongoDB Pipeline: Filters first, then picks 1 random
        pipeline = [
            {'$match': {
                'rarity': {'$in': CONFIG.RARITIES},
                'id': {'$nin': claimed_ids}
            }},
            {'$sample': {'size': 1}} # Database side random selection
        ]
        
        cursor = collection.aggregate(pipeline)
        result = await cursor.to_list(length=1)
        return result[0] if result else None
    except Exception as e:
        print(f"Error fetching character: {e}")
        return None

def build_caption(char: dict, user_id: int, first_name: str) -> str:
    # Safely handling missing fields with .get()
    event = f"\n🎪 ᴇᴠᴇɴᴛ: <b>{char.get('event', {}).get('name', 'N/A')}</b>" if char.get('event') else ""
    
    return (
        f"<b>🎊 ᴅᴀɪʟʏ ᴄʟᴀɪᴍ sᴜᴄᴄᴇss</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💫 ᴄᴏɴɢʀᴀᴛs <a href='tg://user?id={user_id}'>{first_name}</a>\n"
        f"🎴 ɴᴀᴍᴇ: <b>{char.get('name', 'Unknown')}</b>\n"
        f"⭐ ʀᴀʀɪᴛʏ: <b>{char.get('rarity', 'Unknown')}</b>\n"
        f"🎯 ᴀɴɪᴍᴇ: <b>{char.get('anime', 'Unknown')}</b>\n"
        f"🆔 ɪᴅ: <code>{char.get('id', 'N/A')}</code>\n"
        f"{event}\n"
        f"✨ ᴄᴏᴍᴇ ʙᴀᴄᴋ ᴀғᴛᴇʀ 24 ʜᴏᴜʀs!"
    )

async def hclaim(update: Update, context: CallbackContext):
    query_user = update.effective_user
    chat_id = update.effective_chat.id
    
    # 1. Group Check
    if chat_id != CONFIG.MAIN_GROUP_ID:
        keyboard = [[InlineKeyboardButton("🔗 ᴊᴏɪɴ ᴍᴀɪɴ ɢʀᴏᴜᴘ", url=CONFIG.MAIN_GROUP_LINK)]]
        await update.message.reply_text(
            "⚠️ <b>Access Denied!</b>\n\nDaily claims are only allowed in our support group.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return

    # 2. Concurrency Lock
    if query_user.id in claim_lock:
        return # Ignore multiple clicks silently or send warning

    claim_lock.add(query_user.id)

    try:
        # 3. Time Check (Using UTC)
        now = datetime.now(timezone.utc)
        user_data = await user_collection.find_one({'id': query_user.id})

        if user_data and (last_claimed := user_data.get('last_daily_claim')):
            # Ensuring last_claimed has timezone info
            if last_claimed.tzinfo is None:
                last_claimed = last_claimed.replace(tzinfo=timezone.utc)
                
            elapsed = now - last_claimed
            if elapsed < timedelta(hours=CONFIG.COOLDOWN_HOURS):
                remaining = timedelta(hours=CONFIG.COOLDOWN_HOURS) - elapsed
                await update.message.reply_text(
                    f"⏰ <b>ᴀʟʀᴇᴀᴅʏ ᴄʟᴀɪᴍᴇᴅ</b>\n\n⏳ ɴᴇxᴛ ᴄʟᴀɪᴍ ᴘᴏssɪʙʟᴇ ɪɴ: <code>{format_time(remaining)}</code>",
                    parse_mode=ParseMode.HTML
                )
                return

        # 4. Fetch Unique Character
        char = await get_random_unique_character(query_user.id)
        if not char:
            await update.message.reply_text("❌ <b>ɴᴏ ɴᴇᴡ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴀᴠᴀɪʟᴀʙʟᴇ</b>\nYou have claimed everything!")
            return

        # 5. Database Update (Atomic)
        await user_collection.update_one(
            {'id': query_user.id},
            {
                '$push': {'characters': char},
                '$set': {
                    'last_daily_claim': now,
                    'first_name': query_user.first_name,
                    'username': query_user.username
                }
            },
            upsert=True
        )

        # 6. Success Response
        await update.message.reply_photo(
            photo=char.get('img_url', 'https://i.imgur.com/placeholder.png'),
            caption=build_caption(char, query_user.id, query_user.first_name),
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        await update.message.reply_text(f"❌ <b>Sʏsᴛᴇᴍ Eʀʀᴏʀ:</b> <code>{str(e)}</code>", parse_mode=ParseMode.HTML)
    finally:
        claim_lock.discard(query_user.id)

# Add Handler
application.add_handler(CommandHandler(['hclaim', 'claim'], hclaim, block=False))
