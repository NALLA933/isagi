from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from shivu import LOGGER, application, user_collection
from html import escape

pending_gifts = {}


def is_video_url(url):
    """Check if URL is a video based on extension or domain patterns"""
    if not url:
        return False
    
    url_lower = url.lower()
    
    # Check for video file extensions
    video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v']
    if any(url_lower.endswith(ext) for ext in video_extensions):
        return True
    
    # Check for video hosting patterns in URL
    video_patterns = [
        '/video/',
        '/videos/',
        'video=',
        'v=',
        '.mp4?',
        '/stream/',
    ]
    if any(pattern in url_lower for pattern in video_patterns):
        return True
    
    return False


async def send_media_message(context, chat_id, media_url, caption, reply_markup=None, is_video=False, reply_to_message_id=None):
    """Helper function to send photo or video with fallback support (removed - not needed)"""
    pass


async def reply_media_message(message, media_url, caption, reply_markup=None, is_video=False):
    """Helper function to reply with photo or video with fallback support"""
    try:
        # Auto-detect if not explicitly set
        if not is_video:
            is_video = is_video_url(media_url)
        
        if is_video:
            # Try sending as video
            try:
                return await message.reply_video(
                    video=media_url,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode='HTML',
                    supports_streaming=True,
                    read_timeout=120,
                    write_timeout=120
                )
            except Exception as video_error:
                LOGGER.warning(f"Failed to send as video, trying as photo: {video_error}")
                # Fallback to photo if video fails
                return await message.reply_photo(
                    photo=media_url,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
        else:
            # Send as photo
            return await message.reply_photo(
                photo=media_url,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    except Exception as e:
        LOGGER.error(f"Failed to send media: {e}")
        # Ultimate fallback to text-only
        return await message.reply_text(
            text=caption,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )


async def handle_gift_command(update: Update, context: CallbackContext):
    """Handle gift command with FULL IMAGE & VIDEO SUPPORT"""
    try:
        message = update.message
        sender_id = message.from_user.id

        if not message.reply_to_message:
            await message.reply_text("Reply to someone's message to gift", parse_mode='HTML')
            return

        receiver_id = message.reply_to_message.from_user.id
        receiver_username = message.reply_to_message.from_user.username or "N/A"
        receiver_first_name = message.reply_to_message.from_user.first_name
        receiver_is_bot = message.reply_to_message.from_user.is_bot

        if sender_id == receiver_id:
            await message.reply_text("You can't gift to yourself", parse_mode='HTML')
            return

        if receiver_is_bot:
            await message.reply_text("ᴀᴄʜᴀ ʟᴀᴜᴅᴇ ʙᴏᴛ ʟᴏ ᴅᴇɢᴀ!", parse_mode='HTML')
            return

        if len(context.args) != 1:
            await message.reply_text("Usage: /gift character_id", parse_mode='HTML')
            return

        character_id = context.args[0]
        sender = await user_collection.find_one({'id': sender_id})

        if not sender:
            await message.reply_text("You don't have any characters", parse_mode='HTML')
            return

        character = next((c for c in sender.get('characters', []) if isinstance(c, dict) and str(c.get('id')) == str(character_id)), None)

        if not character:
            await message.reply_text("You don't own this character", parse_mode='HTML')
            return

        if sender_id in pending_gifts:
            await message.reply_text("You already have a pending gift", parse_mode='HTML')
            return

        pending_gifts[sender_id] = {
            'character': character,
            'receiver_id': receiver_id,
            'receiver_username': receiver_username,
            'receiver_first_name': receiver_first_name,
            'sender_username': message.from_user.username or "N/A",
            'sender_first_name': message.from_user.first_name
        }

        caption = (
            f"<b>🎁 Gift Confirmation</b>\n"
            f"To: <a href='tg://user?id={receiver_id}'>{escape(receiver_first_name)}</a>\n\n"
            f"✨ <b>Name:</b> {escape(character.get('name', 'Unknown'))}\n"
            f"📺 <b>Anime:</b> {escape(character.get('anime', 'Unknown'))}\n"
            f"🆔 <b>ID:</b> {character.get('id', 'N/A')}\n"
            f"🎴 <b>Rarity:</b> {character.get('rarity', 'Common')}\n\n"
            f"<i>Confirm gift?</i>"
        )

        keyboard = [[
            InlineKeyboardButton("✅ Confirm", callback_data=f"gift_confirm:{sender_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"gift_cancel:{sender_id}")
        ]]

        media_url = character.get('img_url', 'https://i.imgur.com/placeholder.png')
        # Check both database flag and URL pattern for video detection
        is_video = character.get('is_video', False) or is_video_url(media_url)

        # Use helper function for sending media with auto-detection
        await reply_media_message(
            message, 
            media_url, 
            caption, 
            InlineKeyboardMarkup(keyboard), 
            is_video
        )

    except Exception as e:
        LOGGER.error(f"Gift command error: {e}")
        import traceback
        traceback.print_exc()
        await message.reply_text(f"❌ Error: {str(e)}", parse_mode='HTML')


async def handle_gift_callback(update: Update, context: CallbackContext):
    """Handle gift confirmation/cancellation with FULL IMAGE & VIDEO SUPPORT"""
    query = update.callback_query

    try:
        if ':' not in query.data:
            await query.answer("❌ Invalid data", show_alert=True)
            return

        action, user_id_str = query.data.split(':', 1)
        user_id = int(user_id_str)

        if query.from_user.id != user_id:
            await query.answer("⚠️ Not your gift", show_alert=True)
            return

        await query.answer()

        if user_id not in pending_gifts:
            await query.answer("❌ No pending gift", show_alert=True)
            return

        gift_data = pending_gifts[user_id]
        character = gift_data['character']

        if action == "gift_confirm":
            sender = await user_collection.find_one({'id': user_id})

            if not sender:
                raise Exception("Sender not found")

            char_exists = any(isinstance(c, dict) and str(c.get('id')) == str(character['id']) for c in sender.get('characters', []))

            if not char_exists:
                raise Exception("Character no longer available")

            # Remove from sender
            await user_collection.update_one(
                {'id': user_id}, 
                {'$pull': {'characters': {'id': character['id']}}}
            )

            # Add to receiver
            receiver = await user_collection.find_one({'id': gift_data['receiver_id']})

            if receiver:
                await user_collection.update_one(
                    {'id': gift_data['receiver_id']}, 
                    {'$push': {'characters': character}}
                )
            else:
                await user_collection.insert_one({
                    'id': gift_data['receiver_id'],
                    'username': gift_data['receiver_username'],
                    'first_name': gift_data['receiver_first_name'],
                    'characters': [character]
                })

            # Update the confirmation message
            await query.edit_message_caption(
                caption=(
                    f"<b>✅ Gift Successful!</b>\n\n"
                    f"✨ {escape(character.get('name', 'Unknown'))} sent to "
                    f"<a href='tg://user?id={gift_data['receiver_id']}'>{escape(gift_data['receiver_first_name'])}</a>\n\n"
                    f"<i>Thank you for gifting! 🎁</i>"
                ),
                parse_mode='HTML'
            )

        elif action == "gift_cancel":
            await query.edit_message_caption(
                caption="<b>❌ Gift Cancelled</b>\n\n<i>The character remains in your collection.</i>",
                parse_mode='HTML'
            )

        # Clean up pending gift
        del pending_gifts[user_id]

    except Exception as e:
        LOGGER.error(f"Callback error: {e}")
        import traceback
        traceback.print_exc()
        try:
            await query.answer(f"❌ Error: {str(e)[:100]}", show_alert=True)
        except:
            pass


# Register handlers
application.add_handler(CommandHandler("gift", handle_gift_command, block=False))
application.add_handler(CallbackQueryHandler(handle_gift_callback, pattern='^gift_(confirm|cancel):', block=False))