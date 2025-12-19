import asyncio
import random
import time
import logging
from typing import List, Dict, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import TelegramError
from shivu import application, user_collection, collection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RARITY_MAP = {
    "common": "🟢 Common", "rare": "🟣 Rare", "legendary": "🟡 Legendary",
    "special": "💮 Special Edition", "neon": "💫 Neon", "manga": "✨ Manga",
    "cosplay": "🎭 Cosplay", "celestial": "🎐 Celestial", "premium": "🔮 Premium Edition",
    "erotic": "💋 Erotic", "summer": "🌤 Summer", "winter": "☃️ Winter",
    "monsoon": "☔️ Monsoon", "valentine": "💝 Valentine", "halloween": "🎃 Halloween",
    "christmas": "🎄 Christmas", "mythic": "🏵 Mythic", "amv": "🎥 AMV", "tiny": "👼 Tiny"
}

TIERS = {
    "🟢 Common": 1, "🟣 Rare": 2, "🟡 Legendary": 3, "💮 Special Edition": 4,
    "💫 Neon": 5, "✨ Manga": 5, "🎭 Cosplay": 5, "🎐 Celestial": 6,
    "🔮 Premium Edition": 6, "💋 Erotic": 6, "🌤 Summer": 4, "☃️ Winter": 4,
    "☔️ Monsoon": 4, "💝 Valentine": 5, "🎃 Halloween": 5, "🎄 Christmas": 5,
    "🏵 Mythic": 7, "🎥 AMV": 5, "👼 Tiny": 4
}

SEASONAL_RARITIES = {"🌤 Summer", "☃️ Winter", "☔️ Monsoon"}
HOLIDAY_RARITIES = {"💝 Valentine", "🎃 Halloween", "🎄 Christmas"}
SPECIAL_RARITIES = {"💮 Special Edition", "💫 Neon", "✨ Manga", "🎭 Cosplay", "🎐 Celestial", "🔮 Premium Edition", "💋 Erotic"}
CREATIVE_RARITIES = {"🎥 AMV", "👼 Tiny"}
BASE_RARITIES = {"🟢 Common", "🟣 Rare", "🟡 Legendary"}
ULTIMATE_RARITIES = {"🏵 Mythic"}

