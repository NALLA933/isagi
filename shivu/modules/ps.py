import random
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler

from shivu import application, db, user_collection, CHARA_CHANNEL_ID, SUPPORT_CHAT

collection = db['anime_characters_lol']
ps_config_collection = db['ps_config']
characters_collection = collection

sudo_users = ["8297659126", "8420981179", "5147822244"]

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
    "default": None
}

# Default configuration
DEFAULT_PS_CONFIG = {
    "rarities": {
        "🟢 Common": {"weight": 60, "price": 2000},
        "🟣 Rare": {"weight": 25, "price": 5000},
        "🟡 Legendary": {"weight": 10, "price": 10000},
        "💮 Special Edition": {"weight": 5, "price": 25000}
    },
    "refresh_cost": 20000,
    "refresh_limit": 2,
    "store_items": 3,
    "cooldown_hours": 24
}

async def is_sudo_user(user_id: int) -> bool:
    return str(user_id) in sudo_users

async def get_ps_config():
    """Get PS configuration from database or return default"""
    config = await ps_config_collection.find_one({"_id": "ps_config"})
    if not config:
        await ps_config_collection.insert_one({"_id": "ps_config", **DEFAULT_PS_CONFIG})
        return DEFAULT_PS_CONFIG
    return config

async def get_random_rarity(config):
    """Get random rarity based on weights"""
    rarities = config['rarities']
    rarity_list = list(rarities.keys())
    weights = [rarities[r]['weight'] for r in rarity_list]
    return random.choices(rarity_list, weights=weights, k=1)[0]

async def generate_ps_characters(user_id, config):
    """Generate random characters for private store"""
    try:
        store_items = config.get('store_items', 3)
        characters = []
        
        for _ in range(store_items):
            rarity = await get_random_rarity(config)
            
            # Get random character from collection
            pipeline = [
                {'$match': {'rarity': rarity}},
                {'$sample': {'size': 1}}
            ]
            
            char = await characters_collection.aggregate(pipeline).to_list(length=1)
            if char:
                characters.append(char[0])
            else:
                # Fallback: get any character if specific rarity not found
                any_char = await characters_collection.aggregate([{'$sample': {'size': 1}}]).to_list(length=1)
                if any_char:
                    characters.append(any_char[0])
        
        return characters
    except Exception as e:
        print(f"Error generating PS characters: {e}")
        return []

async def get_user_ps_data(user_id):
    """Get user's private store data"""
    user = await user_collection.find_one({"id": user_id})
    if not user:
        return None
    
    return user.get('private_store', {
        'characters': [],
        'last_reset': None,
        'refresh_count': 0,
        'last_refresh': None
    })

async def update_user_ps_data(user_id, ps_data):
    """Update user's private store data"""
    await user_collection.update_one(
        {"id": user_id},
        {"$set": {"private_store": ps_data}},
        upsert=True
    )

