import random
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from shivu import application, db, user_collection

collection = db['anime_characters_lol']
ps_config_collection = db['ps_config']
sudo_users = ["8297659126", "8420981179", "5147822244"]

DEFAULT_CONFIG = {
    "rarities": {
        "🟢 Common": {"weight": 60, "price": 2000},
        "🟣 Rare": {"weight": 25, "price": 5000},
        "🟡 Legendary": {"weight": 10, "price": 10000},
        "💮 Special Edition": {"weight": 5, "price": 25000}
    },
    "refresh_cost": 20000,
    "refresh_limit": 2,
    "store_items": 3,
    "cooldown_hours": 24
}

async def get_config():
    cfg = await ps_config_collection.find_one({"_id": "ps_config"})
    if not cfg:
        await ps_config_collection.insert_one({"_id": "ps_config", **DEFAULT_CONFIG})
        return DEFAULT_CONFIG
    return cfg

async def get_rarity(cfg):
    rarities = cfg['rarities']
    return random.choices(list(rarities.keys()), [rarities[r]['weight'] for r in rarities], k=1)[0]

async def generate_chars(uid, cfg):
    chars = []
    for _ in range(cfg.get('store_items', 3)):
        rarity = await get_rarity(cfg)
        pipe = [{'$match': {'rarity': rarity}}, {'$sample': {'size': 1}}]
        char = await collection.aggregate(pipe).to_list(length=1)
        if char:
            chars.append(char[0])
    return chars

async def get_ps_data(uid):
    user = await user_collection.find_one({"id": uid})
    return user.get('private_store', {'characters': [], 'last_reset': None, 'refresh_count': 0, 'purchased': []}) if user else None

async def update_ps_data(uid, data):
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

async def build_caption(char, cfg, page, total, ps_data, balance):
    cid = char.get("id") or char.get("_id")
    name = char.get("name", "Unknown")
    anime = char.get("anime", "Unknown")
    rarity = char.get("rarity", "Unknown")
    price = cfg['rarities'].get(rarity, {}).get('price', 0)
    
    refresh_left = max(0, cfg.get('refresh_limit', 2) - ps_data.get('refresh_count', 0))
    last_reset = ps_data.get('last_reset')
    if last_reset:
        if isinstance(last_reset, str):
            last_reset = datetime.fromisoformat(last_reset)
        next_reset = last_reset + timedelta(hours=cfg.get('cooldown_hours', 24))
        time_rem = time_left(next_reset)
    else:
        time_rem = "ᴀᴠᴀɪʟᴀʙʟᴇ ɴᴏᴡ"
    
    purchased = ps_data.get('purchased', [])
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

