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

MESSAGE_FREQUENCY = 1
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
cached_characters = []

spawn_settings_collection = None
group_rarity_collection = None
get_spawn_settings = None
get_group_exclusive = None

SPAWN_EMOJIS = ["🪽", "🪿", "🪻", "🪼", "🫎", "🫚", "🪭", "🫛", "🪯", "🐦‍⬛", "🫏", "🫷", "🧋", "🫧", "🪩"]

for module_name in ALL_MODULES:
    try:
        importlib.import_module("shivu.modules." + module_name)
        LOGGER.info(f"Module loaded: {module_name}")
    except Exception as e:
        LOGGER.error(f"Module failed: {module_name} - {e}")

async def cache_characters():
    global cached_characters
    try:
        cached_characters = list(await collection.find({}).to_list(length=None))
        LOGGER.info(f"Cached {len(cached_characters)} characters")
    except Exception as e:
        LOGGER.error(f"Error caching characters: {e}")

async def is_character_allowed(character, chat_id=None):
    try:
        if character.get('removed', False):
            return False

        char_rarity = character.get('rarity', 'Common')
        rarity_emoji = char_rarity.split(' ')[0] if isinstance(char_rarity, str) and ' ' in char_rarity else char_rarity
        
        is_video = character.get('is_video', False)
        
        if is_video and rarity_emoji == '🎥':
            if chat_id == AMV_ALLOWED_GROUP_ID:
                return True
            else:
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
        LOGGER.error(f"Error in is_character_allowed: {e}")
        return True

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
        except BadRequest:
            pass

        rarity = character.get('rarity', 'Common')
        rarity_emoji = rarity.split(' ')[0] if isinstance(rarity, str) and ' ' in rarity else rarity

        is_video = character.get('is_video', False)
        media_url = character.get('img_url')

        emoji1 = random.choice(SPAWN_EMOJIS)
        emoji2 = random.choice(SPAWN_EMOJIS)

        missed_caption = f"""<b><u>{emoji1} Time's Up {emoji2}</u></b>

<b>{rarity_emoji} Name:</b> <code>{character.get('name', 'Unknown')}</code>
<b>🪼 Anime:</b> <code>{character.get('anime', 'Unknown')}</code>
<b>🪯 Rarity:</b> <code>{rarity}</code>

<i>{random.choice(SPAWN_EMOJIS)} This character has vanished into the void.</i>"""

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
        except BadRequest:
            pass

        last_characters.pop(chat_id, None)
        spawn_messages.pop(chat_id, None)
        spawn_message_links.pop(chat_id, None)
        currently_spawning.pop(chat_id, None)

    except Exception as e:
        LOGGER.error(f"Error in despawn_character: {e}")
    finally:
        currently_spawning.pop(str(chat_id), None)

async def message_counter(update: Update, context: CallbackContext) -> None:
    try:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return

        if not update.message:
            return

        chat_id = update.effective_chat.id
        chat_id_str = str(chat_id)

        if chat_id_str not in locks:
            locks[chat_id_str] = asyncio.Lock()
        
        lock = locks[chat_id_str]

        async with lock:
            if chat_id_str not in message_counts:
                message_counts[chat_id_str] = 0

            message_counts[chat_id_str] += 1
            
            LOGGER.info(f"Chat {chat_id} Count: {message_counts[chat_id_str]}/{MESSAGE_FREQUENCY}")

            if message_counts[chat_id_str] >= MESSAGE_FREQUENCY:
                if chat_id_str not in currently_spawning or not currently_spawning[chat_id_str]:
                    LOGGER.info(f"Spawning in chat {chat_id}")
                    currently_spawning[chat_id_str] = True
                    message_counts[chat_id_str] = 0
                    await send_image(update, context)

    except Exception as e:
        LOGGER.error(f"Error in message_counter: {e}")
        currently_spawning[str(update.effective_chat.id)] = False

