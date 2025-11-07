import importlib
import time
import random
import re
import asyncio
import traceback
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackContext, MessageHandler, filters, CallbackQueryHandler
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
DEFAULT_MESSAGE_FREQUENCY = 50
DESPAWN_TIME = 180  # 3 minutes (180 seconds)
# MAIN GROUP WHERE AMV/VIDEO CHARACTERS CAN SPAWN
AMV_ALLOWED_GROUP_ID = -1003100468240
# BACKUP USER ID - receives automatic backups
BACKUP_USER_ID = 5147822244

# ==================== GLOBAL STATE ====================
locks = {}
message_counts = {}
sent_characters = {}
last_characters = {}
first_correct_guesses = {}
last_user = {}
warned_users = {}
spawn_messages = {}  # Track spawn messages for deletion
spawn_message_links = {}  # Track spawn message links for wrong guess button
spawn_settings_collection = None
group_rarity_collection = None

# ==================== IMPORT ALL MODULES ====================
for module_name in ALL_MODULES:
    try:
        importlib.import_module("shivu.modules." + module_name)
        LOGGER.info(f"✅ Imported: {module_name}")
    except Exception as e:
        LOGGER.error(f"❌ Failed to import {module_name}: {e}")

# Load spawn settings and group rarity functions
try:
    from shivu.modules.rarity import (
        spawn_settings_collection as ssc,
        group_rarity_collection as grc,
        get_spawn_settings,
        get_group_exclusive
    )
    spawn_settings_collection = ssc
    group_rarity_collection = grc
    LOGGER.info("✅ Enhanced rarity system loaded (group exclusive + global)")
except Exception as e:
    LOGGER.error(f"⚠️ Could not import rarity system: {e}")
    get_spawn_settings = None
    get_group_exclusive = None

# ==================== SETUP BACKUP SYSTEM ====================
try:
    from shivu.modules.backup import setup_backup_handlers
    setup_backup_handlers(application)
    LOGGER.info(f"✅ Backup system initialized - Backups will be sent to user {BACKUP_USER_ID}")
except Exception as e:
    LOGGER.error(f"⚠️ Could not import backup system: {e}")


# ==================== HELPER FUNCTIONS ====================
def escape_markdown(text):
    if not text:
        return ""
    escape_chars = r'\*_`\\~>#+-=|{}.!'
    return re.sub(r'([%s])' % re.escape(escape_chars), str(text))


async def is_character_allowed(character, chat_id=None):
    """
    Enhanced check: Group gets exclusive rarity + all global enabled rarities.
    - If a group has an exclusive, ONLY that group can spawn it
    - Other groups get all global enabled rarities (minus exclusives)
    """
    try:
        if character.get('removed', False):
            return False

        # Get character rarity emoji
        char_rarity = character.get('rarity', '🟢 Common')
        if isinstance(char_rarity, str) and ' ' in char_rarity:
            rarity_emoji = char_rarity.split(' ')[0]
        else:
            rarity_emoji = char_rarity

        # ===== CHECK GROUP EXCLUSIVITY =====
        if group_rarity_collection is not None and chat_id:
            try:
                # Check if current group has this rarity as exclusive - ALWAYS ALLOW
                current_group_exclusive = await group_rarity_collection.find_one({
                    'chat_id': chat_id,
                    'rarity_emoji': rarity_emoji
                })

                if current_group_exclusive:
                    LOGGER.info(f"✅ Chat {chat_id} allowing exclusive rarity {rarity_emoji}")
                    return True

                # Check if this rarity is exclusive to ANOTHER group - BLOCK IT
                other_group_exclusive = await group_rarity_collection.find_one({
                    'rarity_emoji': rarity_emoji,
                    'chat_id': {'$ne': chat_id}
                })

                if other_group_exclusive:
                    LOGGER.info(f"❌ Chat {chat_id} blocking {rarity_emoji} (exclusive to chat {other_group_exclusive['chat_id']})")
                    return False

            except Exception as e:
                LOGGER.error(f"Error checking group exclusivity: {e}")

        # ===== AMV/VIDEO RESTRICTION (STILL APPLIES) =====
        is_video = character.get('is_video', False)
        if is_video and chat_id != AMV_ALLOWED_GROUP_ID:
            LOGGER.info(f"❌ AMV character blocked in chat {chat_id} (not main group)")
            return False

        # ===== CHECK GLOBAL RARITY SETTINGS =====
        if spawn_settings_collection is not None and get_spawn_settings is not None:
            try:
                settings = await get_spawn_settings()
                if settings and settings.get('rarities'):
                    rarities = settings['rarities']
                    if rarity_emoji in rarities:
                        is_enabled = rarities[rarity_emoji].get('enabled', True)
                        if not is_enabled:
                            LOGGER.info(f"❌ Blocking {rarity_emoji} - globally disabled")
                            return False
            except Exception as e:
                LOGGER.error(f"Error checking global rarity settings: {e}")

        return True

    except Exception as e:
        LOGGER.error(f"Error in is_character_allowed: {e}")
        return True


