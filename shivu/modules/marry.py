import asyncio 
import time 
import random 
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup 
from telegram.ext import CommandHandler, CallbackContext 
from telegram.error import TelegramError 
from shivu import application, user_collection, collection 
 
# --- CONFIGURATION ---
PROPOSAL_COST = 2000 
DICE_COOLDOWN = 1800  
PROPOSE_COOLDOWN = 300  
UPDATE_CHANNEL_USERNAME = "PICK_X_UPDATE"  # Required Channel
LOG_GROUP_ID = -1003139865857 # Log Group ID
 
cooldowns = {'dice': {}, 'propose': {}} 

class Icons:
    SUCCESS = "💖"
    FAIL = "💔"
    DICE = "🎲"
    GOLD = "💰"
    TIME = "⏰"
    STAR = "✨"

# --- LOGGING SYSTEM ---
async def send_log(context: CallbackContext, user_id, first_name, char, cmd_name):
    """Sends a log of the win to the specified group"""
    try:
        log_text = (
            f"<b>#NEW_WIN 🏆</b>\n\n"
            f"<b>👤 ᴜsᴇʀ:</b> <a href='tg://user?id={user_id}'>{first_name}</a>\n"
            f"<b>🆔 ɪᴅ:</b> <code>{user_id}</code>\n"
            f"<b>🕹️ ᴄᴏᴍᴍᴀɴᴅ:</b> /{cmd_name}\n"
            f"<b>🌸 ᴄʜᴀʀᴀᴄᴛᴇʀ:</b> {char['name']}\n"
            f"<b>💎 ʀᴀʀɪᴛʏ:</b> {char['rarity']}\n"
            f"<b>📅 ᴅᴀᴛᴇ:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        await context.bot.send_photo(
            chat_id=LOG_GROUP_ID,
            photo=char['img_url'],
            caption=log_text,
            parse_mode='HTML'
        )
    except Exception as e:
        print(f"Log Error: {e}")