def get_time_remaining(target_time):
    """Calculate time remaining until target time"""
    if not target_time:
        return "N/A"
    
    now = datetime.utcnow()
    if isinstance(target_time, str):
        target_time = datetime.fromisoformat(target_time)
    
    remaining = target_time - now
    if remaining.total_seconds() <= 0:
        return "Available now"
    
    hours = int(remaining.total_seconds() // 3600)
    minutes = int((remaining.total_seconds() % 3600) // 60)
    return f"{hours}h {minutes}m"

async def build_ps_caption(character, config, page, total, ps_data, user_balance):
    """Build caption for private store character"""
    char_id = character.get("id", character.get("_id"))
    name = character.get("name", "Unknown")
    anime = character.get("anime", "Unknown")
    rarity = character.get("rarity", "Unknown")
    img_url = character.get("img_url", "")
    
    # Get price from config
    price = config['rarities'].get(rarity, {}).get('price', 0)
    
    # Check refresh info
    refresh_limit = config.get('refresh_limit', 2)
    refresh_count = ps_data.get('refresh_count', 0)
    refreshes_left = max(0, refresh_limit - refresh_count)
    
    # Calculate next free store time
    last_reset = ps_data.get('last_reset')
    cooldown_hours = config.get('cooldown_hours', 24)
    if last_reset:
        if isinstance(last_reset, str):
            last_reset = datetime.fromisoformat(last_reset)
        next_reset = last_reset + timedelta(hours=cooldown_hours)
        time_remaining = get_time_remaining(next_reset)
    else:
        time_remaining = "Available now"
    
    caption = (
        f"╭─━━━━━━━━━━━━━━━─╮\n"
        f"│  🎁 𝗣𝗥𝗜𝗩𝗔𝗧𝗘 𝗦𝗧𝗢𝗥𝗘  │\n"
        f"╰─━━━━━━━━━━━━━━━─╯\n\n"
        f"✨ <b>{name}</b>\n\n"
        f"🎭 𝗔𝗻𝗶𝗺𝗲: <code>{anime}</code>\n"
        f"💫 𝗥𝗮𝗿𝗶𝘁𝘆: {rarity}\n"
        f"💎 𝗣𝗿𝗶𝗰𝗲: <b>{price}</b> Gold\n"
        f"🔖 𝗜𝗗: <code>{char_id}</code>\n\n"
        f"📖 𝗣𝗮𝗴𝗲: {page}/{total}\n"
        f"💰 𝗬𝗼𝘂𝗿 𝗕𝗮𝗹𝗮𝗻𝗰𝗲: <b>{user_balance}</b> Gold\n\n"
        f"🌀 𝗥𝗲𝗳𝗿𝗲𝘀𝗵𝗲𝘀 𝗹𝗲𝗳𝘁: {refreshes_left}/{refresh_limit}\n"
        f"⏰ 𝗡𝗲𝘅𝘁 𝗳𝗿𝗲𝗲 𝘀𝘁𝗼𝗿𝗲: {time_remaining}\n\n"
        f"Tap <b>Buy</b> to purchase this character!"
    )
    
    return caption, img_url, price

async def ps(update: Update, context: CallbackContext):
    """Private Store command"""
    user_id = update.effective_user.id
    config = await get_ps_config()
    
    # Get user data
    user = await user_collection.find_one({"id": user_id})
    if not user:
        await update.message.reply_text(
            "⚠️ You need to start the bot first!\n"
            "Use /start to begin your journey.",
            parse_mode="HTML"
        )
        return
    
    user_balance = user.get('balance', 0)
    ps_data = await get_user_ps_data(user_id)
    
    # Check if store needs reset
    cooldown_hours = config.get('cooldown_hours', 24)
    last_reset = ps_data.get('last_reset')
    needs_reset = True
    
    if last_reset:
        if isinstance(last_reset, str):
            last_reset = datetime.fromisoformat(last_reset)
        time_since_reset = datetime.utcnow() - last_reset
        needs_reset = time_since_reset.total_seconds() >= (cooldown_hours * 3600)
    
    # Generate new characters if needed
    if needs_reset or not ps_data.get('characters'):
        characters = await generate_ps_characters(user_id, config)
        if not characters:
            await update.message.reply_text("⚠️ Failed to generate store. Please try again later.")
            return
        
        ps_data = {
            'characters': characters,
            'last_reset': datetime.utcnow().isoformat(),
            'refresh_count': 0,
            'last_refresh': None
        }
        await update_user_ps_data(user_id, ps_data)
    
    characters = ps_data.get('characters', [])
    if not characters:
        await update.message.reply_text("⚠️ No characters available in your store.")
        return
    
    # Store data in context
    context.user_data['ps_page'] = 0
    context.user_data['ps_characters'] = characters
    
    # Build first page
    page = 0
    character = characters[page]
    caption, img_url, price = await build_ps_caption(character, config, page + 1, len(characters), ps_data, user_balance)
    
    # Build buttons
    buttons = []
    nav_buttons = []
    
    # Buy button
    char_id = character.get("id", character.get("_id"))
    buttons.append([InlineKeyboardButton("💳 Buy", callback_data=f"ps_buy_{char_id}")])
    
    # Navigation buttons
    if len(characters) > 1:
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ Prev", callback_data=f"ps_page_{page-1}"))
        
        refresh_limit = config.get('refresh_limit', 2)
        refresh_count = ps_data.get('refresh_count', 0)
        
        if refresh_count < refresh_limit:
            nav_buttons.append(InlineKeyboardButton("🔄 Refresh", callback_data="ps_refresh"))
        else:
            nav_buttons.append(InlineKeyboardButton("🔄 Used", callback_data="ps_refresh_limit"))
        
        if page < len(characters) - 1:
            nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"ps_page_{page+1}"))
    else:
        refresh_limit = config.get('refresh_limit', 2)
        refresh_count = ps_data.get('refresh_count', 0)
        
        if refresh_count < refresh_limit:
            nav_buttons.append(InlineKeyboardButton("🔄 Refresh", callback_data="ps_refresh"))
        else:
            nav_buttons.append(InlineKeyboardButton("🔄 Used", callback_data="ps_refresh_limit"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton("🏠 Close", callback_data="ps_close")])
    
    markup = InlineKeyboardMarkup(buttons)
    
    msg = await update.message.reply_photo(
        photo=img_url,
        caption=caption,
        parse_mode="HTML",
        reply_markup=markup
    )
    
    context.user_data['ps_message_id'] = msg.message_id
    context.user_data['ps_chat_id'] = update.effective_chat.id