async def get_chat_message_frequency(chat_id):
    try:
        chat_frequency = await user_totals_collection.find_one({'chat_id': str(chat_id)})
        if chat_frequency:
            return chat_frequency.get('message_frequency', DEFAULT_MESSAGE_FREQUENCY)
        else:
            await user_totals_collection.insert_one({
                'chat_id': str(chat_id),
                'message_frequency': DEFAULT_MESSAGE_FREQUENCY
            })
            return DEFAULT_MESSAGE_FREQUENCY
    except Exception as e:
        LOGGER.error(f"Error in get_chat_message_frequency: {e}")
        return DEFAULT_MESSAGE_FREQUENCY


async def update_grab_task(user_id: int):
    try:
        user = await user_collection.find_one({'id': user_id})
        if user and 'pass_data' in user:
            await user_collection.update_one(
                {'id': user_id},
                {'$inc': {'pass_data.tasks.grabs': 1}}
            )
    except Exception as e:
        LOGGER.error(f"Error in update_grab_task: {e}")


# ==================== DESPAWN CHARACTER FUNCTION ====================
async def despawn_character(chat_id, message_id, character, context):
    """Handle character despawn after timeout"""
    try:
        await asyncio.sleep(DESPAWN_TIME)

        # Check if character was grabbed - if yes, don't show despawn message
        if chat_id in first_correct_guesses:
            LOGGER.info(f"Character was grabbed in chat {chat_id}, skipping despawn message")
            # Clean up without showing despawn message
            last_characters.pop(chat_id, None)
            spawn_messages.pop(chat_id, None)
            spawn_message_links.pop(chat_id, None)
            return

        # Delete spawn message
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            LOGGER.info(f"Deleted spawn message in chat {chat_id}")
        except BadRequest as e:
            LOGGER.warning(f"Could not delete spawn message: {e}")

        # Send missed message
        rarity = character.get('rarity', '🟢 Common')
        rarity_emoji = rarity.split(' ')[0] if isinstance(rarity, str) and ' ' in rarity else '🟢'

        # Check if character is video or image
        is_video = character.get('is_video', False)
        media_url = character.get('img_url')

        missed_caption = f"""⏰ ᴛɪᴍᴇ's ᴜᴘ! ʏᴏᴜ ᴀʟʟ ᴍɪssᴇᴅ ᴛʜɪs ᴡᴀɪғᴜ!

{rarity_emoji} ɴᴀᴍᴇ: <b>{character.get('name', 'Unknown')}</b>
⚡ ᴀɴɪᴍᴇ: <b>{character.get('anime', 'Unknown')}</b>
🎯 ʀᴀʀɪᴛʏ: <b>{rarity}</b>

💔 ʙᴇᴛᴛᴇʀ ʟᴜᴄᴋ ɴᴇxᴛ ᴛɪᴍᴇ!"""

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

        LOGGER.info(f"Sent missed message for chat {chat_id}")

        # Delete missed message after 10 seconds
        await asyncio.sleep(10)
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=missed_msg.message_id)
            LOGGER.info(f"Deleted missed message in chat {chat_id}")
        except BadRequest as e:
            LOGGER.warning(f"Could not delete missed message: {e}")

        # Clean up
        last_characters.pop(chat_id, None)
        spawn_messages.pop(chat_id, None)
        spawn_message_links.pop(chat_id, None)

    except Exception as e:
        LOGGER.error(f"Error in despawn_character: {e}")
        LOGGER.error(traceback.format_exc())


