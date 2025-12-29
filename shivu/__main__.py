import shivu.mongodb_patch
import importlib
import asyncio
import random
import re
import traceback
from html import escape
from collections import deque
from time import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackContext, MessageHandler, filters, Application
from telegram.error import BadRequest

from shivu import db, shivuu, application, LOGGER
from shivu.modules import ALL_MODULES

from pymongo import collection as pymongo_collection
from pymongo.errors import OperationFailure

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

FANCY_FONTS = {
    'bold_serif': {
        'a': '𝐚', 'b': '𝐛', 'c': '𝐜', 'd': '𝐝', 'e': '𝐞', 'f': '𝐟', 'g': '𝐠', 'h': '𝐡',
        'i': '𝐢', 'j': '𝐣', 'k': '𝐤', 'l': '𝐥', 'm': '𝐦', 'n': '𝐧', 'o': '𝐨', 'p': '𝐩',
        'q': '𝐪', 'r': '𝐫', 's': '𝐬', 't': '𝐭', 'u': '𝐮', 'v': '𝐯', 'w': '𝐰', 'x': '𝐱',
        'y': '𝐲', 'z': '𝐳', 'A': '𝐀', 'B': '𝐁', 'C': '𝐂', 'D': '𝐃', 'E': '𝐄', 'F': '𝐅',
        'G': '𝐆', 'H': '𝐇', 'I': '𝐈', 'J': '𝐉', 'K': '𝐊', 'L': '𝐋', 'M': '𝐌', 'N': '𝐍',
        'O': '𝐎', 'P': '𝐏', 'Q': '𝐐', 'R': '𝐑', 'S': '𝐒', 'T': '𝐓', 'U': '𝐔', 'V': '𝐕',
        'W': '𝐖', 'X': '𝐗', 'Y': '𝐘', 'Z': '𝐙'
    },
    'script': {
        'a': '𝒶', 'b': '𝒷', 'c': '𝒸', 'd': '𝒹', 'e': '𝑒', 'f': '𝒻', 'g': '𝑔', 'h': '𝒽',
        'i': '𝒾', 'j': '𝒿', 'k': '𝓀', 'l': '𝓁', 'm': '𝓂', 'n': '𝓃', 'o': '𝑜', 'p': '𝓅',
        'q': '𝓆', 'r': '𝓇', 's': '𝓈', 't': '𝓉', 'u': '𝓊', 'v': '𝓋', 'w': '𝓌', 'x': '𝓍',
        'y': '𝓎', 'z': '𝓏', 'A': '𝒜', 'B': '𝐵', 'C': '𝒞', 'D': '𝒟', 'E': '𝐸', 'F': '𝐹',
        'G': '𝒢', 'H': '𝐻', 'I': '𝐼', 'J': '𝒥', 'K': '𝒦', 'L': '𝐿', 'M': '𝑀', 'N': '𝒩',
        'O': '𝒪', 'P': '𝒫', 'Q': '𝒬', 'R': '𝑅', 'S': '𝒮', 'T': '𝒯', 'U': '𝒰', 'V': '𝒱',
        'W': '𝒲', 'X': '𝒳', 'Y': '𝒴', 'Z': '𝒵'
    }
}

