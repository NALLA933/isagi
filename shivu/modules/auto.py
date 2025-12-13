import asyncio
import random
import time
from typing import List, Dict, Tuple, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from telegram.error import TelegramError
from shivu import application, user_collection, collection

HAREM_MODE_MAPPING = {
    "common": "🟢 Common", "rare": "🟣 Rare", "legendary": "🟡 Legendary",
    "special": "💮 Special Edition", "neon": "💫 Neon", "manga": "✨ Manga",
    "cosplay": "🎭 Cosplay", "celestial": "🎐 Celestial", "premium": "🔮 Premium Edition",
    "erotic": "💋 Erotic", "summer": "🌤 Summer", "winter": "☃️ Winter",
    "monsoon": "☔️ Monsoon", "valentine": "💝 Valentine", "halloween": "🎃 Halloween",
    "christmas": "🎄 Christmas", "mythic": "🏵 Mythic", "events": "🎗 Special Events",
    "amv": "🎥 AMV", "tiny": "👼 Tiny", "default": None
}

RARITY_TIERS = {
    "🟢 Common": 1, "🟣 Rare": 2, "🟡 Legendary": 3, "💮 Special Edition": 4,
    "💫 Neon": 5, "✨ Manga": 5, "🎭 Cosplay": 5, "🎐 Celestial": 6,
    "🔮 Premium Edition": 6, "💋 Erotic": 6, "🌤 Summer": 4, "☃️ Winter": 4,
    "☔️ Monsoon": 4, "💝 Valentine": 5, "🎃 Halloween": 5, "🎄 Christmas": 5,
    "🏵 Mythic": 7, "🎗 Special Events": 6, "🎥 AMV": 5, "👼 Tiny": 4
}

FUSION_COSTS = {1: 500, 2: 1000, 3: 2000, 4: 3500, 5: 5000, 6: 7500, 7: 10000}
FUSION_SUCCESS_RATES = {0: 0.85, 1: 0.70, 2: 0.55, 3: 0.40}
STONE_BOOST = 0.15
COOLDOWN_TIME = 1800
ANIMATIONS = ["⚡", "🌀", "✨", "💫", "🔮"]

cooldowns = {}
sessions = {}

def get_tier(rarity: str) -> int:
    return RARITY_TIERS.get(rarity, 1)

