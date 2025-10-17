import importlib
import time
import random
import re
import asyncio
import traceback
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackContext, MessageHandler, filters, Application
from telegram.error import BadRequest, Forbidden

from shivu import (
    db,
    shivuu,
    application,
    LOGGER
)
from shivu.modules import ALL_MODULES

# ==================== DATABASE COLLECTIONS ====================
collection = db['anime_characters_lol']
user_collection = db['user_collection_lmaoooo']
user_totals_collection = db['user_totals_lmaoooo']
group_user_totals_collection = db['group_user_totalsssssss']
top_global_groups_collection = db['top_global_groups']

# ==================== CONFIGURATION ====================
LOG_CHAT_ID = -1003071132623
DEFAULT_MESSAGE_FREQUENCY = 50

# ==================== GLOBAL STATE ====================
locks = {}
message_counts = {}
sent_characters = {}
last_characters = {}
first_correct_guesses = {}
last_user = {}
warned_users = {}

# ==================== CUSTOM MODULE IMPORTS ====================
spawn_settings_collection = None

def import_custom_modules():
    """Import all custom modules with error handling"""
    global spawn_settings_collection
    
    LOGGER.info("="*50)
    LOGGER.info("IMPORTING CUSTOM MODULES")
    LOGGER.info("="*50)
    
    # Import rarity module
    try:
        from shivu.modules.rarity import register_rarity_handlers, spawn_settings_collection as ssc
        spawn_settings_collection = ssc
        LOGGER.info("[SUCCESS] Imported: rarity module")
        return True
    except ImportError as e:
        LOGGER.warning(f"[WARNING] Rarity module not found: {e}")
        return False
    except Exception as e:
        LOGGER.error(f"[ERROR] Failed to import rarity: {e}")
        LOGGER.error(traceback.format_exc())
        return False


def import_standard_modules():
    """Import all standard modules"""
    LOGGER.info("="*50)
    LOGGER.info("STARTING STANDARD MODULE IMPORTS")
    LOGGER.info("="*50)
    
    success_count = 0
    fail_count = 0
    
    for module_name in ALL_MODULES:
        try:
            imported_module = importlib.import_module("shivu.modules." + module_name)
            LOGGER.info(f"[SUCCESS] Imported: {module_name}")
            success_count += 1
        except Exception as e:
            LOGGER.error(f"[ERROR] Failed to import {module_name}: {e}")
            LOGGER.error(traceback.format_exc())
            fail_count += 1
    
    LOGGER.info(f"[SUMMARY] Module Import: {success_count} successful, {fail_count} failed")
    return success_count, fail_count


# ==================== HELPER FUNCTIONS ====================
def escape_markdown(text):
    """Escape markdown special characters"""
    if not text:
        return ""
    escape_chars = r'\*_`\\~>#+-=|{}.!'
    return re.sub(r'([%s])' % re.escape(escape_chars), r'\\\1', str(text))


async def is_character_allowed(character):
    """Check if character is allowed to spawn based on settings"""
    try:
        # Check if character is removed
        if character.get('removed', False):
            LOGGER.debug(f"Character {character.get('id')} is marked as removed")
            return False

        # If spawn settings collection is available, check settings
        if spawn_settings_collection:
            settings = await spawn_settings_collection.find_one({'type': 'global'})
            if settings:
                # Check disabled rarities
                disabled_rarities = settings.get('disabled_rarities', [])
                char_rarity = character.get('rarity', 'Common')
                
                # Extract emoji from rarity
                if isinstance(char_rarity, str) and ' ' in char_rarity:
                    rarity_emoji = char_rarity.split(' ')[0]
                else:
                    rarity_emoji = char_rarity
                
                if rarity_emoji in disabled_rarities:
                    LOGGER.debug(f"Character {character.get('id')} has disabled rarity: {rarity_emoji}")
                    return False
                
                # Check disabled animes
                disabled_animes = settings.get('disabled_animes', [])
                char_anime = character.get('anime', '').lower()
                
                if char_anime in [anime.lower() for anime in disabled_animes]:
                    LOGGER.debug(f"Character {character.get('id')} is from disabled anime: {char_anime}")
                    return False
        
        return True
    except Exception as e:
        LOGGER.error(f"Error checking character spawn permission: {e}")
        return True


