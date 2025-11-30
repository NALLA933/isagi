import random
from datetime import datetime, timedelta
import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest
import html

from shivu import application, db, user_collection

collection = db['anime_characters_lol']
shop_collection = db['shop']
shop_history_collection = db['shop_history']
auction_collection = db['auctions']
bid_collection = db['bids']

sudo_users = ["8297659126", "8420981179", "5147822244"]

KOLKATA_TZ = pytz.timezone('Asia/Kolkata')

def get_kolkata_time():
    """Get current time in Kolkata timezone"""
    return datetime.now(KOLKATA_TZ)

def utc_to_kolkata(utc_time):
    """Convert UTC time to Kolkata timezone"""
    if utc_time.tzinfo is None:
        utc_time = pytz.utc.localize(utc_time)
    return utc_time.astimezone(KOLKATA_TZ)

def kolkata_to_utc(kolkata_time):
    """Convert Kolkata time to UTC"""
    if kolkata_time.tzinfo is None:
        kolkata_time = KOLKATA_TZ.localize(kolkata_time)
    return kolkata_time.astimezone(pytz.utc)

async def is_sudo_user(user_id: int) -> bool:
    return str(user_id) in sudo_users

def escape_html(text):
    """Escape HTML special characters"""
    if not text:
        return ""
    return html.escape(str(text))

async def sadd(update: Update, context: CallbackContext):
    """Add character to shop"""
    user_id = update.effective_user.id
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪssɪᴏɴ")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b> /sadd &lt;id&gt; &lt;price&gt; [limit] [discount%] [featured]\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b> /sadd CHAR001 1000 5 20 yes",
            parse_mode="HTML"
        )
        return
    
    try:
        char_id = context.args[0]
        price = int(context.args[1])
        limit = None if len(context.args) < 3 or context.args[2].lower() in ["0", "unlimited"] else int(context.args[2])
        discount = max(0, min(int(context.args[3]), 90)) if len(context.args) >= 4 else 0
        featured = len(context.args) >= 5 and context.args[4].lower() in ["yes", "true", "1"]
        
        character = await collection.find_one({"id": char_id})
        if not character:
            await update.message.reply_text(f"⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ <code>{escape_html(char_id)}</code> ɴᴏᴛ ғᴏᴜɴᴅ", parse_mode="HTML")
            return
        
        existing = await shop_collection.find_one({"id": char_id})
        if existing:
            await update.message.reply_text("⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴀʟʀᴇᴀᴅʏ ɪɴ sʜᴏᴘ")
            return
        
        final_price = int(price * (1 - discount / 100))
        current_time_utc = datetime.utcnow()
        
        await shop_collection.insert_one({
            "id": char_id,
            "price": price,
            "original_price": price,
            "discount": discount,
            "final_price": final_price,
            "added_by": user_id,
            "added_at": current_time_utc,
            "limit": limit,
            "sold": 0,
            "featured": featured,
            "views": 0
        })
        
        char_name = escape_html(character.get('name', 'Unknown'))
        await update.message.reply_text(
            f"✨ <b>ᴀᴅᴅᴇᴅ ᴛᴏ sʜᴏᴘ!</b>\n\n"
            f"🎭 {char_name}\n"
            f"💎 {price:,} → <b>{final_price:,}</b> ɢᴏʟᴅ\n"
            f"🏷️ <b>{discount}%</b> ᴏғғ\n"
            f"🔢 ʟɪᴍɪᴛ: {'∞' if not limit else limit}\n"
            f"⭐ ғᴇᴀᴛᴜʀᴇᴅ: {'ʏᴇs' if featured else 'ɴᴏ'}",
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ғᴏʀᴍᴀᴛ")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {escape_html(str(e))}", parse_mode="HTML")

async def srm(update: Update, context: CallbackContext):
    """Remove character from shop"""
    user_id = update.effective_user.id
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪssɪᴏɴ")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("⚠️ <b>ᴜsᴀɢᴇ:</b> /srm &lt;character_id&gt;", parse_mode="HTML")
        return
    
    char_id = context.args[0]
    result = await shop_collection.delete_one({"id": char_id})
    
    if result.deleted_count:
        await update.message.reply_text(f"🗑️ <b>ʀᴇᴍᴏᴠᴇᴅ</b> {escape_html(char_id)}", parse_mode="HTML")
    else:
        await update.message.reply_text("⚠️ ɴᴏᴛ ғᴏᴜɴᴅ ɪɴ sʜᴏᴘ")