def calc_cost(r1: str, r2: str) -> int:
    return FUSION_COSTS.get((get_tier(r1) + get_tier(r2)) // 2, 1000)

def calc_rate(r1: str, r2: str, stones: int = 0) -> float:
    diff = abs(get_tier(r1) - get_tier(r2))
    return min(FUSION_SUCCESS_RATES.get(min(diff, 3), 0.40) + min(stones, 3) * STONE_BOOST, 0.95)

def get_result_rarity(r1: str, r2: str) -> str:
    result_tier = min(max(get_tier(r1), get_tier(r2)) + 1, 7)
    return next((r for r, t in RARITY_TIERS.items() if t == result_tier), "🏵 Mythic")

def check_cd(uid: int) -> Tuple[bool, int]:
    if uid in cooldowns and time.time() - cooldowns[uid] < COOLDOWN_TIME:
        return False, int(COOLDOWN_TIME - (time.time() - cooldowns[uid]))
    return True, 0

async def get_chars(uid: int) -> List[Dict]:
    user = await user_collection.find_one({'id': uid})
    return user.get('characters', []) if user else []

async def get_user_data(uid: int) -> Dict:
    return await user_collection.find_one({'id': uid}) or {}

async def update_balance(uid: int, amount: int) -> bool:
    user = await get_user_data(uid)
    if user.get('balance', 0) < abs(amount):
        return False
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': amount}})
    return True

async def update_stones(uid: int, amount: int) -> bool:
    user = await get_user_data(uid)
    if amount < 0 and user.get('fusion_stones', 0) < abs(amount):
        return False
    await user_collection.update_one({'id': uid}, {'$inc': {'fusion_stones': amount}}, upsert=True)
    return True

async def remove_chars(uid: int, ids: List[str]) -> bool:
    chars = await get_chars(uid)
    for cid in ids:
        for i, c in enumerate(chars):
            if c.get('id') == cid:
                chars.pop(i)
                break
    await user_collection.update_one({'id': uid}, {'$set': {'characters': chars}})
    return True

async def add_char(uid: int, char: Dict) -> bool:
    await user_collection.update_one({'id': uid}, {'$push': {'characters': char}})
    return True

async def fuse_cmd(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    
    can_use, remaining = check_cd(uid)
    if not can_use:
        await update.message.reply_text(
            f"⏱️ cooldown active\nwait {remaining//60}m {remaining%60}s",
            parse_mode='HTML'
        )
        return
    
    chars = await get_chars(uid)
    if len(chars) < 2:
        await update.message.reply_text("❌ need at least 2 characters\nuse /grab")
        return
    
    buttons = [[InlineKeyboardButton(
        f"{c.get('rarity', '🟢')} {c.get('name', 'unknown')[:12]}",
        callback_data=f"fs1_{c.get('id')}"
    )] for c in chars[:8]]
    buttons.append([InlineKeyboardButton("❌ cancel", callback_data="fc")])
    
    sessions[uid] = {'step': 1, 'owner': uid}
    
    await update.message.reply_text(
        f"⚗️ fusion lab\n\nselect first character:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    
    if data == "fc":
        sessions.pop(uid, None)
        await query.edit_message_text("❌ cancelled")
        return
    
    session = sessions.get(uid)
    if not session or session.get('owner') != uid:
        await query.answer("❌ not your session", show_alert=True)
        return
    
    await query.answer()
    
    if data.startswith("fs1_"):
        cid = data[4:]
        chars = await get_chars(uid)
        char1 = next((c for c in chars if c.get('id') == cid), None)
        
        if not char1:
            await query.edit_message_text("❌ character not found")
            return
        
        sessions[uid] = {'step': 2, 'c1': cid, 'c1_data': char1, 'stones': 0, 'owner': uid}
        
        buttons = [[InlineKeyboardButton(
            f"{c.get('rarity', '🟢')} {c.get('name', 'unknown')[:12]}",
            callback_data=f"fs2_{c.get('id')}"
        )] for c in chars[:8] if c.get('id') != cid]
        buttons.append([InlineKeyboardButton("❌ cancel", callback_data="fc")])
        
        try:
            await query.edit_message_media(
                media=InputMediaPhoto(
                    media=char1.get('img_url', ''),
                    caption=f"✅ selected: {char1.get('rarity')} {char1.get('name')}\n\nselect second character:"
                ),
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except:
            await query.edit_message_text(
                f"✅ selected: {char1.get('rarity')} {char1.get('name')}\n\nselect second character:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
    
    elif data.startswith("fs2_"):
        cid = data[4:]
        chars = await get_chars(uid)
        char2 = next((c for c in chars if c.get('id') == cid), None)
        
        if not char2:
            await query.edit_message_text("❌ character not found")
            return
        
        session['c2'] = cid
        session['c2_data'] = char2
        await show_confirm(query, uid)
    
    elif data.startswith("fst_"):
        stones = int(data[4])
        if not await update_stones(uid, 0):
            user_stones = (await get_user_data(uid)).get('fusion_stones', 0)
            if user_stones < stones:
                await query.answer(f"❌ need {stones} stones (have {user_stones})", show_alert=True)
                return
        
        session['stones'] = stones
        await show_confirm(query, uid)
    
    elif data == "fconf":
        await execute_fusion(query, uid)
    
    elif data == "fshop":
        await show_shop(query, uid)
    
    elif data.startswith("fb_"):
        amount = int(data[3:])
        prices = {1: 100, 5: 450, 10: 850, 20: 1600}
        cost = prices.get(amount, 0)
        
        if not await update_balance(uid, -cost):
            bal = (await get_user_data(uid)).get('balance', 0)
            await query.answer(f"❌ need {cost:,} coins (have {bal:,})", show_alert=True)
            return
        
        await update_stones(uid, amount)
        await query.answer(f"✅ bought {amount} stones!", show_alert=True)
        await show_shop(query, uid)

async def show_confirm(query, uid: int):
    session = sessions[uid]
    c1 = session['c1_data']
    c2 = session['c2_data']
    stones = session.get('stones', 0)
    
    r1, r2 = c1.get('rarity'), c2.get('rarity')
    result_r = get_result_rarity(r1, r2)
    cost = calc_cost(r1, r2)
    rate = calc_rate(r1, r2, stones)
    
    user = await get_user_data(uid)
    bal = user.get('balance', 0)
    user_stones = user.get('fusion_stones', 0)
    
    buttons = []
    stone_btns = [InlineKeyboardButton(
        f"{'✅' if stones == i else '💎'} {i} stone{'s' if i > 1 else ''}",
        callback_data=f"fst_{i}"
    ) for i in range(1, 4) if user_stones >= i]
    
    if stone_btns:
        buttons.append(stone_btns[:2] if len(stone_btns) > 1 else stone_btns)
        if len(stone_btns) > 2:
            buttons.append([stone_btns[2]])
    
    buttons.extend([
        [InlineKeyboardButton("✅ fuse" if bal >= cost else "❌ insufficient", callback_data="fconf" if bal >= cost else "fc")],
        [InlineKeyboardButton("💎 buy stones", callback_data="fshop"), InlineKeyboardButton("❌ cancel", callback_data="fc")]
    ])
    
    caption = (
        f"⚗️ fusion preview\n\n"
        f"1️⃣ {r1} {c1.get('name')}\n"
        f"2️⃣ {r2} {c2.get('name')}\n"
        f"➡️ {result_r}\n\n"
        f"success: {rate*100:.0f}%\n"
        f"cost: {cost:,} 💰\n"
        f"balance: {bal:,} 💰\n"
        f"stones: {stones} (+{stones*15}%)" if stones else f"stones: 0"
    )
    
    try:
        media_group = [
            InputMediaPhoto(media=c1.get('img_url', ''), caption=f"1️⃣ {c1.get('name')}"),
            InputMediaPhoto(media=c2.get('img_url', ''), caption=f"2️⃣ {c2.get('name')}")
        ]
        await query.message.reply_media_group(media=media_group)
        await query.edit_message_text(caption, reply_markup=InlineKeyboardMarkup(buttons))
    except:
        await query.edit_message_text(caption, reply_markup=InlineKeyboardMarkup(buttons))

async def execute_fusion(query, uid: int):
    session = sessions.get(uid)
    if not session:
        await query.edit_message_text("❌ session expired")
        return
    
    c1, c2 = session['c1_data'], session['c2_data']
    stones = session.get('stones', 0)
    cost = calc_cost(c1.get('rarity'), c2.get('rarity'))
    
    if not await update_balance(uid, -cost):
        await query.edit_message_text("❌ insufficient balance")
        return
    
    if stones > 0 and not await update_stones(uid, -stones):
        await update_balance(uid, cost)
        await query.edit_message_text("❌ stone error")
        return
    
    await remove_chars(uid, [session['c1'], session['c2']])
    
    for i, anim in enumerate(ANIMATIONS):
        await query.edit_message_text(f"{anim} fusing... {i*20}%")
        await asyncio.sleep(1)
    
    rate = calc_rate(c1.get('rarity'), c2.get('rarity'), stones)
    success = random.random() < rate
    
    if success:
        result_r = get_result_rarity(c1.get('rarity'), c2.get('rarity'))
        new_chars = await collection.aggregate([
            {'$match': {'rarity': result_r}},
            {'$sample': {'size': 1}}
        ]).to_list(length=None)
        
        if new_chars:
            new_char = new_chars[0]
            await add_char(uid, new_char)
            
            await query.message.reply_photo(
                photo=new_char.get('img_url', ''),
                caption=f"✨ success!\n\n{result_r}\n{new_char.get('name')}\n{new_char.get('anime', 'unknown')}\nid: {new_char.get('id')}"
            )
            await query.edit_message_text("✅ fusion complete!")
        else:
            await update_balance(uid, cost)
            await query.edit_message_text("❌ no result available (refunded)")
    else:
        await query.edit_message_text(f"💔 failed\n\nlost:\n{c1.get('name')}\n{c2.get('name')}")
    
    cooldowns[uid] = time.time()
    sessions.pop(uid, None)

async def show_shop(query, uid: int):
    user = await get_user_data(uid)
    bal = user.get('balance', 0)
    stones = user.get('fusion_stones', 0)
    
    buttons = [
        [InlineKeyboardButton("💎 1 - 100", callback_data="fb_1"), InlineKeyboardButton("💎 5 - 450", callback_data="fb_5")],
        [InlineKeyboardButton("💎 10 - 850", callback_data="fb_10"), InlineKeyboardButton("💎 20 - 1600", callback_data="fb_20")],
        [InlineKeyboardButton("⬅️ back", callback_data="fc")]
    ]
    
    await query.edit_message_text(
        f"💎 stone shop\n\nbalance: {bal:,} 💰\nstones: {stones}\n\n"
        f"1 stone = 100 💰\n5 stones = 450 💰 (10% off)\n10 stones = 850 💰 (15% off)\n20 stones = 1600 💰 (20% off)\n\n"
        f"+15% success per stone (max 3)",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def info_cmd(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user_data(uid)
    chars = await get_chars(uid)
    
    can_use, remaining = check_cd(uid)
    status = "ready ✅" if can_use else f"cooldown {remaining//60}m {remaining%60}s ⏱️"
    
    rarity_count = {}
    for c in chars:
        r = c.get('rarity', '🟢 Common')
        rarity_count[r] = rarity_count.get(r, 0) + 1
    
    top_rarities = sorted(rarity_count.items(), key=lambda x: get_tier(x[0]), reverse=True)[:5]
    rarity_text = "\n".join([f"{r}: {cnt}" for r, cnt in top_rarities]) or "none"
    
    await update.message.reply_text(
        f"⚗️ fusion info\n\n"
        f"balance: {user.get('balance', 0):,} 💰\n"
        f"stones: {user.get('fusion_stones', 0)} 💎\n"
        f"characters: {len(chars)}\n"
        f"status: {status}\n\n"
        f"top rarities:\n{rarity_text}\n\n"
        f"rates:\nsame tier: 85%\n1 diff: 70%\n2 diff: 55%\n3+ diff: 40%\n\n"
        f"/fuse - start fusion\n/buystone - quick shop"
    )

async def buystone_cmd(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user_data(uid)
    
    buttons = [
        [InlineKeyboardButton("💎 1 - 100", callback_data="fb_1"), InlineKeyboardButton("💎 5 - 450", callback_data="fb_5")],
        [InlineKeyboardButton("💎 10 - 850", callback_data="fb_10"), InlineKeyboardButton("💎 20 - 1600", callback_data="fb_20")],
        [InlineKeyboardButton("❌ close", callback_data="fc")]
    ]
    
    await update.message.reply_text(
        f"💎 stone shop\n\nbalance: {user.get('balance', 0):,} 💰\nstones: {user.get('fusion_stones', 0)}\n\n"
        f"packages:\n1 = 100 💰\n5 = 450 💰 (save 50)\n10 = 850 💰 (save 150)\n20 = 1600 💰 (save 400)",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

application.add_handler(CommandHandler(['fuse', 'fusion'], fuse_cmd, block=False))
application.add_handler(CommandHandler(['fusioninfo', 'finfo'], info_cmd, block=False))
application.add_handler(CommandHandler(['buystone', 'buystones'], buystone_cmd, block=False))
application.add_handler(CallbackQueryHandler(callback_handler, pattern='^f', block=False))