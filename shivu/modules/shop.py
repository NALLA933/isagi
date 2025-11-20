import random
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler

from shivu import application, db, user_collection, CHARA_CHANNEL_ID, SUPPORT_CHAT

collection = db['anime_characters_lol']
shop_collection = db['shop']
characters_collection = collection
shop_history_collection = db['shop_history']

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
            "• /shop featured - ғᴇᴀᴛᴜʀᴇᴅ ɪᴛᴇᴍs\n"
            "• /shop cheap - ʟᴏᴡᴇsᴛ ᴘʀɪᴄᴇ ғɪʀsᴛ\n"
            "• /shop expensive - ʜɪɢʜᴇsᴛ ᴘʀɪᴄᴇ ғɪʀsᴛ\n"
            "• /shop discount - ʙᴇsᴛ ᴅɪsᴄᴏᴜɴᴛs ғɪʀsᴛ",
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
        action_buttons.append(InlineKeyboardButton("💳 ʙᴜʏ", callback_data=f"shop_buy_{char_id}"))
    
    if action_buttons:
        buttons.append(action_buttons)

    if total_pages > 1:
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"shop_page_{page-1}"))
        nav_buttons.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="shop_pageinfo"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"shop_page_{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    sort_buttons = [
        InlineKeyboardButton("⭐ ғᴇᴀᴛᴜʀᴇᴅ", callback_data="shop_sort_featured"),
        InlineKeyboardButton("💰 ᴄʜᴇᴀᴘ", callback_data="shop_sort_cheap")
    ]
    buttons.append(sort_buttons)
    
    sort_buttons2 = [
        InlineKeyboardButton("💎 ᴇxᴘᴇɴsɪᴠᴇ", callback_data="shop_sort_expensive"),
        InlineKeyboardButton("🏷️ ᴅɪsᴄᴏᴜɴᴛ", callback_data="shop_sort_discount")
    ]
    buttons.append(sort_buttons2)

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
            action_buttons.append(InlineKeyboardButton("💳 ʙᴜʏ", callback_data=f"shop_buy_{char_id}"))
        
        if action_buttons:
            buttons.append(action_buttons)

        if len(shop_items_ids) > 1:
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"shop_page_{page-1}"))
            nav_buttons.append(InlineKeyboardButton(f"{page+1}/{len(shop_items_ids)}", callback_data="shop_pageinfo"))
            if page < len(shop_items_ids) - 1:
                nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"shop_page_{page+1}"))

        if nav_buttons:
            buttons.append(nav_buttons)

        sort_buttons = [
            InlineKeyboardButton("⭐ ғᴇᴀᴛᴜʀᴇᴅ", callback_data="shop_sort_featured"),
            InlineKeyboardButton("💰 ᴄʜᴇᴀᴘ", callback_data="shop_sort_cheap")
        ]
        buttons.append(sort_buttons)
        
        sort_buttons2 = [
            InlineKeyboardButton("💎 ᴇxᴘᴇɴsɪᴠᴇ", callback_data="shop_sort_expensive"),
            InlineKeyboardButton("🏷️ ᴅɪsᴄᴏᴜɴᴛ", callback_data="shop_sort_discount")
        ]
        buttons.append(sort_buttons2)

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
        except Exception as e:
            try:
                await query.edit_message_caption(
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup
                )
            except:
                pass

    if data.startswith("shop_page_"):
        page = int(data.split("_")[2])
        await render_shop_page(page)

    elif data == "shop_pageinfo":
        await query.answer()

    elif data.startswith("shop_sort_"):
        sort_type = data.split("_")[2]
        
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

    elif data.startswith("shop_buy_"):
        char_id = data.split("_", 2)[2]

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
                InlineKeyboardButton("✅ ᴄᴏɴғɪʀᴍ", callback_data=f"shop_confirm_{char_id}"),
                InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="shop_cancel")
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

    elif data.startswith("shop_confirm_"):
        char_id = data.split("_", 2)[2]

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

    elif data == "shop_cancel":
        page = context.user_data.get('shop_page', 0)
        shop_items_ids = context.user_data.get('shop_items', [])

        if not shop_items_ids:
            await query.answer("⚠️ sᴇssɪᴏɴ ᴇxᴘɪʀᴇᴅ. ᴘʟᴇᴀsᴇ ᴜsᴇ /shop ᴀɢᴀɪɴ.", show_alert=True)
            return

        await render_shop_page(page)
        await query.answer("ᴘᴜʀᴄʜᴀsᴇ ᴄᴀɴᴄᴇʟʟᴇᴅ.", show_alert=False)

application.add_handler(CommandHandler("shop", shop, block=False))
application.add_handler(CommandHandler("addshop", addshop, block=False))
application.add_handler(CommandHandler("rmshop", rmshop, block=False))
application.add_handler(CommandHandler("updateshop", updateshop, block=False))
application.add_handler(CommandHandler("shophistory", shophistory, block=False))
application.add_handler(CallbackQueryHandler(shop_callback, pattern=r"^shop_", block=False))