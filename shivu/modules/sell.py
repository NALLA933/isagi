from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest
from datetime import datetime
from bson import ObjectId
from shivu import application, db, user_collection

# Database collections
collection = db['anime_characters_lol']
sell_listings = db['sell_listings']
sell_history = db['sell_history']

# ============================================
# SELL COMMAND - List character for sale
# ============================================
async def sell(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b> /sell &lt;character_id&gt; &lt;price&gt;\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b> /sell 12345 5000",
            parse_mode="HTML"
        )
        return
    
    try:
        char_id = context.args[0]
        price = int(context.args[1])
        
        if price <= 0:
            await update.message.reply_text("⚠️ ᴘʀɪᴄᴇ ᴍᴜsᴛ ʙᴇ ɢʀᴇᴀᴛᴇʀ ᴛʜᴀɴ 0")
            return
        
        # Get user data
        user_data = await user_collection.find_one({"id": user_id})
        if not user_data:
            await update.message.reply_text("⚠️ ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ғᴏᴜɴᴅ")
            return
        
        # Find character in user's collection
        user_chars = user_data.get("characters", [])
        char_to_sell = None
        
        for c in user_chars:
            if str(c.get("id", c.get("_id"))) == char_id:
                char_to_sell = c
                break
        
        if not char_to_sell:
            await update.message.reply_text(
                f"⚠️ ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴄʜᴀʀᴀᴄᴛᴇʀ <code>{char_id}</code>", 
                parse_mode="HTML"
            )
            return
        
        # Check if already listed
        existing = await sell_listings.find_one({
            "seller_id": user_id, 
            "character.id": char_to_sell.get("id", char_to_sell.get("_id"))
        })
        if existing:
            await update.message.reply_text(
                "⚠️ <b>ᴀʟʀᴇᴀᴅʏ ʟɪsᴛᴇᴅ!</b>\n\nᴜsᴇ /unsell ᴛᴏ ʀᴇᴍᴏᴠᴇ ɪᴛ ғɪʀsᴛ", 
                parse_mode="HTML"
            )
            return
        
        # Create listing
        listing = {
            "seller_id": user_id,
            "character": char_to_sell,
            "price": price,
            "listed_at": datetime.utcnow(),
            "views": 0
        }
        
        # Add to marketplace and remove from user
        await sell_listings.insert_one(listing)
        await user_collection.update_one(
            {"id": user_id}, 
            {"$pull": {"characters": char_to_sell}}
        )
        
        name = char_to_sell.get("name", "Unknown")
        anime = char_to_sell.get("anime", "Unknown")
        rarity = char_to_sell.get("rarity", "Unknown")
        
        await update.message.reply_text(
            f"<b>✨ ʟɪsᴛᴇᴅ ғᴏʀ sᴀʟᴇ!</b>\n\n"
            f"🎭 <b>{name}</b>\n"
            f"📺 {anime}\n"
            f"💫 {rarity}\n"
            f"💰 <b>{price:,}</b> ɢᴏʟᴅ\n\n"
            f"ᴜsᴇ /market ᴛᴏ ᴠɪᴇᴡ ʏᴏᴜʀ ʟɪsᴛɪɴɢ",
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ғᴏʀᴍᴀᴛ")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

# ============================================
# UNSELL COMMAND - Remove listing
# ============================================
async def unsell(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b> /unsell &lt;character_id&gt;\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b> /unsell 12345",
            parse_mode="HTML"
        )
        return
    
    try:
        char_id = context.args[0]
        listing = await sell_listings.find_one({
            "seller_id": user_id, 
            "character.id": char_id
        })
        
        if not listing:
            await update.message.reply_text(
                f"⚠️ ɴᴏ ʟɪsᴛɪɴɢ ғᴏᴜɴᴅ ғᴏʀ <code>{char_id}</code>", 
                parse_mode="HTML"
            )
            return
        
        # Return character to user
        character = listing["character"]
        await user_collection.update_one(
            {"id": user_id}, 
            {"$push": {"characters": character}}, 
            upsert=True
        )
        await sell_listings.delete_one({"_id": listing["_id"]})
        
        name = character.get("name", "Unknown")
        await update.message.reply_text(
            f"<b>🔙 ʀᴇᴍᴏᴠᴇᴅ ғʀᴏᴍ ᴍᴀʀᴋᴇᴛ</b>\n\n"
            f"✨ <b>{name}</b> ʀᴇᴛᴜʀɴᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

# ============================================
# MARKET COMMAND - Browse marketplace
# ============================================
async def market(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    filter_query = {}
    sort_by = [("listed_at", -1)]
    
    # Handle filters
    if context.args:
        arg = context.args[0].lower()
        if arg == "mine":
            filter_query["seller_id"] = user_id
        elif arg == "cheap":
            sort_by = [("price", 1)]
        elif arg == "expensive":
            sort_by = [("price", -1)]
    
    # Get listings
    listings = await sell_listings.find(filter_query).sort(sort_by).to_list(length=None)
    
    if not listings:
        buttons = [[InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="mr")]]
        markup = InlineKeyboardMarkup(buttons)
        
        await update.message.reply_text(
            "<b>🏪 ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ ᴇᴍᴘᴛʏ</b>\n\n"
            "😔 ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴀᴠᴀɪʟᴀʙʟᴇ\n\n"
            "💡 <b>ᴛɪᴘs:</b>\n"
            "• ᴜsᴇ /sell ᴛᴏ ʟɪsᴛ ʏᴏᴜʀ ᴄʜᴀʀᴀᴄᴛᴇʀs\n"
            "• /market mine - ʏᴏᴜʀ ʟɪsᴛɪɴɢs\n"
            "• /market cheap - ʙᴇsᴛ ᴅᴇᴀʟs",
            parse_mode="HTML",
            reply_markup=markup
        )
        return
    
    # Store listings in user data for pagination
    page = 0
    context.user_data['market_listings'] = [str(l['_id']) for l in listings]
    context.user_data['market_page'] = page
    
    await render_market_page(update.message, context, listings, page, user_id)

# ============================================
# RENDER MARKET PAGE - Display listing
# ============================================
async def render_market_page(message, context, listings, page, user_id):
    if page >= len(listings):
        return
    
    listing = listings[page]
    char = listing["character"]
    seller_id = listing["seller_id"]
    price = listing["price"]
    
    # Increment view count
    await sell_listings.update_one(
        {"_id": listing["_id"]}, 
        {"$inc": {"views": 1}}
    )
    
    # Get seller name
    try:
        seller = await context.bot.get_chat(seller_id)
        seller_name = seller.first_name
    except:
        seller_name = f"User {seller_id}"
    
    # Character details
    name = char.get("name", "Unknown")
    anime = char.get("anime", "Unknown")
    rarity = char.get("rarity", "Unknown")
    img_url = char.get("img_url", "")
    is_video = rarity == "🎥 AMV"
    views = listing.get("views", 0)
    is_own = seller_id == user_id
    
    caption = (
        f"<b>🏪 ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ {'(ʏᴏᴜʀ ʟɪsᴛɪɴɢ)' if is_own else ''}</b>\n\n"
        f"✨ <b>{name}</b>\n"
        f"🎭 {anime}\n"
        f"💫 {rarity}\n"
        f"💰 <b>{price:,}</b> ɢᴏʟᴅ\n"
        f"👤 sᴇʟʟᴇʀ: {seller_name}\n"
        f"👁️ {views:,} ᴠɪᴇᴡs\n"
        f"📖 ᴘᴀɢᴇ {page+1}/{len(listings)}"
    )
    
    # Build buttons
    buttons = []
    
    if is_own:
        buttons.append([InlineKeyboardButton("🗑️ ʀᴇᴍᴏᴠᴇ ʟɪsᴛɪɴɢ", callback_data=f"mu_{listing['_id']}")])
    else:
        buttons.append([InlineKeyboardButton("💳 ʙᴜʏ ɴᴏᴡ", callback_data=f"mb_{listing['_id']}")])
    
    # Navigation
    if len(listings) > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️ ᴘʀᴇᴠ", callback_data=f"mp_{page-1}"))
        nav.append(InlineKeyboardButton(f"• {page+1}/{len(listings)} •", callback_data="mpi"))
        if page < len(listings) - 1:
            nav.append(InlineKeyboardButton("ɴᴇxᴛ ▶️", callback_data=f"mp_{page+1}"))
        buttons.append(nav)
    
    # Filters
    buttons.append([
        InlineKeyboardButton("💰 ᴄʜᴇᴀᴘ", callback_data="mf_cheap"),
        InlineKeyboardButton("💎 ᴇxᴘᴇɴsɪᴠᴇ", callback_data="mf_expensive"),
        InlineKeyboardButton("🔄", callback_data="mr")
    ])
    
    markup = InlineKeyboardMarkup(buttons)
    
    # Update media
    try:
        if is_video:
            await query.edit_message_media(
                media=InputMediaVideo(media=img_url, caption=caption, parse_mode="HTML"),
                reply_markup=markup
            )
        else:
            await query.edit_message_media(
                media=InputMediaPhoto(media=img_url, caption=caption, parse_mode="HTML"),
                reply_markup=markup
            )
    except BadRequest:
        try:
            await query.edit_message_caption(
                caption=caption, 
                parse_mode="HTML", 
                reply_markup=markup
            )
        except:
            pass

# ============================================
# REGISTER ALL HANDLERS
# ============================================
application.add_handler(CommandHandler("sell", sell, block=False))
application.add_handler(CommandHandler("unsell", unsell, block=False))
application.add_handler(CommandHandler("market", market, block=False))
application.add_handler(CommandHandler("msales", msales, block=False))
application.add_handler(CallbackQueryHandler(market_callback, pattern=r"^m", block=False))