from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest
from datetime import datetime
from bson import ObjectId
from shivu import application, db, user_collection

collection = db['anime_characters_lol']
sell_listings = db['sell_listings']
sell_history = db['sell_history']

# Constants
MIN_PRICE = 100
MAX_PRICE = 1000000
MARKET_FEE = 0.05  # 5% transaction fee
LISTINGS_PER_PAGE = 1

async def sell(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b> /sell &lt;character_id&gt; &lt;price&gt;\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>/sell 12345 5000</code>\n\n"
            f"💡 <i>ᴘʀɪᴄᴇ ʀᴀɴɢᴇ: {MIN_PRICE:,} - {MAX_PRICE:,} ɢᴏʟᴅ</i>\n"
            f"📊 <i>ᴍᴀʀᴋᴇᴛ ғᴇᴇ: {int(MARKET_FEE*100)}%</i>",
            parse_mode="HTML"
        )
        return
    
    try:
        char_id = context.args[0]
        price = int(context.args[1])
        
        if price < MIN_PRICE or price > MAX_PRICE:
            await update.message.reply_text(
                f"⚠️ <b>ɪɴᴠᴀʟɪᴅ ᴘʀɪᴄᴇ</b>\n\n"
                f"ᴘʀɪᴄᴇ ᴍᴜsᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ {MIN_PRICE:,} ᴀɴᴅ {MAX_PRICE:,} ɢᴏʟᴅ",
                parse_mode="HTML"
            )
            return
        
        user_data = await user_collection.find_one({"id": user_id})
        if not user_data:
            await update.message.reply_text("⚠️ <b>ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ғᴏᴜɴᴅ</b>", parse_mode="HTML")
            return
        
        char_to_sell = next((c for c in user_data.get("characters", []) if str(c.get("id", c.get("_id"))) == char_id), None)
        
        if not char_to_sell:
            await update.message.reply_text(
                f"⚠️ <b>ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ</b>\n\n"
                f"ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴄʜᴀʀᴀᴄᴛᴇʀ <code>{char_id}</code>\n\n"
                f"<i>ᴜsᴇ /collection ᴛᴏ ᴠɪᴇᴡ ʏᴏᴜʀ ᴄʜᴀʀᴀᴄᴛᴇʀs</i>",
                parse_mode="HTML"
            )
            return
        
        if await sell_listings.find_one({"seller_id": user_id, "character.id": char_to_sell.get("id", char_to_sell.get("_id"))}):
            await update.message.reply_text(
                "⚠️ <b>ᴀʟʀᴇᴀᴅʏ ʟɪsᴛᴇᴅ!</b>\n\n"
                "ᴛʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ ɪs ᴀʟʀᴇᴀᴅʏ ᴏɴ sᴀʟᴇ\n\n"
                "<i>ᴜsᴇ /unsell ᴛᴏ ʀᴇᴍᴏᴠᴇ ɪᴛ ғɪʀsᴛ</i>",
                parse_mode="HTML"
            )
            return
        
        user_listings = await sell_listings.count_documents({"seller_id": user_id})
        if user_listings >= 10:
            await update.message.reply_text(
                "⚠️ <b>ʟɪsᴛɪɴɢ ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ</b>\n\n"
                "ʏᴏᴜ ᴄᴀɴ ᴏɴʟʏ ʟɪsᴛ ᴜᴘ ᴛᴏ 10 ᴄʜᴀʀᴀᴄᴛᴇʀs\n\n"
                "<i>ʀᴇᴍᴏᴠᴇ sᴏᴍᴇ ᴡɪᴛʜ /unsell</i>",
                parse_mode="HTML"
            )
            return
        
        await sell_listings.insert_one({
            "seller_id": user_id,
            "character": char_to_sell,
            "price": price,
            "listed_at": datetime.utcnow(),
            "views": 0,
            "favorites": 0
        })
        
        await user_collection.update_one({"id": user_id}, {"$pull": {"characters": char_to_sell}})
        
        fee = int(price * MARKET_FEE)
        you_get = price - fee
        
        await update.message.reply_text(
            f"<b>✨ ʟɪsᴛᴇᴅ ғᴏʀ sᴀʟᴇ!</b>\n\n"
            f"🎭 <b>{char_to_sell.get('name', 'Unknown')}</b>\n"
            f"📺 {char_to_sell.get('anime', 'Unknown')}\n"
            f"💫 {char_to_sell.get('rarity', 'Unknown')}\n\n"
            f"💰 <b>ᴘʀɪᴄᴇ:</b> {price:,} ɢᴏʟᴅ\n"
            f"📉 <b>ᴍᴀʀᴋᴇᴛ ғᴇᴇ:</b> {fee:,} ɢᴏʟᴅ ({int(MARKET_FEE*100)}%)\n"
            f"💵 <b>ʏᴏᴜ ɢᴇᴛ:</b> {you_get:,} ɢᴏʟᴅ\n\n"
            f"<i>ᴜsᴇ /market mine ᴛᴏ ᴠɪᴇᴡ ʏᴏᴜʀ ʟɪsᴛɪɴɢs</i>",
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("⚠️ <b>ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ғᴏʀᴍᴀᴛ</b>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"⚠️ <b>ᴇʀʀᴏʀ:</b> {str(e)}", parse_mode="HTML")

async def unsell(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b> /unsell &lt;character_id&gt;\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>/unsell 12345</code>\n\n"
            "<i>ᴜsᴇ /market mine ᴛᴏ sᴇᴇ ʏᴏᴜʀ ʟɪsᴛɪɴɢs</i>",
            parse_mode="HTML"
        )
        return
    
    try:
        listing = await sell_listings.find_one({"seller_id": user_id, "character.id": context.args[0]})
        
        if not listing:
            await update.message.reply_text(
                f"⚠️ <b>ʟɪsᴛɪɴɢ ɴᴏᴛ ғᴏᴜɴᴅ</b>\n\n"
                f"ɴᴏ ᴀᴄᴛɪᴠᴇ ʟɪsᴛɪɴɢ ғᴏʀ <code>{context.args[0]}</code>",
                parse_mode="HTML"
            )
            return
        
        await user_collection.update_one({"id": user_id}, {"$push": {"characters": listing["character"]}}, upsert=True)
        await sell_listings.delete_one({"_id": listing["_id"]})
        
        await update.message.reply_text(
            f"<b>🔙 ʀᴇᴍᴏᴠᴇᴅ ғʀᴏᴍ ᴍᴀʀᴋᴇᴛ</b>\n\n"
            f"✨ <b>{listing['character'].get('name', 'Unknown')}</b> ʀᴇᴛᴜʀɴᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ\n\n"
            f"👁️ <i>{listing.get('views', 0)} ᴠɪᴇᴡs ᴡʜɪʟᴇ ʟɪsᴛᴇᴅ</i>",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ <b>ᴇʀʀᴏʀ:</b> {str(e)}", parse_mode="HTML")

async def market(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    filter_query = {}
    sort_by = [("listed_at", -1)]
    filter_type = "all"
    
    if context.args:
        arg = context.args[0].lower()
        if arg == "mine":
            filter_query["seller_id"] = user_id
            filter_type = "mine"
        elif arg == "cheap":
            sort_by = [("price", 1)]
            filter_type = "cheap"
        elif arg == "expensive":
            sort_by = [("price", -1)]
            filter_type = "expensive"
        elif arg == "popular":
            sort_by = [("views", -1)]
            filter_type = "popular"
    
    listings = await sell_listings.find(filter_query).sort(sort_by).to_list(length=None)
    
    if not listings:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="j")]])
        await update.message.reply_text(
            "<b>🏪 ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ ᴇᴍᴘᴛʏ</b>\n\n"
            "😔 ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴀᴠᴀɪʟᴀʙʟᴇ\n\n"
            "<b>💡 ᴛɪᴘs:</b>\n"
            "• ᴜsᴇ /sell ᴛᴏ ʟɪsᴛ ʏᴏᴜʀ ᴄʜᴀʀᴀᴄᴛᴇʀs\n"
            "• /market mine - ʏᴏᴜʀ ʟɪsᴛɪɴɢs\n"
            "• /market cheap - ʙᴇsᴛ ᴅᴇᴀʟs\n"
            "• /market expensive - ʜɪɢʜ ᴠᴀʟᴜᴇ\n"
            "• /market popular - ᴍᴏsᴛ ᴠɪᴇᴡᴇᴅ",
            parse_mode="HTML",
            reply_markup=markup
        )
        return
    
    context.user_data['market_listings'] = [str(l['_id']) for l in listings]
    context.user_data['market_page'] = 0
    context.user_data['market_filter'] = filter_type
    await render_market_page(update.message, context, listings, 0, user_id)

