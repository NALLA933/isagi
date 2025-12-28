import asyncio
import html
from datetime import datetime, timezone
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from shivu import LOGGER, application, user_collection, collection

# --- CONFIGURATION ---
LOG_CHANNEL_ID = -1002900862232 
GIFT_TIMEOUT = 60
MAX_INVENTORY_SIZE = 1000  # Adjust as needed
pending_gifts = {}
gift_tasks = {}

# --- UNICODE SMALL CAPS STYLE (WITH CUSTOM ꜱ) ---
class Style:
    GIFT = "🎁 ɢɪꜰᴛ ᴛʀᴀɴꜱꜰᴇʀ"
    TO = "👤 ʀᴇᴄɪᴘɪᴇɴᴛ :"
    FROM = "👤 ꜱᴇɴᴅᴇʀ :"
    CHAR = "🍥 ᴄʜᴀʀᴀᴄᴛᴇʀ :"
    ID = "🆔 ɪᴅ :"
    STATUS = "✨ ꜱᴛᴀᴛᴜꜱ :"
    LINE = "──────────────────"
    # Error messages in small caps
    ERROR = "❌ ᴇʀʀᴏʀ"
    WARNING = "⚠️ ᴡᴀʀɴɪɴɢ"
    SUCCESS = "✅ ꜱᴜᴄᴄᴇꜱꜱ"
    INFO = "💡 ɪɴꜰᴏ"
    INV_FULL = "📦 ɪɴᴠᴇɴᴛᴏʀʏ ꜰᴜʟʟ"
    TIMEOUT = "⏰ ᴛɪᴍᴇᴏᴜᴛ"
    NOT_FOUND = "🔍 ɴᴏᴛ ꜰᴏᴜɴᴅ"

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

async def cleanup_pending_gift(sender_id: int, sent_msg=None):
    """Robust cleanup of pending gifts with task management"""
    if sender_id in gift_tasks:
        gift_tasks[sender_id].cancel()
        gift_tasks.pop(sender_id, None)
    
    if sender_id in pending_gifts:
        if sent_msg:
            try:
                await sent_msg.delete()
            except Exception as e:
                LOGGER.error(f"Failed to delete message for sender {sender_id}: {e}")
        pending_gifts.pop(sender_id, None)

async def check_receiver_inventory_size(receiver_id: int) -> bool:
    """Check if receiver has space in inventory using database aggregation"""
    try:
        pipeline = [
            {"$match": {"id": receiver_id}},
            {"$project": {
                "characters_count": {"$size": {"$ifNull": ["$characters", []]}}
            }}
        ]
        
        result = await user_collection.aggregate(pipeline).to_list(length=1)
        
        if result and len(result) > 0:
            current_count = result[0].get('characters_count', 0)
            return current_count < MAX_INVENTORY_SIZE
        
        # User doesn't exist yet, so inventory is empty
        return True
        
    except Exception as e:
        LOGGER.error(f"Error checking inventory size for user {receiver_id}: {e}")
        return False

