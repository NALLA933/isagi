import random
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest

from shivu import application, db, user_collection

collection = db['anime_characters_lol']
shop_collection = db['shop']
shop_history_collection = db['shop_history']
auction_collection = db['auctions']
bid_collection = db['bids']

sudo_users = ["8297659126", "8420981179", "5147822244"]

async def is_sudo_user(user_id: int) -> bool:
    return str(user_id) in sudo_users

async def sadd(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪssɪᴏɴ")
        return
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ /sadd <id> <price> [limit] [discount%] [featured]", parse_mode="HTML")
        return
    
    char_id, price = context.args[0], int(context.args[1])
    limit = None if len(context.args) < 3 or context.args[2].lower() in ["0", "unlimited"] else int(context.args[2])
    discount = max(0, min(int(context.args[3]), 90)) if len(context.args) >= 4 else 0
    featured = len(context.args) >= 5 and context.args[4].lower() in ["yes", "true", "1"]
    
    character = await collection.find_one({"id": char_id})
    if not character or await shop_collection.find_one({"id": char_id}):
        await update.message.reply_text(f"⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ {'not found' if not character else 'already in shop'}")
        return
    
    final_price = int(price * (1 - discount / 100))
    await shop_collection.insert_one({
        "id": char_id, "price": price, "original_price": price, "discount": discount,
        "final_price": final_price, "added_by": user_id, "added_at": datetime.utcnow(),
        "limit": limit, "sold": 0, "featured": featured, "views": 0
    })
    
    await update.message.reply_text(
        f"✨ <b>ᴀᴅᴅᴇᴅ ᴛᴏ sʜᴏᴘ!</b>\n\n🎭 {character['name']}\n"
        f"💎 {price:,} → <b>{final_price:,}</b> ɢᴏʟᴅ\n🔢 ʟɪᴍɪᴛ: {'∞' if not limit else limit}",
        parse_mode="HTML"
    )

async def srm(update: Update, context: CallbackContext):
    if not await is_sudo_user(update.effective_user.id) or len(context.args) < 1:
        return
    
    char_id = context.args[0]
    result = await shop_collection.delete_one({"id": char_id})
    await update.message.reply_text("🗑️ ʀᴇᴍᴏᴠᴇᴅ" if result.deleted_count else "⚠️ ɴᴏᴛ ғᴏᴜɴᴅ")

async def shop(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Check for active auction
    active_auction = await auction_collection.find_one({"status": "active", "end_time": {"$gt": datetime.utcnow()}})
    if active_auction:
        await show_auction(update, context, active_auction)
        return
    
    filter_query = {"discount": {"$gt": 0}} if context.args and context.args[0].lower() == "discount" else {}
    shop_items = await shop_collection.find(filter_query).sort([("featured", -1), ("added_at", -1)]).to_list(None)
    
    if not shop_items:
        await update.message.reply_text(
            "🏪 <b>sʜᴏᴘ ɪs ᴇᴍᴘᴛʏ</b>\n\nᴄʜᴇᴄᴋ ʙᴀᴄᴋ ʟᴀᴛᴇʀ!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="sr_reload")]])
        )
        return
    
    context.user_data['shop_items'] = [item['id'] for item in shop_items]
    context.user_data['shop_page'] = 0
    await render_shop_page(update.message, context, user_id, 0)

def build_caption(character, shop_item, page, total, user_data=None):
    price, final_price = shop_item["price"], shop_item.get("final_price", shop_item["price"])
    discount, sold = shop_item.get("discount", 0), shop_item.get("sold", 0)
    limit, featured = shop_item.get("limit"), shop_item.get("featured", False)
    
    sold_out = limit and sold >= limit
    owned = user_data and any(c.get("id") == character["id"] for c in user_data.get("characters", []))
    
    status = "🚫 sᴏʟᴅ ᴏᴜᴛ" if sold_out else "✅ ᴏᴡɴᴇᴅ" if owned else "⭐ ғᴇᴀᴛᴜʀᴇᴅ" if featured else ""
    
    caption = f"<b>🏪 sʜᴏᴘ {status}</b>\n\n✨ {character['name']}\n🎭 {character.get('anime', 'Unknown')}\n"
    caption += f"💎 <s>{price:,}</s> → <b>{final_price:,}</b> ɢᴏʟᴅ\n🏷️ <b>{discount}%</b> ᴏғғ!\n" if discount > 0 else f"💎 <b>{final_price:,}</b> ɢᴏʟᴅ\n"
    caption += f"🔢 {'∞' if not limit else f'{sold}/{limit}'} | 👁️ {shop_item.get('views', 0):,}\n📖 {page}/{total}"
    
    return caption, character.get("img_url", ""), sold_out or owned, character.get("rarity") == "🎥 AMV"

async def render_shop_page(message, context, user_id, page):
    items = context.user_data.get('shop_items', [])
    if not items or page >= len(items):
        return
    
    char_id = items[page]
    character = await collection.find_one({"id": char_id})
    shop_item = await shop_collection.find_one({"id": char_id})
    user_data = await user_collection.find_one({"id": user_id})
    
    if not character or not shop_item:
        return
    
    await shop_collection.update_one({"id": char_id}, {"$inc": {"views": 1}})
    
    caption, media_url, sold_out, is_video = build_caption(character, shop_item, page + 1, len(items), user_data)
    
    buttons = [[InlineKeyboardButton("💳 ʙᴜʏ" if not sold_out else "🚫 ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ", callback_data=f"sb_{char_id}" if not sold_out else "sna")]]
    
    if len(items) > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"sp_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{len(items)}", callback_data="spi"))
        if page < len(items) - 1:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"sp_{page+1}"))
        buttons.append(nav)
    
    buttons.append([InlineKeyboardButton("🏷️ ᴅɪsᴄᴏᴜɴᴛs", callback_data="ss_discount"), InlineKeyboardButton("🔄", callback_data="sr")])
    
    try:
        func = message.reply_video if is_video else message.reply_photo
        await func(video=media_url if is_video else None, photo=None if is_video else media_url, 
                  caption=caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
    except:
        await message.reply_text(caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

async def shist(update: Update, context: CallbackContext):
    history = await shop_history_collection.find({"user_id": update.effective_user.id}).sort("purchase_date", -1).limit(10).to_list(10)
    
    if not history:
        await update.message.reply_text("📜 <b>ɴᴏ ᴘᴜʀᴄʜᴀsᴇ ʜɪsᴛᴏʀʏ</b>", parse_mode="HTML")
        return
    
    text = "<b>📜 ʏᴏᴜʀ ᴘᴜʀᴄʜᴀsᴇ ʜɪsᴛᴏʀʏ</b>\n\n"
    total = sum(r.get("price", 0) for r in history)
    
    for i, r in enumerate(history, 1):
        char = await collection.find_one({"id": r["character_id"]})
        name = char.get("name", "Unknown") if char else "Unknown"
        text += f"{i}. {name} - {r.get('price', 0):,} ɢᴏʟᴅ\n"
    
    text += f"\n━━━━━━━━━━━━━\n💰 ᴛᴏᴛᴀʟ: {total:,} ɢᴏʟᴅ"
    await update.message.reply_text(text, parse_mode="HTML")

async def astart(update: Update, context: CallbackContext):
    if not await is_sudo_user(update.effective_user.id) or len(context.args) < 3:
        return
    
    char_id, starting_bid, duration_hours = context.args[0], int(context.args[1]), int(context.args[2])
    character = await collection.find_one({"id": char_id})
    
    if not character or await auction_collection.find_one({"status": "active"}):
        await update.message.reply_text("⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ not found or auction active")
        return
    
    end_time = datetime.utcnow() + timedelta(hours=duration_hours)
    await auction_collection.insert_one({
        "character_id": char_id, "starting_bid": starting_bid, "current_bid": starting_bid,
        "highest_bidder": None, "start_time": datetime.utcnow(), "end_time": end_time,
        "status": "active", "created_by": update.effective_user.id, "bid_count": 0
    })
    
    caption = f"<b>🔨 ᴀᴜᴄᴛɪᴏɴ sᴛᴀʀᴛᴇᴅ!</b>\n\n💎 {character['name']}\n💰 {starting_bid:,} ɢᴏʟᴅ\n⏰ {end_time.strftime('%d %b, %H:%M')}\n\nᴜsᴇ /bid [ᴀᴍᴏᴜɴᴛ]"
    buttons = [[InlineKeyboardButton("🔨 ᴠɪᴇᴡ", callback_data="av")]]
    
    func = update.message.reply_video if character.get("rarity") == "🎥 AMV" else update.message.reply_photo
    await func(video=character.get("img_url") if character.get("rarity") == "🎥 AMV" else None,
               photo=character.get("img_url") if character.get("rarity") != "🎥 AMV" else None,
               caption=caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

async def aend(update: Update, context: CallbackContext):
    if not await is_sudo_user(update.effective_user.id):
        return
    
    auction = await auction_collection.find_one({"status": "active"})
    if not auction:
        await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ")
        return
    
    winner_id = auction.get("highest_bidder")
    character = await collection.find_one({"id": auction["character_id"]})
    
    if winner_id:
        await user_collection.update_one({"id": winner_id}, {"$inc": {"balance": -auction["current_bid"]}, "$push": {"characters": character}})
        await update.message.reply_text(f"<b>🎊 ᴡɪɴɴᴇʀ:</b> <a href='tg://user?id={winner_id}'>User</a>\n💰 {auction['current_bid']:,}", parse_mode="HTML")
    else:
        await update.message.reply_text("⚠️ ɴᴏ ʙɪᴅs")
    
    await auction_collection.update_one({"_id": auction["_id"]}, {"$set": {"status": "ended"}})

async def bid(update: Update, context: CallbackContext):
    if not context.args:
        return
    
    user_id, bid_amount = update.effective_user.id, int(context.args[0])
    auction = await auction_collection.find_one({"status": "active"})
    
    if not auction:
        await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ")
        return
    
    min_bid = int(auction["current_bid"] * 1.05)
    user_data = await user_collection.find_one({"id": user_id})
    balance = user_data.get("balance", 0) if user_data else 0
    
    if bid_amount < min_bid or balance < bid_amount:
        await update.message.reply_text(f"⚠️ ᴍɪɴ: {min_bid:,} | ʙᴀʟ: {balance:,}")
        return
    
    await auction_collection.update_one({"_id": auction["_id"]}, {"$set": {"current_bid": bid_amount, "highest_bidder": user_id}, "$inc": {"bid_count": 1}})
    await bid_collection.insert_one({"auction_id": auction["_id"], "user_id": user_id, "amount": bid_amount, "timestamp": datetime.utcnow()})
    await update.message.reply_text(f"✅ ʙɪᴅ: {bid_amount:,} ɢᴏʟᴅ", parse_mode="HTML")

async def show_auction(update, context, auction):
    character = await collection.find_one({"id": auction["character_id"]})
    time_left = auction["end_time"] - datetime.utcnow()
    
    caption = f"<b>🔨 ᴀᴜᴄᴛɪᴏɴ</b>\n\n💎 {character['name']}\n💰 {auction['current_bid']:,}\n⏰ {int(time_left.total_seconds()/3600)}h {int(time_left.total_seconds()%3600/60)}m"
    buttons = [[InlineKeyboardButton("🔨 ᴠɪᴇᴡ", callback_data="av")]]
    
    await update.message.reply_photo(photo=character.get("img_url"), caption=caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

async def shop_callback(update, context):
    query = update.callback_query
    await query.answer()
    data, user_id = query.data, query.from_user.id
    
    if data.startswith("sp_"):
        await render_shop_page_edit(query, context, user_id, int(data.split("_")[1]))
    elif data == "sr":
        await render_shop_page_edit(query, context, user_id, context.user_data.get('shop_page', 0))
    elif data.startswith("sb_"):
        await handle_buy(query, context, user_id, data.split("_", 1)[1])

async def render_shop_page_edit(query, context, user_id, page):
    items = context.user_data.get('shop_items', [])
    char_id = items[page]
    character = await collection.find_one({"id": char_id})
    shop_item = await shop_collection.find_one({"id": char_id})
    user_data = await user_collection.find_one({"id": user_id})
    
    caption, media_url, sold_out, is_video = build_caption(character, shop_item, page + 1, len(items), user_data)
    buttons = [[InlineKeyboardButton("💳 ʙᴜʏ" if not sold_out else "🚫", callback_data=f"sb_{char_id}" if not sold_out else "sna")]]
    
    try:
        await query.edit_message_caption(caption=caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
    except:
        pass

async def handle_buy(query, context, user_id, char_id):
    shop_item = await shop_collection.find_one({"id": char_id})
    character = await collection.find_one({"id": char_id})
    user_data = await user_collection.find_one({"id": user_id})
    
    price = shop_item.get("final_price", shop_item["price"])
    balance = user_data.get("balance", 0) if user_data else 0
    
    if balance < price:
        await query.answer(f"⚠️ ɴᴇᴇᴅ {price:,}", show_alert=True)
        return
    
    await user_collection.update_one({"id": user_id}, {"$inc": {"balance": -price}, "$push": {"characters": character}}, upsert=True)
    await shop_collection.update_one({"id": char_id}, {"$inc": {"sold": 1}})
    await shop_history_collection.insert_one({"user_id": user_id, "character_id": char_id, "price": price, "purchase_date": datetime.utcnow()})
    await query.answer("✨ ᴘᴜʀᴄʜᴀsᴇᴅ!")

application.add_handler(CommandHandler("shop", shop, block=False))
application.add_handler(CommandHandler("sadd", sadd, block=False))
application.add_handler(CommandHandler("srm", srm, block=False))
application.add_handler(CommandHandler("shist", shist, block=False))
application.add_handler(CommandHandler("astart", astart, block=False))
application.add_handler(CommandHandler("aend", aend, block=False))
application.add_handler(CommandHandler("bid", bid, block=False))
application.add_handler(CallbackQueryHandler(shop_callback, pattern=r"^s", block=False))