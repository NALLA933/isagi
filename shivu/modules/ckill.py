import traceback
from html import escape
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import application, user_collection, LOGGER

OWNER_ID = [8420981179, 5147822244]
LOG_CHAT_ID = -1003071132623


async def ckill(update: Update, context: CallbackContext) -> None:
    """Reset user balance to 0 (Owner only)"""
    user_id = update.effective_user.id

    LOGGER.info(f"[CKILL] Command called by user {user_id}")

    if user_id != OWNER_ID:
        await update.message.reply_text("This command is owner only.")
        LOGGER.warning(f"[CKILL] Unauthorized access by user {user_id}")
        return

    target_user_id = None
    target_username = None
    target_first_name = None

    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        target_username = update.message.reply_to_message.from_user.username
        target_first_name = update.message.reply_to_message.from_user.first_name
        LOGGER.info(f"[CKILL] Target from reply: {target_user_id}")
    elif context.args:
        try:
            target_user_id = int(context.args[0])
            LOGGER.info(f"[CKILL] Target from argument: {target_user_id}")
        except ValueError:
            await update.message.reply_text(
                "<b>Invalid user ID</b>\n\n"
                "Usage:\n"
                "Reply to user: <code>/ckill</code>\n"
                "Use ID: <code>/ckill user_id</code>",
                parse_mode='HTML'
            )
            return
    else:
        await update.message.reply_text(
            "Usage:\n"
            "Reply to user: <code>/ckill</code>\n"
            "Use ID: <code>/ckill user_id</code>",
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
            LOGGER.warning(f"[CKILL] User {target_user_id} not found")
            return

        wallet_balance = user.get('balance', 0)
        bank_balance = user.get('bank', 0)
        total_balance = wallet_balance + bank_balance

        if not target_username:
            target_username = user.get('username', 'N/A')
        if not target_first_name:
            target_first_name = user.get('first_name', 'Unknown')

        LOGGER.info(f"[CKILL] Current balance for {target_user_id} - Wallet: {wallet_balance}, Bank: {bank_balance}")

        result = await user_collection.update_one(
            {'id': target_user_id},
            {'$set': {'balance': 0, 'bank': 0}}
        )

        LOGGER.info(f"[CKILL] Database update - modified={result.modified_count}")

        if result.modified_count > 0:
            try:
                from datetime import datetime
                now = datetime.now()
                date_str = now.strftime("%d/%m/%Y")
                time_str = now.strftime("%I:%M %p")

                group_name = update.effective_chat.title if update.effective_chat.type in ['group', 'supergroup'] else "Private Chat"
                group_id = update.effective_chat.id

                log_caption = (
                    f"<b>Balance Reset Log</b>\n"
                    f"{'='*30}\n\n"
                    f"<b>Executed by:</b>\n"
                    f"Name: <a href='tg://user?id={user_id}'>{escape(update.effective_user.first_name)}</a>\n"
                    f"Username: @{update.effective_user.username or 'N/A'}\n"
                    f"ID: <code>{user_id}</code>\n\n"
                    f"<b>Target User:</b>\n"
                    f"Name: <a href='tg://user?id={target_user_id}'>{escape(target_first_name)}</a>\n"
                    f"Username: @{target_username or 'N/A'}\n"
                    f"ID: <code>{target_user_id}</code>\n\n"
                    f"<b>Balance Change:</b>\n"
                    f"Wallet: <code>{wallet_balance:,}</code> to <code>0</code>\n"
                    f"Bank: <code>{bank_balance:,}</code> to <code>0</code>\n"
                    f"Total Removed: <code>{total_balance:,}</code>\n\n"
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
                LOGGER.info(f"[CKILL] Log sent to {LOG_CHAT_ID}")
            except Exception as log_error:
                LOGGER.error(f"[CKILL] Log send failed: {log_error}")
                LOGGER.error(traceback.format_exc())

            await update.message.reply_text(
                f"<b>Balance reset successful</b>\n\n"
                f"<b>User:</b> <a href='tg://user?id={target_user_id}'>{escape(target_first_name)}</a>\n"
                f"<b>ID:</b> <code>{target_user_id}</code>\n\n"
                f"<b>Previous Balance:</b>\n"
                f"Wallet: <code>{wallet_balance:,}</code>\n"
                f"Bank: <code>{bank_balance:,}</code>\n"
                f"Total: <code>{total_balance:,}</code>\n\n"
                f"<b>New Balance:</b> <code>0</code>",
                parse_mode='HTML'
            )

            LOGGER.info(f"[CKILL] Reset complete for {target_user_id} - Removed {total_balance} coins")

        else:
            await update.message.reply_text("Failed to update balance", parse_mode='HTML')
            LOGGER.error(f"[CKILL] Update failed for {target_user_id}")

    except Exception as e:
        LOGGER.error(f"[CKILL ERROR] {e}")
        LOGGER.error(traceback.format_exc())
        await update.message.reply_text(
            f"<b>Error:</b> <code>{str(e)}</code>",
            parse_mode='HTML'
        )


# Direct handler registration
application.add_handler(CommandHandler('ckill', ckill, block=False))
LOGGER.info("[CKILL] Handler registered")