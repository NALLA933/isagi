import random 
import asyncio
from datetime import datetime, timedelta 
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto 
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler 
from shivu import application, db, user_collection 

# --- DATABASE SETUP ---
collection = db['anime_characters_lol'] 
luv_config_collection = db['luv_config'] 
super_admin = "6863917190"

# --- PREMIUM DESIGN STYLE ---
class Style:
    PS = "✨ ᴘʀɪᴠᴀᴛᴇ ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ ✨"
    LINE = "──────────────────"
    NAME = "🌸 ɴᴀᴍᴇ :"
    ANIME = "🎬 ᴀɴɪᴍᴇ :"
    RARITY = "💎 ʀᴀʀɪᴛʏ :"
    OLD_PRICE = "💰 ᴏʀɪɢɪɴᴀʟ :"
    DISCOUNT = "🏷️ ᴅɪsᴄᴏᴜɴᴛ :"
    DEAL = "🔥 ᴅᴇᴀʟ ᴘʀɪᴄᴇ :"
    WALLET = "💵 ʙᴀʟᴀɴᴄᴇ :"

# --- CONFIGURATION ---
DEFAULT_CONFIG = { 
    "rarities": { 
        "🟢 Common": {"weight": 60, "min_price": 2000, "max_price": 4000}, 
        "Purple Rare": {"weight": 25, "min_price": 5000, "max_price": 9000}, 
        "Yellow Legendary": {"weight": 10, "min_price": 12000, "max_price": 20000}, 
        "Special Edition": {"weight": 5, "min_price": 35000, "max_price": 60000} 
    }, 
    "refresh_cost": 20000, 
    "refresh_limit": 2, 
    "store_items": 3, 
    "cooldown_hours": 24 
} 

panel_owners = {}
market_deals = {} # Stores pricing for each session

# --- PRICE & DISCOUNT LOGIC ---
def generate_deal(cfg, rarity):
    rarity_data = cfg['rarities'].get(rarity, {"min_price": 1000, "max_price": 5000})
    min_p = rarity_data.get('min_price')
    max_p = rarity_data.get('max_price')
    
    # 1. Base price select karna
    original_price = random.randint(min_p, max_p)
    
    # 2. 5% se 20% ke beech random discount
    discount_pct = random.randint(5, 20)
    
    # 3. Discount ke baad wala price calculate karna
    discount_amount = (original_price * discount_pct) // 100
    final_price = original_price - discount_amount
    
    return {
        "original": original_price,
        "percent": discount_pct,
        "final": final_price
    }

async def get_config(): 
    cfg = await luv_config_collection.find_one({"_id": "luv_config"}) 
    return cfg if cfg else DEFAULT_CONFIG

async def generate_chars(uid, cfg): 
    chars = [] 
    market_deals[uid] = {}
    for _ in range(cfg.get('store_items', 3)): 
        rarity = random.choices(list(cfg['rarities'].keys()), [cfg['rarities'][r]['weight'] for r in cfg['rarities']], k=1)[0] 
        char = await collection.aggregate([{'$match': {'rarity': rarity}}, {'$sample': {'size': 1}}]).to_list(length=1) 
        if char: 
            cid = str(char[0].get("id") or char[0].get("_id"))
            market_deals[uid][cid] = generate_deal(cfg, rarity)
            chars.append(char[0]) 
    return chars 

# --- UI BUILDER ---
async def build_caption(char, cfg, page, total, luv_data, balance, uid): 
    cid = str(char.get("id") or char.get("_id"))
    deal = market_deals.get(uid, {}).get(cid)
    if not deal:
        deal = generate_deal(cfg, char.get('rarity'))
        market_deals.setdefault(uid, {})[cid] = deal

    purchased = luv_data.get('purchased', [])
    price_tag = "✅ ᴀʟʀᴇᴀᴅʏ ᴏᴡɴᴇᴅ" if cid in purchased else f"<b>{deal['final']:,} ɢᴏʟᴅ</b>"

    caption = ( 
        f"<b>{Style.PS}</b>\n" 
        f"{Style.LINE}\n" 
        f"<b>{Style.NAME}</b> <code>{char.get('name')}</code>\n" 
        f"<b>{Style.ANIME}</b> <code>{char.get('anime')}</code>\n" 
        f"<b>{Style.RARITY}</b> {char.get('rarity')}\n" 
        f"<b>🆔 ɪᴅ :</b> <code>#{cid}</code>\n"
        f"{Style.LINE}\n"
        f"<b>{Style.OLD_PRICE}</b> <strike>{deal['original']:,}</strike> ɢ\n"
        f"<b>{Style.DISCOUNT}</b> <code>{deal['percent']}% ᴏꜰꜰ</code>\n"
        f"<b>{Style.DEAL}</b> {price_tag}\n"
        f"{Style.LINE}\n"
        f"<b>{Style.WALLET}</b> <code>{balance:,} ɢᴏʟᴅ</code>\n"
        f"<b>ᴘᴀɢᴇ :</b> <code>{page}/{total}</code>"
    )
    return caption, char.get("img_url", ""), deal['final'], cid in purchased 