SPAWN_TEMPLATES = [
    "✨ 𝐀 𝐖𝐢𝐥𝐝 𝐖𝐚𝐢𝐟𝐮 𝐀𝐩𝐩𝐞𝐚𝐫𝐞𝐝! ✨",
    "🌸 𝒜 𝑅𝒶𝓇𝑒 𝐵𝑒𝒶𝓊𝓉𝓎 𝐻𝒶𝓈 𝒜𝓇𝓇𝒾𝓋𝑒𝒹! 🌸",
    "⚡ 𝐋𝐢𝐠𝐡𝐭𝐧𝐢𝐧𝐠 𝐒𝐭𝐫𝐢𝐤𝐞𝐬! 𝐀 𝐖𝐚𝐢𝐟𝐮 𝐀𝐩𝐩𝐞𝐚𝐫𝐬! ⚡",
    "💫 𝒮𝓉𝒶𝓇𝒹𝓊𝓈𝓉 𝐹𝒶𝓁𝓁𝓈... 𝒜 𝒲𝒶𝒾𝒻𝓊 𝐸𝓂𝑒𝓇𝑔𝑒𝓈! 💫",
    "🎭 𝐓𝐡𝐞 𝐒𝐭𝐚𝐠𝐞 𝐈𝐬 𝐒𝐞𝐭! 𝐀 𝐍𝐞𝐰 𝐂𝐡𝐚𝐫𝐚𝐜𝐭𝐞𝐫 𝐀𝐩𝐩𝐞𝐚𝐫𝐬! 🎭",
]

GRAB_SUCCESS_TEMPLATES = [
    "🎊 𝐂𝐨𝐧𝐠𝐫𝐚𝐭𝐮𝐥𝐚𝐭𝐢𝐨𝐧𝐬! 🎊",
    "🎉 𝒜𝓂𝒶𝓏𝒾𝓃𝑔! 🎉",
    "✨ 𝐅𝐚𝐧𝐭𝐚𝐬𝐭𝐢𝐜! ✨",
    "🌟 𝐈𝐧𝐜𝐫𝐞𝐝𝐢𝐛𝐥𝐞! 🌟",
    "💎 𝐏𝐞𝐫𝐟𝐞𝐜𝐭! 💎",
]

ANIMATION_FRAMES = [
    "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"
]

SPARKLE_ANIMATIONS = [
    "✦", "✧", "✨", "✦", "✧"
]

def convert_to_fancy(text, font_type='bold_serif'):
    if font_type not in FANCY_FONTS:
        return text
    font = FANCY_FONTS[font_type]
    return ''.join(font.get(c, c) for c in text)

for module_name in ALL_MODULES:
    try:
        importlib.import_module("shivu.modules." + module_name)
        LOGGER.info(f"✅ Module loaded: {module_name}")
    except Exception as e:
        LOGGER.error(f"❌ Module failed: {module_name} - {e}")

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

