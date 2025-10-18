import importlib
import time
import random
import re
import asyncio
import traceback
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackContext, MessageHandler, filters, Application, CallbackQueryHandler
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
            LOGGER.info(f"✅ Successfully imported: {module_name}")
            success_count += 1
        except Exception as e:
            LOGGER.error(f"❌ Failed to import {module_name}: {e}")
            LOGGER.error(traceback.format_exc())
            fail_count += 1

    LOGGER.info(f"📊 Module Import Summary: {success_count} successful, {fail_count} failed")
    return success_count, fail_count


def import_custom_modules():
    """Import all custom modules with error handling"""
    global spawn_settings_collection

    LOGGER.info("="*50)
    LOGGER.info("IMPORTING CUSTOM MODULES")
    LOGGER.info("="*50)

    # Import rarity module
    try:
        from shivu.modules.rarity import spawn_settings_collection as ssc
        spawn_settings_collection = ssc
        LOGGER.info("✅ Imported: rarity module")
        return True
    except ImportError as e:
        LOGGER.warning(f"⚠️ Rarity module not found: {e}")
        return False
    except Exception as e:
        LOGGER.error(f"❌ Failed to import rarity: {e}")
        LOGGER.error(traceback.format_exc())
        return False


# ==================== PASS SYSTEM INTEGRATION ====================
async def update_grab_task(user_id: int):
    """Update grab task count for pass system"""
    try:
        user = await user_collection.find_one({'id': user_id})
        if user and 'pass_data' in user:
            await user_collection.update_one(
                {'id': user_id},
                {'$inc': {'pass_data.tasks.grabs': 1}}
            )
            LOGGER.debug(f"[PASS] Grab task updated for user {user_id}")
    except Exception as e:
        LOGGER.error(f"[PASS] Error updating grab task: {e}")


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
        if character.get('removed', False):
            LOGGER.debug(f"Character {character.get('id')} is marked as removed")
            return False

        if spawn_settings_collection is not None:
            settings = await spawn_settings_collection.find_one({'type': 'rarity_control'})
            if settings:
                char_rarity = character.get('rarity', '🟢 Common')
                if isinstance(char_rarity, str) and ' ' in char_rarity:
                    rarity_emoji = char_rarity.split(' ')[0]
                else:
                    rarity_emoji = char_rarity

                rarities = settings.get('rarities', {})
                if rarity_emoji in rarities:
                    if not rarities[rarity_emoji].get('enabled', True):
                        LOGGER.debug(f"Character {character.get('id')} has disabled rarity: {rarity_emoji}")
                        return False

            old_settings = await spawn_settings_collection.find_one({'type': 'global'})
            if old_settings:
                disabled_rarities = old_settings.get('disabled_rarities', [])
                char_rarity = character.get('rarity', 'Common')

                if isinstance(char_rarity, str) and ' ' in char_rarity:
                    rarity_emoji = char_rarity.split(' ')[0]
                else:
                    rarity_emoji = char_rarity

                if rarity_emoji in disabled_rarities:
                    LOGGER.debug(f"Character {character.get('id')} has disabled rarity: {rarity_emoji}")
                    return False

                disabled_animes = old_settings.get('disabled_animes', [])
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
        if update.effective_chat.type not in ['group', 'supergroup']:
            return

        if not update.message or not update.message.text:
            return

        if update.message.text.startswith('/'):
            return

        chat_id = str(update.effective_chat.id)
        user_id = update.effective_user.id

        if chat_id not in locks:
            locks[chat_id] = asyncio.Lock()
        lock = locks[chat_id]

        async with lock:
            message_frequency = await get_chat_message_frequency(chat_id)

            if chat_id in last_user and last_user[chat_id]['user_id'] == user_id:
                last_user[chat_id]['count'] += 1
                if last_user[chat_id]['count'] >= 10:
                    if user_id in warned_users and time.time() - warned_users[user_id] < 600:
                        return
                    else:
                        try:
                            await update.message.reply_text(
                                f"⚠️ 𝘿𝙤𝙣'𝙩 𝙎𝙥𝙖𝙢 {escape(update.effective_user.first_name)}...\n"
                                "𝙔𝙤𝙪𝙧 𝙈𝙚𝙨𝙨𝙖𝙜𝙚𝙨 𝙒𝙞𝙡𝙡 𝙗𝙚 𝙞𝙜𝙣𝙤𝙧𝙚𝙙 𝙛𝙤𝙧 10 𝙈𝙞𝙣𝙪𝙩𝙚𝙨..."
                            )
                        except Exception as e:
                            LOGGER.error(f"Error sending spam warning: {e}")
                        warned_users[user_id] = time.time()
                        return
            else:
                last_user[chat_id] = {'user_id': user_id, 'count': 1}

            if chat_id not in message_counts:
                message_counts[chat_id] = 0

            message_counts[chat_id] += 1
            LOGGER.debug(f"Chat {chat_id}: Message {message_counts[chat_id]}/{message_frequency}")

            if message_counts[chat_id] >= message_frequency:
                LOGGER.info(f"[SPAWN] Triggering spawn in chat {chat_id} (reached {message_frequency} messages)")
                await send_image(update, context)
                message_counts[chat_id] = 0

    except Exception as e:
        LOGGER.error(f"[ERROR] Error in message_counter: {e}")
        LOGGER.error(traceback.format_exc())