SPECIAL_FUSIONS = {
    ("🌤 Summer", "☃️ Winter"): [("🏵 Mythic", 0.40), ("🎐 Celestial", 0.30), ("💫 Neon", 0.20), ("🟡 Legendary", 0.10)],
    ("🌤 Summer", "☔️ Monsoon"): [("🎐 Celestial", 0.35), ("💫 Neon", 0.30), ("🔮 Premium Edition", 0.25), ("🟡 Legendary", 0.10)],
    ("☃️ Winter", "☔️ Monsoon"): [("🎐 Celestial", 0.40), ("💫 Neon", 0.30), ("💮 Special Edition", 0.20), ("🟣 Rare", 0.10)],
    ("🌤 Summer", "🌤 Summer"): [("🔮 Premium Edition", 0.50), ("💫 Neon", 0.30), ("🎐 Celestial", 0.15), ("🏵 Mythic", 0.05)],
    ("☃️ Winter", "☃️ Winter"): [("🔮 Premium Edition", 0.50), ("💫 Neon", 0.30), ("🎐 Celestial", 0.15), ("🏵 Mythic", 0.05)],
    ("☔️ Monsoon", "☔️ Monsoon"): [("🎐 Celestial", 0.50), ("💫 Neon", 0.30), ("🔮 Premium Edition", 0.15), ("🏵 Mythic", 0.05)],
    ("💝 Valentine", "🎃 Halloween"): [("🏵 Mythic", 0.45), ("🎐 Celestial", 0.30), ("💫 Neon", 0.20), ("🔮 Premium Edition", 0.05)],
    ("💝 Valentine", "🎄 Christmas"): [("🎐 Celestial", 0.40), ("💫 Neon", 0.35), ("🔮 Premium Edition", 0.20), ("🏵 Mythic", 0.05)],
    ("🎃 Halloween", "🎄 Christmas"): [("🏵 Mythic", 0.40), ("🎐 Celestial", 0.30), ("💫 Neon", 0.25), ("🔮 Premium Edition", 0.05)],
    ("💝 Valentine", "🌤 Summer"): [("💫 Neon", 0.45), ("🔮 Premium Edition", 0.30), ("🎐 Celestial", 0.20), ("🏵 Mythic", 0.05)],
    ("💝 Valentine", "☃️ Winter"): [("🎐 Celestial", 0.40), ("💫 Neon", 0.35), ("🔮 Premium Edition", 0.20), ("🏵 Mythic", 0.05)],
    ("🎃 Halloween", "☃️ Winter"): [("🏵 Mythic", 0.45), ("🎐 Celestial", 0.30), ("💫 Neon", 0.20), ("🔮 Premium Edition", 0.05)],
    ("🎃 Halloween", "☔️ Monsoon"): [("🎐 Celestial", 0.40), ("💫 Neon", 0.35), ("🔮 Premium Edition", 0.20), ("🏵 Mythic", 0.05)],
    ("🎄 Christmas", "☃️ Winter"): [("🏵 Mythic", 0.50), ("🎐 Celestial", 0.30), ("💫 Neon", 0.15), ("🔮 Premium Edition", 0.05)],
    ("🎥 AMV", "✨ Manga"): [("🎐 Celestial", 0.50), ("💫 Neon", 0.30), ("🏵 Mythic", 0.15), ("🔮 Premium Edition", 0.05)],
    ("🎥 AMV", "🎭 Cosplay"): [("💫 Neon", 0.45), ("🎐 Celestial", 0.35), ("🔮 Premium Edition", 0.15), ("🏵 Mythic", 0.05)],
    ("✨ Manga", "🎭 Cosplay"): [("💫 Neon", 0.45), ("🎐 Celestial", 0.30), ("🔮 Premium Edition", 0.20), ("🏵 Mythic", 0.05)],
    ("👼 Tiny", "🏵 Mythic"): [("🏵 Mythic", 0.60), ("🎐 Celestial", 0.25), ("💫 Neon", 0.10), ("🔮 Premium Edition", 0.05)],
    ("💋 Erotic", "💝 Valentine"): [("🏵 Mythic", 0.55), ("🎐 Celestial", 0.25), ("💫 Neon", 0.15), ("🔮 Premium Edition", 0.05)],
    ("💋 Erotic", "🌤 Summer"): [("🎐 Celestial", 0.50), ("💫 Neon", 0.30), ("🔮 Premium Edition", 0.15), ("🏵 Mythic", 0.05)],
    ("💋 Erotic", "☃️ Winter"): [("🎐 Celestial", 0.45), ("💫 Neon", 0.30), ("🔮 Premium Edition", 0.20), ("🏵 Mythic", 0.05)],
    ("💫 Neon", "💫 Neon"): [("🎐 Celestial", 0.55), ("🏵 Mythic", 0.25), ("🔮 Premium Edition", 0.15), ("💫 Neon", 0.05)],
    ("💫 Neon", "🎭 Cosplay"): [("🎐 Celestial", 0.45), ("🔮 Premium Edition", 0.30), ("🏵 Mythic", 0.20), ("💫 Neon", 0.05)],
    ("🔮 Premium Edition", "🔮 Premium Edition"): [("🏵 Mythic", 0.60), ("🎐 Celestial", 0.25), ("💫 Neon", 0.10), ("🔮 Premium Edition", 0.05)],
    ("🔮 Premium Edition", "💫 Neon"): [("🏵 Mythic", 0.50), ("🎐 Celestial", 0.30), ("💫 Neon", 0.15), ("🔮 Premium Edition", 0.05)],
    ("🎐 Celestial", "🎐 Celestial"): [("🏵 Mythic", 0.70), ("🎐 Celestial", 0.20), ("💫 Neon", 0.08), ("🔮 Premium Edition", 0.02)],
    ("🎐 Celestial", "💫 Neon"): [("🏵 Mythic", 0.55), ("🎐 Celestial", 0.30), ("💫 Neon", 0.12), ("🔮 Premium Edition", 0.03)],
    ("🎐 Celestial", "🔮 Premium Edition"): [("🏵 Mythic", 0.60), ("🎐 Celestial", 0.25), ("💫 Neon", 0.12), ("🔮 Premium Edition", 0.03)],
    ("🏵 Mythic", "🏵 Mythic"): [("🏵 Mythic", 0.95), ("🎐 Celestial", 0.04), ("💫 Neon", 0.01)],
    ("🏵 Mythic", "🎐 Celestial"): [("🏵 Mythic", 0.80), ("🎐 Celestial", 0.15), ("💫 Neon", 0.05)],
    ("🟡 Legendary", "🟡 Legendary"): [("💮 Special Edition", 0.70), ("🟡 Legendary", 0.20), ("💫 Neon", 0.08), ("🎐 Celestial", 0.02)],
    ("💮 Special Edition", "💮 Special Edition"): [("💫 Neon", 0.70), ("💮 Special Edition", 0.20), ("🎐 Celestial", 0.08), ("🏵 Mythic", 0.02)],
    ("🏵 Mythic", "💝 Valentine"): [("🏵 Mythic", 0.85), ("🎐 Celestial", 0.10), ("💫 Neon", 0.05)],
    ("🏵 Mythic", "🌤 Summer"): [("🏵 Mythic", 0.80), ("🎐 Celestial", 0.12), ("💫 Neon", 0.08)],
    ("🏵 Mythic", "☃️ Winter"): [("🏵 Mythic", 0.80), ("🎐 Celestial", 0.12), ("💫 Neon", 0.08)],
    ("👼 Tiny", "👼 Tiny"): [("💮 Special Edition", 0.50), ("💫 Neon", 0.30), ("🎐 Celestial", 0.15), ("🏵 Mythic", 0.05)],
    ("👼 Tiny", "💫 Neon"): [("🎐 Celestial", 0.45), ("💫 Neon", 0.35), ("🔮 Premium Edition", 0.15), ("🏵 Mythic", 0.05)],
    ("🟢 Common", "🟢 Common"): [("🟢 Common", 0.60), ("🟣 Rare", 0.30), ("🟡 Legendary", 0.08), ("💮 Special Edition", 0.02)],
    ("🟣 Rare", "🟣 Rare"): [("🟣 Rare", 0.50), ("🟡 Legendary", 0.35), ("💮 Special Edition", 0.12), ("💫 Neon", 0.03)],
    ("🟢 Common", "🟣 Rare"): [("🟣 Rare", 0.55), ("🟡 Legendary", 0.30), ("🟢 Common", 0.12), ("💮 Special Edition", 0.03)],
    ("🟣 Rare", "🟡 Legendary"): [("🟡 Legendary", 0.45), ("💮 Special Edition", 0.35), ("🟣 Rare", 0.15), ("💫 Neon", 0.05)],
    ("🟢 Common", "🟡 Legendary"): [("🟣 Rare", 0.50), ("🟡 Legendary", 0.30), ("🟢 Common", 0.15), ("💮 Special Edition", 0.05)]
}

COSTS = {1: 500, 2: 1000, 3: 2000, 4: 3500, 5: 5000, 6: 7500, 7: 10000}
BASE_RATES = {0: 0.70, 1: 0.55, 2: 0.40, 3: 0.30}
STONE_BOOST = 0.15
COOLDOWN = 1800
SESSION_EXPIRE = 300
CHARS_PER_PAGE = 8

