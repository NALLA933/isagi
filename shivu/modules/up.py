import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dataclasses import dataclass

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from shivu import application, user_collection

SMALLCAPS_MAP = {
    'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ғ', 'g': 'ɢ', 'h': 'ʜ',
    'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ',
    'q': 'ǫ', 'r': 'ʀ', 's': 's', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x',
    'y': 'ʏ', 'z': 'ᴢ',
    'A': 'ᴀ', 'B': 'ʙ', 'C': 'ᴄ', 'D': 'ᴅ', 'E': 'ᴇ', 'F': 'ғ', 'G': 'ɢ', 'H': 'ʜ',
    'I': 'ɪ', 'J': 'ᴊ', 'K': 'ᴋ', 'L': 'ʟ', 'M': 'ᴍ', 'N': 'ɴ', 'O': 'ᴏ', 'P': 'ᴘ',
    'Q': 'ǫ', 'R': 'ʀ', 'S': 's', 'T': 'ᴛ', 'U': 'ᴜ', 'V': 'ᴠ', 'W': 'ᴡ', 'X': 'x',
    'Y': 'ʏ', 'Z': 'ᴢ'
}

def sc(text: str) -> str:
    return ''.join(SMALLCAPS_MAP.get(c, c) for c in text)

@dataclass
class ShopItem:
    item_id: str
    name: str
    description: str
    price_coins: int
    price_tokens: int
    emoji: str
    category: str
    effect_type: str
    effect_value: int
    duration: int
    max_stack: int
    level_required: int

