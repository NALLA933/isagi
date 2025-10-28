from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, MessageHandler, filters
import re
from shivu import application, shivuu, LOGGER

# Database
db = shivuu['Character_catcher']
collection = db['anime_characters_lol']
user_collection = db["user_collection_lmaoooo"]
user_totals_collection = db['user_totals_lmaoooo']

# Owners
OWNERS = [8420981179, 5147822244]

# Rarities
RARITIES = {
    1: ("common", "🟢 Common"),
    2: ("rare", "🟣 Rare"),
    3: ("legendary", "🟡 Legendary"),
    4: ("special", "💮 Special Edition"),
    5: ("neon", "💫 Neon"),
    6: ("manga", "✨ Manga"),
    7: ("cosplay", "🎭 Cosplay"),
    8: ("celestial", "🎐 Celestial"),
    9: ("premium", "🔮 Premium Edition"),
    10: ("erotic", "💋 Erotic"),
    11: ("summer", "🌤 Summer"),
    12: ("winter", "☃️ Winter"),
    13: ("monsoon", "☔️ Monsoon"),
    14: ("valentine", "💝 Valentine"),
    15: ("halloween", "🎃 Halloween"),
    16: ("christmas", "🎄 Christmas"),
    17: ("mythic", "🏵 Mythic"),
    18: ("events", "🎗 Special Events"),
    19: ("amv", "🎥 Amv"),
    20: ("tiny", "👼 Tiny")
}

async def add_command(update: Update, context: CallbackContext):
    """Add characters: add 10 1 (reply) or add 10 1 @user"""
    
    user_id = update.effective_user.id
    
    # Owner check
    if user_id not in OWNERS:
        return
    
    LOGGER.info(f"[ADD] Command called by {user_id}")
    
    # Parse input
    text = update.message.text.strip()
    match = re.search(r'(\d+)\s+(\d+)', text)
    
    if not match:
        await update.message.reply_text("Usage: add <quantity> <rarity>\nExample: add 10 1")
        return
    
    qty = int(match.group(1))
    rarity_num = int(match.group(2))
    
    # Validate
    if not (1 <= qty <= 100):
        await update.message.reply_text("❌ Quantity: 1-100")
        return
    
    if rarity_num not in RARITIES:
        await update.message.reply_text(f"❌ Rarity: 1-{len(RARITIES)}")
        return
    
    # Get target user
    target_id = None
    target_name = None
    target_first_name = None
    
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        target_id = user.id
        target_name = user.username
        target_first_name = user.first_name
        LOGGER.info(f"[ADD] Target from reply: {target_id}")
    else:
        words = text.split()
        if len(words) >= 3:
            arg = words[2].lstrip('@')
            if arg.isdigit():
                target_id = int(arg)
                LOGGER.info(f"[ADD] Target from ID: {target_id}")
            else:
                target_name = arg
                LOGGER.info(f"[ADD] Target from username: {target_name}")
    
    if not target_id and not target_name:
        await update.message.reply_text("❌ Reply to user or use: add 10 1 @username")
        return
    
    # Get rarity
    rarity_key, rarity_display = RARITIES[rarity_num]
    
    # Fetch random characters
    try:
        chars = await collection.aggregate([
            {"$match": {"rarity": rarity_key}},
            {"$sample": {"size": qty}}
        ]).to_list(qty)
        
        if not chars:
            await update.message.reply_text(f"❌ No {rarity_display} characters found")
            return
        
        LOGGER.info(f"[ADD] Found {len(chars)} characters")
        
    except Exception as e:
        LOGGER.error(f"[ADD ERROR] Failed to fetch characters: {e}")
        await update.message.reply_text("❌ Database error")
        return
    
    # Prepare data
    char_list = [{
        'id': c['id'],
        'name': c['name'],
        'anime': c['anime'],
        'img_url': c['img_url'],
        'rarity': c['rarity']
    } for c in chars]
    
    # Bulk insert
    try:
        # Find user by ID or username
        query = {'id': target_id} if target_id else {'username': target_name}
        
        await user_collection.update_one(
            query,
            {
                '$push': {'characters': {'$each': char_list}},
                '$set': {
                    'username': target_name,
                    'first_name': target_first_name
                }
            },
            upsert=True
        )
        
        await user_totals_collection.update_one(
            query,
            {
                '$inc': {'count': qty},
                '$set': {
                    'username': target_name,
                    'first_name': target_first_name
                }
            },
            upsert=True
        )
        
        LOGGER.info(f"[ADD] Successfully added {qty} characters to {target_id or target_name}")
        
    except Exception as e:
        LOGGER.error(f"[ADD ERROR] Failed to insert characters: {e}")
        await update.message.reply_text("❌ Failed to add characters")
        return
    
    # Response
    names = '\n'.join([f"• {c['name']}" for c in chars[:5]])
    if len(chars) > 5:
        names += f"\n... +{len(chars)-5} more"
    
    display_name = f"@{target_name}" if target_name else target_first_name or target_id
    
    await update.message.reply_text(
        f"✅ Added {qty}x {rarity_display}\n"
        f"👤 {display_name}\n\n{names}"
    )

# ------------------ HANDLER REGISTRATION ------------------
def register_add_handler():
    """Register /add command and text handlers"""
    
    # /add command handler
    add_cmd_handler = CommandHandler('add', add_command, block=False)
    
    # Plain text "add" handler (without /)
    add_text_handler = MessageHandler(
        filters.TEXT & filters.Regex(r'^add\s+\d+\s+\d+', re.IGNORECASE) & ~filters.COMMAND,
        add_command,
        block=False
    )
    
    application.add_handler(add_cmd_handler)
    application.add_handler(add_text_handler)
    
    LOGGER.info("[ADD] Handlers registered successfully")

# Initialize on import
register_add_handler()