import random 
import asyncio
from datetime import datetime, timedelta 
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto 
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler 
from shivu import application, db, user_collection 

collection = db['anime_characters_lol'] 
luv_config_collection = db['luv_config'] 
sudo_users = ["8297659126", "8420981179", "5147822244"] 
super_admin = ["8420981179", "6863917190"]

DEFAULT_CONFIG = { 
    "rarities": { 
        "🟢 Common": {"weight": 60, "min_price": 1500, "max_price": 2500}, 
        "🟣 Rare": {"weight": 25, "min_price": 4000, "max_price": 6000}, 
        "🟡 Legendary": {"weight": 10, "min_price": 8000, "max_price": 12000}, 
        "💮 Special Edition": {"weight": 5, "min_price": 20000, "max_price": 30000} 
    }, 
    "refresh_cost": 20000, 
    "refresh_limit": 2, 
    "store_items": 3, 
    "cooldown_hours": 24 
} 

panel_owners = {}
character_prices = {}

async def get_config(): 
    cfg = await luv_config_collection.find_one({"_id": "luv_config"}) 
    if not cfg: 
        await luv_config_collection.insert_one({"_id": "luv_config", **DEFAULT_CONFIG}) 
        return DEFAULT_CONFIG 
    return cfg 

async def get_rarity(cfg): 
    rarities = cfg['rarities'] 
    return random.choices(list(rarities.keys()), [rarities[r]['weight'] for r in rarities], k=1)[0] 

def get_random_price(cfg, rarity):
    rarity_data = cfg['rarities'].get(rarity, {})
    min_price = rarity_data.get('min_price', 1000)
    max_price = rarity_data.get('max_price', 5000)
    return random.randint(min_price, max_price)

async def generate_chars(uid, cfg): 
    chars = [] 
    if uid not in character_prices:
        character_prices[uid] = {}
    
    for _ in range(cfg.get('store_items', 3)): 
        rarity = await get_rarity(cfg) 
        pipe = [{'$match': {'rarity': rarity}}, {'$sample': {'size': 1}}] 
        char = await collection.aggregate(pipe).to_list(length=1) 
        if char: 
            char_data = char[0]
            cid = str(char_data.get("id") or char_data.get("_id"))
            character_prices[uid][cid] = get_random_price(cfg, rarity)
            chars.append(char_data) 
    return chars 

async def get_luv_data(uid): 
    user = await user_collection.find_one({"id": uid}) 
    return user.get('private_store', {'characters': [], 'last_reset': None, 'refresh_count': 0, 'purchased': []}) if user else None 

async def update_luv_data(uid, data): 
    await user_collection.update_one({"id": uid}, {"$set": {"private_store": data}}, upsert=True) 

