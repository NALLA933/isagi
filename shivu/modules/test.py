from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, MessageHandler, filters
from html import escape
import random
import re
from shivu import db, application

# Database collections
collection = db['anime_characters_lol']
user_collection = db['user_collection_lmaoooo']

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


async def add_characters(update: Update, context: CallbackContext) -> None:
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
    target_first_name = None
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_user_id = target_user.id
        target_username = target_user.username
        target_first_name = target_user.first_name
    
    # Parse command arguments
    args = context.args
    text = update.message.text
    
    quantity = None
    rarity_choice = None
    
    # Handle both /add and plain "add" format
    if not args:
        # Try to parse from plain text without command prefix
        match = re.match(r'^(?:/)?add\s+(\d+)\s+(\d+)', text, re.IGNORECASE)
        if match:
            quantity = int(match.group(1))
            rarity_choice = int(match.group(2))
        else:
            rarity_list_text = "\n".join([f"{i+1}. {RARITY_LIST[i]} - {HAREM_MODE_MAPPING[RARITY_LIST[i]]}" 
                                          for i in range(len(RARITY_LIST))])
            await update.message.reply_text(
                "❌ <b>Invalid format!</b>\n\n"
                "<b>Usage:</b> <code>/add &lt;quantity&gt; &lt;rarity&gt;</code> or <code>add &lt;quantity&gt; &lt;rarity&gt;</code>\n\n"
                "<b>Rarity Options:</b>\n" + rarity_list_text,
                parse_mode='HTML'
            )
            return
    else:
        if len(args) < 2:
            rarity_list_text = "\n".join([f"{i+1}. {RARITY_LIST[i]} - {HAREM_MODE_MAPPING[RARITY_LIST[i]]}" 
                                          for i in range(len(RARITY_LIST))])
            await update.message.reply_text(
                "❌ <b>Invalid format!</b>\n\n"
                "<b>Usage:</b> <code>/add &lt;quantity&gt; &lt;rarity&gt;</code> or <code>add &lt;quantity&gt; &lt;rarity&gt;</code>\n\n"
                "<b>Rarity Options:</b>\n" + rarity_list_text,
                parse_mode='HTML'
            )
            return
        
        try:
            quantity = int(args[0])
            rarity_choice = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ Quantity and rarity must be numbers!")
            return
    
    # Check for username in args (optional, for direct targeting)
    if args and len(args) >= 3 and not target_user_id:
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
            "❌ <b>Please specify a user!</b>\n\n"
            "You can:\n"
            "• Reply to a user's message\n"
            "• Use: <code>/add &lt;quantity&gt; &lt;rarity&gt; &lt;user_id&gt;</code>\n"
            "• Use: <code>/add &lt;quantity&gt; &lt;rarity&gt; @username</code>",
            parse_mode='HTML'
        )
        return
    
    # Validate quantity
    if quantity < 1 or quantity > 100:
        await update.message.reply_text("❌ Quantity must be between 1 and 100!")
        return
    
    # Validate rarity choice
    if rarity_choice < 1 or rarity_choice > len(RARITY_LIST):
        rarity_list_text = "\n".join([f"{i+1}. {RARITY_LIST[i]} - {HAREM_MODE_MAPPING[RARITY_LIST[i]]}" 
                                      for i in range(len(RARITY_LIST))])
        await update.message.reply_text(
            f"❌ <b>Invalid rarity!</b> Choose between 1 and {len(RARITY_LIST)}\n\n"
            "<b>Rarity Options:</b>\n" + rarity_list_text,
            parse_mode='HTML'
        )
        return
    
    selected_rarity = RARITY_LIST[rarity_choice - 1]
    rarity_display = HAREM_MODE_MAPPING[selected_rarity]
    
    # Get random characters from database with selected rarity
    try:
        characters = await collection.aggregate([
            {"$match": {"rarity": selected_rarity}},
            {"$sample": {"size": quantity}}
        ]).to_list(length=quantity)
    except Exception as e:
        print(f"Error fetching characters: {e}")
        await update.message.reply_text(f"❌ Error fetching characters from database!")
        return
    
    if not characters:
        await update.message.reply_text(f"❌ No characters found with rarity: {rarity_display}")
        return
    
    # Add characters to user's collection
    added_characters = []
    for char in characters:
        character_data = {
            'id': char.get('id'),
            'name': char.get('name'),
            'anime': char.get('anime'),
            'img_url': char.get('img_url'),
            'rarity': char.get('rarity'),
        }
        
        # Add to user collection
        try:
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
        except Exception as e:
            print(f"Error adding character to collection: {e}")
            continue
        
        added_characters.append(f"• {escape(char.get('name', 'Unknown'))} ({escape(char.get('anime', 'Unknown'))})")
    
    # Send success message
    if target_username:
        target_display = f"@{target_username}"
    elif target_first_name:
        target_display = escape(target_first_name)
    else:
        target_display = f"User ID: {target_user_id}"
    
    success_msg = (
        f"✅ <b>Characters Added Successfully!</b>\n\n"
        f"<b>Target:</b> {target_display}\n"
        f"<b>Quantity:</b> {quantity}\n"
        f"<b>Rarity:</b> {rarity_display}\n\n"
        f"<b>Added Characters:</b>\n" + "\n".join(added_characters[:10])
    )
    
    if len(added_characters) > 10:
        success_msg += f"\n<i>... and {len(added_characters) - 10} more!</i>"
    
    # Get random character image for display
    random_char = random.choice(characters)
    char_img = random_char.get('img_url')
    
    if char_img:
        await update.message.reply_photo(
            photo=char_img,
            caption=success_msg,
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(success_msg, parse_mode='HTML')


async def handle_add_message(update: Update, context: CallbackContext) -> None:
    """Handle both /add command and plain 'add' messages"""
    text = update.message.text.strip()
    
    # Check if message starts with "add" (case insensitive)
    if re.match(r'^add\s+\d+\s+\d+', text, re.IGNORECASE):
        # Parse as add command
        await add_characters(update, context)


# Register handlers
application.add_handler(CommandHandler("add", add_characters, block=False))
application.add_handler(MessageHandler(
    filters.TEXT & filters.Regex(r'^add\s+\d+\s+\d+', re.IGNORECASE), 
    handle_add_message,
    block=False
))