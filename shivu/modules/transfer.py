import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from shivu import application, user_collection, db

# Configuration
OWNER_ID = 8420981179
LOG_CHANNEL_ID = -1003110990230  # Apna Log Channel ID yahan dalein

async def get_user_name(user_id):
    """Database se user ka naam nikalne ke liye helper function"""
    user = await user_collection.find_one({'id': user_id})
    return user.get('username', 'Unknown') if user else "Unknown"

async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        
        # 1. Authorization Check
        if user_id != OWNER_ID:
            await update.message.reply_text('🚫 **Access Denied:** Only the developer can perform mass transfers.')
            return

        # 2. Argument Check
        if len(context.args) != 2:
            await update.message.reply_text('ℹ️ **Usage:** `/transfer <sender_id> <receiver_id>`')
            return

        s_id = int(context.args[0])
        r_id = int(context.args[1])

        if s_id == r_id:
            await update.message.reply_text('❌ Sender and Receiver cannot be the same.')
            return

        # 3. Data Fetching
        sender = await user_collection.find_one({'id': s_id})
        receiver = await user_collection.find_one({'id': r_id})

        if not sender:
            await update.message.reply_text(f'❌ Sender `{s_id}` not found in Database.')
            return
        if not receiver:
            await update.message.reply_text(f'❌ Receiver `{r_id}` not found in Database.')
            return

        s_waifus = sender.get('characters', [])
        if not s_waifus:
            await update.message.reply_text('⚠️ Sender has no characters to transfer.')
            return

        # 4. Preparation for Confirmation
        s_name = sender.get('first_name', 'User1')
        r_name = receiver.get('first_name', 'User2')
        
        context.user_data['tr_data'] = {'s': s_id, 'r': r_id, 'count': len(s_waifus)}

        keyboard = [
            [InlineKeyboardButton("✅ Confirm Transfer", callback_data='confirm_tr')],
            [InlineKeyboardButton("❌ Abort", callback_data='cancel_tr')]
        ]

        msg = (
            f"🔄 **Transfer Initiation**\n\n"
            f"**From:** {s_name} (`{s_id}`)\n"
            f"**To:** {r_name} (`{r_id}`)\n"
            f"**Amount:** `{len(s_waifus)}` Characters\n\n"
            f"Do you want to proceed? This action is irreversible."
        )
        
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    except ValueError:
        await update.message.reply_text('❌ Please provide valid numeric IDs.')
    except Exception as e:
        logging.error(f"Error in transfer: {e}")

async def transfer_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = context.user_data.get('tr_data')

    if query.data == 'confirm_tr':
        if not data:
            await query.edit_message_text("❌ Session expired. Re-run the command.")
            return

        s_id, r_id, count = data['s'], data['r'], data['count']
        
        try:
            # Atomic update (Dono ko ek saath update karna)
            sender = await user_collection.find_one({'id': s_id})
            s_waifus = sender.get('characters', [])

            # Receiver update: Push all characters from sender
            await user_collection.update_one(
                {'id': r_id},
                {'$push': {'characters': {'$each': s_waifus}}}
            )
            
            # Sender update: Clear characters
            await user_collection.update_one({'id': s_id}, {'$set': {'characters': []}})

            success_text = f"✅ **Success!**\n`{count}` characters moved from `{s_id}` to `{r_id}`."
            await query.edit_message_text(success_text, parse_mode='Markdown')

            # Log to Channel
            await context.bot.send_message(
                LOG_CHANNEL_ID,
                f"#TRANSFER_LOG\nOwner: {OWNER_ID}\nFrom: `{s_id}`\nTo: `{r_id}`\nTotal: `{count}`"
            )

        except Exception as e:
            await query.edit_message_text(f"⚠️ **Database Error:** {e}")
        
        context.user_data.pop('tr_data', None)

    elif query.data == 'cancel_tr':
        await query.edit_message_text("❌ Transfer operation cancelled.")
        context.user_data.pop('tr_data', None)

# Registration
application.add_handler(CommandHandler("transfer", transfer))
application.add_handler(CallbackQueryHandler(transfer_confirm, pattern='^confirm_tr|^cancel_tr$'))