async def render_market_page(message, context, listings, page, user_id):
    if page >= len(listings):
        return
    
    listing = listings[page]
    char = listing["character"]
    seller_id = listing["seller_id"]
    price = listing["price"]
    
    await sell_listings.update_one({"_id": listing["_id"]}, {"$inc": {"views": 1}})
    
    try:
        seller = await context.bot.get_chat(seller_id)
        seller_name = seller.first_name
    except:
        seller_name = f"User {seller_id}"
    
    is_video = char.get("rarity") == "🎥 AMV"
    is_own = seller_id == user_id
    
    fee = int(price * MARKET_FEE)
    final_price = price - fee if is_own else price
    
    time_diff = datetime.utcnow() - listing.get("listed_at", datetime.utcnow())
    hours = int(time_diff.total_seconds() / 3600)
    time_str = f"{hours}h ago" if hours > 0 else "just now"
    
    caption = (
        f"<b>🏪 ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ {'(ʏᴏᴜʀ ʟɪsᴛɪɴɢ)' if is_own else ''}</b>\n\n"
        f"✨ <b>{char.get('name', 'Unknown')}</b>\n"
        f"🎭 {char.get('anime', 'Unknown')}\n"
        f"💫 {char.get('rarity', 'Unknown')}\n\n"
        f"💰 <b>ᴘʀɪᴄᴇ:</b> {price:,} ɢᴏʟᴅ\n"
        f"👤 <b>sᴇʟʟᴇʀ:</b> {seller_name}\n"
        f"👁️ <b>ᴠɪᴇᴡs:</b> {listing.get('views', 0):,}\n"
        f"⏰ <b>ʟɪsᴛᴇᴅ:</b> {time_str}\n\n"
        f"📖 ᴘᴀɢᴇ {page+1}/{len(listings)}"
    )
    
    if is_own:
        caption += f"\n\n💵 <b>ʏᴏᴜ'ʟʟ ɢᴇᴛ:</b> {final_price:,} ɢᴏʟᴅ (ᴀғᴛᴇʀ {int(MARKET_FEE*100)}% ғᴇᴇ)"
    
    buttons = []
    
    # Main action button
    main_btn = InlineKeyboardButton(
        "🗑️ ʀᴇᴍᴏᴠᴇ" if is_own else "💳 ʙᴜʏ ɴᴏᴡ",
        callback_data=f"k_{listing['_id']}" if is_own else f"t_{listing['_id']}"
    )
    buttons.append([main_btn])
    
    # Navigation
    if len(listings) > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"p_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{len(listings)}", callback_data="z"))
        if page < len(listings) - 1:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"p_{page+1}"))
        buttons.append(nav)
    
    # Filters
    buttons.append([
        InlineKeyboardButton("💰 ᴄʜᴇᴀᴘ", callback_data="e_cheap"),
        InlineKeyboardButton("💎 ᴇxᴘᴇɴsɪᴠᴇ", callback_data="e_expensive"),
        InlineKeyboardButton("🔥 ᴘᴏᴘᴜʟᴀʀ", callback_data="e_popular")
    ])
    
    # Bottom row
    buttons.append([
        InlineKeyboardButton("👤 ᴍɪɴᴇ", callback_data="e_mine"),
        InlineKeyboardButton("🏪 ᴀʟʟ", callback_data="e_all"),
        InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="j")
    ])
    
    markup = InlineKeyboardMarkup(buttons)
    
    try:
        if is_video:
            await message.reply_video(
                video=char.get("img_url"),
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        else:
            await message.reply_photo(
                photo=char.get("img_url"),
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
    except BadRequest:
        await message.reply_text(f"{caption}\n\n⚠️ ᴍᴇᴅɪᴀ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ", parse_mode="HTML", reply_markup=markup)

async def msales(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    sales = await sell_history.find({"seller_id": user_id}).sort("sold_at", -1).limit(15).to_list(15)
    purchases = await sell_history.find({"buyer_id": user_id}).sort("sold_at", -1).limit(15).to_list(15)
    
    active_listings = await sell_listings.count_documents({"seller_id": user_id})
    
    text = "<b>📊 ʏᴏᴜʀ ᴛʀᴀᴅᴇ ʜɪsᴛᴏʀʏ</b>\n\n"
    
    if sales:
        text += "<b>💰 ʀᴇᴄᴇɴᴛ sᴀʟᴇs:</b>\n"
        total = sum(s.get("price", 0) for s in sales)
        for idx, s in enumerate(sales[:5], 1):
            text += f"{idx}. {s.get('character_name', 'Unknown')} - {s.get('price', 0):,} 💎\n"
        text += f"<b>ᴛᴏᴛᴀʟ ᴇᴀʀɴᴇᴅ:</b> {total:,} 💰\n\n"
    
    if purchases:
        text += "<b>🛒 ʀᴇᴄᴇɴᴛ ᴘᴜʀᴄʜᴀsᴇs:</b>\n"
        total = sum(p.get("price", 0) for p in purchases)
        for idx, p in enumerate(purchases[:5], 1):
            text += f"{idx}. {p.get('character_name', 'Unknown')} - {p.get('price', 0):,} 💎\n"
        text += f"<b>ᴛᴏᴛᴀʟ sᴘᴇɴᴛ:</b> {total:,} 💰\n\n"
    
    text += f"<b>📦 ᴀᴄᴛɪᴠᴇ ʟɪsᴛɪɴɢs:</b> {active_listings}/10"
    
    if not sales and not purchases:
        text += "😔 ɴᴏ ᴛʀᴀᴅᴇ ʜɪsᴛᴏʀʏ ʏᴇᴛ\n\n<i>sᴛᴀʀᴛ ʙᴜʏɪɴɢ ᴏʀ sᴇʟʟɪɴɢ ᴡɪᴛʜ /market!</i>"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def market_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    # Navigation (p_0, p_1, etc.)
    if data.startswith("p_"):
        page = int(data.split("_")[1])
        listings = [await sell_listings.find_one({"_id": ObjectId(lid)}) for lid in context.user_data.get('market_listings', [])]
        listings = [l for l in listings if l]
        
        if listings:
            context.user_data['market_page'] = page
            await update_market_display(query, context, listings, page, user_id)
        else:
            await query.answer("⚠️ ɴᴏ ʟɪsᴛɪɴɢs", show_alert=True)
    
    # Page info (z)
    elif data == "z":
        await query.answer("📖 ᴜsᴇ ᴀʀʀᴏᴡs ᴛᴏ ɴᴀᴠɪɢᴀᴛᴇ")
    
    # Refresh (j)
    elif data == "j":
        current_filter = context.user_data.get('market_filter', 'all')
        filter_query = {}
        sort_by = [("listed_at", -1)]
        
        if current_filter == "mine":
            filter_query["seller_id"] = user_id
        elif current_filter == "cheap":
            sort_by = [("price", 1)]
        elif current_filter == "expensive":
            sort_by = [("price", -1)]
        elif current_filter == "popular":
            sort_by = [("views", -1)]
        
        listings = await sell_listings.find(filter_query).sort(sort_by).to_list(None)
        if listings:
            context.user_data['market_listings'] = [str(l['_id']) for l in listings]
            context.user_data['market_page'] = 0
            await update_market_display(query, context, listings, 0, user_id)
            await query.answer("🔄 ʀᴇғʀᴇsʜᴇᴅ")
        else:
            await query.answer("😔 ᴍᴀʀᴋᴇᴛ ᴇᴍᴘᴛʏ", show_alert=True)
    
    # Filters (e_cheap, e_expensive, e_popular, e_mine, e_all)
    elif data.startswith("e_"):
        filter_type = data.split("_")[1]
        filter_query = {}
        sort_by = [("listed_at", -1)]
        
        if filter_type == "mine":
            filter_query["seller_id"] = user_id
            filter_name = "ʏᴏᴜʀ ʟɪsᴛɪɴɢs"
        elif filter_type == "cheap":
            sort_by = [("price", 1)]
            filter_name = "💰 ᴄʜᴇᴀᴘᴇsᴛ ғɪʀsᴛ"
        elif filter_type == "expensive":
            sort_by = [("price", -1)]
            filter_name = "💎 ᴍᴏsᴛ ᴇxᴘᴇɴsɪᴠᴇ ғɪʀsᴛ"
        elif filter_type == "popular":
            sort_by = [("views", -1)]
            filter_name = "🔥 ᴍᴏsᴛ ᴘᴏᴘᴜʟᴀʀ"
        else:
            filter_name = "🏪 ᴀʟʟ ʟɪsᴛɪɴɢs"
        
        listings = await sell_listings.find(filter_query).sort(sort_by).to_list(None)
        
        if listings:
            context.user_data['market_listings'] = [str(l['_id']) for l in listings]
            context.user_data['market_page'] = 0
            context.user_data['market_filter'] = filter_type
            await update_market_display(query, context, listings, 0, user_id)
            await query.answer(filter_name)
        else:
            await query.answer("😔 ɴᴏ ʟɪsᴛɪɴɢs", show_alert=True)
    
    # Buy request (t_<listing_id>)
    elif data.startswith("t_"):
        listing = await sell_listings.find_one({"_id": ObjectId(data.split("_", 1)[1])})
        
        if not listing:
            await query.answer("⚠️ ʟɪsᴛɪɴɢ ɴᴏ ʟᴏɴɢᴇʀ ᴀᴠᴀɪʟᴀʙʟᴇ", show_alert=True)
            return
        
        if listing["seller_id"] == user_id:
            await query.answer("⚠️ ᴄᴀɴ'ᴛ ʙᴜʏ ʏᴏᴜʀ ᴏᴡɴ ʟɪsᴛɪɴɢ", show_alert=True)
            return
        
        user_data = await user_collection.find_one({"id": user_id})
        balance = user_data.get("balance", 0) if user_data else 0
        price = listing["price"]
        
        if balance < price:
            await query.answer(
                f"⚠️ ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ\n\nɴᴇᴇᴅ: {price:,} ɢᴏʟᴅ\nʏᴏᴜ ʜᴀᴠᴇ: {balance:,} ɢᴏʟᴅ",
                show_alert=True
            )
            return
        
        buttons = [[
            InlineKeyboardButton("✅ ᴄᴏɴғɪʀᴍ", callback_data=f"w_{listing['_id']}"),
            InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="x")
        ]]
        
        try:
            await query.edit_message_caption(
                caption=(
                    f"<b>💳 ᴄᴏɴғɪʀᴍ ᴘᴜʀᴄʜᴀsᴇ</b>\n\n"
                    f"✨ <b>{listing['character'].get('name', 'Unknown')}</b>\n"
                    f"🎭 {listing['character'].get('anime', 'Unknown')}\n"
                    f"💫 {listing['character'].get('rarity', 'Unknown')}\n\n"
                    f"💰 <b>ᴘʀɪᴄᴇ:</b> {price:,} ɢᴏʟᴅ\n\n"
                    f"💵 <b>ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ:</b> {balance:,} ɢᴏʟᴅ\n"
                    f"📉 <b>ᴀғᴛᴇʀ ᴘᴜʀᴄʜᴀsᴇ:</b> {balance - price:,} ɢᴏʟᴅ\n\n"
                    f"⚠️ <i>ᴀʀᴇ ʏᴏᴜ sᴜʀᴇ?</i>"
                ),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except BadRequest:
            pass
    
    # Confirm purchase (w_<listing_id>)
    elif data.startswith("w_"):
        listing = await sell_listings.find_one({"_id": ObjectId(data.split("_", 1)[1])})
        
        if not listing:
            await query.answer("⚠️ ʟɪsᴛɪɴɢ ɴᴏ ʟᴏɴɢᴇʀ ᴀᴠᴀɪʟᴀʙʟᴇ", show_alert=True)
            return
        
        if listing["seller_id"] == user_id:
            await query.answer("⚠️ ᴄᴀɴ'ᴛ ʙᴜʏ ʏᴏᴜʀ ᴏᴡɴ ʟɪsᴛɪɴɢ", show_alert=True)
            return
        
        user_data = await user_collection.find_one({"id": user_id})
        balance = user_data.get("balance", 0) if user_data else 0
        price = listing["price"]
        
        if balance < price:
            await query.answer("⚠️ ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ", show_alert=True)
            return
        
        char = listing["character"]
        
        # Calculate seller's earnings (after fee)
        fee = int(price * MARKET_FEE)
        seller_gets = price - fee
        
        # Update buyer
        await user_collection.update_one(
            {"id": user_id},
            {"$inc": {"balance": -price}, "$push": {"characters": char}},
            upsert=True
        )
        
        # Update seller
        await user_collection.update_one(
            {"id": listing["seller_id"]},
            {"$inc": {"balance": seller_gets}},
            upsert=True
        )
        
        # Remove listing
        await sell_listings.delete_one({"_id": listing["_id"]})
        
        # Save to history
        await sell_history.insert_one({
            "seller_id": listing["seller_id"],
            "buyer_id": user_id,
            "character_name": char.get("name", "Unknown"),
            "character_anime": char.get("anime", "Unknown"),
            "price": price,
            "fee": fee,
            "sold_at": datetime.utcnow()
        })
        
        # Notify seller
        try:
            await context.bot.send_message(
                listing["seller_id"],
                f"<b>💰 sᴀʟᴇ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
                f"✨ <b>{char.get('name', 'Unknown')}</b> sᴏʟᴅ!\n\n"
                f"💵 <b>ᴇᴀʀɴᴇᴅ:</b> {seller_gets:,} ɢᴏʟᴅ\n"
                f"📊 <b>ғᴇᴇ:</b> {fee:,} ɢᴏʟᴅ ({int(MARKET_FEE*100)}%)\n"
                f"👤 <b>ʙᴜʏᴇʀ:</b> {query.from_user.first_name}",
                parse_mode="HTML"
            )
        except:
            pass
        
        try:
            await query.edit_message_caption(
                caption=(
                    f"<b>✅ ᴘᴜʀᴄʜᴀsᴇ sᴜᴄᴄᴇssғᴜʟ!</b>\n\n"
                    f"🎉 <b>{char.get('name', 'Unknown')}</b>\n"
                    f"🎭 {char.get('anime', 'Unknown')}\n"
                    f"💫 {char.get('rarity', 'Unknown')}\n\n"
                    f"💰 <b>ᴘᴀɪᴅ:</b> {price:,} ɢᴏʟᴅ\n"
                    f"💵 <b>ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ:</b> {balance - price:,} ɢᴏʟᴅ\n\n"
                    f"<i>ᴄʜᴀʀᴀᴄᴛᴇʀ ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ!</i>"
                ),
                parse_mode="HTML"
            )
        except BadRequest:
            pass
        
        await query.answer("✨ ᴘᴜʀᴄʜᴀsᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!")
    
    # Remove own listing (k_<listing_id>)
    elif data.startswith("k_"):
        listing = await sell_listings.find_one({"_id": ObjectId(data.split("_", 1)[1]), "seller_id": user_id})
        
        if not listing:
            await query.answer("⚠️ ʟɪsᴛɪɴɢ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        await user_collection.update_one(
            {"id": user_id},
            {"$push": {"characters": listing["character"]}},
            upsert=True
        )
        await sell_listings.delete_one({"_id": listing["_id"]})
        await query.answer("🔙 ʀᴇᴍᴏᴠᴇᴅ ғʀᴏᴍ ᴍᴀʀᴋᴇᴛ")
        
        # Refresh market
        current_filter = context.user_data.get('market_filter', 'all')
        filter_query = {}
        sort_by = [("listed_at", -1)]
        
        if current_filter == "mine":
            filter_query["seller_id"] = user_id
        elif current_filter == "cheap":
            sort_by = [("price", 1)]
        elif current_filter == "expensive":
            sort_by = [("price", -1)]
        elif current_filter == "popular":
            sort_by = [("views", -1)]
        
        listings = await sell_listings.find(filter_query).sort(sort_by).to_list(None)
        if listings:
            context.user_data['market_listings'] = [str(l['_id']) for l in listings]
            context.user_data['market_page'] = 0
            await update_market_display(query, context, listings, 0, user_id)
        else:
            try:
                await query.edit_message_caption(
                    caption="<b>🏪 ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ ᴇᴍᴘᴛʏ</b>\n\nɴᴏ ʟɪsᴛɪɴɢs ᴀᴠᴀɪʟᴀʙʟᴇ",
                    parse_mode="HTML"
                )
            except:
                pass
    
    # Cancel (x)
    elif data == "x":
        page = context.user_data.get('market_page', 0)
        listings = [await sell_listings.find_one({"_id": ObjectId(lid)}) for lid in context.user_data.get('market_listings', [])]
        listings = [l for l in listings if l]
        
        if listings:
            await update_market_display(query, context, listings, page, user_id)
        await query.answer("❌ ᴄᴀɴᴄᴇʟʟᴇᴅ")

async def update_market_display(query, context, listings, page, user_id):
    if page >= len(listings):
        return
    
    listing = listings[page]
    char = listing["character"]
    seller_id = listing["seller_id"]
    price = listing["price"]
    
    try:
        seller = await context.bot.get_chat(seller_id)
        seller_name = seller.first_name
    except:
        seller_name = f"User {seller_id}"
    
    is_video = char.get("rarity") == "🎥 AMV"
    is_own = seller_id == user_id
    
    fee = int(price * MARKET_FEE)
    final_price = price - fee if is_own else price
    
    time_diff = datetime.utcnow() - listing.get("listed_at", datetime.utcnow())
    hours = int(time_diff.total_seconds() / 3600)
    time_str = f"{hours}h ago" if hours > 0 else "just now"
    
    caption = (
        f"<b>🏪 ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ {'(ʏᴏᴜʀ ʟɪsᴛɪɴɢ)' if is_own else ''}</b>\n\n"
        f"✨ <b>{char.get('name', 'Unknown')}</b>\n"
        f"🎭 {char.get('anime', 'Unknown')}\n"
        f"💫 {char.get('rarity', 'Unknown')}\n\n"
        f"💰 <b>ᴘʀɪᴄᴇ:</b> {price:,} ɢᴏʟᴅ\n"
        f"👤 <b>sᴇʟʟᴇʀ:</b> {seller_name}\n"
        f"👁️ <b>ᴠɪᴇᴡs:</b> {listing.get('views', 0):,}\n"
        f"⏰ <b>ʟɪsᴛᴇᴅ:</b> {time_str}\n\n"
        f"📖 ᴘᴀɢᴇ {page+1}/{len(listings)}"
    )
    
    if is_own:
        caption += f"\n\n💵 <b>ʏᴏᴜ'ʟʟ ɢᴇᴛ:</b> {final_price:,} ɢᴏʟᴅ (ᴀғᴛᴇʀ {int(MARKET_FEE*100)}% ғᴇᴇ)"
    
    buttons = []
    
    # Main action button
    main_btn = InlineKeyboardButton(
        "🗑️ ʀᴇᴍᴏᴠᴇ" if is_own else "💳 ʙᴜʏ ɴᴏᴡ",
        callback_data=f"k_{listing['_id']}" if is_own else f"t_{listing['_id']}"
    )
    buttons.append([main_btn])
    
    # Navigation
    if len(listings) > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"p_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{len(listings)}", callback_data="z"))
        if page < len(listings) - 1:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"p_{page+1}"))
        buttons.append(nav)
    
    # Filters
    buttons.append([
        InlineKeyboardButton("💰 ᴄʜᴇᴀᴘ", callback_data="e_cheap"),
        InlineKeyboardButton("💎 ᴇxᴘᴇɴsɪᴠᴇ", callback_data="e_expensive"),
        InlineKeyboardButton("🔥 ᴘᴏᴘᴜʟᴀʀ", callback_data="e_popular")
    ])
    
    # Bottom row
    buttons.append([
        InlineKeyboardButton("👤 ᴍɪɴᴇ", callback_data="e_mine"),
        InlineKeyboardButton("🏪 ᴀʟʟ", callback_data="e_all"),
        InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="j")
    ])
    
    markup = InlineKeyboardMarkup(buttons)
    
    try:
        if is_video:
            await query.edit_message_media(
                media=InputMediaVideo(media=char.get("img_url"), caption=caption, parse_mode="HTML"),
                reply_markup=markup
            )
        else:
            await query.edit_message_media(
                media=InputMediaPhoto(media=char.get("img_url"), caption=caption, parse_mode="HTML"),
                reply_markup=markup
            )
    except BadRequest:
        try:
            await query.edit_message_caption(caption=caption, parse_mode="HTML", reply_markup=markup)
        except:
            pass

# Register handlers
application.add_handler(CommandHandler("sell", sell, block=False))
application.add_handler(CommandHandler("unsell", unsell, block=False))
application.add_handler(CommandHandler("market", market, block=False))
application.add_handler(CommandHandler("msales", msales, block=False))
application.add_handler(CallbackQueryHandler(market_callback, pattern=r"^[jpzetkwx]", block=False))