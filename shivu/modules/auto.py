from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from shivu import application, user_collection, collection, LOGGER
import asyncio

# Owner IDs from your request
OWNER_IDS = [8420981179, 8297659126]

async def lock(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    
    # Check if user is owner
    if user_id not in OWNER_IDS:
        await update.message.reply_text("❌ This command is for owners only!")
        return

    if not context.args:
        await update.message.reply_text(
            "❌ Please provide character ID!\n"
            "Usage: /lock <character_id>\n"
            "Example: /lock 12345"
        )
        return

    character_id = str(context.args[0])

    try:
        # Check if character exists in main collection
        character = await collection.find_one({'id': character_id})
        
        if not character:
            await update.message.reply_text("❌ Character not found in database!")
            return

        # Import locked_characters collection
        from shivu import locked_characters
        
        # Check if already locked
        existing_lock = await locked_characters.find_one({'character_id': character_id})
        
        if existing_lock:
            # Character is already locked
            await update.message.reply_text(
                f"⚠️ Character is already locked!\n\n"
                f"Name: {character.get('name', 'Unknown')}\n"
                f"Anime: {character.get('anime', 'Unknown')}\n"
                f"ID: {character_id}\n\n"
                f"🔒 This character is permanently locked and will never spawn."
            )
            return

        # Ask for confirmation before permanent lock
        buttons = [[
            InlineKeyboardButton("✅ PERMANENTLY LOCK", callback_data=f"perm_lock_{character_id}_{user_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"lock_cancel_{user_id}")
        ]]
        
        warning_text = (
            f"⚠️ ⚠️ ⚠️ **WARNING: PERMANENT LOCK** ⚠️ ⚠️ ⚠️\n\n"
            f"Character: {character.get('name', 'Unknown')}\n"
            f"Anime: {character.get('anime', 'Unknown')}\n"
            f"ID: `{character_id}`\n\n"
            f"❌ **This action is IRREVERSIBLE!**\n"
            f"❌ Character will NEVER spawn again\n"
            f"❌ Character cannot be unlocked\n"
            f"❌ Character is removed from spawning pool permanently\n\n"
            f"Are you absolutely sure?"
        )
        
        media_url = character.get('img_url')
        
        if character.get('is_video', False):
            await update.message.reply_video(
                video=media_url,
                caption=warning_text,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode='Markdown',
                supports_streaming=True
            )
        else:
            await update.message.reply_photo(
                photo=media_url,
                caption=warning_text,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode='Markdown'
            )

    except Exception as e:
        LOGGER.error(f"Lock command error: {e}")
        await update.message.reply_text("❌ Error occurred")

async def lock_confirm(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    
    try:
        await query.answer()
        data = query.data
        
        if data.startswith('perm_lock_'):
            # Format: perm_lock_characterid_userid
            parts = data.split('_')
            if len(parts) != 4:
                await query.answer("Invalid data", show_alert=True)
                return
                
            character_id = parts[2]
            owner_id = int(parts[3])
            
            # Verify owner
            if query.from_user.id != owner_id:
                await query.answer("❌ You are not authorized!", show_alert=True)
                return
            
            # Get character details
            character = await collection.find_one({'id': character_id})
            if not character:
                await query.answer("Character not found", show_alert=True)
                return
            
            # Import locked_characters collection
            from shivu import locked_characters
            
            # Check if already locked (double check)
            existing_lock = await locked_characters.find_one({'character_id': character_id})
            if existing_lock:
                await query.edit_message_caption(
                    caption="⚠️ Character was already locked by another process!",
                    parse_mode='Markdown'
                )
                return
            
            # Create permanent lock entry
            lock_data = {
                'character_id': character_id,
                'name': character.get('name', 'Unknown'),
                'anime': character.get('anime', 'Unknown'),
                'img_url': character.get('img_url', ''),
                'is_video': character.get('is_video', False),
                'locked_by': owner_id,
                'locked_at': query.message.date,
                'permanent': True,
                'locked_username': query.from_user.username or query.from_user.first_name,
                'note': "PERMANENTLY LOCKED - CANNOT BE UNLOCKED"
            }
            
            # Insert into locked collection
            await locked_characters.insert_one(lock_data)
            
            # Success message
            success_msg = (
                f"🔒 **PERMANENTLY LOCKED!**\n\n"
                f"Character: {character.get('name', 'Unknown')}\n"
                f"Anime: {character.get('anime', 'Unknown')}\n"
                f"ID: `{character_id}`\n\n"
                f"❌ **This character will NEVER spawn again!**\n"
                f"⛔ No unlock command available\n"
                f"🔐 Locked by: {query.from_user.mention_html()}\n"
                f"📅 Locked at: {query.message.date.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"⚠️ **This action is irreversible!**"
            )
            
            await query.edit_message_caption(
                caption=success_msg,
                parse_mode='HTML'
            )
            
            LOGGER.info(f"Character {character_id} permanently locked by {owner_id}")
            
        elif data.startswith('lock_cancel_'):
            owner_id = int(data.split('_')[2])
            
            if query.from_user.id != owner_id:
                await query.answer("❌ Not your request!", show_alert=True)
                return
            
            await query.edit_message_caption(
                caption="✅ Lock operation cancelled.",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        LOGGER.error(f"Lock confirm error: {e}")
        await query.answer(f"Error: {str(e)[:100]}", show_alert=True)

async def lockedlist(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    
    # Check if user is owner
    if user_id not in OWNER_IDS:
        await update.message.reply_text("❌ This command is for owners only!")
        return
    
    try:
        from shivu import locked_characters
        
        # Get all locked characters
        locked_chars = await locked_characters.find().sort('locked_at', -1).to_list(length=1000)
        
        if not locked_chars:
            await update.message.reply_text("✅ No characters are locked!")
            return
        
        # Create paginated message
        page = int(context.args[0]) if context.args and context.args[0].isdigit() else 1
        per_page = 15
        total = len(locked_chars)
        total_pages = (total + per_page - 1) // per_page
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * per_page
        end_idx = min(start_idx + per_page, total)
        
        message = f"🔒 **PERMANENTLY LOCKED CHARACTERS**\n"
        message += f"Page: {page}/{total_pages} | Total: {total} characters\n\n"
        
        for i, char in enumerate(locked_chars[start_idx:end_idx], start_idx + 1):
            lock_date = char.get('locked_at', 'Unknown')
            if hasattr(lock_date, 'strftime'):
                lock_date = lock_date.strftime('%Y-%m-%d')
            
            message += (
                f"{i}. **{char.get('name', 'Unknown')}**\n"
                f"   📺 {char.get('anime', 'Unknown')}\n"
                f"   🆔 `{char.get('character_id')}`\n"
                f"   🔒 {lock_date} | By: {char.get('locked_username', 'Owner')}\n"
                f"   ─────────────────────\n"
            )
        
        message += f"\n⚠️ **These {total} characters are permanently locked and will never spawn!**"
        
        # Add pagination buttons
        buttons = []
        if total_pages > 1:
            row = []
            if page > 1:
                row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"locklist_{page-1}"))
            row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="locklist_current"))
            if page < total_pages:
                row.append(InlineKeyboardButton("Next ➡️", callback_data=f"locklist_{page+1}"))
            buttons.append(row)
        
        if len(message) > 4000:
            # Split message if too long
            parts = [message[i:i+4000] for i in range(0, len(message), 4000)]
            for part in parts[:1]:  # Send first part with buttons
                await update.message.reply_text(
                    part,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
                )
            for part in parts[1:]:
                await update.message.reply_text(part, parse_mode='Markdown')
        else:
            await update.message.reply_text(
                message,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
            )
    
    except Exception as e:
        LOGGER.error(f"Lockedlist error: {e}")
        await update.message.reply_text("❌ Error occurred")

async def lockedlist_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    
    try:
        await query.answer()
        
        if not query.data.startswith('locklist_'):
            return
        
        data = query.data
        if data == "locklist_current":
            await query.answer("Current page", show_alert=False)
            return
        
        page = int(data.split('_')[1])
        
        from shivu import locked_characters
        locked_chars = await locked_characters.find().sort('locked_at', -1).to_list(length=1000)
        
        if not locked_chars:
            await query.edit_message_text("✅ No characters are locked!")
            return
        
        per_page = 15
        total = len(locked_chars)
        total_pages = (total + per_page - 1) // per_page
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * per_page
        end_idx = min(start_idx + per_page, total)
        
        message = f"🔒 **PERMANENTLY LOCKED CHARACTERS**\n"
        message += f"Page: {page}/{total_pages} | Total: {total} characters\n\n"
        
        for i, char in enumerate(locked_chars[start_idx:end_idx], start_idx + 1):
            lock_date = char.get('locked_at', 'Unknown')
            if hasattr(lock_date, 'strftime'):
                lock_date = lock_date.strftime('%Y-%m-%d')
            
            message += (
                f"{i}. **{char.get('name', 'Unknown')}**\n"
                f"   📺 {char.get('anime', 'Unknown')}\n"
                f"   🆔 `{char.get('character_id')}`\n"
                f"   🔒 {lock_date} | By: {char.get('locked_username', 'Owner')}\n"
                f"   ─────────────────────\n"
            )
        
        message += f"\n⚠️ **These {total} characters are permanently locked and will never spawn!**"
        
        # Update buttons
        buttons = []
        if total_pages > 1:
            row = []
            if page > 1:
                row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"locklist_{page-1}"))
            row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="locklist_current"))
            if page < total_pages:
                row.append(InlineKeyboardButton("Next ➡️", callback_data=f"locklist_{page+1}"))
            buttons.append(row)
        
        await query.edit_message_text(
            text=message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
        )
    
    except Exception as e:
        LOGGER.error(f"Lockedlist callback error: {e}")
        await query.answer("Error updating list!", show_alert=True)

