from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from shivu import LOGGER, application, user_collection
from html import escape
import asyncio

# --- CONFIGURATION ---
LOG_CHANNEL_ID = -1002900862232 
GIFT_TIMEOUT = 60
pending_gifts = {}

# --- UTILS ---

def is_video_url(url):
    if not url: return False
    url_lower = url.lower()
    video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v']
    video_patterns = ['/video/', '/videos/', 'video=', 'v=', '.mp4?', '/stream/']
    return any(url_lower.endswith(ext) for ext in video_extensions) or any(pattern in url_lower for pattern in video_patterns)

async def send_log(context: CallbackContext, text: str):
    """Activity ko log channel par bhejta hai"""
    try:
        await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode='HTML')
    except Exception as e:
        LOGGER.error(f"Log sending failed: {e}")

async def reply_media_message(message, media_url, caption, reply_markup=None):
    try:
        is_video = is_video_url(media_url)
        if is_video:
            return await message.reply_video(video=media_url, caption=caption, reply_markup=reply_markup, parse_mode='HTML')
        return await message.reply_photo(photo=media_url, caption=caption, reply_markup=reply_markup, parse_mode='HTML')
    except Exception:
        return await message.reply_text(text=caption, reply_markup=reply_markup, parse_mode='HTML')

# --- HANDLERS ---

async def expire_gift(sender_id, message):
    await asyncio.sleep(GIFT_TIMEOUT)
    if sender_id in pending_gifts:
        try:
            await message.delete()
        except: pass
        pending_gifts.pop(sender_id, None)

async def handle_gift_command(update: Update, context: CallbackContext):
    msg = update.message
    sender_id = msg.from_user.id

    if not msg.reply_to_message:
        return await msg.reply_text("❌ Reply to a user to gift.")

    receiver = msg.reply_to_message.from_user
    if sender_id == receiver.id:
        return await msg.reply_text("❌ You can't gift to yourself.")
    if receiver.is_bot:
        return await msg.reply_text("❌ Bots ko gift nahi de sakte.")

    if len(context.args) != 1:
        return await msg.reply_text("<b>Usage:</b> <code>/gift character_id</code>", parse_mode='HTML')

    char_id = context.args[0]
    sender_data = await user_collection.find_one({'id': sender_id})
    
    # Ownership Check
    character = next((c for c in sender_data.get('characters', []) if str(c.get('id')) == str(char_id)), None)
    
    if not character:
        return await msg.reply_text("❌ Ye character aapke paas nahi hai.")

    if sender_id in pending_gifts:
        return await msg.reply_text("⚠️ Ek gift pehle se pending hai.")

    pending_gifts[sender_id] = {
        'character': character,
        'receiver_id': receiver.id,
        'receiver_name': receiver.first_name,
        'receiver_username': receiver.username
    }

    caption = (
        f"<b>🎁 GIFT REQUEST</b>\n\n"
        f"<b>To:</b> <a href='tg://user?id={receiver.id}'>{escape(receiver.first_name)}</a>\n"
        f"<b>Character:</b> <code>{escape(character['name'])}</code>\n"
        f"<b>ID:</b> #{character['id']}\n\n"
        f"<i>Confirm within {GIFT_TIMEOUT} seconds.</i>"
    )

    keyboard = [[
        InlineKeyboardButton("✅ Confirm", callback_data=f"gift_z:{sender_id}"),
        InlineKeyboardButton("❌ Cancel", callback_data=f"gift_v:{sender_id}")
    ]]

    sent_msg = await reply_media_message(msg, character.get('img_url'), caption, InlineKeyboardMarkup(keyboard))
    asyncio.create_task(expire_gift(sender_id, sent_msg))

async def handle_gift_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    action_data = query.data.split(':')
    action = action_data[0]
    sender_id = int(action_data[1])

    if query.from_user.id != sender_id:
        return await query.answer("⚠️ Not your gift!", show_alert=True)

    gift_data = pending_gifts.get(sender_id)
    if not gift_data:
        await query.message.delete()
        return await query.answer("❌ Request expired.", show_alert=True)

    char = gift_data['character']

    if action == "gift_z": # Confirm
        # Atomic Update: Remove from sender, Push to receiver
        res = await user_collection.update_one(
            {'id': sender_id, 'characters.id': char['id']},
            {'$pull': {'characters': {'id': char['id']}}}
        )

        if res.modified_count > 0:
            await user_collection.update_one(
                {'id': gift_data['receiver_id']},
                {'$push': {'characters': char}},
                upsert=True
            )
            
            await query.edit_message_caption(
                caption=f"<b>✅ GIFT DELIVERED</b>\n\n<b>To:</b> <a href='tg://user?id={gift_data['receiver_id']}'>{escape(gift_data['receiver_name'])}</a>\n<b>Character:</b> <code>{char['name']}</code>",
                parse_mode='HTML'
            )

            # --- SEND LOG ---
            log_msg = (
                f"📢 <b>#GIFT_LOG</b>\n"
                f"👤 <b>Sender:</b> {query.from_user.mention_html()}\n"
                f"👤 <b>Receiver:</b> <a href='tg://user?id={gift_data['receiver_id']}'>{escape(gift_data['receiver_name'])}</a>\n"
                f"🍥 <b>Character:</b> {char['name']} (ID: {char['id']})"
            )
            await send_log(context, log_msg)
        else:
            await query.answer("❌ Error: Transfer failed!", show_alert=True)

    elif action == "gift_v": # Cancel
        await query.message.delete()
        await send_log(context, f"❌ <b>#GIFT_CANCELLED</b>\nSender: {query.from_user.mention_html()} cancelled the gift.")

    pending_gifts.pop(sender_id, None)

# Add Handlers
application.add_handler(CommandHandler("gift", handle_gift_command, block=False))
application.add_handler(CallbackQueryHandler(handle_gift_callback, pattern='^gift_(z|v):', block=False))