async def get_chat_message_frequency(chat_id):
    """Get message frequency for a specific chat"""
    try:
        chat_frequency = await user_totals_collection.find_one({'chat_id': chat_id})
        if chat_frequency:
            return chat_frequency.get('message_frequency', DEFAULT_MESSAGE_FREQUENCY)
        else:
            # Initialize chat settings in database
            await user_totals_collection.insert_one({
                'chat_id': chat_id,
                'message_frequency': DEFAULT_MESSAGE_FREQUENCY
            })
            return DEFAULT_MESSAGE_FREQUENCY
    except Exception as e:
        LOGGER.error(f"Error fetching chat frequency: {e}")
        return DEFAULT_MESSAGE_FREQUENCY


# ==================== MESSAGE COUNTER ====================
async def message_counter(update: Update, context: CallbackContext) -> None:
    """Count messages and spawn characters at intervals"""
    try:
        # Ignore non-group messages
        if update.effective_chat.type not in ['group', 'supergroup']:
            return

        # Ignore bot messages and commands
        if not update.message or not update.message.text:
            return

        if update.message.text.startswith('/'):
            return

        chat_id = str(update.effective_chat.id)
        user_id = update.effective_user.id

        # Initialize lock for this chat
        if chat_id not in locks:
            locks[chat_id] = asyncio.Lock()
        lock = locks[chat_id]

        async with lock:
            # Get message frequency
            message_frequency = await get_chat_message_frequency(chat_id)

            # Anti-spam check
            if chat_id in last_user and last_user[chat_id]['user_id'] == user_id:
                last_user[chat_id]['count'] += 1
                if last_user[chat_id]['count'] >= 10:
                    # Check if user was recently warned
                    if user_id in warned_users and time.time() - warned_users[user_id] < 600:
                        return
                    else:
                        try:
                            await update.message.reply_text(
                                f"[WARNING] Don't Spam {escape(update.effective_user.first_name)}...\n"
                                "Your Messages Will be ignored for 10 Minutes..."
                            )
                        except Exception as e:
                            LOGGER.error(f"Error sending spam warning: {e}")
                        warned_users[user_id] = time.time()
                        return
            else:
                last_user[chat_id] = {'user_id': user_id, 'count': 1}

            # Initialize message count for this chat
            if chat_id not in message_counts:
                message_counts[chat_id] = 0

            # Increment message count
            message_counts[chat_id] += 1

            LOGGER.debug(f"Chat {chat_id}: Message {message_counts[chat_id]}/{message_frequency}")

            # Check if it's time to spawn
            if message_counts[chat_id] >= message_frequency:
                LOGGER.info(f"[SPAWN] Triggering spawn in chat {chat_id} (reached {message_frequency} messages)")
                await send_image(update, context)
                message_counts[chat_id] = 0  # Reset counter

    except Exception as e:
        LOGGER.error(f"[ERROR] Error in message_counter: {e}")
        LOGGER.error(traceback.format_exc())


