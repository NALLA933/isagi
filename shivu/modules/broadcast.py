from telegram import Update
from telegram.ext import CallbackContext, CommandHandler
import asyncio

from shivu import application, top_global_groups_collection, user_collection

async def send_message(context, message, chat_id):
    try:
        await context.bot.forward_message(
            chat_id=chat_id,
            from_chat_id=message.chat_id,
            message_id=message.message_id
        )
        return True
    except:
        return False

async def broadcast(update: Update, context: CallbackContext) -> None:
    OWNER_ID = 8420981179

    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Not authorized.")
        return

    message_to_broadcast = update.message.reply_to_message
    if not message_to_broadcast:
        await update.message.reply_text("Reply to a message to broadcast.")
        return

    all_chats = await top_global_groups_collection.distinct("group_id")
    all_users = await user_collection.distinct("id")
    targets = list(set(all_chats + all_users))

    await update.message.reply_text(f"Broadcasting to {len(targets)} targets...")

    tasks = [send_message(context, message_to_broadcast, chat_id) for chat_id in targets]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success = sum(1 for r in results if r is True)
    failed = len(results) - success

    await update.message.reply_text(
        f"Broadcast complete.\nSent: {success}\nFailed: {failed}\nTotal: {len(targets)}"
    )

application.add_handler(CommandHandler("broadcast", broadcast, block=False))