from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from shivu import application, user_collection

OWNER_ID = 8420981179

async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return # Chup-chaap return kar do agar owner nahi hai

    if len(context.args) != 2:
        await update.message.reply_text('❌ Sahi tarika: `/transfer 123 456`')
        return

    try:
        s_id = int(context.args[0])
        r_id = int(context.args[1])

        # Database se check karein ki users hain ya nahi
        sender = await user_collection.find_one({'id': s_id})
        receiver = await user_collection.find_one({'id': r_id})

        if not sender or not receiver:
            await update.message.reply_text('❌ User database mein nahi mila.')
            return

        s_waifus = sender.get('characters', [])
        
        # Sari details callback_data mein bhar di hain
        # Format: TR|SenderID|ReceiverID
        keyboard = [
            [InlineKeyboardButton("✅ Confirm", callback_data=f"TR|{s_id}|{r_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="TR|CANCEL")]
        ]

        await update.message.reply_text(
            f"🔄 **Mass Transfer**\n\n"
            f"From: `{s_id}`\n"
            f"To: `{r_id}`\n"
            f"Total: `{len(s_waifus)}` characters\n\n"
            "Kya aap pakka transfer karna chahte hain?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text('❌ IDs sirf numbers honi chahiye.')

async def transfer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split('|') # Data ko split kar rahe hain
    
    await query.answer()

    if data[1] == "CANCEL":
        await query.edit_message_text("❌ Transfer cancel kar diya gaya.")
        return

    # Button se IDs nikalna
    s_id = int(data[1])
    r_id = int(data[2])

    try:
        sender = await user_collection.find_one({'id': s_id})
        s_waifus = sender.get('characters', [])

        if not s_waifus:
            await query.edit_message_text("⚠️ Transfer fail: Sender ke paas kuch nahi hai.")
            return

        # 1. Receiver mein add karein
        await user_collection.update_one(
            {'id': r_id},
            {'$push': {'characters': {'$each': s_waifus}}}
        )
        # 2. Sender se remove karein
        await user_collection.update_one({'id': s_id}, {'$set': {'characters': []}})

        await query.edit_message_text(f"✅ Success! `{len(s_waifus)}` characters transferred to `{r_id}`.")
    
    except Exception as e:
        await query.edit_message_text(f"❌ Error: {str(e)}")

# Handlers register karein (Dhyan se dekhien pattern)
application.add_handler(CommandHandler("transfer", transfer))
application.add_handler(CallbackQueryHandler(transfer_callback, pattern="^TR\|"))
