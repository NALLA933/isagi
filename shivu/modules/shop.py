import random
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler

from shivu import application, db, user_collection, CHARA_CHANNEL_ID, SUPPORT_CHAT

# Database collections
collection = db['anime_characters_lol']  # Main character collection
shop_collection = db['shop']  # Shop collection

# Character collection
characters_collection = collection

# Sudo users list
sudo_users = ["8297659126", "8420981179", "5147822244"]

# Items per page
ITEMS_PER_PAGE = 1

async def is_sudo_user(user_id: int) -> bool:
    """Check if user is sudo user"""
    return str(user_id) in sudo_users

async def addshop(update: Update, context: CallbackContext):
    """Add character to shop - Sudo only"""
    user_id = update.effective_user.id
    
    if not await is_sudo_user(user_id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Usage: /addshop <character_id> <price>")
        return
    
    try:
        char_id = context.args[0]
        price = int(context.args[1])
        
        if price <= 0:
            await update.message.reply_text("❌ Price must be greater than 0.")
            return
        
        # Check if character exists
        character = await characters_collection.find_one({"id": char_id})
        if not character:
            await update.message.reply_text(f"❌ Character with ID {char_id} not found in database.")
            return
        
        # Check if already in shop
        existing = await shop_collection.find_one({"id": char_id})
        if existing:
            await update.message.reply_text(f"❌ Character {character['name']} is already in the shop.")
            return
        
        # Add to shop with price
        shop_item = {
            "id": char_id,
            "price": price,
            "added_by": user_id,
            "added_at": datetime.utcnow()
        }
        
        await shop_collection.insert_one(shop_item)
        await update.message.reply_text(
            f"✅ Successfully added <b>{character['name']}</b> to shop!\n"
            f"💰 Price: {price} Gold",
            parse_mode="HTML"
        )
    
    except ValueError:
        await update.message.reply_text("❌ Invalid price. Please provide a valid number.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def rmshop(update: Update, context: CallbackContext):
    """Remove character from shop - Sudo only"""
    user_id = update.effective_user.id
    
    if not await is_sudo_user(user_id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("❌ Usage: /rmshop <character_id>")
        return
    
    try:
        char_id = context.args[0]
        
        # Check if in shop
        shop_item = await shop_collection.find_one({"id": char_id})
        if not shop_item:
            await update.message.reply_text(f"❌ Character with ID {char_id} is not in the shop.")
            return
        
        # Get character details
        character = await characters_collection.find_one({"id": char_id})
        char_name = character['name'] if character else char_id
        
        # Remove from shop
        await shop_collection.delete_one({"id": char_id})
        await update.message.reply_text(f"✅ Successfully removed <b>{char_name}</b> from shop!", parse_mode="HTML")
    
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

def build_caption(waifu: dict, shop_item: dict, page: int, total: int) -> str:
    """Create HTML caption for the waifu"""
    wid = waifu.get("id", waifu.get("_id"))
    name = waifu.get("name", "Unknown")
    anime = waifu.get("anime", "Unknown")
    rarity = waifu.get("rarity", "Unknown")
    price = shop_item.get("price", 0)
    img_url = waifu.get("img_url", "")

    caption = (
        f"<b>🏪 Character Shop</b>\n\n"
        f"<b>{name}</b>\n"
        f"🎌 <b>Anime:</b> {anime}\n"
        f"💠 <b>Rarity:</b> {rarity}\n"
        f"🆔 <b>ID:</b> <code>{wid}</code>\n"
        f"💰 <b>Price:</b> {price} Gold\n\n"
        f"📄 Page {page}/{total}\n\n"
        "Tap <b>Buy</b> to purchase. Use /bal to check your balance."
    )
    return caption, img_url

async def store(update: Update, context: CallbackContext):
    """Show waifus in the store with pagination"""
    user_id = update.effective_user.id
    
    # Get all shop items
    shop_items = await shop_collection.find({}).to_list(length=None)
    
    if not shop_items:
        await update.message.reply_text("🏪 The shop is currently empty. Check back later!")
        return
    
    # Start at page 0
    page = 0
    total_pages = len(shop_items)
    
    # Store in context for pagination
    context.user_data['shop_items'] = [item['id'] for item in shop_items]
    context.user_data['shop_page'] = page
    
    # Get first character
    char_id = shop_items[page]['id']
    character = await characters_collection.find_one({"id": char_id})
    
    if not character:
        await update.message.reply_text("❌ Error loading shop character.")
        return
    
    caption, img_url = build_caption(character, shop_items[page], page + 1, total_pages)
    
    # Build keyboard
    buttons = []
    nav_buttons = []
    
    if total_pages > 1:
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ Prev", callback_data=f"shop_page_{page-1}"))
        nav_buttons.append(InlineKeyboardButton("🔄 Refresh", callback_data="shop_refresh"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"shop_page_{page+1}"))
    else:
        nav_buttons.append(InlineKeyboardButton("🔄 Refresh", callback_data="shop_refresh"))
    
    buttons.append([InlineKeyboardButton("💳 Buy", callback_data=f"shop_buy_{char_id}")])
    if nav_buttons:
        buttons.append(nav_buttons)
    
    markup = InlineKeyboardMarkup(buttons)
    
    msg = await update.message.reply_photo(
        photo=img_url,
        caption=caption,
        parse_mode="HTML",
        reply_markup=markup
    )
    
    # Store message ID for editing
    context.user_data['shop_message_id'] = msg.message_id

async def shop_callback(update: Update, context: CallbackContext):
    """Handle all shop callbacks"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    # Handle pagination
    if data.startswith("shop_page_"):
        page = int(data.split("_")[2])
        shop_items_ids = context.user_data.get('shop_items', [])
        
        if not shop_items_ids or page >= len(shop_items_ids):
            await query.answer("❌ Invalid page.", show_alert=True)
            return
        
        context.user_data['shop_page'] = page
        char_id = shop_items_ids[page]
        
        # Get character and shop item
        character = await characters_collection.find_one({"id": char_id})
        shop_item = await shop_collection.find_one({"id": char_id})
        
        if not character or not shop_item:
            await query.answer("❌ Character not found.", show_alert=True)
            return
        
        caption, img_url = build_caption(character, shop_item, page + 1, len(shop_items_ids))
        
        # Build keyboard
        buttons = []
        nav_buttons = []
        
        if len(shop_items_ids) > 1:
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("◀️ Prev", callback_data=f"shop_page_{page-1}"))
            nav_buttons.append(InlineKeyboardButton("🔄 Refresh", callback_data="shop_refresh"))
            if page < len(shop_items_ids) - 1:
                nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"shop_page_{page+1}"))
        else:
            nav_buttons.append(InlineKeyboardButton("🔄 Refresh", callback_data="shop_refresh"))
        
        buttons.append([InlineKeyboardButton("💳 Buy", callback_data=f"shop_buy_{char_id}")])
        if nav_buttons:
            buttons.append(nav_buttons)
        
        markup = InlineKeyboardMarkup(buttons)
        
        try:
            await query.edit_message_media(
                media=query.message.photo[0].file_id if query.message.photo else img_url,
                reply_markup=markup
            )
            await query.edit_message_caption(
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        except:
            await query.message.reply_photo(
                photo=img_url,
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
    
    # Handle refresh
    elif data == "shop_refresh":
        shop_items = await shop_collection.find({}).to_list(length=None)
        
        if not shop_items:
            await query.edit_message_caption("🏪 The shop is currently empty. Check back later!")
            return
        
        # Reset to first page
        page = 0
        context.user_data['shop_items'] = [item['id'] for item in shop_items]
        context.user_data['shop_page'] = page
        
        char_id = shop_items[page]['id']
        character = await characters_collection.find_one({"id": char_id})
        
        if not character:
            await query.answer("❌ Error loading shop.", show_alert=True)
            return
        
        caption, img_url = build_caption(character, shop_items[page], page + 1, len(shop_items))
        
        # Build keyboard
        buttons = []
        nav_buttons = []
        
        if len(shop_items) > 1:
            nav_buttons.append(InlineKeyboardButton("🔄 Refresh", callback_data="shop_refresh"))
            nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"shop_page_{page+1}"))
        else:
            nav_buttons.append(InlineKeyboardButton("🔄 Refresh", callback_data="shop_refresh"))
        
        buttons.append([InlineKeyboardButton("💳 Buy", callback_data=f"shop_buy_{char_id}")])
        if nav_buttons:
            buttons.append(nav_buttons)
        
        markup = InlineKeyboardMarkup(buttons)
        
        await query.edit_message_caption(
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup
        )
    
    elif data.startswith("shop_confirm_"):
        char_id = data.split("_", 2)[2]
        
        if await has_purchased(user_id, char_id):
            await query.answer(
                "⚠️ 𝐘𝐨𝐮 𝐡𝐚𝐯𝐞 𝐚𝐥𝐫𝐞𝐚𝐝𝐲 𝐩𝐮𝐫𝐜𝐡𝐚𝐬𝐞𝐝 𝐭𝐡𝐢𝐬 𝐜𝐡𝐚𝐫𝐚𝐜𝐭𝐞𝐫 𝐟𝐫𝐨𝐦 𝐭𝐡𝐞 𝐬𝐡𝐨𝐩!",
                show_alert=True
            )
            return
        
        shop_item = await shop_collection.find_one({"id": char_id})
        if not shop_item:
            await query.answer("⚠️ 𝐓𝐡𝐢𝐬 𝐢𝐭𝐞𝐦 𝐢𝐬 𝐧𝐨 𝐥𝐨𝐧𝐠𝐞𝐫 𝐚𝐯𝐚𝐢𝐥𝐚𝐛𝐥𝐞.", show_alert=True)
            return
        
        limit = shop_item.get("limit", 0)
        if limit > 0:
            purchase_count = await get_purchase_count(char_id)
            if purchase_count >= limit:
                await query.answer("⚠️ 𝐓𝐡𝐢𝐬 𝐢𝐭𝐞𝐦 𝐢𝐬 𝐨𝐮𝐭 𝐨𝐟 𝐬𝐭𝐨𝐜𝐤!", show_alert=True)
                return
        
        character = await characters_collection.find_one({"id": char_id})
        if not character:
            await query.answer("⚠️ 𝐂𝐡𝐚𝐫𝐚𝐜𝐭𝐞𝐫 𝐧𝐨𝐭 𝐟𝐨𝐮𝐧𝐝.", show_alert=True)
            return
        
        price = shop_item.get("price", 0)
        
        user_data = await user_collection.find_one({"id": user_id})
        balance = user_data.get("balance", 0) if user_data else 0
        
        if balance < price:
            await query.answer("⚠️ 𝐈𝐧𝐬𝐮𝐟𝐟𝐢𝐜𝐢𝐞𝐧𝐭 𝐛𝐚𝐥𝐚𝐧𝐜𝐞!", show_alert=True)
            await query.edit_message_caption(
                caption=f"╔═══════════════════════╗\n"
                        f"║  ⚠️ 𝐈𝐍𝐒𝐔𝐅𝐅𝐈𝐂𝐈𝐄𝐍𝐓 𝐅𝐔𝐍𝐃𝐒  ║\n"
                        f"╚═══════════════════════╝\n\n"
                        f"💔 𝐘𝐨𝐮 𝐝𝐨𝐧'𝐭 𝐡𝐚𝐯𝐞 𝐞𝐧𝐨𝐮𝐠𝐡 𝐆𝐨𝐥𝐝!\n\n"
                        f"💰 𝐑𝐞𝐪𝐮𝐢𝐫𝐞𝐝: <b>{price}</b> 𝐆𝐨𝐥𝐝\n"
                        f"👛 𝐘𝐨𝐮𝐫 𝐁𝐚𝐥𝐚𝐧𝐜𝐞: <b>{balance}</b> 𝐆𝐨𝐥𝐝\n"
                        f"📉 𝐒𝐡𝐨𝐫𝐭: <b>{price - balance}</b> 𝐆𝐨𝐥𝐝\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"💡 𝐔𝐬𝐞 /bal 𝐭𝐨 𝐜𝐡𝐞𝐜𝐤 𝐲𝐨𝐮𝐫 𝐛𝐚𝐥𝐚𝐧𝐜𝐞!",
                parse_mode="HTML"
            )
            return
        
        await user_collection.update_one(
            {"id": user_id},
            {
                "$inc": {"balance": -price},
                "$push": {"characters": character}
            },
            upsert=True
        )
        
        await shop_purchases_collection.insert_one({
            "user_id": user_id,
            "char_id": char_id,
            "price": price,
            "purchased_at": datetime.utcnow()
        })
        
        new_balance = balance - price
        
        await query.edit_message_caption(
            caption=f"╔═══════════════════════╗\n"
                    f"║  🎉 𝐏𝐔𝐑𝐂𝐇𝐀𝐒𝐄 𝐒𝐔𝐂𝐂𝐄𝐒𝐒  ║\n"
                    f"╚═══════════════════════╝\n\n"
                    f"🎊 𝐂𝐨𝐧𝐠𝐫𝐚𝐭𝐮𝐥𝐚𝐭𝐢𝐨𝐧𝐬!\n\n"
                    f"┏━━━━━━━━━━━━━━━━━━━━━┓\n"
                    f"┃  ✨ <b>{character['name']}</b>\n"
                    f"┗━━━━━━━━━━━━━━━━━━━━━┛\n\n"
                    f"💸 𝐏𝐚𝐢𝐝: <b>{price}</b> 𝐆𝐨𝐥𝐝\n"
                    f"💰 𝐑𝐞𝐦𝐚𝐢𝐧𝐢𝐧𝐠: <b>{new_balance}</b> 𝐆𝐨𝐥𝐝\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ 𝐀𝐝𝐝𝐞𝐝 𝐭𝐨 𝐲𝐨𝐮𝐫 𝐡𝐚𝐫𝐞𝐦!\n"
                    f"🎁 𝐄𝐧𝐣𝐨𝐲 𝐲𝐨𝐮𝐫 𝐧𝐞𝐰 𝐜𝐡𝐚𝐫𝐚𝐜𝐭𝐞𝐫!",
            parse_mode="HTML"
        )
        await query.answer("🎉 𝐏𝐮𝐫𝐜𝐡𝐚𝐬𝐞 𝐬𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥!", show_alert=False)
    
    elif data == "shop_cancel":
        page = context.user_data.get('shop_page', 0)
        shop_items_ids = context.user_data.get('shop_items', [])
        
        if not shop_items_ids:
            await query.answer("⚠️ 𝐒𝐞𝐬𝐬𝐢𝐨𝐧 𝐞𝐱𝐩𝐢𝐫𝐞𝐝. 𝐏𝐥𝐞𝐚𝐬𝐞 𝐮𝐬𝐞 /store 𝐚𝐠𝐚𝐢𝐧.", show_alert=True)
            return
        
        char_id = shop_items_ids[page]
        character = await characters_collection.find_one({"id": char_id})
        shop_item = await shop_collection.find_one({"id": char_id})
        
        if not character or not shop_item:
            await query.answer("❌ 𝐄𝐫𝐫𝐨𝐫 𝐥𝐨𝐚𝐝𝐢𝐧𝐠 𝐬𝐡𝐨𝐩.", show_alert=True)
            return
        
        purchase_count = await get_purchase_count(char_id)
        shop_item['purchased'] = purchase_count
        
        caption, img_url = build_caption(character, shop_item, page + 1, len(shop_items_ids))
        
        buttons = []
        nav_buttons = []
        
        if len(shop_items_ids) > 1:
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("⬅️ 𝐏𝐫𝐞𝐯", callback_data=f"shop_page_{page-1}"))
            nav_buttons.append(InlineKeyboardButton("🔄 𝐑𝐞𝐟𝐫𝐞𝐬𝐡", callback_data="shop_refresh"))
            if page < len(shop_items_ids) - 1:
                nav_buttons.append(InlineKeyboardButton("𝐍𝐞𝐱𝐭 ➡️", callback_data=f"shop_page_{page+1}"))
        else:
            nav_buttons.append(InlineKeyboardButton("🔄 𝐑𝐞𝐟𝐫𝐞𝐬𝐡", callback_data="shop_refresh"))
        
        buttons.append([InlineKeyboardButton("🛒 𝐁𝐮𝐲 𝐍𝐨𝐰", callback_data=f"shop_buy_{char_id}")])
        if nav_buttons:
            buttons.append(nav_buttons)
        
        markup = InlineKeyboardMarkup(buttons)
        
        try:
            await query.edit_message_media(
                media=InputMediaPhoto(media=img_url, caption=caption, parse_mode="HTML"),
                reply_markup=markup
            )
        except:
            await query.edit_message_caption(
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        await query.answer("🚫 𝐏𝐮𝐫𝐜𝐡𝐚𝐬𝐞 𝐜𝐚𝐧𝐜𝐞𝐥𝐥𝐞𝐝.", show_alert=False)

application.add_handler(CommandHandler("store", store, block=False))
application.add_handler(CommandHandler("addshop", addshop, block=False))
application.add_handler(CommandHandler("rmshop", rmshop, block=False))
application.add_handler(CallbackQueryHandler(shop_callback, pattern=r"^shop_", block=False))