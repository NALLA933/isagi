import random
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler

from shivu import application, db, user_collection, CHARA_CHANNEL_ID, SUPPORT_CHAT

collection = db['anime_characters_lol']
shop_collection = db['shop']
characters_collection = collection
shop_history_collection = db['shop_history']
giveaway_collection = db['giveaways']
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
    try:
        char_id = context.args[0]
        price = int(context.args[1])
        limit = None
        discount = 0
        featured = False
        if len(context.args) >= 3:
            limit_arg = context.args[2].lower()
            if limit_arg not in ["0", "unlimited", "infinity"]:
                limit = int(context.args[2])
                if limit <= 0:
                    limit = None
        if len(context.args) >= 4:
            discount = max(0, min(int(context.args[3]), 90))
        if len(context.args) >= 5:
            featured = context.args[4].lower() in ["yes", "true", "1", "featured"]
        if price <= 0:
            await update.message.reply_text("⚠️ ᴘʀɪᴄᴇ ᴍᴜsᴛ ʙᴇ > 0")
            return
        character = await characters_collection.find_one({"id": char_id})
        if not character:
            await update.message.reply_text(f"⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ {char_id} ɴᴏᴛ ғᴏᴜɴᴅ")
            return
        existing = await shop_collection.find_one({"id": char_id})
        if existing:
            await update.message.reply_text(f"⚠️ {character['name']} ᴀʟʀᴇᴀᴅʏ ɪɴ sʜᴏᴘ", parse_mode="HTML")
            return
        final_price = int(price * (1 - discount / 100)) if discount > 0 else price
        shop_item = {
            "id": char_id,
            "price": price,
            "original_price": price,
            "discount": discount,
            "final_price": final_price,
            "added_by": user_id,
            "added_at": datetime.utcnow(),
            "limit": limit,
            "sold": 0,
            "featured": featured,
            "views": 0
        }
        await shop_collection.insert_one(shop_item)
        limit_text = "∞" if limit is None else str(limit)
        await update.message.reply_text(
            f"✨ <b>{character['name']}</b> ᴀᴅᴅᴇᴅ\n"
            f"💎 {price:,} → {final_price:,} ɢᴏʟᴅ\n"
            f"🔢 ʟɪᴍɪᴛ: {limit_text}",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ {str(e)}")

async def srm(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪssɪᴏɴ")
        return
    if len(context.args) < 1:
        await update.message.reply_text("⚠️ /srm <id>")
        return
    try:
        char_id = context.args[0]
        shop_item = await shop_collection.find_one({"id": char_id})
        if not shop_item:
            await update.message.reply_text(f"⚠️ {char_id} ɴᴏᴛ ɪɴ sʜᴏᴘ")
            return
        character = await characters_collection.find_one({"id": char_id})
        char_name = character['name'] if character else char_id
        await shop_collection.delete_one({"id": char_id})
        await update.message.reply_text(f"✨ <b>{char_name}</b> ʀᴇᴍᴏᴠᴇᴅ", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"⚠️ {str(e)}")

async def shop(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    active_auction = await auction_collection.find_one({"status": "active", "end_time": {"$gt": datetime.utcnow()}})
    if active_auction:
        await show_auction_shop(update, context, active_auction)
        return
    sort_by = [("featured", -1), ("added_at", -1)]
    filter_query = {}
    if context.args:
        arg = context.args[0].lower()
        if arg == "cheap":
            sort_by = [("final_price", 1)]
        elif arg == "expensive":
            sort_by = [("final_price", -1)]
        elif arg == "discount":
            filter_query["discount"] = {"$gt": 0}
            sort_by = [("discount", -1)]
        elif arg == "featured":
            filter_query["featured"] = True
    shop_items = await shop_collection.find(filter_query).sort(sort_by).to_list(length=None)
    if not shop_items:
        await update.message.reply_text("🏪 sʜᴏᴘ ᴇᴍᴘᴛʏ", parse_mode="HTML")
        return
    page = 0
    context.user_data['shop_items'] = [item['id'] for item in shop_items]
    context.user_data['shop_page'] = page
    char_id = shop_items[page]['id']
    character = await characters_collection.find_one({"id": char_id})
    user_data = await user_collection.find_one({"id": user_id})
    await shop_collection.update_one({"id": char_id}, {"$inc": {"views": 1}})
    caption, media_url, sold_out, is_video = build_caption(character, shop_items[page], page + 1, len(shop_items), user_data)
    buttons = []
    if not sold_out:
        buttons.append([InlineKeyboardButton("💳 ʙᴜʏ", callback_data=f"sb_{char_id}")])
    if len(shop_items) > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"sp_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{len(shop_items)}", callback_data="spi"))
        if page < len(shop_items) - 1:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"sp_{page+1}"))
        buttons.append(nav)
    buttons.append([
        InlineKeyboardButton("⭐", callback_data="ss_featured"),
        InlineKeyboardButton("💰", callback_data="ss_cheap"),
        InlineKeyboardButton("💎", callback_data="ss_expensive"),
        InlineKeyboardButton("🏷️", callback_data="ss_discount")
    ])
    markup = InlineKeyboardMarkup(buttons)
    if is_video:
        await update.message.reply_video(video=media_url, caption=caption, parse_mode="HTML", reply_markup=markup)
    else:
        await update.message.reply_photo(photo=media_url, caption=caption, parse_mode="HTML", reply_markup=markup)

