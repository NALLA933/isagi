import random
import time
import asyncio
from html import escape
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, LinkPreviewOptions
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from shivu import application, SUPPORT_CHAT, BOT_USERNAME, LOGGER, user_collection, collection
from shivu.modules.chatlog import track_bot_start
from shivu.modules.database.sudo import fetch_sudo_users
from pymongo import UpdateOne

# --- ASSETS ---
VIDEOS = [
    "https://files.catbox.moe/k3dhbe.mp4",
    "https://files.catbox.moe/iitev2.mp4",
    "https://files.catbox.moe/hs0e56.mp4"
]

def get_random_video():
    return random.choice(VIDEOS)

REFERRER_REWARD = 1000
NEW_USER_BONUS = 500

REFERRAL_MILESTONES = {
    5: {"gold": 5000, "characters": 1, "rarity": ["common", "rare"]},
    10: {"gold": 15000, "characters": 2, "rarity": ["rare", "legendary"]},
    25: {"gold": 40000, "characters": 3, "rarity": ["legendary", "special", "neon"]},
    50: {"gold": 100000, "characters": 5, "rarity": ["special", "neon", "manga", "celestial"]},
    100: {"gold": 250000, "characters": 10, "rarity": ["celestial", "premium", "mythic"]}
}

HAREM_MODE_MAPPING = {
    "common": "🟢 Common", "rare": "🟣 Rare", "legendary": "🟡 Legendary",
    "special": "💮 Special", "neon": "💫 Neon", "manga": "✨ Manga",
    "cosplay": "🎭 Cosplay", "celestial": "🎐 Celestial", "premium": "🔮 Premium",
    "erotic": "💋 Erotic", "summer": "🌤 Summer", "winter": "☃️ Winter",
    "monsoon": "☔️ Monsoon", "valentine": "💝 Valentine", "halloween": "🎃 Halloween",
    "christmas": "🎄 Christmas", "mythic": "🏵 Mythic", "events": "🎗 Events",
    "amv": "🎥 AMV", "tiny": "👼 Tiny"
}

# --- NEW: PROGRESS BAR HELPER ---
def get_progress_bar(current, total):
    percent = min(current / total, 1.0)
    filled = int(10 * percent)
    bar = '▰' * filled + '▱' * (10 - filled)
    return f"{bar} {int(percent * 100)}%"

# --- UPGRADED: MILESTONE REWARD (BULK WRITE) ---
async def give_milestone_reward(user_id: int, milestone: int, context: CallbackContext) -> bool:
    try:
        reward = REFERRAL_MILESTONES[milestone]
        gold = reward["gold"]
        char_count = reward["characters"]
        rarities = reward["rarity"]

        # Bulk write performance ke liye
        bulk_ops = [UpdateOne({"id": user_id}, {"$inc": {"balance": gold}})]
        
        characters_received = []
        for _ in range(char_count):
            rarity = random.choice(rarities)
            char_cursor = collection.aggregate([{"$match": {"rarity": rarity}}, {"$sample": {"size": 1}}])
            char_list = await char_cursor.to_list(1)
            if char_list:
                character = char_list[0]
                characters_received.append(character)
                bulk_ops.append(UpdateOne({"id": user_id}, {"$push": {"characters": character}}))

        await user_collection.bulk_write(bulk_ops)

        char_list_text = "\n".join([f"{HAREM_MODE_MAPPING.get(c.get('rarity', 'common'), '🟢')} {c.get('name', 'Unknown')}" for c in characters_received])
        
        msg = f"<b>🎉 ᴍɪʟᴇsᴛᴏɴᴇ ʀᴇᴀᴄʜᴇᴅ: {milestone}</b>\n\n💰 ɢᴏʟᴅ: <code>{gold:,}</code>\n🎴 ᴄʜᴀʀᴀᴄᴛᴇʀs: <code>{char_count}</code>\n\n<b>ᴄʜᴀʀᴀᴄᴛᴇʀs ʀᴇᴄᴇɪᴠᴇᴅ:</b>\n{char_list_text}"
        await context.bot.send_message(chat_id=user_id, text=msg, parse_mode='HTML', link_preview_options=LinkPreviewOptions(url=get_random_video(), show_above_text=True))
        return True
    except Exception as e:
        LOGGER.error(f"Error in milestone: {e}")
        return False