async def animate_spawn_message(context, chat_id, message_id, character):
    try:
        for i in range(3):
            frame = SPARKLE_ANIMATIONS[i % len(SPARKLE_ANIMATIONS)]
            await asyncio.sleep(0.5)
            
    except Exception as e:
        LOGGER.debug(f"Animation error: {e}")

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

        char_name = convert_to_fancy(character.get('name', 'Unknown'), 'script')
        anime_name = convert_to_fancy(character.get('anime', 'Unknown'), 'script')

        missed_caption = f"""╔══════════════════════╗
  ⏰ 𝐓𝐈𝐌𝐄'𝐒 𝐔𝐏! ⏰
╚══════════════════════╝

💔 𝒯𝒽𝒾𝓈 𝒷𝑒𝒶𝓊𝓉𝓎 𝒽𝒶𝓈 𝓋𝒶𝓃𝒾𝓈𝒽𝑒𝒹...

{rarity_emoji} 𝐍𝐚𝐦𝐞: <b>{char_name}</b>
⚡ 𝐀𝐧𝐢𝐦𝐞: <b>{anime_name}</b>
🎯 𝐑𝐚𝐫𝐢𝐭𝐲: <b>{rarity}</b>

╭─────────────────────╮
│  💫 𝐁𝐞𝐭𝐭𝐞𝐫 𝐋𝐮𝐜𝐤 𝐍𝐞𝐱𝐭 𝐓𝐢𝐦𝐞! 💫  │
╰─────────────────────╯"""

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
        if update.effective_chat.type not in ['group', 'supergroup']:
            return

        if not update.message and not update.edited_message:
            return

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        chat_id_str = str(chat_id)

        if chat_id_str not in locks:
            locks[chat_id_str] = asyncio.Lock()
        lock = locks[chat_id_str]

        async with lock:
            if chat_id_str not in message_counts:
                message_counts[chat_id_str] = 0

            message_counts[chat_id_str] += 1
            
            msg_content = "unknown"
            if update.message:
                if update.message.text:
                    if update.message.text.startswith('/'):
                        msg_content = f"command: {update.message.text.split()[0]}"
                    else:
                        msg_content = "text"
                elif update.message.photo:
                    msg_content = "photo"
                elif update.message.video:
                    msg_content = "video"
                elif update.message.document:
                    msg_content = "document"
                elif update.message.sticker:
                    msg_content = "sticker"
                elif update.message.animation:
                    msg_content = "animation"
                elif update.message.voice:
                    msg_content = "voice"
                elif update.message.audio:
                    msg_content = "audio"
                elif update.message.video_note:
                    msg_content = "video_note"
                else:
                    msg_content = "other_media"
            
            sender_type = "🤖bot" if update.effective_user.is_bot else "👤user"
            
            LOGGER.info(f"📊 Chat {chat_id} | Count: {message_counts[chat_id_str]}/{MESSAGE_FREQUENCY} | {sender_type} {user_id} | {msg_content}")

            if message_counts[chat_id_str] >= MESSAGE_FREQUENCY:
                if chat_id_str not in currently_spawning or not currently_spawning[chat_id_str]:
                    LOGGER.info(f"🎯 Triggering spawn in chat {chat_id} after {message_counts[chat_id_str]} messages")
                    currently_spawning[chat_id_str] = True
                    message_counts[chat_id_str] = 0
                    asyncio.create_task(send_image(update, context))
                else:
                    LOGGER.debug(f"⏭️ Spawn already in progress for chat {chat_id}, skipping")

    except Exception as e:
        LOGGER.error(f"Error in message_counter: {e}")
        LOGGER.error(traceback.format_exc())