async def ps_callback(update: Update, context: CallbackContext):
    """Handle private store callbacks"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    config = await get_ps_config()
    
    async def render_ps_page(page):
        """Render a specific page of private store"""
        characters = context.user_data.get('ps_characters', [])
        if not characters or page >= len(characters):
            await query.answer("⚠️ Invalid page.", show_alert=True)
            return
        
        context.user_data['ps_page'] = page
        character = characters[page]
        
        user = await user_collection.find_one({"id": user_id})
        user_balance = user.get('balance', 0) if user else 0
        ps_data = await get_user_ps_data(user_id)
        
        caption, img_url, price = await build_ps_caption(character, config, page + 1, len(characters), ps_data, user_balance)
        
        # Build buttons
        buttons = []
        nav_buttons = []
        
        char_id = character.get("id", character.get("_id"))
        buttons.append([InlineKeyboardButton("💳 Buy", callback_data=f"ps_buy_{char_id}")])
        
        if len(characters) > 1:
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("◀️ Prev", callback_data=f"ps_page_{page-1}"))
            
            refresh_limit = config.get('refresh_limit', 2)
            refresh_count = ps_data.get('refresh_count', 0)
            
            if refresh_count < refresh_limit:
                nav_buttons.append(InlineKeyboardButton("🔄 Refresh", callback_data="ps_refresh"))
            else:
                nav_buttons.append(InlineKeyboardButton("🔄 Used", callback_data="ps_refresh_limit"))
            
            if page < len(characters) - 1:
                nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"ps_page_{page+1}"))
        else:
            refresh_limit = config.get('refresh_limit', 2)
            refresh_count = ps_data.get('refresh_count', 0)
            
            if refresh_count < refresh_limit:
                nav_buttons.append(InlineKeyboardButton("🔄 Refresh", callback_data="ps_refresh"))
            else:
                nav_buttons.append(InlineKeyboardButton("🔄 Used", callback_data="ps_refresh_limit"))
        
        if nav_buttons:
            buttons.append(nav_buttons)
        
        buttons.append([InlineKeyboardButton("🏠 Close", callback_data="ps_close")])
        
        markup = InlineKeyboardMarkup(buttons)
        
        try:
            await query.edit_message_media(
                media=InputMediaPhoto(media=img_url, caption=caption, parse_mode="HTML"),
                reply_markup=markup
            )
        except Exception as e:
            try:
                await query.edit_message_caption(
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup
                )
            except:
                pass
    
    if data.startswith("ps_page_"):
        page = int(data.split("_")[2])
        await render_ps_page(page)
    
    elif data == "ps_refresh":
        user = await user_collection.find_one({"id": user_id})
        if not user:
            await query.answer("⚠️ User not found.", show_alert=True)
            return
        
        ps_data = await get_user_ps_data(user_id)
        refresh_limit = config.get('refresh_limit', 2)
        refresh_count = ps_data.get('refresh_count', 0)
        
        if refresh_count >= refresh_limit:
            await query.answer("⚠️ You've used all your refreshes!", show_alert=True)
            return
        
        refresh_cost = config.get('refresh_cost', 20000)
        user_balance = user.get('balance', 0)
        
        if user_balance < refresh_cost:
            await query.answer(f"⚠️ You need {refresh_cost} Gold to refresh!", show_alert=True)
            return
        
        # Show confirmation
        buttons = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data="ps_refresh_confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="ps_refresh_cancel")
            ]
        ]
        markup = InlineKeyboardMarkup(buttons)
        
        await query.edit_message_caption(
            caption=f"╭─━━━━━━━━━━━━━━━━━─╮\n"
                    f"│  🔄 CONFIRM REFRESH  │\n"
                    f"╰─━━━━━━━━━━━━━━━━━─╯\n\n"
                    f"💰 Cost: <b>{refresh_cost}</b> Gold\n"
                    f"💳 Your Balance: <b>{user_balance}</b> Gold\n\n"
                    f"This will generate 3 new random characters.\n"
                    f"🌀 Refreshes left: {refresh_limit - refresh_count - 1}/{refresh_limit} (after this)\n\n"
                    f"Are you sure?",
            parse_mode="HTML",
            reply_markup=markup
        )
    
    elif data == "ps_refresh_confirm":
        user = await user_collection.find_one({"id": user_id})
        if not user:
            await query.answer("⚠️ User not found.", show_alert=True)
            return
        
        ps_data = await get_user_ps_data(user_id)
        refresh_cost = config.get('refresh_cost', 20000)
        user_balance = user.get('balance', 0)
        
        if user_balance < refresh_cost:
            await query.answer("⚠️ Insufficient balance!", show_alert=True)
            return
        
        # Deduct cost and generate new characters
        await user_collection.update_one(
            {"id": user_id},
            {"$inc": {"balance": -refresh_cost}}
        )
        
        characters = await generate_ps_characters(user_id, config)
        if not characters:
            await query.answer("⚠️ Failed to generate characters.", show_alert=True)
            return
        
        ps_data['characters'] = characters
        ps_data['refresh_count'] = ps_data.get('refresh_count', 0) + 1
        ps_data['last_refresh'] = datetime.utcnow().isoformat()
        await update_user_ps_data(user_id, ps_data)
        
        context.user_data['ps_characters'] = characters
        context.user_data['ps_page'] = 0
        
        await query.answer("✨ Store refreshed!", show_alert=False)
        await render_ps_page(0)
    
    elif data == "ps_refresh_cancel":
        page = context.user_data.get('ps_page', 0)
        await render_ps_page(page)
        await query.answer("Refresh cancelled.", show_alert=False)
    
    elif data == "ps_refresh_limit":
        await query.answer("⚠️ You've used all your refreshes for today!", show_alert=True)
    
    elif data.startswith("ps_buy_"):
        char_id = data.split("_", 2)[2]
        characters = context.user_data.get('ps_characters', [])
        
        character = None
        for char in characters:
            if char.get("id") == char_id or char.get("_id") == char_id:
                character = char
                break
        
        if not character:
            await query.answer("⚠️ Character not found.", show_alert=True)
            return
        
        rarity = character.get('rarity', 'Unknown')
        price = config['rarities'].get(rarity, {}).get('price', 0)
        
        buttons = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"ps_confirm_{char_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data="ps_buy_cancel")
            ]
        ]
        markup = InlineKeyboardMarkup(buttons)
        
        await query.edit_message_caption(
            caption=f"╭─━━━━━━━━━━━━━━━─╮\n"
                    f"│  💳 CONFIRM PURCHASE  │\n"
                    f"╰─━━━━━━━━━━━━━━━─╯\n\n"
                    f"✨ <b>{character['name']}</b>\n"
                    f"💫 Rarity: {rarity}\n"
                    f"💎 Price: <b>{price}</b> Gold\n\n"
                    f"Are you sure you want to buy this character?",
            parse_mode="HTML",
            reply_markup=markup
        )
    
    elif data.startswith("ps_confirm_"):
        char_id = data.split("_", 2)[2]
        characters = context.user_data.get('ps_characters', [])
        
        character = None
        for char in characters:
            if char.get("id") == char_id or char.get("_id") == char_id:
                character = char
                break
        
        if not character:
            await query.answer("⚠️ Character not found.", show_alert=True)
            return
        
        user = await user_collection.find_one({"id": user_id})
        if not user:
            await query.answer("⚠️ User not found.", show_alert=True)
            return
        
        rarity = character.get('rarity', 'Unknown')
        price = config['rarities'].get(rarity, {}).get('price', 0)
        user_balance = user.get('balance', 0)
        
        if user_balance < price:
            await query.answer("⚠️ Not enough Gold!", show_alert=True)
            await query.edit_message_caption(
                caption=f"╭─━━━━━━━━━━━━━━━━━─╮\n"
                        f"│  ⚠️ INSUFFICIENT BALANCE │\n"
                        f"╰─━━━━━━━━━━━━━━━━━─╯\n\n"
                        f"You need <b>{price}</b> Gold but only have <b>{user_balance}</b> Gold.\n"
                        f"Use /bal to check your balance.",
                parse_mode="HTML"
            )
            return
        
        # Check if already owned
        user_chars = user.get("characters", [])
        if any((c.get("id") == char_id or c.get("_id") == char_id) for c in user_chars):
            await query.answer("⚠️ You already own this character!", show_alert=True)
            return
        
        # Purchase character
        await user_collection.update_one(
            {"id": user_id},
            {
                "$inc": {"balance": -price},
                "$push": {"characters": character}
            }
        )
        
        await query.edit_message_caption(
            caption=f"╭─━━━━━━━━━━━━━━━━─╮\n"
                    f"│  ✨ PURCHASE SUCCESS! │\n"
                    f"╰─━━━━━━━━━━━━━━━━─╯\n\n"
                    f"You bought <b>{character['name']}</b> for <b>{price}</b> Gold!\n"
                    f"The character has been added to your harem.\n\n"
                    f"💰 Remaining Balance: <b>{user_balance - price}</b> Gold",
            parse_mode="HTML"
        )
        await query.answer("✨ Purchase successful!", show_alert=False)
    
    elif data == "ps_buy_cancel":
        page = context.user_data.get('ps_page', 0)
        await render_ps_page(page)
        await query.answer("Purchase cancelled.", show_alert=False)
    
    elif data == "ps_close":
        try:
            await query.message.delete()
        except:
            await query.edit_message_caption("Store closed.")
        await query.answer("Store closed.", show_alert=False)

# Admin commands for configuration
async def ps_set_rarity(update: Update, context: CallbackContext):
    """Set rarity weight and price - /psrarity <rarity> <weight> <price>"""
    user_id = update.effective_user.id
    
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ You don't have permission to use this command.")
        return
    
    if len(context.args) < 3:
        rarity_list = "\n".join([f"• {k}" for k in HAREM_MODE_MAPPING.values() if k])
        await update.message.reply_text(
            f"⚠️ Usage: /psrarity <rarity> <weight> <price>\n\n"
            f"Available rarities:\n{rarity_list}",
            parse_mode="HTML"
        )
        return
    
    try:
        rarity = " ".join(context.args[:-2])
        weight = int(context.args[-2])
        price = int(context.args[-1])
        
        if weight < 0 or price < 0:
            await update.message.reply_text("⚠️ Weight and price must be positive numbers.")
            return
        
        config = await get_ps_config()
        
        if rarity not in config['rarities']:
            config['rarities'][rarity] = {}
        
        config['rarities'][rarity]['weight'] = weight
        config['rarities'][rarity]['price'] = price
        
        await ps_config_collection.update_one(
            {"_id": "ps_config"},
            {"$set": config},
            upsert=True
        )
        
        await update.message.reply_text(
            f"✅ Updated <b>{rarity}</b>\n"
            f"Weight: {weight}%\n"
            f"Price: {price} Gold",
            parse_mode="HTML"
        )
    
    except ValueError:
        await update.message.reply_text("⚠️ Invalid weight or price. Please provide numbers.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

async def ps_set_config(update: Update, context: CallbackContext):
    """Set PS configuration - /psconfig <refresh_cost|refresh_limit|store_items|cooldown_hours> <value>"""
    user_id = update.effective_user.id
    
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ You don't have permission to use this command.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ Usage: /psconfig <setting> <value>\n\n"
            "Available settings:\n"
            "• refresh_cost - Cost to refresh store\n"
            "• refresh_limit - Max refreshes per cooldown\n"
            "• store_items - Number of items in store\n"
            "• cooldown_hours - Hours until store resets",
            parse_mode="HTML"
        )
        return
    
    try:
        setting = context.args[0]
        value = int(context.args[1])
        
        valid_settings = ['refresh_cost', 'refresh_limit', 'store_items', 'cooldown_hours']
        
        if setting not in valid_settings:
            await update.message.reply_text(f"⚠️ Invalid setting. Choose from: {', '.join(valid_settings)}")
            return
        
        if value < 0:
            await update.message.reply_text("⚠️ Value must be positive.")
            return
        
        config = await get_ps_config()
        config[setting] = value
        
        await ps_config_collection.update_one(
            {"_id": "ps_config"},
            {"$set": config},
            upsert=True
        )
        
        await update.message.reply_text(
            f"✅ Updated configuration\n"
            f"<b>{setting}</b>: {value}",
            parse_mode="HTML"
        )
    
    except ValueError:
        await update.message.reply_text("⚠️ Invalid value. Please provide a number.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

async def ps_view_config(update: Update, context: CallbackContext):
    """View current PS configuration - /psview"""
    user_id = update.effective_user.id
    
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ You don't have permission to use this command.")
        return
    
    try:
        config = await get_ps_config()
        
        rarities_text = ""
        for rarity, data in config['rarities'].items():
            rarities_text += f"• {rarity}\n  Weight: {data['weight']}% | Price: {data['price']} Gold\n"
        
        message = (
            f"╭─━━━━━━━━━━━━━━━━━━━━━─╮\n"
            f"│  ⚙️ 𝗣𝗥𝗜𝗩𝗔𝗧𝗘 𝗦𝗧𝗢𝗥𝗘 𝗖𝗢𝗡𝗙𝗜𝗚  │\n"
            f"╰─━━━━━━━━━━━━━━━━━━━━━─╯\n\n"
            f"<b>General Settings:</b>\n"
            f"💰 Refresh Cost: {config.get('refresh_cost', 20000)} Gold\n"
            f"🔄 Refresh Limit: {config.get('refresh_limit', 2)}\n"
            f"🎁 Store Items: {config.get('store_items', 3)}\n"
            f"⏰ Cooldown: {config.get('cooldown_hours', 24)} hours\n\n"
            f"<b>Rarity Configuration:</b>\n"
            f"{rarities_text}\n"
            f"Use /psrarity to modify rarities\n"
            f"Use /psconfig to modify settings"
        )
        
        await update.message.reply_text(message, parse_mode="HTML")
    
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

async def ps_reset_user(update: Update, context: CallbackContext):
    """Reset a user's private store - /psreset <user_id>"""
    user_id = update.effective_user.id
    
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ You don't have permission to use this command.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("⚠️ Usage: /psreset <user_id>")
        return
    
    try:
        target_user_id = int(context.args[0])
        
        user = await user_collection.find_one({"id": target_user_id})
        if not user:
            await update.message.reply_text("⚠️ User not found.")
            return
        
        # Reset private store data
        ps_data = {
            'characters': [],
            'last_reset': None,
            'refresh_count': 0,
            'last_refresh': None
        }
        
        await update_user_ps_data(target_user_id, ps_data)
        
        await update.message.reply_text(
            f"✅ Reset private store for user {target_user_id}\n"
            f"They will get new characters on next /ps use.",
            parse_mode="HTML"
        )
    
    except ValueError:
        await update.message.reply_text("⚠️ Invalid user ID.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

async def ps_add_rarity(update: Update, context: CallbackContext):
    """Add a new rarity to PS - /psaddrarity <rarity_name> <weight> <price>"""
    user_id = update.effective_user.id
    
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ You don't have permission to use this command.")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text("⚠️ Usage: /psaddrarity <rarity_name> <weight> <price>")
        return
    
    try:
        rarity = " ".join(context.args[:-2])
        weight = int(context.args[-2])
        price = int(context.args[-1])
        
        if weight < 0 or price < 0:
            await update.message.reply_text("⚠️ Weight and price must be positive numbers.")
            return
        
        config = await get_ps_config()
        
        if rarity in config['rarities']:
            await update.message.reply_text(f"⚠️ Rarity <b>{rarity}</b> already exists. Use /psrarity to modify it.", parse_mode="HTML")
            return
        
        config['rarities'][rarity] = {
            'weight': weight,
            'price': price
        }
        
        await ps_config_collection.update_one(
            {"_id": "ps_config"},
            {"$set": config},
            upsert=True
        )
        
        await update.message.reply_text(
            f"✅ Added new rarity <b>{rarity}</b>\n"
            f"Weight: {weight}%\n"
            f"Price: {price} Gold",
            parse_mode="HTML"
        )
    
    except ValueError:
        await update.message.reply_text("⚠️ Invalid weight or price. Please provide numbers.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

async def ps_remove_rarity(update: Update, context: CallbackContext):
    """Remove a rarity from PS - /psrmrarity <rarity_name>"""
    user_id = update.effective_user.id
    
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ You don't have permission to use this command.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("⚠️ Usage: /psrmrarity <rarity_name>")
        return
    
    try:
        rarity = " ".join(context.args)
        config = await get_ps_config()
        
        if rarity not in config['rarities']:
            await update.message.reply_text(f"⚠️ Rarity <b>{rarity}</b> not found.", parse_mode="HTML")
            return
        
        del config['rarities'][rarity]
        
        await ps_config_collection.update_one(
            {"_id": "ps_config"},
            {"$set": config},
            upsert=True
        )
        
        await update.message.reply_text(
            f"✅ Removed rarity <b>{rarity}</b> from configuration.",
            parse_mode="HTML"
        )
    
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

async def ps_stats(update: Update, context: CallbackContext):
    """View PS statistics - /psstats"""
    user_id = update.effective_user.id
    
    try:
        user = await user_collection.find_one({"id": user_id})
        if not user:
            await update.message.reply_text("⚠️ User not found. Use /start first.")
            return
        
        ps_data = await get_user_ps_data(user_id)
        config = await get_ps_config()
        
        refresh_limit = config.get('refresh_limit', 2)
        refresh_count = ps_data.get('refresh_count', 0)
        refreshes_left = max(0, refresh_limit - refresh_count)
        
        last_reset = ps_data.get('last_reset')
        cooldown_hours = config.get('cooldown_hours', 24)
        
        if last_reset:
            if isinstance(last_reset, str):
                last_reset = datetime.fromisoformat(last_reset)
            next_reset = last_reset + timedelta(hours=cooldown_hours)
            time_remaining = get_time_remaining(next_reset)
        else:
            time_remaining = "Available now"
        
        characters = ps_data.get('characters', [])
        char_count = len(characters)
        
        message = (
            f"╭─━━━━━━━━━━━━━━━━━━━─╮\n"
            f"│  📊 𝗬𝗢𝗨𝗥 𝗣𝗦 𝗦𝗧𝗔𝗧𝗦  │\n"
            f"╰─━━━━━━━━━━━━━━━━━━━─╯\n\n"
            f"🎁 𝗖𝗵𝗮𝗿𝗮𝗰𝘁𝗲𝗿𝘀 𝗔𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲: {char_count}\n"
            f"🌀 𝗥𝗲𝗳𝗿𝗲𝘀𝗵𝗲𝘀 𝗟𝗲𝗳𝘁: {refreshes_left}/{refresh_limit}\n"
            f"⏰ 𝗡𝗲𝘅𝘁 𝗥𝗲𝘀𝗲𝘁: {time_remaining}\n\n"
            f"💰 𝗥𝗲𝗳𝗿𝗲𝘀𝗵 𝗖𝗼𝘀𝘁: {config.get('refresh_cost', 20000)} Gold\n"
            f"💳 𝗬𝗼𝘂𝗿 𝗕𝗮𝗹𝗮𝗻𝗰𝗲: {user.get('balance', 0)} Gold\n\n"
            f"Use /ps to open your private store!"
        )
        
        await update.message.reply_text(message, parse_mode="HTML")
    
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

async def ps_help(update: Update, context: CallbackContext):
    """Show PS help - /pshelp"""
    user_message = (
        f"╭─━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
        f"│  🎁 𝗣𝗥𝗜𝗩𝗔𝗧𝗘 𝗦𝗧𝗢𝗥𝗘 𝗛𝗘𝗟𝗣  │\n"
        f"╰─━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"<b>User Commands:</b>\n"
        f"• /ps - Open your private store\n"
        f"• /psstats - View your PS statistics\n"
        f"• /pshelp - Show this help message\n\n"
        f"<b>How it works:</b>\n"
        f"🎁 Get 3 random characters every 24 hours\n"
        f"🔄 Refresh up to 2 times (costs Gold)\n"
        f"💳 Buy characters with Gold\n"
        f"⏰ Store resets automatically after cooldown\n\n"
        f"<b>Character Prices:</b>\n"
        f"Prices vary by rarity - check each character!"
    )
    
    user_id = update.effective_user.id
    if await is_sudo_user(user_id):
        admin_message = (
            f"\n\n<b>Admin Commands:</b>\n"
            f"• /psview - View current configuration\n"
            f"• /psconfig <setting> <value> - Update settings\n"
            f"• /psrarity <rarity> <weight> <price> - Update rarity\n"
            f"• /psaddrarity <rarity> <weight> <price> - Add new rarity\n"
            f"• /psrmrarity <rarity> - Remove rarity\n"
            f"• /psreset <user_id> - Reset user's store\n\n"
            f"<b>Settings:</b>\n"
            f"• refresh_cost - Cost to refresh\n"
            f"• refresh_limit - Max refreshes\n"
            f"• store_items - Number of items\n"
            f"• cooldown_hours - Reset time"
        )
        user_message += admin_message
    
    await update.message.reply_text(user_message, parse_mode="HTML")

# Register handlers
application.add_handler(CommandHandler("ps", ps, block=False))
application.add_handler(CommandHandler("psstats", ps_stats, block=False))
application.add_handler(CommandHandler("pshelp", ps_help, block=False))
application.add_handler(CommandHandler("psview", ps_view_config, block=False))
application.add_handler(CommandHandler("psconfig", ps_set_config, block=False))
application.add_handler(CommandHandler("psrarity", ps_set_rarity, block=False))
application.add_handler(CommandHandler("psaddrarity", ps_add_rarity, block=False))
application.add_handler(CommandHandler("psrmrarity", ps_remove_rarity, block=False))
application.add_handler(CommandHandler("psreset", ps_reset_user, block=False))
application.add_handler(CallbackQueryHandler(ps_callback, pattern=r"^ps_", block=False))