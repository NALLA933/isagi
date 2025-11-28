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
        return {"status": "success", "chat_id": chat_id}
    except Exception as e:
        error_text = str(e).lower()

        if "retry after" in error_text or "flood" in error_text:
            await asyncio.sleep(2)
            try:
                await context.bot.forward_message(
                    chat_id=chat_id,
                    from_chat_id=message.chat_id,
                    message_id=message.message_id
                )
                return {"status": "success", "chat_id": chat_id}
            except:
                pass

        if any(x in error_text for x in ["chat not found", "bot was blocked", "user is deactivated", "forbidden"]):
            return {"status": "invalid", "chat_id": chat_id}

        return {"status": "failed", "chat_id": chat_id}

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
    results = await asyncio.gather(*tasks)

    success = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "failed")
    invalid = sum(1 for r in results if r["status"] == "invalid")

    await update.message.reply_text(
        f"Broadcast complete.\n"
        f"Sent: {success}\n"
        f"Failed: {failed}\n"
        f"Invalid: {invalid}\n"
        f"Total: {len(targets)}"
    )

application.add_handler(CommandHandler("broadcast", broadcast, block=False))