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
UPDATE_CHANNEL = "@PICK_X_UPDATE" # Required Channel
LOG_GROUP_ID = -1003139865857     # Log Group ID
 
cooldowns = {'dice': {}, 'propose': {}} 

class Icons:
    SUCCESS = "✨"
    HEART = "💖"
    FAIL = "💔"
    DICE = "🎲"
    GOLD = "💰"
    TIME = "⏰"
    ID = "🆔"

# --- LOGGING SYSTEM ---
async def send_win_log(context: CallbackContext, user, char, method):
    """Sends a premium log to the specified group"""
    log_text = (
        f"<b>🏆 ɴᴇᴡ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴄʟᴀɪᴍᴇᴅ!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>👤 ᴜsᴇʀ:</b> <a href='tg://user?id={user.id}'>{user.first_name}</a>\n"
        f"<b>🆔 ᴜ-ɪᴅ:</b> <code>{user.id}</code>\n"
        f"<b>🕹️ ᴍᴇᴛʜᴏᴅ:</b> <code>/{method}</code>\n\n"
        f"<b>🌸 ɴᴀᴍᴇ:</b> {char['name']}\n"
        f"<b>💎 ʀᴀʀɪᴛʏ:</b> {char['rarity']}\n"
        f"<b>📅 ᴅᴀᴛᴇ:</b> {datetime.now().strftime('%d/%m/%Y | %H:%M')}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    try:
        await context.bot.send_photo(chat_id=LOG_GROUP_ID, photo=char['img_url'], caption=log_text, parse_mode='HTML')
    except Exception as e:
        print(f"Log Error: {e}")

# --- FORCE JOIN CHECK ---
async def is_user_joined(context: CallbackContext, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(UPDATE_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

# --- UTILS ---
def check_cooldown(user_id, cmd_type, cooldown_time): 
    if user_id in cooldowns[cmd_type]: 
        elapsed = time.time() - cooldowns[cmd_type][user_id] 
        if elapsed < cooldown_time: 
            return False, int(cooldown_time - elapsed) 
    cooldowns[cmd_type][user_id] = time.time() 
    return True, 0 

# --- UPDATED DICE COMMAND ---
async def dice_marry(update: Update, context: CallbackContext): 
    user = update.effective_user
    
    can_use, rem = check_cooldown(user.id, 'dice', DICE_COOLDOWN) 
    if not can_use: 
        return await update.message.reply_text(f"<b>{Icons.TIME} ᴄᴏᴏʟᴅᴏᴡɴ:</b> ᴡᴀɪᴛ <code>{rem//60}ᴍ {rem%60}s</code>", parse_mode='HTML') 

    dice_msg = await context.bot.send_dice(update.effective_chat.id, emoji='🎲') 
    val = dice_msg.dice.value 
    await asyncio.sleep(3.5) 

    if val in [1, 6]: 
        # Fetch character
        chars = await collection.aggregate([{'$match': {'rarity': {'$in': ['🟢 Common', '🟣 Rare', '🟡 Legendary']}}}, {'$sample': {'size': 1}}]).to_list(length=1) 
        if not chars: return
        
        char = chars[0]
        await user_collection.update_one({'id': user.id}, {'$push': {'characters': char}}, upsert=True)
        
        caption = (
            f"<b>{Icons.DICE} ᴅɪᴄᴇ ʀᴇsᴜʟᴛ: {val}</b>\n"
            f"<b>{Icons.SUCCESS} ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs <a href='tg://user?id={user.id}'>{user.first_name}</a>!</b>\n\n"
            f"<b>{char['name']}</b> ᴀᴄᴄᴇᴘᴛᴇᴅ ʏᴏᴜʀ ᴘʀᴏᴘᴏsᴀʟ!\n"
            f"<b>🌸 ɴᴀᴍᴇ:</b> <code>{char['name']}</code>\n"
            f"<b>💎 ʀᴀʀɪᴛʏ:</b> <code>{char['rarity']}</code>\n"
            f"<b>🎬 ᴀɴɪᴍᴇ:</b> <code>{char['anime']}</code>\n"
            f"<b>{Icons.ID} ɪᴅ:</b> <code>{char['id']}</code>\n\n"
            f"✨ ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ʜᴀʀᴇᴍ!"
        )
        await update.message.reply_photo(photo=char['img_url'], caption=caption, parse_mode='HTML')
        await send_win_log(context, user, char, "dice")
    else: 
        await update.message.reply_text(f"<b>{Icons.DICE} ᴅɪᴄᴇ ʀᴇsᴜʟᴛ: {val}</b>\n{Icons.FAIL} sʜᴇ ʀᴇᴊᴇᴄᴛᴇᴅ ʏᴏᴜ! ᴛʀʏ ᴀɢᴀɪɴ ɪɴ 30ᴍ.", parse_mode='HTML')

# --- UPDATED PROPOSE COMMAND ---
async def propose(update: Update, context: CallbackContext): 
    user = update.effective_user

    # Membership Lock
    if not await is_user_joined(context, user.id):
        btn = [[InlineKeyboardButton("📢 ᴊᴏɪɴ ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ", url="https://t.me/PICK_X_UPDATE")]]
        return await update.message.reply_text(
            f"<b>⚠️ ᴀᴄᴄᴇss ʟᴏᴄᴋᴇᴅ!</b>\n\nʏᴏᴜ ᴍᴜsᴛ ᴊᴏɪɴ ᴏᴜʀ ᴄʜᴀɴɴᴇʟ ᴛᴏ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.",
            reply_markup=InlineKeyboardMarkup(btn),
            parse_mode='HTML'
        )

    user_data = await user_collection.find_one({'id': user.id}) 
    if not user_data or user_data.get('balance', 0) < PROPOSAL_COST: 
        return await update.message.reply_text(f"<b>{Icons.GOLD} ɪɴsᴜғғɪᴄɪᴇɴᴛ ɢᴏʟᴅ!</b>\nɴᴇᴇᴅ: <code>{PROPOSAL_COST}</code>", parse_mode='HTML') 

    can_use, rem = check_cooldown(user.id, 'propose', PROPOSE_COOLDOWN) 
    if not can_use: 
        return await update.message.reply_text(f"<b>{Icons.TIME} ᴄᴏᴏʟᴅᴏᴡɴ:</b> <code>{rem//60}ᴍ {rem%60}s</code>", parse_mode='HTML') 

    # Deduction
    await user_collection.update_one({'id': user.id}, {'$inc': {'balance': -PROPOSAL_COST}}) 
    
    msg = await update.message.reply_text("<b>💍 ᴘʀᴏᴘᴏsɪɴɢ ᴛᴏ ʏᴏᴜʀ ʟᴏᴠᴇ...</b>", parse_mode='HTML')
    await asyncio.sleep(2) 

    if random.random() > 0.4: 
        await msg.edit_text(f"<b>{Icons.FAIL} sʜᴇ ʀᴇᴊᴇᴄᴛᴇᴅ ʏᴏᴜʀ ᴘʀᴏᴘᴏsᴀʟ!</b>", parse_mode='HTML')
    else: 
        chars = await collection.aggregate([{'$match': {'rarity': {'$in': ['💮 Special Edition', '💫 Neon', '✨ Manga', '🎐 Celestial']}}}, {'$sample': {'size': 1}}]).to_list(length=1) 
        if not chars:
            await user_collection.update_one({'id': user.id}, {'$inc': {'balance': PROPOSAL_COST}})
            return await msg.edit_text("<b>ɴᴏ ʀᴀʀᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs ғᴏᴜɴᴅ. ʀᴇғᴜɴᴅᴇᴅ!</b>")
        
        char = chars[0]
        await user_collection.update_one({'id': user.id}, {'$push': {'characters': char}}, upsert=True)
        await msg.delete()
        
        caption = (
            f"<b>{Icons.HEART} sʜᴇ sᴀɪᴅ ʏᴇs!</b>\n\n"
            f"<b>🌸 ɴᴀᴍᴇ:</b> <code>{char['name']}</code>\n"
            f"<b>💎 ʀᴀʀɪᴛʏ:</b> <code>{char['rarity']}</code>\n"
            f"<b>🎬 ᴀɴɪᴍᴇ:</b> <code>{char['anime']}</code>\n"
            f"<b>{Icons.ID} ɪᴅ:</b> <code>{char['id']}</code>\n\n"
            f"<b>✨ ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ʜᴀʀᴇᴍ!</b>"
        )
        await update.message.reply_photo(photo=char['img_url'], caption=caption, parse_mode='HTML')
        await send_win_log(context, user, char, "propose")

# --- HANDLERS ---
application.add_handler(CommandHandler(['dice', 'marry'], dice_marry, block=False)) 
application.add_handler(CommandHandler(['propose'], propose, block=False))