async def send_image(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)

    try:
        emoji1 = random.choice(SPAWN_EMOJIS)
        emoji2 = random.choice(SPAWN_EMOJIS)
        emoji3 = random.choice(SPAWN_EMOJIS)
        
        loading_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"<b>{emoji1} {emoji2} {emoji3} Spawning Character {emoji3} {emoji2} {emoji1}</b>",
            parse_mode='HTML'
        )

        if not cached_characters:
            await cache_characters()

        all_characters = cached_characters

        if not all_characters:
            LOGGER.warning("No characters available")
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=loading_msg.message_id)
            except:
                pass
            currently_spawning[chat_id_str] = False
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

        allowed_characters = [c for c in available_characters if await is_character_allowed(c, chat_id)]

        if not allowed_characters:
            LOGGER.warning("No allowed characters")
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=loading_msg.message_id)
            except:
                pass
            currently_spawning[chat_id_str] = False
            return

        character = None

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
                char_rarity = char.get('rarity', 'Common')
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
                        break

        except Exception as e:
            LOGGER.error(f"Error in weighted selection: {e}")

        if not character:
            character = random.choice(allowed_characters)

        sent_characters[chat_id].append(character['id'])
        last_characters[chat_id] = character

        if chat_id in first_correct_guesses:
            del first_correct_guesses[chat_id]

        rarity = character.get('rarity', 'Common')
        rarity_emoji = rarity.split(' ')[0] if isinstance(rarity, str) and ' ' in rarity else rarity

        LOGGER.info(f"Spawned: {character.get('name')} ({rarity_emoji})")

        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=loading_msg.message_id)
        except:
            pass

        spawn_emoji1 = random.choice(SPAWN_EMOJIS)
        spawn_emoji2 = random.choice(SPAWN_EMOJIS)
        spawn_emoji3 = random.choice(SPAWN_EMOJIS)

        caption = f"""<b><u>{spawn_emoji1} A Wild Character Appeared {spawn_emoji2}</u></b>

<b>{spawn_emoji3} A mysterious character has spawned in the chat!</b>

<b>🪼 Quick! Use:</b> <code>/grab [name]</code> or <code>/g [name]</code>
<b>🪯 Time Limit:</b> <code>{DESPAWN_TIME // 60} minutes</code>

<i>🫧 Will you be fast enough to claim this character?</i>"""

        is_video = character.get('is_video', False)
        media_url = character.get('img_url')

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

        spawn_messages[chat_id] = spawn_msg.message_id

        chat_username = update.effective_chat.username
        if chat_username:
            spawn_message_links[chat_id] = f"https://t.me/{chat_username}/{spawn_msg.message_id}"
        else:
            chat_id_str_link = str(chat_id).replace('-100', '')
            spawn_message_links[chat_id] = f"https://t.me/c/{chat_id_str_link}/{spawn_msg.message_id}"

        asyncio.create_task(despawn_character(chat_id, spawn_msg.message_id, character, context))

    except Exception as e:
        LOGGER.error(f"Error in send_image: {e}")
        LOGGER.error(traceback.format_exc())
    finally:
        currently_spawning[chat_id_str] = False

