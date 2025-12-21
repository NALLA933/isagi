from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from shivu import application, user_collection

# --- CONFIGURATION ---
OWNER_ID = 8420981179
LOG_GROUP_ID = -1003110990230  # <--- Apne Group ki ID yahan daalein (Must start with -100)
# ---------------------

async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return 

    if len(context.args) != 2:
        await update.message.reply_text('❌ Use: `/transfer <sender_id> <receiver_id>`')
        return

    try:
        s_id = int(context.args[0])
        r_id = int(context.args[1])

        sender = await user_collection.find_one({'id': s_id})
        receiver = await user_collection.find_one({'id': r_id})

        if not sender or not receiver:
            await update.message.reply_text('❌ User(s) not found in Database.')
            return

        s_waifus = sender.get('characters', [])
        
        # Sari details callback_data mein store hain (No expiry issue)
        keyboard = [
            [InlineKeyboardButton("✅ Confirm", callback_data=f"TR|{s_id}|{r_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="TR|CANCEL")]
        ]

        await update.message.reply_text(
            f"🔄 **Transfer Request**\n\n"
            f"**From:** `{s_id}`\n"
            f"**To:** `{r_id}`\n"
            f"**Total Characters:** `{len(s_waifus)}` \n\n"
            "Proceed with transfer?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text('❌ Numeric IDs use karein.')

async def transfer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split('|')
    await query.answer()

    if data[1] == "CANCEL":
        await query.edit_message_text("❌ Transfer aborted by Owner.")
        return

    s_id, r_id = int(data[1]), int(data[2])

    try:
        sender = await user_collection.find_one({'id': s_id})
        s_waifus = sender.get('characters', [])

        if not s_waifus:
            await query.edit_message_text("⚠️ Error: Sender has 0 characters.")
            return

        # Database Updates
        await user_collection.update_one({'id': r_id}, {'$push': {'characters': {'$each': s_waifus}}})
        await user_collection.update_one({'id': s_id}, {'$set': {'characters': []}})

        success_msg = f"✅ **Success!** `{len(s_waifus)}` characters moved from `{s_id}` to `{r_id}`."
        await query.edit_message_text(success_msg, parse_mode='Markdown')

        # --- LOG TO GROUP ---
        log_text = (
            f"📢 **#TRANSFER_LOG**\n\n"
            f"**Owner:** [{update.effective_user.first_name}](tg://user?id={OWNER_ID})\n"
            f"**From User:** `{s_id}`\n"
            f"**To User:** `{r_id}`\n"
            f"**Total Characters:** `{len(s_waifus)}` \n"
            f"**Status:** Successfully Completed ✅"
        )
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text=log_text, parse_mode='Markdown')

    except Exception as e:
        await query.edit_message_text(f"❌ Database Error: {str(e)}")

# Handlers
application.add_handler(CommandHandler("transfer", transfer))
application.add_handler(CallbackQueryHandler(transfer_callback, pattern="^TR\|"))