async def send_image(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    try:
        all_characters = list(await collection.find({}).to_list(length=None))

        if not all_characters:
            LOGGER.warning(f"No characters available for spawn in chat {chat_id}")
            currently_spawning[str(chat_id)] = False
            return

        if chat_id not in sent_characters:
            sent_characters[chat_id] = []

        if len(sent_characters[chat_id]) >= len(all_characters):
            sent_characters[chat_id] = []

        available_characters = [
            c for c in all_characters
            if 'id' in c and c.get('id') not in sent_characters[chat_id]
        ]

        if not available_characters:
            available_characters = all_characters
            sent_characters[chat_id] = []

        allowed_characters = []
        for char in available_characters:
            if await is_character_allowed(char, chat_id):
                allowed_characters.append(char)

        if not allowed_characters:
            LOGGER.warning(f"No allowed characters for spawn in chat {chat_id}")
            currently_spawning[str(chat_id)] = False
            return

        character = None
        selected_rarity = None

        try:
            group_setting = None
            if group_rarity_collection is not None and get_group_exclusive is not None:
                group_setting = await get_group_exclusive(chat_id)

            global_rarities = {}
            if spawn_settings_collection is not None and get_spawn_settings is not None:
                settings = await get_spawn_settings()
                global_rarities = settings.get('rarities', {}) if settings else {}

            rarity_pools = {}
            for char in allowed_characters:
                char_rarity = char.get('rarity', '🟢 Common')
                emoji = char_rarity.split(' ')[0] if isinstance(char_rarity, str) and ' ' in char_rarity else char_rarity

                if emoji not in rarity_pools:
                    rarity_pools[emoji] = []
                rarity_pools[emoji].append(char)

            weighted_choices = []

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

            if weighted_choices:
                total_chance = sum(choice['chance'] for choice in weighted_choices)
                rand = random.uniform(0, total_chance)

                cumulative = 0
                for choice in weighted_choices:
                    cumulative += choice['chance']
                    if rand <= cumulative:
                        character = random.choice(choice['chars'])
                        selected_rarity = choice['emoji']
                        break

        except Exception as e:
            LOGGER.error(f"Error in weighted selection: {e}\n{traceback.format_exc()}")

        if not character:
            character = random.choice(allowed_characters)

        sent_characters[chat_id].append(character['id'])
        last_characters[chat_id] = character

        if chat_id in first_correct_guesses:
            del first_correct_guesses[chat_id]

        rarity = character.get('rarity', 'Common')
        if isinstance(rarity, str) and ' ' in rarity:
            rarity_emoji = rarity.split(' ')[0]
        else:
            rarity_emoji = '🟢'

        LOGGER.info(f"✨ Spawned character: {character.get('name')} ({rarity_emoji}) in chat {chat_id}")

        spawn_header = random.choice(SPAWN_TEMPLATES)
        char_name_fancy = convert_to_fancy(character.get('name', 'Unknown'), 'script')
        
        caption = f"""╔═══════════════════════╗
{spawn_header}
╚═══════════════════════╝

✦━━━━━━━━━━━━━━━━━━━━✦

{rarity_emoji} 𝐀 𝐌𝐲𝐬𝐭𝐞𝐫𝐢𝐨𝐮𝐬 𝐂𝐡𝐚𝐫𝐚𝐜𝐭𝐞𝐫 𝐀𝐩𝐩𝐞𝐚𝐫𝐬!

╭─────────────────────╮
│ 📝 𝐔𝐬𝐞: /grab [name]   │
│ ⏰ 𝐓𝐢𝐦𝐞: {DESPAWN_TIME // 60} minutes      │
╰─────────────────────╯

✦━━━━━━━━━━━━━━━━━━━━✦

💫 𝒲𝒾𝓁𝓁 𝓎𝑜𝓊 𝒷𝑒 𝓉𝒽𝑒 𝑜𝓃𝑒 𝓉𝑜 𝒸𝓁𝒶𝒾𝓂 𝓉𝒽𝒾𝓈 𝒷𝑒𝒶𝓊𝓉𝓎? 💫"""

        is_video = character.get('is_video', False)
        media_url = character.get('img_url')

        if is_video:
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
            spawn_msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=media_url,
                caption=caption,
                parse_mode='Markdown',
                read_timeout=180,
                write_timeout=180
            )

        spawn_messages[chat_id] = spawn_msg.message_id

        chat_username = update.effective_chat.username
        if chat_username:
            spawn_message_links[chat_id] = f"https://t.me/{chat_username}/{spawn_msg.message_id}"
        else:
            chat_id_str = str(chat_id).replace('-100', '')
            spawn_message_links[chat_id] = f"https://t.me/c/{chat_id_str}/{spawn_msg.message_id}"

        currently_spawning[str(chat_id)] = False

        asyncio.create_task(despawn_character(chat_id, spawn_msg.message_id, character, context))

    except Exception as e:
        LOGGER.error(f"Error in send_image: {e}")
        LOGGER.error(traceback.format_exc())
        currently_spawning[str(chat_id)] = False

