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

ITEMS_PER_PAGE = 1

async def is_sudo_user(user_id: int) -> bool:
    return str(user_id) in sudo_users

async def addshop(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b> /addshop <character_id> <price> [limit] [discount%] [featured]\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇs:</b>\n"
            "• /addshop ABC123 5000\n"
            "• /addshop ABC123 5000 10\n"
            "• /addshop ABC123 5000 unlimited 20 yes",
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
            if limit_arg in ["0", "unlimited", "infinity"]:
                limit = None
            else:
                limit = int(context.args[2])
                if limit <= 0:
                    limit = None

        if len(context.args) >= 4:
            discount = int(context.args[3])
            discount = max(0, min(discount, 90))

        if len(context.args) >= 5:
            featured = context.args[4].lower() in ["yes", "true", "1", "featured"]

        if price <= 0:
            await update.message.reply_text("⚠️ ᴘʀɪᴄᴇ ᴍᴜsᴛ ʙᴇ ɢʀᴇᴀᴛᴇʀ ᴛʜᴀɴ 0.")
            return

        character = await characters_collection.find_one({"id": char_id})
        if not character:
            await update.message.reply_text(f"⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴡɪᴛʜ ɪᴅ {char_id} ɴᴏᴛ ғᴏᴜɴᴅ ɪɴ ᴅᴀᴛᴀʙᴀsᴇ.")
            return

        existing = await shop_collection.find_one({"id": char_id})
        if existing:
            await update.message.reply_text(f"⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ <b>{character['name']}</b> ɪs ᴀʟʀᴇᴀᴅʏ ɪɴ ᴛʜᴇ sʜᴏᴘ.", parse_mode="HTML")
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
        limit_text = "ᴜɴʟɪᴍɪᴛᴇᴅ" if limit is None else str(limit)
        discount_text = f"\n🏷️ ᴅɪsᴄᴏᴜɴᴛ: {discount}%" if discount > 0 else ""
        featured_text = "\n⭐ ғᴇᴀᴛᴜʀᴇᴅ ɪᴛᴇᴍ" if featured else ""
        
        await update.message.reply_text(
            f"✨ sᴜᴄᴄᴇssғᴜʟʟʏ ᴀᴅᴅᴇᴅ <b>{character['name']}</b> ᴛᴏ sʜᴏᴘ!\n"
            f"💎 ᴘʀɪᴄᴇ: {price:,} ɢᴏʟᴅ\n"
            f"💰 ғɪɴᴀʟ ᴘʀɪᴄᴇ: {final_price:,} ɢᴏʟᴅ\n"
            f"🔢 ʟɪᴍɪᴛ: {limit_text}"
            f"{discount_text}{featured_text}",
            parse_mode="HTML"
        )

    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ɪɴᴘᴜᴛ. ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀs.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

async def rmshop(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("⚠️ ᴜsᴀɢᴇ: /rmshop <character_id>")
        return

    try:
        char_id = context.args[0]
        shop_item = await shop_collection.find_one({"id": char_id})
        if not shop_item:
            await update.message.reply_text(f"⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴡɪᴛʜ ɪᴅ {char_id} ɪs ɴᴏᴛ ɪɴ ᴛʜᴇ sʜᴏᴘ.")
            return

        character = await characters_collection.find_one({"id": char_id})
        char_name = character['name'] if character else char_id

        await shop_collection.delete_one({"id": char_id})
        await update.message.reply_text(f"✨ sᴜᴄᴄᴇssғᴜʟʟʏ ʀᴇᴍᴏᴠᴇᴅ <b>{char_name}</b> ғʀᴏᴍ sʜᴏᴘ!", parse_mode="HTML")

    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

async def updateshop(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.")
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b> /updateshop <character_id> <field> <value>\n\n"
            "<b>ғɪᴇʟᴅs:</b> price, limit, discount, featured\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇs:</b>\n"
            "• /updateshop ABC123 price 8000\n"
            "• /updateshop ABC123 discount 30\n"
            "• /updateshop ABC123 featured yes",
            parse_mode="HTML"
        )
        return

    try:
        char_id = context.args[0]
        field = context.args[1].lower()
        value = " ".join(context.args[2:])

        shop_item = await shop_collection.find_one({"id": char_id})
        if not shop_item:
            await update.message.reply_text(f"⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴡɪᴛʜ ɪᴅ {char_id} ɪs ɴᴏᴛ ɪɴ ᴛʜᴇ sʜᴏᴘ.")
            return

        character = await characters_collection.find_one({"id": char_id})
        char_name = character['name'] if character else char_id

        if field == "price":
            new_price = int(value)
            if new_price <= 0:
                await update.message.reply_text("⚠️ ᴘʀɪᴄᴇ ᴍᴜsᴛ ʙᴇ ɢʀᴇᴀᴛᴇʀ ᴛʜᴀɴ 0.")
                return
            discount = shop_item.get("discount", 0)
            final_price = int(new_price * (1 - discount / 100))
            await shop_collection.update_one(
                {"id": char_id},
                {"$set": {"price": new_price, "original_price": new_price, "final_price": final_price}}
            )
            await update.message.reply_text(f"✨ ᴜᴘᴅᴀᴛᴇᴅ ᴘʀɪᴄᴇ ᴏғ <b>{char_name}</b> ᴛᴏ {new_price:,} ɢᴏʟᴅ!", parse_mode="HTML")

        elif field == "limit":
            if value.lower() in ["unlimited", "infinity", "0"]:
                new_limit = None
            else:
                new_limit = int(value)
            await shop_collection.update_one({"id": char_id}, {"$set": {"limit": new_limit}})
            limit_text = "ᴜɴʟɪᴍɪᴛᴇᴅ" if new_limit is None else str(new_limit)
            await update.message.reply_text(f"✨ ᴜᴘᴅᴀᴛᴇᴅ ʟɪᴍɪᴛ ᴏғ <b>{char_name}</b> ᴛᴏ {limit_text}!", parse_mode="HTML")

        elif field == "discount":
            new_discount = int(value)
            new_discount = max(0, min(new_discount, 90))
            price = shop_item.get("original_price", shop_item.get("price"))
            final_price = int(price * (1 - new_discount / 100))
            await shop_collection.update_one(
                {"id": char_id},
                {"$set": {"discount": new_discount, "final_price": final_price}}
            )
            await update.message.reply_text(f"✨ ᴜᴘᴅᴀᴛᴇᴅ ᴅɪsᴄᴏᴜɴᴛ ᴏғ <b>{char_name}</b> ᴛᴏ {new_discount}%!", parse_mode="HTML")

        elif field == "featured":
            new_featured = value.lower() in ["yes", "true", "1", "featured"]
            await shop_collection.update_one({"id": char_id}, {"$set": {"featured": new_featured}})
            status = "ғᴇᴀᴛᴜʀᴇᴅ" if new_featured else "ʀᴇɢᴜʟᴀʀ"
            await update.message.reply_text(f"✨ ᴜᴘᴅᴀᴛᴇᴅ <b>{char_name}</b> ᴛᴏ {status} sᴛᴀᴛᴜs!", parse_mode="HTML")

        else:
            await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ғɪᴇʟᴅ. ᴜsᴇ: price, limit, discount, ᴏʀ featured")

    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ᴠᴀʟᴜᴇ ᴘʀᴏᴠɪᴅᴇᴅ.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

def build_caption(waifu: dict, shop_item: dict, page: int, total: int, user_data=None) -> tuple:
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
    limit_text = "ᴜɴʟɪᴍɪᴛᴇᴅ" if limit is None else f"{sold}/{limit}"
    sold_out = False
    already_bought = False

    if limit is not None and sold >= limit:
        sold_out = True

    if user_data:
        user_chars = user_data.get("characters", [])
        if any((c.get("id") == wid or c.get("_id") == wid) for c in user_chars):
            already_bought = True

    status_emoji = ""
    status_text = ""
    
    if sold_out:
        status_emoji = "🚫"
        status_text = "\n\n⚠️ <b>sᴏʟᴅ ᴏᴜᴛ!</b>"
    elif already_bought:
        status_emoji = "✅"
        status_text = "\n\n✅ <b>ᴀʟʀᴇᴀᴅʏ ᴏᴡɴᴇᴅ!</b>"
    elif featured:
        status_emoji = "⭐"

    caption = (
        f"<b>╭─━━━━━━━━━━━━━━━━━─╮</b>\n"
        f"<b>│  🏪 ᴄʜᴀʀᴀᴄᴛᴇʀ sʜᴏᴘ {status_emoji} │</b>\n"
        f"<b>╰─━━━━━━━━━━━━━━━━━─╯</b>\n\n"
        f"✨ <b>{name}</b>\n\n"
        f"🎭 ᴀɴɪᴍᴇ: <code>{anime}</code>\n"
        f"💫 ʀᴀʀɪᴛʏ: {rarity}\n"
        f"🔖 ɪᴅ: <code>{wid}</code>\n"
    )
    
    if discount > 0 and not sold_out and not already_bought:
        caption += f"💎 ᴘʀɪᴄᴇ: <s>{price:,}</s> → <b>{final_price:,}</b> ɢᴏʟᴅ\n"
        caption += f"🏷️ ᴅɪsᴄᴏᴜɴᴛ: <b>{discount}%</b>\n"
    else:
        caption += f"💎 ᴘʀɪᴄᴇ: <b>{final_price:,}</b> ɢᴏʟᴅ\n"
    
    caption += (
        f"🔢 ʟɪᴍɪᴛ: {limit_text}\n"
        f"👁️ ᴠɪᴇᴡs: {views:,}\n"
    )
    
    if featured and not sold_out and not already_bought:
        caption += f"⭐ <b>ғᴇᴀᴛᴜʀᴇᴅ ɪᴛᴇᴍ</b>\n"
    
    caption += (
        f"📖 ᴘᴀɢᴇ: {page}/{total}"
        f"{status_text}\n\n"
    )
    
    if not sold_out and not already_bought:
        caption += "ᴛᴀᴘ <b>ʙᴜʏ</b> ᴛᴏ ᴘᴜʀᴄʜᴀsᴇ ᴛʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ!"
    
    return caption, img_url, sold_out or already_bought, is_video

async def shop(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    active_auction = await auction_collection.find_one({
        "status": "active",
        "end_time": {"$gt": datetime.utcnow()}
    })
    
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
            sort_by = [("added_at", -1)]
    
    shop_items = await shop_collection.find(filter_query).sort(sort_by).to_list(length=None)

    if not shop_items:
        await update.message.reply_text(
            "🏪 ᴛʜᴇ sʜᴏᴘ ɪs ᴄᴜʀʀᴇɴᴛʟʏ ᴇᴍᴘᴛʏ. ᴄʜᴇᴄᴋ ʙᴀᴄᴋ ʟᴀᴛᴇʀ!\n\n"
            "<b>sᴏʀᴛɪɴɢ ᴏᴘᴛɪᴏɴs:</b>\n"
            "• /shop featured\n"
            "• /shop cheap\n"
            "• /shop expensive\n"
            "• /shop discount",
            parse_mode="HTML"
        )
        return

    page = 0
    total_pages = len(shop_items)
    context.user_data['shop_items'] = [item['id'] for item in shop_items]
    context.user_data['shop_page'] = page
    context.user_data['shop_filter'] = context.args[0] if context.args else None

    char_id = shop_items[page]['id']
    character = await characters_collection.find_one({"id": char_id})
    user_data = await user_collection.find_one({"id": user_id})
    
    await shop_collection.update_one({"id": char_id}, {"$inc": {"views": 1}})
    
    caption, media_url, sold_out, is_video = build_caption(character, shop_items[page], page + 1, total_pages, user_data)

    buttons = []
    action_buttons = []
    nav_buttons = []

    if not sold_out:
        action_buttons.append(InlineKeyboardButton("💳 ʙᴜʏ", callback_data=f"shopbuy_{char_id}"))
    
    if action_buttons:
        buttons.append(action_buttons)

    if total_pages > 1:
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"shoppg_{page-1}"))
        nav_buttons.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="shoppginfo"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"shoppg_{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([
        InlineKeyboardButton("⭐ ғᴇᴀᴛᴜʀᴇᴅ", callback_data="shopsort_featured"),
        InlineKeyboardButton("💰 ᴄʜᴇᴀᴘ", callback_data="shopsort_cheap")
    ])
    
    buttons.append([
        InlineKeyboardButton("💎 ᴇxᴘᴇɴsɪᴠᴇ", callback_data="shopsort_expensive"),
        InlineKeyboardButton("🏷️ ᴅɪsᴄᴏᴜɴᴛ", callback_data="shopsort_discount")
    ])

    markup = InlineKeyboardMarkup(buttons)

    if is_video:
        msg = await update.message.reply_video(
            video=media_url,
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup
        )
    else:
        msg = await update.message.reply_photo(
            photo=media_url,
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup
        )

    context.user_data['shop_message_id'] = msg.message_id
    context.user_data['shop_chat_id'] = update.effective_chat.id