# --- CHANNEL JOIN CHECK ---
async def is_user_joined(context: CallbackContext, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(f"@{UPDATE_CHANNEL_USERNAME}", user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

# --- UI HELPERS ---
def get_join_button():
    keyboard = [[InlineKeyboardButton("📢 ᴊᴏɪɴ ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ", url=f"https://t.me/{UPDATE_CHANNEL_USERNAME}")]]
    return InlineKeyboardMarkup(keyboard)

def check_cooldown(user_id, cmd_type, cooldown_time): 
    if user_id in cooldowns[cmd_type]: 
        elapsed = time.time() - cooldowns[cmd_type][user_id] 
        if elapsed < cooldown_time: 
            return False, int(cooldown_time - elapsed) 
    cooldowns[cmd_type][user_id] = time.time() 
    return True, 0 

# --- CORE LOGIC ---
async def get_unique_chars(user_id, rarities=None, count=1): 
    rarities = rarities or ['🟢 Common', '🟣 Rare', '🟡 Legendary'] 
    user_data = await user_collection.find_one({'id': user_id}) 
    claimed_ids = [c.get('id') for c in user_data.get('characters', [])] if user_data else [] 
    pipeline = [{'$match': {'rarity': {'$in': rarities}, 'id': {'$nin': claimed_ids}}}, {'$sample': {'size': count}}] 
    return await collection.aggregate(pipeline).to_list(length=None) 

async def add_char_to_user(user_id, username, first_name, char): 
    await user_collection.update_one( 
        {'id': user_id}, 
        {'$push': {'characters': char}, '$set': {'username': username, 'first_name': first_name}},
        upsert=True
    ) 
    return True

# --- COMMANDS ---
async def dice_marry(update: Update, context: CallbackContext): 
    user = update.effective_user
    can_use, rem = check_cooldown(user.id, 'dice', DICE_COOLDOWN) 
    if not can_use: 
        return await update.message.reply_text(f"<b>{Icons.TIME} ᴄᴏᴏʟᴅᴏᴡɴ:</b> ᴡᴀɪᴛ <code>{rem//60}ᴍ {rem%60}s</code>", parse_mode='HTML') 

    dice_msg = await context.bot.send_dice(update.effective_chat.id, emoji='🎲') 
    dice_val = dice_msg.dice.value 
    await asyncio.sleep(3) 

    if dice_val in [1, 6]: 
        chars = await get_unique_chars(user.id) 
        if not chars: return await update.message.reply_text("<b>ɴᴏ ᴀᴠᴀɪʟᴀʙʟᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs!</b>", parse_mode='HTML') 
        
        char = chars[0] 
        await add_char_to_user(user.id, user.username, user.first_name, char) 
        
        caption = (
            f"<b>{Icons.DICE} ᴅɪᴄᴇ ʀᴇsᴜʟᴛ: {dice_val}</b>\n"
            f"<b>{Icons.SUCCESS} ᴄᴏɴɢʀᴀᴛs <a href='tg://user?id={user.id}'>{user.first_name}</a>!</b>\n\n"
            f"🌸 ɴᴀᴍᴇ: <b>{char['name']}</b>\n"
            f"💎 ʀᴀʀɪᴛʏ: <b>{char['rarity']}</b>\n"
            f"🎬 ᴀɴɪᴍᴇ: <b>{char['anime']}</b>\n"
            f"🆔 ɪᴅ: <code>{char['id']}</code>\n\n"
            f"✨ ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ʜᴀʀᴇᴍ!"
        )
        await update.message.reply_photo(photo=char['img_url'], caption=caption, parse_mode='HTML')
        await send_log(context, user.id, user.first_name, char, "dice")
    else: 
        await update.message.reply_text(f"<b>{Icons.FAIL} sʜᴇ ʀᴇᴊᴇᴄᴛᴇᴅ ʏᴏᴜ!</b>\nᴅɪᴄᴇ ʀᴇsᴜʟᴛ: <b>{dice_val}</b>\nɴᴇᴇᴅᴇᴅ: <b>1</b> ᴏʀ <b>6</b>", parse_mode='HTML') 

async def propose(update: Update, context: CallbackContext): 
    user = update.effective_user
    
    # Channel Join Check
    if not await is_user_joined(context, user.id):
        return await update.message.reply_text(
            f"<b>❌ ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ!</b>\n\nʏᴏᴜ ᴍᴜsᴛ ᴊᴏɪɴ ᴏᴜʀ ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ ᴛᴏ ᴜsᴇ ᴘʀᴏᴘᴏsᴇ ᴄᴏᴍᴍᴀɴᴅ.",
            reply_markup=get_join_button(),
            parse_mode='HTML'
        )

    user_data = await user_collection.find_one({'id': user.id}) 
    if not user_data or user_data.get('balance', 0) < PROPOSAL_COST: 
        return await update.message.reply_text(f"<b>{Icons.GOLD} ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ!</b>\nɴᴇᴇᴅ: <code>{PROPOSAL_COST}</code>", parse_mode='HTML') 

    can_use, rem = check_cooldown(user.id, 'propose', PROPOSE_COOLDOWN) 
    if not can_use: 
        return await update.message.reply_text(f"<b>{Icons.TIME} ᴄᴏᴏʟᴅᴏᴡɴ:</b> <code>{rem//60}ᴍ {rem%60}s</code>", parse_mode='HTML') 

    await user_collection.update_one({'id': user.id}, {'$inc': {'balance': -PROPOSAL_COST}}) 
    msg = await update.message.reply_text("<b>💍 ᴘʀᴏᴘᴏsɪɴɢ ᴛᴏ ᴛʜᴇ ʙᴇsᴛ ᴄʜᴀʀᴀᴄᴛᴇʀ...</b>", parse_mode='HTML')
    await asyncio.sleep(2) 

    if random.random() > 0.4: 
        await msg.edit_text(f"<b>{Icons.FAIL} sʜᴇ ʀᴇᴊᴇᴄᴛᴇᴅ ʏᴏᴜʀ ᴘʀᴏᴘᴏsᴀʟ ᴀɴᴅ ʀᴀɴ ᴀᴡᴀʏ!</b>", parse_mode='HTML')
    else: 
        chars = await get_unique_chars(user.id, rarities=['💮 Special Edition', '💫 Neon', '✨ Manga', '🎐 Celestial']) 
        if not chars: 
            await user_collection.update_one({'id': user.id}, {'$inc': {'balance': PROPOSAL_COST}}) 
            return await msg.edit_text("<b>ɴᴏ ʀᴀʀᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs ғᴏᴜɴᴅ. ʀᴇғᴜɴᴅᴇᴅ!</b>") 

        char = chars[0] 
        await add_char_to_user(user.id, user.username, user.first_name, char) 
        await msg.delete()
        
        caption = (
            f"<b>{Icons.SUCCESS} sʜᴇ sᴀɪᴅ ʏᴇs!</b>\n\n"
            f"🌸 ɴᴀᴍᴇ: <b>{char['name']}</b>\n"
            f"💎 ʀᴀʀɪᴛʏ: <b>{char['rarity']}</b>\n"
            f"🎬 ᴀɴɪᴍᴇ: <b>{char['anime']}</b>\n"
            f"🆔 ɪᴅ: <code>{char['id']}</code>\n\n"
            f"✨ ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ʟᴇɢᴇɴᴅᴀʀʏ ʜᴀʀᴇᴍ!"
        )
        await update.message.reply_photo(photo=char['img_url'], caption=caption, parse_mode='HTML')
        await send_log(context, user.id, user.first_name, char, "propose")

# --- HANDLERS ---
application.add_handler(CommandHandler(['dice', 'marry'], dice_marry, block=False)) 
application.add_handler(CommandHandler(['propose'], propose, block=False))
