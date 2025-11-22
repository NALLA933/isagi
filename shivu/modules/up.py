from datetime import datetime, timedelta
from typing import Dict, List
from dataclasses import dataclass

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from shivu import application, user_collection

SMALLCAPS_MAP = {c: v for c, v in zip(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ',
    'ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ'
)}

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
    # HP Potions
    "hp_potion_small": ShopItem("hp_potion_small", "Small HP Potion", "Restores 50 HP", 100, 0, "🧪", "consumable", "heal_hp", 50, 0, 99, 1),
    "hp_potion_medium": ShopItem("hp_potion_medium", "Medium HP Potion", "Restores 150 HP", 250, 0, "💊", "consumable", "heal_hp", 150, 0, 99, 10),
    "hp_potion_large": ShopItem("hp_potion_large", "Large HP Potion", "Restores 300 HP", 500, 0, "🍶", "consumable", "heal_hp", 300, 0, 99, 20),
    
    # Mana Potions
    "mana_potion_small": ShopItem("mana_potion_small", "Small Mana Potion", "Restores 40 MP", 120, 0, "🔵", "consumable", "heal_mana", 40, 0, 99, 1),
    "mana_potion_medium": ShopItem("mana_potion_medium", "Medium Mana Potion", "Restores 100 MP", 280, 0, "💙", "consumable", "heal_mana", 100, 0, 99, 10),
    "mana_potion_large": ShopItem("mana_potion_large", "Large Mana Potion", "Restores 200 MP", 550, 0, "🌊", "consumable", "heal_mana", 200, 0, 99, 20),
    
    # Special Items
    "elixir": ShopItem("elixir", "Full Elixir", "Restores all HP and Mana", 1000, 5, "✨", "consumable", "full_restore", 0, 0, 10, 30),
    
    # Elemental Crystals
    **{f"{elem}_crystal": ShopItem(f"{elem}_crystal", f"{elem.title()} Crystal", f"Boost {elem.title()} attacks by 25% for 3 turns", 400, 0, emoji, "buff", f"{elem}_boost", 25, 3, 5, 15)
       for elem, emoji in [("fire", "🔥"), ("ice", "❄️"), ("lightning", "⚡"), ("water", "💧"), ("earth", "🌍"), ("wind", "💨"), ("dark", "🌑"), ("light", "✨")]},
    
    # Stat Boosters
    "strength_potion": ShopItem("strength_potion", "Strength Potion", "+30% Attack for 5 turns", 600, 0, "💪", "buff", "attack_boost", 30, 5, 5, 20),
    "defense_potion": ShopItem("defense_potion", "Defense Potion", "+40% Defense for 5 turns", 600, 0, "🛡️", "buff", "defense_boost", 40, 5, 5, 20),
    "speed_potion": ShopItem("speed_potion", "Speed Potion", "+35% Speed for 5 turns", 600, 0, "⚡", "buff", "speed_boost", 35, 5, 5, 20),
    
    # Special Items
    "phoenix_feather": ShopItem("phoenix_feather", "Phoenix Feather", "Auto-revive with 50% HP once per battle", 2000, 10, "🪶", "special", "revive", 50, 0, 3, 40),
    "lucky_charm": ShopItem("lucky_charm", "Lucky Charm", "+15% Critical Hit chance for 5 turns", 800, 0, "🍀", "buff", "crit_boost", 15, 5, 5, 25),
    "smoke_bomb": ShopItem("smoke_bomb", "Smoke Bomb", "+30% Dodge chance for 3 turns", 500, 0, "💨", "buff", "dodge_boost", 30, 3, 5, 15),
    
    # Battle Tickets
    "battle_ticket": ShopItem("battle_ticket", "Battle Ticket", "+5 AI battles for today", 1500, 0, "🎫", "special", "ai_battles", 5, 0, 3, 1),
    "pvp_ticket": ShopItem("pvp_ticket", "PVP Ticket", "+5 PVP battles for today", 2000, 0, "🎟️", "special", "pvp_battles", 5, 0, 3, 1),
    
    # Long-term Boosters
    "exp_boost": ShopItem("exp_boost", "EXP Booster", "+50% EXP gain for 24 hours", 3000, 15, "⭐", "boost", "exp_boost", 50, 1440, 1, 30),
    "coin_boost": ShopItem("coin_boost", "Coin Booster", "+50% Coin gain for 24 hours", 2500, 12, "💰", "boost", "coin_boost", 50, 1440, 1, 25),
    
    # Rare Items
    "master_scroll": ShopItem("master_scroll", "Master Scroll", "Instantly learn one locked attack", 5000, 25, "📜", "special", "unlock_attack", 1, 0, 10, 50),
}