# --- ORIGINAL START LOGIC WITH TASK UPGRADE ---
async def start(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id
        first_name = update.effective_user.first_name or "User"
        username = update.effective_user.username or ""
        args = context.args

        user_data = await user_collection.find_one({"id": user_id})
        is_new_user = user_data is None

        if is_new_user:
            # Referral logic within start
            referring_user_id = None
            if args and args[0].startswith('r_'):
                try:
                    referring_user_id = int(args[0][2:])
                except: pass

            new_user = {
                "id": user_id, "first_name": first_name, "username": username,
                "balance": 500, "characters": [], "referred_users": 0,
                "referred_by": referring_user_id, "invited_user_ids": [],
                "pass_data": {"tasks": {"invites": 0, "daily_reset": datetime.utcnow()}}
            }
            await user_collection.insert_one(new_user)
            user_data = new_user

            if referring_user_id and referring_user_id != user_id:
                # Update referrer & check milestone
                ref_user = await user_collection.find_one({"id": referring_user_id})
                if ref_user:
                    old_count = ref_user.get('referred_users', 0)
                    new_count = old_count + 1
                    await user_collection.update_one(
                        {"id": referring_user_id},
                        {"$inc": {"balance": REFERRER_REWARD, "referred_users": 1, "pass_data.tasks.invites": 1},
                         "$push": {"invited_user_ids": user_id}}
                    )
                    if new_count in REFERRAL_MILESTONES:
                        await give_milestone_reward(referring_user_id, new_count, context)

        # UI Stats
        balance = user_data.get('balance', 0)
        chars = len(user_data.get('characters', []))
        refs = user_data.get('referred_users', 0)

        caption = f"<b>ᴡᴇʟᴄᴏᴍᴇ {'ʙᴀᴄᴋ' if not is_new_user else ''}</b>\n\nɪ ᴀᴍ ᴘɪᴄᴋ ᴄᴀᴛᴄʜᴇʀ...\n\n💰 ɢᴏʟᴅ: <b>{balance:,}</b>\n🎴 ᴄʜᴀʀᴀᴄᴛᴇʀs: <b>{chars}</b>\n👥 ʀᴇғᴇʀʀᴀʟs: <b>{refs}</b>"
        
        keyboard = [
            [InlineKeyboardButton("ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ", url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
            [InlineKeyboardButton("ʜᴇʟᴘ", callback_data='help'), InlineKeyboardButton("ɪɴᴠɪᴛᴇ", callback_data='referral')],
            [InlineKeyboardButton("🏆 ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ", callback_data='top_refer'), InlineKeyboardButton("ᴄʀᴇᴅɪᴛs", callback_data='credits')]
        ]

        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', 
                                      link_preview_options=LinkPreviewOptions(url=get_random_video(), show_above_text=True))
    except Exception as e:
        LOGGER.error(f"Error in start: {e}")

# --- NEW: REFERRAL LEADERBOARD ---
async def show_top_refer(update: Update, context: CallbackContext):
    query = update.callback_query
    top_cursor = user_collection.find().sort("referred_users", -1).limit(10)
    top_users = await top_cursor.to_list(10)
    
    msg = "<b>🏆 ᴛᴏᴘ ʀᴇғᴇʀʀᴇʀs</b>\n\n"
    for i, user in enumerate(top_users, 1):
        msg += f"{i}. {escape(user.get('first_name', 'User'))} — <code>{user.get('referred_users', 0)}</code>\n"
    
    kb = [[InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='referral')]]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

# --- CALLBACK HANDLER (FIXED BACK BUTTON & INDENTATION) ---
async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        await query.answer()
        user_data = await user_collection.find_one({"id": user_id})
        video_url = get_random_video()

        if query.data == 'referral':
            count = user_data.get('referred_users', 0)
            next_m = next((m for m in sorted(REFERRAL_MILESTONES.keys()) if count < m), 100)
            prog = get_progress_bar(count, next_m)
            
            # Task status
            daily_invs = user_data.get('pass_data', {}).get('tasks', {}).get('invites', 0)
            task_text = "✅ Done" if daily_invs >= 3 else f"⏳ {daily_invs}/3"

            text = f"""<b>🎁 ɪɴᴠɪᴛᴇ & ᴇᴀʀɴ</b>
            
<b>📊 ʏᴏᴜʀ ᴘʀᴏɢʀᴇss (Next: {next_m}):</b>
{prog}

<b>📅 ᴅᴀɪʟʏ ɪɴᴠɪᴛᴇ ᴛᴀsᴋ:</b>
Invite 3 users: {task_status}

👥 ᴛᴏᴛᴀʟ ɪɴᴠɪᴛᴇᴅ: <b>{count}</b>
💰 ᴇᴀʀɴᴇᴅ: <b>{count * REFERRER_REWARD:,}</b>

🔗 <code>https://t.me/{BOT_USERNAME}?start=r_{user_id}</code>"""
            
            kb = [
                [InlineKeyboardButton("📤 sʜᴀʀᴇ", url=f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME}?start=r_{user_id}")],
                [InlineKeyboardButton("🏆 ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ", callback_data='top_refer')],
                [InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='back')]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

        elif query.data == 'top_refer':
            await show_top_refer(update, context)

        elif query.data == 'back':
            # Yahan se back button main menu par le jayega
            balance = user_data.get('balance', 0)
            chars = len(user_data.get('characters', []))
            refs = user_data.get('referred_users', 0)
            caption = f"<b>ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ</b>\n\n💰 ɢᴏʟᴅ: <b>{balance:,}</b>\n🎴 ᴄʜᴀʀᴀᴄᴛᴇʀs: <b>{chars}</b>\n👥 ʀᴇғᴇʀʀᴀʟs: <b>{refs}</b>"
            keyboard = [
                [InlineKeyboardButton("ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ", url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
                [InlineKeyboardButton("ʜᴇʟᴘ", callback_data='help'), InlineKeyboardButton("ɪɴᴠɪᴛᴇ", callback_data='referral')],
                [InlineKeyboardButton("🏆 ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ", callback_data='top_refer'), InlineKeyboardButton("ᴄʀᴇᴅɪᴛs", callback_data='credits')]
            ]
            await query.edit_message_text(caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

        # Add help/credits handling as per your original code...
        elif query.data == 'help':
             # (Aapka original help text)
             pass

    except Exception as e:
        LOGGER.error(f"Callback Error: {e}")

# --- HANDLERS ---
application.add_handler(CommandHandler('start', start, block=False))
application.add_handler(CallbackQueryHandler(button_callback, pattern='^(help|referral|credits|back|top_refer)$', block=False))
