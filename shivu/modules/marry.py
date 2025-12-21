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
UPDATE_CHANNEL = "@PICK_X_UPDATE" # Channel Username
LOG_GROUP_ID = -1003139865857   # Log Group ID

cooldowns = {'dice': {}, 'propose': {}} 

# --- PREMIUM STYLES ---
class Icons:
    HEART = "💖"
    DICE = "🎲"
    GOLD = "💰"
    TIME = "⏰"
    JOIN = "📢"
    LOG = "📜"
    STAR = "✨"

# --- HELPER FUNCTIONS ---
async def is_user_joined(context: CallbackContext, user_id: int) -> bool:
    """Checks if user is in the required channel"""
    try:
        member = await context.bot.get_chat_member(UPDATE_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

async def send_win_log(context: CallbackContext, user, char, method):
    """Sends log to the specified group"""
    log_text = (
        f"<b>{Icons.LOG} ɴᴇᴡ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴄʟᴀɪᴍᴇᴅ!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>👤 ᴘʟᴀʏᴇʀ:</b> <a href='tg://user?id={user.id}'>{user.first_name}</a>\n"
        f"<b>🆔 ɪᴅ:</b> <code>{user.id}</code>\n"
        f"<b>🕹️ ᴍᴇᴛʜᴏᴅ:</b> <code>/{method}</code>\n\n"
        f"<b>🌸 ᴄʜᴀʀᴀᴄᴛᴇʀ:</b> {char['name']}\n"
        f"<b>💎 ʀᴀʀɪᴛʏ:</b> {char['rarity']}\n"
        f"<b>📅 ᴅᴀᴛᴇ:</b> {datetime.now().strftime('%d %b %Y')}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    try:
        await context.bot.send_photo(chat_id=LOG_GROUP_ID, photo=char['img_url'], caption=log_text, parse_mode='HTML')
    except Exception as e:
        print(f"Log Error: {e}")

def check_cooldown(user_id, cmd_type, cooldown_time): 
    if user_id in cooldowns[cmd_type]: 
        elapsed = time.time() - cooldowns[cmd_type][user_id] 
        if elapsed < cooldown_time: 
            return False, int(cooldown_time - elapsed) 
    cooldowns[cmd_type][user_id] = time.time() 
    return True, 0 

# --- COMMANDS ---

async def dice_marry(update: Update, context: CallbackContext): 
    user = update.effective_user
    
    can_use, rem = check_cooldown(user.id, 'dice', DICE_COOLDOWN) 
    if not can_use: 
        return await update.message.reply_text(f"<b>{Icons.TIME} ᴡᴀɪᴛ</b> <code>{rem//60}ᴍ {rem%60}s</code> <b>ʙᴇғᴏʀᴇ ʀᴏʟʟɪɴɢ ᴀɢᴀɪɴ!</b>", parse_mode='HTML') 

    dice_msg = await context.bot.send_dice(update.effective_chat.id, emoji='🎲') 
    val = dice_msg.dice.value 
    await asyncio.sleep(3.5) 

    if val in [1, 6]: 
        chars = await collection.aggregate([{'$match': {'rarity': {'$in': ['🟢 Common', '🟣 Rare']}}}, {'$sample': {'size': 1}}]).to_list(length=1) 
        if not chars: return 
        
        char = chars[0]
        await user_collection.update_one({'id': user.id}, {'$push': {'characters': char}}, upsert=True)
        
        caption = (
            f"<b>{Icons.DICE} ᴅɪᴄᴇ ʀᴇsᴜʟᴛ: {val}</b>\n\n"
            f"<b>{Icons.HEART} ᴄᴏɴɢʀᴀᴛs <a href='tg://user?id={user.id}'>{user.first_name}</a>!</b>\n"
            f"ʏᴏᴜ ᴡᴏɴ <b>{char['name']}</b>\n"
            f"ʀᴀʀɪᴛʏ: <code>{char['rarity']}</code>"
        )
        await update.message.reply_photo(photo=char['img_url'], caption=caption, parse_mode='HTML')
        await send_win_log(context, user, char, "dice")
    else: 
        await update.message.reply_text(f"<b>{Icons.DICE} ᴅɪᴄᴇ: {val}</b>\n{Icons.FAIL} sʜᴇ ʀᴇᴊᴇᴄᴛᴇᴅ ʏᴏᴜ! ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.", parse_mode='HTML')

async def propose(update: Update, context: CallbackContext): 
    user = update.effective_user

    # --- MEMBERSHIP CHECK ---
    if not await is_user_joined(context, user.id):
        btn = [[InlineKeyboardButton(f"{Icons.JOIN} ᴊᴏɪɴ ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ", url="https://t.me/PICK_X_UPDATE")]]
        return await update.message.reply_text(
            f"<b>⚠️ ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ!</b>\n\nʏᴏᴜ ᴍᴜsᴛ ᴊᴏɪɴ ᴏᴜʀ ᴄʜᴀɴɴᴇʟ ᴛᴏ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.",
            reply_markup=InlineKeyboardMarkup(btn),
            parse_mode='HTML'
        )

    user_data = await user_collection.find_one({'id': user.id}) 
    if not user_data or user_data.get('balance', 0) < PROPOSAL_COST: 
        return await update.message.reply_text(f"<b>{Icons.GOLD} ɪɴsᴜғғɪᴄɪᴇɴᴛ ɢᴏʟᴅ!</b>\nɴᴇᴇᴅ: <code>{PROPOSAL_COST}</code>", parse_mode='HTML') 

    can_use, rem = check_cooldown(user.id, 'propose', PROPOSE_COOLDOWN) 
    if not can_use: 
        return await update.message.reply_text(f"<b>{Icons.TIME} ᴄᴏᴏʟᴅᴏᴡɴ:</b> <code>{rem//60}ᴍ {rem%60}s</code>", parse_mode='HTML') 

    await user_collection.update_one({'id': user.id}, {'$inc': {'balance': -PROPOSAL_COST}}) 
    msg = await update.message.reply_text("<b>💍 ᴘʀᴏᴘᴏsɪɴɢ ᴡɪᴛʜ ʟᴏᴠᴇ...</b>", parse_mode='HTML')
    await asyncio.sleep(2) 

    if random.random() > 0.4: 
        await msg.edit_text(f"<b>{Icons.FAIL} sʜᴇ ʀᴇᴊᴇᴄᴛᴇᴅ ʏᴏᴜʀ ᴘʀᴏᴘᴏsᴀʟ!</b>", parse_mode='HTML')
    else: 
        chars = await collection.aggregate([{'$match': {'rarity': {'$in': ['💮 Special Edition', '💫 Neon', '✨ Manga']}}}, {'$sample': {'size': 1}}]).to_list(length=1) 
        if not chars: return
        
        char = chars[0]
        await user_collection.update_one({'id': user.id}, {'$push': {'characters': char}}, upsert=True)
        await msg.delete()
        
        caption = (
            f"<b>{Icons.HEART} sʜᴇ sᴀɪᴅ ʏᴇs!</b>\n\n"
            f"<b>🌸 ɴᴀᴍᴇ:</b> <code>{char['name']}</code>\n"
            f"<b>💎 ʀᴀʀɪᴛʏ:</b> {char['rarity']}\n"
            f"<b>🎬 ᴀɴɪᴍᴇ:</b> {char['anime']}\n\n"
            f"<b>✨ ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ʜᴀʀᴇᴍ!</b>"
        )
        await update.message.reply_photo(photo=char['img_url'], caption=caption, parse_mode='HTML')
        await send_win_log(context, user, char, "propose")

# --- HANDLERS ---
application.add_handler(CommandHandler(['dice', 'marry'], dice_marry, block=False)) 
application.add_handler(CommandHandler(['propose'], propose, block=False))