# --- ATOMIC TRANSFER WITHOUT TRANSACTIONS ---
async def atomic_transfer_character(sender_id: int, receiver_id: int, character: dict) -> bool:
    """
    Atomic character transfer using pull-then-push with rollback
    Returns True if successful, False if failed
    """
    try:
        # Final global collection check
        global_char = await collection.find_one({'id': character['id']})
        if not global_char:
            LOGGER.warning(f"Character {character['id']} not found in global collection during transfer")
            return False
        
        # Step 1: Pull from sender (only if they have it)
        pull_result = await user_collection.update_one(
            {'id': sender_id, 'characters.id': character['id']},
            {'$pull': {'characters': {'id': character['id']}}}
        )
        
        if pull_result.modified_count == 0:
            LOGGER.warning(f"Character {character['id']} not found with sender {sender_id} during transfer")
            return False
        
        LOGGER.info(f"Character {character['id']} successfully pulled from sender {sender_id}")
        
        # Step 2: Push to receiver with inventory size check
        try:
            # Check inventory size atomically in the update query
            push_result = await user_collection.update_one(
                {
                    'id': receiver_id,
                    '$expr': {'$lt': [{'$size': {'$ifNull': ['$characters', []]}}, MAX_INVENTORY_SIZE]}
                },
                {'$push': {'characters': character}},
                upsert=True
            )
            
            if push_result.modified_count == 0 and push_result.upserted_id is None:
                LOGGER.error(f"Failed to push character {character['id']} to receiver {receiver_id} - inventory full or condition failed")
                raise Exception("Push operation failed (inventory full)")
                
            LOGGER.info(f"Character {character['id']} successfully pushed to receiver {receiver_id}")
            return True
            
        except Exception as push_error:
            # Step 3: Rollback - add character back to sender
            LOGGER.error(f"Push failed, rolling back: {push_error}")
            rollback_result = await user_collection.update_one(
                {'id': sender_id},
                {'$push': {'characters': character}}
            )
            
            if rollback_result.modified_count == 0 and rollback_result.upserted_id is None:
                LOGGER.critical(f"ROLLBACK FAILED! Character {character['id']} lost between sender {sender_id} and receiver {receiver_id}")
                # Emergency recovery without circular import
                try:
                    recovery_collection = user_collection.database['lost_characters']
                    await recovery_collection.insert_one({
                        'character': character,
                        'sender_id': sender_id,
                        'receiver_id': receiver_id,
                        'timestamp': datetime.now(timezone.utc),
                        'error': str(push_error),
                        'character_id': character['id'],
                        'character_name': character.get('name', 'Unknown')
                    })
                    LOGGER.info(f"Lost character {character['id']} logged to recovery collection")
                except Exception as recovery_error:
                    LOGGER.error(f"Failed to log lost character to recovery collection: {recovery_error}")
            else:
                LOGGER.info(f"Rollback successful for character {character['id']}")
            
            return False
            
    except Exception as e:
        LOGGER.error(f"Atomic transfer failed: {e}")
        return False

# --- HANDLERS ---