# --- MAIN HANDLERS ---
async def luv(update: Update, context: CallbackContext): 
    uid = update.effective_user.id 
    cfg = await get_config() 
    user = await user_collection.find_one({"id": uid}) 
    if not user: return await update.message.reply_text("❌ ꜱᴛᴀʀᴛ ʙᴏᴛ ꜰɪʀꜱᴛ!") 

    luv_data = user.get('private_store', {'characters': [], 'last_reset': None, 'purchased': []})
    
    # Auto-Reset Logic (24 Hours)
    needs_reset = True
    if luv_data.get('last_reset'):
        lr = datetime.fromisoformat(luv_data['last_reset']) if isinstance(luv_data['last_reset'], str) else luv_data['last_reset']
        if (datetime.utcnow() - lr).total_seconds() < (cfg['cooldown_hours'] * 3600):
            needs_reset = False

    if needs_reset or not luv_data.get('characters'):
        chars = await generate_chars(uid, cfg)
        luv_data = {'characters': chars, 'last_reset': datetime.utcnow().isoformat(), 'purchased': []}
        await user_collection.update_one({"id": uid}, {"$set": {"private_store": luv_data}}, upsert=True)

    context.user_data['luv_chars'] = luv_data['characters']
    caption, img, final_price, owned = await build_caption(luv_data['characters'][0], cfg, 1, len(luv_data['characters']), luv_data, user.get('balance', 0), uid)
    
    btns = []
    if not owned: btns.append([InlineKeyboardButton("🛒 ᴘᴜʀᴄʜᴀsᴇ ᴅᴇᴀʟ", callback_data=f"luv_buy_{str(luv_data['characters'][0].get('id'))}_{uid}")])
    btns.append([InlineKeyboardButton("⟲ ʀᴇғʀᴇsʜ ʟɪsᴛ", callback_data=f"luv_ref_{uid}"), InlineKeyboardButton("ɴᴇxᴛ ⊳", callback_data=f"luv_page_1_{uid}")])
    
    msg = await update.message.reply_photo(photo=img, caption=caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
    panel_owners[msg.message_id] = uid

async def luv_callback(update: Update, context: CallbackContext):
    q = update.callback_query
    uid = q.from_user.id
    if panel_owners.get(q.message.message_id) != uid:
        return await q.answer("⚠️ ᴛʜɪs ɪs ɴᴏᴛ ʏᴏᴜʀ sʜᴏᴘ!", show_alert=True)

    data = q.data.split("_")
    cfg = await get_config()
    user = await user_collection.find_one({"id": uid})
    luv_data = user.get('private_store')

    if data[1] == "page":
        page = int(data[2])
        char = luv_data['characters'][page]
        caption, img, f_price, owned = await build_caption(char, cfg, page+1, len(luv_data['characters']), luv_data, user.get('balance', 0), uid)
        
        btns = []
        if not owned: btns.append([InlineKeyboardButton("🛒 ᴘᴜʀᴄʜᴀsᴇ ᴅᴇᴀʟ", callback_data=f"luv_buy_{str(char.get('id'))}_{uid}")])
        nav = []
        if page > 0: nav.append(InlineKeyboardButton("⊲ ᴘʀᴇᴠ", callback_data=f"luv_page_{page-1}_{uid}"))
        if page < len(luv_data['characters'])-1: nav.append(InlineKeyboardButton("ɴᴇxᴛ ⊳", callback_data=f"luv_page_{page+1}_{uid}"))
        btns.append(nav)
        
        await q.edit_message_media(media=InputMediaPhoto(media=img, caption=caption, parse_mode="HTML"), reply_markup=InlineKeyboardMarkup(btns))

    elif data[1] == "buy":
        cid = data[2]
        deal = market_deals.get(uid, {}).get(cid)
        if user.get('balance', 0) < deal['final']:
            return await q.answer("❌ ɪɴsᴜғғɪᴄɪᴇɴᴛ ɢᴏʟᴅ!", show_alert=True)
        
        char = next(c for c in luv_data['characters'] if str(c.get("id")) == cid)
        await user_collection.update_one({"id": uid}, {"$inc": {"balance": -deal['final']}, "$push": {"characters": char, "private_store.purchased": cid}})
        await q.answer("🎊 ᴘᴜʀᴄʜᴀsᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!", show_alert=True)
        # Refresh current view
        await q.message.delete()

application.add_handler(CommandHandler("ps", luv, block=False))
application.add_handler(CallbackQueryHandler(luv_callback, pattern=r"^luv_", block=False))
