from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from shivu import LOGGER, application, user_collection
from html import escape

LOG_CHAT_ID = -1002900862232
pending_gifts = {}

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

        if sender_id == receiver_id:
            await message.reply_text("You can't gift to yourself", parse_mode='HTML')
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
            f"<b>Gift Confirmation</b>\n"
            f"To: <a href='tg://user?id={receiver_id}'>{escape(receiver_first_name)}</a>\n\n"
            f"Name: {escape(character.get('name', 'Unknown'))}\n"
            f"Anime: {escape(character.get('anime', 'Unknown'))}\n"
            f"ID: {character.get('id', 'N/A')}\n"
            f"Rarity: {character.get('rarity', 'Common')}\n\n"
            f"Confirm gift?"
        )

        keyboard = [[
            InlineKeyboardButton("Confirm", callback_data=f"gift_confirm:{sender_id}"),
            InlineKeyboardButton("Cancel", callback_data=f"gift_cancel:{sender_id}")
        ]]

        media_url = character.get('img_url', 'https://i.imgur.com/placeholder.png')
        
        if character.get('is_video', False):
            await message.reply_video(video=media_url, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', supports_streaming=True)
        else:
            await message.reply_photo(photo=media_url, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    except Exception as e:
        LOGGER.error(f"Gift command error: {e}")
        await message.reply_text(f"Error: {str(e)}", parse_mode='HTML')

async def handle_gift_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    
    try:
        if ':' not in query.data:
            await query.answer("Invalid data", show_alert=True)
            return

        action, user_id_str = query.data.split(':', 1)
        user_id = int(user_id_str)

        if query.from_user.id != user_id:
            await query.answer("Not your gift", show_alert=True)
            return

        await query.answer()

        if user_id not in pending_gifts:
            await query.answer("No pending gift", show_alert=True)
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

            await user_collection.update_one({'id': user_id}, {'$pull': {'characters': {'id': character['id']}}})

            receiver = await user_collection.find_one({'id': gift_data['receiver_id']})
            
            if receiver:
                await user_collection.update_one({'id': gift_data['receiver_id']}, {'$push': {'characters': character}})
            else:
                await user_collection.insert_one({
                    'id': gift_data['receiver_id'],
                    'username': gift_data['receiver_username'],
                    'first_name': gift_data['receiver_first_name'],
                    'characters': [character]
                })

            log_caption = (
                f"<b>Gift Log</b>\n\n"
                f"From: <a href='tg://user?id={user_id}'>{escape(gift_data['sender_first_name'])}</a> ({user_id})\n"
                f"To: <a href='tg://user?id={gift_data['receiver_id']}'>{escape(gift_data['receiver_first_name'])}</a> ({gift_data['receiver_id']})\n\n"
                f"Character: {escape(character.get('name', 'Unknown'))}\n"
                f"ID: {character.get('id', 'N/A')}"
            )

            media_url = character.get('img_url', 'https://i.imgur.com/placeholder.png')
            
            try:
                if character.get('is_video', False):
                    await context.bot.send_video(chat_id=LOG_CHAT_ID, video=media_url, caption=log_caption, parse_mode='HTML', supports_streaming=True)
                else:
                    await context.bot.send_photo(chat_id=LOG_CHAT_ID, photo=media_url, caption=log_caption, parse_mode='HTML')
            except Exception as log_error:
                LOGGER.error(f"Log send failed: {log_error}")

            await query.edit_message_caption(
                caption=f"Gift successful!\n{escape(character.get('name', 'Unknown'))} sent to <a href='tg://user?id={gift_data['receiver_id']}'>{escape(gift_data['receiver_first_name'])}</a>",
                parse_mode='HTML'
            )

        elif action == "gift_cancel":
            await query.edit_message_caption(caption="Gift cancelled", parse_mode='HTML')

        del pending_gifts[user_id]

    except Exception as e:
        LOGGER.error(f"Callback error: {e}")
        await query.answer(f"Error: {str(e)}", show_alert=True)

application.add_handler(CommandHandler("gift", handle_gift_command, block=False))
application.add_handler(CallbackQueryHandler(handle_gift_callback, pattern='^gift_(confirm|cancel):', block=False))