async def shop(update: Update, context: CallbackContext):
    """Display shop"""
    user_id = update.effective_user.id
    
    # Check for active auction first
    active_auction = await auction_collection.find_one({
        "status": "active",
        "end_time": {"$gt": datetime.utcnow()}
    })
    
    if active_auction:
        await show_auction(update, context, active_auction)
        return
    
    # Filter for discount items if requested
    filter_query = {}
    if context.args and context.args[0].lower() == "discount":
        filter_query = {"discount": {"$gt": 0}}
    
    cursor = shop_collection.find(filter_query).sort([("featured", -1), ("added_at", -1)])
    shop_items = await cursor.to_list(length=None)
    
    if not shop_items:
        await update.message.reply_text(
            "🏪 <b>sʜᴏᴘ ɪs ᴇᴍᴘᴛʏ</b>\n\nᴄʜᴇᴄᴋ ʙᴀᴄᴋ ʟᴀᴛᴇʀ!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="sr_reload")
            ]])
        )
        return
    
    context.user_data['shop_items'] = [item['id'] for item in shop_items]
    context.user_data['shop_page'] = 0
    await render_shop_page(update.message, context, user_id, 0)

def build_caption(character, shop_item, page, total, user_data=None):
    """Build shop item caption with proper HTML escaping"""
    price = shop_item["price"]
    final_price = shop_item.get("final_price", price)
    discount = shop_item.get("discount", 0)
    sold = shop_item.get("sold", 0)
    limit = shop_item.get("limit")
    featured = shop_item.get("featured", False)
    
    # Check if sold out or owned
    sold_out = limit and sold >= limit
    owned = False
    if user_data:
        user_chars = user_data.get("characters", [])
        owned = any(c.get("id") == character["id"] for c in user_chars)
    
    # Status badge
    status = ""
    if sold_out:
        status = "🚫 sᴏʟᴅ ᴏᴜᴛ"
    elif owned:
        status = "✅ ᴏᴡɴᴇᴅ"
    elif featured:
        status = "⭐ ғᴇᴀᴛᴜʀᴇᴅ"
    
    # Escape all text fields
    char_name = escape_html(character.get('name', 'Unknown'))
    char_anime = escape_html(character.get('anime', 'Unknown'))
    char_rarity = escape_html(character.get('rarity', 'Unknown'))
    
    caption = f"<b>🏪 sʜᴏᴘ {status}</b>\n\n"
    caption += f"✨ {char_name}\n"
    caption += f"🎭 {char_anime}\n"
    caption += f"💫 {char_rarity}\n\n"
    
    if discount > 0:
        caption += f"💎 <s>{price:,}</s> → <b>{final_price:,}</b> ɢᴏʟᴅ\n"
        caption += f"🏷️ <b>{discount}%</b> ᴏғғ!\n"
    else:
        caption += f"💎 <b>{final_price:,}</b> ɢᴏʟᴅ\n"
    
    # Stock and views
    stock_text = "∞" if not limit else f"{sold}/{limit}"
    caption += f"🔢 {stock_text} | 👁️ {shop_item.get('views', 0):,}\n"
    caption += f"📖 {page}/{total}"
    
    media_url = character.get("img_url", "")
    is_video = character.get("rarity") == "🎥 AMV"
    
    return caption, media_url, sold_out or owned, is_video

