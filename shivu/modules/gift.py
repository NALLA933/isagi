import asyncio
import html
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from shivu import LOGGER, application, user_collection

# --- CONFIGURATION ---
LOG_CHANNEL_ID = -1002900862232 
GIFT_TIMEOUT = 60
pending_gifts = {}

# --- UNICODE SMALL CAPS STYLE ---
class Style:
    GIFT = "🎁 ɢɪғᴛ ᴛʀᴀɴsғᴇʀ"
    TO = "👤 ʀᴇᴄɪᴘɪᴇɴᴛ :"
    FROM = "👤 sᴇɴᴅᴇʀ :"
    CHAR = "🍥 ᴄʜᴀʀᴀᴄᴛᴇʀ :"
    ID = "🆔 ɪᴅ :"
    STATUS = "✨ sᴛᴀᴛᴜs :"
    LINE = "──────────────────"

# --- UTILS ---

def is_video_url(url):
    if not url: return False
    url_lower = url.lower()
    video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v']
    video_patterns = ['/video/', '/videos/', 'video=', 'v=', '.mp4?', '/stream/']
    return any(url_lower.endswith(ext) for ext in video_extensions) or any(pattern in url_lower for pattern in video_patterns)

async def send_log(context: CallbackContext, text: str):
    try:
        await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode='HTML')
    except Exception as e:
        LOGGER.error(f"Log failed: {e}")

async def reply_media_message(message, media_url, caption, reply_markup=None):
    try:
        is_video = is_video_url(media_url)
        if is_video:
            return await message.reply_video(video=media_url, caption=caption, reply_markup=reply_markup, parse_mode='HTML')
        return await message.reply_photo(photo=media_url, caption=caption, reply_markup=reply_markup, parse_mode='HTML')
    except Exception:
        return await message.reply_text(text=caption, reply_markup=reply_markup, parse_mode='HTML')

# --- HANDLERS ---

async def handle_gift_command(update: Update, context: CallbackContext):
    msg = update.message
    sender_id = msg.from_user.id

    if not msg.reply_to_message:
        return await msg.reply_text("<b>❌ Please reply to a user to send a gift.</b>", parse_mode='HTML')

    receiver = msg.reply_to_message.from_user
    if sender_id == receiver.id or receiver.is_bot:
        return await msg.reply_text("<b>❌ Invalid User for gift.</b>", parse_mode='HTML')

    if len(context.args) != 1:
        return await msg.reply_text("<b>💡 Usage:</b> <code>/gift character_id</code>", parse_mode='HTML')

    char_id = context.args[0]
    sender_data = await user_collection.find_one({'id': sender_id})
    character = next((c for c in sender_data.get('characters', []) if str(c.get('id')) == str(char_id)), None)
    
    if not character:
        return await msg.reply_text("<b>❌ You don't own this character.</b>", parse_mode='HTML')

    if sender_id in pending_gifts:
        return await msg.reply_text("<b>⚠️ One gift is already in progress...</b>", parse_mode='HTML')

    pending_gifts[sender_id] = {
        'character': character,
        'receiver_id': receiver.id,
        'receiver_name': receiver.first_name
    }

    # Aesthetic Small Caps Caption
    caption = (
        f"<b>{Style.GIFT}</b>\n"
        f"{Style.LINE}\n"
        f"<b>{Style.TO}</b> <a href='tg://user?id={receiver.id}'>{html.escape(receiver.first_name)}</a>\n"
        f"<b>{Style.CHAR}</b> <code>{html.escape(character['name'])}</code>\n"
        f"<b>{Style.ID}</b> <code>#{character['id']}</code>\n"
        f"{Style.LINE}\n"
        f"<i>⏳ ᴄᴏɴғɪʀᴍ ᴡɪᴛʜɪɴ {GIFT_TIMEOUT}s ᴛᴏ sᴇɴᴅ.</i>"
    )

    keyboard = [[
        InlineKeyboardButton("✅ ᴄᴏɴғɪʀᴍ", callback_data=f"gift_z:{sender_id}"),
        InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data=f"gift_v:{sender_id}")
    ]]

    sent_msg = await reply_media_message(msg, character.get('img_url'), caption, InlineKeyboardMarkup(keyboard))
    
    # Auto-expiry task
    async def expire():
        await asyncio.sleep(GIFT_TIMEOUT)
        if sender_id in pending_gifts:
            try: await sent_msg.delete()
            except: pass
            pending_gifts.pop(sender_id, None)
    asyncio.create_task(expire())

async def handle_gift_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    action_data = query.data.split(':')
    action, sender_id = action_data[0], int(action_data[1])

    if query.from_user.id != sender_id:
        return await query.answer("⚠️ Not your request!", show_alert=True)

    gift_data = pending_gifts.get(sender_id)
    if not gift_data:
        try: await query.message.delete()
        except: pass
        return await query.answer("❌ Request Expired.", show_alert=True)

    char = gift_data['character']

    if action == "gift_z":
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
            
            # Final Success Design
            final_caption = (
                f"<b>🎊 ɢɪғᴛ ᴅᴇʟɪᴠᴇʀᴇᴅ 🎊</b>\n"
                f"{Style.LINE}\n"
                f"<b>{Style.TO}</b> <a href='tg://user?id={gift_data['receiver_id']}'>{html.escape(gift_data['receiver_name'])}</a>\n"
                f"<b>{Style.CHAR}</b> <code>{char['name']}</code>\n"
                f"{Style.LINE}\n"
                f"<i>✓ ᴄʜᴀʀᴀᴄᴛᴇʀ sᴜᴄᴄᴇssғᴜʟʟʏ ᴛʀᴀɴsғᴇʀʀᴇᴅ.</i>"
            )
            await query.edit_message_caption(caption=final_caption, parse_mode='HTML')

            log_msg = (
                f"📢 <b>#ɢɪғᴛ_ʟᴏɢ</b>\n\n"
                f"<b>{Style.FROM}</b> {query.from_user.mention_html()}\n"
                f"<b>{Style.TO}</b> <a href='tg://user?id={gift_data['receiver_id']}'>{html.escape(gift_data['receiver_name'])}</a>\n"
                f"<b>{Style.CHAR}</b> {char['name']} (ID: {char['id']})\n"
                f"<b>{Style.STATUS}</b> sᴜᴄᴄᴇss ✅"
            )
            await send_log(context, log_msg)
        else:
            await query.answer("❌ Transfer failed.", show_alert=True)

    elif action == "gift_v":
        await query.message.delete()
        await send_log(context, f"❌ <b>#ɢɪғᴛ_ᴄᴀɴᴄᴇʟʟᴇᴅ</b>\nʙʏ: {query.from_user.mention_html()}")

    pending_gifts.pop(sender_id, None)

# Register Handlers
application.add_handler(CommandHandler("gift", handle_gift_command, block=False))
application.add_handler(CallbackQueryHandler(handle_gift_callback, pattern='^gift_(z|v):', block=False))