# ==================== SPAWN CHARACTER ====================
async def send_image(update: Update, context: CallbackContext) -> None:
    """Send a random character image to the chat"""
    chat_id = update.effective_chat.id

    try:
        LOGGER.info(f"[SPAWN] Starting spawn process for chat {chat_id}")

        # Fetch all characters
        all_characters = list(await collection.find({}).to_list(length=None))

        if not all_characters:
            LOGGER.error("[SPAWN] No characters found in database")
            return

        LOGGER.info(f"[SPAWN] Total characters in database: {len(all_characters)}")

        # Initialize sent characters list for this chat
        if chat_id not in sent_characters:
            sent_characters[chat_id] = []

        # Reset if all characters have been sent
        if len(sent_characters[chat_id]) >= len(all_characters):
            LOGGER.info(f"[SPAWN] Resetting sent characters for chat {chat_id}")
            sent_characters[chat_id] = []

        # Filter characters that haven't been sent yet
        available_characters = [
            c for c in all_characters
            if 'id' in c and c.get('id') not in sent_characters[chat_id]
        ]

        if not available_characters:
            available_characters = all_characters
            sent_characters[chat_id] = []

        LOGGER.info(f"[SPAWN] Available characters before filtering: {len(available_characters)}")

        # Filter by spawn settings
        allowed_characters = []
        for char in available_characters:
            if await is_character_allowed(char):
                allowed_characters.append(char)

        LOGGER.info(f"[SPAWN] Allowed characters after filtering: {len(allowed_characters)}")

        if not allowed_characters:
            LOGGER.warning(f"[SPAWN] No allowed characters to spawn in chat {chat_id}")
            return

        # Select random character
        character = random.choice(allowed_characters)

        # Mark character as sent
        sent_characters[chat_id].append(character['id'])
        last_characters[chat_id] = character

        # Clear previous guess tracker
        if chat_id in first_correct_guesses:
            del first_correct_guesses[chat_id]

        # Get rarity emoji
        rarity = character.get('rarity', 'Common')
        if isinstance(rarity, str) and ' ' in rarity:
            rarity_emoji = rarity.split(' ')[0]
        else:
            rarity_emoji = ''

        # Send character image
        caption = (
            f"***{rarity_emoji} Look a Waifu has spawned! "
            f"Make her yours by giving\n/grab Waifu name***"
        )

        await context.bot.send_photo(
            chat_id=chat_id,
            photo=character['img_url'],
            caption=caption,
            parse_mode='Markdown'
        )

        LOGGER.info(f"[SPAWN] Character spawned: {character.get('name', 'Unknown')} (ID: {character.get('id')}) in chat {chat_id}")

    except Exception as e:
        LOGGER.error(f"[SPAWN ERROR] {e}")
        LOGGER.error(traceback.format_exc())


