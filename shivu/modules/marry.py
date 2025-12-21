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
PROPOSE_SUCCESS_RATE = 1/6 # Half of Dice Marry (33% -> 16.6%)

# --- CUSTOM IMAGES ---
PROPOSE_IMAGES = ["https://files.catbox.moe/umb328.jpg", "https://files.catbox.moe/vaz41p.jpg"]
REJECT_IMAGES = ["https://files.catbox.moe/58ye4i.jpg", "https://files.catbox.moe/3m3um2.jpg"]

# Messages
SUCCESS_MSGS = ["ᴀᴄᴄᴇᴘᴛᴇᴅ ʏᴏᴜʀ ᴘʀᴏᴘᴏsᴀʟ", "sᴀɪᴅ ʏᴇs ᴛᴏ ʏᴏᴜʀ ʜᴇᴀʀᴛ", "ɪs ɴᴏᴡ ʏᴏᴜʀs ғᴏʀᴇᴠᴇʀ", "ᴊᴏɪɴᴇᴅ ʏᴏᴜʀ ʜᴀʀᴇᴍ", "ғᴇʟʟ ғᴏʀ ʏᴏᴜ"] 
FAIL_MSGS = ["sʜᴇ ʀᴇᴊᴇᴄᴛᴇᴅ ʏᴏᴜ ᴀɴᴅ ʀᴀɴ ᴀᴡᴀʏ", "sʜᴇ sᴀɪᴅ ɴᴏ ᴀɴᴅ ʟᴇғᴛ", "sʜᴇ ᴡᴀʟᴋᴇᴅ ᴀᴡᴀʏ ғʀᴏᴍ ʏᴏᴜ", "sʜᴇ ᴅɪsᴀᴘᴘᴇᴀʀᴇᴅ ɪɴ ᴛʜᴇ ᴡɪɴᴅ", "ʙᴇᴛᴛᴇʀ ʟᴜᴄᴋ ɴᴇxᴛ ᴛɪᴍᴇ"] 

cooldowns = {'dice': {}, 'propose': {}} 

# --- HELPER FUNCTIONS ---
def check_cooldown(user_id, cmd_type, cooldown_time): 
    try: 
        if user_id in cooldowns[cmd_type]: 
            elapsed = time.time() - cooldowns[cmd_type][user_id] 
            if elapsed < cooldown_time: 
                return False, int(cooldown_time - elapsed) 
        cooldowns[cmd_type][user_id] = time.time() 
        return True, 0 
    except: return True, 0 

