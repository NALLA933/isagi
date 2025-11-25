from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from shivu import LOGGER, application, user_collection
from html import escape
import asyncio

pending_gifts = {}
GIFT_TIMEOUT = 60


def is_video_url(url):
    if not url:
        return False

    url_lower = url.lower()

    video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v']
    if any(url_lower.endswith(ext) for ext in video_extensions):
        return True

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


async def reply_media_message(message, media_url, caption, reply_markup=None, is_video=False):
    try:
        if not is_video:
            is_video = is_video_url(media_url)

        if is_video:
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
                return await message.reply_photo(
                    photo=media_url,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
        else:
            return await message.reply_photo(
                photo=media_url,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    except Exception as e:
        LOGGER.error(f"Failed to send media: {e}")
        return await message.reply_text(
            text=caption,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )


async def expire_gift(sender_id, message, chat_id):
    await asyncio.sleep(GIFT_TIMEOUT)
    
    if sender_id in pending_gifts:
        try:
            await message.delete()
        except Exception as e:
            LOGGER.error(f"Failed to delete expired gift message: {e}")
        
        del pending_gifts[sender_id]
        
        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text="⏰ <b>Gift Expired</b>\n\n<i>Your gift request has timed out. You can send a new gift now.</i>",
                parse_mode='HTML'
            )
        except Exception as e:
            LOGGER.error(f"Failed to send expiration notice: {e}")


async def handle_gift_command(update: Update, context: CallbackContext):
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
            await message.reply_text("ᴀᴄʜᴀ ʟᴀᴜᴅᴇ ʙᴏᴛ ᴋᴏ ᴅᴇɢᴀ!\n sᴏᴊᴀ ᴍᴜᴛᴛʜɪ ᴍᴀʀ ʙʜᴀɪ", parse_mode='HTML')
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
            f"<blockquote expandable><b>🎁 Gift Confirmation</b>\n"
            f"<b>To:</b> <a href='tg://user?id={receiver_id}'>{escape(receiver_first_name)}</a>\n\n"
            f"<b>✨ Name:</b> <code>{escape(character.get('name', 'Unknown'))}</code>\n"
            f"<b>📺 Anime:</b> <code>{escape(character.get('anime', 'Unknown'))}</code>\n"
            f"<b>🆔 ID:</b> <code>{character.get('id', 'N/A')}</code>\n"
            f"<b>🎴 Rarity:</b> <code>{character.get('rarity', 'Common')}</code></blockquote>\n\n"
            f"<i>⏰ You have {GIFT_TIMEOUT} seconds to confirm</i>"
        )

        keyboard = [[
            InlineKeyboardButton("✅ Confirm", callback_data=f"gift_confirm:{sender_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"gift_cancel:{sender_id}")
        ]]

        media_url = character.get('img_url', 'https://i.imgur.com/placeholder.png')
        is_video = character.get('is_video', False) or is_video_url(media_url)

        sent_message = await reply_media_message(
            message, 
            media_url, 
            caption, 
            InlineKeyboardMarkup(keyboard), 
            is_video
        )

        asyncio.create_task(expire_gift(sender_id, sent_message, message.chat_id))

    except Exception as e:
        LOGGER.error(f"Gift command error: {e}")
        import traceback
        traceback.print_exc()
        await message.reply_text(f"❌ Error: {str(e)}", parse_mode='HTML')


async def handle_gift_callback(update: Update, context: CallbackContext):
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

            sender_characters = sender.get('characters', [])
            found = False
            updated_characters = []
            
            for c in sender_characters:
                if not found and isinstance(c, dict) and str(c.get('id')) == str(character['id']):
                    found = True
                    continue
                updated_characters.append(c)
            
            await user_collection.update_one(
                {'id': user_id}, 
                {'$set': {'characters': updated_characters}}
            )

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

            await query.edit_message_caption(
                caption=(
                    f"<blockquote expandable><b>✅ Gift Successful!</b>\n\n"
                    f"<b>✨ Character:</b> <code>{escape(character.get('name', 'Unknown'))}</code>\n"
                    f"<b>📺 From:</b> <code>{escape(character.get('anime', 'Unknown'))}</code>\n"
                    f"<b>🎁 Sent to:</b> <a href='tg://user?id={gift_data['receiver_id']}'>{escape(gift_data['receiver_first_name'])}</a></blockquote>\n\n"
                    f"<i>Thank you for gifting! 🎁</i>"
                ),
                parse_mode='HTML'
            )

        elif action == "gift_cancel":
            await query.message.delete()
            
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="<b>❌ Gift Cancelled</b>\n\n<i>The character remains in your collection.</i>",
                parse_mode='HTML'
            )

        del pending_gifts[user_id]

    except Exception as e:
        LOGGER.error(f"Callback error: {e}")
        import traceback
        traceback.print_exc()
        try:
            await query.answer(f"❌ Error: {str(e)[:100]}", show_alert=True)
        except:
            pass


application.add_handler(CommandHandler("gift", handle_gift_command, block=False))
application.add_handler(CallbackQueryHandler(handle_gift_callback, pattern='^gift_(confirm|cancel):', block=False))