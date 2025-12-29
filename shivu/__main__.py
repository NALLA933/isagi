import shivu.mongodb_patch
import importlib
import asyncio
import random
import traceback
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackContext, MessageHandler, filters, Application
from telegram.error import BadRequest

from shivu import db, shivuu, application, LOGGER
from shivu.modules import ALL_MODULES

from pymongo import collection as pymongo_collection
from pymongo.errors import OperationFailure

# ==================== MONGODB PATCH ====================
_orig_create_index = pymongo_collection.Collection.create_index

def _safe_create_index(self, keys, **kwargs):
    try:
        return _orig_create_index(self, keys, **kwargs)
    except OperationFailure as e:
        if e.code == 86:
            LOGGER.debug(f"Index already exists on {self.name}, skipping")
            return None
        raise

pymongo_collection.Collection.create_index = _safe_create_index

# ==================== DATABASE COLLECTIONS ====================
collection = db['anime_characters_lol']
user_collection = db['user_collection_lmaoooo']
user_totals_collection = db['user_totals_lmaoooo']
group_user_totals_collection = db['group_user_totalsssssss']
top_global_groups_collection = db['top_global_groups']

# ==================== CONFIGURATION ====================
MESSAGE_FREQUENCY = 10  # 🚀 REDUCED from 40 to 10 for faster spawning
DESPAWN_TIME = 180  # 3 minutes
AMV_ALLOWED_GROUP_ID = -1003100468240

# ==================== GLOBAL STATE ====================
locks = {}
message_counts = {}
sent_characters = {}
last_characters = {}
first_correct_guesses = {}
spawn_messages = {}
spawn_message_links = {}
currently_spawning = {}

# ==================== RARITY SYSTEM GLOBALS ====================
spawn_settings_collection = None
group_rarity_collection = None
get_spawn_settings = None
get_group_exclusive = None

# ==================== LOADING ANIMATIONS ====================
SPAWN_ANIMATIONS = [
    "✨💫⭐🌟✨",
    "🎯🎪🎭🎨🎯",
    "🌸🌺🌼🌻🌸",
    "💎💠🔷🔹💎",
    "🎀🎁🎊🎉🎀",
    "⚡🔥💥✨⚡",
    "🌈🦋🌸💫🌈",
    "🎮🎲🎰🎪🎮"
]

GRAB_SUCCESS_ANIMATIONS = [
    "🎉🎊🎈🎁✨",
    "🏆🥇🌟💫⭐",
    "💖💝💗💓💖",
    "🎯🎪🎭🎨🎊",
    "🌸🌺🦋🌼🌻"
]

# ==================== MODULE LOADING ====================
for module_name in ALL_MODULES:
    try:
        importlib.import_module("shivu.modules." + module_name)
        LOGGER.info(f"✅ Module loaded: {module_name}")
    except Exception as e:
        LOGGER.error(f"❌ Module failed: {module_name} - {e}")

# ==================== CHARACTER VALIDATION ====================
async def is_character_allowed(character, chat_id=None):
    """
    Check if a character is allowed to spawn in a specific chat.
    Handles removed characters, video/AMV restrictions, and rarity exclusivity.
    """
    try:
        # Check if character is removed
        if character.get('removed', False):
            LOGGER.debug(f"Character {character.get('name')} is removed")
            return False

        # Extract rarity information
        char_rarity = character.get('rarity', '🟢 Common')
        rarity_emoji = char_rarity.split(' ')[0] if isinstance(char_rarity, str) and ' ' in char_rarity else char_rarity
        
        is_video = character.get('is_video', False)
        
        # Handle AMV/Video character restrictions
        if is_video and rarity_emoji == '🎥':
            if chat_id == AMV_ALLOWED_GROUP_ID:
                LOGGER.info(f"✅ AMV {character.get('name')} allowed in main group")
                return True
            else:
                LOGGER.debug(f"❌ AMV {character.get('name')} blocked in group {chat_id}")
                return False

        # Check group-specific rarity exclusivity
        if group_rarity_collection is not None and chat_id:
            try:
                # Check if this group has exclusive access to this rarity
                current_group_exclusive = await group_rarity_collection.find_one({
                    'chat_id': chat_id,
                    'rarity_emoji': rarity_emoji
                })
                if current_group_exclusive:
                    return True

                # Check if another group has exclusive access
                other_group_exclusive = await group_rarity_collection.find_one({
                    'rarity_emoji': rarity_emoji,
                    'chat_id': {'$ne': chat_id}
                })
                if other_group_exclusive:
                    return False
            except Exception as e:
                LOGGER.error(f"Error checking group exclusivity: {e}")

        # Check global rarity settings
        if spawn_settings_collection is not None and get_spawn_settings is not None:
            try:
                settings = await get_spawn_settings()
                if settings and settings.get('rarities'):
                    rarities = settings['rarities']
                    if rarity_emoji in rarities:
                        is_enabled = rarities[rarity_emoji].get('enabled', True)
                        if not is_enabled:
                            return False
            except Exception as e:
                LOGGER.error(f"Error checking global rarity: {e}")

        return True

    except Exception as e:
        LOGGER.error(f"Error in is_character_allowed: {e}\n{traceback.format_exc()}")
        return True