SHOP_ITEMS = {
    "hp_potion_small": ShopItem(
        "hp_potion_small", "Small HP Potion", "Restores 50 HP instantly",
        100, 0, "🧪", "consumable", "heal_hp", 50, 0, 99, 1
    ),
    "hp_potion_medium": ShopItem(
        "hp_potion_medium", "Medium HP Potion", "Restores 150 HP instantly",
        250, 0, "💊", "consumable", "heal_hp", 150, 0, 99, 10
    ),
    "hp_potion_large": ShopItem(
        "hp_potion_large", "Large HP Potion", "Restores 300 HP instantly",
        500, 0, "🍶", "consumable", "heal_hp", 300, 0, 99, 20
    ),
    
    "mana_potion_small": ShopItem(
        "mana_potion_small", "Small Mana Potion", "Restores 40 Mana instantly",
        120, 0, "🔵", "consumable", "heal_mana", 40, 0, 99, 1
    ),
    "mana_potion_medium": ShopItem(
        "mana_potion_medium", "Medium Mana Potion", "Restores 100 Mana instantly",
        280, 0, "💙", "consumable", "heal_mana", 100, 0, 99, 10
    ),
    "mana_potion_large": ShopItem(
        "mana_potion_large", "Large Mana Potion", "Restores 200 Mana instantly",
        550, 0, "🌊", "consumable", "heal_mana", 200, 0, 99, 20
    ),
    
    "elixir": ShopItem(
        "elixir", "Full Elixir", "Restores all HP and Mana",
        1000, 5, "✨", "consumable", "full_restore", 0, 0, 10, 30
    ),
    
    "fire_crystal": ShopItem(
        "fire_crystal", "Fire Crystal", "Boost Fire attacks by 25% for 3 turns",
        400, 0, "🔥", "buff", "fire_boost", 25, 3, 5, 15
    ),
    "ice_crystal": ShopItem(
        "ice_crystal", "Ice Crystal", "Boost Ice attacks by 25% for 3 turns",
        400, 0, "❄️", "buff", "ice_boost", 25, 3, 5, 15
    ),
    "lightning_crystal": ShopItem(
        "lightning_crystal", "Lightning Crystal", "Boost Lightning attacks by 25% for 3 turns",
        400, 0, "⚡", "buff", "lightning_boost", 25, 3, 5, 15
    ),
    "water_crystal": ShopItem(
        "water_crystal", "Water Crystal", "Boost Water attacks by 25% for 3 turns",
        400, 0, "💧", "buff", "water_boost", 25, 3, 5, 15
    ),
    "earth_crystal": ShopItem(
        "earth_crystal", "Earth Crystal", "Boost Earth attacks by 25% for 3 turns",
        400, 0, "🌍", "buff", "earth_boost", 25, 3, 5, 15
    ),
    "wind_crystal": ShopItem(
        "wind_crystal", "Wind Crystal", "Boost Wind attacks by 25% for 3 turns",
        400, 0, "💨", "buff", "wind_boost", 25, 3, 5, 15
    ),
    "dark_crystal": ShopItem(
        "dark_crystal", "Dark Crystal", "Boost Dark attacks by 25% for 3 turns",
        400, 0, "🌑", "buff", "dark_boost", 25, 3, 5, 15
    ),
    "light_crystal": ShopItem(
        "light_crystal", "Light Crystal", "Boost Light attacks by 25% for 3 turns",
        400, 0, "✨", "buff", "light_boost", 25, 3, 5, 15
    ),
    
    "strength_potion": ShopItem(
        "strength_potion", "Strength Potion", "+30% Attack for 5 turns",
        600, 0, "💪", "buff", "attack_boost", 30, 5, 5, 20
    ),
    "defense_potion": ShopItem(
        "defense_potion", "Defense Potion", "+40% Defense for 5 turns",
        600, 0, "🛡️", "buff", "defense_boost", 40, 5, 5, 20
    ),
    "speed_potion": ShopItem(
        "speed_potion", "Speed Potion", "+35% Speed for 5 turns",
        600, 0, "⚡", "buff", "speed_boost", 35, 5, 5, 20
    ),
    
    "phoenix_feather": ShopItem(
        "phoenix_feather", "Phoenix Feather", "Auto-revive with 50% HP once per battle",
        2000, 10, "🪶", "special", "revive", 50, 0, 3, 40
    ),
    
    "lucky_charm": ShopItem(
        "lucky_charm", "Lucky Charm", "+15% Critical Hit chance for 5 turns",
        800, 0, "🍀", "buff", "crit_boost", 15, 5, 5, 25
    ),
    
    "smoke_bomb": ShopItem(
        "smoke_bomb", "Smoke Bomb", "+30% Dodge chance for 3 turns",
        500, 0, "💨", "buff", "dodge_boost", 30, 3, 5, 15
    ),
    
    "battle_ticket": ShopItem(
        "battle_ticket", "Battle Ticket", "+5 AI battles for today",
        1500, 0, "🎫", "special", "ai_battles", 5, 0, 3, 1
    ),
    
    "pvp_ticket": ShopItem(
        "pvp_ticket", "PVP Ticket", "+5 PVP battles for today",
        2000, 0, "🎟️", "special", "pvp_battles", 5, 0, 3, 1
    ),
    
    "exp_boost": ShopItem(
        "exp_boost", "EXP Booster", "+50% EXP gain for 24 hours",
        3000, 15, "⭐", "boost", "exp_boost", 50, 1440, 1, 30
    ),
    
    "coin_boost": ShopItem(
        "coin_boost", "Coin Booster", "+50% Coin gain for 24 hours",
        2500, 12, "💰", "boost", "coin_boost", 50, 1440, 1, 25
    ),
    
    "master_scroll": ShopItem(
        "master_scroll", "Master Scroll", "Instantly learn one locked attack",
        5000, 25, "📜", "special", "unlock_attack", 1, 0, 10, 50
    ),
}

SHOP_CATEGORIES = {
    "consumable": {"name": "Consumables", "emoji": "🧪", "desc": "Potions and instant-use items"},
    "buff": {"name": "Buffs", "emoji": "✨", "desc": "Temporary stat boosters"},
    "special": {"name": "Special", "emoji": "🎁", "desc": "Unique powerful items"},
    "boost": {"name": "Boosters", "emoji": "⚡", "desc": "Long-term enhancements"},
}

async def get_user(uid: int):
    try:
        return await user_collection.find_one({'id': uid})
    except:
        return None

async def get_inventory(uid: int) -> Dict[str, int]:
    doc = await get_user(uid)
    if not doc:
        return {}
    return doc.get('battle_inventory', {})

async def add_item_to_inventory(uid: int, item_id: str, quantity: int = 1):
    inventory = await get_inventory(uid)
    current = inventory.get(item_id, 0)
    inventory[item_id] = current + quantity
    
    try:
        await user_collection.update_one(
            {'id': uid},
            {'$set': {'battle_inventory': inventory}},
            upsert=True
        )
        return True
    except:
        return False

