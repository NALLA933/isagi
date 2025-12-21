from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from shivu import application, user_collection
import html

# --- CONFIGURATION ---
OWNER_ID = 8420981179
LOG_GROUP_ID = -1003110990230  # <--- Apna Group ID dalein

async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return 

    if len(context.args) != 2:
        await update.message.reply_text('❌ <b>Usage:</b> /transfer <code>sender_id</code> <code>receiver_id</code>', parse_mode='HTML')
        return

    try:
        s_id = int(context.args[0])
        r_id = int(context.args[1])

        sender = await user_collection.find_one({'id': s_id})
        receiver = await user_collection.find_one({'id': r_id})

        if not sender or not receiver:
            await update.message.reply_text('❌ <b>User not found in Database.</b>', parse_mode='HTML')
            return

        s_waifus = sender.get('characters', [])
        
        keyboard = [
            [InlineKeyboardButton("✅ Confirm", callback_data=f"TR|{s_id}|{r_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="TR|CANCEL")]
        ]

        msg = (
            f"🔄 <b>Transfer Request</b>\n\n"
            f"<b>From:</b> <code>{s_id}</code>\n"
            f"<b>To:</b> <code>{r_id}</code>\n"
            f"<b>Total:</b> <code>{len(s_waifus)}</code> characters\n\n"
            "Confirm transfer?"
        )
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    except ValueError:
        await update.message.reply_text('❌ <b>Error:</b> IDs numbers mein honi chahiye.', parse_mode='HTML')

async def transfer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split('|')
    await query.answer()

    if data[1] == "CANCEL":
        await query.edit_message_text("❌ <b>Transfer cancelled by Owner.</b>", parse_mode='HTML')
        return

    s_id, r_id = int(data[1]), int(data[2])

    try:
        sender = await user_collection.find_one({'id': s_id})
        s_waifus = sender.get('characters', [])

        if not s_waifus:
            await query.edit_message_text("⚠️ <b>Sender has 0 characters.</b>", parse_mode='HTML')
            return

        # DB Update
        await user_collection.update_one({'id': r_id}, {'$push': {'characters': {'$each': s_waifus}}})
        await user_collection.update_one({'id': s_id}, {'$set': {'characters': []}})

        await query.edit_message_text(f"✅ <b>Success!</b> Moved <code>{len(s_waifus)}</code> characters.", parse_mode='HTML')

        # --- SAFE LOGGING (HTML) ---
        user_name = html.escape(update.effective_user.first_name) # Special chars fix
        log_text = (
            f"📢 <b>#TRANSFER_LOG</b>\n\n"
            f"<b>By Owner:</b> {user_name} (<code>{OWNER_ID}</code>)\n"
            f"<b>From:</b> <code>{s_id}</code>\n"
            f"<b>To:</b> <code>{r_id}</code>\n"
            f"<b>Total:</b> <code>{len(s_waifus)}</code>\n"
            f"<b>Status:</b> Completed ✅"
        )
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text=log_text, parse_mode='HTML')

    except Exception as e:
        # Error message ko bhi escape karna zaroori hai
        error_msg = html.escape(str(e))
        await query.edit_message_text(f"❌ <b>Database Error:</b> <code>{error_msg}</code>", parse_mode='HTML')

# Handlers
application.add_handler(CommandHandler("transfer", transfer))
application.add_handler(CallbackQueryHandler(transfer_callback, pattern="^TR\|"))