# ==================== CHAT FREQUENCY MANAGEMENT ====================
async def get_chat_message_frequency(chat_id):
    """
    Get the message frequency for a specific chat from database.
    Creates entry if doesn't exist.
    """
    try:
        chat_frequency = await user_totals_collection.find_one({'chat_id': str(chat_id)})
        if chat_frequency:
            return chat_frequency.get('message_frequency', MESSAGE_FREQUENCY)
        else:
            await user_totals_collection.insert_one({
                'chat_id': str(chat_id),
                'message_frequency': MESSAGE_FREQUENCY
            })
            return MESSAGE_FREQUENCY
    except Exception as e:
        LOGGER.error(f"Error in get_chat_message_frequency: {e}")
        return MESSAGE_FREQUENCY

async def set_chat_message_frequency(chat_id, frequency):
    """
    Set custom message frequency for a specific chat.
    """
    try:
        await user_totals_collection.update_one(
            {'chat_id': str(chat_id)},
            {'$set': {'message_frequency': frequency}},
            upsert=True
        )
        LOGGER.info(f"✅ Set frequency for chat {chat_id}: {frequency}")
        return True
    except Exception as e:
        LOGGER.error(f"Error in set_chat_message_frequency: {e}")
        return False

# ==================== TASK UPDATES ====================
async def update_grab_task(user_id: int):
    """Update user's grab task counter for battle pass/achievements."""
    try:
        user = await user_collection.find_one({'id': user_id})
        if user and 'pass_data' in user:
            await user_collection.update_one(
                {'id': user_id},
                {'$inc': {'pass_data.tasks.grabs': 1}}
            )
    except Exception as e:
        LOGGER.error(f"Error in update_grab_task: {e}")

# ==================== DESPAWN MECHANISM ====================
async def despawn_character(chat_id, message_id, character, context):
    """
    Handle character despawn after timeout.
    Deletes spawn message and shows missed character info.
    """
    try:
        await asyncio.sleep(DESPAWN_TIME)

        # If someone already grabbed it, don't despawn
        if chat_id in first_correct_guesses:
            last_characters.pop(chat_id, None)
            spawn_messages.pop(chat_id, None)
            spawn_message_links.pop(chat_id, None)
            currently_spawning.pop(chat_id, None)
            return

        # Delete spawn message
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except BadRequest as e:
            LOGGER.warning(f"Could not delete spawn message: {e}")

        # Prepare despawn message
        rarity = character.get('rarity', '🟢 Common')
        rarity_emoji = rarity.split(' ')[0] if isinstance(rarity, str) and ' ' in rarity else '🟢'

        is_video = character.get('is_video', False)
        media_url = character.get('img_url')

        missed_caption = f"""<blockquote expandable>⏰ <b>Time's Up!</b>

{rarity_emoji} <b>Name:</b> <code>{character.get('name', 'Unknown')}</code>
⚡ <b>Anime:</b> <code>{character.get('anime', 'Unknown')}</code>
🎯 <b>Rarity:</b> <code>{rarity}</code>

💔 This character has vanished. Better luck next time!</blockquote>"""

        # Send missed notification
        if is_video:
            missed_msg = await context.bot.send_video(
                chat_id=chat_id,
                video=media_url,
                caption=missed_caption,
                parse_mode='HTML',
                supports_streaming=True
            )
        else:
            missed_msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=media_url,
                caption=missed_caption,
                parse_mode='HTML'
            )

        # Auto-delete missed notification after 10 seconds
        await asyncio.sleep(10)
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=missed_msg.message_id)
        except BadRequest as e:
            LOGGER.warning(f"Could not delete missed message: {e}")

        # Cleanup state
        last_characters.pop(chat_id, None)
        spawn_messages.pop(chat_id, None)
        spawn_message_links.pop(chat_id, None)
        currently_spawning.pop(chat_id, None)

    except Exception as e:
        LOGGER.error(f"Error in despawn_character: {e}")
        LOGGER.error(traceback.format_exc())
    finally:
        # Always cleanup spawning flag
        currently_spawning.pop(str(chat_id), None)

