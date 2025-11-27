from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest
from datetime import datetime
from bson import ObjectId
from shivu import application, db, user_collection

collection = db['anime_characters_lol']
sell_listings = db['sell_listings']
sell_history = db['sell_history']

MIN_PRICE = 100
MAX_PRICE = 1000000
MARKET_FEE = 0.05

async def sell(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ <b>ɪɴᴄᴏʀʀᴇᴄᴛ ᴜsᴀɢᴇ</b>\n\n"
            "<b>ғᴏʀᴍᴀᴛ:</b> <code>/sell [character_id] [price]</code>\n\n"
            "<blockquote><b>ᴇxᴀᴍᴘʟᴇ:</b> <code>/sell 12345 5000</code>\n\n"
            f"💰 <b>ᴘʀɪᴄᴇ ʀᴀɴɢᴇ:</b> {MIN_PRICE:,} - {MAX_PRICE:,}\n"
            f"💸 <b>ᴍᴀʀᴋᴇᴛ ғᴇᴇ:</b> {int(MARKET_FEE*100)}%</blockquote>",
            parse_mode="HTML"
        )
        return
    
    try:
        char_id = context.args[0]
        price = int(context.args[1])
        
        if price < MIN_PRICE or price > MAX_PRICE:
            await update.message.reply_text(
                f"⚠️ <b>ɪɴᴠᴀʟɪᴅ ᴘʀɪᴄᴇ ʀᴀɴɢᴇ</b>\n\n"
                f"<blockquote>ᴘʀɪᴄᴇ ᴍᴜsᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ:\n"
                f"<b>{MIN_PRICE:,}</b> - <b>{MAX_PRICE:,}</b> ɢᴏʟᴅ</blockquote>",
                parse_mode="HTML"
            )
            return
        
        user_data = await user_collection.find_one({"id": user_id})
        if not user_data:
            await update.message.reply_text("⚠️ <b>ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ғᴏᴜɴᴅ ɪɴ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ</b>", parse_mode="HTML")
            return
        
        char_to_sell = next((c for c in user_data.get("characters", []) if str(c.get("id", c.get("_id"))) == char_id), None)
        
        if not char_to_sell:
            await update.message.reply_text(
                f"⚠️ <b>ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ</b>\n\n"
                f"<blockquote>ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴄʜᴀʀᴀᴄᴛᴇʀ ɪᴅ: <code>{char_id}</code>\n\n"
                f"💡 ᴜsᴇ /collection ᴛᴏ ᴠɪᴇᴡ ʏᴏᴜʀ ᴄʜᴀʀᴀᴄᴛᴇʀs</blockquote>",
                parse_mode="HTML"
            )
            return
        
        if await sell_listings.find_one({"seller_id": user_id, "character.id": char_to_sell.get("id", char_to_sell.get("_id"))}):
            await update.message.reply_text(
                "⚠️ <b>ᴀʟʀᴇᴀᴅʏ ʟɪsᴛᴇᴅ</b>\n\n"
                "<blockquote>ᴛʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ ɪs ᴀʟʀᴇᴀᴅʏ ᴏɴ ᴛʜᴇ ᴍᴀʀᴋᴇᴛ\n\n"
                "💡 ᴜsᴇ /unsell ᴛᴏ ʀᴇᴍᴏᴠᴇ ɪᴛ ғɪʀsᴛ</blockquote>",
                parse_mode="HTML"
            )
            return
        
        user_listings = await sell_listings.count_documents({"seller_id": user_id})
        if user_listings >= 10:
            await update.message.reply_text(
                "⚠️ <b>ʟɪsᴛɪɴɢ ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ</b>\n\n"
                "<blockquote>📦 <b>ᴍᴀx ʟɪsᴛɪɴɢs:</b> 10/10\n\n"
                "💡 ʀᴇᴍᴏᴠᴇ sᴏᴍᴇ ᴡɪᴛʜ /unsell ᴏʀ /mymarket</blockquote>",
                parse_mode="HTML"
            )
            return
        
        await sell_listings.insert_one({
            "seller_id": user_id,
            "character": char_to_sell,
            "price": price,
            "listed_at": datetime.utcnow(),
            "views": 0
        })
        
        await user_collection.update_one({"id": user_id}, {"$pull": {"characters": char_to_sell}})
        
        fee = int(price * MARKET_FEE)
        you_get = price - fee
        
        await update.message.reply_text(
            f"✅ <b>sᴜᴄᴄᴇssғᴜʟʟʏ ʟɪsᴛᴇᴅ!</b>\n\n"
            f"<blockquote expandable>🎭 <b>ɴᴀᴍᴇ:</b> <code>{char_to_sell.get('name', 'Unknown')}</code>\n"
            f"📺 <b>ᴀɴɪᴍᴇ:</b> <code>{char_to_sell.get('anime', 'Unknown')}</code>\n"
            f"💫 <b>ʀᴀʀɪᴛʏ:</b> {char_to_sell.get('rarity', 'Unknown')}\n"
            f"🆔 <b>ɪᴅ:</b> <code>{char_id}</code></blockquote>\n\n"
            f"<blockquote>💰 <b>ʟɪsᴛᴇᴅ ᴘʀɪᴄᴇ:</b> <code>{price:,}</code> ɢᴏʟᴅ\n"
            f"📉 <b>ᴍᴀʀᴋᴇᴛ ғᴇᴇ:</b> <code>{fee:,}</code> ɢᴏʟᴅ ({int(MARKET_FEE*100)}%)\n"
            f"💵 <b>ʏᴏᴜ ʀᴇᴄᴇɪᴠᴇ:</b> <code>{you_get:,}</code> ɢᴏʟᴅ</blockquote>\n\n"
            f"📊 ᴠɪᴇᴡ ʏᴏᴜʀ ʟɪsᴛɪɴɢs: /mymarket",
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("⚠️ <b>ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ғᴏʀᴍᴀᴛ</b>\n\n<blockquote>ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ</blockquote>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"⚠️ <b>ᴇʀʀᴏʀ:</b>\n\n<blockquote><code>{str(e)}</code></blockquote>", parse_mode="HTML")

async def unsell(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "⚠️ <b>ɪɴᴄᴏʀʀᴇᴄᴛ ᴜsᴀɢᴇ</b>\n\n"
            "<b>ғᴏʀᴍᴀᴛ:</b> <code>/unsell [character_id]</code>\n\n"
            "<blockquote><b>ᴇxᴀᴍᴘʟᴇ:</b> <code>/unsell 12345</code>\n\n"
            "💡 ᴜsᴇ /mymarket ᴛᴏ sᴇᴇ ʏᴏᴜʀ ʟɪsᴛɪɴɢs</blockquote>",
            parse_mode="HTML"
        )
        return
    
    try:
        listing = await sell_listings.find_one({"seller_id": user_id, "character.id": context.args[0]})
        
        if not listing:
            await update.message.reply_text(
                f"⚠️ <b>ʟɪsᴛɪɴɢ ɴᴏᴛ ғᴏᴜɴᴅ</b>\n\n"
                f"<blockquote>ɴᴏ ᴀᴄᴛɪᴠᴇ ʟɪsᴛɪɴɢ ғᴏʀ ɪᴅ: <code>{context.args[0]}</code></blockquote>",
                parse_mode="HTML"
            )
            return
        
        await user_collection.update_one({"id": user_id}, {"$push": {"characters": listing["character"]}}, upsert=True)
        await sell_listings.delete_one({"_id": listing["_id"]})
        
        await update.message.reply_text(
            f"✅ <b>ʀᴇᴍᴏᴠᴇᴅ ғʀᴏᴍ ᴍᴀʀᴋᴇᴛ</b>\n\n"
            f"<blockquote>🎭 <b>{listing['character'].get('name', 'Unknown')}</b>\n"
            f"ʀᴇᴛᴜʀɴᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ\n\n"
            f"👁️ <b>ᴛᴏᴛᴀʟ ᴠɪᴇᴡs:</b> {listing.get('views', 0):,}</blockquote>",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ <b>ᴇʀʀᴏʀ:</b>\n\n<blockquote><code>{str(e)}</code></blockquote>", parse_mode="HTML")

async def market(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    listings = await sell_listings.find({}).sort("listed_at", -1).to_list(length=100)
    
    if not listings:
        await update.message.reply_text(
            "🏪 <b>ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ</b>\n\n"
            "<blockquote>😔 ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴄᴜʀʀᴇɴᴛʟʏ ᴀᴠᴀɪʟᴀʙʟᴇ\n\n"
            "<b>💡 ᴄᴏᴍᴍᴀɴᴅs:</b>\n"
            "• /sell - ʟɪsᴛ ʏᴏᴜʀ ᴄʜᴀʀᴀᴄᴛᴇʀs\n"
            "• /mymarket - ʏᴏᴜʀ ʟɪsᴛɪɴɢs\n"
            "• /msales - ᴛʀᴀᴅᴇ ʜɪsᴛᴏʀʏ\n"
            "• /lists - ᴠɪᴇᴡ ᴀʟʟ ʟɪsᴛɪɴɢs</blockquote>",
            parse_mode="HTML"
        )
        return
    
    context.user_data['market_listings'] = [str(l['_id']) for l in listings]
    context.user_data['market_page'] = 0
    context.user_data['viewing_mine'] = False
    await render_market_page(update.message, context, listings, 0, user_id)

async def mymarket(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    listings = await sell_listings.find({"seller_id": user_id}).sort("listed_at", -1).to_list(length=100)
    
    if not listings:
        await update.message.reply_text(
            "📦 <b>ʏᴏᴜʀ ʟɪsᴛɪɴɢs</b>\n\n"
            "<blockquote>😔 ʏᴏᴜ ʜᴀᴠᴇ ɴᴏ ᴀᴄᴛɪᴠᴇ ʟɪsᴛɪɴɢs\n\n"
            "💡 ᴜsᴇ /sell ᴛᴏ ʟɪsᴛ ᴄʜᴀʀᴀᴄᴛᴇʀs</blockquote>",
            parse_mode="HTML"
        )
        return
    
    context.user_data['market_listings'] = [str(l['_id']) for l in listings]
    context.user_data['market_page'] = 0
    context.user_data['viewing_mine'] = True
    await render_market_page(update.message, context, listings, 0, user_id, my_listings=True)

async def lists(update: Update, context: CallbackContext):
    listings = await sell_listings.find({}).sort("listed_at", -1).to_list(length=100)
    
    if not listings:
        await update.message.reply_text(
            "📋 <b>ᴍᴀʀᴋᴇᴛ ʟɪsᴛɪɴɢs</b>\n\n"
            "<blockquote>😔 ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴄᴜʀʀᴇɴᴛʟʏ ʟɪsᴛᴇᴅ\n\n"
            "💡 ᴜsᴇ /sell ᴛᴏ ʟɪsᴛ ʏᴏᴜʀ ᴄʜᴀʀᴀᴄᴛᴇʀs</blockquote>",
            parse_mode="HTML"
        )
        return
    
    text = f"📋 <b>ᴍᴀʀᴋᴇᴛ ʟɪsᴛɪɴɢs</b>\n\n"
    text += f"<blockquote><b>ᴛᴏᴛᴀʟ ʟɪsᴛɪɴɢs:</b> {len(listings)}/100</blockquote>\n\n"
    
    for idx, listing in enumerate(listings[:50], 1):
        char = listing["character"]
        price = listing["price"]
        
        try:
            seller = await context.bot.get_chat(listing["seller_id"])
            seller_name = seller.first_name[:15]
        except:
            seller_name = "Unknown"
        
        text += (
            f"<blockquote expandable>"
            f"<b>{idx}.</b> <code>{char.get('name', 'Unknown')[:20]}</code>\n"
            f"💰 <b>ᴘʀɪᴄᴇ:</b> <code>{price:,}</code> ɢᴏʟᴅ\n"
            f"👤 <b>sᴇʟʟᴇʀ:</b> {seller_name}\n"
            f"🆔 <b>ɪᴅ:</b> <code>{char.get('id', char.get('_id', 'N/A'))}</code>"
            f"</blockquote>\n\n"
        )
        
        if len(text) > 3500:
            await update.message.reply_text(text, parse_mode="HTML")
            text = ""
    
    if text:
        await update.message.reply_text(text, parse_mode="HTML")
    
    if len(listings) > 50:
        await update.message.reply_text(
            f"<blockquote>📊 <b>sʜᴏᴡɪɴɢ:</b> 50/{len(listings)} ʟɪsᴛɪɴɢs\n\n"
            f"💡 ᴜsᴇ /market ᴛᴏ ʙʀᴏᴡsᴇ ᴡɪᴛʜ ɪᴍᴀɢᴇs</blockquote>",
            parse_mode="HTML"
        )

async def render_market_page(message, context, listings, page, user_id, my_listings=False):
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
    final_price = price - fee
    
    time_diff = datetime.utcnow() - listing.get("listed_at", datetime.utcnow())
    hours = int(time_diff.total_seconds() / 3600)
    days = hours // 24
    if days > 0:
        time_str = f"{days}d ago"
    elif hours > 0:
        time_str = f"{hours}h ago"
    else:
        time_str = "just now"
    
    caption = f"{'📦 <b>ʏᴏᴜʀ ʟɪsᴛɪɴɢ</b>' if is_own else '🏪 <b>ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ</b>'}\n\n"
    
    caption += (
        f"<blockquote expandable>"
        f"🎭 <b>ɴᴀᴍᴇ:</b> <code>{char.get('name', 'Unknown')}</code>\n"
        f"📺 <b>ᴀɴɪᴍᴇ:</b> <code>{char.get('anime', 'Unknown')}</code>\n"
        f"💫 <b>ʀᴀʀɪᴛʏ:</b> {char.get('rarity', 'Unknown')}\n"
        f"🆔 <b>ɪᴅ:</b> <code>{char.get('id', char.get('_id', 'N/A'))}</code>"
        f"</blockquote>\n\n"
    )
    
    caption += (
        f"<blockquote>"
        f"💰 <b>ᴘʀɪᴄᴇ:</b> <code>{price:,}</code> ɢᴏʟᴅ\n"
        f"👤 <b>sᴇʟʟᴇʀ:</b> {seller_name}\n"
        f"👁️ <b>ᴠɪᴇᴡs:</b> {listing.get('views', 0):,}\n"
        f"⏰ <b>ʟɪsᴛᴇᴅ:</b> {time_str}"
        f"</blockquote>\n\n"
    )
    
    if is_own:
        caption += (
            f"<blockquote>"
            f"💵 <b>ʏᴏᴜ'ʟʟ ʀᴇᴄᴇɪᴠᴇ:</b> <code>{final_price:,}</code> ɢᴏʟᴅ\n"
            f"📉 <b>ᴍᴀʀᴋᴇᴛ ғᴇᴇ:</b> <code>{fee:,}</code> ({int(MARKET_FEE*100)}%)"
            f"</blockquote>\n\n"
        )
    
    caption += f"📖 <b>ᴘᴀɢᴇ:</b> {page+1}/{len(listings)}"
    
    buttons = []
    
    if is_own:
        buttons.append([InlineKeyboardButton("🗑️ ʀᴇᴍᴏᴠᴇ ʟɪsᴛɪɴɢ", callback_data=f"market_remove_{listing['_id']}")])
    else:
        buttons.append([InlineKeyboardButton("💳 ʙᴜʏ ɴᴏᴡ", callback_data=f"bi_{listing['_id']}")])
    
    if len(listings) > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ ᴘʀᴇᴠ", callback_data=f"market_page_{page-1}"))
        nav.append(InlineKeyboardButton(f"• {page+1}/{len(listings)} •", callback_data="market_pageinfo"))
        if page < len(listings) - 1:
            nav.append(InlineKeyboardButton("ɴᴇxᴛ ➡️", callback_data=f"market_page_{page+1}"))
        buttons.append(nav)
    
    buttons.append([InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="market_refresh")])
    
    markup = InlineKeyboardMarkup(buttons)
    
    try:
        if is_video:
            await message.reply_video(
                video=char.get("img_url"),
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup,
                has_spoiler=True
            )
        else:
            await message.reply_photo(
                photo=char.get("img_url"),
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup,
                has_spoiler=True
            )
    except BadRequest:
        await message.reply_text(f"{caption}\n\n⚠️ <blockquote>ᴍᴇᴅɪᴀ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ</blockquote>", parse_mode="HTML", reply_markup=markup)

async def msales(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    sales = await sell_history.find({"seller_id": user_id}).sort("sold_at", -1).limit(10).to_list(10)
    purchases = await sell_history.find({"buyer_id": user_id}).sort("sold_at", -1).limit(10).to_list(10)
    
    active_listings = await sell_listings.count_documents({"seller_id": user_id})
    
    text = "📊 <b>ᴛʀᴀᴅᴇ ʜɪsᴛᴏʀʏ</b>\n\n"
    
    if sales:
        text += "<blockquote expandable><b>💰 ʀᴇᴄᴇɴᴛ sᴀʟᴇs:</b>\n"
        total_earned = sum(s.get("price", 0) - s.get("fee", 0) for s in sales)
        for idx, s in enumerate(sales[:5], 1):
            net = s.get("price", 0) - s.get("fee", 0)
            text += f"{idx}. <code>{s.get('character_name', 'Unknown')}</code> → <code>{net:,}</code> 💎\n"
        text += f"\n<b>ᴛᴏᴛᴀʟ ᴇᴀʀɴᴇᴅ:</b> <code>{total_earned:,}</code> 💰</blockquote>\n\n"
    
    if purchases:
        text += "<blockquote expandable><b>🛒 ʀᴇᴄᴇɴᴛ ᴘᴜʀᴄʜᴀsᴇs:</b>\n"
        total_spent = sum(p.get("price", 0) for p in purchases)
        for idx, p in enumerate(purchases[:5], 1):
            text += f"{idx}. <code>{p.get('character_name', 'Unknown')}</code> → <code>{p.get('price', 0):,}</code> 💎\n"
        text += f"\n<b>ᴛᴏᴛᴀʟ sᴘᴇɴᴛ:</b> <code>{total_spent:,}</code> 💰</blockquote>\n\n"
    
    text += f"<blockquote><b>📦 ᴀᴄᴛɪᴠᴇ ʟɪsᴛɪɴɢs:</b> {active_listings}/10</blockquote>"
    
    if not sales and not purchases:
        text += "<blockquote>😔 ɴᴏ ᴛʀᴀᴅᴇ ʜɪsᴛᴏʀʏ ʏᴇᴛ\n\n💡 sᴛᴀʀᴛ ᴛʀᴀᴅɪɴɢ ᴡɪᴛʜ /market</blockquote>"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def market_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("market_page_"):
        await query.answer()
        page = int(data.split("_")[2])
        listings = [await sell_listings.find_one({"_id": ObjectId(lid)}) for lid in context.user_data.get('market_listings', [])]
        listings = [l for l in listings if l]
        
        if listings:
            context.user_data['market_page'] = page
            await update_market_display(query, context, listings, page, user_id)
    
    elif data == "market_pageinfo":
        await query.answer("📖 ᴜsᴇ ᴀʀʀᴏᴡs ᴛᴏ ɴᴀᴠɪɢᴀᴛᴇ")
    
    elif data == "market_refresh":
        is_mine = context.user_data.get('viewing_mine', False)
        filter_query = {"seller_id": user_id} if is_mine else {}
        
        listings = await sell_listings.find(filter_query).sort("listed_at", -1).to_list(100)
        if listings:
            context.user_data['market_listings'] = [str(l['_id']) for l in listings]
            context.user_data['market_page'] = 0
            await update_market_display(query, context, listings, 0, user_id)
            await query.answer("🔄 ʀᴇғʀᴇsʜᴇᴅ")
        else:
            await query.answer("😔 ɴᴏ ʟɪsᴛɪɴɢs", show_alert=True)
    
    elif data.startswith("bi_"):
        listing_id = data.replace("bi_", "")
        listing = await sell_listings.find_one({"_id": ObjectId(listing_id)})
        
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
            shortage = price - balance
            await query.answer(
                f"⚠️ ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ\n\n"
                f"💰 ɴᴇᴇᴅ: {price:,} ɢᴏʟᴅ\n"
                f"💵 ʜᴀᴠᴇ: {balance:,} ɢᴏʟᴅ\n"
                f"📉 sʜᴏʀᴛ: {shortage:,} ɢᴏʟᴅ",
                show_alert=True
            )
            return
        
        char = listing["character"]
        
        confirm_text = (
            f"💳 <b>ᴄᴏɴғɪʀᴍ ᴘᴜʀᴄʜᴀsᴇ?</b>\n\n"
            f"<blockquote expandable>"
            f"🎭 <b>ɴᴀᴍᴇ:</b> <code>{char.get('name', 'Unknown')}</code>\n"
            f"📺 <b>ᴀɴɪᴍᴇ:</b> <code>{char.get('anime', 'Unknown')}</code>\n"
            f"💫 <b>ʀᴀʀɪᴛʏ:</b> {char.get('rarity', 'Unknown')}"
            f"</blockquote>\n\n"
            f"<blockquote>"
            f"💰 <b>ᴘʀɪᴄᴇ:</b> <code>{price:,}</code> ɢᴏʟᴅ\n"
            f"💵 <b>ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ:</b> <code>{balance:,}</code> ɢᴏʟᴅ\n"
            f"📊 <b>ᴀғᴛᴇʀ ᴘᴜʀᴄʜᴀsᴇ:</b> <code>{balance - price:,}</code> ɢᴏʟᴅ"
            f"</blockquote>\n\n"
            f"⚠️ ᴄᴏɴғɪʀᴍ ᴛʜɪs ᴛʀᴀɴsᴀᴄᴛɪᴏɴ?"
        )
        
        buttons = [[
            InlineKeyboardButton("✅ ᴄᴏɴғɪʀᴍ ᴘᴜʀᴄʜᴀsᴇ", callback_data=f"cf_{listing['_id']}"),
            InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="market_cancel")
        ]]
        
        try:
            await query.edit_message_caption(
                caption=confirm_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            await query.answer()
        except BadRequest:
            await query.answer()
    
    elif data.startswith("cf_"):
        listing_id = data.replace("cf_", "")
        listing = await sell_listings.find_one({"_id": ObjectId(listing_id)})
        
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
            shortage = price - balance
            await query.answer(
                f"⚠️ ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ\n\n"
                f"💰 ɴᴇᴇᴅ: {price:,} ɢᴏʟᴅ\n"
                f"💵 ʜᴀᴠᴇ: {balance:,} ɢᴏʟᴅ\n"
                f"📉 sʜᴏʀᴛ: {shortage:,} ɢᴏʟᴅ",
                show_alert=True
            )
            return
        
        char = listing["character"]
        
        fee = int(price * MARKET_FEE)
        seller_gets = price - fee
        
        await user_collection.update_one(
            {"id": user_id},
            {"$inc": {"balance": -price}, "$push": {"characters": char}},
            upsert=True
        )
        
        await user_collection.update_one(
            {"id": listing["seller_id"]},
            {"$inc": {"balance": seller_gets}},
            upsert=True
        )
        
        await sell_listings.delete_one({"_id": listing["_id"]})
        
        await sell_history.insert_one({
            "seller_id": listing["seller_id"],
            "buyer_id": user_id,
            "character_name": char.get("name", "Unknown"),
            "character_anime": char.get("anime", "Unknown"),
            "price": price,
            "fee": fee,
            "sold_at": datetime.utcnow()
        })
        
        try:
            await context.bot.send_message(
                listing["seller_id"],
                f"💰 <b>sᴀʟᴇ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
                f"<blockquote expandable>"
                f"🎭 <b>{char.get('name', 'Unknown')}</b>\n"
                f"📺 {char.get('anime', 'Unknown')}\n"
                f"💫 {char.get('rarity', 'Unknown')}"
                f"</blockquote>\n\n"
                f"<blockquote>"
                f"💵 <b>ʏᴏᴜ ʀᴇᴄᴇɪᴠᴇᴅ:</b> <code>{seller_gets:,}</code> ɢᴏʟᴅ\n"
                f"📉 <b>ᴍᴀʀᴋᴇᴛ ғᴇᴇ:</b> <code>{fee:,}</code> ɢᴏʟᴅ ({int(MARKET_FEE*100)}%)\n"
                f"👤 <b>ʙᴜʏᴇʀ:</b> {query.from_user.first_name}"
                f"</blockquote>",
                parse_mode="HTML"
            )
        except:
            pass
        
        success_text = (
            f"✅ <b>ᴘᴜʀᴄʜᴀsᴇ sᴜᴄᴄᴇssғᴜʟ!</b>\n\n"
            f"<blockquote expandable>"
            f"🎭 <b>ɴᴀᴍᴇ:</b> <code>{char.get('name', 'Unknown')}</code>\n"
            f"📺 <b>ᴀɴɪᴍᴇ:</b> <code>{char.get('anime', 'Unknown')}</code>\n"
            f"💫 <b>ʀᴀʀɪᴛʏ:</b> {char.get('rarity', 'Unknown')}\n"
            f"🆔 <b>ɪᴅ:</b> <code>{char.get('id', char.get('_id', 'N/A'))}</code>"
            f"</blockquote>\n\n"
            f"<blockquote>"
            f"💰 <b>ᴘᴀɪᴅ:</b> <code>{price:,}</code> ɢᴏʟᴅ\n"
            f"💵 <b>ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ:</b> <code>{balance - price:,}</code> ɢᴏʟᴅ"
            f"</blockquote>\n\n"
            f"🎉 ᴄʜᴀʀᴀᴄᴛᴇʀ ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ!"
        )
        
        try:
            await query.edit_message_caption(
                caption=success_text,
                parse_mode="HTML"
            )
            await query.answer("✨ ᴘᴜʀᴄʜᴀsᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!")
        except BadRequest:
            await query.answer("✨ ᴘᴜʀᴄʜᴀsᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!")
    
    elif data.startswith("market_remove_"):
        listing_id = data.replace("market_remove_", "")
        listing = await sell_listings.find_one({"_id": ObjectId(listing_id), "seller_id": user_id})
        
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
        
        is_mine = context.user_data.get('viewing_mine', False)
        filter_query = {"seller_id": user_id} if is_mine else {}
        
        listings = await sell_listings.find(filter_query).sort("listed_at", -1).to_list(100)
        if listings:
            context.user_data['market_listings'] = [str(l['_id']) for l in listings]
            context.user_data['market_page'] = 0
            await update_market_display(query, context, listings, 0, user_id)
        else:
            try:
                await query.edit_message_caption(
                    caption="<b>📦 ɴᴏ ᴀᴄᴛɪᴠᴇ ʟɪsᴛɪɴɢs</b>\n\n<blockquote>💡 ᴜsᴇ /sell ᴛᴏ ʟɪsᴛ ᴄʜᴀʀᴀᴄᴛᴇʀs</blockquote>",
                    parse_mode="HTML"
                )
            except:
                pass
    
    elif data == "market_cancel":
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
    final_price = price - fee
    
    time_diff = datetime.utcnow() - listing.get("listed_at", datetime.utcnow())
    hours = int(time_diff.total_seconds() / 3600)
    days = hours // 24
    if days > 0:
        time_str = f"{days}d ago"
    elif hours > 0:
        time_str = f"{hours}h ago"
    else:
        time_str = "just now"
    
    caption = f"{'📦 <b>ʏᴏᴜʀ ʟɪsᴛɪɴɢ</b>' if is_own else '🏪 <b>ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ</b>'}\n\n"
    
    caption += (
        f"<blockquote expandable>"
        f"🎭 <b>ɴᴀᴍᴇ:</b> <code>{char.get('name', 'Unknown')}</code>\n"
        f"📺 <b>ᴀɴɪᴍᴇ:</b> <code>{char.get('anime', 'Unknown')}</code>\n"
        f"💫 <b>ʀᴀʀɪᴛʏ:</b> {char.get('rarity', 'Unknown')}\n"
        f"🆔 <b>ɪᴅ:</b> <code>{char.get('id', char.get('_id', 'N/A'))}</code>"
        f"</blockquote>\n\n"
    )
    
    caption += (
        f"<blockquote>"
        f"💰 <b>ᴘʀɪᴄᴇ:</b> <code>{price:,}</code> ɢᴏʟᴅ\n"
        f"👤 <b>sᴇʟʟᴇʀ:</b> {seller_name}\n"
        f"👁️ <b>ᴠɪᴇᴡs:</b> {listing.get('views', 0):,}\n"
        f"⏰ <b>ʟɪsᴛᴇᴅ:</b> {time_str}"
        f"</blockquote>\n\n"
    )
    
    if is_own:
        caption += (
            f"<blockquote>"
            f"💵 <b>ʏᴏᴜ'ʟʟ ʀᴇᴄᴇɪᴠᴇ:</b> <code>{final_price:,}</code> ɢᴏʟᴅ\n"
            f"📉 <b>ᴍᴀʀᴋᴇᴛ ғᴇᴇ:</b> <code>{fee:,}</code> ({int(MARKET_FEE*100)}%)"
            f"</blockquote>\n\n"
        )
    
    caption += f"📖 <b>ᴘᴀɢᴇ:</b> {page+1}/{len(listings)}"
    
    buttons = []
    
    if is_own:
        buttons.append([InlineKeyboardButton("🗑️ ʀᴇᴍᴏᴠᴇ ʟɪsᴛɪɴɢ", callback_data=f"market_remove_{listing['_id']}")])
    else:
        buttons.append([InlineKeyboardButton("💳 ʙᴜʏ ɴᴏᴡ", callback_data=f"bi_{listing['_id']}")])
    
    if len(listings) > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ ᴘʀᴇᴠ", callback_data=f"market_page_{page-1}"))
        nav.append(InlineKeyboardButton(f"• {page+1}/{len(listings)} •", callback_data="market_pageinfo"))
        if page < len(listings) - 1:
            nav.append(InlineKeyboardButton("ɴᴇxᴛ ➡️", callback_data=f"market_page_{page+1}"))
        buttons.append(nav)
    
    buttons.append([InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="market_refresh")])
    
    markup = InlineKeyboardMarkup(buttons)
    
    try:
        if is_video:
            await query.edit_message_media(
                media=InputMediaVideo(media=char.get("img_url"), caption=caption, parse_mode="HTML", has_spoiler=True),
                reply_markup=markup
            )
        else:
            await query.edit_message_media(
                media=InputMediaPhoto(media=char.get("img_url"), caption=caption, parse_mode="HTML", has_spoiler=True),
                reply_markup=markup
            )
    except BadRequest:
        try:
            await query.edit_message_caption(caption=caption, parse_mode="HTML", reply_markup=markup)
        except:
            pass

application.add_handler(CommandHandler("sell", sell, block=False))
application.add_handler(CommandHandler("unsell", unsell, block=False))
application.add_handler(CommandHandler("market", market, block=False))
application.add_handler(CommandHandler("mymarket", mymarket, block=False))
application.add_handler(CommandHandler("msales", msales, block=False))
application.add_handler(CommandHandler("lists", lists, block=False))
application.add_handler(CallbackQueryHandler(market_callback, pattern=r"^market_", block=False))
application.add_handler(CallbackQueryHandler(market_callback, pattern=r"^bi_", block=False))
application.add_handler(CallbackQueryHandler(market_callback, pattern=r"^cf_", block=False))