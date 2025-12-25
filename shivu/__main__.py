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
    # ... (keep all your existing functions exactly as they are)
    # Your existing is_character_allowed function
    pass


async def get_chat_message_frequency(chat_id):
    # ... (keep all your existing functions exactly as they are)
    pass


async def update_grab_task(user_id: int):
    # ... (keep all your existing functions exactly as they are)
    pass


async def despawn_character(chat_id, message_id, character, context):
    # ... (keep all your existing functions exactly as they are)
    pass


async def message_counter(update: Update, context: CallbackContext) -> None:
    # ... (keep all your existing functions exactly as they are)
    pass


async def send_image(update: Update, context: CallbackContext) -> None:
    # ... (keep all your existing functions exactly as they are)
    pass


async def guess(update: Update, context: CallbackContext) -> None:
    # ... (keep all your existing functions exactly as they are)
    pass


def setup_handlers() -> None:
    """Setup all command handlers"""
    application.add_handler(CommandHandler(["grab", "g"], guess, block=False))
    application.add_handler(MessageHandler(filters.ALL, message_counter, block=False))


async def main() -> None:
    """Main async entry point"""
    LOGGER.info("Bot starting...")
    
    # Setup handlers
    setup_handlers()
    
    # Start the bot
    await shivuu.initialize()
    await shivuu.start()
    
    # Start the auction monitor task
    monitor_task = asyncio.create_task(monitor_auctions())
    
    LOGGER.info("✅ ʏᴏɪᴄʜɪ ʀᴀɴᴅɪ ʙᴏᴛ sᴛᴀʀᴛᴇᴅ")
    
    try:
        # Keep the bot running
        await application.start()
        await shivuu.idle()
    finally:
        # Cleanup
        await shivuu.stop()
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    # Start the bot with proper async handling
    asyncio.run(main())