# ==================== MESSAGE COUNTER (ENHANCED) ====================
async def message_counter(update: Update, context: CallbackContext) -> None:
    """
    Count ALL messages including commands for spawn triggering.
    🚀 NOW COUNTS COMMANDS TOO!
    """
    try:
        # Only process group messages
        if update.effective_chat.type not in ['group', 'supergroup']:
            return

        # Skip if no message
        if not update.message and not update.edited_message:
            return

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        chat_id_str = str(chat_id)

        # Initialize lock for this chat
        if chat_id_str not in locks:
            locks[chat_id_str] = asyncio.Lock()
        lock = locks[chat_id_str]

        async with lock:
            # Initialize message count
            if chat_id_str not in message_counts:
                message_counts[chat_id_str] = 0

            # Increment counter
            message_counts[chat_id_str] += 1
            
            # Determine message type for logging
            msg_type = "unknown"
            if update.message:
                if update.message.text:
                    msg_type = "command" if update.message.text.startswith('/') else "text"
                elif update.message.photo:
                    msg_type = "photo"
                elif update.message.video:
                    msg_type = "video"
                elif update.message.document:
                    msg_type = "document"
                elif update.message.sticker:
                    msg_type = "sticker"
                elif update.message.animation:
                    msg_type = "animation"
                elif update.message.voice:
                    msg_type = "voice"
                elif update.message.audio:
                    msg_type = "audio"
                elif update.message.video_note:
                    msg_type = "video_note"
                else:
                    msg_type = "other"
            
            # Get chat-specific frequency from database
            chat_frequency = await get_chat_message_frequency(chat_id)
            
            LOGGER.info(f"📊 Chat {chat_id} | Count: {message_counts[chat_id_str]}/{chat_frequency} | Type: {msg_type}")

            # Check if spawn threshold reached
            if message_counts[chat_id_str] >= chat_frequency:
                # Prevent multiple simultaneous spawns
                if chat_id_str not in currently_spawning or not currently_spawning[chat_id_str]:
                    LOGGER.info(f"🎯 Spawning triggered in chat {chat_id}")
                    currently_spawning[chat_id_str] = True
                    message_counts[chat_id_str] = 0  # Reset counter
                    
                    # Spawn character
                    await send_image(update, context)

    except Exception as e:
        LOGGER.error(f"Error in message_counter: {e}")
        LOGGER.error(traceback.format_exc())
        # Reset spawning flag on error
        currently_spawning[str(chat_id)] = False