async def shophistory(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    try:
        history = await shop_history_collection.find({"user_id": user_id}).sort("purchase_date", -1).limit(10).to_list(length=10)
        
        if not history:
            await update.message.reply_text(
                "<b>╭─━━━━━━━━━━━━━━━━━━─╮</b>\n"
                "<b>│  📜 ᴘᴜʀᴄʜᴀsᴇ ʜɪsᴛᴏʀʏ  │</b>\n"
                "<b>╰─━━━━━━━━━━━━━━━━━━─╯</b>\n\n"
                "ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴍᴀᴅᴇ ᴀɴʏ ᴘᴜʀᴄʜᴀsᴇs ʏᴇᴛ!",
                parse_mode="HTML"
            )
            return
        
        text = (
            "<b>╭─━━━━━━━━━━━━━━━━━━─╮</b>\n"
            "<b>│  📜 ᴘᴜʀᴄʜᴀsᴇ ʜɪsᴛᴏʀʏ  │</b>\n"
            "<b>╰─━━━━━━━━━━━━━━━━━━─╯</b>\n\n"
        )
        
        total_spent = 0
        for i, record in enumerate(history, 1):
            character = await characters_collection.find_one({"id": record["character_id"]})
            name = character.get("name", "Unknown") if character else "Unknown"
            price = record.get("price", 0)
            date = record.get("purchase_date", datetime.utcnow())
            date_str = date.strftime("%d %b %Y")
            
            total_spent += price
            text += f"{i}. <b>{name}</b> - {price:,} ɢᴏʟᴅ\n   <i>{date_str}</i>\n\n"
        
        text += f"💰 <b>ᴛᴏᴛᴀʟ sᴘᴇɴᴛ:</b> {total_spent:,} ɢᴏʟᴅ"
        
        await update.message.reply_text(text, parse_mode="HTML")
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

async def startgiveaway(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.")
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b> /startgiveaway <character_id> <duration_hours> <min_activity>\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇs:</b>\n"
            "• /startgiveaway ABC123 24 10\n"
            "• /startgiveaway ABC123 48 20",
            parse_mode="HTML"
        )
        return

    try:
        char_id = context.args[0]
        duration_hours = int(context.args[1])
        min_activity = int(context.args[2])

        if duration_hours <= 0 or min_activity < 0:
            await update.message.reply_text("⚠️ ᴅᴜʀᴀᴛɪᴏɴ ᴀɴᴅ ᴍɪɴɪᴍᴜᴍ ᴀᴄᴛɪᴠɪᴛʏ ᴍᴜsᴛ ʙᴇ ᴘᴏsɪᴛɪᴠᴇ.")
            return

        character = await characters_collection.find_one({"id": char_id})
        if not character:
            await update.message.reply_text(f"⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴡɪᴛʜ ɪᴅ {char_id} ɴᴏᴛ ғᴏᴜɴᴅ.")
            return

        active_giveaway = await giveaway_collection.find_one({"status": "active"})
        if active_giveaway:
            await update.message.reply_text("⚠️ ᴛʜᴇʀᴇ's ᴀʟʀᴇᴀᴅʏ ᴀɴ ᴀᴄᴛɪᴠᴇ ɢɪᴠᴇᴀᴡᴀʏ!")
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
            f"<b>╭─━━━━━━━━━━━━━━━━━━─╮</b>\n"
            f"<b>│  🎉 ɢɪᴠᴇᴀᴡᴀʏ sᴛᴀʀᴛᴇᴅ!  │</b>\n"
            f"<b>╰─━━━━━━━━━━━━━━━━━━─╯</b>\n\n"
            f"🎁 <b>{character['name']}</b>\n"
            f"🎭 {character.get('anime', 'Unknown')}\n"
            f"💫 {character.get('rarity', 'Unknown')}\n\n"
            f"⏰ ᴇɴᴅs: <b>{end_time.strftime('%d %b %Y, %H:%M UTC')}</b>\n"
            f"📊 ᴍɪɴ ᴀᴄᴛɪᴠɪᴛʏ: <b>{min_activity}</b> ᴄʜᴀʀs ᴄᴏʟʟᴇᴄᴛᴇᴅ\n"
            f"👥 ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs: <b>0</b>\n\n"
            f"ᴄʟɪᴄᴋ ᴊᴏɪɴ ᴛᴏ ᴘᴀʀᴛɪᴄɪᴘᴀᴛᴇ!"
        )

        buttons = [[InlineKeyboardButton("🎫 ᴊᴏɪɴ ɢɪᴠᴇᴀᴡᴀʏ", callback_data="giveaway_join")]]
        markup = InlineKeyboardMarkup(buttons)

        if character.get("rarity") == "🎥 AMV":
            await update.message.reply_video(
                video=img_url,
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        else:
            await update.message.reply_photo(
                photo=img_url,
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )

    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ɪɴᴘᴜᴛ. ᴘʟᴇᴀsᴇ ᴜsᴇ ɴᴜᴍʙᴇʀs.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

async def endgiveaway(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.")
        return

    try:
        giveaway = await giveaway_collection.find_one({"status": "active"})
        if not giveaway:
            await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢɪᴠᴇᴀᴡᴀʏ ғᴏᴜɴᴅ.")
            return

        participants = giveaway.get("participants", [])
        if not participants:
            await update.message.reply_text("⚠️ ɴᴏ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs ɪɴ ᴛʜᴇ ɢɪᴠᴇᴀᴡᴀʏ.")
            await giveaway_collection.update_one(
                {"_id": giveaway["_id"]},
                {"$set": {"status": "ended"}}
            )
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
            {"$set": {"status": "ended", "winner": winner_id, "end_time": datetime.utcnow()}}
        )

        winner_user = await context.bot.get_chat(winner_id)
        winner_name = winner_user.first_name if winner_user else f"User {winner_id}"

        await update.message.reply_text(
            f"<b>╭─━━━━━━━━━━━━━━━━━━─╮</b>\n"
            f"<b>│  🎊 ɢɪᴠᴇᴀᴡᴀʏ ᴇɴᴅᴇᴅ!  │</b>\n"
            f"<b>╰─━━━━━━━━━━━━━━━━━━─╯</b>\n\n"
            f"🎁 <b>{character['name']}</b>\n"
            f"🏆 ᴡɪɴɴᴇʀ: <a href='tg://user?id={winner_id}'>{winner_name}</a>\n"
            f"👥 ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs: <b>{len(participants)}</b>\n\n"
            f"ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs! 🎉",
            parse_mode="HTML"
        )

    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

async def giveawaystatus(update: Update, context: CallbackContext):
    try:
        giveaway = await giveaway_collection.find_one({"status": "active"})
        if not giveaway:
            await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢɪᴠᴇᴀᴡᴀʏ.")
            return

        character = await characters_collection.find_one({"id": giveaway["character_id"]})
        participants = giveaway.get("participants", [])
        end_time = giveaway.get("end_time")
        time_left = end_time - datetime.utcnow()
        hours_left = int(time_left.total_seconds() / 3600)
        minutes_left = int((time_left.total_seconds() % 3600) / 60)

        await update.message.reply_text(
            f"<b>╭─━━━━━━━━━━━━━━━━━━─╮</b>\n"
            f"<b>│  🎉 ɢɪᴠᴇᴀᴡᴀʏ sᴛᴀᴛᴜs  │</b>\n"
            f"<b>╰─━━━━━━━━━━━━━━━━━━─╯</b>\n\n"
            f"🎁 <b>{character['name']}</b>\n"
            f"⏰ ᴛɪᴍᴇ ʟᴇғᴛ: <b>{hours_left}h {minutes_left}m</b>\n"
            f"👥 ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs: <b>{len(participants)}</b>\n"
            f"📊 ᴍɪɴ ᴀᴄᴛɪᴠɪᴛʏ: <b>{giveaway['min_activity']}</b> ᴄʜᴀʀs",
            parse_mode="HTML"
        )

    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

async def startauction(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.")
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b> /startauction <character_id> <starting_bid> <duration_hours>\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇs:</b>\n"
            "• /startauction ABC123 10000 24\n"
            "• /startauction ABC123 50000 48",
            parse_mode="HTML"
        )
        return

    try:
        char_id = context.args[0]
        starting_bid = int(context.args[1])
        duration_hours = int(context.args[2])

        if starting_bid <= 0 or duration_hours <= 0:
            await update.message.reply_text("⚠️ sᴛᴀʀᴛɪɴɢ ʙɪᴅ ᴀɴᴅ ᴅᴜʀᴀᴛɪᴏɴ ᴍᴜsᴛ ʙᴇ ᴘᴏsɪᴛɪᴠᴇ.")
            return

        character = await characters_collection.find_one({"id": char_id})
        if not character:
            await update.message.reply_text(f"⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴡɪᴛʜ ɪᴅ {char_id} ɴᴏᴛ ғᴏᴜɴᴅ.")
            return

        active_auction = await auction_collection.find_one({"status": "active"})
        if active_auction:
            await update.message.reply_text("⚠️ ᴛʜᴇʀᴇ's ᴀʟʀᴇᴀᴅʏ ᴀɴ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ!")
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
            f"<b>╭─━━━━━━━━━━━━━━━━━━─╮</b>\n"
            f"<b>│  🔨 ᴀᴜᴄᴛɪᴏɴ sᴛᴀʀᴛᴇᴅ!  │</b>\n"
            f"<b>╰─━━━━━━━━━━━━━━━━━━─╯</b>\n\n"
            f"💎 <b>{character['name']}</b>\n"
            f"🎭 {character.get('anime', 'Unknown')}\n"
            f"💫 {character.get('rarity', 'Unknown')}\n\n"
            f"💰 sᴛᴀʀᴛɪɴɢ ʙɪᴅ: <b>{starting_bid:,}</b> ɢᴏʟᴅ\n"
            f"🏆 ᴄᴜʀʀᴇɴᴛ ʙɪᴅ: <b>{starting_bid:,}</b> ɢᴏʟᴅ\n"
            f"👤 ʜɪɢʜᴇsᴛ ʙɪᴅᴅᴇʀ: <b>ɴᴏɴᴇ</b>\n"
            f"⏰ ᴇɴᴅs: <b>{end_time.strftime('%d %b %Y, %H:%M UTC')}</b>\n\n"
            f"ᴜsᴇ /shop ᴛᴏ ᴠɪᴇᴡ ᴀɴᴅ ᴘʟᴀᴄᴇ ʙɪᴅs!"
        )

        buttons = [[InlineKeyboardButton("🔨 ᴠɪᴇᴡ ᴀᴜᴄᴛɪᴏɴ", callback_data="auction_view")]]
        markup = InlineKeyboardMarkup(buttons)

        if character.get("rarity") == "🎥 AMV":
            await update.message.reply_video(
                video=img_url,
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        else:
            await update.message.reply_photo(
                photo=img_url,
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )

    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ɪɴᴘᴜᴛ. ᴘʟᴇᴀsᴇ ᴜsᴇ ɴᴜᴍʙᴇʀs.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

async def endauction(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.")
        return

    try:
        auction = await auction_collection.find_one({"status": "active"})
        if not auction:
            await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ ғᴏᴜɴᴅ.")
            return

        highest_bidder = auction.get("highest_bidder")
        character = await characters_collection.find_one({"id": auction["character_id"]})

        if highest_bidder:
            final_bid = auction.get("current_bid")
            
            await user_collection.update_one(
                {"id": highest_bidder},
                {
                    "$inc": {"balance": -final_bid},
                    "$push": {"characters": character}
                }
            )

            await bid_collection.insert_one({
                "auction_id": auction["_id"],
                "user_id": highest_bidder,
                "amount": final_bid,
                "timestamp": datetime.utcnow(),
                "won": True
            })

            winner_user = await context.bot.get_chat(highest_bidder)
            winner_name = winner_user.first_name if winner_user else f"User {highest_bidder}"

            await update.message.reply_text(
                f"<b>╭─━━━━━━━━━━━━━━━━━━─╮</b>\n"
                f"<b>│  🎊 ᴀᴜᴄᴛɪᴏɴ ᴇɴᴅᴇᴅ!  │</b>\n"
                f"<b>╰─━━━━━━━━━━━━━━━━━━─╯</b>\n\n"
                f"💎 <b>{character['name']}</b>\n"
                f"🏆 ᴡɪɴɴᴇʀ: <a href='tg://user?id={highest_bidder}'>{winner_name}</a>\n"
                f"💰 ғɪɴᴀʟ ʙɪᴅ: <b>{final_bid:,}</b> ɢᴏʟᴅ\n"
                f"📊 ᴛᴏᴛᴀʟ ʙɪᴅs: <b>{auction['bid_count']}</b>\n\n"
                f"ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs! 🎉",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                f"<b>╭─━━━━━━━━━━━━━━━━━━─╮</b>\n"
                f"<b>│  ⚠️ ᴀᴜᴄᴛɪᴏɴ ᴇɴᴅᴇᴅ  │</b>\n"
                f"<b>╰─━━━━━━━━━━━━━━━━━━─╯</b>\n\n"
                f"ɴᴏ ʙɪᴅs ᴡᴇʀᴇ ᴘʟᴀᴄᴇᴅ.",
                parse_mode="HTML"
            )

        await auction_collection.update_one(
            {"_id": auction["_id"]},
            {"$set": {"status": "ended", "end_time": datetime.utcnow()}}
        )

    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

async def auctionstatus(update: Update, context: CallbackContext):
    try:
        auction = await auction_collection.find_one({"status": "active"})
        if not auction:
            await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ.")
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

        await update.message.reply_text(
            f"<b>╭─━━━━━━━━━━━━━━━━━━─╮</b>\n"
            f"<b>│  🔨 ᴀᴜᴄᴛɪᴏɴ sᴛᴀᴛᴜs  │</b>\n"
            f"<b>╰─━━━━━━━━━━━━━━━━━━─╯</b>\n\n"
            f"💎 <b>{character['name']}</b>\n"
            f"💰 ᴄᴜʀʀᴇɴᴛ ʙɪᴅ: <b>{auction['current_bid']:,}</b> ɢᴏʟᴅ\n"
            f"👤 ʜɪɢʜᴇsᴛ ʙɪᴅᴅᴇʀ: <b>{bidder_text}</b>\n"
            f"⏰ ᴛɪᴍᴇ ʟᴇғᴛ: <b>{hours_left}h {minutes_left}m</b>\n"
            f"📊 ᴛᴏᴛᴀʟ ʙɪᴅs: <b>{auction['bid_count']}</b>",
            parse_mode="HTML"
        )

    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

async def show_auction_shop(update: Update, context: CallbackContext, auction: dict):
    user_id = update.effective_user.id
    char_id = auction["character_id"]
    
    character = await characters_collection.find_one({"id": char_id})
    if not character:
        await update.message.reply_text("⚠️ ᴀᴜᴄᴛɪᴏɴ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ.")
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
        f"<b>╭─━━━━━━━━━━━━━━━━━━─╮</b>\n"
        f"<b>│  🔨 ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ  │</b>\n"
        f"<b>╰─━━━━━━━━━━━━━━━━━━─╯</b>\n\n"
        f"💎 <b>{character['name']}</b>\n\n"
        f"🎭 ᴀɴɪᴍᴇ: <code>{character.get('anime', 'Unknown')}</code>\n"
        f"💫 ʀᴀʀɪᴛʏ: {character.get('rarity', 'Unknown')}\n"
        f"🔖 ɪᴅ: <code>{char_id}</code>\n\n"
        f"💰 ᴄᴜʀʀᴇɴᴛ ʙɪᴅ: <b>{auction['current_bid']:,}</b> ɢᴏʟᴅ\n"
        f"👤 ʜɪɢʜᴇsᴛ ʙɪᴅᴅᴇʀ: <b>{bidder_text}</b>\n"
        f"⏰ ᴛɪᴍᴇ ʟᴇғᴛ: <b>{hours_left}h {minutes_left}m</b>\n"
        f"📊 ᴛᴏᴛᴀʟ ʙɪᴅs: <b>{auction['bid_count']}</b>\n\n"
        f"ᴇɴᴛᴇʀ ʏᴏᴜʀ ʙɪᴅ ᴀᴍᴏᴜɴᴛ:"
    )

    context.user_data['auction_mode'] = True
    context.user_data['auction_id'] = str(auction['_id'])

    buttons = [
        [
            InlineKeyboardButton(f"+{auction['current_bid']//10:,}", callback_data=f"aucbid_{auction['current_bid']//10}"),
            InlineKeyboardButton(f"+{auction['current_bid']//5:,}", callback_data=f"aucbid_{auction['current_bid']//5}")
        ],
        [
            InlineKeyboardButton(f"+{auction['current_bid']//2:,}", callback_data=f"aucbid_{auction['current_bid']//2}"),
            InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="auc_cancel")
        ]
    ]
    markup = InlineKeyboardMarkup(buttons)

    if is_video:
        msg = await update.message.reply_video(
            video=img_url,
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup
        )
    else:
        msg = await update.message.reply_photo(
            photo=img_url,
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup
        )

    context.user_data['auction_message_id'] = msg.message_id

