import random
from datetime import datetime, timedelta
import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from shivu import application, db, user_collection, CHARA_CHANNEL_ID, SUPPORT_CHAT

collection = db['anime_characters_lol']
shop_collection = db['shop']
characters_collection = collection
shop_history_collection = db['shop_history']
giveaway_collection = db['giveaways']
auction_collection = db['auctions']
bid_collection = db['bids']

sudo_users = ["8297659126", "8420981179", "5147822244"]

# Initialize scheduler for auto-ending giveaways
scheduler = AsyncIOScheduler(timezone='Asia/Kolkata')
scheduler.start()

# Kolkata timezone
IST = pytz.timezone('Asia/Kolkata')

def get_ist_time():
    """Get current time in IST"""
    return datetime.now(IST)

def to_ist(utc_time):
    """Convert UTC datetime to IST"""
    if utc_time.tzinfo is None:
        utc_time = pytz.utc.localize(utc_time)
    return utc_time.astimezone(IST)

def to_utc(ist_time):
    """Convert IST datetime to UTC"""
    if ist_time.tzinfo is None:
        ist_time = IST.localize(ist_time)
    return ist_time.astimezone(pytz.utc).replace(tzinfo=None)

async def is_sudo_user(user_id: int) -> bool:
    return str(user_id) in sudo_users

async def auto_end_giveaway(giveaway_id, context):
    """Automatically end giveaway and select winner"""
    try:
        giveaway = await giveaway_collection.find_one({"_id": giveaway_id, "status": "active"})
        if not giveaway:
            return
        
        participants = giveaway.get("participants", [])
        character = await characters_collection.find_one({"id": giveaway["character_id"]})
        
        if not participants:
            await giveaway_collection.update_one(
                {"_id": giveaway_id},
                {"$set": {"status": "ended", "end_reason": "no_participants"}}
            )
            return
        
        # Select random winner
        winner_id = random.choice(participants)
        
        # Give character to winner
        await user_collection.update_one(
            {"id": winner_id},
            {"$push": {"characters": character}},
            upsert=True
        )
        
        # Update giveaway status
        await giveaway_collection.update_one(
            {"_id": giveaway_id},
            {
                "$set": {
                    "status": "ended",
                    "winner": winner_id,
                    "end_reason": "completed",
                    "actual_end_time": datetime.utcnow()
                }
            }
        )
        
        # Try to get winner's name
        try:
            winner_user = await context.bot.get_chat(winner_id)
            winner_name = winner_user.first_name
        except:
            winner_name = f"User {winner_id}"
        
        # Announce winner
        announcement = (
            f"<b>🎊 ɢɪᴠᴇᴀᴡᴀʏ ᴇɴᴅᴇᴅ!</b>\n\n"
            f"🎁 <b>{character['name']}</b>\n"
            f"🎭 {character.get('anime', 'Unknown')}\n"
            f"💫 {character.get('rarity', 'Unknown')}\n\n"
            f"🏆 ᴡɪɴɴᴇʀ: <a href='tg://user?id={winner_id}'>{winner_name}</a>\n"
            f"👥 ᴛᴏᴛᴀʟ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs: {len(participants)}\n"
            f"⏰ ᴇɴᴅᴇᴅ ᴀᴛ: {get_ist_time().strftime('%d %b %Y, %I:%M %p IST')}\n\n"
            f"ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs! 🎉"
        )
        
        # Send announcement to support chat if available
        try:
            if SUPPORT_CHAT:
                await context.bot.send_message(
                    chat_id=SUPPORT_CHAT,
                    text=announcement,
                    parse_mode="HTML"
                )
        except:
            pass
            
    except Exception as e:
        print(f"Error auto-ending giveaway: {e}")

async def sadd(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴀᴅᴅ ɪᴛᴇᴍs")
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b> /sadd &lt;id&gt; &lt;price&gt; [limit] [discount%] [featured]\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇs:</b>\n"
            "• /sadd CHAR001 5000\n"
            "• /sadd CHAR002 10000 50 20 yes\n"
            "• /sadd CHAR003 8000 unlimited 10",
            parse_mode="HTML"
        )
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
            await update.message.reply_text("⚠️ ᴘʀɪᴄᴇ ᴍᴜsᴛ ʙᴇ ɢʀᴇᴀᴛᴇʀ ᴛʜᴀɴ 0")
            return
        
        character = await characters_collection.find_one({"id": char_id})
        if not character:
            await update.message.reply_text(f"⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ <code>{char_id}</code> ɴᴏᴛ ғᴏᴜɴᴅ ɪɴ ᴅᴀᴛᴀʙᴀsᴇ", parse_mode="HTML")
            return
        
        existing = await shop_collection.find_one({"id": char_id})
        if existing:
            await update.message.reply_text(f"⚠️ <b>{character['name']}</b> ɪs ᴀʟʀᴇᴀᴅʏ ɪɴ sʜᴏᴘ!", parse_mode="HTML")
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
        discount_text = f"\n🏷️ <b>{discount}%</b> ᴅɪsᴄᴏᴜɴᴛ" if discount > 0 else ""
        featured_text = "\n⭐ <b>ғᴇᴀᴛᴜʀᴇᴅ</b>" if featured else ""
        
        await update.message.reply_text(
            f"✨ <b>ᴀᴅᴅᴇᴅ ᴛᴏ sʜᴏᴘ!</b>\n\n"
            f"🎭 <b>{character['name']}</b>\n"
            f"📺 {character.get('anime', 'Unknown')}\n"
            f"💎 {price:,} → <b>{final_price:,}</b> ɢᴏʟᴅ{discount_text}\n"
            f"🔢 ʟɪᴍɪᴛ: <b>{limit_text}</b>{featured_text}",
            parse_mode="HTML"
        )
    except ValueError as e:
        await update.message.reply_text(f"⚠️ ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ғᴏʀᴍᴀᴛ!")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

