import traceback
from html import escape
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import application, user_collection, LOGGER

OWNER_ID = 8420981179
LOG_CHAT_ID = -1003071132623


async def kill(update: Update, context: CallbackContext) -> None:
    """Remove all characters from user collection (Owner only)"""
    user_id = update.effective_user.id

    LOGGER.info(f"[KILL] Command called by user {user_id}")

    if user_id != OWNER_ID:
        await update.message.reply_text("This command is owner only.")
        LOGGER.warning(f"[KILL] Unauthorized access by user {user_id}")
        return

    target_user_id = None
    target_username = None
    target_first_name = None

    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        target_username = update.message.reply_to_message.from_user.username
        target_first_name = update.message.reply_to_message.from_user.first_name
        LOGGER.info(f"[KILL] Target from reply: {target_user_id}")
    elif context.args:
        try:
            target_user_id = int(context.args[0])
            LOGGER.info(f"[KILL] Target from argument: {target_user_id}")
        except ValueError:
            await update.message.reply_text(
                "<b>Invalid user ID</b>\n\n"
                "Usage:\n"
                "Reply to user: <code>/kill</code>\n"
                "Use ID: <code>/kill user_id</code>",
                parse_mode='HTML'
            )
            return
    else:
        await update.message.reply_text(
            "Usage:\n"
            "Reply to user: <code>/kill</code>\n"
            "Use ID: <code>/kill user_id</code>",
            parse_mode='HTML'
        )
        return

    try:
        user = await user_collection.find_one({'id': target_user_id})

        if not user:
            await update.message.reply_text(
                f"User not found\nID: <code>{target_user_id}</code>",
                parse_mode='HTML'
            )
            LOGGER.warning(f"[KILL] User {target_user_id} not found")
            return

        characters = user.get('characters', [])
        character_count = len(characters)

        if not target_username:
            target_username = user.get('username', 'N/A')
        if not target_first_name:
            target_first_name = user.get('first_name', 'Unknown')

        LOGGER.info(f"[KILL] Character count for {target_user_id}: {character_count}")

        if character_count == 0:
            await update.message.reply_text(
                f"User has no characters\n\n"
                f"<b>User:</b> <a href='tg://user?id={target_user_id}'>{escape(target_first_name)}</a>\n"
                f"<b>ID:</b> <code>{target_user_id}</code>",
                parse_mode='HTML'
            )
            return

        character_details = []
        for i, char in enumerate(characters[:10]):
            char_name = char.get('name', 'Unknown')
            char_anime = char.get('anime', 'Unknown')
            char_id = char.get('id', 'N/A')
            character_details.append(f"{i+1}. {char_name} ({char_anime}) - ID: {char_id}")

        result = await user_collection.update_one(
            {'id': target_user_id},
            {'$set': {'characters': []}}
        )

        LOGGER.info(f"[KILL] Database update - modified={result.modified_count}")

        if result.modified_count > 0:
            try:
                from datetime import datetime
                now = datetime.now()
                date_str = now.strftime("%d/%m/%Y")
                time_str = now.strftime("%I:%M %p")

                group_name = update.effective_chat.title if update.effective_chat.type in ['group', 'supergroup'] else "Private Chat"
                group_id = update.effective_chat.id

                char_list = "\n".join(character_details)
                if character_count > 10:
                    char_list += f"\n... and {character_count - 10} more"

                log_caption = (
                    f"<b>Characters Wiped Log</b>\n"
                    f"{'='*30}\n\n"
                    f"<b>Executed by:</b>\n"
                    f"Name: <a href='tg://user?id={user_id}'>{escape(update.effective_user.first_name)}</a>\n"
                    f"Username: @{update.effective_user.username or 'N/A'}\n"
                    f"ID: <code>{user_id}</code>\n\n"
                    f"<b>Target User:</b>\n"
                    f"Name: <a href='tg://user?id={target_user_id}'>{escape(target_first_name)}</a>\n"
                    f"Username: @{target_username or 'N/A'}\n"
                    f"ID: <code>{target_user_id}</code>\n\n"
                    f"<b>Characters Removed:</b>\n"
                    f"Total: <code>{character_count}</code> characters\n\n"
                    f"<b>Top 10 Characters:</b>\n"
                    f"<code>{char_list}</code>\n\n"
                    f"<b>Location:</b>\n"
                    f"Group: <code>{escape(group_name)}</code>\n"
                    f"Group ID: <code>{group_id}</code>\n\n"
                    f"<b>Timestamp:</b>\n"
                    f"Date: <code>{date_str}</code>\n"
                    f"Time: <code>{time_str}</code>"
                )

                await context.bot.send_message(
                    chat_id=LOG_CHAT_ID,
                    text=log_caption,
                    parse_mode='HTML'
                )
                LOGGER.info(f"[KILL] Log sent to {LOG_CHAT_ID}")
            except Exception as log_error:
                LOGGER.error(f"[KILL] Log send failed: {log_error}")
                LOGGER.error(traceback.format_exc())

            await update.message.reply_text(
                f"<b>Characters wiped successfully</b>\n\n"
                f"<b>User:</b> <a href='tg://user?id={target_user_id}'>{escape(target_first_name)}</a>\n"
                f"<b>ID:</b> <code>{target_user_id}</code>\n\n"
                f"<b>Removed:</b> <code>{character_count}</code> characters\n\n"
                f"<b>Top 10 Removed:</b>\n"
                f"<code>{chr(10).join(character_details[:10])}</code>",
                parse_mode='HTML'
            )

            LOGGER.info(f"[KILL] Removed {character_count} characters from {target_user_id}")

        else:
            await update.message.reply_text("Failed to remove characters", parse_mode='HTML')
            LOGGER.error(f"[KILL] Removal failed for {target_user_id}")

    except Exception as e:
        LOGGER.error(f"[KILL ERROR] {e}")
        LOGGER.error(traceback.format_exc())
        await update.message.reply_text(
            f"<b>Error:</b> <code>{str(e)}</code>",
            parse_mode='HTML'
        )


# Direct handler registration
application.add_handler(CommandHandler('kill', kill, block=False))
LOGGER.info("[KILL] Handler registered")