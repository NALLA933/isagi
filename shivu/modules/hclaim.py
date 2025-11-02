import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext
from shivu import application, user_collection, collection, LOGGER
import random

claim_lock = {}
MAIN_GROUP_ID = -1003100468240
MAIN_GROUP_LINK = "https://t.me/PICK_X_SUPPORT"

async def format_time_delta(delta):
    seconds = delta.total_seconds()
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours)}ʜ {int(minutes)}ᴍ {int(seconds)}s"

async def get_unique_characters(user_id, rarities=['🟢 Common', '🟣 Rare', '🟡 Legendary']):
    try:
        user_data = await user_collection.find_one({'id': user_id})
        claimed_ids = [c.get('id') for c in user_data.get('characters', [])] if user_data else []

        available = []
        async for char in collection.find({'rarity': {'$in': rarities}}):
            if char.get('id') not in claimed_ids:
                available.append(char)

        return [random.choice(available)] if available else []
    except Exception as e:
        LOGGER.error(f"[HCLAIM] Error fetching characters: {e}")
        return []

async def hclaim(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    
    # Check if command is used in the main group
    if chat_id != MAIN_GROUP_ID:
        keyboard = [[InlineKeyboardButton("🔗 ᴊᴏɪɴ ᴍᴀɪɴ ɢʀᴏᴜᴘ", url=MAIN_GROUP_LINK)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴄᴀɴ ᴏɴʟʏ ʙᴇ ᴜsᴇᴅ ɪɴ ᴛʜᴇ ᴍᴀɪɴ ɢʀᴏᴜᴘ!\n\n"
            "📍 ᴘʟᴇᴀsᴇ ᴊᴏɪɴ ᴏᴜʀ ᴍᴀɪɴ ɢʀᴏᴜᴘ ᴛᴏ ᴜsᴇ ᴛʜɪs ғᴇᴀᴛᴜʀᴇ.",
            reply_markup=reply_markup
        )
        return
    
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    username = update.effective_user.username

    if user_id in claim_lock:
        await update.message.reply_text("⏳ ᴄʟᴀɪᴍ ɪɴ ᴘʀᴏɢʀᴇss ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ")
        return

    claim_lock[user_id] = True
    try:
        user_data = await user_collection.find_one({'id': user_id})

        if not user_data:
            user_data = {'id': user_id, 'first_name': first_name, 'username': username, 'characters': [], 'last_daily_claim': None}
            await user_collection.insert_one(user_data)

        last_claimed = user_data.get('last_daily_claim')
        if last_claimed and isinstance(last_claimed, datetime) and last_claimed.date() == datetime.utcnow().date():
            remaining = timedelta(days=1) - (datetime.utcnow() - last_claimed)
            formatted_time = await format_time_delta(remaining)
            await update.message.reply_text(
                f"⏰ ᴀʟʀᴇᴀᴅʏ ᴄʟᴀɪᴍᴇᴅ ᴛᴏᴅᴀʏ\n⏳ ɴᴇxᴛ ᴄʟᴀɪᴍ ɪɴ: `{formatted_time}`",
                parse_mode='Markdown'
            )
            return

        characters = await get_unique_characters(user_id)
        if not characters:
            await update.message.reply_text("❌ ɴᴏ ɴᴇᴡ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴀᴠᴀɪʟᴀʙʟᴇ")
            return

        char = characters[0]

        await user_collection.update_one(
            {'id': user_id},
            {
                '$push': {'characters': char},
                '$set': {'last_daily_claim': datetime.utcnow(), 'first_name': first_name, 'username': username}
            }
        )

        event = f"\n🎪 ᴇᴠᴇɴᴛ: <b>{char['event']['name']}</b>" if char.get('event', {}).get('name') else ""
        origin = f"\n🌍 ᴏʀɪɢɪɴ: <b>{char['origin']}</b>" if char.get('origin') else ""
        abilities = f"\n⚔️ ᴀʙɪʟɪᴛɪᴇs: <b>{char['abilities']}</b>" if char.get('abilities') else ""
        description = f"\n📝 ᴅᴇsᴄʀɪᴘᴛɪᴏɴ: <b>{char['description']}</b>" if char.get('description') else ""

        caption = f"""🎊 ᴅᴀɪʟʏ ᴄʟᴀɪᴍ sᴜᴄᴄᴇss
💫 ᴄᴏɴɢʀᴀᴛs <a href='tg://user?id={user_id}'>{first_name}</a>
🎴 ɴᴀᴍᴇ: <b>{char.get('name', 'Unknown')}</b>
⭐ ʀᴀʀɪᴛʏ: <b>{char.get('rarity', 'Unknown')}</b>
🎯 ᴀɴɪᴍᴇ: <b>{char.get('anime', 'Unknown')}</b>
🆔 ɪᴅ: <code>{char.get('id', 'N/A')}</code>{event}{origin}{abilities}{description}
✨ ᴄᴏᴍᴇ ʙᴀᴄᴋ ɪɴ 24 ʜᴏᴜʀs"""

        await update.message.reply_photo(
            photo=char.get('img_url', 'https://i.imgur.com/placeholder.png'),
            caption=caption,
            parse_mode='HTML'
        )

    except Exception as e:
        LOGGER.error(f"[HCLAIM] Error: {e}")
        await update.message.reply_text("❌ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ")
    finally:
        claim_lock.pop(user_id, None)

application.add_handler(CommandHandler(['hclaim', 'claim'], hclaim, block=False))