from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from shivu import shivuu as bot, LOGGER, application
from shivu import user_collection
from html import escape
import traceback

# Log chat ID
LOG_CHAT_ID = -1002900862232

# Store pending gifts
pending_gifts = {}

async def handle_gift_command(update: Update, context: CallbackContext):
    """Handle the /gift command"""
    try:
        message = update.message
        sender_id = message.from_user.id

        LOGGER.info(f"[GIFT] Command called by user {sender_id}")

        # Check if replying to a message
        if not message.reply_to_message:
            await message.reply_text(
                "<b>❌ You need to reply to someone's message to gift!</b>",
                parse_mode='HTML'
            )
            return

        # Get receiver info
        receiver_id = message.reply_to_message.from_user.id
        receiver_username = message.reply_to_message.from_user.username or "N/A"
        receiver_first_name = message.reply_to_message.from_user.first_name

        # Check if gifting to self
        if sender_id == receiver_id:
            await message.reply_text(
                "<b>❌ You can't gift characters to yourself!</b>",
                parse_mode='HTML'
            )
            return

        # Check command format
        if len(context.args) != 1:
            await message.reply_text(
                "<b>❌ Usage:</b> Reply with <code>/gift character_id</code>",
                parse_mode='HTML'
            )
            return

        character_id = context.args[0]

        # Get sender's data
        sender = await user_collection.find_one({'id': sender_id})
        if not sender:
            await message.reply_text(
                "<b>❌ You don't have any characters to gift!</b>",
                parse_mode='HTML'
            )
            return

        # Find character in sender's collection
        character = None
        for char in sender.get('characters', []):
            if isinstance(char, dict) and str(char.get('id')) == str(character_id):
                character = char
                break

        if not character:
            await message.reply_text(
                "<b>❌ You don't own this character!</b>",
                parse_mode='HTML'
            )
            return

        # Check pending gifts
        if sender_id in pending_gifts:
            await message.reply_text(
                "<b>❌ You already have a pending gift!\nPlease confirm or cancel it first.</b>",
                parse_mode='HTML'
            )
            return

        # Store gift info
        pending_gifts[sender_id] = {
            'character': character,
            'receiver_id': receiver_id,
            'receiver_username': receiver_username,
            'receiver_first_name': receiver_first_name,
            'sender_username': message.from_user.username or "N/A",
            'sender_first_name': message.from_user.first_name
        }

        LOGGER.info(f"[GIFT] Pending gift stored for user {sender_id} -> {receiver_id}")

        # Get character rarity
        rarity = character.get('rarity', '🟢 Common')
        if isinstance(rarity, str):
            rarity_parts = rarity.split(' ', 1)
            rarity_emoji = rarity_parts[0] if len(rarity_parts) > 0 else '🟢'
            rarity_text = rarity_parts[1] if len(rarity_parts) > 1 else 'Common'
        else:
            rarity_emoji = '🟢'
            rarity_text = 'Common'

        # Create confirmation message
        caption = (
            f"<b>🎁 Gift Confirmation</b>\n\n"
            f"<b>To:</b> <a href='tg://user?id={receiver_id}'>{escape(receiver_first_name)}</a>\n\n"
            f"<b>Character Details:</b>\n"
            f"• <b>Name:</b> <code>{escape(character.get('name', 'Unknown'))}</code>\n"
            f"• <b>Anime:</b> <code>{escape(character.get('anime', 'Unknown'))}</code>\n"
            f"• <b>ID:</b> <code>{character.get('id', 'N/A')}</code>\n"
            f"• <b>Rarity:</b> {rarity_emoji} <code>{rarity_text}</code>\n\n"
            f"<i>Are you sure you want to gift this character?</i>"
        )

        # Create confirmation buttons with gift-specific prefix
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"gift_confirm:{sender_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"gift_cancel:{sender_id}")
            ]
        ]

        await message.reply_photo(
            photo=character.get('img_url', 'https://i.imgur.com/placeholder.png'),
            caption=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

        LOGGER.info(f"[GIFT] Confirmation message sent for user {sender_id}")

    except Exception as e:
        LOGGER.error(f"[GIFT ERROR] Command failed: {e}")
        LOGGER.error(traceback.format_exc())
        try:
            await message.reply_text(
                f"<b>❌ An error occurred!</b>\n<code>{str(e)}</code>",
                parse_mode='HTML'
            )
        except:
            pass

async def handle_gift_callback(update: Update, context: CallbackContext):
    """Handle gift confirmation callbacks"""
    query = update.callback_query

    try:
        # Parse callback data
        data = query.data

        LOGGER.info(f"[GIFT CALLBACK] Processing: {data} from user {query.from_user.id}")

        # Parse the callback data format: gift_confirm:user_id or gift_cancel:user_id
        if ':' not in data:
            LOGGER.error(f"[GIFT CALLBACK] Malformed data: {data}")
            await query.answer("❌ Invalid gift data!", show_alert=True)
            return

        action, user_id_str = data.split(':', 1)
        user_id = int(user_id_str)

        LOGGER.info(f"[GIFT CALLBACK] Action: {action}, User: {user_id}")

        # Verify user authorization
        if query.from_user.id != user_id:
            LOGGER.warning(f"[GIFT CALLBACK] Unauthorized: {query.from_user.id} tried to access {user_id}'s gift")
            await query.answer("⚠️ This is not your gift confirmation!", show_alert=True)
            return

        # Answer the callback
        await query.answer()

        # Check if pending gift exists
        if user_id not in pending_gifts:
            LOGGER.warning(f"[GIFT CALLBACK] No pending gift for user {user_id}")
            await query.answer("❌ No pending gift found or already processed!", show_alert=True)
            return

        gift_data = pending_gifts[user_id]
        character = gift_data['character']

        if action == "gift_confirm":  # Confirm
            LOGGER.info(f"[GIFT CALLBACK] Processing confirmation for user {user_id}")
            try:
                # Get sender and receiver data
                sender = await user_collection.find_one({'id': user_id})
                receiver = await user_collection.find_one({'id': gift_data['receiver_id']})

                LOGGER.info(f"[GIFT CALLBACK] Sender found: {sender is not None}, Receiver found: {receiver is not None}")

                if not sender:
                    raise Exception("Sender not found in database")

                # Verify character still exists in sender's collection
                char_exists = False
                for char in sender.get('characters', []):
                    if isinstance(char, dict) and str(char.get('id')) == str(character['id']):
                        char_exists = True
                        break

                if not char_exists:
                    raise Exception("Character no longer in sender's collection")

                # Remove from sender (remove only ONE instance)
                result = await user_collection.update_one(
                    {'id': user_id},
                    {'$pull': {'characters': {'id': character['id']}}}
                )
                LOGGER.info(f"[GIFT CALLBACK] Removed from sender - Modified: {result.modified_count}")

                # Add to receiver
                if receiver:
                    result = await user_collection.update_one(
                        {'id': gift_data['receiver_id']},
                        {'$push': {'characters': character}}
                    )
                    LOGGER.info(f"[GIFT CALLBACK] Added to receiver - Modified: {result.modified_count}")
                else:
                    await user_collection.insert_one({
                        'id': gift_data['receiver_id'],
                        'username': gift_data['receiver_username'],
                        'first_name': gift_data['receiver_first_name'],
                        'characters': [character]
                    })
                    LOGGER.info(f"[GIFT CALLBACK] Created new receiver document")

                # Get character rarity for log
                rarity = character.get('rarity', '🟢 Common')
                if isinstance(rarity, str):
                    rarity_parts = rarity.split(' ', 1)
                    rarity_emoji = rarity_parts[0] if len(rarity_parts) > 0 else '🟢'
                    rarity_text = rarity_parts[1] if len(rarity_parts) > 1 else 'Common'
                else:
                    rarity_emoji = '🟢'
                    rarity_text = 'Common'

                # Send log to log chat
                try:
                    log_caption = (
                        f"<b>🎁 Gift Transaction Log</b>\n"
                        f"{'='*30}\n\n"
                        f"<b>📤 Sender:</b>\n"
                        f"• Name: <a href='tg://user?id={user_id}'>{escape(gift_data['sender_first_name'])}</a>\n"
                        f"• Username: @{gift_data['sender_username']}\n"
                        f"• ID: <code>{user_id}</code>\n\n"
                        f"<b>📥 Receiver:</b>\n"
                        f"• Name: <a href='tg://user?id={gift_data['receiver_id']}'>{escape(gift_data['receiver_first_name'])}</a>\n"
                        f"• Username: @{gift_data['receiver_username']}\n"
                        f"• ID: <code>{gift_data['receiver_id']}</code>\n\n"
                        f"<b>🎭 Character:</b>\n"
                        f"• Name: <code>{escape(character.get('name', 'Unknown'))}</code>\n"
                        f"• Anime: <code>{escape(character.get('anime', 'Unknown'))}</code>\n"
                        f"• ID: <code>{character.get('id', 'N/A')}</code>\n"
                        f"• Rarity: {rarity_emoji} <code>{rarity_text}</code>\n\n"
                        f"✅ <i>Gift successfully transferred!</i>"
                    )

                    await context.bot.send_photo(
                        chat_id=LOG_CHAT_ID,
                        photo=character.get('img_url', 'https://i.imgur.com/placeholder.png'),
                        caption=log_caption,
                        parse_mode='HTML'
                    )
                    LOGGER.info(f"[GIFT CALLBACK] Log sent to chat {LOG_CHAT_ID}")
                except Exception as log_error:
                    LOGGER.error(f"[GIFT CALLBACK] Failed to send log: {log_error}")

                # Update confirmation message
                success_msg = (
                    f"✅ <b>Gift Successful!</b>\n\n"
                    f"<code>{escape(character.get('name', 'Unknown'))}</code> has been gifted to "
                    f"<a href='tg://user?id={gift_data['receiver_id']}'>{escape(gift_data['receiver_first_name'])}</a>!"
                )

                await query.edit_message_caption(
                    caption=success_msg,
                    parse_mode='HTML'
                )

                LOGGER.info(f"[GIFT CALLBACK] Gift completed successfully for user {user_id}")

            except Exception as e:
                LOGGER.error(f"[GIFT CALLBACK] Processing failed: {e}")
                LOGGER.error(traceback.format_exc())
                await query.edit_message_caption(
                    caption=f"❌ <b>Failed to process gift!</b>\n\n<code>{str(e)}</code>",
                    parse_mode='HTML'
                )

        elif action == "gift_cancel":  # Cancel
            LOGGER.info(f"[GIFT CALLBACK] Gift cancelled by user {user_id}")
            await query.edit_message_caption(
                caption="❌ <b>Gift cancelled!</b>",
                parse_mode='HTML'
            )

        # Clean up pending gift
        if user_id in pending_gifts:
            del pending_gifts[user_id]
            LOGGER.info(f"[GIFT CALLBACK] Cleaned up pending gift for user {user_id}")

    except Exception as e:
        LOGGER.error(f"[GIFT CALLBACK] Callback handler failed: {e}")
        LOGGER.error(traceback.format_exc())
        try:
            await query.answer(f"❌ Error: {str(e)}", show_alert=True)
        except:
            pass

def register_gift_handlers():
    """Register gift command and callback handlers"""
    LOGGER.info("[GIFT] Registering handlers...")

    # Add command handler
    application.add_handler(CommandHandler("gift", handle_gift_command, block=False))

    # Add callback handler with specific pattern - ONLY catches gift callbacks
    application.add_handler(
        CallbackQueryHandler(
            handle_gift_callback,
            pattern='^gift_(confirm|cancel):',  # Only matches gift_confirm: or gift_cancel:
            block=False
        )
    )

    LOGGER.info("[GIFT] Handlers registered successfully")
    LOGGER.info(f"[GIFT] Total handlers: {len(application.handlers)}")

# Register handlers
register_gift_handlers()