SHOP_CATEGORIES = {
    "consumable": {"name": "Consumables", "emoji": "🧪", "desc": "Potions and instant-use items"},
    "buff": {"name": "Buffs", "emoji": "✨", "desc": "Temporary stat boosters"},
    "special": {"name": "Special", "emoji": "🎁", "desc": "Unique powerful items"},
    "boost": {"name": "Boosters", "emoji": "⚡", "desc": "Long-term enhancements"},
}

# Database Functions
async def get_user(uid: int):
    try:
        return await user_collection.find_one({'id': uid})
    except:
        return None

async def get_inventory(uid: int) -> Dict[str, int]:
    doc = await get_user(uid)
    return doc.get('battle_inventory', {}) if doc else {}

async def add_item_to_inventory(uid: int, item_id: str, quantity: int = 1):
    inventory = await get_inventory(uid)
    inventory[item_id] = inventory.get(item_id, 0) + quantity
    try:
        await user_collection.update_one({'id': uid}, {'$set': {'battle_inventory': inventory}}, upsert=True)
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
        await user_collection.update_one({'id': uid}, {'$set': {'battle_inventory': inventory}}, upsert=True)
        return True
    except:
        return False

async def get_active_boosts(uid: int) -> List[Dict]:
    doc = await get_user(uid)
    if not doc:
        return []
    
    boosts = doc.get('active_boosts', [])
    active_boosts = [b for b in boosts if datetime.utcnow() < datetime.fromisoformat(b['expires_at'])]
    
    if len(active_boosts) != len(boosts):
        try:
            await user_collection.update_one({'id': uid}, {'$set': {'active_boosts': active_boosts}})
        except:
            pass
    
    return active_boosts

async def add_boost(uid: int, boost_type: str, value: int, duration_minutes: int):
    expires_at = (datetime.utcnow() + timedelta(minutes=duration_minutes)).isoformat()
    boost = {'type': boost_type, 'value': value, 'expires_at': expires_at}
    
    try:
        await user_collection.update_one({'id': uid}, {'$push': {'active_boosts': boost}}, upsert=True)
        return True
    except:
        return False

def calc_level(xp: int) -> int:
    import math
    return min(max(1, math.floor(math.sqrt(max(xp, 0) / 100)) + 1), 100)

# Keyboard Functions
def create_shop_main_menu(uid: int) -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton(f"{cat['emoji']} {sc(cat['name'])}", callback_data=f"bshop_{cid}_{uid}")]
                for cid, cat in SHOP_CATEGORIES.items()]
    keyboard.extend([
        [InlineKeyboardButton(f"🎒 {sc('my inventory')}", callback_data=f"bshop_inv_{uid}")],
        [InlineKeyboardButton(f"📊 {sc('active boosts')}", callback_data=f"bshop_boosts_{uid}")],
        [InlineKeyboardButton(f"◀️ {sc('back to rpg menu')}", callback_data=f"rpg_menu_{uid}")]
    ])
    return InlineKeyboardMarkup(keyboard)