async def handle_gift_command(update: Update, context: CallbackContext):
    msg = update.message
    sender_id = msg.from_user.id

    if not msg.reply_to_message:
        return await msg.reply_text(f"<b>{Style.ERROR} ᴘʟᴇᴀꜱᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜꜱᴇʀ ᴛᴏ ꜱᴇɴᴅ ᴀ ɢɪꜰᴛ.</b>", parse_mode='HTML')

    receiver = msg.reply_to_message.from_user
    if sender_id == receiver.id or receiver.is_bot:
        return await msg.reply_text(f"<b>{Style.ERROR} ɪɴᴠᴀʟɪᴅ ᴜꜱᴇʀ ꜰᴏʀ ɢɪꜰᴛ.</b>", parse_mode='HTML')

    if len(context.args) != 1:
        return await msg.reply_text(f"<b>{Style.INFO} ᴜꜱᴀɢᴇ:</b> <code>/gift character_id</code>", parse_mode='HTML')

    char_id = context.args[0]
    
    # Check if sender has a pending gift already
    if sender_id in pending_gifts:
        return await msg.reply_text(f"<b>{Style.WARNING} ᴏɴᴇ ɢɪꜰᴛ ɪꜱ ᴀʟʀᴇᴀᴅʏ ɪɴ ᴘʀᴏɢʀᴇꜱꜱ...</b>", parse_mode='HTML')
    
    # Check if receiver has full inventory using database aggregation
    has_space = await check_receiver_inventory_size(receiver.id)
    if not has_space:
        return await msg.reply_text(f"<b>{Style.INV_FULL} ʀᴇᴄᴇɪᴠᴇʀ'ꜱ ɪɴᴠᴇɴᴛᴏʀʏ ɪꜱ ꜰᴜʟʟ (ᴍᴀx {MAX_INVENTORY_SIZE}).</b>", parse_mode='HTML')

    # Check if character exists in sender's inventory
    sender_data = await user_collection.find_one({'id': sender_id})
    if not sender_data:
        return await msg.reply_text(f"<b>{Style.ERROR} ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴛʜɪꜱ ᴄʜᴀʀᴀᴄᴛᴇʀ.</b>", parse_mode='HTML')
    
    character = next((c for c in sender_data.get('characters', []) if str(c.get('id')) == str(char_id)), None)
    
    if not character:
        return await msg.reply_text(f"<b>{Style.ERROR} ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴛʜɪꜱ ᴄʜᴀʀᴀᴄᴛᴇʀ.</b>", parse_mode='HTML')
    
    # Verify character exists in global collection
    global_char = await collection.find_one({'id': character['id']})
    if not global_char:
        return await msg.reply_text(f"<b>{Style.ERROR} ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ ɪɴ ɢʟᴏʙᴀʟ ᴄᴏʟʟᴇᴄᴛɪᴏɴ.</b>", parse_mode='HTML')

    pending_gifts[sender_id] = {
        'character': character,
        'receiver_id': receiver.id,
        'receiver_name': receiver.first_name,
        'message_id': None,
        'created_at': datetime.now(timezone.utc),
        'global_check': True  # Mark that we've checked global collection
    }

    # Aesthetic Small Caps Caption with custom 'ꜱ'
    caption = (
        f"<b>{Style.GIFT}</b>\n"
        f"{Style.LINE}\n"
        f"<b>{Style.TO}</b> <a href='tg://user?id={receiver.id}'>{html.escape(receiver.first_name)}</a>\n"
        f"<b>{Style.CHAR}</b> <code>{html.escape(character['name'])}</code>\n"
        f"<b>{Style.ID}</b> <code>#{character['id']}</code>\n"
        f"{Style.LINE}\n"
        f"<i>⏳ ᴄᴏɴꜰɪʀᴍ ᴡɪᴛʜɪɴ {GIFT_TIMEOUT}ꜱ ᴛᴏ ꜱᴇɴᴅ.</i>"
    )

    keyboard = [[
        InlineKeyboardButton("✅ ᴄᴏɴꜰɪʀᴍ", callback_data=f"gift_z:{sender_id}"),
        InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data=f"gift_v:{sender_id}")
    ]]

    sent_msg = await reply_media_message(msg, character.get('img_url'), caption, InlineKeyboardMarkup(keyboard))
    
    if sent_msg:
        pending_gifts[sender_id]['message_id'] = sent_msg.message_id
    
    async def expire():
        await asyncio.sleep(GIFT_TIMEOUT)
        if sender_id in pending_gifts:
            await cleanup_pending_gift(sender_id, sent_msg)
    
    # Store task for proper cleanup
    gift_tasks[sender_id] = asyncio.create_task(expire())