# Add this function to check if character is locked (for spawning system)
async def is_character_locked(character_id: str) -> bool:
    """Check if a character is permanently locked"""
    try:
        from shivu import locked_characters
        locked_char = await locked_characters.find_one({'character_id': str(character_id)})
        return locked_char is not None
    except Exception as e:
        LOGGER.error(f"is_character_locked error: {e}")
        return False

# Add this function to filter locked characters from a list
async def filter_locked_characters(character_list):
    """Filter out locked characters from a list"""
    try:
        from shivu import locked_characters
        
        # Get all locked character IDs
        locked_chars = await locked_characters.find({}, {'character_id': 1}).to_list(length=1000)
        locked_ids = {str(char['character_id']) for char in locked_chars}
        
        # Filter out locked characters
        return [char for char in character_list if str(char.get('id')) not in locked_ids]
    except Exception as e:
        LOGGER.error(f"filter_locked_characters error: {e}")
        return character_list

# Add this to your shivu.py database initialization:
"""
# In your imports section
from motor.motor_asyncio import AsyncIOMotorClient

# In your database connection section (after connecting to MongoDB)
locked_characters = db["locked_characters"]

# Create index for faster lookup
await locked_characters.create_index("character_id", unique=True)
"""

# Register handlers
application.add_handler(CommandHandler('lock', lock, block=False))
application.add_handler(CommandHandler('locked', lockedlist, block=False))
application.add_handler(CallbackQueryHandler(lock_confirm, pattern="^(perm_lock|lock_cancel)_", block=False))
application.add_handler(CallbackQueryHandler(lockedlist_callback, pattern="^locklist_", block=False))