async def guess(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    try:
        if chat_id not in last_characters:
            emoji = random.choice(SPAWN_EMOJIS)
            await update.message.reply_html(
                f'<b><u>{emoji} No Active Spawn</u></b>\n\n'
                f'<i>🪼 No character has spawned yet. Wait for one to appear!</i>'
            )
            return

        if chat_id in first_correct_guesses:
            emoji = random.choice(SPAWN_EMOJIS)
            await update.message.reply_html(
                f'<b><u>{emoji} Already Claimed</u></b>\n\n'
                f'<i>🫧 This character has been grabbed by someone else. Better luck next time!</i>'
            )
            return

        guess_text = ' '.join(context.args).lower() if context.args else ''

        if not guess_text:
            emoji = random.choice(SPAWN_EMOJIS)
            await update.message.reply_html(
                f'<b><u>{emoji} Missing Name</u></b>\n\n'
                f'<b>🪼 Provide a character name!</b>\n\n'
                f'<b>Example:</b> <code>/grab Naruto</code> or <code>/g Sasuke</code>'
            )
            return

        if "()" in guess_text or "&" in guess_text:
            emoji = random.choice(SPAWN_EMOJIS)
            await update.message.reply_html(
                f'<b><u>{emoji} Invalid Input</u></b>\n\n'
                f'<i>🪯 Special characters like (), & are not allowed.</i>'
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

            LOGGER.info(f"User {user_id} grabbed {character_name}")

            if chat_id in spawn_messages:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=spawn_messages[chat_id])
                except BadRequest:
                    pass
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
                InlineKeyboardButton("🪼 View Harem", switch_inline_query_current_chat=f"collection.{user_id}")
            ]]

            rarity = character.get('rarity', 'Common')
            if isinstance(rarity, str) and ' ' in rarity:
                rarity_parts = rarity.split(' ', 1)
                rarity_emoji = rarity_parts[0]
                rarity_text = rarity_parts[1] if len(rarity_parts) > 1 else 'Common'
            else:
                rarity_emoji = rarity
                rarity_text = rarity

            emoji1 = random.choice(SPAWN_EMOJIS)
            emoji2 = random.choice(SPAWN_EMOJIS)
            emoji3 = random.choice(SPAWN_EMOJIS)

            success_message = f"""<b><u>{emoji1} {emoji2} Congratulations {emoji2} {emoji1}</u></b>

<b><a href="tg://user?id={user_id}">{escape(update.effective_user.first_name)}</a></b> <i>successfully grabbed a new character!</i>

<b>🪼 Name:</b> <code>{character.get('name', 'Unknown')}</code>
<b>{rarity_emoji} Rarity:</b> <code>{rarity_text}</code>
<b>🪯 Anime:</b> <code>{character.get('anime', 'Unknown')}</code>

<i>{emoji3} Character added to your collection!</i>"""

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
                    InlineKeyboardButton("🪭 View Spawn", url=spawn_message_links[chat_id])
                ])

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            
            emoji = random.choice(SPAWN_EMOJIS)
            await update.message.reply_html(
                f'<b><u>{emoji} Wrong Name</u></b>\n\n<i>🫧 That\'s not correct. Try again!</i>',
                reply_markup=reply_markup
            )

    except Exception as e:
        LOGGER.error(f"Error in guess: {e}")
        LOGGER.error(traceback.format_exc())

async def fix_my_db():
    try:
        await collection.drop_index("id_1")
        await collection.drop_index("characters.id_1")
        LOGGER.info("Database indexes cleaned")
    except Exception as e:
        LOGGER.info(f"Index cleanup: {e}")

async def main():
    try:
        await fix_my_db()
        
        await cache_characters()
        
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
            LOGGER.info("Rarity system loaded")
        except Exception as e:
            LOGGER.warning(f"Rarity system: {e}")

        try:
            from shivu.modules.backup import setup_backup_handlers
            setup_backup_handlers(application)
            LOGGER.info("Backup system initialized")
        except Exception as e:
            LOGGER.warning(f"Backup system: {e}")

        await shivuu.start()
        LOGGER.info("Pyrogram started")

        application.add_handler(CommandHandler(["grab", "g"], guess, block=False))
        application.add_handler(MessageHandler(filters.ALL, message_counter, block=False))

        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        
        LOGGER.info("BOT STARTED")

        while True:
            await asyncio.sleep(3600)

    except Exception as e:
        LOGGER.error(f"Fatal: {e}")
        traceback.print_exc()
    finally:
        LOGGER.info("Cleaning up")
        try:
            await application.stop()
            await application.shutdown()
            await shivuu.stop()
        except Exception as e:
            LOGGER.error(f"Cleanup error: {e}")

if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        LOGGER.info("Bot stopped")
