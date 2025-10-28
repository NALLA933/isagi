from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, MessageHandler, filters
from html import escape 
import random
import re
from shivu import application, shivuu

# MongoDB setup
lol = shivuu
db = lol['Character_catcher']
collection = db['anime_characters_lol']
user_collection = db["user_collection_lmaoooo"]
user_totals_collection = db['user_totals_lmaoooo']

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
        return
    
    # Check if it's a reply to another user
    target_user = None
    target_user_id = None
    target_username = None
    target_first_name = None
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_user_id = target_user.id
        target_username = target_user.username
        target_first_name = target_user.first_name
    
    # Parse command arguments
    text = update.message.text.strip()
    
    # Parse quantity and rarity from text - works with or without command prefix
    match = re.search(r'(?:add\s+)?(\d+)\s+(\d+)', text, re.IGNORECASE)
    if not match:
        await update.message.reply_text(
            "❌ Invalid format!\n\nUsage: `add <quantity> <rarity>` or `/add <quantity> <rarity>`\n\n"
            "Rarities: 1=Common, 2=Rare, 3=Legendary, 4=Special, 5=Neon, 6=Manga, 7=Cosplay, 8=Celestial, 9=Premium, 10=Erotic, 11=Summer, 12=Winter, 13=Monsoon, 14=Valentine, 15=Halloween, 16=Christmas, 17=Mythic, 18=Events, 19=Amv, 20=Tiny",
            parse_mode='Markdown'
        )
        return
    
    quantity = int(match.group(1))
    rarity_choice = int(match.group(2))
    
    # Check for username/ID in args
    args = context.args if context.args else text.split()[1:]
    if len(args) >= 3 and not target_user_id:
        username_or_id = args[2]
        if username_or_id.isdigit():
            target_user_id = int(username_or_id)
        else:
            target_username = username_or_id.lstrip('@')
    
    # Validate target user
    if not target_user_id:
        await update.message.reply_text("❌ Reply to a user or provide user ID/username!")
        return
    
    # Validate quantity
    if quantity < 1 or quantity > 100:
        await update.message.reply_text("❌ Quantity must be between 1 and 100!")
        return
    
    # Validate rarity choice
    if rarity_choice < 1 or rarity_choice > len(RARITY_LIST):
        await update.message.reply_text(f"❌ Invalid rarity! Choose between 1 and {len(RARITY_LIST)}")
        return
    
    selected_rarity = RARITY_LIST[rarity_choice - 1]
    rarity_display = HAREM_MODE_MAPPING[selected_rarity]
    
    # Get random characters from database with selected rarity
    pipeline = [
        {"$match": {"rarity": selected_rarity}},
        {"$sample": {"size": quantity}}
    ]
    
    characters = await collection.aggregate(pipeline).to_list(length=quantity)
    
    if not characters:
        await update.message.reply_text(f"❌ No characters found with rarity: {rarity_display}")
        return
    
    # Prepare bulk character data
    character_list = []
    for char in characters:
        character_data = {
            'id': char['id'],
            'name': char['name'],
            'anime': char['anime'],
            'img_url': char['img_url'],
            'rarity': char['rarity'],
        }
        character_list.append(character_data)
    
    # Add all characters to user collection in one operation
    await user_collection.update_one(
        {'id': target_user_id},
        {
            '$push': {'characters': {'$each': character_list}},
            '$set': {
                'username': target_username,
                'first_name': target_first_name
            }
        },
        upsert=True
    )
    
    # Update user totals
    await user_totals_collection.update_one(
        {'id': target_user_id},
        {
            '$inc': {'count': quantity},
            '$set': {
                'username': target_username,
                'first_name': target_first_name
            }
        },
        upsert=True
    )
    
    # Send success message
    target_display = f"@{target_username}" if target_username else target_first_name or f"User {target_user_id}"
    
    char_names = [f"• {c['name']}" for c in characters[:5]]
    char_display = "\n".join(char_names)
    if len(characters) > 5:
        char_display += f"\n... and {len(characters) - 5} more!"
    
    success_msg = (
        f"✅ Added {quantity} x {rarity_display} to {target_display}\n\n"
        f"{char_display}"
    )
    
    await update.message.reply_text(success_msg)

# Handler for both /add command and plain "add" text
async def handle_add_message(update: Update, context: CallbackContext):
    """Handle plain 'add' messages without prefix"""
    await add_characters(update, context)

# Register handlers - Add these at the bottom of your main bot file
def register_handlers():
    """Register the add command handlers"""
    # Handler for /add command
    application.add_handler(CommandHandler("add", add_characters, block=False))
    
    # Handler for plain "add" without slash (higher priority)
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r'^add\s+\d+\s+\d+', re.IGNORECASE) & ~filters.COMMAND,
        handle_add_message,
        block=False
    ))
    
    # Handler for messages starting with numbers (for ultra-fast usage)
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r'^\d+\s+\d+$') & filters.REPLY,
        handle_add_message,
        block=False
    ))

# Auto-register when module is imported
register_handlers()