# ==================== CHARACTER SPAWN (ENHANCED) ====================
async def send_image(update: Update, context: CallbackContext) -> None:
    """
    Spawn a character in the chat with animations and weighted rarity selection.
    🎨 NOW WITH ANIMATIONS!
    """
    chat_id = update.effective_chat.id

    try:
        # Fetch all characters
        all_characters = list(await collection.find({}).to_list(length=None))

        if not all_characters:
            LOGGER.warning(f"No characters available in database")
            return

        # Initialize sent characters tracker
        if chat_id not in sent_characters:
            sent_characters[chat_id] = []

        # Reset if all characters have been sent
        if len(sent_characters[chat_id]) >= len(all_characters):
            sent_characters[chat_id] = []
            LOGGER.info(f"♻️ Reset character pool for chat {chat_id}")

        # Filter out already sent characters
        available_characters = [
            c for c in all_characters
            if 'id' in c and c.get('id') not in sent_characters[chat_id]
        ]

        if not available_characters:
            available_characters = all_characters
            sent_characters[chat_id] = []

        # Filter allowed characters
        allowed_characters = [c for c in available_characters if await is_character_allowed(c, chat_id)]

        if not allowed_characters:
            LOGGER.warning(f"No allowed characters for chat {chat_id}")
            return

        character = None

        # ==================== WEIGHTED RARITY SELECTION ====================
        try:
            group_setting = None
            if group_rarity_collection is not None and get_group_exclusive is not None:
                group_setting = await get_group_exclusive(chat_id)

            global_rarities = {}
            if spawn_settings_collection is not None and get_spawn_settings is not None:
                settings = await get_spawn_settings()
                global_rarities = settings.get('rarities', {}) if settings else {}

            # Build rarity pools
            rarity_pools = {}
            for char in allowed_characters:
                char_rarity = char.get('rarity', '🟢 Common')
                emoji = char_rarity.split(' ')[0] if isinstance(char_rarity, str) and ' ' in char_rarity else char_rarity

                if emoji not in rarity_pools:
                    rarity_pools[emoji] = []
                rarity_pools[emoji].append(char)

            weighted_choices = []

            # Add group exclusive rarity
            if group_setting:
                exclusive_emoji = group_setting['rarity_emoji']
                exclusive_chance = group_setting.get('chance', 10.0)

                if exclusive_emoji in rarity_pools and rarity_pools[exclusive_emoji]:
                    weighted_choices.append({
                        'emoji': exclusive_emoji,
                        'chars': rarity_pools[exclusive_emoji],
                        'chance': exclusive_chance,
                        'is_exclusive': True
                    })

            # Add global rarities
            for emoji, rarity_data in global_rarities.items():
                if not rarity_data.get('enabled', True):
                    continue

                if group_setting and emoji == group_setting['rarity_emoji']:
                    continue

                if emoji in rarity_pools and rarity_pools[emoji]:
                    weighted_choices.append({
                        'emoji': emoji,
                        'chars': rarity_pools[emoji],
                        'chance': rarity_data.get('chance', 5.0),
                        'is_exclusive': False
                    })

            # Perform weighted selection
            if weighted_choices:
                total_chance = sum(choice['chance'] for choice in weighted_choices)
                rand = random.uniform(0, total_chance)

                cumulative = 0
                for choice in weighted_choices:
                    cumulative += choice['chance']
                    if rand <= cumulative:
                        character = random.choice(choice['chars'])
                        break

        except Exception as e:
            LOGGER.error(f"Error in weighted selection: {e}\n{traceback.format_exc()}")

        # Fallback to random selection
        if not character:
            character = random.choice(allowed_characters)

        # Mark character as sent
        sent_characters[chat_id].append(character['id'])
        last_characters[chat_id] = character

        # Clear previous correct guesses
        if chat_id in first_correct_guesses:
            del first_correct_guesses[chat_id]

        # Extract rarity info
        rarity = character.get('rarity', 'Common')
        rarity_emoji = rarity.split(' ')[0] if isinstance(rarity, str) and ' ' in rarity else '🟢'

        LOGGER.info(f"✨ Spawned: {character.get('name')} ({rarity_emoji}) in chat {chat_id}")

        # ==================== ANIMATED SPAWN MESSAGE ====================
        animation = random.choice(SPAWN_ANIMATIONS)
        
        caption = f"""<blockquote expandable>{animation}

✨ <b>A Wild Character Appeared!</b>

🎯 A mysterious character has spawned in the chat!

<b>Quick! Use:</b> <code>/grab [name]</code> or <code>/g [name]</code>
⏰ <b>Time Limit:</b> {DESPAWN_TIME // 60} minutes

💫 Will you be fast enough to claim this beauty?

{animation}</blockquote>"""

        is_video = character.get('is_video', False)
        media_url = character.get('img_url')

        # Send spawn message
        if is_video:
            spawn_msg = await context.bot.send_video(
                chat_id=chat_id,
                video=media_url,
                caption=caption,
                parse_mode='HTML',
                supports_streaming=True,
                read_timeout=300,
                write_timeout=300
            )
        else:
            spawn_msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=media_url,
                caption=caption,
                parse_mode='HTML',
                read_timeout=180,
                write_timeout=180
            )

        # Store spawn message info
        spawn_messages[chat_id] = spawn_msg.message_id

        # Generate message link
        chat_username = update.effective_chat.username
        if chat_username:
            spawn_message_links[chat_id] = f"https://t.me/{chat_username}/{spawn_msg.message_id}"
        else:
            chat_id_str = str(chat_id).replace('-100', '')
            spawn_message_links[chat_id] = f"https://t.me/c/{chat_id_str}/{spawn_msg.message_id}"

        # Start despawn timer
        asyncio.create_task(despawn_character(chat_id, spawn_msg.message_id, character, context))

    except Exception as e:
        LOGGER.error(f"Error in send_image: {e}")
        LOGGER.error(traceback.format_exc())
    finally:
        # Always reset spawning flag
        currently_spawning[str(chat_id)] = False