# ==================== MESSAGE COUNTER ====================
async def message_counter(update: Update, context: CallbackContext) -> None:
    try:
        # Only process group messages
        if update.effective_chat.type not in ['group', 'supergroup']:
            return

        # Check if message exists
        if not update.message:
            return

        # Ignore bot messages
        if update.effective_user.is_bot:
            return

        chat_id = str(update.effective_chat.id)
        user_id = update.effective_user.id

        # Initialize lock for this chat
        if chat_id not in locks:
            locks[chat_id] = asyncio.Lock()
        lock = locks[chat_id]

        async with lock:
            # Get message frequency for this chat
            message_frequency = await get_chat_message_frequency(chat_id)

            # Spam detection
            if chat_id in last_user and last_user[chat_id]['user_id'] == user_id:
                last_user[chat_id]['count'] += 1
                if last_user[chat_id]['count'] >= 10:
                    if user_id in warned_users and time.time() - warned_users[user_id] < 600:
                        return
                    else:
                        try:
                            await update.message.reply_html(
                                f"<b>ᴅᴏɴ'ᴛ sᴘᴀᴍ</b> {escape(update.effective_user.first_name)}...\n"
                                "<b>ʏᴏᴜʀ ᴍᴇssᴀɢᴇs ᴡɪʟʟ ʙᴇ ɪɢɴᴏʀᴇᴅ ғᴏʀ 10 ᴍɪɴᴜᴛᴇs...!!</b>"
                            )
                        except:
                            pass
                        warned_users[user_id] = time.time()
                        return
            else:
                last_user[chat_id] = {'user_id': user_id, 'count': 1}

            # Initialize message counter for this chat
            if chat_id not in message_counts:
                message_counts[chat_id] = 0

            # Increment message count
            message_counts[chat_id] += 1

            LOGGER.info(f"Chat {chat_id}: {message_counts[chat_id]}/{message_frequency} messages")

            # Check if it's time to spawn
            if message_counts[chat_id] >= message_frequency:
                LOGGER.info(f"Spawning character in chat {chat_id}")
                await send_image(update, context)
                message_counts[chat_id] = 0

    except Exception as e:
        LOGGER.error(f"Error in message_counter: {e}")
        LOGGER.error(traceback.format_exc())


