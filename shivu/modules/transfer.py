import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from shivu import application, user_collection

OWNER_ID = 8420981179

async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text('🚫 Unauthorized.')
            return

        if len(context.args) != 2:
            await update.message.reply_text('ℹ️ Use: `/transfer <sender_id> <receiver_id>`')
            return

        s_id = int(context.args[0])
        r_id = int(context.args[1])

        sender = await user_collection.find_one({'id': s_id})
        receiver = await user_collection.find_one({'id': r_id})

        if not sender or not receiver:
            await update.message.reply_text('❌ User not found in DB.')
            return

        count = len(sender.get('characters', []))
        if count == 0:
            await update.message.reply_text('⚠️ Sender has no characters.')
            return

        # Yahan humne IDs ko callback_data mein daal diya hai (S: Sender, R: Receiver)
        keyboard = [
            [InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_tr|{s_id}|{r_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_tr")]
        ]

        await update.message.reply_text(
            f"🔄 **Transfer Details**\nFrom: `{s_id}`\nTo: `{r_id}`\nCharacters: `{count}`\n\nConfirm?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    except ValueError:
        await update.message.reply_text('❌ Use numeric IDs.')

async def transfer_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith('confirm_tr'):
        # Data ko split karke IDs nikalna
        try:
            _, s_id, r_id = query.data.split('|')
            s_id, r_id = int(s_id), int(r_id)

            sender = await user_collection.find_one({'id': s_id})
            s_waifus = sender.get('characters', [])

            if not s_waifus:
                await query.edit_message_text("❌ Sender already has 0 characters.")
                return

            # Main Transfer Logic
            await user_collection.update_one({'id': r_id}, {'$push': {'characters': {'$each': s_waifus}}})
            await user_collection.update_one({'id': s_id}, {'$set': {'characters': []}})

            await query.edit_message_text(f"✅ **Success!** Moved `{len(s_waifus)}` characters to `{r_id}`.")
        
        except Exception as e:
            await query.edit_message_text(f"⚠️ Error: {str(e)}")

    elif query.data == 'cancel_tr':
        await query.edit_message_text("❌ Transfer cancelled.")

# Handlers (Note: pattern updated for split data)
application.add_handler(CommandHandler("transfer", transfer))
application.add_handler(CallbackQueryHandler(transfer_confirm, pattern='^confirm_tr|cancel_tr'))
