import random
import time
import asyncio
from html import escape
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, LinkPreviewOptions
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from pymongo import UpdateOne
from shivu import application, SUPPORT_CHAT, BOT_USERNAME, LOGGER, user_collection, collection

# --- CONFIG & ASSETS ---
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
    "celestial": "🎐 Celestial", "premium": "🔮 Premium", "mythic": "🏵 Mythic"
}

# --- HELPERS ---
def get_progress_bar(current, total):
    percent = min(current / total, 1.0)
    filled_length = int(10 * percent)
    bar = '▰' * filled_length + '▱' * (10 - filled_length)
    return f"{bar} {int(percent * 100)}%"

# --- REWARD SYSTEM (BULK UPDATES) ---
async def give_milestone_reward(user_id: int, milestone: int, context: CallbackContext):
    try:
        reward = REFERRAL_MILESTONES[milestone]
        rarities = reward["rarity"]
        
        # Get random characters based on count
        char_cursor = collection.aggregate([
            {"$match": {"rarity": {"$in": rarities}}},
            {"$sample": {"size": reward["characters"]}}
        ])
        chars_to_give = await char_cursor.to_list(None)

        # Bulk Update for Efficiency
        bulk_ops = [UpdateOne({"id": user_id}, {"$inc": {"balance": reward["gold"]}})]
        for char in chars_to_give:
            bulk_ops.append(UpdateOne({"id": user_id}, {"$push": {"characters": char}}))
        
        await user_collection.bulk_write(bulk_ops)

        char_text = "\n".join([f"{HAREM_MODE_MAPPING.get(c['rarity'], '⚪')} {c['name']}" for c in chars_to_give])
        msg = f"<b>🎉 ᴍɪʟᴇsᴛᴏɴᴇ {milestone} ʀᴇᴀᴄʜᴇᴅ!</b>\n\n💰 +{reward['gold']:,} Gold\n🎴 {reward['characters']} Characters:\n{char_text}"
        
        await context.bot.send_message(user_id, msg, parse_mode='HTML', 
                                       link_preview_options=LinkPreviewOptions(url=get_random_video(), show_above_text=True))
    except Exception as e:
        LOGGER.error(f"Milestone Error: {e}")

# --- COMMANDS ---
async def start(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id
        first_name = update.effective_user.first_name
        args = context.args

        user_data = await user_collection.find_one({"id": user_id})
        is_new = user_data is None

        if is_new:
            # Referral Logic
            ref_by = None
            if args and args[0].startswith('r_'):
                ref_by = int(args[0][2:])
                if ref_by != user_id:
                    # Update Referrer
                    ref_user = await user_collection.find_one({"id": ref_by})
                    if ref_user:
                        new_count = ref_user.get('referred_users', 0) + 1
                        await user_collection.update_one(
                            {"id": ref_by},
                            {"$inc": {"referred_users": 1, "balance": REFERRER_REWARD, "daily_tasks.invites": 1},
                             "$push": {"invited_user_ids": user_id}}
                        )
                        # Check Milestone
                        if new_count in REFERRAL_MILESTONES:
                            await give_milestone_reward(ref_by, new_count, context)

            # Insert New User
            user_data = {
                "id": user_id, "first_name": first_name, "balance": NEW_USER_BONUS,
                "referred_users": 0, "referred_by": ref_by, "characters": [],
                "daily_tasks": {"invites": 0, "last_reset": datetime.utcnow()}
            }
            await user_collection.insert_one(user_data)

        # Welcome Message (Standardized UI)
        caption = f"<b>ᴡᴇʟᴄᴏᴍᴇ {'ʙᴀᴄᴋ' if not is_new else ''}</b>\n\n💰 Gold: {user_data.get('balance', 0):,}\n👥 Refs: {user_data.get('referred_users', 0)}"
        keyboard = [[InlineKeyboardButton("ɪɴᴠɪᴛᴇ", callback_data='referral'), InlineKeyboardButton("🏆 ᴛᴏᴘ", callback_data='top_refer')]]
        
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML',
                                      link_preview_options=LinkPreviewOptions(url=get_random_video(), show_above_text=True))
    except Exception as e:
        LOGGER.error(f"Start Error: {e}")

async def referral_menu(update: Update, context: CallbackContext, is_callback=False):
    user_id = update.effective_user.id
    user = await user_collection.find_one({"id": user_id})
    count = user.get('referred_users', 0)
    
    # Dynamic Progress Bar
    next_m = next((m for m in sorted(REFERRAL_MILESTONES.keys()) if count < m), 100)
    prog_bar = get_progress_bar(count, next_m)
    
    # Daily Task (Invite 3)
    task_count = user.get('daily_tasks', {}).get('invites', 0)
    task_status = "✅ Done" if task_count >= 3 else f"⏳ {task_count}/3"

    text = f"""<b>🎁 ʀᴇғᴇʀʀᴀʟ ᴅᴀsʜʙᴏᴀʀᴅ</b>
    
<b>📊 ᴘʀᴏɢʀᴇss ᴛᴏ {next_m} ʀᴇғs:</b>
{prog_bar}

<b>📅 ᴅᴀɪʟʏ ᴛᴀsᴋ:</b>
Invite 3 friends: {task_status}
<i>(Get Special Event Box on completion)</i>

<b>🔗 ʏᴏᴜʀ ʟɪɴᴋ:</b>
<code>https://t.me/{BOT_USERNAME}?start=r_{user_id}</code>"""

    kb = [[InlineKeyboardButton("🏆 Leaderboard", callback_data='top_refer')],
          [InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='back')]]
    
    if is_callback:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

# --- LEADERBOARD ---
async def top_referral(update: Update, context: CallbackContext):
    query = update.callback_query
    cursor = user_collection.find().sort("referred_users", -1).limit(10)
    top_list = await cursor.to_list(length=10)
    
    text = "<b>🏆 ʀᴇғᴇʀʀᴀʟ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b>\n\n"
    for i, user in enumerate(top_list, 1):
        name = escape(user.get('first_name', 'Unknown'))
        text += f"{i}. {name} — <b>{user.get('referred_users', 0)}</b> refs\n"
    
    kb = [[InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='referral')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

# --- MAIN CALLBACK HANDLER (FIXED INDENTATION) ---
async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    
    try: # Bada Try Block for safety
        await query.answer()
        user_id = query.from_user.id
        
        if data == 'referral':
            await referral_menu(update, context, is_callback=True)
        elif data == 'top_refer':
            await top_referral(update, context)
        elif data == 'back':
            # Redirect to start or main menu logic
            pass 
            
    except Exception as e:
        LOGGER.error(f"Callback Error: {e}")
        await query.answer("⚠️ Session Expired", show_alert=True)

# --- HANDLERS ---
application.add_handler(CommandHandler('start', start, block=False))
application.add_handler(CommandHandler('refer', referral_menu, block=False))
application.add_handler(CallbackQueryHandler(button_callback, pattern='^(referral|top_refer|back)$', block=False))
