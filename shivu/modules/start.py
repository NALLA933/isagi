import random
import asyncio
from html import escape
from datetime import datetime
from pymongo import UpdateOne
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, LinkPreviewOptions
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from shivu import application, SUPPORT_CHAT, BOT_USERNAME, LOGGER, user_collection, collection

# --- CONFIG & ASSETS ---
VIDEOS = [
    "https://files.catbox.moe/k3dhbe.mp4",
    "https://files.catbox.moe/iitev2.mp4",
    "https://files.catbox.moe/hs0e56.mp4"
]

REFERRER_REWARD = 1000
NEW_USER_BONUS = 500
DAILY_INVITE_GOAL = 3  # Task target

OWNERS = [{"name": "Thorfinn", "username": "ll_Thorfinn_ll"}]
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
    "celestial": "🎐 Celestial", "premium": "🔮 Premium", "mythic": "🏵 Mythic"
}

# --- HELPER FUNCTIONS ---
def get_video():
    return random.choice(VIDEOS)

def get_progress_bar(current, total):
    """Generates a visual progress bar"""
    percentage = min(current / total, 1)
    filled = int(percentage * 10)
    bar = "🟢" * filled + "⚪" * (10 - filled)
    return f"{bar} ({int(percentage*100)}%)"

# --- REWARD SYSTEM ---
async def give_milestone_reward(user_id: int, milestone: int, context: CallbackContext):
    try:
        reward = REFERRAL_MILESTONES[milestone]
        rarities = reward["rarity"]
        char_count = reward["characters"]
        
        # Performance: Bulk Fetch random characters
        chars_to_add = []
        for _ in range(char_count):
            char_cursor = collection.aggregate([
                {"$match": {"rarity": random.choice(rarities)}},
                {"$sample": {"size": 1}}
            ])
            char_list = await char_cursor.to_list(1)
            if char_list:
                chars_to_add.append(char_list[0])

        # Performance: Bulk Write for database efficiency
        ops = [UpdateOne({"id": user_id}, {"$inc": {"balance": reward["gold"]}})]
        for char in chars_to_add:
            ops.append(UpdateOne({"id": user_id}, {"$push": {"characters": char}}))
        
        await user_collection.bulk_write(ops)

        char_names = "\n".join([f"{HAREM_MODE_MAPPING.get(c['rarity'], '🟢')} {c['name']}" for c in chars_to_add])
        await context.bot.send_message(
            chat_id=user_id,
            text=f"<b>🏆 ᴍɪʟᴇsᴛᴏɴᴇ {milestone} ʀᴇᴀᴄʜᴇᴅ!</b>\n\n💰 Gold: +{reward['gold']:,}\n🎴 Characters Received:\n{char_names}",
            parse_mode='HTML'
        )
    except Exception as e:
        LOGGER.error(f"Reward Error: {e}")

async def process_referral(user_id, first_name, ref_id, context):
    try:
        if user_id == ref_id: return
        
        # Update Referrer & Task tracking
        today = datetime.now().strftime("%Y-%m-%d")
        await user_collection.update_one(
            {"id": ref_id},
            {
                "$inc": {"balance": REFERRER_REWARD, "referred_users": 1, "daily_tasks.invites": 1},
                "$push": {"invited_user_ids": user_id},
                "$set": {"last_invite_date": today}
            }
        )
        
        ref_data = await user_collection.find_one({"id": ref_id})
        count = ref_data.get('referred_users', 0)
        daily_count = ref_data.get('daily_tasks', {}).get('invites', 0)

        # Milestone Check
        if count in REFERRAL_MILESTONES:
            await give_milestone_reward(ref_id, count, context)

        # Success Message with Daily Task Progress
        task_info = f"\n🎯 Daily Task: {daily_count}/{DAILY_INVITE_GOAL}" if daily_count <= DAILY_INVITE_GOAL else ""
        await context.bot.send_message(
            chat_id=ref_id,
            text=f"<b>✨ ɴᴇᴡ ʀᴇғᴇʀʀᴀʟ sᴜᴄᴄᴇss!</b>\n\n<b>{escape(first_name)}</b> joined via your link.\n💰 Gold: +{REFERRER_REWARD}{task_info}",
            parse_mode='HTML'
        )
    except Exception as e:
        LOGGER.error(f"Referral Processing Error: {e}")

# --- COMMANDS ---
async def toprefer(update: Update, context: CallbackContext):
    """Referral Leaderboard"""
    cursor = user_collection.find().sort("referred_users", -1).limit(10)
    leaders = await cursor.to_list(10)
    
    text = "<b>🏆 ʀᴇғᴇʀʀᴀʟ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b>\n\n"
    for i, user in enumerate(leaders, 1):
        text += f"{i}. {escape(user.get('first_name'))[:15]} — <b>{user.get('referred_users', 0)}</b>\n"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='referral')]]))
    else:
        await update.message.reply_text(text, parse_mode='HTML')

async def start(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id
        first_name = update.effective_user.first_name
        user_data = await user_collection.find_one({"id": user_id})
        
        is_new = user_data is None
        if is_new:
            user_data = {"id": user_id, "first_name": first_name, "balance": 500, "referred_users": 0, "characters": [], "daily_tasks": {"invites": 0}}
            await user_collection.insert_one(user_data)
            if context.args and context.args[0].startswith('r_'):
                await process_referral(user_id, first_name, int(context.args[0][2:]), context)

        welcome_text = f"<b>ᴡᴇʟᴄᴏᴍᴇ {'ʙᴀᴄᴋ' if not is_new else ''}, {escape(first_name)}!</b>\n\nI spawn anime characters in your groups for you to collect!"
        
        keyboard = [
            [InlineKeyboardButton("ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ", url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
            [InlineKeyboardButton("ʜᴇʟᴘ", callback_data='help'), InlineKeyboardButton("ɪɴᴠɪᴛᴇ", callback_data='referral')]
        ]
        
        await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', link_preview_options=LinkPreviewOptions(url=get_video(), show_above_text=True))
    except Exception as e:
        LOGGER.error(f"Start Error: {e}")

# --- CALLBACK LOGIC ---
async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    try:
        await query.answer()
        user_id = query.from_user.id
        user_data = await user_collection.find_one({"id": user_id})

        if query.data == 'referral':
            count = user_data.get('referred_users', 0)
            link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
            next_m = next((m for m in sorted(REFERRAL_MILESTONES.keys()) if count < m), 100)
            
            # Progress Bar Implementation
            progress = get_progress_bar(count, next_m)
            
            text = f"<b>🎁 ɪɴᴠɪᴛᴇ & ᴇᴀʀɴ</b>\n\n<b>📊 Milestone Progress</b>\n{progress}\n🎯 Goal: {next_m} Refs\n\n<b>🔗 Referral Link</b>\n<code>{link}</code>"
            keyboard = [
                [InlineKeyboardButton("📤 sʜᴀʀᴇ", url=f"https://t.me/share/url?url={link}")],
                [InlineKeyboardButton("🏆 ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ", callback_data='toprefer')],
                [InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='back')]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

        elif query.data == 'toprefer':
            await toprefer(update, context)

        elif query.data == 'back':
            # Logic for main menu...
            pass

    except Exception as e:
        LOGGER.error(f"Callback Error: {e}")

# Register Handlers
application.add_handler(CommandHandler('start', start, block=False))
application.add_handler(CommandHandler('toprefer', toprefer, block=False))
application.add_handler(CallbackQueryHandler(button_callback, pattern='^(help|referral|toprefer|back)$', block=False))