# ==================== ENHANCED SPAWN (GROUP EXCLUSIVE + GLOBAL) ====================
async def send_image(update: Update, context: CallbackContext) -> None:
    """
    Enhanced spawn logic:
    - Group gets its exclusive rarity (if set) + all global enabled rarities
    - Other groups don't get the exclusive rarity
    - Uses weighted selection based on rarity chances
    """
    chat_id = update.effective_chat.id

    try:
        LOGGER.info(f"Starting character spawn for chat {chat_id}")

        # Get all characters from database
        all_characters = list(await collection.find({}).to_list(length=None))

        if not all_characters:
            LOGGER.warning("No characters found in database!")
            return

        LOGGER.info(f"Found {len(all_characters)} total characters in database")

        # Initialize sent characters list
        if chat_id not in sent_characters:
            sent_characters[chat_id] = []

        # Reset if all characters have been sent
        if len(sent_characters[chat_id]) >= len(all_characters):
            sent_characters[chat_id] = []
            LOGGER.info(f"Reset sent characters for chat {chat_id}")

        # Get available characters
        available_characters = [
            c for c in all_characters
            if 'id' in c and c.get('id') not in sent_characters[chat_id]
        ]

        if not available_characters:
            available_characters = all_characters
            sent_characters[chat_id] = []

        LOGGER.info(f"Available characters: {len(available_characters)}")

        # Filter allowed characters (checks exclusivity + global settings)
        allowed_characters = []
        for char in available_characters:
            if await is_character_allowed(char, chat_id):
                allowed_characters.append(char)

        if not allowed_characters:
            LOGGER.warning("No allowed characters to spawn!")
            return

        LOGGER.info(f"Allowed characters after filtering: {len(allowed_characters)}")

        # ===== WEIGHTED SELECTION WITH GROUP EXCLUSIVE + GLOBAL =====
        character = None
        selected_rarity = None

        try:
            # Get group exclusive settings
            group_setting = None
            if group_rarity_collection is not None and get_group_exclusive is not None:
                group_setting = await get_group_exclusive(chat_id)

            # Get global settings
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

            # Build weighted choices
            weighted_choices = []

            # Add exclusive rarity if group has one
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
                    LOGGER.info(f"✨ Chat {chat_id} has EXCLUSIVE {exclusive_emoji} ({exclusive_chance}%)")

            # Add all global enabled rarities (excluding exclusive if already added)
            for emoji, rarity_data in global_rarities.items():
                if not rarity_data.get('enabled', True):
                    continue

                # Skip if this is the exclusive rarity (already added)
                if group_setting and emoji == group_setting['rarity_emoji']:
                    continue

                if emoji in rarity_pools and rarity_pools[emoji]:
                    weighted_choices.append({
                        'emoji': emoji,
                        'chars': rarity_pools[emoji],
                        'chance': rarity_data.get('chance', 5.0),
                        'is_exclusive': False
                    })

            # Select character using weighted random
            if weighted_choices:
                total_chance = sum(choice['chance'] for choice in weighted_choices)
                rand = random.uniform(0, total_chance)

                cumulative = 0
                for choice in weighted_choices:
                    cumulative += choice['chance']
                    if rand <= cumulative:
                        character = random.choice(choice['chars'])
                        selected_rarity = choice['emoji']
                        exclusive_tag = " [EXCLUSIVE]" if choice['is_exclusive'] else ""
                        LOGGER.info(
                            f"🎯 Chat {chat_id} spawned {selected_rarity}{exclusive_tag} "
                            f"(chance: {choice['chance']:.2f}%, roll: {rand:.2f}/{total_chance:.2f})"
                        )
                        break

        except Exception as e:
            LOGGER.error(f"Error in weighted selection: {e}\n{traceback.format_exc()}")

        # Fallback to random selection if weighted selection failed
        if not character:
            character = random.choice(allowed_characters)
            LOGGER.warning(f"⚠️ Chat {chat_id} used fallback random selection")

        LOGGER.info(f"Selected character: {character.get('name', 'Unknown')}")

        # Mark character as sent
        sent_characters[chat_id].append(character['id'])
        last_characters[chat_id] = character

        # Reset first correct guesses
        if chat_id in first_correct_guesses:
            del first_correct_guesses[chat_id]

        # Get rarity emoji
        rarity = character.get('rarity', 'Common')
        if isinstance(rarity, str) and ' ' in rarity:
            rarity_emoji = rarity.split(' ')[0]
        else:
            rarity_emoji = '🟢'

        # Caption for spawn message
        caption = f"""***{rarity_emoji} ʟᴏᴏᴋ ᴀ ᴡᴀɪғᴜ ʜᴀs sᴘᴀᴡɴᴇᴅ !! ᴍᴀᴋᴇ ʜᴇʀ ʏᴏᴜʀ's ʙʏ ɢɪᴠɪɴɢ
/grab 𝚆𝚊𝚒𝚏𝚞 𝚗𝚊𝚖𝚎

⏰ ʏᴏᴜ ʜᴀᴠᴇ {DESPAWN_TIME // 60} ᴍɪɴᴜᴛᴇs ᴛᴏ ɢʀᴀʙ!***"""

        # Check if character is video or image
        is_video = character.get('is_video', False)
        media_url = character.get('img_url')

        if is_video:
            # Send as video for MP4/AMV characters
            LOGGER.info(f"Spawning VIDEO character: {character.get('name')}")
            spawn_msg = await context.bot.send_video(
                chat_id=chat_id,
                video=media_url,
                caption=caption,
                parse_mode='Markdown',
                supports_streaming=True,
                read_timeout=300,
                write_timeout=300,
                connect_timeout=60,
                pool_timeout=60
            )
        else:
            # Send as photo for image characters
            LOGGER.info(f"Spawning IMAGE character: {character.get('name')}")
            spawn_msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=media_url,
                caption=caption,
                parse_mode='Markdown',
                read_timeout=180,
                write_timeout=180
            )

        # Store spawn message ID
        spawn_messages[chat_id] = spawn_msg.message_id

        # Create message link for the button (for wrong guesses)
        chat_username = update.effective_chat.username
        if chat_username:
            spawn_message_links[chat_id] = f"https://t.me/{chat_username}/{spawn_msg.message_id}"
        else:
            # For private groups without username, use the chat ID format
            chat_id_str = str(chat_id).replace('-100', '')
            spawn_message_links[chat_id] = f"https://t.me/c/{chat_id_str}/{spawn_msg.message_id}"

        LOGGER.info(f"✅ Character spawned successfully in chat {chat_id}")

        # Schedule despawn
        asyncio.create_task(despawn_character(chat_id, spawn_msg.message_id, character, context))
        LOGGER.info(f"⏰ Despawn scheduled for chat {chat_id} in {DESPAWN_TIME} seconds")

    except Exception as e:
        LOGGER.error(f"❌ Error in send_image for chat {chat_id}: {e}")
        LOGGER.error(traceback.format_exc())


