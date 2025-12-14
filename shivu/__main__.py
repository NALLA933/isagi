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
from shivu.autofix_system import create_autofix_system, apply_autofix_to_handlers

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

autofix = create_autofix_system(shivuu, LOGGER)

for module_name in ALL_MODULES:
    try:
        loaded_module = importlib.import_module("shivu.modules." + module_name)
        autofix.wrap_module(loaded_module)
        LOGGER.info(f"✅ Module loaded with auto-fix: {module_name}")
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


@autofix.wrap_handler(module_name="main")
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


@autofix.wrap_handler(module_name="main")
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


@autofix.wrap_handler(module_name="main")
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


@autofix.wrap_handler(module_name="main")
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


@autofix.wrap_handler(module_name="main")
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


@autofix.wrap_handler(module_name="main")
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

        caption = f"""***{rarity_emoji} ʟᴏᴏᴋ ᴀ ᴡᴀɪғᴜ ʜᴀs sᴘᴀᴡɴᴇᴅ !! ᴍᴀᴋᴇ ʜᴇʀ ʏᴏᴜʀ's ʙʏ ɢɪᴠɪɴɢ
/grab 𝚆𝚊𝚒𝚏𝚞 𝚗𝚊𝚖𝚎

⏰ ʏᴏᴜ ʜᴀᴠᴇ {DESPAWN_TIME // 60} ᴍɪɴᴜᴛᴇs ᴛᴏ ɢʀᴀʙ!***"""

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


@autofix.wrap_handler(module_name="main")
async def guess(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    try:
        if chat_id not in last_characters:
            await update.message.reply_html('<b>ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ ʏᴇᴛ!</b>')
            return

        if chat_id in first_correct_guesses:
            await update.message.reply_html(
                '<b>🚫 ᴡᴀɪғᴜ ᴀʟʀᴇᴀᴅʏ ɢʀᴀʙʙᴇᴅ ʙʏ sᴏᴍᴇᴏɴᴇ ᴇʟsᴇ ⚡. ʙᴇᴛᴛᴇʀ ʟᴜᴄᴋ ɴᴇxᴛ ᴛɪᴍᴇ..!!</b>'
            )
            return

        guess_text = ' '.join(context.args).lower() if context.args else ''

        if not guess_text:
            await update.message.reply_html('<b>ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ɴᴀᴍᴇ!</b>')
            return

        if "()" in guess_text or "&" in guess_text:
            await update.message.reply_html(
                "<b>ɴᴀʜʜ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴜsᴇ ᴛʜɪs ᴛʏᴘᴇs ᴏғ ᴡᴏʀᴅs...❌</b>"
            )
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

            spawn_message_links.pop(chat_id, None)

        else:
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


def main() -> None:
    application.add_handler(CommandHandler(["grab", "g"], guess, block=False))
    application.add_handler(MessageHandler(filters.ALL, message_counter, block=False))

    apply_autofix_to_handlers(application, autofix)

    LOGGER.info("🚀 Bot starting with auto-fix protection...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    shivuu.start()
    LOGGER.info("✅ ʏᴏɪᴄʜɪ ʀᴀɴᴅɪ ʙᴏᴛ sᴛᴀʀᴛᴇᴅ ᴡɪᴛʜ ᴀᴜᴛᴏ-ғɪx sʏsᴛᴇᴍ")
    main()