def time_left(target): 
    if not target: 
        return "ᴀᴠᴀɪʟᴀʙʟᴇ ɴᴏᴡ" 
    if isinstance(target, str): 
        target = datetime.fromisoformat(target) 
    diff = target - datetime.utcnow() 
    if diff.total_seconds() <= 0: 
        return "ᴀᴠᴀɪʟᴀʙʟᴇ ɴᴏᴡ" 
    h, m = int(diff.total_seconds() // 3600), int((diff.total_seconds() % 3600) // 60) 
    return f"{h}ʜ {m}ᴍ" 

async def build_caption(char, cfg, page, total, luv_data, balance, uid): 
    cid = str(char.get("id") or char.get("_id"))
    name = char.get("name", "Unknown") 
    anime = char.get("anime", "Unknown") 
    rarity = char.get("rarity", "Unknown") 
    
    price = character_prices.get(uid, {}).get(cid, 0)
    if price == 0:
        rarity_data = cfg['rarities'].get(rarity, {})
        price = rarity_data.get('min_price', 1000)

    refresh_left = max(0, cfg.get('refresh_limit', 2) - luv_data.get('refresh_count', 0)) 
    last_reset = luv_data.get('last_reset') 
    if last_reset: 
        if isinstance(last_reset, str): 
            last_reset = datetime.fromisoformat(last_reset) 
        next_reset = last_reset + timedelta(hours=cfg.get('cooldown_hours', 24)) 
        time_rem = time_left(next_reset) 
    else: 
        time_rem = "ᴀᴠᴀɪʟᴀʙʟᴇ ɴᴏᴡ" 

    purchased = luv_data.get('purchased', []) 
    status = "⊗ ᴀʟʀᴇᴀᴅʏ ᴏᴡɴᴇᴅ" if cid in purchased else f"⊙ {price} ɢᴏʟᴅ" 

    return ( 
        f"╭────────────────╮\n" 
        f"│   ＰＲＩＶＡＴＥ ＳＴＯＲＥ   │\n" 
        f"╰────────────────╯\n\n" 
        f"⟡ ɴᴀᴍᴇ: <b>{name}</b>\n" 
        f"⟡ ᴀɴɪᴍᴇ: <code>{anime}</code>\n" 
        f"⟡ ʀᴀʀɪᴛʏ: {rarity}\n" 
        f"⟡ ᴘʀɪᴄᴇ: {status}\n" 
        f"⟡ ɪᴅ: <code>{cid}</code>\n\n" 
        f"⟡ ʀᴇғʀᴇꜱʜᴇꜱ ʟᴇꜰᴛ: {refresh_left}/{cfg.get('refresh_limit', 2)}\n" 
        f"⟡ ɴᴇxᴛ ʀᴇꜱᴇᴛ: {time_rem}\n\n" 
        f"───────\n" 
        f"⟡ ᴘᴀɢᴇ: {page}/{total}\n" 
        f"⟡ ʙᴀʟᴀɴᴄᴇ: {balance} ɢᴏʟᴅ" 
    ), char.get("img_url", ""), price, cid in purchased 

async def delete_message_after_delay(context: CallbackContext, chat_id: int, message_id: int, delay: int = 1800):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        if message_id in panel_owners:
            del panel_owners[message_id]
    except:
        pass

async def luv(update: Update, context: CallbackContext): 
    uid = update.effective_user.id 
    cfg = await get_config() 
    user = await user_collection.find_one({"id": uid}) 

    if not user: 
        await update.message.reply_text("⊗ ꜱᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ ꜰɪʀꜱᴛ! ᴜꜱᴇ /start") 
        return 

    balance = user.get('balance', 0) 
    luv_data = await get_luv_data(uid) 

    cooldown = cfg.get('cooldown_hours', 24) 
    last_reset = luv_data.get('last_reset') 
    needs_reset = True 

    if last_reset: 
        if isinstance(last_reset, str): 
            last_reset = datetime.fromisoformat(last_reset) 
        needs_reset = (datetime.utcnow() - last_reset).total_seconds() >= (cooldown * 3600) 

    if needs_reset or not luv_data.get('characters'): 
        chars = await generate_chars(uid, cfg) 
        if not chars: 
            await update.message.reply_text("⊗ ꜰᴀɪʟᴇᴅ ᴛᴏ ɢᴇɴᴇʀᴀᴛᴇ ꜱᴛᴏʀᴇ") 
            return 
        luv_data = {'characters': chars, 'last_reset': datetime.utcnow().isoformat(), 'refresh_count': 0, 'purchased': []} 
        await update_luv_data(uid, luv_data) 

    chars = luv_data.get('characters', []) 
    if not chars: 
        await update.message.reply_text("⊗ ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀꜱ ᴀᴠᴀɪʟᴀʙʟᴇ") 
        return 

    context.user_data['luv_page'] = 0 
    context.user_data['luv_chars'] = chars 

    char = chars[0] 
    caption, img, price, owned = await build_caption(char, cfg, 1, len(chars), luv_data, balance, uid) 
    cid = str(char.get("id") or char.get("_id"))

    btns = [] 
    if not owned: 
        btns.append([InlineKeyboardButton("⊙ ʙᴜʏ", callback_data=f"luv_buy_{cid}_{uid}")]) 

    nav = [] 
    if len(chars) > 1: 
        refresh_left = max(0, cfg.get('refresh_limit', 2) - luv_data.get('refresh_count', 0)) 
        nav.append(InlineKeyboardButton("⟲ ʀᴇғʀᴇꜱʜ" if refresh_left > 0 else "⟲ ᴜꜱᴇᴅ",  
                                        callback_data=f"luv_ref_{uid}" if refresh_left > 0 else f"luv_nope_{uid}")) 
        nav.append(InlineKeyboardButton("ɴᴇxᴛ ⊳", callback_data=f"luv_page_1_{uid}")) 
        btns.append(nav) 
    else: 
        refresh_left = max(0, cfg.get('refresh_limit', 2) - luv_data.get('refresh_count', 0)) 
        btns.append([InlineKeyboardButton("⟲ ʀᴇғʀᴇꜱʜ" if refresh_left > 0 else "⟲ ᴜꜱᴇᴅ",  
                                         callback_data=f"luv_ref_{uid}" if refresh_left > 0 else f"luv_nope_{uid}")]) 

    btns.append([InlineKeyboardButton("⊗ ᴄʟᴏꜱᴇ", callback_data=f"luv_close_{uid}")]) 

    msg = await update.message.reply_photo(photo=img, caption=caption, parse_mode="HTML",  
                                           reply_markup=InlineKeyboardMarkup(btns)) 
    
    panel_owners[msg.message_id] = uid
    context.user_data['luv_msg_id'] = msg.message_id 
    asyncio.create_task(delete_message_after_delay(context, msg.chat_id, msg.message_id))

async def luv_callback(update: Update, context: CallbackContext): 
    q = update.callback_query 
    uid = q.from_user.id 
    data = q.data 
    cfg = await get_config() 

    parts = data.split("_")
    if len(parts) >= 3:
        try:
            owner_id = int(parts[-1])
        except:
            owner_id = None
    else:
        owner_id = None

    msg_id = q.message.message_id
    if msg_id in panel_owners:
        owner_id = panel_owners[msg_id]

    if owner_id and owner_id != uid:
        await q.answer("⊗ ᴛʜɪꜱ ɪꜱ ɴᴏᴛ ʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ!", show_alert=True)
        return

    async def render_page(page): 
        chars = context.user_data.get('luv_chars', []) 
        if not chars or page >= len(chars): 
            await q.answer("⊗ ɪɴᴠᴀʟɪᴅ ᴘᴀɢᴇ", show_alert=True) 
            return 

        context.user_data['luv_page'] = page 
        char = chars[page] 
        user = await user_collection.find_one({"id": uid}) 
        balance = user.get('balance', 0) if user else 0 
        luv_data = await get_luv_data(uid) 

        caption, img, price, owned = await build_caption(char, cfg, page + 1, len(chars), luv_data, balance, uid) 
        cid = str(char.get("id") or char.get("_id"))

        btns = [] 
        if not owned: 
            btns.append([InlineKeyboardButton("⊙ ʙᴜʏ", callback_data=f"luv_buy_{cid}_{uid}")]) 

        nav = [] 
        if len(chars) > 1: 
            if page > 0: 
                nav.append(InlineKeyboardButton("⊲ ᴘʀᴇᴠ", callback_data=f"luv_page_{page-1}_{uid}")) 
            refresh_left = max(0, cfg.get('refresh_limit', 2) - luv_data.get('refresh_count', 0)) 
            nav.append(InlineKeyboardButton("⟲ ʀᴇғʀᴇꜱʜ" if refresh_left > 0 else "⟲ ᴜꜱᴇᴅ",  
                                           callback_data=f"luv_ref_{uid}" if refresh_left > 0 else f"luv_nope_{uid}")) 
            if page < len(chars) - 1: 
                nav.append(InlineKeyboardButton("ɴᴇxᴛ ⊳", callback_data=f"luv_page_{page+1}_{uid}")) 
            btns.append(nav) 

        btns.append([InlineKeyboardButton("⊗ ᴄʟᴏꜱᴇ", callback_data=f"luv_close_{uid}")]) 

        try: 
            await q.edit_message_media(media=InputMediaPhoto(media=img, caption=caption, parse_mode="HTML"), 
                                       reply_markup=InlineKeyboardMarkup(btns)) 
        except: 
            try: 
                await q.edit_message_caption(caption=caption, parse_mode="HTML",  
                                            reply_markup=InlineKeyboardMarkup(btns)) 
            except: 
                pass 

    if data.startswith("luv_page_"): 
        await q.answer()
        page_num = int(parts[-2])
        await render_page(page_num) 

    elif data.startswith("luv_ref_"):
        user = await user_collection.find_one({"id": uid}) 
        if not user: 
            await q.answer("⊗ ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ", show_alert=True) 
            return 

        luv_data = await get_luv_data(uid) 
        refresh_left = max(0, cfg.get('refresh_limit', 2) - luv_data.get('refresh_count', 0)) 

        if refresh_left <= 0: 
            await q.answer("⊗ ɴᴏ ʀᴇғʀᴇꜱʜᴇꜱ ʟᴇꜰᴛ!", show_alert=True) 
            return 

        cost = cfg.get('refresh_cost', 20000) 
        balance = user.get('balance', 0) 

        if balance < cost: 
            await q.answer(f"⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ!\n\nʏᴏᴜ ɴᴇᴇᴅ: {cost} ɢᴏʟᴅ\nʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ: {balance} ɢᴏʟᴅ\nꜱʜᴏʀᴛ ʙʏ: {cost - balance} ɢᴏʟᴅ", show_alert=True) 
            return

        await q.answer()
        btns = [[InlineKeyboardButton("✓ ᴄᴏɴꜰɪʀᴍ", callback_data=f"luv_refok_{uid}"), 
                 InlineKeyboardButton("✗ ᴄᴀɴᴄᴇʟ", callback_data=f"luv_cancel_{uid}")]] 

        await q.edit_message_caption( 
            caption=f"╭────────────────╮\n" 
                    f"│   ＣＯＮＦＩＲＭ ＲＥＦＲＥＳＨ   │\n" 
                    f"╰────────────────╯\n\n" 
                    f"⟡ ᴄᴏꜱᴛ: <b>{cost}</b> ɢᴏʟᴅ\n" 
                    f"⟡ ʙᴀʟᴀɴᴄᴇ: <b>{balance}</b> ɢᴏʟᴅ\n" 
                    f"⟡ ʀᴇꜰʀᴇꜱʜᴇꜱ ʟᴇꜰᴛ: {refresh_left-1}/{cfg.get('refresh_limit', 2)}\n\n" 
                    f"ɢᴇɴᴇʀᴀᴛᴇ 3 ɴᴇᴡ ʀᴀɴᴅᴏᴍ ᴄʜᴀʀᴀᴄᴛᴇʀꜱ?", 
            parse_mode="HTML", 
            reply_markup=InlineKeyboardMarkup(btns) 
        ) 

    elif data.startswith("luv_refok_"):
        user = await user_collection.find_one({"id": uid}) 
        luv_data = await get_luv_data(uid) 
        cost = cfg.get('refresh_cost', 20000) 
        balance = user.get('balance', 0) 

        if balance < cost: 
            await q.answer("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ!", show_alert=True) 
            return 

        await q.answer()
        await user_collection.update_one({"id": uid}, {"$inc": {"balance": -cost}}) 

        await q.edit_message_caption( 
            caption="╭────────────────╮\n" 
                    "│   ⟲ ＲＥＦＲＥＳＨＩＮＧ...   │\n" 
                    "╰────────────────╯\n\n" 
                    "⟡ ɢᴇɴᴇʀᴀᴛɪɴɢ ɴᴇᴡ ᴄʜᴀʀᴀᴄᴛᴇʀꜱ...", 
            parse_mode="HTML" 
        ) 

        chars = await generate_chars(uid, cfg) 
        if not chars: 
            await q.answer("⊗ ꜰᴀɪʟᴇᴅ ᴛᴏ ɢᴇɴᴇʀᴀᴛᴇ", show_alert=True) 
            return 

        luv_data['characters'] = chars 
        luv_data['refresh_count'] = luv_data.get('refresh_count', 0) + 1 
        luv_data['purchased'] = [] 
        await update_luv_data(uid, luv_data) 

        context.user_data['luv_chars'] = chars 
        context.user_data['luv_page'] = 0 

        await q.answer("✓ ꜱᴛᴏʀᴇ ʀᴇғʀᴇꜱʜᴇᴅ!") 
        await render_page(0) 

    elif data.startswith("luv_cancel_"):
        await q.answer()
        await render_page(context.user_data.get('luv_page', 0)) 

    elif data.startswith("luv_nope_"):
        await q.answer("⊗ ɴᴏ ʀᴇғʀᴇꜱʜᴇꜱ ʟᴇꜰᴛ!", show_alert=True) 

    elif data.startswith("luv_buy_"): 
        cid = parts[-2]
        chars = context.user_data.get('luv_chars', []) 
        char = next((c for c in chars if str(c.get("id") or c.get("_id")) == cid), None) 

        if not char: 
            await q.answer("⊗ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ", show_alert=True) 
            return 

        luv_data = await get_luv_data(uid) 
        if cid in luv_data.get('purchased', []): 
            await q.answer("⊗ ᴀʟʀᴇᴀᴅʏ ᴘᴜʀᴄʜᴀꜱᴇᴅ!", show_alert=True) 
            return 

        await q.answer()
        rarity = char.get('rarity', 'Unknown') 
        price = character_prices.get(uid, {}).get(cid, 0)
        if price == 0:
            rarity_data = cfg['rarities'].get(rarity, {})
            price = rarity_data.get('min_price', 1000)

        btns = [[InlineKeyboardButton("✓ ᴄᴏɴꜰɪʀᴍ", callback_data=f"luv_ok_{cid}_{uid}"), 
                 InlineKeyboardButton("✗ ᴄᴀɴᴄᴇʟ", callback_data=f"luv_buyno_{uid}")]] 

        await q.edit_message_caption( 
            caption=f"╭────────────────╮\n" 
                    f"│   ＣＯＮＦＩＲＭ ＰＵＲＣＨＡＳＥ   │\n" 
                    f"╰────────────────╯\n\n" 
                    f"⟡ ɴᴀᴍᴇ: <b>{char['name']}</b>\n" 
                    f"⟡ ʀᴀʀɪᴛʏ: {rarity}\n" 
                    f"⟡ ᴘʀɪᴄᴇ: <b>{price}</b> ɢᴏʟᴅ\n\n" 
                    f"ᴄᴏɴꜰɪʀᴍ ᴘᴜʀᴄʜᴀꜱᴇ?", 
            parse_mode="HTML", 
            reply_markup=InlineKeyboardMarkup(btns) 
        ) 

    elif data.startswith("luv_ok_"): 
        cid = parts[-2]
        chars = context.user_data.get('luv_chars', []) 
        char = next((c for c in chars if str(c.get("id") or c.get("_id")) == cid), None) 

        if not char: 
            await q.answer("⊗ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ", show_alert=True) 
            return 

        user = await user_collection.find_one({"id": uid}) 
        luv_data = await get_luv_data(uid) 

        if cid in luv_data.get('purchased', []): 
            await q.answer("⊗ ᴀʟʀᴇᴀᴅʏ ᴘᴜʀᴄʜᴀꜱᴇᴅ!", show_alert=True) 
            return 

        rarity = char.get('rarity', 'Unknown') 
        price = character_prices.get(uid, {}).get(cid, 0)
        if price == 0:
            rarity_data = cfg['rarities'].get(rarity, {})
            price = rarity_data.get('min_price', 1000)
        
        balance = user.get('balance', 0) 

        if balance < price: 
            await q.answer("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ!", show_alert=True) 
            await q.edit_message_caption( 
                caption=f"╭────────────────╮\n" 
                        f"│   ⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ɢᴏʟᴅ   │\n" 
                        f"╰────────────────╯\n\n" 
                        f"⟡ ɴᴇᴇᴅ: <b>{price}</b> ɢᴏʟᴅ\n" 
                        f"⟡ ʜᴀᴠᴇ: <b>{balance}</b> ɢᴏʟᴅ\n\n" 
                        f"ᴜꜱᴇ /bal ᴛᴏ ᴄʜᴇᴄᴋ ʙᴀʟᴀɴᴄᴇ", 
                parse_mode="HTML" 
            ) 
            return 

        await q.answer()
        await user_collection.update_one({"id": uid},  
                                         {"$inc": {"balance": -price}, "$push": {"characters": char}}) 

        if 'purchased' not in luv_data: 
            luv_data['purchased'] = [] 
        luv_data['purchased'].append(cid) 
        await update_luv_data(uid, luv_data) 

        btns = [[InlineKeyboardButton("⊙ ᴍᴀɪɴ ꜱʜᴏᴘ", callback_data=f"luv_main_{uid}"), 
                 InlineKeyboardButton("⊗ ᴄʟᴏꜱᴇ", callback_data=f"luv_close_{uid}")]] 

        await q.edit_message_caption( 
            caption=f"╭────────────────╮\n" 
                    f"│   ✓ ＰＵＲＣＨＡＳＥ ＳＵＣＣＥＳＳ   │\n" 
                    f"╰────────────────╯\n\n" 
                    f"⟡ ɴᴀᴍᴇ: <b>{char['name']}</b>\n" 
                    f"⟡ ᴘᴀɪᴅ: <b>{price}</b> ɢᴏʟᴅ\n" 
                    f"⟡ ʀᴇᴍᴀɪɴɪɴɢ: <b>{balance - price}</b> ɢᴏʟᴅ\n\n" 
                    f"ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ʜᴀʀᴇᴍ!", 
            parse_mode="HTML", 
            reply_markup=InlineKeyboardMarkup(btns) 
        ) 
        await q.answer("✓ ᴘᴜʀᴄʜᴀꜱᴇᴅ!") 

    elif data.startswith("luv_buyno_"):
        await q.answer()
        await render_page(context.user_data.get('luv_page', 0)) 

    elif data.startswith("luv_main_"):
        await q.answer()
        await render_page(0) 

    elif data.startswith("luv_close_"):
        await q.answer()
        try: 
            msg_id = q.message.message_id
            if msg_id in panel_owners:
                del panel_owners[msg_id]
            await q.message.delete() 
        except: 
            await q.edit_message_caption("ꜱᴛᴏʀᴇ ᴄʟᴏꜱᴇᴅ") 

async def luv_view(update: Update, context: CallbackContext): 
    if str(update.effective_user.id) != super_admin: 
        await update.message.reply_text("⊗ ᴏɴʟʏ ꜱᴜᴘᴇʀ ᴀᴅᴍɪɴ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ!")
        return 
    cfg = await get_config() 
    rarities = "\n".join([f"⟡ {r}: {d['weight']}% | {d.get('min_price', 0)}-{d.get('max_price', 0)}g" for r, d in cfg['rarities'].items()]) 
    await update.message.reply_text( 
        f"╭────────────────╮\n│   ʟᴜᴠ ᴄᴏɴꜰɪɢ   │\n╰────────────────╯\n\n" 
        f"⟡ ʀᴇғʀᴇꜱʜ ᴄᴏꜱᴛ: {cfg.get('refresh_cost')}\n" 
        f"⟡ ʀᴇғʀᴇꜱʜ ʟɪᴍɪᴛ: {cfg.get('refresh_limit')}\n" 
        f"⟡ ɪᴛᴇᴍꜱ: {cfg.get('store_items')}\n" 
        f"⟡ ᴄᴏᴏʟᴅᴏᴡɴ: {cfg.get('cooldown_hours')}ʜ\n\n{rarities}", 
        parse_mode="HTML" 
    ) 

async def luv_stats(update: Update, context: CallbackContext): 
    uid = update.effective_user.id 
    user = await user_collection.find_one({"id": uid}) 
    if not user: 
        await update.message.reply_text("⊗ ᴜꜱᴇ /start ꜰɪʀꜱᴛ") 
        return 

    luv_data = await get_luv_data(uid) 
    cfg = await get_config() 
    refresh_left = max(0, cfg.get('refresh_limit', 2) - luv_data.get('refresh_count', 0)) 

    last_reset = luv_data.get('last_reset') 
    if last_reset: 
        if isinstance(last_reset, str): 
            last_reset = datetime.fromisoformat(last_reset) 
        next_reset = last_reset + timedelta(hours=cfg.get('cooldown_hours', 24)) 
        time_rem = time_left(next_reset) 
    else: 
        time_rem = "ᴀᴠᴀɪʟᴀʙʟᴇ ɴᴏᴡ" 

    await update.message.reply_text( 
        f"╭────────────────╮\n│   ʏᴏᴜʀ ʟᴜᴠ ꜱᴛᴀᴛꜱ   │\n╰────────────────╯\n\n" 
        f"⟡ ᴄʜᴀʀᴀᴄᴛᴇʀꜱ: {len(luv_data.get('characters', []))}\n" 
        f"⟡ ʀᴇғʀᴇꜱʜᴇꜱ: {refresh_left}/{cfg.get('refresh_limit', 2)}\n" 
        f"⟡ ɴᴇxᴛ ʀᴇꜱᴇᴛ: {time_rem}\n" 
        f"⟡ ʙᴀʟᴀɴᴄᴇ: {user.get('balance', 0)} ɢᴏʟᴅ\n\n" 
        f"ᴜꜱᴇ /ps ᴛᴏ ᴏᴘᴇɴ ꜱᴛᴏʀᴇ!", 
        parse_mode="HTML" 
    ) 

async def luv_help(update: Update, context: CallbackContext): 
    msg = ( 
        f"╭────────────────╮\n│   ʟᴜᴠ ʜᴇʟᴘ   │\n╰────────────────╯\n\n" 
        f"<b>ᴄᴏᴍᴍᴀɴᴅꜱ:</b>\n" 
        f"⟡ /ps - ᴏᴘᴇɴ ꜱᴛᴏʀᴇ\n" 
        f"⟡ /pstats - ᴠɪᴇᴡ ꜱᴛᴀᴛꜱ\n\n" 
        f"<b>ʜᴏᴡ ɪᴛ ᴡᴏʀᴋꜱ:</b>\n" 
        f"⟡ ɢᴇᴛ 3 ʀᴀɴᴅᴏᴍ ᴄʜᴀʀᴀᴄᴛᴇʀꜱ ᴇᴠᴇʀʏ 24ʜ\n" 
        f"⟡ ʀᴀɴᴅᴏᴍ ᴘʀɪᴄᴇꜱ ʙᴀꜱᴇᴅ ᴏɴ ʀᴀʀɪᴛʏ\n" 
        f"⟡ ʀᴇғʀᴇꜱʜ ᴜᴘ ᴛᴏ 2x (ᴄᴏꜱᴛꜱ ɢᴏʟᴅ)\n" 
        f"⟡ ʙᴜʏ ᴡɪᴛʜ ɢᴏʟᴅ\n" 
        f"⟡ ᴀᴜᴛᴏ ʀᴇꜱᴇᴛ ᴀꜰᴛᴇʀ ᴄᴏᴏʟᴅᴏᴡɴ\n"
        f"⟡ ꜱᴛᴏʀᴇ ᴍᴇꜱꜱᴀɢᴇꜱ ᴀᴜᴛᴏ-ᴅᴇʟᴇᴛᴇ ᴀꜰᴛᴇʀ 30 ᴍɪɴ" 
    ) 

    uid = update.effective_user.id 
    if str(uid) == super_admin: 
        msg += ( 
            f"\n\n<b>ꜱᴜᴘᴇʀ ᴀᴅᴍɪɴ:</b>\n" 
            f"⟡ /pview - ᴠɪᴇᴡ ᴄᴏɴꜰɪɢ\n" 
            f"⟡ /pconfig <key> <val>\n" 
            f"⟡ /prarity <name> <weight> <min> <max>\n" 
            f"⟡ /prmrarity <name>\n" 
            f"⟡ /preset <uid>" 
        ) 

    await update.message.reply_text(msg, parse_mode="HTML") 

async def luv_config(update: Update, context: CallbackContext): 
    if str(update.effective_user.id) != super_admin: 
        await update.message.reply_text("⊗ ᴏɴʟʏ ꜱᴜᴘᴇʀ ᴀᴅᴍɪɴ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ!")
        return 

    if len(context.args) < 2: 
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /pconfig <key> <value>\nᴋᴇʏꜱ: refresh_cost, refresh_limit, store_items, cooldown_hours") 
        return 

    try: 
        key, val = context.args[0], int(context.args[1]) 
        if key not in ['refresh_cost', 'refresh_limit', 'store_items', 'cooldown_hours']: 
            await update.message.reply_text("⊗ ɪɴᴠᴀʟɪᴅ ᴋᴇʏ") 
            return 

        cfg = await get_config() 
        cfg[key] = val 
        await luv_config_collection.update_one({"_id": "luv_config"}, {"$set": cfg}, upsert=True) 
        await update.message.reply_text(f"✓ {key} = {val}", parse_mode="HTML") 
    except: 
        await update.message.reply_text("⊗ ɪɴᴠᴀʟɪᴅ ᴠᴀʟᴜᴇ") 

async def luv_rarity(update: Update, context: CallbackContext): 
    if str(update.effective_user.id) != super_admin: 
        await update.message.reply_text("⊗ ᴏɴʟʏ ꜱᴜᴘᴇʀ ᴀᴅᴍɪɴ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ!")
        return 

    if len(context.args) < 4: 
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /prarity <name> <weight> <min_price> <max_price>\nᴇxᴀᴍᴘʟᴇ: /prarity 🔥 Epic 15 5000 8000") 
        return 

    try: 
        name = " ".join(context.args[:-3]) 
        weight = int(context.args[-3])
        min_price = int(context.args[-2])
        max_price = int(context.args[-1])
        
        if min_price >= max_price:
            await update.message.reply_text("⊗ ᴍɪɴ ᴘʀɪᴄᴇ ᴍᴜꜱᴛ ʙᴇ ʟᴇꜱꜱ ᴛʜᴀɴ ᴍᴀx ᴘʀɪᴄᴇ!")
            return

        cfg = await get_config() 
        if name not in cfg['rarities']: 
            cfg['rarities'][name] = {} 
        cfg['rarities'][name] = {'weight': weight, 'min_price': min_price, 'max_price': max_price} 

        await luv_config_collection.update_one({"_id": "luv_config"}, {"$set": cfg}, upsert=True) 
        await update.message.reply_text(f"✓ {name}: {weight}% | {min_price}-{max_price}g", parse_mode="HTML") 
    except: 
        await update.message.reply_text("⊗ ɪɴᴠᴀʟɪᴅ ᴠᴀʟᴜᴇꜱ") 

async def luv_reset(update: Update, context: CallbackContext): 
    if str(update.effective_user.id) != super_admin: 
        await update.message.reply_text("⊗ ᴏɴʟʏ ꜱᴜᴘᴇʀ ᴀᴅᴍɪɴ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ!")
        return 

    if len(context.args) < 1: 
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /preset <uid>") 
        return 

    try: 
        target_uid = int(context.args[0]) 
        luv_data = {'characters': [], 'last_reset': None, 'refresh_count': 0, 'purchased': []} 
        await update_luv_data(target_uid, luv_data) 
        if target_uid in character_prices:
            del character_prices[target_uid]
        await update.message.reply_text(f"✓ ʀᴇꜱᴇᴛ ᴜꜱᴇʀ {target_uid}") 
    except: 
        await update.message.reply_text("⊗ ɪɴᴠᴀʟɪᴅ ᴜɪᴅ") 

async def luv_rmrarity(update: Update, context: CallbackContext): 
    if str(update.effective_user.id) != super_admin: 
        await update.message.reply_text("⊗ ᴏɴʟʏ ꜱᴜᴘᴇʀ ᴀᴅᴍɪɴ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ!")
        return 

    if len(context.args) < 1: 
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /prmrarity <rarity_name>") 
        return 

    try: 
        name = " ".join(context.args) 
        cfg = await get_config() 

        if name not in cfg['rarities']: 
            await update.message.reply_text(f"⊗ ʀᴀʀɪᴛʏ '<b>{name}</b>' ɴᴏᴛ ꜰᴏᴜɴᴅ", parse_mode="HTML") 
            return 

        if len(cfg['rarities']) <= 1: 
            await update.message.reply_text("⊗ ᴄᴀɴɴᴏᴛ ʀᴇᴍᴏᴠᴇ ʟᴀꜱᴛ ʀᴀʀɪᴛʏ!") 
            return 

        del cfg['rarities'][name] 
        await luv_config_collection.update_one({"_id": "luv_config"}, {"$set": cfg}, upsert=True) 
        await update.message.reply_text(f"✓ ʀᴇᴍᴏᴠᴇᴅ '<b>{name}</b>'", parse_mode="HTML") 
    except Exception as e: 
        await update.message.reply_text(f"⊗ ᴇʀʀᴏʀ: {str(e)}") 

application.add_handler(CommandHandler("ps", luv, block=False)) 
application.add_handler(CommandHandler("pstats", luv_stats, block=False)) 
application.add_handler(CommandHandler("phelp", luv_help, block=False)) 
application.add_handler(CommandHandler("pview", luv_view, block=False)) 
application.add_handler(CommandHandler("pconfig", luv_config, block=False)) 
application.add_handler(CommandHandler("prarity", luv_rarity, block=False)) 
application.add_handler(CommandHandler("prmrarity", luv_rmrarity, block=False)) 
application.add_handler(CommandHandler("preset", luv_reset, block=False)) 
application.add_handler(CallbackQueryHandler(luv_callback, pattern=r"^luv_", block=False))