from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler, filters
from html import escape 
import random
import re
from shivu import application
from motor.motor_asyncio import AsyncIOMotorClient

# MongoDB setup
lol = AsyncIOMotorClient('your_mongodb_connection_string')
db = lol['Character_catcher']
collection = db['anime_characters_lol']
user_collection = db["user_collection_lmaoooo"]

# Owner IDs
OWNERS = [8420981179, 5147822244]

# Rarity mapping
HAREM_MODE_MAPPING = {
    "common": "🟢 Common",
    "rare": "🟣 Rare",
    "legendary": "🟡 Legendary",
    "special": "💮 Special Edition",
    "neon": "💫 Neon",
    "manga": "✨ Manga",
    "cosplay": "🎭 Cosplay",
    "celestial": "🎐 Celestial",
    "premium": "🔮 Premium Edition",
    "erotic": "💋 Erotic",
    "summer": "🌤 Summer",
    "winter": "☃️ Winter",
    "monsoon": "☔️ Monsoon",
    "valentine": "💝 Valentine",
    "halloween": "🎃 Halloween",
    "christmas": "🎄 Christmas",
    "mythic": "🏵 Mythic",
    "events": "🎗 Special Events",
    "amv": "🎥 Amv",
    "tiny": "👼 Tiny",
}

RARITY_LIST = list(HAREM_MODE_MAPPING.keys())

async def add_characters(update: Update, context: CallbackContext):
    """Add random characters to a user. Usage: /add <quantity> <rarity_number> or add <quantity> <rarity_number>"""
    
    user_id = update.effective_user.id
    
    # Check if user is owner
    if user_id not in OWNERS:
        await update.message.reply_text("❌ You don't have permission to use this command!")
        return
    
    # Check if it's a reply to another user
    target_user = None
    target_user_id = None
    target_username = None
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_user_id = target_user.id
        target_username = target_user.username or target_user.first_name
    
    # Parse command arguments
    args = context.args
    text = update.message.text
    
    # Handle both /add and plain "add" format
    if not args:
        # Try to parse from plain text without command prefix
        match = re.match(r'^(?:/)?add\s+(\d+)\s+(\d+)', text, re.IGNORECASE)
        if match:
            quantity = int(match.group(1))
            rarity_choice = int(match.group(2))
        else:
            await update.message.reply_text(
                "❌ Invalid format!\n\n"
                "Usage: `/add <quantity> <rarity>` or `add <quantity> <rarity>`\n\n"
                "**Rarity Options:**\n" + 
                "\n".join([f"{i+1}. {RARITY_LIST[i]} - {HAREM_MODE_MAPPING[RARITY_LIST[i]]}" 
                          for i in range(len(RARITY_LIST))]),
                parse_mode='Markdown'
            )
            return
    else:
        if len(args) < 2:
            await update.message.reply_text(
                "❌ Invalid format!\n\n"
                "Usage: `/add <quantity> <rarity>` or `add <quantity> <rarity>`\n\n"
                "**Rarity Options:**\n" + 
                "\n".join([f"{i+1}. {RARITY_LIST[i]} - {HAREM_MODE_MAPPING[RARITY_LIST[i]]}" 
                          for i in range(len(RARITY_LIST))]),
                parse_mode='Markdown'
            )
            return
        
        try:
            quantity = int(args[0])
            rarity_choice = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ Quantity and rarity must be numbers!")
            return
    
    # Check for username in args (optional, for direct targeting)
    if len(args) >= 3 and not target_user_id:
        username_or_id = args[2]
        # Check if it's a user ID
        if username_or_id.isdigit():
            target_user_id = int(username_or_id)
        else:
            # Remove @ if present
            target_username = username_or_id.lstrip('@')
    
    # Validate target user
    if not target_user_id and not target_username:
        await update.message.reply_text(
            "❌ Please specify a user!\n\n"
            "You can:\n"
            "• Reply to a user's message\n"
            "• Use: `/add <quantity> <rarity> <user_id>`\n"
            "• Use: `/add <quantity> <rarity> @username`",
            parse_mode='Markdown'
        )
        return
    
    # Validate quantity
    if quantity < 1 or quantity > 100:
        await update.message.reply_text("❌ Quantity must be between 1 and 100!")
        return
    
    # Validate rarity choice
    if rarity_choice < 1 or rarity_choice > len(RARITY_LIST):
        await update.message.reply_text(
            f"❌ Invalid rarity! Choose between 1 and {len(RARITY_LIST)}\n\n"
            "**Rarity Options:**\n" + 
            "\n".join([f"{i+1}. {RARITY_LIST[i]} - {HAREM_MODE_MAPPING[RARITY_LIST[i]]}" 
                      for i in range(len(RARITY_LIST))]),
            parse_mode='Markdown'
        )
        return
    
    selected_rarity = RARITY_LIST[rarity_choice - 1]
    rarity_display = HAREM_MODE_MAPPING[selected_rarity]
    
    # Get random characters from database with selected rarity
    characters = await collection.aggregate([
        {"$match": {"rarity": selected_rarity}},
        {"$sample": {"size": quantity}}
    ]).to_list(length=quantity)
    
    if not characters:
        await update.message.reply_text(f"❌ No characters found with rarity: {rarity_display}")
        return
    
    # Add characters to user's collection
    added_characters = []
    for char in characters:
        character_data = {
            'id': char['id'],
            'name': char['name'],
            'anime': char['anime'],
            'img_url': char['img_url'],
            'rarity': char['rarity'],
        }
        
        # Add to user collection
        if target_user_id:
            await user_collection.update_one(
                {'id': target_user_id},
                {'$push': {'characters': character_data}},
                upsert=True
            )
        elif target_username:
            await user_collection.update_one(
                {'username': target_username},
                {'$push': {'characters': character_data}},
                upsert=True
            )
        
        added_characters.append(f"• {char['name']} ({char['anime']})")
    
    # Send success message
    target_display = f"@{target_username}" if target_username else f"User ID: {target_user_id}"
    
    success_msg = (
        f"✅ **Characters Added Successfully!**\n\n"
        f"**Target:** {target_display}\n"
        f"**Quantity:** {quantity}\n"
        f"**Rarity:** {rarity_display}\n\n"
        f"**Added Characters:**\n" + "\n".join(added_characters[:10])
    )
    
    if len(added_characters) > 10:
        success_msg += f"\n... and {len(added_characters) - 10} more!"
    
    await update.message.reply_text(success_msg, parse_mode='Markdown')

# Handler for both /add command and plain "add" text
async def handle_add_message(update: Update, context: CallbackContext):
    """Handle both /add command and plain 'add' messages"""
    text = update.message.text.strip()
    
    # Check if message starts with "add" (case insensitive)
    if re.match(r'^add\s+\d+\s+\d+', text, re.IGNORECASE):
        # Parse as add command
        await add_characters(update, context)

# Register handlers
application.add_handler(CommandHandler("add", add_characters))
application.add_handler(MessageHandler(
    filters.TEXT & filters.Regex(r'^add\s+\d+\s+\d+', re.IGNORECASE), 
    handle_add_message
))