async def render_shop_page(message, context, user_id, page):
    """Render a shop page"""
    items = context.user_data.get('shop_items', [])
    if not items or page >= len(items):
        return
    
    char_id = items[page]
    character = await collection.find_one({"id": char_id})
    shop_item = await shop_collection.find_one({"id": char_id})
    user_data = await user_collection.find_one({"id": user_id})
    
    if not character or not shop_item:
        return
    
    # Increment view count
    await shop_collection.update_one({"id": char_id}, {"$inc": {"views": 1}})
    
    # Build caption and buttons
    caption, media_url, sold_out, is_video = build_caption(
        character, shop_item, page + 1, len(items), user_data
    )
    
    # Buy button
    buttons = []
    if sold_out:
        buttons.append([InlineKeyboardButton("🚫 ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ", callback_data="sna")])
    else:
        buttons.append([InlineKeyboardButton("💳 ʙᴜʏ", callback_data=f"sb_{char_id}")])
    
    # Navigation buttons
    if len(items) > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"sp_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{len(items)}", callback_data="spi"))
        if page < len(items) - 1:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"sp_{page+1}"))
        buttons.append(nav)
    
    # Bottom buttons
    buttons.append([
        InlineKeyboardButton("🏷️ ᴅɪsᴄᴏᴜɴᴛs", callback_data="ss_discount"),
        InlineKeyboardButton("🔄", callback_data="sr")
    ])
    
    markup = InlineKeyboardMarkup(buttons)
    
    try:
        if is_video and media_url:
            await message.reply_video(
                video=media_url,
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        elif media_url:
            await message.reply_photo(
                photo=media_url,
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        else:
            await message.reply_text(
                caption,
                parse_mode="HTML",
                reply_markup=markup
            )
    except BadRequest as e:
        await message.reply_text(
            caption,
            parse_mode="HTML",
            reply_markup=markup
        )

async def shist(update: Update, context: CallbackContext):
    """Show purchase history"""
    user_id = update.effective_user.id
    
    cursor = shop_history_collection.find({"user_id": user_id}).sort("purchase_date", -1).limit(10)
    history = await cursor.to_list(length=10)
    
    if not history:
        await update.message.reply_text(
            "📜 <b>ɴᴏ ᴘᴜʀᴄʜᴀsᴇ ʜɪsᴛᴏʀʏ</b>\n\n"
            "ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴍᴀᴅᴇ ᴀɴʏ ᴘᴜʀᴄʜᴀsᴇs ʏᴇᴛ",
            parse_mode="HTML"
        )
        return
    
    text = "<b>📜 ʏᴏᴜʀ ᴘᴜʀᴄʜᴀsᴇ ʜɪsᴛᴏʀʏ</b>\n\n"
    total = 0
    
    for i, record in enumerate(history, 1):
        char = await collection.find_one({"id": record["character_id"]})
        name = escape_html(char.get("name", "Unknown")) if char else "Unknown"
        price = record.get("price", 0)
        total += price
        
        # Convert to Kolkata time
        purchase_time = record.get("purchase_date", datetime.utcnow())
        purchase_kolkata = utc_to_kolkata(purchase_time)
        date_str = purchase_kolkata.strftime("%d %b, %I:%M %p")
        
        text += f"{i}. {name}\n"
        text += f"   💰 {price:,} ɢᴏʟᴅ | 📅 {date_str}\n\n"
    
    text += f"━━━━━━━━━━━━━\n💰 <b>ᴛᴏᴛᴀʟ sᴘᴇɴᴛ:</b> {total:,} ɢᴏʟᴅ"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def astart(update: Update, context: CallbackContext):
    """Start an auction"""
    user_id = update.effective_user.id
    
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪssɪᴏɴ")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b> /astart &lt;character_id&gt; &lt;starting_bid&gt; &lt;hours&gt;\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b> /astart CHAR001 5000 24",
            parse_mode="HTML"
        )
        return
    
    try:
        char_id = context.args[0]
        starting_bid = int(context.args[1])
        duration_hours = int(context.args[2])
        
        character = await collection.find_one({"id": char_id})
        if not character:
            await update.message.reply_text(
                f"⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ <code>{escape_html(char_id)}</code> ɴᴏᴛ ғᴏᴜɴᴅ",
                parse_mode="HTML"
            )
            return
        
        # Check for active auction
        active = await auction_collection.find_one({"status": "active"})
        if active:
            await update.message.reply_text("⚠️ ᴀɴ ᴀᴜᴄᴛɪᴏɴ ɪs ᴀʟʀᴇᴀᴅʏ ᴀᴄᴛɪᴠᴇ")
            return
        
        start_time_utc = datetime.utcnow()
        end_time_utc = start_time_utc + timedelta(hours=duration_hours)
        
        await auction_collection.insert_one({
            "character_id": char_id,
            "starting_bid": starting_bid,
            "current_bid": starting_bid,
            "highest_bidder": None,
            "start_time": start_time_utc,
            "end_time": end_time_utc,
            "status": "active",
            "created_by": user_id,
            "bid_count": 0
        })
        
        # Convert times to Kolkata
        end_time_kolkata = utc_to_kolkata(end_time_utc)
        
        char_name = escape_html(character.get('name', 'Unknown'))
        char_anime = escape_html(character.get('anime', 'Unknown'))
        
        caption = (
            f"<b>🔨 ᴀᴜᴄᴛɪᴏɴ sᴛᴀʀᴛᴇᴅ!</b>\n\n"
            f"💎 {char_name}\n"
            f"🎭 {char_anime}\n\n"
            f"💰 <b>sᴛᴀʀᴛɪɴɢ ʙɪᴅ:</b> {starting_bid:,} ɢᴏʟᴅ\n"
            f"⏰ <b>ᴇɴᴅs:</b> {end_time_kolkata.strftime('%d %b %Y, %I:%M %p IST')}\n"
            f"⌛ <b>ᴅᴜʀᴀᴛɪᴏɴ:</b> {duration_hours} hours\n\n"
            f"ᴜsᴇ /bid [ᴀᴍᴏᴜɴᴛ] ᴛᴏ ᴘʟᴀᴄᴇ ᴀ ʙɪᴅ"
        )
        
        buttons = [[InlineKeyboardButton("🔨 ᴠɪᴇᴡ ᴀᴜᴄᴛɪᴏɴ", callback_data="av")]]
        markup = InlineKeyboardMarkup(buttons)
        
        media_url = character.get("img_url", "")
        is_video = character.get("rarity") == "🎥 AMV"
        
        try:
            if is_video and media_url:
                await update.message.reply_video(
                    video=media_url,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup
                )
            elif media_url:
                await update.message.reply_photo(
                    photo=media_url,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup
                )
            else:
                await update.message.reply_text(
                    caption,
                    parse_mode="HTML",
                    reply_markup=markup
                )
        except BadRequest:
            await update.message.reply_text(
                caption,
                parse_mode="HTML",
                reply_markup=markup
            )
    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ғᴏʀᴍᴀᴛ")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {escape_html(str(e))}", parse_mode="HTML")