def build_caption(waifu, shop_item, page, total, user_data=None):
    wid = waifu.get("id", waifu.get("_id"))
    name = waifu.get("name", "Unknown")
    anime = waifu.get("anime", "Unknown")
    rarity = waifu.get("rarity", "Unknown")
    price = shop_item.get("price", 0)
    final_price = shop_item.get("final_price", price)
    discount = shop_item.get("discount", 0)
    img_url = waifu.get("img_url", "")
    limit = shop_item.get("limit", None)
    sold = shop_item.get("sold", 0)
    featured = shop_item.get("featured", False)
    views = shop_item.get("views", 0)
    is_video = rarity == "🎥 AMV"
    limit_text = "∞" if limit is None else f"{sold}/{limit}"
    sold_out = limit is not None and sold >= limit
    already_bought = False
    if user_data:
        user_chars = user_data.get("characters", [])
        already_bought = any((c.get("id") == wid or c.get("_id") == wid) for c in user_chars)
    status = ""
    if sold_out:
        status = "🚫 sᴏʟᴅ ᴏᴜᴛ"
    elif already_bought:
        status = "✅ ᴏᴡɴᴇᴅ"
    elif featured:
        status = "⭐"
    caption = f"<b>🏪 sʜᴏᴘ {status}</b>\n\n✨ <b>{name}</b>\n🎭 {anime}\n💫 {rarity}\n"
    if discount > 0 and not sold_out and not already_bought:
        caption += f"💎 <s>{price:,}</s> → <b>{final_price:,}</b>\n🏷️ {discount}% ᴏғғ\n"
    else:
        caption += f"💎 <b>{final_price:,}</b> ɢᴏʟᴅ\n"
    caption += f"🔢 {limit_text} | 👁️ {views:,}\n📖 {page}/{total}"
    return caption, img_url, sold_out or already_bought, is_video

