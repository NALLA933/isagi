from telegram import Update
from telegram.ext import CallbackContext, CommandHandler
import asyncio
import traceback

from shivu import application, top_global_groups_collection, user_collection

async def broadcast(update: Update, context: CallbackContext) -> None:
    OWNER_ID = 8420981179

    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    message_to_broadcast = update.message.reply_to_message
    if message_to_broadcast is None:
        await update.message.reply_text("Please reply to a message to broadcast.")
        return

    # Fetch chats and users
    all_chats = await top_global_groups_collection.distinct("group_id")
    all_users = await user_collection.distinct("id")
    shuyaa = list(set(all_chats + all_users))

    failed_sends = 0
    success_sends = 0

    await update.message.reply_text(f"Broadcast started to {len(shuyaa)} chats/users...")

    for index, chat_id in enumerate(shuyaa, start=1):
        try:
            await context.bot.forward_message(
                chat_id=chat_id,
                from_chat_id=message_to_broadcast.chat_id,
                message_id=message_to_broadcast.message_id
            )
            success_sends += 1

        except Exception as e:
            # Retry once after delay if flood-wait or temporary issue
            err_text = str(e).lower()

            # Handle rate-limit (FloodWait)
            if "flood" in err_text or "retry" in err_text:
                wait_time = 3
                print(f"[RateLimit] Waiting {wait_time}s before retry for {chat_id}")
                await asyncio.sleep(wait_time)
                try:
                    await context.bot.forward_message(
                        chat_id=chat_id,
                        from_chat_id=message_to_broadcast.chat_id,
                        message_id=message_to_broadcast.message_id
                    )
                    success_sends += 1
                    continue
                except Exception:
                    pass

            # Ignore deleted or blocked users
            if any(x in err_text for x in [
                "chat not found", "bot was blocked", "user is deactivated", "chat_write_forbidden"
            ]):
                print(f"Skipping invalid chat/user {chat_id}")
                continue

            failed_sends += 1
            print(f"Failed to send message to {chat_id}: {e}")
            traceback.print_exc()

        # Small delay to avoid hitting flood limits
        await asyncio.sleep(0.6)

        # Periodic progress logs
        if index % 50 == 0:
            print(f"[Broadcast] Progress: {index}/{len(shuyaa)}")

    await update.message.reply_text(
        f"✅ Broadcast complete.\n\n"
        f"📤 Sent successfully: {success_sends}\n"
        f"❌ Failed: {failed_sends}\n"
        f"👥 Total: {len(shuyaa)}"
    )

# Register command
application.add_handler(CommandHandler("broadcast", broadcast, block=False))