# ==================== SPAWN CHARACTER ====================
async def send_image(update: Update, context: CallbackContext) -> None:
    """Send a random character image to the chat"""
    chat_id = update.effective_chat.id

    try:
        LOGGER.info(f"[SPAWN] Starting spawn process for chat {chat_id}")

        all_characters = list(await collection.find({}).to_list(length=None))

        if not all_characters:
            LOGGER.error("[SPAWN] No characters found in database")
            return

        LOGGER.info(f"[SPAWN] Total characters in database: {len(all_characters)}")

        if chat_id not in sent_characters:
            sent_characters[chat_id] = []

        if len(sent_characters[chat_id]) >= len(all_characters):
            LOGGER.info(f"[SPAWN] Resetting sent characters for chat {chat_id}")
            sent_characters[chat_id] = []

        available_characters = [
            c for c in all_characters
            if 'id' in c and c.get('id') not in sent_characters[chat_id]
        ]

        if not available_characters:
            available_characters = all_characters
            sent_characters[chat_id] = []

        LOGGER.info(f"[SPAWN] Available characters before filtering: {len(available_characters)}")

        allowed_characters = []
        for char in available_characters:
            if await is_character_allowed(char):
                allowed_characters.append(char)

        LOGGER.info(f"[SPAWN] Allowed characters after filtering: {len(allowed_characters)}")

        if not allowed_characters:
            LOGGER.warning(f"[SPAWN] No allowed characters to spawn in chat {chat_id}")
            return

        character = None
        try:
            if spawn_settings_collection is not None:
                settings = await spawn_settings_collection.find_one({'type': 'rarity_control'})
                if settings and settings.get('rarities'):
                    rarities = settings['rarities']

                    rarity_groups = {}
                    for char in allowed_characters:
                        char_rarity = char.get('rarity', '🟢 Common')
                        if isinstance(char_rarity, str) and ' ' in char_rarity:
                            rarity_emoji = char_rarity.split(' ')[0]
                        else:
                            rarity_emoji = char_rarity

                        if rarity_emoji not in rarity_groups:
                            rarity_groups[rarity_emoji] = []
                        rarity_groups[rarity_emoji].append(char)

                    weighted_chars = []
                    for emoji, chars in rarity_groups.items():
                        if emoji in rarities and rarities[emoji].get('enabled', True):
                            chance = rarities[emoji].get('chance', 0)
                            weight = max(1, int(chance * 10))
                            for char in chars:
                                weighted_chars.extend([char] * weight)

                    if weighted_chars:
                        character = random.choice(weighted_chars)
                        LOGGER.info(f"[SPAWN] Selected character using weighted rarity system")
        except Exception as e:
            LOGGER.error(f"[SPAWN] Error in weighted selection: {e}")
            LOGGER.error(traceback.format_exc())

        if not character:
            character = random.choice(allowed_characters)
            LOGGER.info(f"[SPAWN] Selected character using random selection (fallback)")

        sent_characters[chat_id].append(character['id'])
        last_characters[chat_id] = character

        if chat_id in first_correct_guesses:
            del first_correct_guesses[chat_id]

        rarity = character.get('rarity', 'Common')
        if isinstance(rarity, str) and ' ' in rarity:
            rarity_emoji = rarity.split(' ')[0]
        else:
            rarity_emoji = ''

        caption = (
            f"***{rarity_emoji} ʟᴏᴏᴋ ᴀ ᴡᴀɪғᴜ ʜᴀꜱ ꜱᴘᴀᴡɴᴇᴅ !! "
            f"ᴍᴀᴋᴇ ʜᴇʀ ʏᴏᴜʀ'ꜱ ʙʏ ɢɪᴠɪɴɢ\n/grab 𝚆𝚊𝚒𝚏𝚞 𝚗𝚊𝚖𝚎***"
        )

        await context.bot.send_photo(
            chat_id=chat_id,
            photo=character['img_url'],
            caption=caption,
            parse_mode='Markdown'
        )

        LOGGER.info(f"[SPAWN] Character spawned: {character.get('name', 'Unknown')} (ID: {character.get('id')}, Rarity: {rarity}) in chat {chat_id}")

    except Exception as e:
        LOGGER.error(f"[SPAWN ERROR] {e}")
        LOGGER.error(traceback.format_exc())


