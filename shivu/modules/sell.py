from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest
from datetime import datetime
from bson import ObjectId
from shivu import application, db, user_collection

collection = db['anime_characters_lol']
sell_listings = db['sell_listings']
sell_history = db['sell_history']

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
        
        user_data = await user_collection.find_one({"id": user_id})
        if not user_data:
            await update.message.reply_text("⚠️ ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ғᴏᴜɴᴅ")
            return
        
        user_chars = user_data.get("characters", [])
        char_to_sell = None
        char_index = None
        
        for idx, c in enumerate(user_chars):
            if str(c.get("id", c.get("_id"))) == char_id:
                char_to_sell = c
                char_index = idx
                break
        
        if not char_to_sell:
            await update.message.reply_text(f"⚠️ ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴄʜᴀʀᴀᴄᴛᴇʀ <code>{char_id}</code>", parse_mode="HTML")
            return
        
        existing = await sell_listings.find_one({"seller_id": user_id, "character.id": char_to_sell.get("id", char_to_sell.get("_id"))})
        if existing:
            await update.message.reply_text("⚠️ <b>ᴀʟʀᴇᴀᴅʏ ʟɪsᴛᴇᴅ!</b>\n\nᴜsᴇ /unsell ᴛᴏ ʀᴇᴍᴏᴠᴇ ɪᴛ ғɪʀsᴛ", parse_mode="HTML")
            return
        
        listing = {
            "seller_id": user_id,
            "character": char_to_sell,
            "price": price,
            "listed_at": datetime.utcnow(),
            "views": 0
        }
        
        await sell_listings.insert_one(listing)
        await user_collection.update_one({"id": user_id}, {"$pull": {"characters": char_to_sell}})
        
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
        listing = await sell_listings.find_one({"seller_id": user_id, "character.id": char_id})
        
        if not listing:
            await update.message.reply_text(f"⚠️ ɴᴏ ʟɪsᴛɪɴɢ ғᴏᴜɴᴅ ғᴏʀ <code>{char_id}</code>", parse_mode="HTML")
            return
        
        character = listing["character"]
        await user_collection.update_one({"id": user_id}, {"$push": {"characters": character}}, upsert=True)
        await sell_listings.delete_one({"_id": listing["_id"]})
        
        name = character.get("name", "Unknown")
        await update.message.reply_text(
            f"<b>🔙 ʀᴇᴍᴏᴠᴇᴅ ғʀᴏᴍ ᴍᴀʀᴋᴇᴛ</b>\n\n"
            f"✨ <b>{name}</b> ʀᴇᴛᴜʀɴᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

async def market(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    filter_query = {}
    sort_by = [("listed_at", -1)]
    
    if context.args:
        arg = context.args[0].lower()
        if arg == "mine":
            filter_query["seller_id"] = user_id
        elif arg == "cheap":
            sort_by = [("price", 1)]
        elif arg == "expensive":
            sort_by = [("price", -1)]
    
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
    
    page = 0
    context.user_data['market_listings'] = [str(l['_id']) for l in listings]
    context.user_data['market_page'] = page
    
    await render_market_page(update.message, context, listings, page, user_id)

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
    
    buttons = []
    
    if is_own:
        buttons.append([InlineKeyboardButton("🗑️ ʀᴇᴍᴏᴠᴇ ʟɪsᴛɪɴɢ", callback_data=f"mu_{listing['_id']}")])
    else:
        buttons.append([InlineKeyboardButton("💳 ʙᴜʏ ɴᴏᴡ", callback_data=f"mb_{listing['_id']}")])
    
    if len(listings) > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️ ᴘʀᴇᴠ", callback_data=f"mp_{page-1}"))
        nav.append(InlineKeyboardButton(f"• {page+1}/{len(listings)} •", callback_data="mpi"))
        if page < len(listings) - 1:
            nav.append(InlineKeyboardButton("ɴᴇxᴛ ▶️", callback_data=f"mp_{page+1}"))
        buttons.append(nav)
    
    buttons.append([
        InlineKeyboardButton("💰 ᴄʜᴇᴀᴘ", callback_data="mf_cheap"),
        InlineKeyboardButton("💎 ᴇxᴘᴇɴsɪᴠᴇ", callback_data="mf_expensive"),
        InlineKeyboardButton("🔄", callback_data="mr")
    ])
    
    markup = InlineKeyboardMarkup(buttons)
    
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
            await query.edit_message_caption(caption=caption, parse_mode="HTML", reply_markup=markup)
        except:
            pass

# Register handlers
application.add_handler(CommandHandler("sell", sell, block=False))
application.add_handler(CommandHandler("unsell", unsell, block=False))
application.add_handler(CommandHandler("market", market, block=False))
application.add_handler(CommandHandler("msales", msales, block=False))
application.add_handler(CallbackQueryHandler(market_callback, pattern=r"^m", block=False))
    if len(listings) > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️ ᴘʀᴇᴠ", callback_data=f"mp_{page-1}"))
        nav.append(InlineKeyboardButton(f"• {page+1}/{len(listings)} •", callback_data="mpi"))
        if page < len(listings) - 1:
            nav.append(InlineKeyboardButton("ɴᴇxᴛ ▶️", callback_data=f"mp_{page+1}"))
        buttons.append(nav)
    
    buttons.append([
        InlineKeyboardButton("💰 ᴄʜᴇᴀᴘ", callback_data="mf_cheap"),
        InlineKeyboardButton("💎 ᴇxᴘᴇɴsɪᴠᴇ", callback_data="mf_expensive"),
        InlineKeyboardButton("🔄", callback_data="mr")
    ])
    
    markup = InlineKeyboardMarkup(buttons)
    
    try:
        if is_video:
            await message.reply_video(video=img_url, caption=caption, parse_mode="HTML", reply_markup=markup)
        else:
            await message.reply_photo(photo=img_url, caption=caption, parse_mode="HTML", reply_markup=markup)
    except BadRequest:
        await message.reply_text(f"{caption}\n\n⚠️ ᴍᴇᴅɪᴀ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ", parse_mode="HTML", reply_markup=markup)

async def msales(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    sales = await sell_history.find({"seller_id": user_id}).sort("sold_at", -1).limit(10).to_list(length=10)
    purchases = await sell_history.find({"buyer_id": user_id}).sort("sold_at", -1).limit(10).to_list(length=10)
    
    text = "<b>📊 ʏᴏᴜʀ ᴛʀᴀᴅᴇ ʜɪsᴛᴏʀʏ</b>\n\n"
    
    if sales:
        text += "<b>💰 sᴀʟᴇs:</b>\n"
        total_earned = 0
        for s in sales:
            name = s.get("character_name", "Unknown")
            price = s.get("price", 0)
            total_earned += price
            text += f"• {name} - {price:,} 💎\n"
        text += f"<b>ᴛᴏᴛᴀʟ ᴇᴀʀɴᴇᴅ:</b> {total_earned:,} 💰\n\n"
    
    if purchases:
        text += "<b>🛒 ᴘᴜʀᴄʜᴀsᴇs:</b>\n"
        total_spent = 0
        for p in purchases:
            name = p.get("character_name", "Unknown")
            price = p.get("price", 0)
            total_spent += price
            text += f"• {name} - {price:,} 💎\n"
        text += f"<b>ᴛᴏᴛᴀʟ sᴘᴇɴᴛ:</b> {total_spent:,} 💰"
    
    if not sales and not purchases:
        text += "😔 ɴᴏ ᴛʀᴀᴅᴇ ʜɪsᴛᴏʀʏ ʏᴇᴛ"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def market_callback(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("mp_"):
        page = int(data.split("_")[1])
        listing_ids = context.user_data.get('market_listings', [])
        
        listings = []
        for lid in listing_ids:
            l = await sell_listings.find_one({"_id": ObjectId(lid)})
            if l:
                listings.append(l)
        
        if not listings:
            await query.answer("⚠️ ɴᴏ ʟɪsᴛɪɴɢs")
            return
        
        context.user_data['market_page'] = page
        await update_market_display(query, context, listings, page, user_id)
    
    elif data == "mpi":
        await query.answer("📖 ᴜsᴇ ᴀʀʀᴏᴡs ᴛᴏ ɴᴀᴠɪɢᴀᴛᴇ")
    
    elif data == "mr":
        listings = await sell_listings.find({}).sort([("listed_at", -1)]).to_list(length=None)
        if listings:
            context.user_data['market_listings'] = [str(l['_id']) for l in listings]
            context.user_data['market_page'] = 0
            await update_market_display(query, context, listings, 0, user_id)
            await query.answer("🔄 ʀᴇғʀᴇsʜᴇᴅ")
        else:
            await query.answer("😔 ᴍᴀʀᴋᴇᴛ ᴇᴍᴘᴛʏ", show_alert=True)
    
    elif data.startswith("mf_"):
        filter_type = data.split("_")[1]
        sort_by = [("price", 1)] if filter_type == "cheap" else [("price", -1)]
        
        listings = await sell_listings.find({}).sort(sort_by).to_list(length=None)
        if listings:
            context.user_data['market_listings'] = [str(l['_id']) for l in listings]
            context.user_data['market_page'] = 0
            await update_market_display(query, context, listings, 0, user_id)
            await query.answer(f"{'💰 ᴄʜᴇᴀᴘᴇsᴛ' if filter_type == 'cheap' else '💎 ᴍᴏsᴛ ᴇxᴘᴇɴsɪᴠᴇ'} ғɪʀsᴛ")
        else:
            await query.answer("😔 ɴᴏ ʟɪsᴛɪɴɢs", show_alert=True)
    
    elif data.startswith("mb_"):
        listing_id = ObjectId(data.split("_", 1)[1])
        listing = await sell_listings.find_one({"_id": listing_id})
        
        if not listing:
            await query.answer("⚠️ ʟɪsᴛɪɴɢ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        seller_id = listing["seller_id"]
        if seller_id == user_id:
            await query.answer("⚠️ ᴄᴀɴ'ᴛ ʙᴜʏ ʏᴏᴜʀ ᴏᴡɴ", show_alert=True)
            return
        
        price = listing["price"]
        char = listing["character"]
        
        user_data = await user_collection.find_one({"id": user_id})
        balance = user_data.get("balance", 0) if user_data else 0
        
        if balance < price:
            await query.answer(f"⚠️ ɴᴇᴇᴅ {price:,} ɢᴏʟᴅ!\nʏᴏᴜ ʜᴀᴠᴇ {balance:,}", show_alert=True)
            return
        
        name = char.get("name", "Unknown")
        
        buttons = [
            [
                InlineKeyboardButton("✅ ᴄᴏɴғɪʀᴍ", callback_data=f"mc_{listing_id}"),
                InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="mx")
            ]
        ]
        markup = InlineKeyboardMarkup(buttons)
        
        try:
            await query.edit_message_caption(
                caption=(
                    f"<b>💳 ᴄᴏɴғɪʀᴍ ᴘᴜʀᴄʜᴀsᴇ</b>\n\n"
                    f"✨ <b>{name}</b>\n"
                    f"💰 ᴘʀɪᴄᴇ: <b>{price:,}</b> ɢᴏʟᴅ\n\n"
                    f"💵 ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ: {balance:,}\n"
                    f"📉 ᴀғᴛᴇʀ: {balance - price:,}"
                ),
                parse_mode="HTML",
                reply_markup=markup
            )
        except BadRequest:
            pass
    
    elif data.startswith("mc_"):
        listing_id = ObjectId(data.split("_", 1)[1])
        listing = await sell_listings.find_one({"_id": listing_id})
        
        if not listing:
            await query.answer("⚠️ ʟɪsᴛɪɴɢ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        seller_id = listing["seller_id"]
        price = listing["price"]
        char = listing["character"]
        
        user_data = await user_collection.find_one({"id": user_id})
        balance = user_data.get("balance", 0) if user_data else 0
        
        if balance < price:
            await query.answer("⚠️ ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ", show_alert=True)
            return
        
        await user_collection.update_one({"id": user_id}, {"$inc": {"balance": -price}, "$push": {"characters": char}}, upsert=True)
        await user_collection.update_one({"id": seller_id}, {"$inc": {"balance": price}}, upsert=True)
        await sell_listings.delete_one({"_id": listing_id})
        
        await sell_history.insert_one({
            "seller_id": seller_id,
            "buyer_id": user_id,
            "character_name": char.get("name", "Unknown"),
            "price": price,
            "sold_at": datetime.utcnow()
        })
        
        name = char.get("name", "Unknown")
        
        try:
            await context.bot.send_message(
                seller_id,
                f"<b>💰 sᴀʟᴇ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
                f"✨ <b>{name}</b> sᴏʟᴅ ғᴏʀ <b>{price:,}</b> ɢᴏʟᴅ",
                parse_mode="HTML"
            )
        except:
            pass
        
        try:
            await query.edit_message_caption(
                caption=(
                    f"<b>✅ ᴘᴜʀᴄʜᴀsᴇ sᴜᴄᴄᴇssғᴜʟ!</b>\n\n"
                    f"🎉 <b>{name}</b>\n"
                    f"💰 ᴘᴀɪᴅ: {price:,} ɢᴏʟᴅ\n"
                    f"💵 ʀᴇᴍᴀɪɴɪɴɢ: {balance - price:,} ɢᴏʟᴅ"
                ),
                parse_mode="HTML"
            )
        except BadRequest:
            pass
        
        await query.answer("✨ ᴘᴜʀᴄʜᴀsᴇᴅ!")
    
    elif data.startswith("mu_"):
        listing_id = ObjectId(data.split("_", 1)[1])
        listing = await sell_listings.find_one({"_id": listing_id, "seller_id": user_id})
        
        if not listing:
            await query.answer("⚠️ ʟɪsᴛɪɴɢ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        char = listing["character"]
        await user_collection.update_one({"id": user_id}, {"$push": {"characters": char}}, upsert=True)
        await sell_listings.delete_one({"_id": listing_id})
        
        await query.answer("🔙 ʀᴇᴍᴏᴠᴇᴅ ғʀᴏᴍ ᴍᴀʀᴋᴇᴛ")
        
        listings = await sell_listings.find({}).sort([("listed_at", -1)]).to_list(length=None)
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
    
    elif data == "mx":
        page = context.user_data.get('market_page', 0)
        listing_ids = context.user_data.get('market_listings', [])
        
        listings = []
        for lid in listing_ids:
            l = await sell_listings.find_one({"_id": ObjectId(lid)})
            if l:
                listings.append(l)
        
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
    
    buttons = []
    
    if is_own:
        buttons.append([InlineKeyboardButton("🗑️ ʀᴇᴍᴏᴠᴇ ʟɪsᴛɪɴɢ", callback_data=f"mu_{listing['_id']}")])
    else:
        buttons.append([InlineKeyboardButton("💳 ʙᴜʏ ɴᴏᴡ", callback_data=f"mb_{listing['_id']}")])