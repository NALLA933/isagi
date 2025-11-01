import logging
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

LOGGER = logging.getLogger(__name__)

OWNER_ID = 5147822244

async def gstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in sudo_users and user_id != OWNER_ID:
        return
    
    try:
        total_users = await user_collection.count_documents({})
        total_chats = await top_global_groups_collection.count_documents({})
        banned_users_count = await BANNED_USERS.count_documents({})
        banned_groups_count = await banned_groups_collection.count_documents({})
        pm_users_count = await pm_users.count_documents({})
        
        stats_text = (
            f"ɢʟᴏʙᴀʟ sᴛᴀᴛɪsᴛɪᴄs\n\n"
            f"ᴛᴏᴛᴀʟ ᴜsᴇʀs: {total_users}\n"
            f"ᴛᴏᴛᴀʟ ᴄʜᴀᴛs: {total_chats}\n"
            f"ᴘᴍ ᴜsᴇʀs: {pm_users_count}\n"
            f"ʙᴀɴɴᴇᴅ ᴜsᴇʀs: {banned_users_count}\n"
            f"ʙᴀɴɴᴇᴅ ɢʀᴏᴜᴘs: {banned_groups_count}"
        )
        
        await update.message.reply_text(stats_text)
        
    except Exception as e:
        LOGGER.error(f"Error in gstats: {e}")
        await update.message.reply_text("ᴇʀʀᴏʀ ғᴇᴛᴄʜɪɴɢ sᴛᴀᴛs")

# Add this handler to your application application.add_handler(CommandHandler("gstats", gstats))