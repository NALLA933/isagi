from pymongo import ReturnDocument
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from shivu import application, OWNER_ID, user_totals_collection, LOGGER

async def change_time(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    chat = update.effective_chat

    try:
        # Check if command is used in a group
        if chat.type not in ['group', 'supergroup']:
            await update.message.reply_text('This command can only be used in groups.')
            return

        # Check if user is admin
        try:
            member = await chat.get_member(user.id)
            if member.status not in ('administrator', 'creator'):
                await update.message.reply_text('You do not have permission to use this command. Only admins can change spawn frequency.')
                return
        except Exception as e:
            LOGGER.error(f"Error checking admin status: {e}")
            await update.message.reply_text('Failed to verify your admin status. Please try again.')
            return

        # Validate arguments
        args = context.args
        if len(args) != 1:
            await update.message.reply_text('Incorrect format. Please use: /changetime NUMBER\n\nExample: /changetime 100')
            return

        # Parse frequency
        try:
            new_frequency = int(args[0])
        except ValueError:
            await update.message.reply_text('Invalid number. Please provide a valid integer.')
            return

        # Validate frequency range
        if new_frequency < 100:
            await update.message.reply_text('The message frequency must be greater than or equal to 100.')
            return

        if new_frequency > 10000:
            await update.message.reply_text('That\'s too much! Please use a value below 10000.')
            return

        # Update database
        chat_frequency = await user_totals_collection.find_one_and_update(
            {'chat_id': str(chat.id)},
            {'$set': {'message_frequency': new_frequency}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )

        await update.message.reply_text(
            f'✅ Successfully changed character spawn frequency to every {new_frequency} messages.\n\n'
            f'Characters will now appear after every {new_frequency} messages in this group.'
        )
        LOGGER.info(f"Changed spawn frequency for chat {chat.id} to {new_frequency}")

    except Exception as e:
        LOGGER.error(f"Error in change_time: {e}")
        await update.message.reply_text('Failed to change character spawn frequency. Please try again later.')


async def change_time_sudo(update: Update, context: CallbackContext) -> None:
    sudo_user_ids = {8420981179}
    user = update.effective_user

    try:
        # Check sudo permission
        if user.id not in sudo_user_ids:
            await update.message.reply_text('You do not have permission to use this command.')
            return

        # Check if command is used in a group
        if update.effective_chat.type not in ['group', 'supergroup']:
            await update.message.reply_text('This command can only be used in groups.')
            return

        # Validate arguments
        args = context.args
        if len(args) != 1:
            await update.message.reply_text('Incorrect format. Please use: /ctime NUMBER\n\nExample: /ctime 50')
            return

        # Parse frequency
        try:
            new_frequency = int(args[0])
        except ValueError:
            await update.message.reply_text('Invalid number. Please provide a valid integer.')
            return

        # Validate frequency range (sudo users can set lower values)
        if new_frequency < 1:
            await update.message.reply_text('The message frequency must be greater than or equal to 1.')
            return

        if new_frequency > 10000:
            await update.message.reply_text('That\'s too much! Please use a value below 10000.')
            return

        # Update database
        chat_frequency = await user_totals_collection.find_one_and_update(
            {'chat_id': str(update.effective_chat.id)},
            {'$set': {'message_frequency': new_frequency}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )

        await update.message.reply_text(
            f'✅ Successfully changed character spawn frequency to every {new_frequency} messages.\n\n'
            f'Characters will now appear after every {new_frequency} messages in this group.'
        )
        LOGGER.info(f"[SUDO] Changed spawn frequency for chat {update.effective_chat.id} to {new_frequency} by user {user.id}")

    except Exception as e:
        LOGGER.error(f"Error in change_time_sudo: {e}")
        await update.message.reply_text('Failed to change character spawn frequency. Please try again later.')


async def check_frequency(update: Update, context: CallbackContext) -> None:
    """Check current spawn frequency for this group"""
    try:
        chat_id = str(update.effective_chat.id)
        
        chat_frequency = await user_totals_collection.find_one({'chat_id': chat_id})
        
        if chat_frequency:
            freq = chat_frequency.get('message_frequency', 70)
            await update.message.reply_text(
                f'📊 Current spawn frequency: Every {freq} messages\n\n'
                f'Use /changetime NUMBER to change it (admin only)'
            )
        else:
            await update.message.reply_text(
                f'📊 Current spawn frequency: Every 70 messages (default)\n\n'
                f'Use /changetime NUMBER to set a custom frequency (admin only)'
            )
            
    except Exception as e:
        LOGGER.error(f"Error in check_frequency: {e}")
        await update.message.reply_text('Failed to check frequency.')


async def force_spawn(update: Update, context: CallbackContext) -> None:
    """Force spawn a character immediately (sudo only)"""
    sudo_user_ids = {8420981179}
    user = update.effective_user
    
    try:
        # Check sudo permission
        if user.id not in sudo_user_ids:
            await update.message.reply_text('⛔ You do not have permission to use this command.')
            return

        # Check if command is used in a group
        if update.effective_chat.type not in ['group', 'supergroup']:
            await update.message.reply_text('This command can only be used in groups.')
            return

        # Import the send_image function from main
        from shivu.main import send_image
        
        # Force spawn character
        await send_image(update, context)
        LOGGER.info(f"[FORCE SPAWN] Character spawned by sudo user {user.id} in chat {update.effective_chat.id}")
        
    except ImportError:
        LOGGER.error("Failed to import send_image function")
        await update.message.reply_text('❌ Failed to spawn character. Module not found.')
    except Exception as e:
        LOGGER.error(f"Error in force_spawn: {e}")
        await update.message.reply_text('❌ Failed to spawn character. Please try again.')


# Register handlers
application.add_handler(CommandHandler("ctime", change_time_sudo, block=False))
application.add_handler(CommandHandler("changetime", change_time, block=False))
application.add_handler(CommandHandler("frequency", check_frequency, block=False))
application.add_handler(CommandHandler("freq", check_frequency, block=False))
application.add_handler(CommandHandler("spawn", force_spawn, block=False))
application.add_handler(CommandHandler("fspawn", force_spawn, block=False))