async def placebiد(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("⚠️ <b>ᴜsᴀɢᴇ:</b> /bid <amount>\n\n<b>ᴇxᴀᴍᴘʟᴇ:</b> /bid 15000", parse_mode="HTML")
        return

    try:
        bid_amount = int(context.args[0])
        
        auction = await auction_collection.find_one({"status": "active"})
        if not auction:
            await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ ғᴏᴜɴᴅ.")
            return

        current_bid = auction.get("current_bid")
        min_bid = int(current_bid * 1.05)

        if bid_amount < min_bid:
            await update.message.reply_text(f"⚠️ ʙɪᴅ ᴍᴜsᴛ ʙᴇ ᴀᴛ ʟᴇᴀsᴛ <b>{min_bid:,}</b> ɢᴏʟᴅ (5% ᴍᴏʀᴇ ᴛʜᴀɴ ᴄᴜʀʀᴇɴᴛ ʙɪᴅ).", parse_mode="HTML")
            return

        user_data = await user_collection.find_one({"id": user_id})
        balance = user_data.get("balance", 0) if user_data else 0

        if balance < bid_amount:
            await update.message.reply_text(f"⚠️ ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ! ʏᴏᴜ ʜᴀᴠᴇ <b>{balance:,}</b> ɢᴏʟᴅ.", parse_mode="HTML")
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
            f"<b>╭─━━━━━━━━━━━━━━━━━━─╮</b>\n"
            f"<b>│  ✅ ʙɪᴅ ᴘʟᴀᴄᴇᴅ!  │</b>\n"
            f"<b>╰─━━━━━━━━━━━━━━━━━━─╯</b>\n\n"
            f"💎 <b>{character['name']}</b>\n"
            f"💰 ʏᴏᴜʀ ʙɪᴅ: <b>{bid_amount:,}</b> ɢᴏʟᴅ\n\n"
            f"ɢᴏᴏᴅ ʟᴜᴄᴋ! 🍀",
            parse_mode="HTML"
        )

    except ValueError:
        await update.message.reply_text("⚠️ ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")