async def ps(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    cfg = await get_config()
    user = await user_collection.find_one({"id": uid})
    
    if not user:
        await update.message.reply_text("⊗ ꜱᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ ꜰɪʀꜱᴛ! ᴜꜱᴇ /start")
        return
    
    balance = user.get('balance', 0)
    ps_data = await get_ps_data(uid)
    
    cooldown = cfg.get('cooldown_hours', 24)
    last_reset = ps_data.get('last_reset')
    needs_reset = True
    
    if last_reset:
        if isinstance(last_reset, str):
            last_reset = datetime.fromisoformat(last_reset)
        needs_reset = (datetime.utcnow() - last_reset).total_seconds() >= (cooldown * 3600)
    
    if needs_reset or not ps_data.get('characters'):
        chars = await generate_chars(uid, cfg)
        if not chars:
            await update.message.reply_text("⊗ ꜰᴀɪʟᴇᴅ ᴛᴏ ɢᴇɴᴇʀᴀᴛᴇ ꜱᴛᴏʀᴇ")
            return
        ps_data = {'characters': chars, 'last_reset': datetime.utcnow().isoformat(), 'refresh_count': 0, 'purchased': []}
        await update_ps_data(uid, ps_data)
    
    chars = ps_data.get('characters', [])
    if not chars:
        await update.message.reply_text("⊗ ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀꜱ ᴀᴠᴀɪʟᴀʙʟᴇ")
        return
    
    context.user_data['ps_page'] = 0
    context.user_data['ps_chars'] = chars
    
    char = chars[0]
    caption, img, price, owned = await build_caption(char, cfg, 1, len(chars), ps_data, balance)
    cid = char.get("id") or char.get("_id")
    
    btns = []
    if not owned:
        btns.append([InlineKeyboardButton("⊙ ʙᴜʏ", callback_data=f"ps_buy_{cid}")])
    
    nav = []
    if len(chars) > 1:
        refresh_left = max(0, cfg.get('refresh_limit', 2) - ps_data.get('refresh_count', 0))
        nav.append(InlineKeyboardButton("⟲ ʀᴇғʀᴇꜱʜ" if refresh_left > 0 else "⟲ ᴜꜱᴇᴅ", 
                                        callback_data="ps_refresh" if refresh_left > 0 else "ps_nope"))
        nav.append(InlineKeyboardButton("ɴᴇxᴛ ⊳", callback_data="ps_page_1"))
        btns.append(nav)
    else:
        refresh_left = max(0, cfg.get('refresh_limit', 2) - ps_data.get('refresh_count', 0))
        btns.append([InlineKeyboardButton("⟲ ʀᴇғʀᴇꜱʜ" if refresh_left > 0 else "⟲ ᴜꜱᴇᴅ", 
                                         callback_data="ps_refresh" if refresh_left > 0 else "ps_nope")])
    
    btns.append([InlineKeyboardButton("⊗ ᴄʟᴏꜱᴇ", callback_data="ps_close")])
    
    msg = await update.message.reply_photo(photo=img, caption=caption, parse_mode="HTML", 
                                           reply_markup=InlineKeyboardMarkup(btns))
    context.user_data['ps_msg_id'] = msg.message_id

async def ps_callback(update: Update, context: CallbackContext):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data
    cfg = await get_config()
    
    async def render_page(page):
        chars = context.user_data.get('ps_chars', [])
        if not chars or page >= len(chars):
            await q.answer("⊗ ɪɴᴠᴀʟɪᴅ ᴘᴀɢᴇ", show_alert=True)
            return
        
        context.user_data['ps_page'] = page
        char = chars[page]
        user = await user_collection.find_one({"id": uid})
        balance = user.get('balance', 0) if user else 0
        ps_data = await get_ps_data(uid)
        
        caption, img, price, owned = await build_caption(char, cfg, page + 1, len(chars), ps_data, balance)
        cid = char.get("id") or char.get("_id")
        
        btns = []
        if not owned:
            btns.append([InlineKeyboardButton("⊙ ʙᴜʏ", callback_data=f"ps_buy_{cid}")])
        
        nav = []
        if len(chars) > 1:
            if page > 0:
                nav.append(InlineKeyboardButton("⊲ ᴘʀᴇᴠ", callback_data=f"ps_page_{page-1}"))
            refresh_left = max(0, cfg.get('refresh_limit', 2) - ps_data.get('refresh_count', 0))
            nav.append(InlineKeyboardButton("⟲ ʀᴇғʀᴇꜱʜ" if refresh_left > 0 else "⟲ ᴜꜱᴇᴅ", 
                                           callback_data="ps_refresh" if refresh_left > 0 else "ps_nope"))
            if page < len(chars) - 1:
                nav.append(InlineKeyboardButton("ɴᴇxᴛ ⊳", callback_data=f"ps_page_{page+1}"))
            btns.append(nav)
        
        btns.append([InlineKeyboardButton("⊗ ᴄʟᴏꜱᴇ", callback_data="ps_close")])
        
        try:
            await q.edit_message_media(media=InputMediaPhoto(media=img, caption=caption, parse_mode="HTML"),
                                       reply_markup=InlineKeyboardMarkup(btns))
        except:
            try:
                await q.edit_message_caption(caption=caption, parse_mode="HTML", 
                                            reply_markup=InlineKeyboardMarkup(btns))
            except:
                pass
    
    if data.startswith("ps_page_"):
        await render_page(int(data.split("_")[2]))
    
    elif data == "ps_refresh":
        user = await user_collection.find_one({"id": uid})
        if not user:
            await q.answer("⊗ ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ", show_alert=True)
            return
        
        ps_data = await get_ps_data(uid)
        refresh_left = max(0, cfg.get('refresh_limit', 2) - ps_data.get('refresh_count', 0))
        
        if refresh_left <= 0:
            await q.answer("⊗ ɴᴏ ʀᴇғʀᴇꜱʜᴇꜱ ʟᴇꜰᴛ!", show_alert=True)
            return
        
        cost = cfg.get('refresh_cost', 20000)
        balance = user.get('balance', 0)
        
        if balance < cost:
            await q.answer(f"⊗ ɴᴇᴇᴅ {cost} ɢᴏʟᴅ!", show_alert=True)
            return
        
        btns = [[InlineKeyboardButton("✓ ᴄᴏɴꜰɪʀᴍ", callback_data="ps_ref_ok"),
                 InlineKeyboardButton("✗ ᴄᴀɴᴄᴇʟ", callback_data="ps_ref_no")]]
        
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
    
    elif data == "ps_ref_ok":
        user = await user_collection.find_one({"id": uid})
        ps_data = await get_ps_data(uid)
        cost = cfg.get('refresh_cost', 20000)
        balance = user.get('balance', 0)
        
        if balance < cost:
            await q.answer("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ!", show_alert=True)
            return
        
        await user_collection.update_one({"id": uid}, {"$inc": {"balance": -cost}})
        
        # Refresh animation
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
        
        ps_data['characters'] = chars
        ps_data['refresh_count'] = ps_data.get('refresh_count', 0) + 1
        ps_data['purchased'] = []
        await update_ps_data(uid, ps_data)
        
        context.user_data['ps_chars'] = chars
        context.user_data['ps_page'] = 0
        
        await q.answer("✓ ꜱᴛᴏʀᴇ ʀᴇғʀᴇꜱʜᴇᴅ!")
        await render_page(0)
    
    elif data == "ps_ref_no":
        await render_page(context.user_data.get('ps_page', 0))
    
    elif data == "ps_nope":
        await q.answer("⊗ ɴᴏ ʀᴇғʀᴇꜱʜᴇꜱ ʟᴇꜰᴛ!", show_alert=True)
    
    elif data.startswith("ps_buy_"):
        cid = data.split("_", 2)[2]
        chars = context.user_data.get('ps_chars', [])
        char = next((c for c in chars if (c.get("id") or c.get("_id")) == cid), None)
        
        if not char:
            await q.answer("⊗ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ", show_alert=True)
            return
        
        ps_data = await get_ps_data(uid)
        if cid in ps_data.get('purchased', []):
            await q.answer("⊗ ᴀʟʀᴇᴀᴅʏ ᴘᴜʀᴄʜᴀꜱᴇᴅ!", show_alert=True)
            return
        
        rarity = char.get('rarity', 'Unknown')
        price = cfg['rarities'].get(rarity, {}).get('price', 0)
        
        btns = [[InlineKeyboardButton("✓ ᴄᴏɴꜰɪʀᴍ", callback_data=f"ps_ok_{cid}"),
                 InlineKeyboardButton("✗ ᴄᴀɴᴄᴇʟ", callback_data="ps_buy_no")]]
        
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
    
    elif data.startswith("ps_ok_"):
        cid = data.split("_", 2)[2]
        chars = context.user_data.get('ps_chars', [])
        char = next((c for c in chars if (c.get("id") or c.get("_id")) == cid), None)
        
        if not char:
            await q.answer("⊗ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ", show_alert=True)
            return
        
        user = await user_collection.find_one({"id": uid})
        ps_data = await get_ps_data(uid)
        
        if cid in ps_data.get('purchased', []):
            await q.answer("⊗ ᴀʟʀᴇᴀᴅʏ ᴘᴜʀᴄʜᴀꜱᴇᴅ!", show_alert=True)
            return
        
        rarity = char.get('rarity', 'Unknown')
        price = cfg['rarities'].get(rarity, {}).get('price', 0)
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
        
        # Purchase
        await user_collection.update_one({"id": uid}, 
                                         {"$inc": {"balance": -price}, "$push": {"characters": char}})
        
        if 'purchased' not in ps_data:
            ps_data['purchased'] = []
        ps_data['purchased'].append(cid)
        await update_ps_data(uid, ps_data)
        
        btns = [[InlineKeyboardButton("⊙ ᴍᴀɪɴ ꜱʜᴏᴘ", callback_data="ps_main"),
                 InlineKeyboardButton("⊗ ᴄʟᴏꜱᴇ", callback_data="ps_close")]]
        
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
    
    elif data == "ps_buy_no":
        await render_page(context.user_data.get('ps_page', 0))
    
    elif data == "ps_main":
        await render_page(0)
    
    elif data == "ps_close":
        try:
            await q.message.delete()
        except:
            await q.edit_message_caption("ꜱᴛᴏʀᴇ ᴄʟᴏꜱᴇᴅ")

# Admin commands (shortened)
async def ps_view(update: Update, context: CallbackContext):
    if str(update.effective_user.id) not in sudo_users:
        return
    cfg = await get_config()
    rarities = "\n".join([f"⟡ {r}: {d['weight']}% | {d['price']}g" for r, d in cfg['rarities'].items()])
    await update.message.reply_text(
        f"╭────────────────╮\n│   ᴘꜱ ᴄᴏɴꜰɪɢ   │\n╰────────────────╯\n\n"
        f"⟡ ʀᴇғʀᴇꜱʜ ᴄᴏꜱᴛ: {cfg.get('refresh_cost')}\n"
        f"⟡ ʀᴇғʀᴇꜱʜ ʟɪᴍɪᴛ: {cfg.get('refresh_limit')}\n"
        f"⟡ ɪᴛᴇᴍꜱ: {cfg.get('store_items')}\n"
        f"⟡ ᴄᴏᴏʟᴅᴏᴡɴ: {cfg.get('cooldown_hours')}ʜ\n\n{rarities}",
        parse_mode="HTML"
    )

async def ps_stats(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await user_collection.find_one({"id": uid})
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /start ꜰɪʀꜱᴛ")
        return
    
    ps_data = await get_ps_data(uid)
    cfg = await get_config()
    refresh_left = max(0, cfg.get('refresh_limit', 2) - ps_data.get('refresh_count', 0))
    
    last_reset = ps_data.get('last_reset')
    if last_reset:
        if isinstance(last_reset, str):
            last_reset = datetime.fromisoformat(last_reset)
        next_reset = last_reset + timedelta(hours=cfg.get('cooldown_hours', 24))
        time_rem = time_left(next_reset)
    else:
        time_rem = "ᴀᴠᴀɪʟᴀʙʟᴇ ɴᴏᴡ"
    
    await update.message.reply_text(
        f"╭────────────────╮\n│   ʏᴏᴜʀ ᴘꜱ ꜱᴛᴀᴛꜱ   │\n╰────────────────╯\n\n"
        f"⟡ ᴄʜᴀʀᴀᴄᴛᴇʀꜱ: {len(ps_data.get('characters', []))}\n"
        f"⟡ ʀᴇғʀᴇꜱʜᴇꜱ: {refresh_left}/{cfg.get('refresh_limit', 2)}\n"
        f"⟡ ɴᴇxᴛ ʀᴇꜱᴇᴛ: {time_rem}\n"
        f"⟡ ʙᴀʟᴀɴᴄᴇ: {user.get('balance', 0)} ɢᴏʟᴅ\n\n"
        f"ᴜꜱᴇ /ps ᴛᴏ ᴏᴘᴇɴ ꜱᴛᴏʀᴇ!",
        parse_mode="HTML"
    )

async def ps_help(update: Update, context: CallbackContext):
    msg = (
        f"╭────────────────╮\n│   ᴘꜱ ʜᴇʟᴘ   │\n╰────────────────╯\n\n"
        f"<b>ᴄᴏᴍᴍᴀɴᴅꜱ:</b>\n"
        f"⟡ /ps - ᴏᴘᴇɴ ꜱᴛᴏʀᴇ\n"
        f"⟡ /psstats - ᴠɪᴇᴡ ꜱᴛᴀᴛꜱ\n\n"
        f"<b>ʜᴏᴡ ɪᴛ ᴡᴏʀᴋꜱ:</b>\n"
        f"⟡ ɢᴇᴛ 3 ʀᴀɴᴅᴏᴍ ᴄʜᴀʀᴀᴄᴛᴇʀꜱ ᴇᴠᴇʀʏ 24ʜ\n"
        f"⟡ ʀᴇғʀᴇꜱʜ ᴜᴘ ᴛᴏ 2x (ᴄᴏꜱᴛꜱ ɢᴏʟᴅ)\n"
        f"⟡ ʙᴜʏ ᴡɪᴛʜ ɢᴏʟᴅ\n"
        f"⟡ ᴀᴜᴛᴏ ʀᴇꜱᴇᴛ ᴀꜰᴛᴇʀ ᴄᴏᴏʟᴅᴏᴡɴ"
    )
    
    uid = update.effective_user.id
    if str(uid) in sudo_users:
        msg += (
            f"\n\n<b>ᴀᴅᴍɪɴ:</b>\n"
            f"⟡ /psview - ᴠɪᴇᴡ ᴄᴏɴꜰɪɢ\n"
            f"⟡ /psconfig <key> <val>\n"
            f"⟡ /psrarity <name> <w> <p>\n"
            f"⟡ /psreset <uid>"
        )
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def ps_config(update: Update, context: CallbackContext):
    if str(update.effective_user.id) not in sudo_users:
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /psconfig <key> <value>\nᴋᴇʏꜱ: refresh_cost, refresh_limit, store_items, cooldown_hours")
        return
    
    try:
        key, val = context.args[0], int(context.args[1])
        if key not in ['refresh_cost', 'refresh_limit', 'store_items', 'cooldown_hours']:
            await update.message.reply_text("⊗ ɪɴᴠᴀʟɪᴅ ᴋᴇʏ")
            return
        
        cfg = await get_config()
        cfg[key] = val
        await ps_config_collection.update_one({"_id": "ps_config"}, {"$set": cfg}, upsert=True)
        await update.message.reply_text(f"✓ {key} = {val}", parse_mode="HTML")
    except:
        await update.message.reply_text("⊗ ɪɴᴠᴀʟɪᴅ ᴠᴀʟᴜᴇ")

async def ps_rarity(update: Update, context: CallbackContext):
    if str(update.effective_user.id) not in sudo_users:
        return
    
    if len(context.args) < 3:
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /psrarity <name> <weight> <price>")
        return
    
    try:
        name = " ".join(context.args[:-2])
        weight, price = int(context.args[-2]), int(context.args[-1])
        
        cfg = await get_config()
        if name not in cfg['rarities']:
            cfg['rarities'][name] = {}
        cfg['rarities'][name] = {'weight': weight, 'price': price}
        
        await ps_config_collection.update_one({"_id": "ps_config"}, {"$set": cfg}, upsert=True)
        await update.message.reply_text(f"✓ {name}: {weight}% | {price}g", parse_mode="HTML")
    except:
        await update.message.reply_text("⊗ ɪɴᴠᴀʟɪᴅ ᴠᴀʟᴜᴇꜱ")

async def ps_reset(update: Update, context: CallbackContext):
    if str(update.effective_user.id) not in sudo_users:
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /psreset <uid>")
        return
    
    try:
        target_uid = int(context.args[0])
        ps_data = {'characters': [], 'last_reset': None, 'refresh_count': 0, 'purchased': []}
        await update_ps_data(target_uid, ps_data)
        await update.message.reply_text(f"✓ ʀᴇꜱᴇᴛ ᴜꜱᴇʀ {target_uid}")
    except:
        await update.message.reply_text("⊗ ɪɴᴠᴀʟɪᴅ ᴜɪᴅ")

async def ps_rmrarity(update: Update, context: CallbackContext):
    if str(update.effective_user.id) not in sudo_users:
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /psrmrarity <rarity_name>")
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
        await ps_config_collection.update_one({"_id": "ps_config"}, {"$set": cfg}, upsert=True)
        await update.message.reply_text(f"✓ ʀᴇᴍᴏᴠᴇᴅ '<b>{name}</b>'", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"⊗ ᴇʀʀᴏʀ: {str(e)}")

# Register handlers
application.add_handler(CommandHandler("ps", ps, block=False))
application.add_handler(CommandHandler("psstats", ps_stats, block=False))
application.add_handler(CommandHandler("pshelp", ps_help, block=False))
application.add_handler(CommandHandler("psview", ps_view, block=False))
application.add_handler(CommandHandler("psconfig", ps_config, block=False))
application.add_handler(CommandHandler("psrarity", ps_rarity, block=False))
application.add_handler(CommandHandler("psrmrarity", ps_rmrarity, block=False))
application.add_handler(CommandHandler("psreset", ps_reset, block=False))
application.add_handler(CallbackQueryHandler(ps_callback, pattern=r"^ps_", block=False))