def create_category_menu(category: str, uid: int, player_level: int) -> InlineKeyboardMarkup:
    items = sorted([i for i in SHOP_ITEMS.values() if i.category == category], key=lambda x: x.price_coins)
    
    keyboard = []
    for item in items:
        locked = "🔒" if item.level_required > player_level else ""
        price_text = f"{item.price_coins}💰" if item.price_tokens == 0 else f"{item.price_tokens}🎫"
        keyboard.append([InlineKeyboardButton(
            f"{item.emoji} {item.name} - {price_text} {locked}",
            callback_data=f"bshop_view_{item.item_id}_{uid}"
        )])
    
    keyboard.append([InlineKeyboardButton(f"◀️ {sc('back')}", callback_data=f"bshop_home_{uid}")])
    return InlineKeyboardMarkup(keyboard)

def create_item_detail_menu(item_id: str, uid: int, quantity: int = 0) -> InlineKeyboardMarkup:
    item = SHOP_ITEMS.get(item_id)
    if not item:
        return InlineKeyboardMarkup([[]])
    
    keyboard = [[InlineKeyboardButton(f"💰 {sc('buy with coins')}", callback_data=f"bshop_coin_{item_id}_{uid}")]]
    
    if item.price_tokens > 0:
        keyboard.append([InlineKeyboardButton(f"🎫 {sc('buy with tokens')}", callback_data=f"bshop_token_{item_id}_{uid}")])
    
    if quantity > 0 and item.category in ["consumable", "buff"]:
        keyboard.append([InlineKeyboardButton(f"🎒 {sc('use item')} (x{quantity})", callback_data=f"bshop_use_{item_id}_{uid}")])
    
    keyboard.append([InlineKeyboardButton(f"◀️ {sc('back')}", callback_data=f"bshop_{item.category}_{uid}")])
    return InlineKeyboardMarkup(keyboard)

# Command Handlers
async def bshop_main(update: Update, context: CallbackContext):
    user = update.effective_user
    doc = await get_user(user.id)
    
    balance = doc.get('balance', 0) if doc else 0
    tokens = doc.get('tokens', 0) if doc else 0
    xp = doc.get('user_xp', 0) if doc else 0
    level = calc_level(xp)
    
    text = f"""<b>🛒 {sc('battle shop')} 🛒</b>
━━━━━━━━━━━━━━━━━━━━

<b>{sc('your wallet')}</b>
💰 Coins: <code>{balance:,}</code>
🎫 Tokens: <code>{tokens:,}</code>
⭐ Level: <code>{level}</code>

<b>{sc('shop categories:')}</b>"""
    
    for cat_id, cat_data in SHOP_CATEGORIES.items():
        items_count = len([i for i in SHOP_ITEMS.values() if i.category == cat_id])
        text += f"\n{cat_data['emoji']} <b>{cat_data['name']}</b> ({items_count} items)\n<i>{cat_data['desc']}</i>"
    
    text += f"\n\n<i>{sc('select a category to browse items!')}</i>"
    
    kb = create_shop_main_menu(user.id)
    
    if update.callback_query:
        try:
            await update.callback_query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except:
            pass
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")

