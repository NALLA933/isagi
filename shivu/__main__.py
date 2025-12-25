import importlib
import asyncio
import random
import re
import traceback
from html import escape
from collections import deque
from time import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackContext, MessageHandler, filters
from telegram.error import BadRequest

from shivu import db, shivuu, application, LOGGER
from shivu.modules import ALL_MODULES
from shivu.modules.ai import monitor_auctions

collection = db['anime_characters_lol']
user_collection = db['user_collection_lmaoooo']
user_totals_collection = db['user_totals_lmaoooo']
group_user_totals_collection = db['group_user_totalsssssss']
top_global_groups_collection = db['top_global_groups']

MESSAGE_FREQUENCY = 40
DESPAWN_TIME = 180
AMV_ALLOWED_GROUP_ID = -1003100468240

locks = {}
message_counts = {}
sent_characters = {}
last_characters = {}
first_correct_guesses = {}
spawn_messages = {}
spawn_message_links = {}
currently_spawning = {}

spawn_settings_collection = None
group_rarity_collection = None
get_spawn_settings = None
get_group_exclusive = None

for module_name in ALL_MODULES:
    try:
        importlib.import_module("shivu.modules." + module_name)
        LOGGER.info(f"✅ Module loaded: {module_name}")
    except Exception as e:
        LOGGER.error(f"❌ Module failed: {module_name} - {e}")

try:
    from shivu.modules.rarity import (
        spawn_settings_collection as ssc,
        group_rarity_collection as grc,
        get_spawn_settings,
        get_group_exclusive
    )
    spawn_settings_collection = ssc
    group_rarity_collection = grc
    LOGGER.info("✅ Rarity system loaded")
except Exception as e:
    LOGGER.warning(f"⚠️ Rarity system not available: {e}")

try:
    from shivu.modules.backup import setup_backup_handlers
    setup_backup_handlers(application)
    LOGGER.info("✅ Backup system initialized")
except Exception as e:
    LOGGER.warning(f"⚠️ Backup system not available: {e}")


async def is_character_allowed(character, chat_id=None):
    try:
        if character.get('removed', False):
            LOGGER.debug(f"Character {character.get('name')} is removed")
            return False

        char_rarity = character.get('rarity', '🟢 Common')
        rarity_emoji = char_rarity.split(' ')[0] if isinstance(char_rarity, str) and ' ' in char_rarity else char_rarity
        
        is_video = character.get('is_video', False)
        
        if is_video and rarity_emoji == '🎥':
            if chat_id == AMV_ALLOWED_GROUP_ID:
                LOGGER.info(f"✅ AMV {character.get('name')} allowed in main group")
                return True
            else:
                LOGGER.debug(f"❌ AMV {character.get('name')} blocked in group {chat_id}")
                return False

        if group_rarity_collection is not None and chat_id:
            try:
                current_group_exclusive = await group_rarity_collection.find_one({
                    'chat_id': chat_id,
                    'rarity_emoji': rarity_emoji
                })
                if current_group_exclusive:
                    return True

                other_group_exclusive = await group_rarity_collection.find_one({
                    'rarity_emoji': rarity_emoji,
                    'chat_id': {'$ne': chat_id}
                })
                if other_group_exclusive:
                    return False
            except Exception as e:
                LOGGER.error(f"Error checking group exclusivity: {e}")

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


async def get_chat_message_frequency(chat_id):
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


async def despawn_character(chat_id, message_id, character, context):
    try:
        await asyncio.sleep(DESPAWN_TIME)

        if chat_id in first_correct_guesses:
            last_characters.pop(chat_id, None)
            spawn_messages.pop(chat_id, None)
            spawn_message_links.pop(chat_id, None)
            currently_spawning.pop(chat_id, None)
            return

        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except BadRequest as e:
            LOGGER.warning(f"Could not delete spawn message: {e}")

        rarity = character.get('rarity', '🟢 Common')
        rarity_emoji = rarity.split(' ')[0] if isinstance(rarity, str) and ' ' in rarity else '🟢'

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

        await asyncio.sleep(10)
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=missed_msg.message_id)
        except BadRequest as e:
            LOGGER.warning(f"Could not delete missed message: {e}")

        last_characters.pop(chat_id, None)
        spawn_messages.pop(chat_id, None)
        spawn_message_links.pop(chat_id, None)
        currently_spawning.pop(chat_id, None)

    except Exception as e:
        LOGGER.error(f"Error in despawn_character: {e}")
        LOGGER.error(traceback.format_exc())


async def message_counter(update: Update, context: CallbackContext) -> None:
    try:
        if update.effective_chat.type not in ['group', '
