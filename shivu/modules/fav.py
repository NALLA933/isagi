from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from shivu import application, user_collection, LOGGER

async def fav(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text('Provide character ID')
        return

    character_id = str(context.args[0])

    try:
        user = await user_collection.find_one({'id': user_id})
        if not user:
            await update.message.reply_text('You have no characters')
            return

        character = next((c for c in user.get('characters', []) if str(c.get('id')) == character_id), None)

        if not character:
            await update.message.reply_text('Character not in your collection')
            return

        buttons = [[
            InlineKeyboardButton("Yes", callback_data=f"fvc_{user_id}_{character_id}"),
            InlineKeyboardButton("No", callback_data=f"fvx_{user_id}")
        ]]

        caption = (
            f"<b>Set as favorite?</b>\n\n"
            f"Name: {character.get('name', 'Unknown')}\n"
            f"Anime: {character.get('anime', 'Unknown')}\n"
            f"ID: {character.get('id', 'Unknown')}"
        )

        media_url = character.get('img_url')
        
        if character.get('is_video', False):
            await update.message.reply_video(video=media_url, caption=caption, reply_markup=InlineKeyboardMarkup(buttons), parse_mode='HTML', supports_streaming=True)
        else:
            await update.message.reply_photo(photo=media_url, caption=caption, reply_markup=InlineKeyboardMarkup(buttons), parse_mode='HTML')

    except Exception as e:
        LOGGER.error(f"Fav error: {e}")
        await update.message.reply_text('Error occurred')

async def handle_fav_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    
    try:
        await query.answer()
        data = query.data

        if not (data.startswith('fvc_') or data.startswith('fvx_')):
            return

        parts = data.split('_', 2)
        if len(parts) < 2:
            await query.answer("Invalid data", show_alert=True)
            return

        action = parts[0]

        if action == 'fvc':
            if len(parts) != 3:
                await query.answer("Invalid data", show_alert=True)
                return

            user_id = int(parts[1])
            character_id = str(parts[2])

            if query.from_user.id != user_id:
                await query.answer("Not your request", show_alert=True)
                return

            user = await user_collection.find_one({'id': user_id})
            if not user:
                await query.answer("User not found", show_alert=True)
                return

            character = next((c for c in user.get('characters', []) if str(c.get('id')) == character_id), None)

            if not character:
                await query.answer("Character not found", show_alert=True)
                return

            await user_collection.update_one({'id': user_id}, {'$set': {'favorites': character}})

            success_caption = (
                f"<b>Successfully set as favorite</b>\n\n"
                f"Name: {character.get('name', 'Unknown')}\n"
                f"Anime: {character.get('anime', 'Unknown')}\n"
                f"ID: {character.get('id', 'Unknown')}\n\n"
                f"This character will appear first in your collection"
            )

            await query.edit_message_caption(caption=success_caption, parse_mode='HTML')

        elif action == 'fvx':
            user_id = int(parts[1])

            if query.from_user.id != user_id:
                await query.answer("Not your request", show_alert=True)
                return

            await query.edit_message_caption(caption="Action cancelled", parse_mode='HTML')

    except Exception as e:
        LOGGER.error(f"Callback error: {e}")
        await query.answer(f"Error: {str(e)[:100]}", show_alert=True)

application.add_handler(CommandHandler('fav', fav, block=False))
application.add_handler(CallbackQueryHandler(handle_fav_callback, pattern="^fv[cx]_", block=False))