async def aend(update: Update, context: CallbackContext):
    """End the active auction"""
    user_id = update.effective_user.id
    
    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪssɪᴏɴ")
        return
    
    auction = await auction_collection.find_one({"status": "active"})
    if not auction:
        await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ")
        return
    
    winner_id = auction.get("highest_bidder")
    character = await collection.find_one({"id": auction["character_id"]})
    
    if winner_id:
        # Award character and deduct gold
        await user_collection.update_one(
            {"id": winner_id},
            {
                "$inc": {"balance": -auction["current_bid"]},
                "$push": {"characters": character}
            },
            upsert=True
        )
        
        try:
            winner_user = await context.bot.get_chat(winner_id)
            winner_name = escape_html(winner_user.first_name)
            winner_mention = f"<a href='tg://user?id={winner_id}'>{winner_name}</a>"
        except:
            winner_mention = f"User {winner_id}"
        
        char_name = escape_html(character.get('name', 'Unknown'))
        end_time_kolkata = utc_to_kolkata(datetime.utcnow())
        
        await update.message.reply_text(
            f"<b>🎊 ᴀᴜᴄᴛɪᴏɴ ᴇɴᴅᴇᴅ!</b>\n\n"
            f"💎 {char_name}\n"
            f"🏆 <b>ᴡɪɴɴᴇʀ:</b> {winner_mention}\n"
            f"💰 <b>ғɪɴᴀʟ ʙɪᴅ:</b> {auction['current_bid']:,} ɢᴏʟᴅ\n"
            f"📊 <b>ᴛᴏᴛᴀʟ ʙɪᴅs:</b> {auction.get('bid_count', 0)}\n"
            f"⏰ {end_time_kolkata.strftime('%d %b %Y, %I:%M %p IST')}",
            parse_mode="HTML"
        )
        
        # Notify winner
        try:
            await context.bot.send_message(
                chat_id=winner_id,
                text=(
                    f"🎉 <b>ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs!</b>\n\n"
                    f"ʏᴏᴜ ᴡᴏɴ <b>{char_name}</b> ғᴏʀ {auction['current_bid']:,} ɢᴏʟᴅ!"
                ),
                parse_mode="HTML"
            )
        except:
            pass
    else:
        await update.message.reply_text("⚠️ ɴᴏ ʙɪᴅs ᴡᴇʀᴇ ᴘʟᴀᴄᴇᴅ")
    
    await auction_collection.update_one(
        {"_id": auction["_id"]},
        {"$set": {"status": "ended", "ended_at": datetime.utcnow()}}
    )

