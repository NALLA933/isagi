import asyncio
from telegram import Update
from telegram.ext import CallbackContext, CommandHandler
from shivu import application, top_global_groups_collection, user_collection

# --- CONFIGURATION ---
OWNER_ID = 8420981179

# --- UNICODE SMALL CAPS STYLE ---
class Style:
    HEADER = "📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ ꜱʏꜱᴛᴇᴍ"
    STATUS = "📊 ʙʀᴏᴀᴅᴄᴀꜱᴛ ꜱᴛᴀᴛᴜꜱ"
    SENT = "✅ ꜱᴇɴᴛ :"
    FAILED = "❌ ꜰᴀɪʟᴇᴅ :"
    INVALID = "🗑️ ɪɴᴠᴀʟɪᴅ :"
    TOTAL = "👥 ᴛᴏᴛᴀʟ ᴛᴀʀɢᴇᴛꜱ :"
    LINE = "──────────────────"

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
            await asyncio.sleep(5) # Flood ke liye thoda zyada wait behtar hai
            try:
                await context.bot.forward_message(
                    chat_id=chat_id,
                    from_chat_id=message.chat_id,
                    message_id=message.message_id
                )
                return {"status": "success", "chat_id": chat_id}
            except:
                pass

        if any(x in error_text for x in ["chat not found", "bot was blocked", "user is deactivated", "forbidden", "chat_write_forbidden"]):
            # Invalid chats ko list se hatane ka status
            return {"status": "invalid", "chat_id": chat_id}

        return {"status": "failed", "chat_id": chat_id}

async def broadcast(update: Update, context: CallbackContext) -> None:
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("<b>❌ ɴᴏᴛ ᴀᴜᴛʜᴏʀɪᴢᴇᴅ.</b>", parse_mode='HTML')
        return

    message_to_broadcast = update.message.reply_to_message
    if not message_to_broadcast:
        await update.message.reply_text("<b>❌ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱᴀɢᴇ ᴛᴏ ʙʀᴏᴀᴅᴄᴀꜱᴛ.</b>", parse_mode='HTML')
        return

    # Fetch targets
    all_chats = await top_global_groups_collection.distinct("group_id")
    all_users = await user_collection.distinct("id")
    targets = list(set(all_chats + all_users))

    start_msg = await update.message.reply_text(
        f"<b>{Style.HEADER}</b>\n{Style.LINE}\n🚀 ʙʀᴏᴀᴅᴄᴀꜱᴛɪɴɢ ᴛᴏ {len(targets)} ᴛᴀʀɢᴇᴛꜱ...",
        parse_mode='HTML'
    )

    tasks = [send_message(context, message_to_broadcast, chat_id) for chat_id in targets]
    results = await asyncio.gather(*tasks)

    success = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "failed")
    invalid = sum(1 for r in results if r["status"] == "invalid")

    # Final result with Small Caps font
    final_text = (
        f"<b>{Style.STATUS}</b>\n"
        f"{Style.LINE}\n"
        f"<b>{Style.SENT}</b> <code>{success}</code>\n"
        f"<b>{Style.FAILED}</b> <code>{failed}</code>\n"
        f"<b>{Style.INVALID}</b> <code>{invalid}</code>\n"
        f"{Style.LINE}\n"
        f"<b>{Style.TOTAL}</b> <code>{len(targets)}</code>\n"
        f"✨ ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!"
    )

    await start_msg.edit_text(final_text, parse_mode='HTML')

# Registration
application.add_handler(CommandHandler("broadcast", broadcast, block=False))