# ==================== GUESS HANDLER ====================
async def guess(update: Update, context: CallbackContext) -> None:
    """Handle character guessing"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    try:
        # Check if there's an active character
        if chat_id not in last_characters:
            return

        # Check if already guessed
        if chat_id in first_correct_guesses:
            await update.message.reply_text(
                '[TAKEN] Waifu already grabbed by someone else, Better Luck Next Time'
            )
            return

        # Get user's guess
        guess_text = ' '.join(context.args).lower() if context.args else ''

        # Validate guess
        if not guess_text:
            await update.message.reply_text('Please provide a name!')
            return

        if "()" in guess_text or "&" in guess_text:
            await update.message.reply_text("You can't use these types of words")
            return

        # Get character name parts
        character_name = last_characters[chat_id].get('name', '').lower()
        name_parts = character_name.split()

        # Check if guess matches
        is_correct = (
            sorted(name_parts) == sorted(guess_text.split()) or
            any(part == guess_text for part in name_parts) or
            guess_text == character_name
        )

        if is_correct:
            # Mark as guessed
            first_correct_guesses[chat_id] = user_id

            # Update or create user
            user = await user_collection.find_one({'id': user_id})
            if user:
                update_fields = {}
                if hasattr(update.effective_user, 'username') and update.effective_user.username:
                    if update.effective_user.username != user.get('username'):
                        update_fields['username'] = update.effective_user.username
                if update.effective_user.first_name != user.get('first_name'):
                    update_fields['first_name'] = update.effective_user.first_name

                if update_fields:
                    await user_collection.update_one({'id': user_id}, {'$set': update_fields})

                await user_collection.update_one(
                    {'id': user_id},
                    {'$push': {'characters': last_characters[chat_id]}}
                )
            else:
                await user_collection.insert_one({
                    'id': user_id,
                    'username': getattr(update.effective_user, 'username', None),
                    'first_name': update.effective_user.first_name,
                    'characters': [last_characters[chat_id]],
                })

            # Update group user totals
            group_user_total = await group_user_totals_collection.find_one({
                'user_id': user_id,
                'group_id': chat_id
            })

            if group_user_total:
                update_fields = {}
                if hasattr(update.effective_user, 'username') and update.effective_user.username:
                    if update.effective_user.username != group_user_total.get('username'):
                        update_fields['username'] = update.effective_user.username
                if update.effective_user.first_name != group_user_total.get('first_name'):
                    update_fields['first_name'] = update.effective_user.first_name

                if update_fields:
                    await group_user_totals_collection.update_one(
                        {'user_id': user_id, 'group_id': chat_id},
                        {'$set': update_fields}
                    )

                await group_user_totals_collection.update_one(
                    {'user_id': user_id, 'group_id': chat_id},
                    {'$inc': {'count': 1}}
                )
            else:
                await group_user_totals_collection.insert_one({
                    'user_id': user_id,
                    'group_id': chat_id,
                    'username': getattr(update.effective_user, 'username', None),
                    'first_name': update.effective_user.first_name,
                    'count': 1,
                })

            # Update group totals
            group_info = await top_global_groups_collection.find_one({'group_id': chat_id})
            if group_info:
                update_fields = {}
                if update.effective_chat.title != group_info.get('group_name'):
                    update_fields['group_name'] = update.effective_chat.title

                if update_fields:
                    await top_global_groups_collection.update_one(
                        {'group_id': chat_id},
                        {'$set': update_fields}
                    )

                await top_global_groups_collection.update_one(
                    {'group_id': chat_id},
                    {'$inc': {'count': 1}}
                )
            else:
                await top_global_groups_collection.insert_one({
                    'group_id': chat_id,
                    'group_name': update.effective_chat.title,
                    'count': 1,
                })

            # Send success message
            character = last_characters[chat_id]
            keyboard = [[
                InlineKeyboardButton(
                    "Harem",
                    switch_inline_query_current_chat=f"collection.{user_id}"
                )
            ]]

            # Get rarity properly
            rarity = character.get('rarity', 'Common')
            if isinstance(rarity, str) and ' ' in rarity:
                rarity_parts = rarity.split(' ', 1)
                rarity_emoji = rarity_parts[0]
                rarity_text = rarity_parts[1] if len(rarity_parts) > 1 else 'Common'
            else:
                rarity_emoji = ''
                rarity_text = rarity

            success_message = (
                f'<b><a href="tg://user?id={user_id}">{escape(update.effective_user.first_name)}</a></b> '
                f'Congratulations! You grabbed a new Waifu!\n\n'
                f'Name: <code>{character.get("name", "Unknown")}</code>\n'
                f'Anime: <code>{character.get("anime", "Unknown")}</code>\n'
                f'{rarity_emoji} Rarity: <code>{rarity_text}</code>\n\n'
                f'Character successfully added to your harem'
            )

            await update.message.reply_text(
                success_message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            LOGGER.info(f"[GRAB] User {user_id} grabbed {character.get('name')} in chat {chat_id}")

        else:
            await update.message.reply_text('Please write the correct name...')

    except Exception as e:
        LOGGER.error(f"[GRAB ERROR] {e}")
        LOGGER.error(traceback.format_exc())
        await update.message.reply_text('An error occurred while processing your guess.')


# ==================== HANDLER REGISTRATION ====================
def register_all_handlers():
    """Register all bot handlers"""
    LOGGER.info("="*50)
    LOGGER.info("REGISTERING HANDLERS")
    LOGGER.info("="*50)

    try:
        # Add grab command handlers
        application.add_handler(CommandHandler(["grab", "g"], guess, block=False))
        LOGGER.info("[SUCCESS] Registered: /grab, /g commands")

        # Register custom module handlers
        try:
            from shivu.modules.remove import register_remove_handlers
            register_remove_handlers()
            LOGGER.info("[SUCCESS] Registered: remove handlers")
        except ImportError:
            LOGGER.warning("[WARNING] Remove module not found, skipping")
        except Exception as e:
            LOGGER.error(f"[ERROR] Failed to register remove handlers: {e}")

        try:
            from shivu.modules.rarity import register_rarity_handlers
            register_rarity_handlers()
            LOGGER.info("[SUCCESS] Registered: rarity handlers")
        except ImportError:
            LOGGER.warning("[WARNING] Rarity module not found, skipping")
        except Exception as e:
            LOGGER.error(f"[ERROR] Failed to register rarity handlers: {e}")

        try:
            from shivu.modules.ckill import register_ckill_handler
            register_ckill_handler()
            LOGGER.info("[SUCCESS] Registered: ckill handler")
        except ImportError:
            LOGGER.warning("[WARNING] Ckill module not found, skipping")
        except Exception as e:
            LOGGER.error(f"[ERROR] Failed to register ckill handler: {e}")

        try:
            from shivu.modules.kill import register_kill_handler
            register_kill_handler()
            LOGGER.info("[SUCCESS] Registered: kill handler")
        except ImportError:
            LOGGER.warning("[WARNING] Kill module not found, skipping")
        except Exception as e:
            LOGGER.error(f"[ERROR] Failed to register kill handler: {e}")

        try:
            from shivu.modules.hclaim import register_hclaim_handler
            register_hclaim_handler()
            LOGGER.info("[SUCCESS] Registered: hclaim handler")
        except ImportError:
            LOGGER.warning("[WARNING] Hclaim module not found, skipping")
        except Exception as e:
            LOGGER.error(f"[ERROR] Failed to register hclaim handler: {e}")

        # Add message handler (MUST BE LAST!)
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            message_counter,
            block=False
        ))
        LOGGER.info("[SUCCESS] Registered: message counter (spawn handler)")

        LOGGER.info("="*50)
        LOGGER.info("[SUCCESS] ALL HANDLERS REGISTERED")
        LOGGER.info(f"[CONFIG] Spawn frequency: {DEFAULT_MESSAGE_FREQUENCY} messages")
        LOGGER.info("="*50)

    except Exception as e:
        LOGGER.error(f"[ERROR] Failed to register handlers: {e}")
        LOGGER.error(traceback.format_exc())
        raise


# ==================== MAIN FUNCTION ====================
def main() -> None:
    """Run bot"""
    try:
        # Import all modules
        import_standard_modules()
        import_custom_modules()

        # Register all handlers
        register_all_handlers()

        # Start polling
        LOGGER.info("="*50)
        LOGGER.info("[START] Starting bot polling...")
        LOGGER.info("="*50)
        
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )

    except Exception as e:
        LOGGER.error(f"[ERROR] Error in main: {e}")
        LOGGER.error(traceback.format_exc())
        raise


# ==================== ENTRY POINT ====================
if __name__ == "__main__":
    try:
        LOGGER.info("="*50)
        LOGGER.info("[START] SHIVU BOT STARTING")
        LOGGER.info("="*50)

        # Start the Pyrogram client
        shivuu.start()
        LOGGER.info("[SUCCESS] Pyrogram client started")

        # Run the bot
        main()

    except KeyboardInterrupt:
        LOGGER.info("[STOP] Bot stopped by user (Ctrl+C)")
    except Exception as e:
        LOGGER.error(f"[ERROR] Fatal error: {e}")
        LOGGER.error(traceback.format_exc())
        raise
    finally:
        try:
            shivuu.stop()
            LOGGER.info("[SUCCESS] Pyrogram client stopped")
        except:
            pass
        LOGGER.info("="*50)
        LOGGER.info("[SHUTDOWN] BOT SHUTDOWN COMPLETE")
        LOGGER.info("="*50)