# ==================== GUESS HANDLER ====================
async def guess(update: Update, context: CallbackContext) -> None:
    """Handle character guessing"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    try:
        if chat_id not in last_characters:
            return

        if chat_id in first_correct_guesses:
            await update.message.reply_text(
                '🚫 𝙒ᴀɪғᴜ ᴀʟʀᴇᴀᴅʏ ɢʀᴀʙʙᴇᴅ ʙʏ 𝙨ᴏᴍᴇᴏɴᴇ ᴇʟ𝙨ᴇ ⚡, '
                '𝘽ᴇᴛᴛᴇʀ 𝙇ᴜᴄᴋ 𝙉ᴇ𝙭ᴛ 𝙏ɪᴍᴇ'
            )
            return

        guess_text = ' '.join(context.args).lower() if context.args else ''

        if not guess_text:
            await update.message.reply_text('𝙋𝙡𝙚𝙖𝙨𝙚 𝙥𝙧𝙤𝙫𝙞𝙙𝙚 𝙖 𝙣𝙖𝙢𝙚!')
            return

        if "()" in guess_text or "&" in guess_text:
            await update.message.reply_text("𝙉𝙖𝙝𝙝 𝙔𝙤𝙪 𝘾𝙖𝙣'𝙩 𝙪𝙨𝙚 𝙏𝙝𝙞𝙨 𝙏𝙮𝙥𝙚𝙨 𝙤𝙛 𝙬𝙤𝙧𝙙𝙨 ❌️")
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

            success_message = (
                f'<b><a href="tg://user?id={user_id}">{escape(update.effective_user.first_name)}</a></b> '
                f'Congratulations 🎊 You grabbed a new Waifu !!✅\n\n'
                f'🍁 𝙉𝙖𝙢𝙚: <code>{character.get("name", "Unknown")}</code>\n'
                f'⛩️ 𝘼𝙣𝙞𝙢𝙚: <code>{character.get("anime", "Unknown")}</code>\n'
                f'{rarity_emoji} 𝙍𝙖𝙧𝙞𝙩𝙮: <code>{rarity_text}</code>\n\n'
                f'✧⁠ Character successfully added in your harem'
            )

            await update.message.reply_text(
                success_message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            LOGGER.info(f"[GRAB] User {user_id} grabbed {character.get('name')} (Rarity: {rarity}) in chat {chat_id}")

        else:
            await update.message.reply_text('𝙋𝙡𝙚𝙖𝙨𝙚 𝙒𝙧𝙞𝙩𝙚 𝘾𝙤𝙧𝙧𝙚𝙘𝙩 𝙉𝙖𝙢𝙚... ❌️')

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
        # Register grab commands
        application.add_handler(CommandHandler(["grab", "g"], guess, block=False))
        LOGGER.info("✅ Registered: /grab, /g commands")

        # Register rarity module handlers FIRST
        try:
            from shivu.modules.rarity import register_rarity_handlers
            register_rarity_handlers()
            LOGGER.info("✅ Registered: rarity handlers")
        except (ImportError, AttributeError) as e:
            LOGGER.warning(f"⚠️ Rarity module not found or no registration function: {e}")
        except Exception as e:
            LOGGER.error(f"❌ Failed to register rarity handlers: {e}")
            LOGGER.error(traceback.format_exc())

        # Register pass system handlers
        try:
            from shivu.modules.pass_system import (
                pass_command, pclaim_command, sweekly_command, tasks_command,
                upgrade_command, invite_command, passhelp_command, addinvite_command,
                addgrab_command, approve_elite_command, pass_callback
            )

            application.add_handler(CommandHandler("pass", pass_command, block=False))
            application.add_handler(CommandHandler("pclaim", pclaim_command, block=False))
            application.add_handler(CommandHandler("sweekly", sweekly_command, block=False))
            application.add_handler(CommandHandler("tasks", tasks_command, block=False))
            application.add_handler(CommandHandler("upgrade", upgrade_command, block=False))
            application.add_handler(CommandHandler("invite", invite_command, block=False))
            application.add_handler(CommandHandler("passhelp", passhelp_command, block=False))
            application.add_handler(CommandHandler("addinvite", addinvite_command, block=False))
            application.add_handler(CommandHandler("addgrab", addgrab_command, block=False))
            application.add_handler(CommandHandler("approveelite", approve_elite_command, block=False))
            application.add_handler(CallbackQueryHandler(pass_callback, pattern=r"^pass_", block=False))

            LOGGER.info("✅ Registered: pass system handlers")
        except ImportError:
            LOGGER.warning("⚠️ Pass system module not found, skipping")
        except Exception as e:
            LOGGER.error(f"❌ Failed to register pass system handlers: {e}")
            LOGGER.error(traceback.format_exc())

        # Register other module handlers
        module_configs = [
            ('remove', 'register_remove_handlers'),
            ('ckill', 'register_ckill_handler'),
            ('kill', 'register_kill_handler'),
            ('hclaim', 'register_hclaim_handler'),
            ('favorite', 'register_favorite_handlers'),
            ('gift', 'register_gift_handlers'),
            ('trade', 'register_trade_handlers'),
            ('upload', 'register_upload_handlers'),
            ('leaderboard', 'register_leaderboard_handlers'),
            ('collection', 'register_collection_handlers'),
            ('change', 'register_change_handlers'),
            ('sudo', 'register_sudo_handlers'),
        ]

        for module_name, register_func_name in module_configs:
            try:
                module = importlib.import_module(f"shivu.modules.{module_name}")
                if hasattr(module, register_func_name):
                    register_func = getattr(module, register_func_name)
                    register_func()
                    LOGGER.info(f"✅ Registered: {module_name} handlers")
                else:
                    LOGGER.warning(f"⚠️ {module_name} module found but no {register_func_name} function")
            except ImportError:
                LOGGER.warning(f"⚠️ {module_name.capitalize()} module not found, skipping")
            except Exception as e:
                LOGGER.error(f"❌ Failed to register {module_name} handlers: {e}")
                LOGGER.error(traceback.format_exc())

        # Add message handler (MUST BE LAST!)
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            message_counter,
            block=False
        ))
        LOGGER.info("✅ Registered: message counter (spawn handler)")

        LOGGER.info("="*50)
        LOGGER.info("✅ ALL HANDLERS REGISTERED SUCCESSFULLY")
        LOGGER.info(f"📊 Default spawn frequency: {DEFAULT_MESSAGE_FREQUENCY} messages")
        LOGGER.info("="*50)

    except Exception as e:
        LOGGER.error(f"❌ Failed to register handlers: {e}")
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
        LOGGER.info("🚀 Starting bot polling...")
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
        LOGGER.info("🤖 SHIVU BOT STARTING")
        LOGGER.info("="*50)

        # Start the Pyrogram client
        shivuu.start()
        LOGGER.info("✅ Pyrogram client started successfully")

        # Run the bot
        main()

    except KeyboardInterrupt:
        LOGGER.info("⚠️ Bot stopped by user (Ctrl+C)")
    except Exception as e:
        LOGGER.error(f"❌ Fatal error: {e}")
        LOGGER.error(traceback.format_exc())
        raise
    finally:
        try:
            shivuu.stop()
            LOGGER.info("✅ Pyrogram client stopped")
        except:
            pass
        LOGGER.info("="*50)
        LOGGER.info("🛑 BOT SHUTDOWN COMPLETE")
        LOGGER.info("="*50)