async def handle_gift_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    action_data = query.data.split(':')
    action, sender_id = action_data[0], int(action_data[1])

    if query.from_user.id != sender_id:
        return await query.answer(f"{Style.WARNING} ɴᴏᴛ ʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ!", show_alert=True)

    gift_data = pending_gifts.get(sender_id)
    if not gift_data:
        try:
            await query.message.delete()
        except:
            pass
        return await query.answer(f"{Style.TIMEOUT} ʀᴇǫᴜᴇꜱᴛ ᴇxᴘɪʀᴇᴅ.", show_alert=True)

    char = gift_data['character']
    receiver_id = gift_data['receiver_id']
    receiver_name = gift_data['receiver_name']

    if action == "gift_z":
        # IMMEDIATE BUTTON PROTECTION: Disable buttons before any processing
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception as e:
            LOGGER.error(f"Failed to disable buttons for sender {sender_id}: {e}")
        
        # PREVENT DOUBLE PROCESSING: Remove from pending immediately
        pending_gifts.pop(sender_id, None)
        
        # Cancel the expiration task
        if sender_id in gift_tasks:
            gift_tasks[sender_id].cancel()
            gift_tasks.pop(sender_id, None)
        
        try:
            # FINAL VERIFICATION: Check sender still owns the character
            final_check = await user_collection.find_one({
                'id': sender_id,
                'characters.id': char['id']
            })
            
            if not final_check:
                await query.message.delete()
                return await query.answer(f"{Style.ERROR} ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏ ʟᴏɴɢᴇʀ ᴀᴠᴀɪʟᴀʙʟᴇ.", show_alert=True)
            
            # Final global collection check
            global_char = await collection.find_one({'id': char['id']})
            if not global_char:
                await query.message.delete()
                return await query.answer(f"{Style.ERROR} ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏ ʟᴏɴɢᴇʀ ᴇxɪꜱᴛꜱ ɪɴ ᴛʜᴇ ɢᴀᴍᴇ.", show_alert=True)
            
            # Perform atomic transfer
            transfer_success = await atomic_transfer_character(sender_id, receiver_id, char)
            
            if transfer_success:
                # Get updated receiver data for logging
                updated_receiver = await user_collection.find_one({'id': receiver_id})
                receiver_char_count = len(updated_receiver.get('characters', [])) if updated_receiver else 0
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                
                final_caption = (
                    f"<b>🎊 ɢɪꜰᴛ ᴅᴇʟɪᴠᴇʀᴇᴅ 🎊</b>\n"
                    f"{Style.LINE}\n"
                    f"<b>{Style.TO}</b> <a href='tg://user?id={receiver_id}'>{html.escape(receiver_name)}</a>\n"
                    f"<b>{Style.CHAR}</b> <code>{char['name']}</code>\n"
                    f"{Style.LINE}\n"
                    f"<i>✓ ᴄʜᴀʀᴀᴄᴛᴇʀ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴛʀᴀɴꜱꜰᴇʀʀᴇᴅ.</i>"
                )
                await query.edit_message_caption(caption=final_caption, parse_mode='HTML')
                
                # Optimized single formatted log string
                log_msg = (
                    f"📢 <b>#ɢɪꜰᴛ_ʟᴏɢ</b>\n"
                    f"🕒 <b>ᴛɪᴍᴇꜱᴛᴀᴍᴘ:</b> <code>{timestamp}</code>\n"
                    f"{Style.LINE}\n"
                    f"<b>{Style.FROM}</b> {query.from_user.mention_html()}\n"
                    f"<b>{Style.TO}</b> <a href='tg://user?id={receiver_id}'>{html.escape(receiver_name)}</a>\n"
                    f"<b>{Style.CHAR}</b> {char['name']} (ɪᴅ: {char['id']})\n"
                    f"<b>📊 ʀᴇᴄᴇɪᴠᴇʀ'ꜱ ᴛᴏᴛᴀʟ:</b> {receiver_char_count}/{MAX_INVENTORY_SIZE} ᴄʜᴀʀᴀᴄᴛᴇʀꜱ\n"
                    f"{Style.LINE}\n"
                    f"<b>{Style.STATUS}</b> {Style.SUCCESS}"
                )
                await send_log(context, log_msg)
                
                # Send confirmation to receiver
                try:
                    receiver_msg = (
                        f"<b>🎁 ɢɪꜰᴛ ʀᴇᴄᴇɪᴠᴇᴅ!</b>\n"
                        f"{Style.LINE}\n"
                        f"<b>{Style.FROM}</b> {query.from_user.mention_html()}\n"
                        f"<b>{Style.CHAR}</b> {char['name']}\n"
                        f"<b>📊 ʏᴏᴜʀ ᴛᴏᴛᴀʟ:</b> {receiver_char_count}/{MAX_INVENTORY_SIZE} ᴄʜᴀʀᴀᴄᴛᴇʀꜱ\n"
                        f"{Style.LINE}\n"
                        f"<i>ᴜꜱᴇ /collection ᴛᴏ ᴠɪᴇᴡ ʏᴏᴜʀ ᴄʜᴀʀᴀᴄᴛᴇʀꜱ.</i>"
                    )
                    await context.bot.send_message(
                        chat_id=receiver_id,
                        text=receiver_msg,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    LOGGER.error(f"Failed to notify receiver {receiver_id}: {e}")
                    
            else:
                # Transfer failed - character should still be with sender due to rollback
                await query.message.delete()
                await query.answer(f"{Style.ERROR} ᴛʀᴀɴꜱꜰᴇʀ ꜰᴀɪʟᴇᴅ. ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ʟᴏꜱᴛ.", show_alert=True)
                
                # Log the failure
                log_msg = (
                    f"❌ <b>#ɢɪꜰᴛ_ꜰᴀɪʟᴜʀᴇ</b>\n"
                    f"🕒 <b>ᴛɪᴍᴇꜱᴛᴀᴍᴘ:</b> <code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</code>\n"
                    f"{Style.LINE}\n"
                    f"<b>{Style.FROM}</b> {query.from_user.mention_html()}\n"
                    f"<b>{Style.TO}</b> <a href='tg://user?id={receiver_id}'>{html.escape(receiver_name)}</a>\n"
                    f"<b>{Style.CHAR}</b> {char['name']} (ɪᴅ: {char['id']})\n"
                    f"{Style.LINE}\n"
                    f"<b>{Style.STATUS}</b> {Style.ERROR}"
                )
                await send_log(context, log_msg)
        
        except Exception as e:
            LOGGER.error(f"Unexpected error in gift transfer for sender {sender_id}: {e}")
            await query.message.delete()
            await query.answer(f"{Style.ERROR} ᴀɴ ᴜɴᴇxᴘᴇᴄᴛᴇᴅ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ.", show_alert=True)
    
    elif action == "gift_v":
        # Immediately remove from pending
        pending_gifts.pop(sender_id, None)
        
        # Cancel the expiration task
        if sender_id in gift_tasks:
            gift_tasks[sender_id].cancel()
            gift_tasks.pop(sender_id, None)
        
        await query.message.delete()
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        log_msg = (
            f"❌ <b>#ɢɪꜰᴛ_ᴄᴀɴᴄᴇʟʟᴇᴅ</b>\n"
            f"🕒 <b>ᴛɪᴍᴇꜱᴛᴀᴍᴘ:</b> <code>{timestamp}</code>\n"
            f"{Style.LINE}\n"
            f"<b>{Style.FROM}</b> {query.from_user.mention_html()}\n"
            f"<b>{Style.CHAR}</b> {char['name']} (ɪᴅ: {char['id']})\n"
            f"{Style.LINE}\n"
            f"<b>{Style.STATUS}</b> ᴄᴀɴᴄᴇʟʟᴇᴅ ❌"
        )
        await send_log(context, log_msg)

# Register Handlers
application.add_handler(CommandHandler("gift", handle_gift_command, block=False))
application.add_handler(CallbackQueryHandler(handle_gift_callback, pattern='^gift_(z|v):', block=False))

# Background cleanup task for stale pending gifts
async def cleanup_stale_gifts():
    """Periodically clean up stale pending gifts"""
    while True:
        try:
            now = datetime.now(timezone.utc)
            stale_senders = []
            
            for sender_id, gift_data in pending_gifts.items():
                if (now - gift_data['created_at']).total_seconds() > GIFT_TIMEOUT + 30:  # Extra 30s buffer
                    stale_senders.append(sender_id)
            
            for sender_id in stale_senders:
                LOGGER.warning(f"Cleaning up stale gift for sender {sender_id}")
                await cleanup_pending_gift(sender_id)
                
        except Exception as e:
            LOGGER.error(f"Error in cleanup_stale_gifts: {e}")
        
        await asyncio.sleep(300)  # Run every 5 minutes

# Start background cleanup when bot starts
async def on_bot_start():
    asyncio.create_task(cleanup_stale_gifts())
    LOGGER.info("Gift system cleanup task started")
    LOGGER.info("Gift system initialized with maximum inventory size: %s", MAX_INVENTORY_SIZE)

# Initialize the cleanup task
try:
    # Check if we're in an async context
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.create_task(on_bot_start())
    else:
        loop.run_until_complete(on_bot_start())
except Exception as e:
    LOGGER.error(f"Failed to start gift cleanup task: {e}")