async def shist(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    history = await shop_history_collection.find({"user_id": user_id}).sort("purchase_date", -1).limit(10).to_list(length=10)
    if not history:
        await update.message.reply_text("📜 ɴᴏ ᴘᴜʀᴄʜᴀsᴇs", parse_mode="HTML")
        return
    text = "<b>📜 ᴘᴜʀᴄʜᴀsᴇ ʜɪsᴛᴏʀʏ</b>\n\n"
    total = 0
    for i, r in enumerate(history, 1):
        character = await characters_collection.find_one({"id": r["character_id"]})
        name = character.get("name", "Unknown") if character else "Unknown"
        price = r.get("price", 0)
        date = r.get("purchase_date", datetime.utcnow()).strftime("%d %b")
        total += price
        text += f"{i}. <b>{name}</b> - {price:,}💰 ({date})\n"
    text += f"\n💰 <b>ᴛᴏᴛᴀʟ:</b> {total:,}"
    await update.message.reply_text(text, parse_mode="HTML")

async def gstart(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪssɪᴏɴ")
        return
    if len(context.args) < 3:
        await update.message.reply_text("⚠️ /gstart <id> <hours> <min_chars>")
        return
    try:
        char_id = context.args[0]
        duration_hours = int(context.args[1])
        min_activity = int(context.args[2])
        character = await characters_collection.find_one({"id": char_id})
        if not character:
            await update.message.reply_text(f"⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ {char_id} ɴᴏᴛ ғᴏᴜɴᴅ")
            return
        active = await giveaway_collection.find_one({"status": "active"})
        if active:
            await update.message.reply_text("⚠️ ɢɪᴠᴇᴀᴡᴀʏ ᴀʟʀᴇᴀᴅʏ ᴀᴄᴛɪᴠᴇ")
            return
        end_time = datetime.utcnow() + timedelta(hours=duration_hours)
        giveaway = {
            "character_id": char_id,
            "start_time": datetime.utcnow(),
            "end_time": end_time,
            "min_activity": min_activity,
            "participants": [],
            "status": "active",
            "created_by": user_id,
            "winner": None
        }
        await giveaway_collection.insert_one(giveaway)
        img_url = character.get("img_url", "")
        caption = (
            f"<b>🎉 ɢɪᴠᴇᴀᴡᴀʏ</b>\n\n"
            f"🎁 <b>{character['name']}</b>\n"
            f"🎭 {character.get('anime', 'Unknown')}\n"
            f"⏰ {end_time.strftime('%d %b, %H:%M UTC')}\n"
            f"📊 ᴍɪɴ: {min_activity} ᴄʜᴀʀs\n"
            f"👥 0 ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs"
        )
        buttons = [[InlineKeyboardButton("🎫 ᴊᴏɪɴ", callback_data="gj")]]
        markup = InlineKeyboardMarkup(buttons)
        if character.get("rarity") == "🎥 AMV":
            await update.message.reply_video(video=img_url, caption=caption, parse_mode="HTML", reply_markup=markup)
        else:
            await update.message.reply_photo(photo=img_url, caption=caption, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        await update.message.reply_text(f"⚠️ {str(e)}")

async def gend(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪssɪᴏɴ")
        return
    giveaway = await giveaway_collection.find_one({"status": "active"})
    if not giveaway:
        await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢɪᴠᴇᴀᴡᴀʏ")
        return
    participants = giveaway.get("participants", [])
    if not participants:
        await giveaway_collection.update_one({"_id": giveaway["_id"]}, {"$set": {"status": "ended"}})
        await update.message.reply_text("⚠️ ɴᴏ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs")
        return
    winner_id = random.choice(participants)
    character = await characters_collection.find_one({"id": giveaway["character_id"]})
    await user_collection.update_one({"id": winner_id}, {"$push": {"characters": character}}, upsert=True)
    await giveaway_collection.update_one({"_id": giveaway["_id"]}, {"$set": {"status": "ended", "winner": winner_id}})
    try:
        winner_user = await context.bot.get_chat(winner_id)
        winner_name = winner_user.first_name
    except:
        winner_name = f"User {winner_id}"
    await update.message.reply_text(
        f"<b>🎊 ɢɪᴠᴇᴀᴡᴀʏ ᴇɴᴅᴇᴅ</b>\n\n"
        f"🎁 <b>{character['name']}</b>\n"
        f"🏆 <a href='tg://user?id={winner_id}'>{winner_name}</a>\n"
        f"👥 {len(participants)} ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs",
        parse_mode="HTML"
    )

async def astart(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪssɪᴏɴ")
        return
    if len(context.args) < 3:
        await update.message.reply_text("⚠️ /astart <id> <start_bid> <hours>")
        return
    try:
        char_id = context.args[0]
        starting_bid = int(context.args[1])
        duration_hours = int(context.args[2])
        character = await characters_collection.find_one({"id": char_id})
        if not character:
            await update.message.reply_text(f"⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ {char_id} ɴᴏᴛ ғᴏᴜɴᴅ")
            return
        active = await auction_collection.find_one({"status": "active"})
        if active:
            await update.message.reply_text("⚠️ ᴀᴜᴄᴛɪᴏɴ ᴀʟʀᴇᴀᴅʏ ᴀᴄᴛɪᴠᴇ")
            return
        end_time = datetime.utcnow() + timedelta(hours=duration_hours)
        auction = {
            "character_id": char_id,
            "starting_bid": starting_bid,
            "current_bid": starting_bid,
            "highest_bidder": None,
            "start_time": datetime.utcnow(),
            "end_time": end_time,
            "status": "active",
            "created_by": user_id,
            "bid_count": 0
        }
        await auction_collection.insert_one(auction)
        img_url = character.get("img_url", "")
        caption = (
            f"<b>🔨 ᴀᴜᴄᴛɪᴏɴ sᴛᴀʀᴛᴇᴅ</b>\n\n"
            f"💎 <b>{character['name']}</b>\n"
            f"🎭 {character.get('anime', 'Unknown')}\n"
            f"💰 sᴛᴀʀᴛ: {starting_bid:,}💰\n"
            f"🏆 ᴄᴜʀʀᴇɴᴛ: {starting_bid:,}💰\n"
            f"⏰ {end_time.strftime('%d %b, %H:%M UTC')}\n\n"
            f"ᴜsᴇ /bid <amount>"
        )
        buttons = [[InlineKeyboardButton("🔨 ᴠɪᴇᴡ", callback_data="av")]]
        markup = InlineKeyboardMarkup(buttons)
        if character.get("rarity") == "🎥 AMV":
            await update.message.reply_video(video=img_url, caption=caption, parse_mode="HTML", reply_markup=markup)
        else:
            await update.message.reply_photo(photo=img_url, caption=caption, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        await update.message.reply_text(f"⚠️ {str(e)}")

async def aend(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪssɪᴏɴ")
        return
    auction = await auction_collection.find_one({"status": "active"})
    if not auction:
        await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ")
        return
    highest_bidder = auction.get("highest_bidder")
    character = await characters_collection.find_one({"id": auction["character_id"]})
    if highest_bidder:
        final_bid = auction.get("current_bid")
        await user_collection.update_one({"id": highest_bidder}, {"$inc": {"balance": -final_bid}, "$push": {"characters": character}})
        try:
            winner_user = await context.bot.get_chat(highest_bidder)
            winner_name = winner_user.first_name
        except:
            winner_name = f"User {highest_bidder}"
        await update.message.reply_text(
            f"<b>🎊 ᴀᴜᴄᴛɪᴏɴ ᴇɴᴅᴇᴅ</b>\n\n"
            f"💎 <b>{character['name']}</b>\n"
            f"🏆 <a href='tg://user?id={highest_bidder}'>{winner_name}</a>\n"
            f"💰 {final_bid:,}💰",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("⚠️ ɴᴏ ʙɪᴅs")
    await auction_collection.update_one({"_id": auction["_id"]}, {"$set": {"status": "ended"}})

async def bid(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("⚠️ /bid <amount>")
        return
    try:
        bid_amount = int(context.args[0])
        auction = await auction_collection.find_one({"status": "active"})
        if not auction:
            await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ")
            return
        current_bid = auction.get("current_bid")
        min_bid = int(current_bid * 1.05)
        if bid_amount < min_bid:
            await update.message.reply_text(f"⚠️ ᴍɪɴ ʙɪᴅ: {min_bid:,}💰")
            return
        user_data = await user_collection.find_one({"id": user_id})
        balance = user_data.get("balance", 0) if user_data else 0
        if balance < bid_amount:
            await update.message.reply_text(f"⚠️ ɪɴsᴜғғɪᴄɪᴇɴᴛ: {balance:,}💰")
            return
        await auction_collection.update_one({"_id": auction["_id"]}, {"$set": {"current_bid": bid_amount, "highest_bidder": user_id}, "$inc": {"bid_count": 1}})
        await bid_collection.insert_one({"auction_id": auction["_id"], "user_id": user_id, "amount": bid_amount, "timestamp": datetime.utcnow()})
        character = await characters_collection.find_one({"id": auction["character_id"]})
        await update.message.reply_text(f"✅ <b>{character['name']}</b>\n💰 {bid_amount:,}💰\n\nɢᴏᴏᴅ ʟᴜᴄᴋ! 🍀", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"⚠️ {str(e)}")

async def show_auction_shop(update, context, auction):
    user_id = update.effective_user.id
    char_id = auction["character_id"]
    character = await characters_collection.find_one({"id": char_id})
    if not character:
        await update.message.reply_text("⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ")
        return
    end_time = auction.get("end_time")
    time_left = end_time - datetime.utcnow()
    hours_left = int(time_left.total_seconds() / 3600)
    minutes_left = int((time_left.total_seconds() % 3600) / 60)
    highest_bidder = auction.get("highest_bidder")
    bidder_text = "ɴᴏɴᴇ"
    if highest_bidder:
        try:
            bidder_user = await context.bot.get_chat(highest_bidder)
            bidder_text = bidder_user.first_name
        except:
            bidder_text = f"User {highest_bidder}"
    img_url = character.get("img_url", "")
    is_video = character.get("rarity") == "🎥 AMV"
    caption = (
        f"<b>🔨 ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ</b>\n\n"
        f"💎 <b>{character['name']}</b>\n"
        f"🎭 {character.get('anime', 'Unknown')}\n\n"
        f"💰 <b>{auction['current_bid']:,}</b>💰\n"
        f"👤 {bidder_text}\n"
        f"⏰ {hours_left}h {minutes_left}m\n"
        f"📊 {auction['bid_count']} ʙɪᴅs\n\n"
        f"/bid <amount>"
    )
    buttons = [[InlineKeyboardButton(f"+{auction['current_bid']//10:,}", callback_data=f"ab_{auction['current_bid']//10}"), InlineKeyboardButton(f"+{auction['current_bid']//5:,}", callback_data=f"ab_{auction['current_bid']//5}")]]
    markup = InlineKeyboardMarkup(buttons)
    if is_video:
        await update.message.reply_video(video=img_url, caption=caption, parse_mode="HTML", reply_markup=markup)
    else:
        await update.message.reply_photo(photo=img_url, caption=caption, parse_mode="HTML", reply_markup=markup)

async def shop_callback(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    async def render_page(page):
        items = context.user_data.get('shop_items', [])
        if not items or page >= len(items):
            return
        context.user_data['shop_page'] = page
        char_id = items[page]
        character = await characters_collection.find_one({"id": char_id})
        shop_item = await shop_collection.find_one({"id": char_id})
        user_data = await user_collection.find_one({"id": user_id})
        if not character or not shop_item:
            return
        await shop_collection.update_one({"id": char_id}, {"$inc": {"views": 1}})
        caption, media_url, sold_out, is_video = build_caption(character, shop_item, page + 1, len(items), user_data)
        buttons = []
        if not sold_out:
            buttons.append([InlineKeyboardButton("💳 ʙᴜʏ", callback_data=f"sb_{char_id}")])
        if len(items) > 1:
            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton("◀️", callback_data=f"sp_{page-1}"))
            nav.append(InlineKeyboardButton(f"{page+1}/{len(items)}", callback_data="spi"))
            if page < len(items) - 1:
                nav.append(InlineKeyboardButton("▶️", callback_data=f"sp_{page+1}"))
            buttons.append(nav)
        buttons.append([
            InlineKeyboardButton("⭐", callback_data="ss_featured"),
            InlineKeyboardButton("💰", callback_data="ss_cheap"),
            InlineKeyboardButton("💎", callback_data="ss_expensive"),
            InlineKeyboardButton("🏷️", callback_data="ss_discount")
        ])
        markup = InlineKeyboardMarkup(buttons)
        try:
            if is_video:
                await query.edit_message_media(media=InputMediaVideo(media=media_url, caption=caption, parse_mode="HTML"), reply_markup=markup)
            else:
                await query.edit_message_media(media=InputMediaPhoto(media=media_url, caption=caption, parse_mode="HTML"), reply_markup=markup)
        except:
            try:
                await query.edit_message_caption(caption=caption, parse_mode="HTML", reply_markup=markup)
            except:
                pass
    
    if data.startswith("sp_"):
        page = int(data.split("_")[1])
        await render_page(page)
    
    elif data == "spi":
        pass
    
    elif data.startswith("ss_"):
        sort_type = data.split("_")[1]
        sort_by = [("featured", -1), ("added_at", -1)]
        filter_query = {}
        if sort_type == "cheap":
            sort_by = [("final_price", 1)]
        elif sort_type == "expensive":
            sort_by = [("final_price", -1)]
        elif sort_type == "discount":
            filter_query["discount"] = {"$gt": 0}
            sort_by = [("discount", -1)]
        elif sort_type == "featured":
            filter_query["featured"] = True
        shop_items = await shop_collection.find(filter_query).sort(sort_by).to_list(length=None)
        if shop_items:
            context.user_data['shop_items'] = [item['id'] for item in shop_items]
            context.user_data['shop_page'] = 0
            await render_page(0)
    
    elif data.startswith("sb_"):
        char_id = data.split("_", 1)[1]
        shop_item = await shop_collection.find_one({"id": char_id})
        character = await characters_collection.find_one({"id": char_id})
        user_data = await user_collection.find_one({"id": user_id})
        if not shop_item or not character:
            await query.answer("⚠️ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        limit = shop_item.get("limit")
        sold = shop_item.get("sold", 0)
        user_chars = user_data.get("characters", []) if user_data else []
        already_bought = any((c.get("id") == char_id or c.get("_id") == char_id) for c in user_chars)
        if (limit and sold >= limit) or already_bought:
            await query.answer("⚠️ sᴏʟᴅ ᴏᴜᴛ", show_alert=True)
            return
        price = shop_item.get("final_price", shop_item.get("price", 0))
        discount = shop_item.get("discount", 0)
        discount_text = ""
        if discount > 0:
            discount_text = f"🏷️ {discount}% ᴏғғ\n"
        buttons = [[InlineKeyboardButton("✅ ᴄᴏɴғɪʀᴍ", callback_data=f"sc_{char_id}"), InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="sx")]]
        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_caption(
            caption=f"<b>💳 ᴄᴏɴғɪʀᴍ</b>\n\n✨ <b>{character['name']}</b>\n🎭 {character.get('anime', 'Unknown')}\n\n{discount_text}💰 <b>{price:,}</b> ɢᴏʟᴅ",
            parse_mode="HTML",
            reply_markup=markup
        )
    
    elif data.startswith("sc_"):
        char_id = data.split("_", 1)[1]
        shop_item = await shop_collection.find_one({"id": char_id})
        character = await characters_collection.find_one({"id": char_id})
        user_data = await user_collection.find_one({"id": user_id})
        if not shop_item or not character:
            await query.answer("⚠️ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        limit = shop_item.get("limit")
        sold = shop_item.get("sold", 0)
        user_chars = user_data.get("characters", []) if user_data else []
        already_bought = any((c.get("id") == char_id or c.get("_id") == char_id) for c in user_chars)
        if (limit and sold >= limit) or already_bought:
            await query.answer("⚠️ sᴏʟᴅ ᴏᴜᴛ", show_alert=True)
            return
        price = shop_item.get("final_price", shop_item.get("price", 0))
        balance = user_data.get("balance", 0) if user_data else 0
        if balance < price:
            await query.answer(f"⚠️ ɴᴇᴇᴅ {price:,}💰", show_alert=True)
            return
        await user_collection.update_one({"id": user_id}, {"$inc": {"balance": -price}, "$push": {"characters": character}}, upsert=True)
        await shop_collection.update_one({"id": char_id}, {"$inc": {"sold": 1}})
        await shop_history_collection.insert_one({"user_id": user_id, "character_id": char_id, "price": price, "purchase_date": datetime.utcnow()})
        await query.edit_message_caption(
            caption=f"<b>✨ sᴜᴄᴄᴇss!</b>\n\n<b>{character['name']}</b>\n💰 {price:,}💰\n\n💵 {balance - price:,}💰 ʟᴇғᴛ",
            parse_mode="HTML"
        )
        await query.answer("✨ ᴘᴜʀᴄʜᴀsᴇᴅ!", show_alert=False)
    
    elif data == "sx":
        page = context.user_data.get('shop_page', 0)
        await render_page(page)
        await query.answer("ᴄᴀɴᴄᴇʟʟᴇᴅ")

async def giveaway_callback(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if data == "gj":
        giveaway = await giveaway_collection.find_one({"status": "active"})
        if not giveaway:
            await query.answer("⚠️ ᴇɴᴅᴇᴅ", show_alert=True)
            return
        user_data = await user_collection.find_one({"id": user_id})
        if not user_data:
            await query.answer("⚠️ sᴛᴀʀᴛ ᴘʟᴀʏɪɴɢ ғɪʀsᴛ", show_alert=True)
            return
        user_chars = user_data.get("characters", [])
        if len(user_chars) < giveaway.get("min_activity", 0):
            await query.answer(f"⚠️ ɴᴇᴇᴅ {giveaway['min_activity']} ᴄʜᴀʀs", show_alert=True)
            return
        if user_id in giveaway.get("participants", []):
            await query.answer("⚠️ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ", show_alert=True)
            return
        await giveaway_collection.update_one({"_id": giveaway["_id"]}, {"$push": {"participants": user_id}})
        participants_count = len(giveaway.get("participants", [])) + 1
        character = await characters_collection.find_one({"id": giveaway["character_id"]})
        end_time = giveaway.get("end_time")
        caption = (
            f"<b>🎉 ɢɪᴠᴇᴀᴡᴀʏ</b>\n\n"
            f"🎁 <b>{character['name']}</b>\n"
            f"🎭 {character.get('anime', 'Unknown')}\n"
            f"⏰ {end_time.strftime('%d %b, %H:%M UTC')}\n"
            f"📊 ᴍɪɴ: {giveaway['min_activity']} ᴄʜᴀʀs\n"
            f"👥 {participants_count} ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs"
        )
        buttons = [[InlineKeyboardButton("🎫 ᴊᴏɪɴ", callback_data="gj")]]
        markup = InlineKeyboardMarkup(buttons)
        try:
            await query.edit_message_caption(caption=caption, parse_mode="HTML", reply_markup=markup)
        except:
            pass
        await query.answer("✅ ᴊᴏɪɴᴇᴅ!")

async def auction_callback(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if data == "av":
        auction = await auction_collection.find_one({"status": "active"})
        if not auction:
            await query.answer("⚠️ ᴇɴᴅᴇᴅ", show_alert=True)
            return
        character = await characters_collection.find_one({"id": auction["character_id"]})
        end_time = auction.get("end_time")
        time_left = end_time - datetime.utcnow()
        hours_left = int(time_left.total_seconds() / 3600)
        minutes_left = int((time_left.total_seconds() % 3600) / 60)
        highest_bidder = auction.get("highest_bidder")
        bidder_text = "ɴᴏɴᴇ"
        if highest_bidder:
            try:
                bidder_user = await context.bot.get_chat(highest_bidder)
                bidder_text = bidder_user.first_name
            except:
                bidder_text = f"User {highest_bidder}"
        caption = (
            f"<b>🔨 ᴀᴜᴄᴛɪᴏɴ</b>\n\n"
            f"💎 <b>{character['name']}</b>\n\n"
            f"💰 <b>{auction['current_bid']:,}</b>💰\n"
            f"👤 {bidder_text}\n"
            f"⏰ {hours_left}h {minutes_left}m\n"
            f"📊 {auction['bid_count']} ʙɪᴅs\n\n"
            f"/bid <amount>"
        )
        try:
            await query.edit_message_caption(caption=caption, parse_mode="HTML")
        except:
            pass
    
    elif data.startswith("ab_"):
        increment = int(data.split("_")[1])
        auction = await auction_collection.find_one({"status": "active"})
        if not auction:
            await query.answer("⚠️ ᴇɴᴅᴇᴅ", show_alert=True)
            return
        bid_amount = auction.get("current_bid") + increment
        user_data = await user_collection.find_one({"id": user_id})
        balance = user_data.get("balance", 0) if user_data else 0
        if balance < bid_amount:
            await query.answer(f"⚠️ ɴᴇᴇᴅ {bid_amount:,}💰", show_alert=True)
            return
        await auction_collection.update_one({"_id": auction["_id"]}, {"$set": {"current_bid": bid_amount, "highest_bidder": user_id}, "$inc": {"bid_count": 1}})
        await bid_collection.insert_one({"auction_id": auction["_id"], "user_id": user_id, "amount": bid_amount, "timestamp": datetime.utcnow()})
        await query.answer(f"✅ ʙɪᴅ: {bid_amount:,}💰")

application.add_handler(CommandHandler("shop", shop, block=False))
application.add_handler(CommandHandler("sadd", sadd, block=False))
application.add_handler(CommandHandler("srm", srm, block=False))
application.add_handler(CommandHandler("shist", shist, block=False))
application.add_handler(CommandHandler("gstart", gstart, block=False))
application.add_handler(CommandHandler("gend", gend, block=False))
application.add_handler(CommandHandler("astart", astart, block=False))
application.add_handler(CommandHandler("aend", aend, block=False))
application.add_handler(CommandHandler("bid", bid, block=False))
application.add_handler(CallbackQueryHandler(shop_callback, pattern=r"^s", block=False))
application.add_handler(CallbackQueryHandler(giveaway_callback, pattern=r"^g", block=False))
application.add_handler(CallbackQueryHandler(auction_callback, pattern=r"^a", block=False))