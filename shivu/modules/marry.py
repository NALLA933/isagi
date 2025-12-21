import asyncio 
import time 
import random 
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup 
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from telegram.error import TelegramError 
from shivu import application, user_collection, collection 

# --- CONFIGURATION ---
PROPOSAL_COST = 2000 
UPDATE_CHANNEL = "@PICK_X_UPDATE" # Ensure '@' is there
LOG_GROUP_ID = -1003139865857   

# --- LOGIC TO FIX ACCESS ISSUE ---
async def is_user_joined(context: CallbackContext, user_id: int) -> bool:
    try:
        # User ka exact status check karne ke liye
        member = await context.bot.get_chat_member(chat_id=UPDATE_CHANNEL, user_id=user_id)
        # Status list: member, administrator, creator
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except Exception as e:
        # Agar user channel mein kabhi gaya hi nahi toh error aayega
        print(f"Join Check Error: {e}")
        return False

# Join Button with Verify Callback
def get_join_markup():
    keyboard = [
        [InlineKeyboardButton("📢 ᴊᴏɪɴ ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ", url="https://t.me/PICK_X_UPDATE")],
        [InlineKeyboardButton("🔄 ᴠᴇʀɪғʏ ᴀᴄᴄᴇss", callback_data="verify_member")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- PROPOSE COMMAND ---
async def propose(update: Update, context: CallbackContext): 
    user = update.effective_user
    
    # Check membership
    if not await is_user_joined(context, user.id):
        return await update.message.reply_text(
            f"<b>❌ ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ!</b>\n\n"
            f"ʜᴇʟʟᴏ {user.first_name}, ᴀᴀᴘɴᴇ ᴀʙʜɪ ᴛᴀᴋ ᴄʜᴀɴɴᴇʟ ᴊᴏɪɴ ɴᴀʜɪ ᴋɪʏᴀ ʜᴀɪ.\n"
            f"ᴊᴏɪɴ ᴋᴀʀɴᴇ ᴋᴇ ʙᴀᴀᴅ ɴɪᴄʜᴇ ᴅɪʏᴇ ɢᴀʏᴇ <b>ᴠᴇʀɪғʏ</b> ʙᴜᴛᴛᴏɴ ᴘᴇ ᴄʟɪᴄᴋ ᴋᴀʀᴇɪɴ.",
            reply_markup=get_join_markup(),
            parse_mode='HTML'
        )

    # ... (Baki ka balance/cooldown logic same rahega) ...
    user_data = await user_collection.find_one({'id': user.id})
    if not user_data or user_data.get('balance', 0) < PROPOSAL_COST:
        return await update.message.reply_text("<b>💰 ɪɴsᴜғғɪᴄɪᴇɴᴛ ɢᴏʟᴅ!</b>", parse_mode='HTML')

    await user_collection.update_one({'id': user.id}, {'$inc': {'balance': -PROPOSAL_COST}})
    msg = await update.message.reply_text("<b>💍 ᴘʀᴏᴘᴏsɪɴɢ...</b>")
    await asyncio.sleep(2)

    # Win/Loss Logic
    if random.random() > 0.4:
        await msg.edit_text("<b>💔 sʜᴇ ʀᴇᴊᴇᴄᴛᴇᴅ ʏᴏᴜ!</b>")
    else:
        # Success logic & log system
        chars = await collection.aggregate([{'$sample': {'size': 1}}]).to_list(length=1)
        char = chars[0]
        await user_collection.update_one({'id': user.id}, {'$push': {'characters': char}})
        await msg.delete()
        await update.message.reply_photo(photo=char['img_url'], caption="<b>💖 sʜᴇ sᴀɪᴅ ʏᴇs!</b>", parse_mode='HTML')

# --- CALLBACK FOR VERIFY BUTTON ---
async def verify_user(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    if await is_user_joined(context, user_id):
        await query.answer("✅ ᴀᴄᴄᴇss ɢʀᴀɴᴛᴇᴅ! ɴᴏᴡ ʏᴏᴜ ᴄᴀɴ ᴜsᴇ /propose", show_alert=True)
        await query.message.delete()
    else:
        await query.answer("❌ ᴀᴀᴘɴᴇ ᴀʙʜɪ ᴛᴀᴋ ᴊᴏɪɴ ɴᴀʜɪ ᴋɪʏᴀ ʜᴀɪ!", show_alert=True)

# Register handlers
application.add_handler(CommandHandler('propose', propose, block=False))
application.add_handler(CallbackQueryHandler(verify_user, pattern="^verify_member$"))