sessions = {}

def norm_rarity(r: str) -> str:
    if r in TIERS:
        return r
    return RARITY_MAP.get(r.lower().replace(" ", ""), "🟢 Common")

def get_tier(r: str) -> int:
    return TIERS.get(norm_rarity(r), 1)

def calc_cost(r1: str, r2: str) -> int:
    avg = (get_tier(r1) + get_tier(r2)) // 2
    return COSTS.get(avg, 1000)

def calc_rate(r1: str, r2: str, stones: int, pity: int) -> float:
    diff = abs(get_tier(r1) - get_tier(r2))
    base = BASE_RATES.get(min(diff, 3), 0.30)
    stone_bonus = min(stones, 3) * STONE_BOOST
    pity_bonus = min(pity, 5) * 0.05
    return min(base + stone_bonus + pity_bonus, 0.95)

def get_rarity_categories(rarity: str) -> set:
    categories = set()
    if rarity in SEASONAL_RARITIES:
        categories.add('seasonal')
    if rarity in HOLIDAY_RARITIES:
        categories.add('holiday')
    if rarity in SPECIAL_RARITIES:
        categories.add('special')
    if rarity in CREATIVE_RARITIES:
        categories.add('creative')
    if rarity in BASE_RARITIES:
        categories.add('base')
    if rarity in ULTIMATE_RARITIES:
        categories.add('ultimate')
    return categories

def get_result_rarity(r1: str, r2: str) -> str:
    r1_norm = norm_rarity(r1)
    r2_norm = norm_rarity(r2)
    combo_key = tuple(sorted([r1_norm, r2_norm]))
    
    if combo_key in SPECIAL_FUSIONS:
        outcomes = SPECIAL_FUSIONS[combo_key]
        roll = random.random()
        cumulative = 0.0
        for rarity, chance in outcomes:
            cumulative += chance
            if roll <= cumulative:
                return rarity
    
    r1_categories = get_rarity_categories(r1_norm)
    r2_categories = get_rarity_categories(r2_norm)
    
    if 'seasonal' in r1_categories and 'seasonal' in r2_categories and r1_norm != r2_norm:
        roll = random.random()
        if roll < 0.35:
            return "🏵 Mythic"
        elif roll < 0.65:
            return "🎐 Celestial"
        elif roll < 0.85:
            return "💫 Neon"
        else:
            return "🔮 Premium Edition"
    
    if 'holiday' in r1_categories and 'seasonal' in r2_categories:
        roll = random.random()
        if roll < 0.40:
            return "🎐 Celestial"
        elif roll < 0.70:
            return "💫 Neon"
        elif roll < 0.90:
            return "🔮 Premium Edition"
        else:
            return "🏵 Mythic"
    
    if 'holiday' in r1_categories and 'holiday' in r2_categories and r1_norm != r2_norm:
        roll = random.random()
        if roll < 0.45:
            return "🏵 Mythic"
        elif roll < 0.75:
            return "🎐 Celestial"
        elif roll < 0.95:
            return "💫 Neon"
        else:
            return "🔮 Premium Edition"
    
    if 'creative' in r1_categories and 'special' in r2_categories:
        roll = random.random()
        if roll < 0.45:
            return "🎐 Celestial"
        elif roll < 0.75:
            return "💫 Neon"
        elif roll < 0.90:
            return "🔮 Premium Edition"
        else:
            return "🏵 Mythic"
    
    if 'ultimate' in r1_categories or 'ultimate' in r2_categories:
        roll = random.random()
        if roll < 0.75:
            return "🏵 Mythic"
        elif roll < 0.90:
            return "🎐 Celestial"
        else:
            return "💫 Neon"
    
    if 'special' in r1_categories and 'special' in r2_categories:
        tier1 = get_tier(r1_norm)
        tier2 = get_tier(r2_norm)
        avg_tier = (tier1 + tier2) / 2
        
        if avg_tier >= 6:
            roll = random.random()
            if roll < 0.50:
                return "🏵 Mythic"
            elif roll < 0.80:
                return "🎐 Celestial"
            else:
                return "💫 Neon"
    
    if random.random() < 0.05:
        lucky_pool = ["🏵 Mythic", "🎐 Celestial", "💫 Neon", "🔮 Premium Edition", "💋 Erotic"]
        return random.choice(lucky_pool)
    
    tier1 = get_tier(r1_norm)
    tier2 = get_tier(r2_norm)
    max_tier = max(tier1, tier2)
    min_tier = min(tier1, tier2)
    tier_diff = abs(tier1 - tier2)
    
    if tier_diff >= 3:
        roll = random.random()
        if roll < 0.50:
            result_tier = (tier1 + tier2) // 2
        elif roll < 0.80:
            result_tier = max_tier
        else:
            result_tier = min(max_tier + 1, 7)
    else:
        roll = random.random()
        if roll < 0.50:
            result_tier = max_tier
        elif roll < 0.80:
            result_tier = min(max_tier + 1, 7)
        else:
            result_tier = min(max_tier + 2, 7)
    
    candidates = [r for r, t in TIERS.items() if t == result_tier]
    
    if not candidates:
        return "🏵 Mythic"
    
    weighted_candidates = []
    for candidate in candidates:
        weight = 1
        cand_categories = get_rarity_categories(candidate)
        
        if any(cat in cand_categories for cat in r1_categories):
            weight += 2
        if any(cat in cand_categories for cat in r2_categories):
            weight += 2
        
        weighted_candidates.extend([candidate] * weight)
    
    return random.choice(weighted_candidates) if weighted_candidates else random.choice(candidates)