async def srm(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ʀᴇᴍᴏᴠᴇ ɪᴛᴇᴍs")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("⚠️ <b>ᴜsᴀɢᴇ:</b> /srm &lt;id&gt;", parse_mode="HTML")
        return
    
    try:
        char_id = context.args[0]
        shop_item = await shop_collection.find_one({"id": char_id})
        
        if not shop_item:
            await update.message.reply_text(f"⚠️ <code>{char_id}</code> ɴᴏᴛ ғᴏᴜɴᴅ ɪɴ sʜᴏᴘ", parse_mode="HTML")
            return
        
        character = await characters_collection.find_one({"id": char_id})
        char_name = character['name'] if character else char_id
        sold_count = shop_item.get('sold', 0)
        
        await shop_collection.delete_one({"id": char_id})
        
        await update.message.reply_text(
            f"🗑️ <b>ʀᴇᴍᴏᴠᴇᴅ ғʀᴏᴍ sʜᴏᴘ</b>\n\n"
            f"✨ <b>{char_name}</b>\n"
            f"📊 ᴛᴏᴛᴀʟ sᴏʟᴅ: {sold_count}",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

async def shop(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Check for active auction first
    active_auction = await auction_collection.find_one({"status": "active", "end_time": {"$gt": datetime.utcnow()}})
    if active_auction:
        await show_auction_shop(update, context, active_auction)
        return
    
    sort_by = [("featured", -1), ("added_at", -1)]
    filter_query = {}
    
    if context.args:
        arg = context.args[0].lower()
        if arg == "discount":
            filter_query["discount"] = {"$gt": 0}
            sort_by = [("discount", -1)]
    
    shop_items = await shop_collection.find(filter_query).sort(sort_by).to_list(length=None)
    
    if not shop_items:
        buttons = [[InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ sʜᴏᴘ", callback_data="sr_reload")]]
        markup = InlineKeyboardMarkup(buttons)
        
        await update.message.reply_text(
            "🏪 <b>sʜᴏᴘ ɪs ᴇᴍᴘᴛʏ</b>\n\n"
            "😔 ɴᴏ ɪᴛᴇᴍs ᴀᴠᴀɪʟᴀʙʟᴇ ʀɪɢʜᴛ ɴᴏᴡ\n\n"
            "💡 <b>ᴛɪᴘs:</b>\n"
            "• ᴄʜᴇᴄᴋ ʙᴀᴄᴋ ʟᴀᴛᴇʀ ғᴏʀ ɴᴇᴡ ɪᴛᴇᴍs\n"
            "• ᴜsᴇ /shop discount ғᴏʀ ᴅɪsᴄᴏᴜɴᴛᴇᴅ ɪᴛᴇᴍs\n"
            "• ᴄʜᴇᴄᴋ ᴀᴜᴄᴛɪᴏɴs ғᴏʀ ʀᴀʀᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs",
            parse_mode="HTML",
            reply_markup=markup
        )
        return
    
    page = 0
    context.user_data['shop_items'] = [item['id'] for item in shop_items]
    context.user_data['shop_page'] = page
    context.user_data['shop_filter'] = filter_query
    
    char_id = shop_items[page]['id']
    character = await characters_collection.find_one({"id": char_id})
    user_data = await user_collection.find_one({"id": user_id})
    
    if not character:
        await update.message.reply_text("⚠️ ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ sʜᴏᴘ ɪᴛᴇᴍ")
        return
    
    await shop_collection.update_one({"id": char_id}, {"$inc": {"views": 1}})
    
    caption, media_url, sold_out, is_video = build_caption(character, shop_items[page], page + 1, len(shop_items), user_data)
    
    buttons = []
    
    if not sold_out:
        buttons.append([InlineKeyboardButton("💳 ʙᴜʏ ɴᴏᴡ", callback_data=f"sb_{char_id}")])
    else:
        buttons.append([InlineKeyboardButton("🚫 ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ", callback_data="sna")])
    
    if len(shop_items) > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️ ᴘʀᴇᴠ", callback_data=f"sp_{page-1}"))
        nav.append(InlineKeyboardButton(f"• {page+1}/{len(shop_items)} •", callback_data="spi"))
        if page < len(shop_items) - 1:
            nav.append(InlineKeyboardButton("ɴᴇxᴛ ▶️", callback_data=f"sp_{page+1}"))
        buttons.append(nav)
    
    buttons.append([
        InlineKeyboardButton("🏷️ ᴅɪsᴄᴏᴜɴᴛs", callback_data="ss_discount"),
        InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="sr")
    ])
    
    markup = InlineKeyboardMarkup(buttons)
    
    try:
        if is_video:
            await update.message.reply_video(video=media_url, caption=caption, parse_mode="HTML", reply_markup=markup)
        else:
            await update.message.reply_photo(photo=media_url, caption=caption, parse_mode="HTML", reply_markup=markup)
    except BadRequest as e:
        await update.message.reply_text(
            f"{caption}\n\n⚠️ ᴄᴏᴜʟᴅɴ'ᴛ ʟᴏᴀᴅ ᴍᴇᴅɪᴀ",
            parse_mode="HTML",
            reply_markup=markup
        )

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
        status = "⭐ ғᴇᴀᴛᴜʀᴇᴅ"
    
    caption = f"<b>🏪 sʜᴏᴘ {status}</b>\n\n"
    caption += f"✨ <b>{name}</b>\n"
    caption += f"🎭 {anime}\n"
    caption += f"💫 {rarity}\n"
    
    if discount > 0 and not sold_out and not already_bought:
        caption += f"💎 <s>{price:,}</s> → <b>{final_price:,}</b> ɢᴏʟᴅ\n"
        caption += f"🏷️ <b>{discount}%</b> ᴏғғ!\n"
    else:
        caption += f"💎 <b>{final_price:,}</b> ɢᴏʟᴅ\n"
    
    caption += f"🔢 sᴛᴏᴄᴋ: {limit_text} | 👁️ {views:,} ᴠɪᴇᴡs\n"
    caption += f"📖 ᴘᴀɢᴇ {page}/{total}"
    
    return caption, img_url, sold_out or already_bought, is_video

async def shist(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    history = await shop_history_collection.find({"user_id": user_id}).sort("purchase_date", -1).limit(10).to_list(length=10)
    
    if not history:
        await update.message.reply_text(
            "📜 <b>ɴᴏ ᴘᴜʀᴄʜᴀsᴇ ʜɪsᴛᴏʀʏ</b>\n\n"
            "ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ʙᴏᴜɢʜᴛ ᴀɴʏᴛʜɪɴɢ ʏᴇᴛ!",
            parse_mode="HTML"
        )
        return
    
    text = "<b>📜 ʏᴏᴜʀ ᴘᴜʀᴄʜᴀsᴇ ʜɪsᴛᴏʀʏ</b>\n\n"
    total = 0
    
    for i, r in enumerate(history, 1):
        character = await characters_collection.find_one({"id": r["character_id"]})
        name = character.get("name", "Unknown") if character else "Unknown"
        price = r.get("price", 0)
        date = r.get("purchase_date", datetime.utcnow()).strftime("%d %b %Y")
        total += price
        text += f"{i}. <b>{name}</b>\n   💰 {price:,} • {date}\n\n"
    
    text += f"━━━━━━━━━━━━━\n💰 <b>ᴛᴏᴛᴀʟ sᴘᴇɴᴛ:</b> {total:,} ɢᴏʟᴅ"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def gstart(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ sᴛᴀʀᴛ ɢɪᴠᴇᴀᴡᴀʏs")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b> /gstart &lt;id&gt; &lt;hours&gt; &lt;min_chars&gt;\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b>\n/gstart CHAR001 24 10\n\n"
            "⏰ ᴛɪᴍᴇᴢᴏɴᴇ: IST (Kolkata)",
            parse_mode="HTML"
        )
        return
    
    try:
        char_id = context.args[0]
        duration_hours = int(context.args[1])
        min_activity = int(context.args[2])
        
        if duration_hours <= 0:
            await update.message.reply_text("⚠️ ᴅᴜʀᴀᴛɪᴏɴ ᴍᴜsᴛ ʙᴇ ɢʀᴇᴀᴛᴇʀ ᴛʜᴀɴ 0")
            return
        
        character = await characters_collection.find_one({"id": char_id})
        if not character:
            await update.message.reply_text(f"⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ <code>{char_id}</code> ɴᴏᴛ ғᴏᴜɴᴅ", parse_mode="HTML")
            return
        
        active = await giveaway_collection.find_one({"status": "active"})
        if active:
            await update.message.reply_text("⚠️ ᴀ ɢɪᴠᴇᴀᴡᴀʏ ɪs ᴀʟʀᴇᴀᴅʏ ᴀᴄᴛɪᴠᴇ!")
            return
        
        # Calculate end time in IST
        start_time_ist = get_ist_time()
        end_time_ist = start_time_ist + timedelta(hours=duration_hours)
        
        # Convert to UTC for storage
        start_time_utc = to_utc(start_time_ist)
        end_time_utc = to_utc(end_time_ist)
        
        giveaway = {
            "character_id": char_id,
            "start_time": start_time_utc,
            "end_time": end_time_utc,
            "min_activity": min_activity,
            "participants": [],
            "status": "active",
            "created_by": user_id,
            "winner": None,
            "duration_hours": duration_hours
        }
        
        result = await giveaway_collection.insert_one(giveaway)
        giveaway_id = result.inserted_id
        
        # Schedule auto-end using IST time
        scheduler.add_job(
            auto_end_giveaway,
            trigger=DateTrigger(run_date=end_time_ist),
            args=[giveaway_id, context],
            id=f"giveaway_{giveaway_id}",
            replace_existing=True
        )
        
        img_url = character.get("img_url", "")
        caption = (
            f"<b>🎉 ɴᴇᴡ ɢɪᴠᴇᴀᴡᴀʏ!</b>\n\n"
            f"🎁 <b>{character['name']}</b>\n"
            f"🎭 {character.get('anime', 'Unknown')}\n"
            f"💫 {character.get('rarity', 'Unknown')}\n\n"
            f"🕐 sᴛᴀʀᴛᴇᴅ: {start_time_ist.strftime('%d %b, %I:%M %p IST')}\n"
            f"⏰ ᴇɴᴅs: {end_time_ist.strftime('%d %b, %I:%M %p IST')}\n"
            f"⏳ ᴅᴜʀᴀᴛɪᴏɴ: {duration_hours} ʜᴏᴜʀs\n"
            f"📊 ʀᴇǫᴜɪʀᴇᴍᴇɴᴛ: {min_activity} ᴄʜᴀʀᴀᴄᴛᴇʀs\n"
            f"👥 ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs: 0\n\n"
            f"ᴄʟɪᴄᴋ ʙᴇʟᴏᴡ ᴛᴏ ᴊᴏɪɴ!"
        )
        
        buttons = [
            [InlineKeyboardButton("🎫 ᴊᴏɪɴ ɢɪᴠᴇᴀᴡᴀʏ", callback_data="gj")],
            [InlineKeyboardButton("📊 ᴠɪᴇᴡ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs", callback_data="gp"),
             InlineKeyboardButton("⏰ ᴛɪᴍᴇ ʟᴇғᴛ", callback_data="gt")]
        ]
        markup = InlineKeyboardMarkup(buttons)
        
        if character.get("rarity") == "🎥 AMV":
            await update.message.reply_video(video=img_url, caption=caption, parse_mode="HTML", reply_markup=markup)
        else:
            await update.message.reply_photo(photo=img_url, caption=caption, parse_mode="HTML", reply_markup=markup)
            
        await update.message.reply_text(
            f"✅ <b>ɢɪᴠᴇᴀᴡᴀʏ sᴄʜᴇᴅᴜʟᴇᴅ!</b>\n\n"
            f"⏰ ᴡɪʟʟ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴇɴᴅ ᴀᴛ:\n"
            f"{end_time_ist.strftime('%d %b %Y, %I:%M %p IST')}",
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ғᴏʀᴍᴀᴛ!")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

async def gend(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴇɴᴅ ɢɪᴠᴇᴀᴡᴀʏs")
        return
    
    giveaway = await giveaway_collection.find_one({"status": "active"})
    if not giveaway:
        await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢɪᴠᴇᴀᴡᴀʏ ғᴏᴜɴᴅ")
        return
    
    # Cancel scheduled job if exists
    try:
        scheduler.remove_job(f"giveaway_{giveaway['_id']}")
    except:
        pass
    
    participants = giveaway.get("participants", [])
    if not participants:
        await giveaway_collection.update_one(
            {"_id": giveaway["_id"]},
            {"$set": {"status": "ended", "end_reason": "manual_no_participants"}}
        )
        await update.message.reply_text("⚠️ ɴᴏ ᴏɴᴇ ᴊᴏɪɴᴇᴅ ᴛʜᴇ ɢɪᴠᴇᴀᴡᴀʏ 😢")
        return
    
    winner_id = random.choice(participants)
    character = await characters_collection.find_one({"id": giveaway["character_id"]})
    
    await user_collection.update_one(
        {"id": winner_id},
        {"$push": {"characters": character}},
        upsert=True
    )
    
    await giveaway_collection.update_one(
        {"_id": giveaway["_id"]},
        {
            "$set": {
                "status": "ended",
                "winner": winner_id,
                "end_reason": "manual",
                "actual_end_time": datetime.utcnow()
            }
        }
    )
    
    try:
        winner_user = await context.bot.get_chat(winner_id)
        winner_name = winner_user.first_name
    except:
        winner_name = f"User {winner_id}"
    
    await update.message.reply_text(
        f"<b>🎊 ɢɪᴠᴇᴀᴡᴀʏ ᴇɴᴅᴇᴅ!</b>\n\n"
        f"🎁 <b>{character['name']}</b>\n"
        f"🏆 ᴡɪɴɴᴇʀ: <a href='tg://user?id={winner_id}'>{winner_name}</a>\n"
        f"👥 ᴛᴏᴛᴀʟ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs: {len(participants)}\n"
        f"⏰ ᴇɴᴅᴇᴅ ᴀᴛ: {get_ist_time().strftime('%d %b %Y, %I:%M %p IST')}\n\n"
        f"ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs! 🎉",
        parse_mode="HTML"
    )

async def gstatus(update: Update, context: CallbackContext):
    """Check current giveaway status"""
    giveaway = await giveaway_collection.find_one({"status": "active"})
    
    if not giveaway:
        await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢɪᴠᴇᴀᴡᴀʏ")
        return
    
    character = await characters_collection.find_one({"id": giveaway["character_id"]})
    start_time_ist = to_ist(giveaway["start_time"])
    end_time_ist = to_ist(giveaway["end_time"])
    current_time_ist = get_ist_time()
    
    time_left = end_time_ist - current_time_ist
    hours_left = int(time_left.total_seconds() / 3600)
    minutes_left = int((time_left.total_seconds() % 3600) / 60)
    
    participants = giveaway.get("participants", [])
    
    text = (
        f"<b>🎉 ᴀᴄᴛɪᴠᴇ ɢɪᴠᴇᴀᴡᴀʏ</b>\n\n"
        f"🎁 <b>{character['name']}</b>\n"
        f"🎭 {character.get('anime', 'Unknown')}\n"
        f"💫 {character.get('rarity', 'Unknown')}\n\n"
        f"🕐 sᴛᴀʀᴛᴇᴅ: {start_time_ist.strftime('%d %b, %I:%M %p')}\n"
        f"⏰ ᴇɴᴅs: {end_time_ist.strftime('%d %b, %I:%M %p')}\n"
        f"⏳ ᴛɪᴍᴇ ʟᴇғᴛ: {hours_left}ʜ {minutes_left}ᴍ\n"
        f"👥 ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs: {len(participants)}\n"
        f"📊 ʀᴇǫᴜɪʀᴇᴍᴇɴᴛ: {giveaway['min_activity']} ᴄʜᴀʀs\n\n"
        f"🕐 ᴄᴜʀʀᴇɴᴛ ᴛɪᴍᴇ: {current_time_ist.strftime('%I:%M %p IST')}"
    )
    
    await update.message.reply_text(text, parse_mode="HTML")

async def astart(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ sᴛᴀʀᴛ ᴀᴜᴄᴛɪᴏɴs")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b> /astart &lt;id&gt; &lt;start_bid&gt; &lt;hours&gt;\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b>\n/astart CHAR001 5000 12",
            parse_mode="HTML"
        )
        return
    
    try:
        char_id = context.args[0]
        starting_bid = int(context.args[1])
        duration_hours = int(context.args[2])
        
        character = await characters_collection.find_one({"id": char_id})
        if not character:
            await update.message.reply_text(f"⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ <code>{char_id}</code> ɴᴏᴛ ғᴏᴜɴᴅ", parse_mode="HTML")
            return
        
        active = await auction_collection.find_one({"status": "active"})
        if active:
            await update.message.reply_text("⚠️ ᴀɴ ᴀᴜᴄᴛɪᴏɴ ɪs ᴀʟʀᴇᴀᴅʏ ᴀᴄᴛɪᴠᴇ!")
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
            f"<b>🔨 ᴀᴜᴄᴛɪᴏɴ sᴛᴀʀᴛᴇᴅ!</b>\n\n"
            f"💎 <b>{character['name']}</b>\n"
            f"🎭 {character.get('anime', 'Unknown')}\n"
            f"💫 {character.get('rarity', 'Unknown')}\n\n"
            f"💰 sᴛᴀʀᴛɪɴɢ ʙɪᴅ: {starting_bid:,} ɢᴏʟᴅ\n"
            f"🏆 ᴄᴜʀʀᴇɴᴛ ʙɪᴅ: {starting_bid:,} ɢᴏʟᴅ\n"
            f"⏰ ᴇɴᴅs: {end_time.strftime('%d %b, %H:%M UTC')}\n\n"
            f"ᴜsᴇ /bid [ᴀᴍᴏᴜɴᴛ] ᴛᴏ ᴘʟᴀᴄᴇ ʏᴏᴜʀ ʙɪᴅ!"
        )
        
        buttons = [
            [InlineKeyboardButton("🔨 ᴠɪᴇᴡ ᴀᴜᴄᴛɪᴏɴ", callback_data="av")],
            [
                InlineKeyboardButton(f"+{starting_bid//10:,}", callback_data=f"ab_{starting_bid//10}"),
                InlineKeyboardButton(f"+{starting_bid//5:,}", callback_data=f"ab_{starting_bid//5}")
            ]
        ]
        markup = InlineKeyboardMarkup(buttons)
        
        if character.get("rarity") == "🎥 AMV":
            await update.message.reply_video(video=img_url, caption=caption, parse_mode="HTML", reply_markup=markup)
        else:
            await update.message.reply_photo(photo=img_url, caption=caption, parse_mode="HTML", reply_markup=markup)
    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ғᴏʀᴍᴀᴛ!")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

async def aend(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴇɴᴅ ᴀᴜᴄᴛɪᴏɴs")
        return
    
    auction = await auction_collection.find_one({"status": "active"})
    if not auction:
        await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ ғᴏᴜɴᴅ")
        return
    
    highest_bidder = auction.get("highest_bidder")
    character = await characters_collection.find_one({"id": auction["character_id"]})
    
    if highest_bidder:
        final_bid = auction.get("current_bid")
        
        await user_collection.update_one(
            {"id": highest_bidder},
            {"$inc": {"balance": -final_bid}, "$push": {"characters": character}}
        )
        
        try:
            winner_user = await context.bot.get_chat(highest_bidder)
            winner_name = winner_user.first_name
        except:
            winner_name = f"User {highest_bidder}"
        
        await update.message.reply_text(
            f"<b>🎊 ᴀᴜᴄᴛɪᴏɴ ᴇɴᴅᴇᴅ!</b>\n\n"
            f"💎 <b>{character['name']}</b>\n"
            f"🏆 ᴡɪɴɴᴇʀ: <a href='tg://user?id={highest_bidder}'>{winner_name}</a>\n"
            f"💰 ғɪɴᴀʟ ʙɪᴅ: {final_bid:,} ɢᴏʟᴅ\n"
            f"📊 ᴛᴏᴛᴀʟ ʙɪᴅs: {auction.get('bid_count', 0)}\n\n"
            f"ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs! 🎉",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("⚠️ ɴᴏ ʙɪᴅs ᴡᴇʀᴇ ᴘʟᴀᴄᴇᴅ 😢")
    
    await auction_collection.update_one(
        {"_id": auction["_id"]},
        {"$set": {"status": "ended"}}
    )

async def bid(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b> /bid [ᴀᴍᴏᴜɴᴛ]\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b> /bid 10000",
            parse_mode="HTML"
        )
        return
    
    try:
        bid_amount = int(context.args[0])
        
        auction = await auction_collection.find_one({"status": "active"})
        if not auction:
            await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ ʀɪɢʜᴛ ɴᴏᴡ")
            return
        
        current_bid = auction.get("current_bid")
        min_bid = int(current_bid * 1.05)
        
        if bid_amount < min_bid:
            await update.message.reply_text(
                f"⚠️ <b>ʙɪᴅ ᴛᴏᴏ ʟᴏᴡ!</b>\n\n"
                f"ᴍɪɴɪᴍᴜᴍ ʙɪᴅ: <b>{min_bid:,}</b> ɢᴏʟᴅ\n"
                f"(5% ᴍᴏʀᴇ ᴛʜᴀɴ ᴄᴜʀʀᴇɴᴛ)",
                parse_mode="HTML"
            )
            return
        
        user_data = await user_collection.find_one({"id": user_id})
        balance = user_data.get("balance", 0) if user_data else 0
        
        if balance < bid_amount:
            await update.message.reply_text(
                f"⚠️ <b>ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ!</b>\n\n"
                f"ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ: {balance:,} ɢᴏʟᴅ\n"
                f"ʀᴇǫᴜɪʀᴇᴅ: {bid_amount:,} ɢᴏʟᴅ\n"
                f"ɴᴇᴇᴅ: {bid_amount - balance:,} ᴍᴏʀᴇ",
                parse_mode="HTML"
            )
            return
        
        await auction_collection.update_one(
            {"_id": auction["_id"]},
            {
                "$set": {
                    "current_bid": bid_amount,
                    "highest_bidder": user_id
                },
                "$inc": {"bid_count": 1}
            }
        )
        
        await bid_collection.insert_one({
            "auction_id": auction["_id"],
            "user_id": user_id,
            "amount": bid_amount,
            "timestamp": datetime.utcnow()
        })
        
        character = await characters_collection.find_one({"id": auction["character_id"]})
        
        await update.message.reply_text(
            f"<b>✅ ʙɪᴅ ᴘʟᴀᴄᴇᴅ!</b>\n\n"
            f"💎 <b>{character['name']}</b>\n"
            f"💰 ʏᴏᴜʀ ʙɪᴅ: {bid_amount:,} ɢᴏʟᴅ\n\n"
            f"ɢᴏᴏᴅ ʟᴜᴄᴋ! 🍀",
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("⚠️ ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ!")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

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
    bidder_text = "ɴᴏɴᴇ ʏᴇᴛ"
    
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
        f"🎭 {character.get('anime', 'Unknown')}\n"
        f"💫 {character.get('rarity', 'Unknown')}\n\n"
        f"💰 ᴄᴜʀʀᴇɴᴛ ʙɪᴅ: <b>{auction['current_bid']:,}</b> ɢᴏʟᴅ\n"
        f"👤 ʜɪɢʜᴇsᴛ ʙɪᴅᴅᴇʀ: {bidder_text}\n"
        f"⏰ ᴛɪᴍᴇ ʟᴇғᴛ: {hours_left}ʜ {minutes_left}ᴍ\n"
        f"📊 ᴛᴏᴛᴀʟ ʙɪᴅs: {auction['bid_count']}\n\n"
        f"ᴜsᴇ /bid [ᴀᴍᴏᴜɴᴛ] ᴛᴏ ʙɪᴅ!"
    )
    
    increment_small = auction['current_bid'] // 10
    increment_medium = auction['current_bid'] // 5
    increment_large = auction['current_bid'] // 2
    
    buttons = [
        [
            InlineKeyboardButton(f"+{increment_small:,} 💰", callback_data=f"ab_{increment_small}"),
            InlineKeyboardButton(f"+{increment_medium:,} 💰", callback_data=f"ab_{increment_medium}"),
            InlineKeyboardButton(f"+{increment_large:,} 💰", callback_data=f"ab_{increment_large}")
        ],
        [InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="av")],
        [InlineKeyboardButton("📊 ʙɪᴅ ʜɪsᴛᴏʀʏ", callback_data="ah")]
    ]
    markup = InlineKeyboardMarkup(buttons)
    
    try:
        if is_video:
            await update.message.reply_video(video=img_url, caption=caption, parse_mode="HTML", reply_markup=markup)
        else:
            await update.message.reply_photo(photo=img_url, caption=caption, parse_mode="HTML", reply_markup=markup)
    except BadRequest as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ ᴀᴜᴄᴛɪᴏɴ: {str(e)}")

async def shop_callback(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    async def render_page(page):
        items = context.user_data.get('shop_items', [])
        if not items or page >= len(items):
            await query.answer("⚠️ ɴᴏ ɪᴛᴇᴍs ғᴏᴜɴᴅ")
            return
        
        context.user_data['shop_page'] = page
        char_id = items[page]
        character = await characters_collection.find_one({"id": char_id})
        shop_item = await shop_collection.find_one({"id": char_id})
        user_data = await user_collection.find_one({"id": user_id})
        
        if not character or not shop_item:
            await query.answer("⚠️ ɪᴛᴇᴍ ɴᴏᴛ ғᴏᴜɴᴅ")
            return
        
        await shop_collection.update_one({"id": char_id}, {"$inc": {"views": 1}})
        
        caption, media_url, sold_out, is_video = build_caption(
            character, shop_item, page + 1, len(items), user_data
        )
        
        buttons = []
        
        if not sold_out:
            buttons.append([InlineKeyboardButton("💳 ʙᴜʏ ɴᴏᴡ", callback_data=f"sb_{char_id}")])
        
        if len(items) > 1:
            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton("◀️ ᴘʀᴇᴠ", callback_data=f"sp_{page-1}"))
            nav.append(InlineKeyboardButton(f"• {page+1}/{len(items)} •", callback_data="spi"))
            if page < len(items) - 1:
                nav.append(InlineKeyboardButton("ɴᴇxᴛ ▶️", callback_data=f"sp_{page+1}"))
            buttons.append(nav)
        
        buttons.append([
            InlineKeyboardButton("🏷️ ᴅɪsᴄᴏᴜɴᴛ", callback_data="ss_discount"),
            InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="sr")
        ])
        
        markup = InlineKeyboardMarkup(buttons)
        
        try:
            if is_video:
                await query.edit_message_media(
                    media=InputMediaVideo(media=media_url, caption=caption, parse_mode="HTML"),
                    reply_markup=markup
                )
            else:
                await query.edit_message_media(
                    media=InputMediaPhoto(media=media_url, caption=caption, parse_mode="HTML"),
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
                await query.answer("⚠️ ᴄᴏᴜʟᴅɴ'ᴛ ᴜᴘᴅᴀᴛᴇ")
    
    if data.startswith("sp_"):
        page = int(data.split("_")[1])
        await render_page(page)
    
    elif data.startswith("ss_"):
        sort_type = data.split("_")[1]
        
        if sort_type == "discount":
            filter_query = {"discount": {"$gt": 0}}
            sort_by = [("discount", -1)]
            
            shop_items = await shop_collection.find(filter_query).sort(sort_by).to_list(length=None)
            
            if shop_items:
                context.user_data['shop_items'] = [item['id'] for item in shop_items]
                context.user_data['shop_page'] = 0
                context.user_data['shop_filter'] = filter_query
                await render_page(0)
                await query.answer(f"🏷️ {len(shop_items)} ᴅɪsᴄᴏᴜɴᴛᴇᴅ ɪᴛᴇᴍs ғᴏᴜɴᴅ!")
            else:
                await query.answer(
                    "😔 ɴᴏ ᴅɪsᴄᴏᴜɴᴛs ᴀᴠᴀɪʟᴀʙʟᴇ\n\n"
                    "ᴄʜᴇᴄᴋ ʙᴀᴄᴋ ʟᴀᴛᴇʀ ғᴏʀ ᴅᴇᴀʟs!",
                    show_alert=True
                )
    
    elif data == "sr_reload":
        sort_by = [("featured", -1), ("added_at", -1)]
        shop_items = await shop_collection.find({}).sort(sort_by).to_list(length=None)
        
        if shop_items:
            context.user_data['shop_items'] = [item['id'] for item in shop_items]
            context.user_data['shop_page'] = 0
            await render_page(0)
            await query.answer(f"✅ {len(shop_items)} ɪᴛᴇᴍs ʟᴏᴀᴅᴇᴅ!")
        else:
            await query.answer("😔 sᴛɪʟʟ ᴇᴍᴘᴛʏ", show_alert=True)
    
    elif data.startswith("sb_"):
        char_id = data.split("_", 1)[1]
        shop_item = await shop_collection.find_one({"id": char_id})
        character = await characters_collection.find_one({"id": char_id})
        user_data = await user_collection.find_one({"id": user_id})
        
        if not shop_item or not character:
            await query.answer("⚠️ ɪᴛᴇᴍ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        limit = shop_item.get("limit")
        sold = shop_item.get("sold", 0)
        
        if limit and sold >= limit:
            await query.answer("⚠️ sᴏʟᴅ ᴏᴜᴛ!", show_alert=True)
            page = context.user_data.get('shop_page', 0)
            await render_page(page)
            return
        
        user_chars = user_data.get("characters", []) if user_data else []
        already_bought = any((c.get("id") == char_id or c.get("_id") == char_id) for c in user_chars)
        
        if already_bought:
            await query.answer("⚠️ ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ᴏᴡɴ ᴛʜɪs!", show_alert=True)
            page = context.user_data.get('shop_page', 0)
            await render_page(page)
            return
        
        price = shop_item.get("final_price", shop_item.get("price", 0))
        original_price = shop_item.get("original_price", price)
        discount = shop_item.get("discount", 0)
        balance = user_data.get("balance", 0) if user_data else 0
        
        discount_text = ""
        if discount > 0:
            savings = original_price - price
            discount_text = f"💎 ᴏʀɪɢɪɴᴀʟ: <s>{original_price:,}</s> ɢᴏʟᴅ\n🏷️ <b>{discount}% ᴏғғ</b> (sᴀᴠᴇ {savings:,} ɢᴏʟᴅ)\n\n"
        
        can_afford = balance >= price
        
        if can_afford:
            balance_status = f"💵 ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ: <b>{balance:,}</b> ɢᴏʟᴅ\n📉 ᴀғᴛᴇʀ ᴘᴜʀᴄʜᴀsᴇ: <b>{balance - price:,}</b> ɢᴏʟᴅ"
        else:
            needed = price - balance
            balance_status = f"⚠️ ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ!\n\n💵 ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ: <b>{balance:,}</b> ɢᴏʟᴅ\n❌ ɴᴇᴇᴅ: <b>{needed:,}</b> ᴍᴏʀᴇ ɢᴏʟᴅ"
        
        buttons = []
        if can_afford:
            buttons.append([
                InlineKeyboardButton("✅ ᴄᴏɴғɪʀᴍ ᴘᴜʀᴄʜᴀsᴇ", callback_data=f"sc_{char_id}"),
                InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="sx")
            ])
        else:
            buttons.append([
                InlineKeyboardButton("❌ ᴄᴀɴɴᴏᴛ ᴀғғᴏʀᴅ", callback_data="sna"),
                InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="sx")
            ])
        
        markup = InlineKeyboardMarkup(buttons)
        
        try:
            await query.edit_message_caption(
                caption=(
                    f"<b>💳 {'ᴄᴏɴғɪʀᴍ ᴘᴜʀᴄʜᴀsᴇ' if can_afford else 'ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ'}</b>\n\n"
                    f"✨ <b>{character['name']}</b>\n"
                    f"🎭 {character.get('anime', 'Unknown')}\n"
                    f"💫 {character.get('rarity', 'Unknown')}\n\n"
                    f"{discount_text}"
                    f"💰 ᴘʀɪᴄᴇ: <b>{price:,}</b> ɢᴏʟᴅ\n\n"
                    f"{balance_status}"
                ),
                parse_mode="HTML",
                reply_markup=markup
            )
            if not can_afford:
                await query.answer("⚠️ ɴᴏᴛ ᴇɴᴏᴜɢʜ ɢᴏʟᴅ!", show_alert=True)
        except BadRequest:
            await query.answer("⚠️ ᴄᴏᴜʟᴅɴ'ᴛ ᴜᴘᴅᴀᴛᴇ", show_alert=True)
    
    elif data.startswith("sc_"):
        char_id = data.split("_", 1)[1]
        shop_item = await shop_collection.find_one({"id": char_id})
        character = await characters_collection.find_one({"id": char_id})
        user_data = await user_collection.find_one({"id": user_id})
        
        if not shop_item or not character:
            await query.answer("⚠️ ɪᴛᴇᴍ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        limit = shop_item.get("limit")
        sold = shop_item.get("sold", 0)
        
        if limit and sold >= limit:
            await query.answer("⚠️ sᴏʟᴅ ᴏᴜᴛ!", show_alert=True)
            return
        
        user_chars = user_data.get("characters", []) if user_data else []
        already_bought = any((c.get("id") == char_id or c.get("_id") == char_id) for c in user_chars)
        
        if already_bought:
            await query.answer("⚠️ ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ᴏᴡɴ ᴛʜɪs!", show_alert=True)
            page = context.user_data.get('shop_page', 0)
            await render_page(page)
            return
        
        price = shop_item.get("final_price", shop_item.get("price", 0))
        balance = user_data.get("balance", 0) if user_data else 0
        
        if balance < price:
            await query.answer(
                f"⚠️ ɴᴇᴇᴅ {price:,} ɢᴏʟᴅ!\nʏᴏᴜ ʜᴀᴠᴇ {balance:,}",
                show_alert=True
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
        
        await shop_collection.update_one({"id": char_id}, {"$inc": {"sold": 1}})
        
        await shop_history_collection.insert_one({
            "user_id": user_id,
            "character_id": char_id,
            "price": price,
            "purchase_date": datetime.utcnow()
        })
        
        try:
            await query.edit_message_caption(
                caption=(
                    f"<b>✨ ᴘᴜʀᴄʜᴀsᴇ sᴜᴄᴄᴇssғᴜʟ!</b>\n\n"
                    f"🎉 <b>{character['name']}</b>\n"
                    f"🎭 {character.get('anime', 'Unknown')}\n"
                    f"💫 {character.get('rarity', 'Unknown')}\n\n"
                    f"💰 ᴘᴀɪᴅ: {price:,} ɢᴏʟᴅ\n"
                    f"💵 ʀᴇᴍᴀɪɴɪɴɢ: <b>{balance - price:,}</b> ɢᴏʟᴅ"
                ),
                parse_mode="HTML"
            )
        except BadRequest:
            pass
        
        await query.answer("✨ ᴘᴜʀᴄʜᴀsᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!", show_alert=False)
    
    elif data == "sx":
        page = context.user_data.get('shop_page', 0)
        await render_page(page)
        await query.answer("❌ ᴘᴜʀᴄʜᴀsᴇ ᴄᴀɴᴄᴇʟʟᴇᴅ")
    
    elif data == "sna":
        await query.answer("💰 ᴇᴀʀɴ ᴍᴏʀᴇ ɢᴏʟᴅ ᴛᴏ ʙᴜʏ ᴛʜɪs!", show_alert=True)

async def giveaway_callback(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if data == "gj":
        giveaway = await giveaway_collection.find_one({"status": "active"})
        if not giveaway:
            await query.answer("⚠️ ɢɪᴠᴇᴀᴡᴀʏ ᴇɴᴅᴇᴅ", show_alert=True)
            return
        
        if datetime.utcnow() > giveaway["end_time"]:
            await query.answer("⚠️ ɢɪᴠᴇᴀᴡᴀʏ ʜᴀs ᴇxᴘɪʀᴇᴅ", show_alert=True)
            return
        
        user_data = await user_collection.find_one({"id": user_id})
        if not user_data:
            await query.answer("⚠️ sᴛᴀʀᴛ ᴘʟᴀʏɪɴɢ ғɪʀsᴛ!", show_alert=True)
            return
        
        user_chars = user_data.get("characters", [])
        if len(user_chars) < giveaway.get("min_activity", 0):
            await query.answer(
                f"⚠️ ɴᴇᴇᴅ {giveaway['min_activity']} ᴄʜᴀʀᴀᴄᴛᴇʀs!\nʏᴏᴜ ʜᴀᴠᴇ {len(user_chars)}",
                show_alert=True
            )
            return
        
        if user_id in giveaway.get("participants", []):
            await query.answer("⚠️ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ!", show_alert=True)
            return
        
        await giveaway_collection.update_one(
            {"_id": giveaway["_id"]},
            {"$push": {"participants": user_id}}
        )
        
        participants_count = len(giveaway.get("participants", [])) + 1
        character = await characters_collection.find_one({"id": giveaway["character_id"]})
        start_time_ist = to_ist(giveaway["start_time"])
        end_time_ist = to_ist(giveaway["end_time"])
        
        caption = (
            f"<b>🎉 ɴᴇᴡ ɢɪᴠᴇᴀᴡᴀʏ!</b>\n\n"
            f"🎁 <b>{character['name']}</b>\n"
            f"🎭 {character.get('anime', 'Unknown')}\n"
            f"💫 {character.get('rarity', 'Unknown')}\n\n"
            f"🕐 sᴛᴀʀᴛᴇᴅ: {start_time_ist.strftime('%d %b, %I:%M %p IST')}\n"
            f"⏰ ᴇɴᴅs: {end_time_ist.strftime('%d %b, %I:%M %p IST')}\n"
            f"📊 ʀᴇǫᴜɪʀᴇᴍᴇɴᴛ: {giveaway['min_activity']} ᴄʜᴀʀᴀᴄᴛᴇʀs\n"
            f"👥 ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs: {participants_count}\n\n"
            f"ᴄʟɪᴄᴋ ʙᴇʟᴏᴡ ᴛᴏ ᴊᴏɪɴ!"
        )
        
        buttons = [
            [InlineKeyboardButton("🎫 ᴊᴏɪɴ ɢɪᴠᴇᴀᴡᴀʏ", callback_data="gj")],
            [InlineKeyboardButton("📊 ᴠɪᴇᴡ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs", callback_data="gp"),
             InlineKeyboardButton("⏰ ᴛɪᴍᴇ ʟᴇғᴛ", callback_data="gt")]
        ]
        markup = InlineKeyboardMarkup(buttons)
        
        try:
            await query.edit_message_caption(
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        except BadRequest:
            pass
        
        await query.answer("✅ ᴊᴏɪɴᴇᴅ ɢɪᴠᴇᴀᴡᴀʏ!", show_alert=False)
    
    elif data == "gp":
        giveaway = await giveaway_collection.find_one({"status": "active"})
        if not giveaway:
            await query.answer("⚠️ ɢɪᴠᴇᴀᴡᴀʏ ᴇɴᴅᴇᴅ", show_alert=True)
            return
        
        participants = giveaway.get("participants", [])
        await query.answer(
            f"👥 {len(participants)} ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs ᴊᴏɪɴᴇᴅ!",
            show_alert=True
        )
    
    elif data == "gt":
        giveaway = await giveaway_collection.find_one({"status": "active"})
        if not giveaway:
            await query.answer("⚠️ ɢɪᴠᴇᴀᴡᴀʏ ᴇɴᴅᴇᴅ", show_alert=True)
            return
        
        end_time_ist = to_ist(giveaway["end_time"])
        current_time_ist = get_ist_time()
        time_left = end_time_ist - current_time_ist
        
        if time_left.total_seconds() <= 0:
            await query.answer("⏰ ɢɪᴠᴇᴀᴡᴀʏ ʜᴀs ᴇɴᴅᴇᴅ!", show_alert=True)
            return
        
        hours_left = int(time_left.total_seconds() / 3600)
        minutes_left = int((time_left.total_seconds() % 3600) / 60)
        
        await query.answer(
            f"⏰ ᴛɪᴍᴇ ʟᴇғᴛ: {hours_left}ʜ {minutes_left}ᴍ\n"
            f"ᴇɴᴅs ᴀᴛ: {end_time_ist.strftime('%I:%M %p IST')}",
            show_alert=True
        )

async def auction_callback(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    if data == "av":
        await query.answer()
        auction = await auction_collection.find_one({"status": "active"})
        if not auction:
            await query.answer("⚠️ ᴀᴜᴄᴛɪᴏɴ ᴇɴᴅᴇᴅ", show_alert=True)
            return
        
        character = await characters_collection.find_one({"id": auction["character_id"]})
        end_time = auction.get("end_time")
        time_left = end_time - datetime.utcnow()
        hours_left = int(time_left.total_seconds() / 3600)
        minutes_left = int((time_left.total_seconds() % 3600) / 60)
        
        highest_bidder = auction.get("highest_bidder")
        bidder_text = "ɴᴏɴᴇ ʏᴇᴛ"
        
        if highest_bidder:
            try:
                bidder_user = await context.bot.get_chat(highest_bidder)
                bidder_text = bidder_user.first_name
            except:
                bidder_text = f"User {highest_bidder}"
        
        increment_small = auction['current_bid'] // 10
        increment_medium = auction['current_bid'] // 5
        increment_large = auction['current_bid'] // 2
        
        caption = (
            f"<b>🔨 ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ</b>\n\n"
            f"💎 <b>{character['name']}</b>\n"
            f"🎭 {character.get('anime', 'Unknown')}\n"
            f"💫 {character.get('rarity', 'Unknown')}\n\n"
            f"💰 ᴄᴜʀʀᴇɴᴛ ʙɪᴅ: <b>{auction['current_bid']:,}</b> ɢᴏʟᴅ\n"
            f"👤 ʜɪɢʜᴇsᴛ ʙɪᴅᴅᴇʀ: {bidder_text}\n"
            f"⏰ ᴛɪᴍᴇ ʟᴇғᴛ: {hours_left}ʜ {minutes_left}ᴍ\n"
            f"📊 ᴛᴏᴛᴀʟ ʙɪᴅs: {auction['bid_count']}\n\n"
            f"ᴜsᴇ /bid [ᴀᴍᴏᴜɴᴛ] ᴛᴏ ʙɪᴅ!"
        )
        
        buttons = [
            [
                InlineKeyboardButton(f"+{increment_small:,} 💰", callback_data=f"ab_{increment_small}"),
                InlineKeyboardButton(f"+{increment_medium:,} 💰", callback_data=f"ab_{increment_medium}"),
                InlineKeyboardButton(f"+{increment_large:,} 💰", callback_data=f"ab_{increment_large}")
            ],
            [InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="av")],
            [InlineKeyboardButton("📊 ʙɪᴅ ʜɪsᴛᴏʀʏ", callback_data="ah")]
        ]
        markup = InlineKeyboardMarkup(buttons)
        
        try:
            await query.edit_message_caption(
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        except BadRequest:
            pass
    
    elif data.startswith("ab_"):
        increment = int(data.split("_")[1])
        auction = await auction_collection.find_one({"status": "active"})
        
        if not auction:
            await query.answer("⚠️ ᴀᴜᴄᴛɪᴏɴ ᴇɴᴅᴇᴅ", show_alert=True)
            return
        
        bid_amount = auction.get("current_bid") + increment
        user_data = await user_collection.find_one({"id": user_id})
        balance = user_data.get("balance", 0) if user_data else 0
        
        if balance < bid_amount:
            await query.answer(
                f"⚠️ ɴᴇᴇᴅ {bid_amount:,} ɢᴏʟᴅ!\nʏᴏᴜ ʜᴀᴠᴇ {balance:,}",
                show_alert=True
            )
            return
        
        await auction_collection.update_one(
            {"_id": auction["_id"]},
            {
                "$set": {
                    "current_bid": bid_amount,
                    "highest_bidder": user_id
                },
                "$inc": {"bid_count": 1}
            }
        )
        
        await bid_collection.insert_one({
            "auction_id": auction["_id"],
            "user_id": user_id,
            "amount": bid_amount,
            "timestamp": datetime.utcnow()
        })
        
        await query.answer(f"✅ ʙɪᴅ ᴘʟᴀᴄᴇᴅ: {bid_amount:,} ɢᴏʟᴅ!")
    
    elif data == "ah":
        auction = await auction_collection.find_one({"status": "active"})
        
        if not auction:
            await query.answer("⚠️ ᴀᴜᴄᴛɪᴏɴ ᴇɴᴅᴇᴅ", show_alert=True)
            return
        
        bids = await bid_collection.find(
            {"auction_id": auction["_id"]}
        ).sort("timestamp", -1).limit(5).to_list(length=5)
        
        if not bids:
            await query.answer("📊 ɴᴏ ʙɪᴅs ʏᴇᴛ", show_alert=True)
            return
        
        history_text = "📊 ʀᴇᴄᴇɴᴛ ʙɪᴅs:\n\n"
        
        for i, bid_item in enumerate(bids, 1):
            try:
                bidder = await context.bot.get_chat(bid_item["user_id"])
                name = bidder.first_name
            except:
                name = f"User {bid_item['user_id']}"
            
            amount = bid_item["amount"]
            history_text += f"{i}. {name}: {amount:,} 💰\n"
        
        await query.answer(history_text, show_alert=True)

# Register all handlers
application.add_handler(CommandHandler("shop", shop, block=False))
application.add_handler(CommandHandler("sadd", sadd, block=False))
application.add_handler(CommandHandler("srm", srm, block=False))
application.add_handler(CommandHandler("shist", shist, block=False))
application.add_handler(CommandHandler("gstart", gstart, block=False))
application.add_handler(CommandHandler("gend", gend, block=False))
application.add_handler(CommandHandler("gstatus", gstatus, block=False))
application.add_handler(CommandHandler("astart", astart, block=False))
application.add_handler(CommandHandler("aend", aend, block=False))
application.add_handler(CommandHandler("bid", bid, block=False))
application.add_handler(CallbackQueryHandler(shop_callback, pattern=r"^s", block=False))
application.add_handler(CallbackQueryHandler(giveaway_callback, pattern=r"^g", block=False))
application.add_handler(CallbackQueryHandler(auction_callback, pattern=r"^a", block=False))