# ==================== GRAB COMMAND (ENHANCED) ====================
async def guess(update: Update, context: CallbackContext) -> None:
    """
    Handle character grab attempts with enhanced validation and animations.
    🎉 NOW WITH SUCCESS ANIMATIONS!
    """
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    try:
        # Check if character exists
        if chat_id not in last_characters:
            await update.message.reply_html(
                '<blockquote>❌ <b>No Active Spawn</b>\n\n'
                'No character has spawned yet. Wait for one to appear!</blockquote>'
            )
            return

        # Check if already grabbed
        if chat_id in first_correct_guesses:
            await update.message.reply_html(
                '<blockquote>🚫 <b>Already Claimed</b>\n\n'
                'This character has been grabbed by someone else. Better luck next time!</blockquote>'
            )
            return

        # Extract guess
        guess_text = ' '.join(context.args).lower() if context.args else ''

        if not guess_text:
            await update.message.reply_html(
                '<blockquote>⚠️ <b>Missing Name</b>\n\n'
                'Provide a character name!\n\n'
                '<b>Example:</b> <code>/grab Naruto</code> or <code>/g Naruto</code></blockquote>'
            )
            return

        # Validate input
        if "()" in guess_text or "&" in guess_text:
            await update.message.reply_html(
                '<blockquote>⛔ <b>Invalid Characters</b>\n\n'
                'Special characters like (), & are not allowed.</blockquote>'
            )
            return

        # Check guess
        character_name = last_characters[chat_id].get('name', '').lower()
        name_parts = character_name.split()

        is_correct = (
            sorted(name_parts) == sorted(guess_text.split()) or
            any(part == guess_text for part in name_parts) or
            guess_text == character_name
        )

        if is_correct:
            # Mark as grabbed
            first_correct_guesses[chat_id] = user_id

            LOGGER.info(f"✅ User {user_id} grabbed {character_name} in chat {chat_id}")

            # Delete spawn message
            if chat_id in spawn_messages:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=spawn_messages[chat_id])
                except BadRequest as e:
                    LOGGER.warning(f"Could not delete spawn: {e}")
                spawn_messages.pop(chat_id, None)

            # ==================== UPDATE USER DATA ====================
            user = await user_collection.find_one({'id': user_id})
            if user:
                # Update username/first_name if changed
                update_fields = {}
                if hasattr(update.effective_user, 'username') and update.effective_user.username:
                    if update.effective_user.username != user.get('username'):
                        update_fields['username'] = update.effective_user.username
                if update.effective_user.first_name != user.get('first_name'):
                    update_fields['first_name'] = update.effective_user.first_name

                if update_fields:
                    await user_collection.update_one({'id': user_id}, {'$set': update_fields})

                # Add character to collection
                await user_collection.update_one(
                    {'id': user_id},
                    {'$push': {'characters': last_characters[chat_id]}}
                )
            else:
                # Create new user
                await user_collection.insert_one({
                    'id': user_id,
                    'username': getattr(update.effective_user, 'username', None),
                    'first_name': update.effective_user.first_name,
                    'characters': [last_characters[chat_id]],
                })

            # Update grab task
            await update_grab_task(user_id)

            # ==================== UPDATE GROUP STATS ====================
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

            # Update global group stats
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

            # ==================== SEND SUCCESS MESSAGE ====================
            character = last_characters[chat_id]
            
            keyboard = [[
                InlineKeyboardButton("🪼 View Harem", switch_inline_query_current_chat=f"collection.{user_id}")
            ]]

            rarity = character.get('rarity', '🟢 Common')
            if isinstance(rarity, str) and ' ' in rarity:
                rarity_parts = rarity.split(' ', 1)
                rarity_emoji = rarity_parts[0]
                rarity_text = rarity_parts[1] if len(rarity_parts) > 1 else 'Common'
            else:
                rarity_emoji = '🟢'
                rarity_text = rarity

            animation = random.choice(GRAB_SUCCESS_ANIMATIONS)

            success_message = f"""<blockquote expandable>{animation}

🎉 <b>Congratulations!</b>

<b><a href="tg://user?id={user_id}">{escape(update.effective_user.first_name)}</a></b> successfully grabbed a new character!

🎀 <b>Name:</b> <code>{character.get('name', 'Unknown')}</code>
{rarity_emoji} <b>Rarity:</b> <code>{rarity_text}</code>
⚡ <b>Anime:</b> <code>{character.get('anime', 'Unknown')}</code>

✨ Character added to your collection!

{animation}</blockquote>"""

            await update.message.reply_text(
                success_message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            # Cleanup
            spawn_message_links.pop(chat_id, None)

        else:
            # Wrong guess
            keyboard = []
            if chat_id in spawn_message_links:
                keyboard.append([
                    InlineKeyboardButton("📍 View Spawn", url=spawn_message_links[chat_id])
                ])

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            
            await update.message.reply_html(
                '<blockquote>❌ <b>Wrong Name</b>\n\nThat\'s not correct. Try again!</blockquote>',
                reply_markup=reply_markup
            )

    except Exception as e:
        LOGGER.error(f"Error in guess: {e}")
        LOGGER.error(traceback.format_exc())

# ==================== ADMIN COMMANDS ====================
async def set_frequency_command(update: Update, context: CallbackContext):
    """
    Admin command to set custom spawn frequency.
    Usage: /setfrequency <number>
    """
    try:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        # Get chat admins
        admins = await context.bot.get_chat_administrators(chat_id)
        admin_ids = [admin.user.id for admin in admins]
        
        # Check if user is admin
        if user_id not in admin_ids:
            await update.message.reply_html(
                '<blockquote>🚫 <b>Admin Only</b>\n\n'
                'Only group administrators can use this command.</blockquote>'
            )
            return
        
        # Validate input
        if not context.args or not context.args[0].isdigit():
            await update.message.reply_html(
                '<blockquote>⚠️ <b>Invalid Input</b>\n\n'
                'Usage: <code>/setfrequency [number]</code>\n\n'
                'Example: <code>/setfrequency 5</code></blockquote>'
            )
            return
        
        frequency = int(context.args[0])
        
        if frequency < 1 or frequency > 100:
            await update.message.reply_html(
                '<blockquote>⚠️ <b>Invalid Range</b>\n\n'
                'Frequency must be between 1 and 100.</blockquote>'
            )
            return
        
        # Set frequency
        success = await set_chat_message_frequency(chat_id, frequency)
        
        if success:
            # Reset counter
            message_counts[str(chat_id)] = 0
            
            await update.message.reply_html(
                f'<blockquote>✅ <b>Frequency Updated</b>\n\n'
                f'Spawn frequency set to: <b>{frequency}</b> messages\n\n'
                f'Characters will now spawn every {frequency} messages!</blockquote>'
            )
        else:
            await update.message.reply_html(
                '<blockquote>❌ <b>Error</b>\n\n'
                'Failed to update spawn frequency. Please try again.</blockquote>'
            )
    
    except Exception as e:
        LOGGER.error(f"Error in set_frequency_command: {e}")
        await update.message.reply_html(
            '<blockquote>❌ <b>Error</b>\n\n'
            'An error occurred while setting the frequency.</blockquote>'
        )

async def force_spawn_command(update: Update, context: CallbackContext):
    """
    Admin command to force instant spawn.
    Usage: /forcespawn
    """
    try:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        chat_id_str = str(chat_id)
        
        # Get chat admins
        admins = await context.bot.get_chat_administrators(chat_id)
        admin_ids = [admin.user.id for admin in admins]
        
        # Check if user is admin
        if user_id not in admin_ids:
            await update.message.reply_html(
                '<blockquote>🚫 <b>Admin Only</b>\n\n'
                'Only group administrators can use this command.</blockquote>'
            )
            return
        
        # Check if spawn in progress
        if chat_id_str in currently_spawning and currently_spawning[chat_id_str]:
            await update.message.reply_html(
                '<blockquote>⚠️ <b>Spawn In Progress</b>\n\n'
                'A character is already spawning. Please wait!</blockquote>'
            )
            return
        
        # Force spawn
        currently_spawning[chat_id_str] = True
        message_counts[chat_id_str] = 0
        
        await update.message.reply_html(
            '<blockquote>⚡ <b>Force Spawn</b>\n\n'
            'Spawning a character now...</blockquote>'
        )
        
        await send_image(update, context)
    
    except Exception as e:
        LOGGER.error(f"Error in force_spawn_command: {e}")
        currently_spawning[str(chat_id)] = False
        await update.message.reply_html(
            '<blockquote>❌ <b>Error</b>\n\n'
            'An error occurred while forcing spawn.</blockquote>'
        )

async def spawn_info_command(update: Update, context: CallbackContext):
    """
    Show current spawn settings and statistics.
    Usage: /spawninfo
    """
    try:
        chat_id = update.effective_chat.id
        chat_id_str = str(chat_id)
        
        # Get current settings
        frequency = await get_chat_message_frequency(chat_id)
        current_count = message_counts.get(chat_id_str, 0)
        remaining = max(0, frequency - current_count)
        
        # Check if spawn active
        spawn_active = chat_id in last_characters and chat_id not in first_correct_guesses
        
        info_message = f"""<blockquote expandable>📊 <b>Spawn Information</b>

⚙️ <b>Current Settings:</b>
• Spawn Frequency: <code>{frequency}</code> messages
• Messages Count: <code>{current_count}/{frequency}</code>
• Messages Remaining: <code>{remaining}</code>

🎯 <b>Current Status:</b>
• Active Spawn: <code>{'Yes ✅' if spawn_active else 'No ❌'}</code>
• Despawn Time: <code>{DESPAWN_TIME // 60} minutes</code>

💡 <b>Admin Commands:</b>
• <code>/setfrequency [num]</code> - Set spawn frequency
• <code>/forcespawn</code> - Force instant spawn
• <code>/spawninfo</code> - Show this info</blockquote>"""
        
        await update.message.reply_html(info_message)
    
    except Exception as e:
        LOGGER.error(f"Error in spawn_info_command: {e}")

# ==================== DATABASE INITIALIZATION ====================
async def fix_my_db():
    """Clean up database indexes."""
    try:
        await collection.drop_index("id_1")
        await collection.drop_index("characters.id_1")
        LOGGER.info("✅ Database indexes cleaned")
    except Exception as e:
        LOGGER.info(f"ℹ️ Index cleanup: {e}")

# ==================== MAIN APPLICATION ====================
async def main():
    try:
        # Initialize database
        await fix_my_db()
        
        # Load rarity system
        try:
            from shivu.modules.rarity import (
                spawn_settings_collection as ssc,
                group_rarity_collection as grc,
                get_spawn_settings as gss,
                get_group_exclusive as gge
            )
            global spawn_settings_collection, group_rarity_collection, get_spawn_settings, get_group_exclusive
            spawn_settings_collection = ssc
            group_rarity_collection = grc
            get_spawn_settings = gss
            get_group_exclusive = gge
            LOGGER.info("✅ Rarity system loaded")
        except Exception as e:
            LOGGER.warning(f"⚠️ Rarity system: {e}")

        # Load backup system
        try:
            from shivu.modules.backup import setup_backup_handlers
            setup_backup_handlers(application)
            LOGGER.info("✅ Backup system initialized")
        except Exception as e:
            LOGGER.warning(f"⚠️ Backup system: {e}")

        # Start Pyrogram
        await shivuu.start()
        LOGGER.info("✅ Pyrogram started")

        # Register handlers
        # 🚀 ENHANCED: Now handles ALL messages including commands
        application.add_handler(MessageHandler(filters.ALL, message_counter, block=False))
        application.add_handler(CommandHandler(["grab", "g"], guess, block=False))
        application.add_handler(CommandHandler("setfrequency", set_frequency_command, block=False))
        application.add_handler(CommandHandler("forcespawn", force_spawn_command, block=False))
        application.add_handler(CommandHandler("spawninfo", spawn_info_command, block=False))

        # Start bot
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        
        LOGGER.info("✅ BOT STARTED SUCCESSFULLY")
        LOGGER.info(f"📊 Default spawn frequency: {MESSAGE_FREQUENCY} messages")
        LOGGER.info(f"⏰ Despawn time: {DESPAWN_TIME} seconds")

        # Keep running
        while True:
            await asyncio.sleep(3600)

    except Exception as e:
        LOGGER.error(f"❌ Fatal error: {e}")
        traceback.print_exc()
    finally:
        LOGGER.info("🔄 Cleaning up...")
        try:
            await application.stop()
            await application.shutdown()
            await shivuu.stop()
        except Exception as e:
            LOGGER.error(f"Cleanup error: {e}")

# ==================== ENTRY POINT ====================
if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        LOGGER.info("⏹️ Bot stopped by user")