async def check_cooldown(uid: int) -> Tuple[bool, int]:
    try:
        user = await user_collection.find_one({'id': uid}, {'last_fusion': 1})
        if user and 'last_fusion' in user:
            elapsed = time.time() - user['last_fusion']
            if elapsed < COOLDOWN:
                return False, int(COOLDOWN - elapsed)
        return True, 0
    except Exception as e:
        logger.error(f"Cooldown check error: {e}")
        return True, 0

async def set_cooldown(uid: int):
    try:
        await user_collection.update_one(
            {'id': uid},
            {'$set': {'last_fusion': time.time()}},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Set cooldown error: {e}")

async def get_user_safe(uid: int) -> Dict:
    try:
        user = await user_collection.find_one({'id': uid})
        return user or {}
    except Exception as e:
        logger.error(f"Get user error: {e}")
        return {}

async def atomic_balance_deduct(uid: int, amount: int) -> bool:
    try:
        result = await user_collection.update_one(
            {'id': uid, 'balance': {'$gte': amount}},
            {'$inc': {'balance': -amount}}
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Balance deduct error: {e}")
        return False

async def atomic_stone_use(uid: int, amount: int) -> bool:
    try:
        result = await user_collection.update_one(
            {'id': uid, 'fusion_stones': {'$gte': amount}},
            {'$inc': {'fusion_stones': -amount}}
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Stone use error: {e}")
        return False

async def atomic_char_swap(uid: int, remove_ids: List[str], add_char: Dict) -> bool:
    try:
        user = await user_collection.find_one({'id': uid})
        if not user:
            return False
        
        chars = user.get('characters', [])
        new_chars = []
        removed_count = 0
        
        for c in chars:
            if c.get('id') in remove_ids and removed_count < len(remove_ids):
                removed_count += 1
                continue
            new_chars.append(c)
        
        if removed_count != len(remove_ids):
            return False
        
        new_chars.append(add_char)
        
        await user_collection.update_one(
            {'id': uid},
            {'$set': {'characters': new_chars}}
        )
        return True
    except Exception as e:
        logger.error(f"Char swap error: {e}")
        return False

async def atomic_char_remove(uid: int, remove_ids: List[str]) -> bool:
    try:
        user = await user_collection.find_one({'id': uid})
        if not user:
            return False
        
        chars = user.get('characters', [])
        new_chars = []
        removed_count = 0
        
        for c in chars:
            if c.get('id') in remove_ids and removed_count < len(remove_ids):
                removed_count += 1
                continue
            new_chars.append(c)
        
        if removed_count != len(remove_ids):
            return False
        
        await user_collection.update_one(
            {'id': uid},
            {'$set': {'characters': new_chars}}
        )
        return True
    except Exception as e:
        logger.error(f"Char remove error: {e}")
        return False

async def log_fusion(uid: int, c1_name: str, c2_name: str, success: bool, result_name: str = None):
    try:
        entry = {
            'time': time.time(),
            'c1': c1_name,
            'c2': c2_name,
            'success': success,
            'result': result_name or 'failed'
        }
        
        await user_collection.update_one(
            {'id': uid},
            {
                '$push': {
                    'fusion_history': {
                        '$each': [entry],
                        '$slice': -20
                    }
                },
                '$inc': {
                    'fusion_total': 1,
                    'fusion_success': 1 if success else 0,
                    'fusion_pity': 0 if success else 1
                }
            },
            upsert=True
        )
    except Exception as e:
        logger.error(f"Log fusion error: {e}")

def cleanup_sessions():
    now = time.time()
    expired = [k for k, v in sessions.items() if now - v.get('created', now) > SESSION_EXPIRE]
    for k in expired:
        del sessions[k]

async def fuse_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = update.effective_user.id
        
        can_use, remaining = await check_cooldown(uid)
        if not can_use:
            await update.message.reply_text(
                f"⏱️ cooldown active\nwait {remaining//60}m {remaining%60}s"
            )
            return
        
        user = await get_user_safe(uid)
        chars = user.get('characters', [])
        
        if len(chars) < 2:
            await update.message.reply_text("❌ need at least 2 characters\nuse /grab")
            return
        
        cleanup_sessions()
        
        page = 0
        sessions[uid] = {
            'step': 1,
            'owner': uid,
            'page': page,
            'created': time.time()
        }
        
        await show_char_page(update.message, uid, chars, page, 1, context)
        
    except Exception as e:
        logger.error(f"Fuse cmd error: {e}")
        await update.message.reply_text("⚠️ error occurred")

async def show_char_page(message, uid: int, chars: List[Dict], page: int, step: int, context: ContextTypes.DEFAULT_TYPE, is_edit: bool = False):
    try:
        start = page * CHARS_PER_PAGE
        end = start + CHARS_PER_PAGE
        page_chars = chars[start:end]
        
        if not page_chars:
            text = "❌ no characters on this page"
            if is_edit:
                try:
                    await message.edit_text(text)
                except Exception:
                    await message.reply_text(text)
            else:
                await message.reply_text(text)
            return
        
        buttons = []
        for c in page_chars:
            char_name = c.get('name', 'unknown')
            display_name = char_name[:10] if len(char_name) > 10 else char_name
            char_id = str(c.get('id', ''))[:20]
            
            buttons.append([InlineKeyboardButton(
                f"{norm_rarity(c.get('rarity', 'common'))} {display_name}",
                callback_data=f"fs{step}_{char_id}"
            )])
        
        nav_btns = []
        if page > 0:
            nav_btns.append(InlineKeyboardButton("◀️ prev", callback_data=f"fp{step}_{page-1}"))
        if end < len(chars):
            nav_btns.append(InlineKeyboardButton("next ▶️", callback_data=f"fp{step}_{page+1}"))
        
        if nav_btns:
            buttons.append(nav_btns)
        
        buttons.append([InlineKeyboardButton("❌ cancel", callback_data="fc")])
        
        text = f"⚗️ select character {step}/2\npage {page+1}/{(len(chars)-1)//CHARS_PER_PAGE+1}"
        
        if is_edit:
            try:
                await message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            except TelegramError as te:
                error_str = str(te).lower()
                if "message can't be edited" in error_str or "message is not modified" in error_str:
                    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
                else:
                    logger.error(f"Edit error: {te}")
                    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Show char page error: {e}")
        try:
            text = f"⚗️ select character {step}/2"
            cancel_button = InlineKeyboardMarkup([[InlineKeyboardButton("❌ cancel", callback_data="fc")]])
            if is_edit:
                await message.edit_text(text, reply_markup=cancel_button)
            else:
                await message.reply_text(text, reply_markup=cancel_button)
        except Exception as inner_e:
            logger.error(f"Fallback error: {inner_e}")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    
    try:
        if data == "fc":
            sessions.pop(uid, None)
            await query.answer()
            try:
                await query.edit_message_text("❌ cancelled")
            except Exception:
                await query.message.reply_text("❌ cancelled")
            return
        
        if data == "fshop" or data.startswith("fb_"):
            await query.answer()
        else:
            session = sessions.get(uid)
            if not session or session.get('owner') != uid:
                await query.answer("❌ not your session", show_alert=True)
                return
            await query.answer()
        
        if data.startswith("fp"):
            parts = data[2:].split('_')
            if len(parts) < 2:
                await query.answer("❌ invalid data", show_alert=True)
                return
            
            session = sessions.get(uid)
            step = int(parts[0])
            page = int(parts[1])
            
            session['page'] = page
            user = await get_user_safe(uid)
            chars = user.get('characters', [])
            
            await show_char_page(query.message, uid, chars, page, step, context, is_edit=True)
            return
        
        if data.startswith("fs1_"):
            cid = data[4:]
            session = sessions.get(uid)
            user = await get_user_safe(uid)
            chars = user.get('characters', [])
            char1 = next((c for c in chars if str(c.get('id')) == cid), None)
            
            if not char1:
                await query.edit_message_text("❌ character not found")
                sessions.pop(uid, None)
                return
            
            sessions[uid].update({
                'step': 2,
                'c1': cid,
                'c1_data': char1,
                'stones': 0,
                'page': 0
            })
            
            try:
                await query.edit_message_text(
                    f"✅ {norm_rarity(char1.get('rarity'))} {char1.get('name')}\n\nselecting second character..."
                )
                msg = query.message
            except Exception as e:
                logger.warning(f"Could not edit message: {e}")
                try:
                    media_url = char1.get('img_url', '')
                    if char1.get('rarity', '').lower() == 'amv' or media_url.endswith(('.mp4', '.mov', '.avi')):
                        msg = await context.bot.send_video(
                            chat_id=query.message.chat_id,
                            video=media_url,
                            caption=f"✅ {norm_rarity(char1.get('rarity'))} {char1.get('name')}\n\nselecting second character..."
                        )
                    else:
                        msg = await context.bot.send_photo(
                            chat_id=query.message.chat_id,
                            photo=media_url,
                            caption=f"✅ {norm_rarity(char1.get('rarity'))} {char1.get('name')}\n\nselecting second character..."
                        )
                except Exception as e2:
                    logger.warning(f"Could not send media: {e2}")
                    msg = await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"✅ {norm_rarity(char1.get('rarity'))} {char1.get('name')}\n\nselecting second character..."
                    )
            
            await asyncio.sleep(0.5)
            await show_char_page(msg, uid, chars, 0, 2, context, is_edit=False)
            return
        
        if data.startswith("fs2_"):
            cid = data[4:]
            session = sessions.get(uid)
            user = await get_user_safe(uid)
            chars = user.get('characters', [])
            char2 = next((c for c in chars if str(c.get('id')) == cid), None)
            
            if not char2:
                await query.edit_message_text("❌ character not found")
                sessions.pop(uid, None)
                return
            
            if cid == session.get('c1'):
                await query.answer("❌ cannot select the same character", show_alert=True)
                return
            
            session['c2'] = cid
            session['c2_data'] = char2
            
            try:
                await query.edit_message_text(
                    f"✅ {norm_rarity(char2.get('rarity'))} {char2.get('name')}\n\npreparing fusion..."
                )
            except Exception as e:
                logger.warning(f"Could not edit message: {e}")
            
            try:
                media_url = char2.get('img_url', '')
                if char2.get('rarity', '').lower() == 'amv' or media_url.endswith(('.mp4', '.mov', '.avi')):
                    await context.bot.send_video(
                        chat_id=query.message.chat_id,
                        video=media_url,
                        caption=f"✅ {norm_rarity(char2.get('rarity'))} {char2.get('name')}\n\npreparing fusion..."
                    )
                else:
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id,
                        photo=media_url,
                        caption=f"✅ {norm_rarity(char2.get('rarity'))} {char2.get('name')}\n\npreparing fusion..."
                    )
            except Exception as e:
                logger.warning(f"Could not send media: {e}")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"✅ {char2.get('name')}\n\npreparing..."
                )
            
            await asyncio.sleep(0.5)
            await show_confirm(query.message.chat_id, uid, context)
            return
        
        if data.startswith("fst_"):
            stones_str = data[4:]
            if not stones_str.isdigit():
                await query.answer("❌ invalid stone count", show_alert=True)
                return
            
            session = sessions.get(uid)
            stones = int(stones_str)
            user = await get_user_safe(uid)
            user_stones = user.get('fusion_stones', 0)
            
            if user_stones < stones:
                await query.answer(f"❌ need {stones} stones (have {user_stones})", show_alert=True)
                return
            
            session['stones'] = stones
            await query.answer(f"✅ Using {stones} stones", show_alert=False)
            await update_confirm_message(query, uid, context)
            return
        
        if data == "fconf":
            session = sessions.get(uid)
            await execute_fusion(query, uid, context)
            return
        
        if data == "fshop":
            await show_shop(query, uid)
            return
        
        if data.startswith("fb_"):
            amount_str = data[3:]
            if not amount_str.isdigit():
                await query.answer("❌ invalid amount", show_alert=True)
                return
            
            amount = int(amount_str)
            prices = {1: 100, 5: 450, 10: 850, 20: 1600}
            cost = prices.get(amount, 0)
            
            if cost == 0:
                await query.answer("❌ invalid purchase", show_alert=True)
                return
            
            if not await atomic_balance_deduct(uid, cost):
                user = await get_user_safe(uid)
                await query.answer(f"❌ need {cost:,} coins (have {user.get('balance', 0):,})", show_alert=True)
                return
            
            await user_collection.update_one(
                {'id': uid},
                {'$inc': {'fusion_stones': amount}},
                upsert=True
            )
            
            await query.answer(f"✅ bought {amount} stones!", show_alert=True)
            await show_shop(query, uid)
            return
            
    except Exception as e:
        logger.error(f"Callback error: {e}", exc_info=True)
        await query.answer("⚠️ error occurred", show_alert=True)

