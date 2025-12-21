import asyncio
from dataclasses import dataclass
from html import escape
from datetime import datetime
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from shivu import application, user_collection

# Configuration
OWNER_ID = 5147822244
LOG_GROUP_ID = -1002956939145  # Aapka Log Group

@dataclass
class UserTarget:
    id: int
    username: str | None = None
    first_name: str = "Unknown"

async def get_target(update: Update, context: CallbackContext) -> UserTarget | None:
    if reply := update.message.reply_to_message:
        return UserTarget(
            id=reply.from_user.id,
            username=reply.from_user.username,
            first_name=reply.from_user.first_name
        )
    
    if context.args:
        try:
            return UserTarget(id=int(context.args[0]))
        except ValueError:
            await update.message.reply_text(
                "<b>❌ Invalid user ID</b>\n\nUsage: <code>/kill [user_id]</code>",
                parse_mode='HTML'
            )
            return None
    
    await update.message.reply_text(
        "<b>⚠️ Usage:</b> <code>/kill [user_id]</code> or reply to a user.",
        parse_mode='HTML'
    )
    return None

async def kill(update: Update, context: CallbackContext) -> None:
    # Owner Check
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ ᴏᴡɴᴇʀ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ!")
        return
    
    if not (target := await get_target(update, context)):
        return
    
    try:
        user = await user_collection.find_one({'id': target.id})
        
        if not user:
            await update.message.reply_text(
                f"<b>❌ User not in Database</b>\nID: <code>{target.id}</code>",
                parse_mode='HTML'
            )
            return
        
        target.first_name = user.get('first_name', target.first_name)
        characters = user.get('characters', [])
        char_count = len(characters)
        
        if char_count == 0:
            await update.message.reply_text(
                f"<b>❌ User has no characters to wipe!</b>\n"
                f"<b>Player:</b> <a href='tg://user?id={target.id}'>{escape(target.first_name)}</a>",
                parse_mode='HTML'
            )
            return
        
        # Action: Wipe Characters
        result = await user_collection.update_one(
            {'id': target.id},
            {'$set': {'characters': []}}
        )
        
        if result.modified_count > 0:
            top_chars_list = [
                f"{i+1}. {c.get('name', 'Unknown')} ({c.get('rarity', 'N/A')})"
                for i, c in enumerate(characters[:5])
            ]
            top_chars = "\n".join(top_chars_list)

            success_msg = (
                f"<b>✅ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴡɪᴘᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>👤 ᴘʟᴀʏᴇʀ:</b> <a href='tg://user?id={target.id}'>{escape(target.first_name)}</a>\n"
                f"<b>🆔 ɪᴅ:</b> <code>{target.id}</code>\n"
                f"<b>🗑️ ʀᴇᴍᴏᴠᴇᴅ:</b> <code>{char_count}</code> characters\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )
            
            # Message to Admin
            await update.message.reply_text(success_msg, parse_mode='HTML')

            # --- LOG SYSTEM ---
            log_text = (
                f"<b>🚨 ᴋɪʟʟ ʟᴏɢ (ᴄʜᴀʀᴀᴄᴛᴇʀ ᴡɪᴘᴇ)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>👨‍💻 ᴀᴅᴍɪɴ:</b> <a href='tg://user?id={OWNER_ID}'>Owner</a>\n"
                f"<b>👤 ᴛᴀʀɢᴇᴛ:</b> <a href='tg://user?id={target.id}'>{escape(target.first_name)}</a>\n"
                f"<b>🆔 ᴛ-ɪᴅ:</b> <code>{target.id}</code>\n"
                f"<b>📊 ᴛᴏᴛᴀʟ ʟᴏss:</b> <code>{char_count}</code> chars\n"
                f"<b>📅 ᴅᴀᴛᴇ:</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
                f"<b>📜 ᴛᴏᴘ 5 ʀᴇᴍᴏᴠᴇᴅ:</b>\n<code>{top_chars}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=LOG_GROUP_ID, 
                    text=log_text, 
                    parse_mode='HTML'
                )
            except Exception as log_e:
                print(f"Log Error: {log_e}")

        else:
            await update.message.reply_text("❌ Failed to modify database.")
    
    except Exception as e:
        await update.message.reply_text(f"<b>⚠️ Error:</b> <code>{str(e)}</code>", parse_mode='HTML')

# Register Handler
application.add_handler(CommandHandler('kill', kill, block=False))
