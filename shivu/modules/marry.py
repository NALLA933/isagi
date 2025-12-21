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
UPDATE_CHANNEL = "@PICK_X_UPDATE" 
LOG_GROUP_ID = -1003139865857     

# --- SUCCESS RATE CALCULATION ---
# Marry (Dice) Chance: 2/6 = 33.33%
# Propose Chance (Half of Marry): 1/6 = 16.66%
PROPOSE_SUCCESS_RATE = 1/6 

PROPOSE_IMAGES = ["https://files.catbox.moe/umb328.jpg", "https://files.catbox.moe/vaz41p.jpg"]
REJECT_IMAGES = ["https://files.catbox.moe/58ye4i.jpg", "https://files.catbox.moe/3m3um2.jpg"]

cooldowns = {'dice': {}, 'propose': {}} 

async def is_user_joined(context: CallbackContext, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(UPDATE_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception: return False

async def send_win_log(context: CallbackContext, user, char, method):
    log_text = (
        f"<b>🏆 ɴᴇᴡ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴄʟᴀɪᴍᴇᴅ!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>👤 ᴜsᴇʀ:</b> <a href='tg://user?id={user.id}'>{user.first_name}</a>\n"
        f"<b>🕹️ ᴍᴇᴛʜᴏᴅ:</b> <code>/{method}</code>\n"
        f"<b>🌸 ɴᴀᴍᴇ:</b> {char['name']}\n"
        f"<b>💎 ʀᴀʀɪᴛʏ:</b> <code>{char['rarity']}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    try: await context.bot.send_photo(chat_id=LOG_GROUP_ID, photo=char['img_url'], caption=log_text, parse_mode='HTML')
    except: pass

# --- PROPOSE COMMAND (LOW CHANCE) ---
async def propose(update: Update, context: CallbackContext): 
    user = update.effective_user

    # 1. Force Join Check
    if not await is_user_joined(context, user.id):
        btn = [[InlineKeyboardButton("📢 ᴊᴏɪɴ ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ", url="https://t.me/PICK_X_UPDATE")]]
        return await update.message.reply_text(
            f"<b>⚠️ ᴀᴄᴄᴇss ʟᴏᴄᴋᴇᴅ!</b>\n\nʏᴏᴜ ᴍᴜsᴛ ᴊᴏɪɴ ᴏᴜʀ ᴄʜᴀɴɴᴇʟ ᴛᴏ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.",
            reply_markup=InlineKeyboardMarkup(btn), parse_mode='HTML'
        )

    user_data = await user_collection.find_one({'id': user.id}) 
    
    # 2. Token Check
    if not user_data or user_data.get('balance', 0) < PROPOSAL_COST: 
        return await update.message.reply_text("ʏᴏᴜ ɴᴇᴇᴅ ᴀᴛ ʟᴇᴀꜱᴛ 2000 ᴛᴏᴋᴇɴꜱ ᴛᴏ ᴘʀᴏᴘᴏꜱᴇ.", parse_mode='HTML') 

    # 3. Cooldown
    can_use, rem = int(time.time()), 0 # Placeholder for cooldown logic
    # (Yahan aapka purana check_cooldown function use hoga)

    await user_collection.update_one({'id': user.id}, {'$inc': {'balance': -PROPOSAL_COST}}) 
    
    p_img = random.choice(PROPOSE_IMAGES)
    msg = await update.message.reply_photo(photo=p_img, caption="<b>💍 ᴘʀᴏᴘᴏsɪɴɢ... ᴡɪʟʟ sʜᴇ ᴀᴄᴄᴇᴘᴛ?</b>", parse_mode='HTML')
    await asyncio.sleep(3) 

    # 4. REDUCED CHANCE LOGIC
    if random.random() > PROPOSE_SUCCESS_RATE: 
        r_img = random.choice(REJECT_IMAGES)
        await msg.delete()
        await update.message.reply_photo(
            photo=r_img, 
            caption=f"<b>💔 sʜᴇ ʀᴇᴊᴇᴄᴛᴇᴅ ʏᴏᴜ!</b>\nᴄʜᴀɴᴄᴇs ᴡᴇʀᴇ ʟᴏᴡ... ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ <a href='tg://user?id={user.id}'>{user.first_name}</a>.",
            parse_mode='HTML'
        )
    else: 
        target_rarities = ['💮 Special Edition', '💫 Neon', '✨ Manga', '🎐 Celestial']
        chars = await collection.aggregate([{'$match': {'rarity': {'$in': target_rarities}}}, {'$sample': {'size': 1}}]).to_list(length=1) 
        
        if not chars:
            await user_collection.update_one({'id': user.id}, {'$inc': {'balance': PROPOSAL_COST}})
            return await msg.edit_caption(caption="<b>ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ғᴏᴜɴᴅ. ʀᴇғᴜɴᴅᴇᴅ!</b>")
        
        char = chars[0]
        await user_collection.update_one({'id': user.id}, {'$push': {'characters': char}}, upsert=True)
        await msg.delete()
        
        caption = (
            f"<b>💖 sʜᴇ sᴀɪᴅ ʏᴇs! (ʀᴀʀᴇ ᴡɪɴ)</b>\n\n"
            f"<b>🌸 ɴᴀᴍᴇ:</b> <code>{char['name']}</code>\n"
            f"<b>💎 ʀᴀʀɪᴛʏ:</b> <code>{char['rarity']}</code>\n"
            f"<b>🎬 ᴀɴɪᴍᴇ:</b> <code>{char['anime']}</code>\n"
            f"<b>🆔 ɪᴅ:</b> <code>{char['id']}</code>\n\n"
            f"<b>✨ ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ʜᴀʀᴇᴍ!</b>"
        )
        await update.message.reply_photo(photo=char['img_url'], caption=caption, parse_mode='HTML')
        await send_win_log(context, user, char, "propose")

# Handler register karein
application.add_handler(CommandHandler(['propose'], propose, block=False))