async def is_user_joined(context: CallbackContext, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(UPDATE_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except: return False

async def get_unique_chars(user_id, rarities=None, count=1): 
    try: 
        rarities = rarities or ['🟢 Common', 'Purple Rare', 'Yellow Legendary'] 
        user_data = await user_collection.find_one({'id': user_id}) 
        claimed_ids = [c.get('id') for c in user_data.get('characters', [])] if user_data else [] 
        pipeline = [{'$match': {'rarity': {'$in': rarities}, 'id': {'$nin': claimed_ids}}}, {'$sample': {'size': count}}] 
        return await collection.aggregate(pipeline).to_list(length=None) 
    except: return [] 

async def add_char_to_user(user_id, username, first_name, char): 
    try: 
        await user_collection.update_one(
            {'id': user_id}, 
            {'$push': {'characters': char}, '$set': {'username': username, 'first_name': first_name}}, 
            upsert=True
        )
        return True
    except: return False

async def send_win_log(context: CallbackContext, user, char, method):
    log_text = (f"<b>🏆 ɴᴇᴡ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴄʟᴀɪᴍᴇᴅ!</b>\n━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>👤 ᴜsᴇʀ:</b> <a href='tg://user?id={user.id}'>{user.first_name}</a>\n"
                f"<b>🕹️ ᴍᴇᴛʜᴏᴅ:</b> <code>/{method}</code>\n"
                f"<b>🌸 ɴᴀᴍᴇ:</b> {char['name']}\n"
                f"<b>💎 ʀᴀʀɪᴛʏ:</b> <code>{char['rarity']}</code>\n━━━━━━━━━━━━━━━━━━━━")
    try: await context.bot.send_photo(chat_id=LOG_GROUP_ID, photo=char['img_url'], caption=log_text, parse_mode='HTML')
    except: pass

# --- DICE COMMAND ---
async def dice_marry(update: Update, context: CallbackContext): 
    user = update.effective_user
    can_use, rem = check_cooldown(user.id, 'dice', DICE_COOLDOWN) 
    if not can_use: return await update.message.reply_text(f"⏳ ᴡᴀɪᴛ <b>{rem//60}ᴍ {rem%60}s</b>", parse_mode='HTML') 
    
    dice_msg = await context.bot.send_dice(update.effective_chat.id, emoji='🎲') 
    val = dice_msg.dice.value 
    await asyncio.sleep(3.5) 

    if val in [1, 6]: 
        chars = await get_unique_chars(user.id) 
        if not chars: return await update.message.reply_text("ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴀᴠᴀɪʟᴀʙʟᴇ.")
        char = chars[0]
        await add_char_to_user(user.id, user.username, user.first_name, char)
        await update.message.reply_photo(photo=char['img_url'], caption=f"<b>🎲 ᴅɪᴄᴇ {val}: {char['name']} {random.choice(SUCCESS_MSGS)}!</b>", parse_mode='HTML')
        await send_win_log(context, user, char, "dice")
    else:
        await update.message.reply_text(f"🎲 ᴅɪᴄᴇ: {val}\n{random.choice(FAIL_MSGS)}", parse_mode='HTML')

# --- PROPOSE COMMAND ---
async def propose(update: Update, context: CallbackContext): 
    user = update.effective_user
    if not await is_user_joined(context, user.id):
        btn = [[InlineKeyboardButton("📢 ᴊᴏɪɴ ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ", url="https://t.me/PICK_X_UPDATE")]]
        return await update.message.reply_text(f"<b>⚠️ ᴀᴄᴄᴇss ʟᴏᴄᴋᴇᴅ!</b>\n\nᴊᴏɪɴ ᴏᴜʀ ᴄʜᴀɴɴᴇʟ ᴛᴏ ᴜsᴇ ᴛʜɪs.", reply_markup=InlineKeyboardMarkup(btn), parse_mode='HTML')

    user_data = await user_collection.find_one({'id': user.id}) 
    if not user_data or user_data.get('balance', 0) < PROPOSAL_COST: 
        return await update.message.reply_text("ʏᴏᴜ ɴᴇᴇᴅ ᴀᴛ ʟᴇᴀꜱᴛ 2000 ᴛᴏᴋᴇɴꜱ ᴛᴏ ᴘʀᴏᴘᴏꜱᴇ.", parse_mode='HTML') 

    can_use, rem = check_cooldown(user.id, 'propose', PROPOSE_COOLDOWN) 
    if not can_use: return await update.message.reply_text(f"⏳ ᴄᴏᴏʟᴅᴏᴡɴ: <code>{rem//60}ᴍ {rem%60}s</code>", parse_mode='HTML') 

    await user_collection.update_one({'id': user.id}, {'$inc': {'balance': -PROPOSAL_COST}}) 
    msg = await update.message.reply_photo(photo=random.choice(PROPOSE_IMAGES), caption="<b>💍 ᴘʀᴏᴘᴏsɪɴɢ...</b>", parse_mode='HTML')
    await asyncio.sleep(3) 

    if random.random() > PROPOSE_SUCCESS_RATE: 
        await msg.delete()
        await update.message.reply_photo(photo=random.choice(REJECT_IMAGES), caption=f"<b>💔 sʜᴇ ʀᴇᴊᴇᴄᴛᴇᴅ ʏᴏᴜ, {user.first_name}!</b>", parse_mode='HTML')
    else: 
        chars = await get_unique_chars(user.id, rarities=['💮 Special Edition', '💫 Neon', '✨ Manga', '🎐 Celestial']) 
        if not chars:
            await user_collection.update_one({'id': user.id}, {'$inc': {'balance': PROPOSAL_COST}})
            return await msg.edit_caption(caption="ʀᴇғᴜɴᴅᴇᴅ! ɴᴏ ʀᴀʀᴇ ᴄʜᴀʀs ʟᴇғᴛ.")
        char = chars[0]
        await add_char_to_user(user.id, user.username, user.first_name, char)
        await msg.delete()
        await update.message.reply_photo(photo=char['img_url'], caption=f"<b>💖 sʜᴇ sᴀɪᴅ ʏᴇs!\n\nɴᴀᴍᴇ: {char['name']}\nʀᴀʀɪᴛʏ: {char['rarity']}</b>", parse_mode='HTML')
        await send_win_log(context, user, char, "propose")

application.add_handler(CommandHandler(['dice', 'marry'], dice_marry, block=False)) 
application.add_handler(CommandHandler(['propose'], propose, block=False))