async def update_confirm_message(query, uid: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        session = sessions.get(uid)
        if not session:
            await query.answer("❌ session expired", show_alert=True)
            return
        
        c1 = session.get('c1_data')
        c2 = session.get('c2_data')
        
        if not c1 or not c2:
            await query.answer("❌ character data missing", show_alert=True)
            return
        
        stones = session.get('stones', 0)
        
        r1 = norm_rarity(c1.get('rarity'))
        r2 = norm_rarity(c2.get('rarity'))
        result_r = get_result_rarity(r1, r2)
        cost = calc_cost(r1, r2)
        
        user = await get_user_safe(uid)
        bal = user.get('balance', 0)
        user_stones = user.get('fusion_stones', 0)
        pity = user.get('fusion_pity', 0)
        rate = calc_rate(r1, r2, stones, pity)
        
        buttons = []
        stone_btns = []
        for i in range(1, 4):
            if user_stones >= i:
                stone_btns.append(InlineKeyboardButton(
                    f"{'✅' if stones == i else '💎'} {i}",
                    callback_data=f"fst_{i}"
                ))
        
        if stone_btns:
            if len(stone_btns) > 1:
                buttons.append(stone_btns[:2])
                if len(stone_btns) > 2:
                    buttons.append([stone_btns[2]])
            else:
                buttons.append(stone_btns)
        
        fuse_text = "✅ fuse" if bal >= cost else "❌ insufficient"
        fuse_callback = "fconf" if bal >= cost else "fc"
        
        buttons.extend([
            [InlineKeyboardButton(fuse_text, callback_data=fuse_callback)],
            [
                InlineKeyboardButton("💎 buy stones", callback_data="fshop"),
                InlineKeyboardButton("❌ cancel", callback_data="fc")
            ]
        ])
        
        pity_text = f' (+{pity*5}% pity)' if pity > 0 else ''
        stone_text = f' (+{stones*15}%)' if stones else ''
        
        caption = (
            f"⚗️ fusion preview\n\n"
            f"1️⃣ {r1} {c1.get('name')}\n"
            f"     ×\n"
            f"2️⃣ {r2} {c2.get('name')}\n"
            f"     ‖\n"
            f"     ⬇️\n"
            f"✨ {result_r}\n\n"
            f"━━━━━━━━━━━━━━\n"
            f"success: {rate*100:.0f}%{pity_text}\n"
            f"cost: {cost:,} 💰\n"
            f"balance: {bal:,} 💰\n"
            f"stones: {stones}{stone_text}"
        )
        
        try:
            await query.edit_message_text(
                text=caption,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except TelegramError as e:
            error_str = str(e).lower()
            if "message is not modified" not in error_str:
                logger.warning(f"Could not update confirm message: {e}")
                
    except Exception as e:
        logger.error(f"Update confirm message error: {e}", exc_info=True)

async def show_confirm(chat_id: int, uid: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        session = sessions.get(uid)
        if not session:
            await context.bot.send_message(chat_id=chat_id, text="❌ session expired")
            return
        
        c1 = session.get('c1_data')
        c2 = session.get('c2_data')
        
        if not c1 or not c2:
            await context.bot.send_message(chat_id=chat_id, text="❌ character data missing")
            sessions.pop(uid, None)
            return
        
        stones = session.get('stones', 0)
        
        r1 = norm_rarity(c1.get('rarity'))
        r2 = norm_rarity(c2.get('rarity'))
        result_r = get_result_rarity(r1, r2)
        cost = calc_cost(r1, r2)
        
        user = await get_user_safe(uid)
        bal = user.get('balance', 0)
        user_stones = user.get('fusion_stones', 0)
        pity = user.get('fusion_pity', 0)
        rate = calc_rate(r1, r2, stones, pity)
        
        buttons = []
        stone_btns = []
        for i in range(1, 4):
            if user_stones >= i:
                stone_btns.append(InlineKeyboardButton(
                    f"{'✅' if stones == i else '💎'} {i}",
                    callback_data=f"fst_{i}"
                ))
        
        if stone_btns:
            if len(stone_btns) > 1:
                buttons.append(stone_btns[:2])
                if len(stone_btns) > 2:
                    buttons.append([stone_btns[2]])
            else:
                buttons.append(stone_btns)
        
        fuse_text = "✅ fuse" if bal >= cost else "❌ insufficient"
        fuse_callback = "fconf" if bal >= cost else "fc"
        
        buttons.extend([
            [InlineKeyboardButton(fuse_text, callback_data=fuse_callback)],
            [
                InlineKeyboardButton("💎 buy stones", callback_data="fshop"),
                InlineKeyboardButton("❌ cancel", callback_data="fc")
            ]
        ])
        
        pity_text = f' (+{pity*5}% pity)' if pity > 0 else ''
        stone_text = f' (+{stones*15}%)' if stones else ''
        
        caption = (
            f"⚗️ fusion preview\n\n"
            f"1️⃣ {r1} {c1.get('name')}\n"
            f"     ×\n"
            f"2️⃣ {r2} {c2.get('name')}\n"
            f"     ‖\n"
            f"     ⬇️\n"
            f"✨ {result_r}\n\n"
            f"━━━━━━━━━━━━━━\n"
            f"success: {rate*100:.0f}%{pity_text}\n"
            f"cost: {cost:,} 💰\n"
            f"balance: {bal:,} 💰\n"
            f"stones: {stones}{stone_text}"
        )
        
        try:
            media_list = []
            
            media1_url = c1.get('img_url', '')
            if c1.get('rarity', '').lower() == 'amv' or media1_url.endswith(('.mp4', '.mov', '.avi')):
                media_list.append(InputMediaVideo(media=media1_url, caption=f"1️⃣ {r1} {c1.get('name')}"))
            else:
                media_list.append(InputMediaPhoto(media=media1_url, caption=f"1️⃣ {r1} {c1.get('name')}"))
            
            media2_url = c2.get('img_url', '')
            if c2.get('rarity', '').lower() == 'amv' or media2_url.endswith(('.mp4', '.mov', '.avi')):
                media_list.append(InputMediaVideo(media=media2_url, caption=f"2️⃣ {r2} {c2.get('name')}"))
            else:
                media_list.append(InputMediaPhoto(media=media2_url, caption=f"2️⃣ {r2} {c2.get('name')}"))
            
            await context.bot.send_media_group(
                chat_id=chat_id,
                media=media_list
            )
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            
        except Exception as e:
            logger.warning(f"Could not send media group in confirm: {e}")
            try:
                media_url = c1.get('img_url', '')
                if c1.get('rarity', '').lower() == 'amv' or media_url.endswith(('.mp4', '.mov', '.avi')):
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=media_url,
                        caption=caption,
                        reply_markup=InlineKeyboardMarkup(buttons)
                    )
                else:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=media_url,
                        caption=caption,
                        reply_markup=InlineKeyboardMarkup(buttons)
                    )
            except Exception as e2:
                logger.warning(f"Could not send single media: {e2}")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=caption,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            
    except Exception as e:
        logger.error(f"Show confirm error: {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text="⚠️ error preparing fusion")

async def execute_fusion(query, uid: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        session = sessions.get(uid)
        if not session:
            await query.edit_message_text("❌ session expired")
            return
        
        c1 = session.get('c1_data')
        c2 = session.get('c2_data')
        
        if not c1 or not c2:
            await query.edit_message_text("❌ character data missing")
            sessions.pop(uid, None)
            return
        
        stones = session.get('stones', 0)
        r1 = norm_rarity(c1.get('rarity'))
        r2 = norm_rarity(c2.get('rarity'))
        cost = calc_cost(r1, r2)
        
        if not await atomic_balance_deduct(uid, cost):
            await query.edit_message_text("❌ insufficient balance")
            sessions.pop(uid, None)
            return
        
        if stones > 0 and not await atomic_stone_use(uid, stones):
            await user_collection.update_one({'id': uid}, {'$inc': {'balance': cost}})
            await query.edit_message_text("❌ insufficient stones (refunded)")
            sessions.pop(uid, None)
            return
        
        animation_frames = ['⚡', '🌀', '✨', '💫', '🔮']
        for i, frame in enumerate(animation_frames):
            try:
                await query.edit_message_text(f"{frame} fusing... {(i+1)*20}%")
                await asyncio.sleep(0.8)
            except Exception as e:
                logger.warning(f"Animation frame error: {e}")
        
        user = await get_user_safe(uid)
        pity = user.get('fusion_pity', 0)
        rate = calc_rate(r1, r2, stones, pity)
        success = random.random() < rate
        
        if success:
            result_r = get_result_rarity(r1, r2)
            
            result_rarity_raw = None
            for key, value in RARITY_MAP.items():
                if value == result_r:
                    result_rarity_raw = key
                    break
            
            match_query = {'$or': [
                {'rarity': result_r},
                {'rarity': result_rarity_raw} if result_rarity_raw else {'rarity': result_r}
            ]}
            
            new_chars = await collection.aggregate([
                {'$match': match_query},
                {'$sample': {'size': 1}}
            ]).to_list(length=1)
            
            if new_chars:
                new_char = new_chars[0]
                
                if not await atomic_char_swap(uid, [session['c1'], session['c2']], new_char):
                    await user_collection.update_one(
                        {'id': uid},
                        {'$inc': {'balance': cost, 'fusion_stones': stones}}
                    )
                    await query.edit_message_text("❌ fusion failed (refunded)")
                    sessions.pop(uid, None)
                    return
                
                await log_fusion(uid, c1.get('name'), c2.get('name'), True, new_char.get('name'))
                
                try:
                    media_url = new_char.get('img_url', '')
                    if new_char.get('rarity', '').lower() == 'amv' or media_url.endswith(('.mp4', '.mov', '.avi')):
                        await context.bot.send_video(
                            chat_id=query.message.chat_id,
                            video=media_url,
                            caption=(
                                f"✨ success!\n\n"
                                f"{result_r}\n"
                                f"{new_char.get('name')}\n"
                                f"{new_char.get('anime', 'unknown')}\n"
                                f"id: {new_char.get('id')}"
                            )
                        )
                    else:
                        await context.bot.send_photo(
                            chat_id=query.message.chat_id,
                            photo=media_url,
                            caption=(
                                f"✨ success!\n\n"
                                f"{result_r}\n"
                                f"{new_char.get('name')}\n"
                                f"{new_char.get('anime', 'unknown')}\n"
                                f"id: {new_char.get('id')}"
                            )
                        )
                except Exception as e:
                    logger.warning(f"Could not send success media: {e}")
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"✨ success!\n\n{result_r}\n{new_char.get('name')}"
                    )
                
                await query.edit_message_text("✅ fusion complete!")
            else:
                await user_collection.update_one(
                    {'id': uid},
                    {'$inc': {'balance': cost, 'fusion_stones': stones}}
                )
                await query.edit_message_text("❌ no result available (refunded)")
        else:
            if not await atomic_char_remove(uid, [session['c1'], session['c2']]):
                await user_collection.update_one(
                    {'id': uid},
                    {'$inc': {'balance': cost, 'fusion_stones': stones}}
                )
                await query.edit_message_text("❌ fusion error (refunded)")
                sessions.pop(uid, None)
                return
            
            await log_fusion(uid, c1.get('name'), c2.get('name'), False)
            await query.edit_message_text(
                f"💔 failed\n\nlost:\n{c1.get('name')}\n{c2.get('name')}\n\npity: +5%"
            )
        
        await set_cooldown(uid)
        sessions.pop(uid, None)
        
    except Exception as e:
        logger.error(f"Execute fusion error: {e}", exc_info=True)
        try:
            await query.edit_message_text("⚠️ fusion error occurred")
        except Exception:
            await query.message.reply_text("⚠️ fusion error occurred")
        sessions.pop(uid, None)

async def show_shop(query, uid: int):
    try:
        user = await get_user_safe(uid)
        bal = user.get('balance', 0)
        stones = user.get('fusion_stones', 0)
        
        buttons = [
            [
                InlineKeyboardButton("💎 1 - 100", callback_data="fb_1"),
                InlineKeyboardButton("💎 5 - 450", callback_data="fb_5")
            ],
            [
                InlineKeyboardButton("💎 10 - 850", callback_data="fb_10"),
                InlineKeyboardButton("💎 20 - 1600", callback_data="fb_20")
            ],
            [InlineKeyboardButton("⬅️ back", callback_data="fc")]
        ]
        
        shop_text = (
            f"💎 stone shop\n\n"
            f"balance: {bal:,} 💰\n"
            f"stones: {stones}\n\n"
            f"1 = 100 💰\n"
            f"5 = 450 💰 (10% off)\n"
            f"10 = 850 💰 (15% off)\n"
            f"20 = 1600 💰 (20% off)\n\n"
            f"+15% success per stone (max 3)"
        )
        
        await query.edit_message_text(
            shop_text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Show shop error: {e}", exc_info=True)
        try:
            await query.answer("⚠️ error loading shop", show_alert=True)
        except Exception:
            pass

async def info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = update.effective_user.id
        user = await get_user_safe(uid)
        chars = user.get('characters', [])
        
        can_use, remaining = await check_cooldown(uid)
        status = "ready ✅" if can_use else f"cooldown {remaining//60}m {remaining%60}s"
        
        pity = user.get('fusion_pity', 0)
        total = user.get('fusion_total', 0)
        success = user.get('fusion_success', 0)
        rate = (success / total * 100) if total > 0 else 0
        
        info_text = (
            f"⚗️ fusion stats\n\n"
            f"balance: {user.get('balance', 0):,} 💰\n"
            f"stones: {user.get('fusion_stones', 0)} 💎\n"
            f"characters: {len(chars)}\n"
            f"status: {status}\n\n"
            f"total fusions: {total}\n"
            f"success rate: {rate:.1f}%\n"
            f"pity bonus: +{pity*5}%\n\n"
            f"/fuse - start fusion\n"
            f"/buystone - shop"
        )
        
        await update.message.reply_text(info_text)
    except Exception as e:
        logger.error(f"Info cmd error: {e}", exc_info=True)
        await update.message.reply_text("⚠️ error occurred")

async def buystone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = update.effective_user.id
        user = await get_user_safe(uid)
        
        buttons = [
            [
                InlineKeyboardButton("💎 1 - 100", callback_data="fb_1"),
                InlineKeyboardButton("💎 5 - 450", callback_data="fb_5")
            ],
            [
                InlineKeyboardButton("💎 10 - 850", callback_data="fb_10"),
                InlineKeyboardButton("💎 20 - 1600", callback_data="fb_20")
            ],
            [InlineKeyboardButton("❌ close", callback_data="fc")]
        ]
        
        shop_text = (
            f"💎 stone shop\n\n"
            f"balance: {user.get('balance', 0):,} 💰\n"
            f"stones: {user.get('fusion_stones', 0)}\n\n"
            f"1 = 100 💰\n"
            f"5 = 450 💰 (save 50)\n"
            f"10 = 850 💰 (save 150)\n"
            f"20 = 1600 💰 (save 400)"
        )
        
        await update.message.reply_text(
            shop_text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Buystone cmd error: {e}", exc_info=True)
        await update.message.reply_text("⚠️ error occurred")

application.add_handler(CommandHandler(['fuse', 'fusion'], fuse_cmd, block=False))
application.add_handler(CommandHandler(['fusioninfo', 'finfo'], info_cmd, block=False))
application.add_handler(CommandHandler(['buystone', 'buystones'], buystone_cmd, block=False))
application.add_handler(CallbackQueryHandler(callback_handler, pattern='^f', block=False))