async def remove_item_from_inventory(uid: int, item_id: str, quantity: int = 1):
    inventory = await get_inventory(uid)
    current = inventory.get(item_id, 0)
    
    if current < quantity:
        return False
    
    inventory[item_id] = current - quantity
    if inventory[item_id] <= 0:
        inventory.pop(item_id, None)
    
    try:
        await user_collection.update_one(
            {'id': uid},
            {'$set': {'battle_inventory': inventory}},
            upsert=True
        )
        return True
    except:
        return False

async def get_active_boosts(uid: int) -> List[Dict]:
    doc = await get_user(uid)
    if not doc:
        return []
    
    boosts = doc.get('active_boosts', [])
    active_boosts = []
    
    for boost in boosts:
        expires_at = datetime.fromisoformat(boost['expires_at'])
        if datetime.utcnow() < expires_at:
            active_boosts.append(boost)
    
    if len(active_boosts) != len(boosts):
        try:
            await user_collection.update_one(
                {'id': uid},
                {'$set': {'active_boosts': active_boosts}}
            )
        except:
            pass
    
    return active_boosts

async def add_boost(uid: int, boost_type: str, value: int, duration_minutes: int):
    expires_at = datetime.utcnow() + timedelta(minutes=duration_minutes)
    
    boost = {
        'type': boost_type,
        'value': value,
        'expires_at': expires_at.isoformat()
    }
    
    try:
        await user_collection.update_one(
            {'id': uid},
            {'$push': {'active_boosts': boost}},
            upsert=True
        )
        return True
    except:
        return False

def calc_level(xp: int) -> int:
    import math
    return min(max(1, math.floor(math.sqrt(max(xp, 0) / 100)) + 1), 100)

def create_shop_main_menu(uid: int) -> InlineKeyboardMarkup:
    keyboard = []
    
    for cat_id, cat_data in SHOP_CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(
            f"{cat_data['emoji']} {sc(cat_data['name'])}",
            callback_data=f"shop_{cat_id}_{uid}"
        )])
    
    keyboard.append([InlineKeyboardButton(
        f"🎒 {sc('my inventory')}",
        callback_data=f"shop_inv_{uid}"
    )])
    
    keyboard.append([InlineKeyboardButton(
        f"📊 {sc('active boosts')}",
        callback_data=f"shop_boosts_{uid}"
    )])
    
    keyboard.append([InlineKeyboardButton(
        f"◀️ {sc('back to menu')}",
        callback_data=f"shop_menu_{uid}"
    )])
    
    return InlineKeyboardMarkup(keyboard)

def create_category_menu(category: str, uid: int, player_level: int) -> InlineKeyboardMarkup:
    keyboard = []
    
    items = [item for item in SHOP_ITEMS.values() if item.category == category]
    items.sort(key=lambda x: x.price_coins)
    
    for item in items:
        locked = "🔒" if item.level_required > player_level else ""
        price_text = f"{item.price_coins}💰" if item.price_tokens == 0 else f"{item.price_tokens}🎫"
        
        keyboard.append([InlineKeyboardButton(
            f"{item.emoji} {item.name} - {price_text} {locked}",
            callback_data=f"shop_view_{item.item_id}_{uid}"
        )])
    
    keyboard.append([InlineKeyboardButton(
        f"◀️ {sc('back')}",
        callback_data=f"shop_home_{uid}"
    )])
    
    return InlineKeyboardMarkup(keyboard)

def create_item_detail_menu(item_id: str, uid: int, quantity: int = 0) -> InlineKeyboardMarkup:
    item = SHOP_ITEMS.get(item_id)
    if not item:
        return InlineKeyboardMarkup([[]])
    
    keyboard = []
    
    keyboard.append([
        InlineKeyboardButton(f"💰 {sc('buy with coins')}", callback_data=f"shop_coin_{item_id}_{uid}"),
    ])
    
    if item.price_tokens > 0:
        keyboard.append([
            InlineKeyboardButton(f"🎫 {sc('buy with tokens')}", callback_data=f"shop_token_{item_id}_{uid}"),
        ])
    
    if quantity > 0 and item.category in ["consumable", "buff"]:
        keyboard.append([
            InlineKeyboardButton(f"🎒 {sc('use item')} (x{quantity})", callback_data=f"shop_use_{item_id}_{uid}"),
        ])
    
    keyboard.append([InlineKeyboardButton(
        f"◀️ {sc('back')}",
        callback_data=f"shop_{item.category}_{uid}"
    )])
    
    return InlineKeyboardMarkup(keyboard)

