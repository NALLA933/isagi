from dataclasses import dataclass
from html import escape
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import application, user_collection

OWNER_ID = 5147822244


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
                "<b>Invalid user ID</b>\n\nUsage: <code>/kill [user_id]</code> or reply",
                parse_mode='HTML'
            )
            return None
    
    await update.message.reply_text(
        "Usage: <code>/kill [user_id]</code> or reply to user",
        parse_mode='HTML'
    )
    return None


async def kill(update: Update, context: CallbackContext) -> None:
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Owner only command")
        return
    
    if not (target := await get_target(update, context)):
        return
    
    try:
        user = await user_collection.find_one({'id': target.id})
        
        if not user:
            await update.message.reply_text(
                f"❌ User not found\nID: <code>{target.id}</code>",
                parse_mode='HTML'
            )
            return
        
        target.first_name = user.get('first_name', target.first_name)
        characters = user.get('characters', [])
        char_count = len(characters)
        
        if char_count == 0:
            await update.message.reply_text(
                f"❌ User has no characters\n\n"
                f"<b>User:</b> <a href='tg://user?id={target.id}'>{escape(target.first_name)}</a>\n"
                f"<b>ID:</b> <code>{target.id}</code>",
                parse_mode='HTML'
            )
            return
        
        result = await user_collection.update_one(
            {'id': target.id},
            {'$set': {'characters': []}}
        )
        
        if result.modified_count > 0:
            top_chars = "\n".join([
                f"{i+1}. {c.get('name', 'Unknown')} ({c.get('anime', 'Unknown')})"
                for i, c in enumerate(characters[:5])
            ])
            
            await update.message.reply_text(
                f"<b>✅ Characters Wiped</b>\n\n"
                f"<b>User:</b> <a href='tg://user?id={target.id}'>{escape(target.first_name)}</a>\n"
                f"<b>ID:</b> <code>{target.id}</code>\n\n"
                f"<b>Removed:</b> <code>{char_count}</code> characters\n\n"
                f"<b>Top 5:</b>\n<code>{top_chars}</code>",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text("❌ Failed to remove characters")
    
    except Exception as e:
        await update.message.reply_text(
            f"<b>Error:</b> <code>{str(e)}</code>",
            parse_mode='HTML'
        )


application.add_handler(CommandHandler('kill', kill, block=False))