async def guess(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    try:
        if chat_id not in last_characters:
            await update.message.reply_html('╔════════════════╗\n<b>⚠️ 𝐍𝐨 𝐀𝐜𝐭𝐢𝐯𝐞 𝐒𝐩𝐚𝐰𝐧</b>\n╚════════════════╝\n\n𝒩𝑜 𝒸𝒽𝒶𝓇𝒶𝒸𝓉𝑒𝓇 𝒽𝒶𝓈 𝓈𝓅𝒶𝓌𝓃𝑒𝒹 𝓎𝑒𝓉!')
            return

        if chat_id in first_correct_guesses:
            await update.message.reply_html('╔═════════════════════╗\n<b>🚫 𝐀𝐥𝐫𝐞𝐚𝐝𝐲 𝐆𝐫𝐚𝐛𝐛𝐞𝐝</b>\n╚═════════════════════╝\n\n💔 𝒯𝒽𝒾𝓈 𝓌𝒶𝒾𝒻𝓊 𝒽𝒶𝓈 𝒶𝓁𝓇𝑒𝒶𝒹𝓎 𝒷𝑒𝑒𝓃 𝒸𝓁𝒶𝒾𝓂𝑒𝒹!\n\n✨ 𝐁𝐞𝐭𝐭𝐞𝐫 𝐥𝐮𝐜𝐤 𝐧𝐞𝐱𝐭 𝐭𝐢𝐦𝐞!')
            return

        guess_text = ' '.join(context.args).lower() if context.args else ''

        if not guess_text:
            await update.message.reply_html('╔════════════════╗\n<b>❌ 𝐍𝐨 𝐍𝐚𝐦𝐞 𝐏𝐫𝐨𝐯𝐢𝐝𝐞𝐝</b>\n╚════════════════╝\n\n𝒫𝓁𝑒𝒶𝓈𝑒 𝓅𝓇𝑜𝓋𝒾𝒹𝑒 𝒶 𝒸𝒽𝒶𝓇𝒶𝒸𝓉𝑒𝓇 𝓃𝒶𝓂𝑒!\n\n📝 𝐄𝐱𝐚𝐦𝐩𝐥𝐞: /grab Naruto')
            return

        if "()" in guess_text or "&" in guess_text:
            await update.message.reply_html("╔═══════════════════╗\n<b>⛔ 𝐈𝐧𝐯𝐚𝐥𝐢𝐝 𝐂𝐡𝐚𝐫𝐚𝐜𝐭𝐞𝐫𝐬</b>\n╚═══════════════════╝\n\n𝒮𝓅𝑒𝒸𝒾𝒶𝓁 𝒸𝒽𝒶𝓇𝒶𝒸𝓉𝑒𝓇𝓈 𝒶𝓇𝑒 𝓃𝑜𝓉 𝒶𝓁𝓁𝑜𝓌𝑒𝒹!")
            return

        character_name = last_characters[chat_id].get('name', '').lower()
        name_parts = character_name.split()

        is_correct = (
            sorted(name_parts) == sorted(guess_text.split()) or
            any(part == guess_text for part in name_parts) or
            guess_text == character_name
        )

        if is_correct:
            first_correct_guesses[chat_id] = user_id

            LOGGER.info(f"✅ User {user_id} grabbed {character_name} in chat {chat_id}")

            if chat_id in spawn_messages:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=spawn_messages[chat_id])
                except BadRequest as e:
                    LOGGER.warning(f"Could not delete spawn message: {e}")
                spawn_messages.pop(chat_id, None)

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

            await update_grab_task(user_id)

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

            character = last_characters[chat_id]
            
            keyboard = [[
                InlineKeyboardButton("🪼 𝐕𝐢𝐞𝐰 𝐇𝐚𝐫𝐞𝐦", switch_inline_query_current_chat=f"collection.{user_id}"),
                InlineKeyboardButton("📊 𝐒𝐭𝐚𝐭𝐬", callback_data=f"stats_{user_id}")
            ]]

            rarity = character.get('rarity', '🟢 Common')
            if isinstance(rarity, str) and ' ' in rarity:
                rarity_parts = rarity.split(' ', 1)
                rarity_emoji = rarity_parts[0]
                rarity_text = rarity_parts[1] if len(rarity_parts) > 1 else 'Common'
            else:
                rarity_emoji = '🟢'
                rarity_text = rarity

            success_header = random.choice(GRAB_SUCCESS_TEMPLATES)
            user_name = escape(update.effective_user.first_name)
            char_name_fancy = convert_to_fancy(character.get('name', 'Unknown'), 'script')
            anime_name_fancy = convert_to_fancy(character.get('anime', 'Unknown'), 'script')

            success_message = f"""╔═══════════════════════════╗
{success_header}
╚═══════════════════════════╝

✨ <b><a href="tg://user?id={user_id}">{user_name}</a></b> ✨

𝒴𝑜𝓊'𝓋𝑒 𝓈𝓊𝒸𝒸𝑒𝓈𝓈𝒻𝓊𝓁𝓁𝓎 𝒸𝓁𝒶𝒾𝓂𝑒𝒹 𝒶 𝓃𝑒𝓌 𝓌𝒶𝒾𝒻𝓊!

╭─────────────────────────╮
│ 🎀 𝐍𝐚𝐦𝐞: <code>{char_name_fancy}</code>
│ {rarity_emoji} 𝐑𝐚𝐫𝐢𝐭𝐲: <code>{rarity_text}</code>
│ ⚡ 𝐀𝐧𝐢𝐦𝐞: <code>{anime_name_fancy}</code>
╰─────────────────────────╯

✦━━━━━━━━━━━━━━━━━━━━━━✦

💎 𝐂𝐡𝐚𝐫𝐚𝐜𝐭𝐞𝐫 𝐚𝐝𝐝𝐞𝐝 𝐭𝐨 𝐲𝐨𝐮𝐫 𝐜𝐨𝐥𝐥𝐞𝐜𝐭𝐢𝐨𝐧!

✦━━━━━━━━━━━━━━━━━━━━━━✦"""

            await update.message.reply_text(
                success_message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            spawn_message_links.pop(chat_id, None)

        else:
            keyboard = []
            if chat_id in spawn_message_links:
                keyboard.append([
                    InlineKeyboardButton("📍 𝐕𝐢𝐞𝐰 𝐒𝐩𝐚𝐰𝐧", url=spawn_message_links[chat_id])
                ])

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            
            wrong_message = """╔═══════════════════╗
<b>❌ 𝐈𝐧𝐜𝐨𝐫𝐫𝐞𝐜𝐭 𝐍𝐚𝐦𝐞</b>
╚═══════════════════╝

𝒯𝒽𝒶𝓉'𝓈 𝓃𝑜𝓉 𝓉𝒽𝑒 𝒸𝑜𝓇𝓇𝑒𝒸𝓉 𝓃𝒶𝓂𝑒!

💡 𝐓𝐫𝐲 𝐚𝐠𝐚𝐢𝐧!"""
            
            await update.message.reply_html(wrong_message, reply_markup=reply_markup)

    except Exception as e:
        LOGGER.error(f"Error in guess: {e}")
        LOGGER.error(traceback.format_exc())

async def fix_my_db():
    try:
        await collection.drop_index("id_1")
        await collection.drop_index("characters.id_1")
        LOGGER.info("✅ Database indexes cleaned up!")
    except Exception as e:
        LOGGER.info(f"ℹ️ Index clean-up not required or failed: {e}")

async def main():
    try:
        await fix_my_db()
        
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
            LOGGER.warning(f"⚠️ Rarity system not available: {e}")

        try:
            from shivu.modules.backup import setup_backup_handlers
            setup_backup_handlers(application)
            LOGGER.info("✅ Backup system initialized")
        except Exception as e:
            LOGGER.warning(f"⚠️ Backup system not available: {e}")

        await shivuu.start()
        LOGGER.info("✅ Pyrogram client started")

        application.add_handler(CommandHandler(["grab", "g"], guess, block=False))
        application.add_handler(MessageHandler(filters.ALL, message_counter, block=False))

        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        
        LOGGER.info("╔═══════════════════════════╗")
        LOGGER.info("║  ✨ 𝐁𝐎𝐓 𝐒𝐓𝐀𝐑𝐓𝐄𝐃 ✨        ║")
        LOGGER.info("╚═══════════════════════════╝")

        while True:
            await asyncio.sleep(3600)

    except Exception as e:
        LOGGER.error(f"❌ Fatal Error: {e}")
        traceback.print_exc()
    finally:
        LOGGER.info("Cleaning up...")
        try:
            await application.stop()
            await application.shutdown()
            await shivuu.stop()
        except Exception as e:
            LOGGER.error(f"Error during cleanup: {e}")

if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        LOGGER.info("Bot stopped.")