async def bid(update: Update, context: CallbackContext):
    """Place a bid on active auction"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b> /bid &lt;amount&gt;\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b> /bid 10000",
            parse_mode="HTML"
        )
        return
    
    try:
        bid_amount = int(context.args[0])
        
        auction = await auction_collection.find_one({"status": "active"})
        if not auction:
            await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ")
            return
        
        # Check if auction ended
        if auction["end_time"] < datetime.utcnow():
            await update.message.reply_text("⚠️ ᴀᴜᴄᴛɪᴏɴ ʜᴀs ᴇɴᴅᴇᴅ")
            return
        
        # Minimum bid is 5% more than current
        min_bid = int(auction["current_bid"] * 1.05)
        
        if bid_amount < min_bid:
            await update.message.reply_text(
                f"⚠️ <b>ᴍɪɴɪᴍᴜᴍ ʙɪᴅ:</b> {min_bid:,} ɢᴏʟᴅ\n"
                f"<b>ᴄᴜʀʀᴇɴᴛ ʙɪᴅ:</b> {auction['current_bid']:,} ɢᴏʟᴅ",
                parse_mode="HTML"
            )
            return
        
        # Check user balance
        user_data = await user_collection.find_one({"id": user_id})
        balance = user_data.get("balance", 0) if user_data else 0
        
        if balance < bid_amount:
            await update.message.reply_text(
                f"⚠️ <b>ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ</b>\n\n"
                f"ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ: {balance:,} ɢᴏʟᴅ\n"
                f"ʙɪᴅ ᴀᴍᴏᴜɴᴛ: {bid_amount:,} ɢᴏʟᴅ",
                parse_mode="HTML"
            )
            return
        
        # Update auction
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
        
        # Record bid
        await bid_collection.insert_one({
            "auction_id": auction["_id"],
            "user_id": user_id,
            "amount": bid_amount,
            "timestamp": datetime.utcnow()
        })
        
        character = await collection.find_one({"id": auction["character_id"]})
        char_name = escape_html(character.get('name', 'Unknown'))
        
        await update.message.reply_text(
            f"✅ <b>ʙɪᴅ ᴘʟᴀᴄᴇᴅ!</b>\n\n"
            f"💎 {char_name}\n"
            f"💰 <b>ʏᴏᴜʀ ʙɪᴅ:</b> {bid_amount:,} ɢᴏʟᴅ\n"
            f"📊 <b>ɴᴇxᴛ ᴍɪɴ:</b> {int(bid_amount * 1.05):,} ɢᴏʟᴅ",
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {escape_html(str(e))}", parse_mode="HTML")

async def show_auction(update, context, auction):
    """Display active auction details"""
    character = await collection.find_one({"id": auction["character_id"]})
    
    if not character:
        await update.message.reply_text("⚠️ ᴀᴜᴄᴛɪᴏɴ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ")
        return
    
    # Calculate time left
    time_left = auction["end_time"] - datetime.utcnow()
    hours_left = int(time_left.total_seconds() / 3600)
    minutes_left = int((time_left.total_seconds() % 3600) / 60)
    
    # Convert times to Kolkata
    end_time_kolkata = utc_to_kolkata(auction["end_time"])
    
    char_name = escape_html(character.get('name', 'Unknown'))
    char_anime = escape_html(character.get('anime', 'Unknown'))
    
    # Get highest bidder info
    highest_bidder_text = "ɴᴏ ʙɪᴅs ʏᴇᴛ"
    if auction.get("highest_bidder"):
        try:
            bidder = await context.bot.get_chat(auction["highest_bidder"])
            bidder_name = escape_html(bidder.first_name)
            highest_bidder_text = f"<a href='tg://user?id={auction['highest_bidder']}'>{bidder_name}</a>"
        except:
            highest_bidder_text = f"User {auction['highest_bidder']}"
    
    caption = (
        f"<b>🔨 ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ</b>\n\n"
        f"💎 {char_name}\n"
        f"🎭 {char_anime}\n"
        f"💫 {escape_html(character.get('rarity', 'Unknown'))}\n\n"
        f"💰 <b>ᴄᴜʀʀᴇɴᴛ ʙɪᴅ:</b> {auction['current_bid']:,} ɢᴏʟᴅ\n"
        f"🏆 <b>ʜɪɢʜᴇsᴛ ʙɪᴅᴅᴇʀ:</b> {highest_bidder_text}\n"
        f"📊 <b>ᴛᴏᴛᴀʟ ʙɪᴅs:</b> {auction.get('bid_count', 0)}\n"
        f"⏰ <b>ᴇɴᴅs:</b> {end_time_kolkata.strftime('%d %b, %I:%M %p IST')}\n"
        f"⌛ <b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {hours_left}h {minutes_left}m\n\n"
        f"💡 ᴍɪɴ ʙɪᴅ: {int(auction['current_bid'] * 1.05):,} ɢᴏʟᴅ"
    )
    
    buttons = [[InlineKeyboardButton("🔨 ᴘʟᴀᴄᴇ ʙɪᴅ", callback_data="ab")]]
    markup = InlineKeyboardMarkup(buttons)
    
    media_url = character.get("img_url", "")
    is_video = character.get("rarity") == "🎥 AMV"
    
    try:
        if is_video and media_url:
            await update.message.reply_video(
                video=media_url,
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        elif media_url:
            await update.message.reply_photo(
                photo=media_url,
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        else:
            await update.message.reply_text(
                caption,
                parse_mode="HTML",
                reply_markup=markup
            )
    except BadRequest:
        await update.message.reply_text(
            caption,
            parse_mode="HTML",
            reply_markup=markup
        )

async def shop_callback(query, context):
    """Handle shop callback queries"""
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    
    if data.startswith("sp_"):
        # Navigate to specific page
        page = int(data.split("_")[1])
        context.user_data['shop_page'] = page
        await render_shop_page_edit(query, context, user_id, page)
    
    elif data == "sr":
        # Refresh current page
        page = context.user_data.get('shop_page', 0)
        await render_shop_page_edit(query, context, user_id, page)
    
    elif data == "sr_reload":
        # Reload entire shop
        await query.message.reply_text("🔄 ʀᴇʟᴏᴀᴅɪɴɢ sʜᴏᴘ...")
        cursor = shop_collection.find().sort([("featured", -1), ("added_at", -1)])
        shop_items = await cursor.to_list(length=None)
        
        if shop_items:
            context.user_data['shop_items'] = [item['id'] for item in shop_items]
            context.user_data['shop_page'] = 0
            await render_shop_page(query.message, context, user_id, 0)
        else:
            await query.message.reply_text("🏪 sʜᴏᴘ ɪs ᴇᴍᴘᴛʏ")
    
    elif data.startswith("sb_"):
        # Buy item
        char_id = data.split("_", 1)[1]
        await handle_buy(query, context, user_id, char_id)
    
    elif data == "ss_discount":
        # Show discount items
        await query.answer("🏷️ ғɪʟᴛᴇʀɪɴɢ ᴅɪsᴄᴏᴜɴᴛs...")
        cursor = shop_collection.find({"discount": {"$gt": 0}}).sort([("discount", -1)])
        shop_items = await cursor.to_list(length=None)
        
        if shop_items:
            context.user_data['shop_items'] = [item['id'] for item in shop_items]
            context.user_data['shop_page'] = 0
            await render_shop_page_edit(query, context, user_id, 0)
        else:
            await query.answer("⚠️ ɴᴏ ᴅɪsᴄᴏᴜɴᴛs ᴀᴠᴀɪʟᴀʙʟᴇ", show_alert=True)
    
    elif data == "spi":
        # Page info (do nothing)
        await query.answer()
    
    elif data == "sna":
        # Not available
        await query.answer("⚠️ ᴛʜɪs ɪᴛᴇᴍ ɪs ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ", show_alert=True)
    
    elif data == "av":
        # View auction
        auction = await auction_collection.find_one({"status": "active"})
        if auction:
            await query.answer("🔨 ᴀᴜᴄᴛɪᴏɴ ᴅᴇᴛᴀɪʟs")
        else:
            await query.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ", show_alert=True)
    
    elif data == "ab":
        # Place bid instruction
        await query.answer("💡 ᴜsᴇ /bid [ᴀᴍᴏᴜɴᴛ] ᴛᴏ ᴘʟᴀᴄᴇ ᴀ ʙɪᴅ", show_alert=True)

async def render_shop_page_edit(query, context, user_id, page):
    """Edit message to show different shop page"""
    items = context.user_data.get('shop_items', [])
    if not items or page >= len(items):
        await query.answer("⚠️ ᴘᴀɢᴇ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
        return
    
    char_id = items[page]
    character = await collection.find_one({"id": char_id})
    shop_item = await shop_collection.find_one({"id": char_id})
    user_data = await user_collection.find_one({"id": user_id})
    
    if not character or not shop_item:
        await query.answer("⚠️ ɪᴛᴇᴍ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
        return
    
    # Increment view count
    await shop_collection.update_one({"id": char_id}, {"$inc": {"views": 1}})
    
    caption, media_url, sold_out, is_video = build_caption(
        character, shop_item, page + 1, len(items), user_data
    )
    
    # Build buttons
    buttons = []
    if sold_out:
        buttons.append([InlineKeyboardButton("🚫 ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ", callback_data="sna")])
    else:
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
        InlineKeyboardButton("🏷️ ᴅɪsᴄᴏᴜɴᴛs", callback_data="ss_discount"),
        InlineKeyboardButton("🔄", callback_data="sr")
    ])
    
    markup = InlineKeyboardMarkup(buttons)
    
    try:
        await query.edit_message_caption(
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup
        )
    except BadRequest:
        # If can't edit (different media type), send new message
        try:
            await query.message.delete()
        except:
            pass
        
        try:
            if is_video and media_url:
                await query.message.reply_video(
                    video=media_url,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup
                )
            elif media_url:
                await query.message.reply_photo(
                    photo=media_url,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup
                )
            else:
                await query.message.reply_text(
                    caption,
                    parse_mode="HTML",
                    reply_markup=markup
                )
        except:
            pass

async def handle_buy(query, context, user_id, char_id):
    """Handle character purchase"""
    shop_item = await shop_collection.find_one({"id": char_id})
    character = await collection.find_one({"id": char_id})
    user_data = await user_collection.find_one({"id": user_id})
    
    if not shop_item or not character:
        await query.answer("⚠️ ɪᴛᴇᴍ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
        return
    
    # Check if sold out
    limit = shop_item.get("limit")
    sold = shop_item.get("sold", 0)
    if limit and sold >= limit:
        await query.answer("⚠️ sᴏʟᴅ ᴏᴜᴛ!", show_alert=True)
        return
    
    # Check if already owned
    if user_data:
        user_chars = user_data.get("characters", [])
        if any(c.get("id") == char_id for c in user_chars):
            await query.answer("⚠️ ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ᴏᴡɴ ᴛʜɪs!", show_alert=True)
            return
    
    # Check balance
    price = shop_item.get("final_price", shop_item["price"])
    balance = user_data.get("balance", 0) if user_data else 0
    
    if balance < price:
        await query.answer(
            f"⚠️ ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ\n\n"
            f"ɴᴇᴇᴅ: {price:,} ɢᴏʟᴅ\n"
            f"ʜᴀᴠᴇ: {balance:,} ɢᴏʟᴅ",
            show_alert=True
        )
        return
    
    # Process purchase
    await user_collection.update_one(
        {"id": user_id},
        {
            "$inc": {"balance": -price},
            "$push": {"characters": character}
        },
        upsert=True
    )
    
    # Update shop stats
    await shop_collection.update_one(
        {"id": char_id},
        {"$inc": {"sold": 1}}
    )
    
    # Record purchase history
    await shop_history_collection.insert_one({
        "user_id": user_id,
        "character_id": char_id,
        "price": price,
        "purchase_date": datetime.utcnow()
    })
    
    char_name = escape_html(character.get('name', 'Unknown'))
    new_balance = balance - price
    
    await query.answer(
        f"✨ ᴘᴜʀᴄʜᴀsᴇᴅ {char_name}!\n\n"
        f"💰 -{price:,} ɢᴏʟᴅ\n"
        f"💳 ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ: {new_balance:,}",
        show_alert=True
    )
    
    # Refresh the page
    page = context.user_data.get('shop_page', 0)
    await render_shop_page_edit(query, context, user_id, page)


# Register all handlers directly
application.add_handler(CommandHandler("shop", shop, block=False))
application.add_handler(CommandHandler("sadd", sadd, block=False))
application.add_handler(CommandHandler("srm", srm, block=False))
application.add_handler(CommandHandler("shist", shist, block=False))
application.add_handler(CommandHandler("astart", astart, block=False))
application.add_handler(CommandHandler("aend", aend, block=False))
application.add_handler(CommandHandler("bid", bid, block=False))
application.add_handler(CallbackQueryHandler(shop_callback, pattern=r"^s|^a", block=False))