async def shop_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    async def render_shop_page(page):
        shop_items_ids = context.user_data.get('shop_items', [])
        if not shop_items_ids or page >= len(shop_items_ids):
            await query.answer("⚠️ ɪɴᴠᴀʟɪᴅ ᴘᴀɢᴇ.", show_alert=True)
            return

        context.user_data['shop_page'] = page
        char_id = shop_items_ids[page]

        character = await characters_collection.find_one({"id": char_id})
        shop_item = await shop_collection.find_one({"id": char_id})
        user_data = await user_collection.find_one({"id": user_id})

        if not character or not shop_item:
            await query.answer("⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ.", show_alert=True)
            return

        await shop_collection.update_one({"id": char_id}, {"$inc": {"views": 1}})

        caption, media_url, sold_out, is_video = build_caption(character, shop_item, page + 1, len(shop_items_ids), user_data)

        buttons = []
        action_buttons = []
        nav_buttons = []

        if not sold_out:
            action_buttons.append(InlineKeyboardButton("💳 ʙᴜʏ", callback_data=f"shopbuy_{char_id}"))
        
        if action_buttons:
            buttons.append(action_buttons)

        if len(shop_items_ids) > 1:
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"shoppg_{page-1}"))
            nav_buttons.append(InlineKeyboardButton(f"{page+1}/{len(shop_items_ids)}", callback_data="shoppginfo"))
            if page < len(shop_items_ids) - 1:
                nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"shoppg_{page+1}"))

        if nav_buttons:
            buttons.append(nav_buttons)

        buttons.append([
            InlineKeyboardButton("⭐ ғᴇᴀᴛᴜʀᴇᴅ", callback_data="shopsort_featured"),
            InlineKeyboardButton("💰 ᴄʜᴇᴀᴘ", callback_data="shopsort_cheap")
        ])
        
        buttons.append([
            InlineKeyboardButton("💎 ᴇxᴘᴇɴsɪᴠᴇ", callback_data="shopsort_expensive"),
            InlineKeyboardButton("🏷️ ᴅɪsᴄᴏᴜɴᴛ", callback_data="shopsort_discount")
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
        except:
            try:
                await query.edit_message_caption(
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup
                )
            except:
                pass

    if data.startswith("shoppg_"):
        page = int(data.split("_")[1])
        await render_shop_page(page)

    elif data == "shoppginfo":
        await query.answer()

    elif data.startswith("shopsort_"):
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
            sort_by = [("added_at", -1)]
        
        shop_items = await shop_collection.find(filter_query).sort(sort_by).to_list(length=None)
        
        if not shop_items:
            await query.answer("⚠️ ɴᴏ ɪᴛᴇᴍs ᴀᴠᴀɪʟᴀʙʟᴇ.", show_alert=True)
            return
        
        context.user_data['shop_items'] = [item['id'] for item in shop_items]
        context.user_data['shop_page'] = 0
        context.user_data['shop_filter'] = sort_type
        
        await render_shop_page(0)
        await query.answer(f"sᴏʀᴛᴇᴅ ʙʏ {sort_type}", show_alert=False)

    elif data.startswith("shopbuy_"):
        char_id = data.split("_", 1)[1]

        shop_item = await shop_collection.find_one({"id": char_id})
        character = await characters_collection.find_one({"id": char_id})
        user_data = await user_collection.find_one({"id": user_id})

        if not shop_item or not character:
            await query.answer("⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ.", show_alert=True)
            return

        limit = shop_item.get("limit", None)
        sold = shop_item.get("sold", 0)
        user_chars = user_data.get("characters", []) if user_data else []
        already_bought = any((c.get("id") == char_id or c.get("_id") == char_id) for c in user_chars)

        if (limit is not None and sold >= limit) or already_bought:
            await query.answer("⚠️ sᴏʟᴅ ᴏᴜᴛ ᴏʀ ᴀʟʀᴇᴀᴅʏ ᴏᴡɴᴇᴅ!", show_alert=True)
            await query.edit_message_caption(
                caption="⚠️ <b>sᴏʟᴅ ᴏᴜᴛ ᴏʀ ᴀʟʀᴇᴀᴅʏ ᴏᴡɴᴇᴅ!</b>",
                parse_mode="HTML"
            )
            return

        price = shop_item.get("final_price", shop_item.get("price", 0))
        discount = shop_item.get("discount", 0)
        
        discount_text = ""
        if discount > 0:
            original_price = shop_item.get("original_price", price)
            discount_text = f"🏷️ ᴅɪsᴄᴏᴜɴᴛ: <b>{discount}%</b>\n💎 ᴏʀɪɢɪɴᴀʟ: <s>{original_price:,}</s>\n"
        
        buttons = [
            [
                InlineKeyboardButton("✅ ᴄᴏɴғɪʀᴍ", callback_data=f"shopconf_{char_id}"),
                InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="shopcancel")
            ]
        ]
        markup = InlineKeyboardMarkup(buttons)

        await query.edit_message_caption(
            caption=f"<b>╭─━━━━━━━━━━━━━━━━━─╮</b>\n"
                    f"<b>│  💳 ᴄᴏɴғɪʀᴍ ᴘᴜʀᴄʜᴀsᴇ  │</b>\n"
                    f"<b>╰─━━━━━━━━━━━━━━━━━─╯</b>\n\n"
                    f"✨ <b>{character['name']}</b>\n"
                    f"🎭 {character.get('anime', 'Unknown')}\n"
                    f"💫 {character.get('rarity', 'Unknown')}\n\n"
                    f"{discount_text}"
                    f"💰 ғɪɴᴀʟ ᴘʀɪᴄᴇ: <b>{price:,}</b> ɢᴏʟᴅ\n\n"
                    f"ᴀʀᴇ ʏᴏᴜ sᴜʀᴇ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ʙᴜʏ ᴛʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ?",
            parse_mode="HTML",
            reply_markup=markup
        )

    elif data.startswith("shopconf_"):
        char_id = data.split("_", 1)[1]

        shop_item = await shop_collection.find_one({"id": char_id})
        character = await characters_collection.find_one({"id": char_id})
        user_data = await user_collection.find_one({"id": user_id})

        if not shop_item or not character:
            await query.answer("⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ.", show_alert=True)
            return

        limit = shop_item.get("limit", None)
        sold = shop_item.get("sold", 0)
        user_chars = user_data.get("characters", []) if user_data else []
        already_bought = any((c.get("id") == char_id or c.get("_id") == char_id) for c in user_chars)

        if (limit is not None and sold >= limit) or already_bought:
            await query.edit_message_caption(
                caption=f"<b>╭─━━━━━━━━━━━━━━━━━─╮</b>\n"
                        f"<b>│  ⚠️ sᴏʟᴅ ᴏᴜᴛ │</b>\n"
                        f"<b>╰─━━━━━━━━━━━━━━━━━─╯</b>\n\n"
                        f"ᴛʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ ᴄᴀɴɴᴏᴛ ʙᴇ ʙᴏᴜɢʜᴛ ᴀɢᴀɪɴ.",
                parse_mode="HTML"
            )
            await query.answer("⚠️ sᴏʟᴅ ᴏᴜᴛ ᴏʀ ᴀʟʀᴇᴀᴅʏ ᴏᴡɴᴇᴅ!", show_alert=True)
            return

        price = shop_item.get("final_price", shop_item.get("price", 0))
        balance = user_data.get("balance", 0) if user_data else 0

        if balance < price:
            await query.answer("⚠️ ɴᴏᴛ ᴇɴᴏᴜɢʜ ɢᴏʟᴅ!", show_alert=True)
            await query.edit_message_caption(
                caption=f"<b>╭─━━━━━━━━━━━━━━━━━━━─╮</b>\n"
                        f"<b>│  ⚠️ ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ │</b>\n"
                        f"<b>╰─━━━━━━━━━━━━━━━━━━━─╯</b>\n\n"
                        f"ʏᴏᴜ ɴᴇᴇᴅ <b>{price:,}</b> ɢᴏʟᴅ ʙᴜᴛ ᴏɴʟʏ ʜᴀᴠᴇ <b>{balance:,}</b> ɢᴏʟᴅ.\n"
                        f"ᴜsᴇ /bal ᴛᴏ ᴄʜᴇᴄᴋ ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ.",
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
        
        await shop_collection.update_one(
            {"id": char_id},
            {"$inc": {"sold": 1}}
        )

        await shop_history_collection.insert_one({
            "user_id": user_id,
            "character_id": char_id,
            "price": price,
            "purchase_date": datetime.utcnow()
        })

        await query.edit_message_caption(
            caption=f"<b>╭─━━━━━━━━━━━━━━━━━─╮</b>\n"
                    f"<b>│  ✨ ᴘᴜʀᴄʜᴀsᴇ sᴜᴄᴄᴇss! │</b>\n"
                    f"<b>╰─━━━━━━━━━━━━━━━━━─╯</b>\n\n"
                    f"ʏᴏᴜ ʙᴏᴜɢʜᴛ <b>{character['name']}</b> ғᴏʀ <b>{price:,}</b> ɢᴏʟᴅ!\n"
                    f"ᴛʜᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs ʙᴇᴇɴ ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ʜᴀʀᴇᴍ.\n\n"
                    f"💰 ʀᴇᴍᴀɪɴɪɴɢ ʙᴀʟᴀɴᴄᴇ: <b>{balance - price:,}</b> ɢᴏʟᴅ",
            parse_mode="HTML"
        )
        await query.answer("✨ ᴘᴜʀᴄʜᴀsᴇ sᴜᴄᴄᴇssғᴜʟ!", show_alert=False)

    elif data == "shopcancel":
        page = context.user_data.get('shop_page', 0)
        shop_items_ids = context.user_data.get('shop_items', [])

        if not shop_items_ids:
            await query.answer("⚠️ sᴇssɪᴏɴ ᴇxᴘɪʀᴇᴅ. ᴘʟᴇᴀsᴇ ᴜsᴇ /shop ᴀɢᴀɪɴ.", show_alert=True)
            return

        await render_shop_page(page)
        await query.answer("ᴘᴜʀᴄʜᴀsᴇ ᴄᴀɴᴄᴇʟʟᴇᴅ.", show_alert=False)

async def giveaway_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "giveaway_join":
        giveaway = await giveaway_collection.find_one({"status": "active"})
        if not giveaway:
            await query.answer("⚠️ ɢɪᴠᴇᴀᴡᴀʏ ʜᴀs ᴇɴᴅᴇᴅ.", show_alert=True)
            return

        user_data = await user_collection.find_one({"id": user_id})
        if not user_data:
            await query.answer("⚠️ ʏᴏᴜ ɴᴇᴇᴅ ᴛᴏ sᴛᴀʀᴛ ᴘʟᴀʏɪɴɢ ғɪʀsᴛ!", show_alert=True)
            return

        user_chars = user_data.get("characters", [])
        if len(user_chars) < giveaway.get("min_activity", 0):
            await query.answer(
                f"⚠️ ʏᴏᴜ ɴᴇᴇᴅ ᴀᴛ ʟᴇᴀsᴛ {giveaway['min_activity']} ᴄʜᴀʀᴀᴄᴛᴇʀs ᴛᴏ ᴊᴏɪɴ!",
                show_alert=True
            )
            return

        if user_id in giveaway.get("participants", []):
            await query.answer("⚠️ ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ ᴛʜɪs ɢɪᴠᴇᴀᴡᴀʏ!", show_alert=True)
            return

        await giveaway_collection.update_one(
            {"_id": giveaway["_id"]},
            {"$push": {"participants": user_id}}
        )

        participants_count = len(giveaway.get("participants", [])) + 1
        character = await characters_collection.find_one({"id": giveaway["character_id"]})
        end_time = giveaway.get("end_time")

        caption = (
            f"<b>╭─━━━━━━━━━━━━━━━━━━─╮</b>\n"
            f"<b>│  🎉 ɢɪᴠᴇᴀᴡᴀʏ sᴛᴀʀᴛᴇᴅ!  │</b>\n"
            f"<b>╰─━━━━━━━━━━━━━━━━━━─╯</b>\n\n"
            f"🎁 <b>{character['name']}</b>\n"
            f"🎭 {character.get('anime', 'Unknown')}\n"
            f"💫 {character.get('rarity', 'Unknown')}\n\n"
            f"⏰ ᴇɴᴅs: <b>{end_time.strftime('%d %b %Y, %H:%M UTC')}</b>\n"
            f"📊 ᴍɪɴ ᴀᴄᴛɪᴠɪᴛʏ: <b>{giveaway['min_activity']}</b> ᴄʜᴀʀs ᴄᴏʟʟᴇᴄᴛᴇᴅ\n"
            f"👥 ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs: <b>{participants_count}</b>\n\n"
            f"ᴄʟɪᴄᴋ ᴊᴏɪɴ ᴛᴏ ᴘᴀʀᴛɪᴄɪᴘᴀᴛᴇ!"
        )

        buttons = [[InlineKeyboardButton("🎫 ᴊᴏɪɴ ɢɪᴠᴇᴀᴡᴀʏ", callback_data="giveaway_join")]]
        markup = InlineKeyboardMarkup(buttons)

        try:
            await query.edit_message_caption(
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        except:
            pass

        await query.answer("✅ ʏᴏᴜ ʜᴀᴠᴇ ᴊᴏɪɴᴇᴅ ᴛʜᴇ ɢɪᴠᴇᴀᴡᴀʏ!", show_alert=False)

async def auction_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "auction_view":
        auction = await auction_collection.find_one({"status": "active"})
        if not auction:
            await query.answer("⚠️ ᴀᴜᴄᴛɪᴏɴ ʜᴀs ᴇɴᴅᴇᴅ.", show_alert=True)
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
            f"<b>╭─━━━━━━━━━━━━━━━━━━─╮</b>\n"
            f"<b>│  🔨 ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ  │</b>\n"
            f"<b>╰─━━━━━━━━━━━━━━━━━━─╯</b>\n\n"
            f"💎 <b>{character['name']}</b>\n\n"
            f"💰 ᴄᴜʀʀᴇɴᴛ ʙɪᴅ: <b>{auction['current_bid']:,}</b> ɢᴏʟᴅ\n"
            f"👤 ʜɪɢʜᴇsᴛ ʙɪᴅᴅᴇʀ: <b>{bidder_text}</b>\n"
            f"⏰ ᴛɪᴍᴇ ʟᴇғᴛ: <b>{hours_left}h {minutes_left}m</b>\n"
            f"📊 ᴛᴏᴛᴀʟ ʙɪᴅs: <b>{auction['bid_count']}</b>\n\n"
            f"ᴜsᴇ /bid <amount> ᴛᴏ ᴘʟᴀᴄᴇ ʏᴏᴜʀ ʙɪᴅ!"
        )

        try:
            await query.edit_message_caption(
                caption=caption,
                parse_mode="HTML"
            )
        except:
            pass

    elif data.startswith("aucbid_"):
        increment = int(data.split("_")[1])
        auction = await auction_collection.find_one({"status": "active"})
        
        if not auction:
            await query.answer("⚠️ ᴀᴜᴄᴛɪᴏɴ ʜᴀs ᴇɴᴅᴇᴅ.", show_alert=True)
            return

        bid_amount = auction.get("current_bid") + increment
        user_data = await user_collection.find_one({"id": user_id})
        balance = user_data.get("balance", 0) if user_data else 0

        if balance < bid_amount:
            await query.answer(f"⚠️ ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ! ʏᴏᴜ ʜᴀᴠᴇ {balance:,} ɢᴏʟᴅ.", show_alert=True)
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

        await query.answer(f"✅ ʙɪᴅ ᴘʟᴀᴄᴇᴅ: {bid_amount:,} ɢᴏʟᴅ!", show_alert=False)

    elif data == "auc_cancel":
        await query.answer("ᴀᴜᴄᴛɪᴏɴ ᴄᴀɴᴄᴇʟʟᴇᴅ.", show_alert=False)

application.add_handler(CommandHandler("shop", shop, block=False))
application.add_handler(CommandHandler("addshop", addshop, block=False))
application.add_handler(CommandHandler("rmshop", rmshop, block=False))
application.add_handler(CommandHandler("updateshop", updateshop, block=False))
application.add_handler(CommandHandler("shophistory", shophistory, block=False))
application.add_handler(CommandHandler("startgiveaway", startgiveaway, block=False))
application.add_handler(CommandHandler("endgiveaway", endgiveaway, block=False))
application.add_handler(CommandHandler("giveawaystatus", giveawaystatus, block=False))
application.add_handler(CommandHandler("startauction", startauction, block=False))
application.add_handler(CommandHandler("endauction", endauction, block=False))
application.add_handler(CommandHandler("auctionstatus", auctionstatus, block=False))
application.add_handler(CommandHandler("bid", placebiد, block=False))
application.add_handler(CallbackQueryHandler(shop_callback, pattern=r"^shop", block=False))
application.add_handler(CallbackQueryHandler(giveaway_callback, pattern=r"^giveaway_", block=False))
application.add_handler(CallbackQueryHandler(auction_callback, pattern=r"^auc", block=False))