async def shop_main(update: Update, context: CallbackContext):
    user = update.effective_user
    doc = await get_user(user.id)
    
    balance = doc.get('balance', 0) if doc else 0
    tokens = doc.get('tokens', 0) if doc else 0
    xp = doc.get('user_xp', 0) if doc else 0
    level = calc_level(xp)
    
    text = f"""<b>🛒 {sc('battle shop')} 🛒</b>
━━━━━━━━━━━━━━━━━━━━

<b>{sc('your wallet')}</b>
💰 Coins: <code>{balance}</code>
🎫 Tokens: <code>{tokens}</code>
⭐ Level: <code>{level}</code>

<b>{sc('shop categories:')}</b>
"""
    
    for cat_id, cat_data in SHOP_CATEGORIES.items():
        items_count = len([i for i in SHOP_ITEMS.values() if i.category == cat_id])
        text += f"\n{cat_data['emoji']} <b>{cat_data['name']}</b> ({items_count} items)\n<i>{cat_data['desc']}</i>"
    
    text += f"\n\n<i>{sc('select a category to browse items!')}</i>"
    
    kb = create_shop_main_menu(user.id)
    
    if hasattr(update, 'callback_query') and update.callback_query:
        try:
            await update.callback_query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except:
            pass
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")

async def shop_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data.split("_")
    
    if len(data) < 2:
        await query.answer(sc("invalid action!"), show_alert=True)
        return
    
    action = data[1] if len(data) > 1 else None
    
    await query.answer()
    
    uid = int(data[-1]) if len(data) > 2 else 0
    
    if update.effective_user.id != uid:
        await query.answer(sc("not your shop!"), show_alert=True)
        return
    
    doc = await get_user(uid)
    balance = doc.get('balance', 0) if doc else 0
    tokens = doc.get('tokens', 0) if doc else 0
    xp = doc.get('user_xp', 0) if doc else 0
    level = calc_level(xp)
    
    # Handle back to RPG menu
    if action == "menu":
        battle_data = doc.get('battle_data', {}) if doc else {}
        ai_count = battle_data.get('ai_battles', 0)
        pvp_count = battle_data.get('pvp_battles', 0)
        
        MAX_AI_BATTLES_PER_DAY = 20
        MAX_PVP_BATTLES_PER_DAY = 30
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"⚔️ {sc('start pve battle')} ({ai_count}/{MAX_AI_BATTLES_PER_DAY})", callback_data=f"rpg_pve_{uid}")],
            [InlineKeyboardButton(f"📊 {sc('view stats')}", callback_data=f"rpg_stats_{uid}")],
            [InlineKeyboardButton(f"📖 {sc('attack list')}", callback_data=f"rpg_attacks_{uid}")],
            [InlineKeyboardButton(f"🏆 {sc('leaderboard')}", callback_data=f"rpg_lead_{uid}")],
            [InlineKeyboardButton(f"🛒 {sc('battle shop')}", callback_data=f"shop_home_{uid}")]
        ])
        
        try:
            await query.message.edit_text(
                f"""<b>⚔️ {sc('rpg battle system')} ⚔️</b>

{sc('daily limits:')}
• AI Battles: {ai_count}/{MAX_AI_BATTLES_PER_DAY}
• PVP Battles: {pvp_count}/{MAX_PVP_BATTLES_PER_DAY}

{sc('select an option:')}""",
                reply_markup=kb, parse_mode="HTML"
            )
        except:
            pass
        return
    
    if action == "home":
        update.callback_query = query
        await shop_main(update, context)
        return
    
    if action in ["consumable", "buff", "special", "boost"]:
        category = action
        cat_data = SHOP_CATEGORIES.get(category)
        
        if not cat_data:
            await query.answer(sc("invalid category!"), show_alert=True)
            return
        
        text = f"""<b>{cat_data['emoji']} {sc(cat_data['name'])} {cat_data['emoji']}</b>
━━━━━━━━━━━━━━━━━━━━

<i>{cat_data['desc']}</i>

<b>{sc('your wallet:')}</b>
💰 {balance} | 🎫 {tokens}

<b>{sc('available items:')}</b>"""
        
        kb = create_category_menu(category, uid, level)
        
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return
    
    if action == "view":
        item_id = data[2]
        item = SHOP_ITEMS.get(item_id)
        
        if not item:
            await query.answer(sc("item not found!"), show_alert=True)
            return
        
        inventory = await get_inventory(uid)
        quantity = inventory.get(item_id, 0)
        
        locked_text = ""
        if item.level_required > level:
            locked_text = f"\n\n🔒 <b>{sc('requires level')} {item.level_required}</b>"
        
        duration_text = ""
        if item.duration > 0:
            if item.duration >= 60:
                hours = item.duration // 60
                duration_text = f"\n⏱️ Duration: {hours} hour(s)"
            else:
                duration_text = f"\n⏱️ Duration: {item.duration} turn(s)"
        
        text = f"""<b>{item.emoji} {item.name} {item.emoji}</b>
━━━━━━━━━━━━━━━━━━━━

<i>{item.description}</i>

<b>{sc('details:')}</b>
💰 Price: {item.price_coins} coins
🎫 Token Price: {item.price_tokens} tokens
📦 Max Stack: {item.max_stack}
⭐ Level Required: {item.level_required}{duration_text}

<b>{sc('you own:')}</b> {quantity} / {item.max_stack}

<b>{sc('your wallet:')}</b>
💰 {balance} | 🎫 {tokens}{locked_text}"""
        
        kb = create_item_detail_menu(item_id, uid, quantity)
        
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return
    
    if action in ["coin", "token"]:
        currency = "coin" if action == "coin" else "token"
        item_id = data[2]
        item = SHOP_ITEMS.get(item_id)
        
        if not item:
            await query.answer(sc("item not found!"), show_alert=True)
            return
        
        if item.level_required > level:
            await query.answer(f"🔒 {sc('requires level')} {item.level_required}!", show_alert=True)
            return
        
        inventory = await get_inventory(uid)
        current_quantity = inventory.get(item_id, 0)
        
        if current_quantity >= item.max_stack:
            await query.answer(f"❌ {sc('maximum stack reached!')} ({item.max_stack})", show_alert=True)
            return
        
        if currency == "coin":
            if balance < item.price_coins:
                await query.answer(f"❌ {sc('not enough coins!')} ({balance}/{item.price_coins})", show_alert=True)
                return
            
            try:
                await user_collection.update_one(
                    {'id': uid},
                    {'$inc': {'balance': -item.price_coins}}
                )
            except:
                await query.answer(sc("purchase failed!"), show_alert=True)
                return
        
        elif currency == "token":
            if item.price_tokens == 0:
                await query.answer(sc("cannot buy with tokens!"), show_alert=True)
                return
            
            if tokens < item.price_tokens:
                await query.answer(f"❌ {sc('not enough tokens!')} ({tokens}/{item.price_tokens})", show_alert=True)
                return
            
            try:
                await user_collection.update_one(
                    {'id': uid},
                    {'$inc': {'tokens': -item.price_tokens}}
                )
            except:
                await query.answer(sc("purchase failed!"), show_alert=True)
                return
        
        success = await add_item_to_inventory(uid, item_id, 1)
        
        if success:
            await query.answer(f"✅ {sc('purchased')} {item.name}!", show_alert=True)
            
            doc = await get_user(uid)
            balance = doc.get('balance', 0) if doc else 0
            tokens = doc.get('tokens', 0) if doc else 0
            
            inventory = await get_inventory(uid)
            quantity = inventory.get(item_id, 0)
            
            duration_text = ""
            if item.duration > 0:
                if item.duration >= 60:
                    hours = item.duration // 60
                    duration_text = f"\n⏱️ Duration: {hours} hour(s)"
                else:
                    duration_text = f"\n⏱️ Duration: {item.duration} turn(s)"
            
            text = f"""<b>{item.emoji} {item.name} {item.emoji}</b>
━━━━━━━━━━━━━━━━━━━━

<i>{item.description}</i>

<b>{sc('details:')}</b>
💰 Price: {item.price_coins} coins
🎫 Token Price: {item.price_tokens} tokens
📦 Max Stack: {item.max_stack}
⭐ Level Required: {item.level_required}{duration_text}

<b>{sc('you own:')}</b> {quantity} / {item.max_stack}

<b>{sc('your wallet:')}</b>
💰 {balance} | 🎫 {tokens}"""
            
            kb = create_item_detail_menu(item_id, uid, quantity)
            
            try:
                await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            except:
                pass
        else:
            await query.answer(sc("purchase failed!"), show_alert=True)
        return
    
    if action == "use":
        item_id = data[2]
        item = SHOP_ITEMS.get(item_id)
        
        if not item:
            await query.answer(sc("item not found!"), show_alert=True)
            return
        
        inventory = await get_inventory(uid)
        if inventory.get(item_id, 0) <= 0:
            await query.answer(sc("you don't have this item!"), show_alert=True)
            return
        
        if item.effect_type in ["exp_boost", "coin_boost"]:
            success = await add_boost(uid, item.effect_type, item.effect_value, item.duration)
            if success:
                await remove_item_from_inventory(uid, item_id, 1)
                hours = item.duration // 60
                await query.answer(f"✅ {item.name} activated! (+{item.effect_value}% for {hours}h)", show_alert=True)
            else:
                await query.answer(sc("failed to use item!"), show_alert=True)
        
        elif item.effect_type in ["ai_battles", "pvp_battles"]:
            battle_data = doc.get('battle_data', {})
            
            if item.effect_type == "ai_battles":
                battle_data['ai_battles'] = max(0, battle_data.get('ai_battles', 0) - item.effect_value)
            else:
                battle_data['pvp_battles'] = max(0, battle_data.get('pvp_battles', 0) - item.effect_value)
            
            try:
                await user_collection.update_one(
                    {'id': uid},
                    {'$set': {'battle_data': battle_data}}
                )
                await remove_item_from_inventory(uid, item_id, 1)
                await query.answer(f"✅ +{item.effect_value} battles added!", show_alert=True)
            except:
                await query.answer(sc("failed to use item!"), show_alert=True)
        
        else:
            await query.answer(sc("this item can only be used in battle!"), show_alert=True)
        
        return
    
    if action == "inv":
        inventory = await get_inventory(uid)
        
        if not inventory:
            text = f"""<b>🎒 {sc('your inventory')} 🎒</b>
━━━━━━━━━━━━━━━━━━━━

<i>{sc('your inventory is empty!')}</i>

{sc('visit the shop to purchase items!')}"""
        else:
            text = f"""<b>🎒 {sc('your inventory')} 🎒</b>
━━━━━━━━━━━━━━━━━━━━

"""
            for item_id, quantity in inventory.items():
                item = SHOP_ITEMS.get(item_id)
                if item:
                    text += f"{item.emoji} <b>{item.name}</b> x{quantity}\n"
            
            text += f"\n<i>{sc('click on items in shop to use them!')}</i>"
        
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"◀️ {sc('back')}", callback_data=f"shop_home_{uid}")
        ]])
        
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return
    
    if action == "boosts":
        boosts = await get_active_boosts(uid)
        
        if not boosts:
            text = f"""<b>📊 {sc('active boosts')} 📊</b>
━━━━━━━━━━━━━━━━━━━━

<i>{sc('no active boosts!')}</i>

{sc('purchase boosters from the shop to enhance your gameplay!')}"""
        else:
            text = f"""<b>📊 {sc('active boosts')} 📊</b>
━━━━━━━━━━━━━━━━━━━━

"""
            for boost in boosts:
                boost_type = boost['type'].replace('_', ' ').title()
                value = boost['value']
                expires_at = datetime.fromisoformat(boost['expires_at'])
                time_left = expires_at - datetime.utcnow()
                hours = int(time_left.total_seconds() // 3600)
                minutes = int((time_left.total_seconds() % 3600) // 60)
                
                emoji = "⭐" if 'exp' in boost['type'] else "💰"
                text += f"{emoji} <b>{boost_type}</b>\n"
                text += f"   +{value}% | {hours}h {minutes}m remaining\n\n"
        
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"◀️ {sc('back')}", callback_data=f"shop_home_{uid}")
        ]])
        
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return

application.add_handler(CommandHandler("hop", shop_main))
application.add_handler(CommandHandler("battleshop", shop_main))
application.add_handler(CommandHandler("bshop", shop_main))
application.add_handler(CallbackQueryHandler(shop_callback, pattern="^shop_"))