async def bshop_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data.split("_")
    
    if len(data) < 3:
        await query.answer(sc("invalid action!"), show_alert=True)
        return
    
    action = data[1]
    uid = int(data[-1])
    
    await query.answer()
    
    if update.effective_user.id != uid:
        await query.answer(sc("not your shop!"), show_alert=True)
        return
    
    doc = await get_user(uid)
    balance = doc.get('balance', 0) if doc else 0
    tokens = doc.get('tokens', 0) if doc else 0
    xp = doc.get('user_xp', 0) if doc else 0
    level = calc_level(xp)
    
    # Handle home
    if action == "home":
        await bshop_main(update, context)
        return
    
    # Handle category selection
    if action in SHOP_CATEGORIES:
        cat_data = SHOP_CATEGORIES[action]
        text = f"""<b>{cat_data['emoji']} {sc(cat_data['name'])} {cat_data['emoji']}</b>
━━━━━━━━━━━━━━━━━━━━

<i>{cat_data['desc']}</i>

<b>{sc('your wallet:')}</b>
💰 {balance:,} | 🎫 {tokens:,}

<b>{sc('available items:')}</b>"""
        
        kb = create_category_menu(action, uid, level)
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return
    
    # Handle item view
    if action == "view":
        item_id = data[2]
        item = SHOP_ITEMS.get(item_id)
        
        if not item:
            await query.answer(sc("item not found!"), show_alert=True)
            return
        
        inventory = await get_inventory(uid)
        quantity = inventory.get(item_id, 0)
        
        locked_text = f"\n\n🔒 <b>{sc('requires level')} {item.level_required}</b>" if item.level_required > level else ""
        duration_text = f"\n⏱️ Duration: {item.duration // 60} hour(s)" if item.duration >= 60 else f"\n⏱️ Duration: {item.duration} turn(s)" if item.duration > 0 else ""
        
        text = f"""<b>{item.emoji} {item.name} {item.emoji}</b>
━━━━━━━━━━━━━━━━━━━━

<i>{item.description}</i>

<b>{sc('details:')}</b>
💰 Price: {item.price_coins:,} coins
🎫 Token Price: {item.price_tokens:,} tokens
📦 Max Stack: {item.max_stack}
⭐ Level Required: {item.level_required}{duration_text}

<b>{sc('you own:')}</b> {quantity} / {item.max_stack}

<b>{sc('your wallet:')}</b>
💰 {balance:,} | 🎫 {tokens:,}{locked_text}"""
        
        kb = create_item_detail_menu(item_id, uid, quantity)
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return
    
    # Handle purchase
    if action in ["coin", "token"]:
        item_id = data[2]
        item = SHOP_ITEMS.get(item_id)
        
        if not item:
            await query.answer(sc("item not found!"), show_alert=True)
            return
        
        if item.level_required > level:
            await query.answer(f"🔒 {sc('requires level')} {item.level_required}!", show_alert=True)
            return
        
        inventory = await get_inventory(uid)
        if inventory.get(item_id, 0) >= item.max_stack:
            await query.answer(f"❌ {sc('maximum stack reached!')} ({item.max_stack})", show_alert=True)
            return
        
        if action == "coin":
            if balance < item.price_coins:
                await query.answer(f"❌ {sc('not enough coins!')} ({balance:,}/{item.price_coins:,})", show_alert=True)
                return
            
            try:
                await user_collection.update_one({'id': uid}, {'$inc': {'balance': -item.price_coins}})
            except:
                await query.answer(sc("purchase failed!"), show_alert=True)
                return
        else:
            if item.price_tokens == 0:
                await query.answer(sc("cannot buy with tokens!"), show_alert=True)
                return
            
            if tokens < item.price_tokens:
                await query.answer(f"❌ {sc('not enough tokens!')} ({tokens:,}/{item.price_tokens:,})", show_alert=True)
                return
            
            try:
                await user_collection.update_one({'id': uid}, {'$inc': {'tokens': -item.price_tokens}})
            except:
                await query.answer(sc("purchase failed!"), show_alert=True)
                return
        
        if await add_item_to_inventory(uid, item_id, 1):
            await query.answer(f"✅ {sc('purchased')} {item.name}!", show_alert=True)
            
            # Refresh display
            doc = await get_user(uid)
            balance = doc.get('balance', 0) if doc else 0
            tokens = doc.get('tokens', 0) if doc else 0
            inventory = await get_inventory(uid)
            quantity = inventory.get(item_id, 0)
            
            duration_text = f"\n⏱️ Duration: {item.duration // 60} hour(s)" if item.duration >= 60 else f"\n⏱️ Duration: {item.duration} turn(s)" if item.duration > 0 else ""
            
            text = f"""<b>{item.emoji} {item.name} {item.emoji}</b>
━━━━━━━━━━━━━━━━━━━━

<i>{item.description}</i>

<b>{sc('details:')}</b>
💰 Price: {item.price_coins:,} coins
🎫 Token Price: {item.price_tokens:,} tokens
📦 Max Stack: {item.max_stack}
⭐ Level Required: {item.level_required}{duration_text}

<b>{sc('you own:')}</b> {quantity} / {item.max_stack}

<b>{sc('your wallet:')}</b>
💰 {balance:,} | 🎫 {tokens:,}"""
            
            kb = create_item_detail_menu(item_id, uid, quantity)
            try:
                await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            except:
                pass
        else:
            await query.answer(sc("purchase failed!"), show_alert=True)
        return
    
    # Handle item use
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
        
        # Handle EXP/Coin boosters
        if item.effect_type in ["exp_boost", "coin_boost"]:
            if await add_boost(uid, item.effect_type, item.effect_value, item.duration):
                await remove_item_from_inventory(uid, item_id, 1)
                hours = item.duration // 60
                await query.answer(f"✅ {item.name} activated! (+{item.effect_value}% for {hours}h)", show_alert=True)
            else:
                await query.answer(sc("failed to use item!"), show_alert=True)
        
        # Handle battle tickets
        elif item.effect_type in ["ai_battles", "pvp_battles"]:
            battle_data = doc.get('battle_data', {})
            
            if item.effect_type == "ai_battles":
                battle_data['ai_battles'] = max(0, battle_data.get('ai_battles', 0) - item.effect_value)
            else:
                battle_data['pvp_battles'] = max(0, battle_data.get('pvp_battles', 0) - item.effect_value)
            
            try:
                await user_collection.update_one({'id': uid}, {'$set': {'battle_data': battle_data}})
                await remove_item_from_inventory(uid, item_id, 1)
                await query.answer(f"✅ +{item.effect_value} battles added!", show_alert=True)
            except:
                await query.answer(sc("failed to use item!"), show_alert=True)
        else:
            await query.answer(sc("this item can only be used in battle!"), show_alert=True)
        return
    
    # Handle inventory view
    if action == "inv":
        inventory = await get_inventory(uid)
        
        if not inventory:
            text = f"""<b>🎒 {sc('your inventory')} 🎒</b>
━━━━━━━━━━━━━━━━━━━━

<i>{sc('your inventory is empty!')}</i>

{sc('visit the shop to purchase items!')}"""
        else:
            text = f"""<b>🎒 {sc('your inventory')} 🎒</b>
━━━━━━━━━━━━━━━━━━━━\n\n"""
            for item_id, quantity in inventory.items():
                item = SHOP_ITEMS.get(item_id)
                if item:
                    text += f"{item.emoji} <b>{item.name}</b> x{quantity}\n"
            text += f"\n<i>{sc('click on items in shop to use them!')}</i>"
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"◀️ {sc('back')}", callback_data=f"bshop_home_{uid}")]])
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return
    
    # Handle active boosts view
    if action == "boosts":
        boosts = await get_active_boosts(uid)
        
        if not boosts:
            text = f"""<b>📊 {sc('active boosts')} 📊</b>
━━━━━━━━━━━━━━━━━━━━

<i>{sc('no active boosts!')}</i>

{sc('purchase boosters from the shop to enhance your gameplay!')}"""
        else:
            text = f"""<b>📊 {sc('active boosts')} 📊</b>
━━━━━━━━━━━━━━━━━━━━\n\n"""
            for boost in boosts:
                boost_type = boost['type'].replace('_', ' ').title()
                value = boost['value']
                expires_at = datetime.fromisoformat(boost['expires_at'])
                time_left = expires_at - datetime.utcnow()
                hours = int(time_left.total_seconds() // 3600)
                minutes = int((time_left.total_seconds() % 3600) // 60)
                
                emoji = "⭐" if 'exp' in boost['type'] else "💰"
                text += f"{emoji} <b>{boost_type}</b>\n   +{value}% | {hours}h {minutes}m remaining\n\n"
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"◀️ {sc('back')}", callback_data=f"bshop_home_{uid}")]])
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return

# Register handlers
application.add_handler(CommandHandler("bshop", bshop_main, block=False))
application.add_handler(CommandHandler("battleshop", bshop_main, block=False))
application.add_handler(CallbackQueryHandler(bshop_callback, pattern="^bshop_", block=False))