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
            "⚠️ <blockquote><b>ᴜsᴀɢᴇ:</b> /sell &lt;character_id&gt; &lt;price&gt;</blockquote>\n\n<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>/sell 12345 5000</code>",
            parse_mode="HTML"
        )
        return
    
    try:
        char_id = context.args[0]
        price = int(context.args[1])
        
        if price <= 0:
            await update.message.reply_text("⚠️ <blockquote>ᴘʀɪᴄᴇ ᴍᴜsᴛ ʙᴇ ɢʀᴇᴀᴛᴇʀ ᴛʜᴀɴ 0</blockquote>", parse_mode="HTML")
            return
        
        user_data = await user_collection.find_one({"id": user_id})
        if not user_data:
            await update.message.reply_text("⚠️ <blockquote>ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ғᴏᴜɴᴅ</blockquote>", parse_mode="HTML")
            return
        
        char_to_sell = next((c for c in user_data.get("characters", []) if str(c.get("id", c.get("_id"))) == char_id), None)
        
        if not char_to_sell:
            await update.message.reply_text(f"⚠️ <blockquote>ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴄʜᴀʀᴀᴄᴛᴇʀ <code>{char_id}</code></blockquote>", parse_mode="HTML")
            return
        
        if await sell_listings.find_one({"seller_id": user_id, "character.id": char_to_sell.get("id", char_to_sell.get("_id"))}):
            await update.message.reply_text("⚠️ <blockquote><b>ᴀʟʀᴇᴀᴅʏ ʟɪsᴛᴇᴅ!</b>\n\nᴜsᴇ /unsell ᴛᴏ ʀᴇᴍᴏᴠᴇ ɪᴛ ғɪʀsᴛ</blockquote>", parse_mode="HTML")
            return
        
        await sell_listings.insert_one({
            "seller_id": user_id,
            "character": char_to_sell,
            "price": price,
            "listed_at": datetime.utcnow(),
            "views": 0
        })
        
        await user_collection.update_one({"id": user_id}, {"$pull": {"characters": char_to_sell}})
        
        await update.message.reply_text(
            f"<blockquote><b>✨ ʟɪsᴛᴇᴅ ғᴏʀ sᴀʟᴇ!</b></blockquote>\n\n🎭 <b>{char_to_sell.get('name', 'Unknown')}</b>\n📺 {char_to_sell.get('anime', 'Unknown')}\n💫 {char_to_sell.get('rarity', 'Unknown')}\n💰 <b>{price:,}</b> ɢᴏʟᴅ\n\n<i>ᴜsᴇ /market ᴛᴏ ᴠɪᴇᴡ ʏᴏᴜʀ ʟɪsᴛɪɴɢ</i>",
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("⚠️ <blockquote>ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ғᴏʀᴍᴀᴛ</blockquote>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"⚠️ <blockquote>ᴇʀʀᴏʀ: {str(e)}</blockquote>", parse_mode="HTML")

async def unsell(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "⚠️ <blockquote><b>ᴜsᴀɢᴇ:</b> /unsell &lt;character_id&gt;</blockquote>\n\n<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>/unsell 12345</code>",
            parse_mode="HTML"
        )
        return
    
    try:
        listing = await sell_listings.find_one({"seller_id": user_id, "character.id": context.args[0]})
        
        if not listing:
            await update.message.reply_text(f"⚠️ <blockquote>ɴᴏ ʟɪsᴛɪɴɢ ғᴏᴜɴᴅ ғᴏʀ <code>{context.args[0]}</code></blockquote>", parse_mode="HTML")
            return
        
        await user_collection.update_one({"id": user_id}, {"$push": {"characters": listing["character"]}}, upsert=True)
        await sell_listings.delete_one({"_id": listing["_id"]})
        
        await update.message.reply_text(
            f"<blockquote><b>🔙 ʀᴇᴍᴏᴠᴇᴅ ғʀᴏᴍ ᴍᴀʀᴋᴇᴛ</b></blockquote>\n\n✨ <b>{listing['character'].get('name', 'Unknown')}</b> ʀᴇᴛᴜʀɴᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ <blockquote>ᴇʀʀᴏʀ: {str(e)}</blockquote>", parse_mode="HTML")

async def market(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    filter_query = {}
    sort_by = [("listed_at", -1)]
    
    if context.args:
        arg = context.args[0].lower()
        if arg == "mine":
            filter_query["seller_id"] = user_id
        elif arg in ["cheap", "expensive"]:
            sort_by = [("price", 1 if arg == "cheap" else -1)]
    
    listings = await sell_listings.find(filter_query).sort(sort_by).to_list(length=None)
    
    if not listings:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="mr")]])
        await update.message.reply_text(
            "<blockquote><b>🏪 ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ ᴇᴍᴘᴛʏ</b></blockquote>\n\n😔 ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴀᴠᴀɪʟᴀʙʟᴇ\n\n<b>💡 ᴛɪᴘs:</b>\n• ᴜsᴇ /sell ᴛᴏ ʟɪsᴛ ʏᴏᴜʀ ᴄʜᴀʀᴀᴄᴛᴇʀs\n• /market mine - ʏᴏᴜʀ ʟɪsᴛɪɴɢs\n• /market cheap - ʙᴇsᴛ ᴅᴇᴀʟs",
            parse_mode="HTML",
            reply_markup=markup
        )
        return
    
    context.user_data['market_listings'] = [str(l['_id']) for l in listings]
    context.user_data['market_page'] = 0
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
    
    caption = (
        f"<blockquote><b>🏪 ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ {'(ʏᴏᴜʀ ʟɪsᴛɪɴɢ)' if is_own else ''}</b></blockquote>\n\n"
        f"✨ <b>{char.get('name', 'Unknown')}</b>\n"
        f"🎭 {char.get('anime', 'Unknown')}\n"
        f"💫 {char.get('rarity', 'Unknown')}\n"
        f"💰 <b>{price:,}</b> ɢᴏʟᴅ\n"
        f"👤 sᴇʟʟᴇʀ: {seller_name}\n"
        f"👁️ {listing.get('views', 0):,} ᴠɪᴇᴡs\n"
        f"📖 ᴘᴀɢᴇ {page+1}/{len(listings)}"
    )
    
    buttons = [[InlineKeyboardButton(
        "🗑️ ʀᴇᴍᴏᴠᴇ ʟɪsᴛɪɴɢ" if is_own else "💳 ʙᴜʏ ɴᴏᴡ",
        callback_data=f"mu_{listing['_id']}" if is_own else f"mb_{listing['_id']}"
    )]]
    
    if len(listings) > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"mp_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{len(listings)}", callback_data="mpi"))
        if page < len(listings) - 1:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"mp_{page+1}"))
        buttons.append(nav)
    
    buttons.append([
        InlineKeyboardButton("💰", callback_data="mf_cheap"),
        InlineKeyboardButton("💎", callback_data="mf_expensive"),
        InlineKeyboardButton("🔄", callback_data="mr")
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
    sales = await sell_history.find({"seller_id": user_id}).sort("sold_at", -1).limit(10).to_list(10)
    purchases = await sell_history.find({"buyer_id": user_id}).sort("sold_at", -1).limit(10).to_list(10)
    
    text = "<blockquote><b>📊 ʏᴏᴜʀ ᴛʀᴀᴅᴇ ʜɪsᴛᴏʀʏ</b></blockquote>\n\n"
    
    if sales:
        text += "<b>💰 sᴀʟᴇs:</b>\n"
        total = sum(s.get("price", 0) for s in sales)
        for s in sales:
            text += f"• {s.get('character_name', 'Unknown')} - {s.get('price', 0):,} 💎\n"
        text += f"<b>ᴛᴏᴛᴀʟ ᴇᴀʀɴᴇᴅ:</b> {total:,} 💰\n\n"
    
    if purchases:
        text += "<b>🛒 ᴘᴜʀᴄʜᴀsᴇs:</b>\n"
        total = sum(p.get("price", 0) for p in purchases)
        for p in purchases:
            text += f"• {p.get('character_name', 'Unknown')} - {p.get('price', 0):,} 💎\n"
        text += f"<b>ᴛᴏᴛᴀʟ sᴘᴇɴᴛ:</b> {total:,} 💰"
    
    if not sales and not purchases:
        text += "😔 ɴᴏ ᴛʀᴀᴅᴇ ʜɪsᴛᴏʀʏ ʏᴇᴛ"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def market_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("mp_"):
        page = int(data.split("_")[1])
        listings = [await sell_listings.find_one({"_id": ObjectId(lid)}) for lid in context.user_data.get('market_listings', [])]
        listings = [l for l in listings if l]
        
        if listings:
            context.user_data['market_page'] = page
            await update_market_display(query, context, listings, page, user_id)
        else:
            await query.answer("⚠️ ɴᴏ ʟɪsᴛɪɴɢs")
    
    elif data == "mpi":
        await query.answer("📖 ᴜsᴇ ᴀʀʀᴏᴡs ᴛᴏ ɴᴀᴠɪɢᴀᴛᴇ")
    
    elif data == "mr":
        listings = await sell_listings.find({}).sort([("listed_at", -1)]).to_list(None)
        if listings:
            context.user_data['market_listings'] = [str(l['_id']) for l in listings]
            context.user_data['market_page'] = 0
            await update_market_display(query, context, listings, 0, user_id)
            await query.answer("🔄 ʀᴇғʀᴇsʜᴇᴅ")
        else:
            await query.answer("😔 ᴍᴀʀᴋᴇᴛ ᴇᴍᴘᴛʏ", show_alert=True)
    
    elif data.startswith("mf_"):
        sort_type = data.split("_")[1]
        sort_by = [("price", 1 if sort_type == "cheap" else -1)]
        listings = await sell_listings.find({}).sort(sort_by).to_list(None)
        
        if listings:
            context.user_data['market_listings'] = [str(l['_id']) for l in listings]
            context.user_data['market_page'] = 0
            await update_market_display(query, context, listings, 0, user_id)
            await query.answer(f"{'💰 ᴄʜᴇᴀᴘᴇsᴛ' if sort_by[0][1] == 1 else '💎 ᴍᴏsᴛ ᴇxᴘᴇɴsɪᴠᴇ'} ғɪʀsᴛ")
        else:
            await query.answer("😔 ɴᴏ ʟɪsᴛɪɴɢs", show_alert=True)
    
    elif data.startswith("mb_"):
        listing = await sell_listings.find_one({"_id": ObjectId(data.split("_", 1)[1])})
        
        if not listing:
            await query.answer("⚠️ ʟɪsᴛɪɴɢ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        if listing["seller_id"] == user_id:
            await query.answer("⚠️ ᴄᴀɴ'ᴛ ʙᴜʏ ʏᴏᴜʀ ᴏᴡɴ", show_alert=True)
            return
        
        user_data = await user_collection.find_one({"id": user_id})
        balance = user_data.get("balance", 0) if user_data else 0
        price = listing["price"]
        
        if balance < price:
            await query.answer(f"⚠️ ɴᴇᴇᴅ {price:,} ɢᴏʟᴅ!\nʏᴏᴜ ʜᴀᴠᴇ {balance:,}", show_alert=True)
            return
        
        buttons = [[
            InlineKeyboardButton("✅ ᴄᴏɴғɪʀᴍ", callback_data=f"mc_{listing['_id']}"),
            InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="mx")
        ]]
        
        try:
            await query.edit_message_caption(
                caption=(
                    f"<blockquote><b>💳 ᴄᴏɴғɪʀᴍ ᴘᴜʀᴄʜᴀsᴇ</b></blockquote>\n\n"
                    f"✨ <b>{listing['character'].get('name', 'Unknown')}</b>\n"
                    f"💰 ᴘʀɪᴄᴇ: <b>{price:,}</b> ɢᴏʟᴅ\n\n"
                    f"💵 ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ: {balance:,}\n"
                    f"📉 ᴀғᴛᴇʀ: {balance - price:,}"
                ),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except BadRequest:
            pass
    
    elif data.startswith("mc_"):
        listing = await sell_listings.find_one({"_id": ObjectId(data.split("_", 1)[1])})
        
        if not listing:
            await query.answer("⚠️ ʟɪsᴛɪɴɢ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        user_data = await user_collection.find_one({"id": user_id})
        balance = user_data.get("balance", 0) if user_data else 0
        price = listing["price"]
        
        if balance < price:
            await query.answer("⚠️ ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ", show_alert=True)
            return
        
        char = listing["character"]
        
        await user_collection.update_one(
            {"id": user_id},
            {"$inc": {"balance": -price}, "$push": {"characters": char}},
            upsert=True
        )
        await user_collection.update_one({"id": listing["seller_id"]}, {"$inc": {"balance": price}}, upsert=True)
        await sell_listings.delete_one({"_id": listing["_id"]})
        
        await sell_history.insert_one({
            "seller_id": listing["seller_id"],
            "buyer_id": user_id,
            "character_name": char.get("name", "Unknown"),
            "price": price,
            "sold_at": datetime.utcnow()
        })
        
        try:
            await context.bot.send_message(
                listing["seller_id"],
                f"<blockquote><b>💰 sᴀʟᴇ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b></blockquote>\n\n✨ <b>{char.get('name', 'Unknown')}</b> sᴏʟᴅ ғᴏʀ <b>{price:,}</b> ɢᴏʟᴅ",
                parse_mode="HTML"
            )
        except:
            pass
        
        try:
            await query.edit_message_caption(
                caption=(
                    f"<blockquote><b>✅ ᴘᴜʀᴄʜᴀsᴇ sᴜᴄᴄᴇssғᴜʟ!</b></blockquote>\n\n"
                    f"🎉 <b>{char.get('name', 'Unknown')}</b>\n"
                    f"💰 ᴘᴀɪᴅ: {price:,} ɢᴏʟᴅ\n"
                    f"💵 ʀᴇᴍᴀɪɴɪɴɢ: {balance - price:,} ɢᴏʟᴅ"
                ),
                parse_mode="HTML"
            )
        except BadRequest:
            pass
        
        await query.answer("✨ ᴘᴜʀᴄʜᴀsᴇᴅ!")
    
    elif data.startswith("mu_"):
        listing = await sell_listings.find_one({"_id": ObjectId(data.split("_", 1)[1]), "seller_id": user_id})
        
        if not listing:
            await query.answer("⚠️ ʟɪsᴛɪɴɢ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        await user_collection.update_one({"id": user_id}, {"$push": {"characters": listing["character"]}}, upsert=True)
        await sell_listings.delete_one({"_id": listing["_id"]})
        await query.answer("🔙 ʀᴇᴍᴏᴠᴇᴅ ғʀᴏᴍ ᴍᴀʀᴋᴇᴛ")
        
        listings = await sell_listings.find({}).sort([("listed_at", -1)]).to_list(None)
        if listings:
            context.user_data['market_listings'] = [str(l['_id']) for l in listings]
            context.user_data['market_page'] = 0
            await update_market_display(query, context, listings, 0, user_id)
        else:
            try:
                await query.edit_message_caption(
                    caption="<blockquote><b>🏪 ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ ᴇᴍᴘᴛʏ</b></blockquote>\n\nɴᴏ ʟɪsᴛɪɴɢs ᴀᴠᴀɪʟᴀʙʟᴇ",
                    parse_mode="HTML"
                )
            except:
                pass
    
    elif data == "mx":
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
    
    caption = (
        f"<blockquote><b>🏪 ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ {'(ʏᴏᴜʀ ʟɪsᴛɪɴɢ)' if is_own else ''}</b></blockquote>\n\n"
        f"✨ <b>{char.get('name', 'Unknown')}</b>\n"
        f"🎭 {char.get('anime', 'Unknown')}\n"
        f"💫 {char.get('rarity', 'Unknown')}\n"
        f"💰 <b>{price:,}</b> ɢᴏʟᴅ\n"
        f"👤 sᴇʟʟᴇʀ: {seller_name}\n"
        f"👁️ {listing.get('views', 0):,} ᴠɪᴇᴡs\n"
        f"📖 ᴘᴀɢᴇ {page+1}/{len(listings)}"
    )
    
    buttons = [[InlineKeyboardButton(
        "🗑️ ʀᴇᴍᴏᴠᴇ ʟɪsᴛɪɴɢ" if is_own else "💳 ʙᴜʏ ɴᴏᴡ",
        callback_data=f"mu_{listing['_id']}" if is_own else f"mb_{listing['_id']}"
    )]]
    
    if len(listings) > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"mp_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{len(listings)}", callback_data="mpi"))
        if page < len(listings) - 1:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"mp_{page+1}"))
        buttons.append(nav)
    
    buttons.append([
        InlineKeyboardButton("💰", callback_data="mf_cheap"),
        InlineKeyboardButton("💎", callback_data="mf_expensive"),
        InlineKeyboardButton("🔄", callback_data="mr")
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

application.add_handler(CommandHandler("sell", sell, block=False))
application.add_handler(CommandHandler("unsell", unsell, block=False))
application.add_handler(CommandHandler("market", market, block=False))
application.add_handler(CommandHandler("msales", msales, block=False))
application.add_handler(CallbackQueryHandler(market_callback, pattern=r"^m", block=False))