# ==================== GUESS HANDLER ====================
async def guess(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    try:
        # Check if there's a character to guess
        if chat_id not in last_characters:
            await update.message.reply_html('<b>ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ ʏᴇᴛ!</b>')
            return

        # Check if already grabbed
        if chat_id in first_correct_guesses:
            await update.message.reply_html(
                '<b>🚫 ᴡᴀɪғᴜ ᴀʟʀᴇᴀᴅʏ ɢʀᴀʙʙᴇᴅ ʙʏ sᴏᴍᴇᴏɴᴇ ᴇʟsᴇ ⚡. ʙᴇᴛᴛᴇʀ ʟᴜᴄᴋ ɴᴇxᴛ ᴛɪᴍᴇ..!!</b>'
            )
            return

        # Get guess text
        guess_text = ' '.join(context.args).lower() if context.args else ''

        if not guess_text:
            await update.message.reply_html('<b>ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ɴᴀᴍᴇ!</b>')
            return

        # Check for invalid characters
        if "()" in guess_text or "&" in guess_text:
            await update.message.reply_html(
                "<b>ɴᴀʜʜ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴜsᴇ ᴛʜɪs ᴛʏᴘᴇs ᴏғ ᴡᴏʀᴅs...❌</b>"
            )
            return

        # Get character name
        character_name = last_characters[chat_id].get('name', '').lower()
        name_parts = character_name.split()

        # Check if guess is correct
        is_correct = (
            sorted(name_parts) == sorted(guess_text.split()) or
            any(part == guess_text for part in name_parts) or
            guess_text == character_name
        )

        if is_correct:
            # Mark as grabbed
            first_correct_guesses[chat_id] = user_id

            # Delete spawn message
            if chat_id in spawn_messages:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=spawn_messages[chat_id])
                    LOGGER.info(f"Deleted spawn message after correct guess in chat {chat_id}")
                except BadRequest as e:
                    LOGGER.warning(f"Could not delete spawn message: {e}")
                spawn_messages.pop(chat_id, None)

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

            # Update grab task
            await update_grab_task(user_id)

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

            # Update global group totals
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
                    "🪼 ʜᴀʀᴇᴍ",
                    switch_inline_query_current_chat=f"collection.{user_id}"
                )
            ]]

            rarity = character.get('rarity', '🟢 Common')
            if isinstance(rarity, str) and ' ' in rarity:
                rarity_parts = rarity.split(' ', 1)
                rarity_emoji = rarity_parts[0]
                rarity_text = rarity_parts[1] if len(rarity_parts) > 1 else 'Common'
            else:
                rarity_emoji = '🟢'
                rarity_text = rarity

            await update.message.reply_text(
                f'Congratulations 🎊\n<b><a href="tg://user?id={user_id}">{escape(update.effective_user.first_name)}</a></b> You grabbed a new waifu!! ✅️\n\n'
                f'🎀 𝙉𝙖𝙢𝙚: <code>{character.get("name", "Unknown")}</code>\n'
                f'{rarity_emoji} 𝙍𝙖𝙧𝙞𝙩𝙮: <code>{rarity_text}</code>\n'
                f'⚡ 𝘼𝙣𝙞𝙢𝙚: <code>{character.get("anime", "Unknown")}</code>\n\n'
                f'✧⁠ Character successfully added in your harem',
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            # Clean up spawn message link after successful grab
            spawn_message_links.pop(chat_id, None)

        else:
            # Wrong guess - show button to view spawn message
            keyboard = []
            if chat_id in spawn_message_links:
                keyboard.append([
                    InlineKeyboardButton(
                        "📍 ᴠɪᴇᴡ sᴘᴀᴡɴ ᴍᴇssᴀɢᴇ",
                        url=spawn_message_links[chat_id]
                    )
                ])

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            await update.message.reply_html(
                '<b>ᴘʟᴇᴀsᴇ ᴡʀɪᴛᴇ ᴀ ᴄᴏʀʀᴇᴄᴛ ɴᴀᴍᴇ..❌</b>',
                reply_markup=reply_markup
            )

    except Exception as e:
        LOGGER.error(f"Error in guess: {e}")
        LOGGER.error(traceback.format_exc())


# ==================== MAIN ====================
def main() -> None:
    application.add_handler(CommandHandler(["grab", "g"], guess, block=False))
    application.add_handler(MessageHandler(filters.ALL, message_counter, block=False))

    LOGGER.info("Bot handlers registered")
    LOGGER.info("Starting bot with enhanced rarity system...")
    LOGGER.info("Features: Group exclusive rarities + Global rarities")

    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    shivuu.start()
    LOGGER.info("=" * 50)
    LOGGER.info("ʏᴏɪᴄʜɪ ʀᴀɴᴅɪ ʙᴏᴛ sᴛᴀʀᴛᴇᴅ")
    LOGGER.info("Enhanced Rarity System Active:")
    LOGGER.info("   • Groups can have EXCLUSIVE rarities")
    LOGGER.info("   • Each group gets: Exclusive + All Global")
    LOGGER.info("   • Exclusives blocked in other groups")
    LOGGER.info(f"   • Backup system active (User ID: {BACKUP_USER_ID})")
    LOGGER.info("=" * 50)
    main()