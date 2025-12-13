import asyncio
import random
import time
import logging
from typing import List, Dict, Tuple, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from telegram.error import TelegramError
from shivu import application, user_collection, collection
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RARITY_MAP = {
    "common": "🟢 Common", "rare": "🟣 Rare", "legendary": "🟡 Legendary",
    "special": "💮 Special Edition", "neon": "💫 Neon", "manga": "✨ Manga",
    "cosplay": "🎭 Cosplay", "celestial": "🎐 Celestial", "premium": "🔮 Premium Edition",
    "erotic": "💋 Erotic", "summer": "🌤 Summer", "winter": "☃️ Winter",
    "monsoon": "☔️ Monsoon", "valentine": "💝 Valentine", "halloween": "🎃 Halloween",
    "christmas": "🎄 Christmas", "mythic": "🏵 Mythic", "events": "🎗 Special Events",
    "amv": "🎥 AMV", "tiny": "👼 Tiny"
}

TIERS = {
    "🟢 Common": 1, "🟣 Rare": 2, "🟡 Legendary": 3, "💮 Special Edition": 4,
    "💫 Neon": 5, "✨ Manga": 5, "🎭 Cosplay": 5, "🎐 Celestial": 6,
    "🔮 Premium Edition": 6, "💋 Erotic": 6, "🌤 Summer": 4, "☃️ Winter": 4,
    "☔️ Monsoon": 4, "💝 Valentine": 5, "🎃 Halloween": 5, "🎄 Christmas": 5,
    "🏵 Mythic": 7, "🎗 Special Events": 6, "🎥 AMV": 5, "👼 Tiny": 4
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

def get_result_rarity(r1: str, r2: str) -> str:
    max_tier = max(get_tier(r1), get_tier(r2))
    roll = random.random()
    
    if roll < 0.60:
        result_tier = max_tier
    elif roll < 0.90:
        result_tier = min(max_tier + 1, 7)
    else:
        result_tier = min(max_tier + 2, 7)
    
    candidates = [r for r, t in TIERS.items() if t == result_tier]
    return random.choice(candidates) if candidates else "🏵 Mythic"

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

async def fuse_cmd(update: Update, context: CallbackContext):
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

async def show_char_page(message, uid: int, chars: List[Dict], page: int, step: int, context: CallbackContext, is_edit: bool = False):
    try:
        start = page * CHARS_PER_PAGE
        end = start + CHARS_PER_PAGE
        page_chars = chars[start:end]
        
        if not page_chars:
            if is_edit:
                await message.edit_text("❌ no characters on this page")
            else:
                await message.reply_text("❌ no characters on this page")
            return
        
        buttons = []
        for c in page_chars:
            buttons.append([InlineKeyboardButton(
                f"{norm_rarity(c.get('rarity', 'common'))} {c.get('name', 'unknown')[:12]}",
                callback_data=f"fs{step}_{c.get('id')}"
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
                if "message can't be edited" in str(te).lower() or "message is not modified" in str(te).lower():
                    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
                else:
                    raise
        else:
            await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Show char page error: {e}")
        try:
            await message.reply_text(f"⚗️ select character {step}/2", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ cancel", callback_data="fc")]]))
        except:
            pass

async def callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    
    try:
        if data == "fc":
            sessions.pop(uid, None)
            await query.edit_message_text("❌ cancelled")
            return
        
        session = sessions.get(uid)
        if not session or session.get('owner') != uid:
            await query.answer("❌ not your session", show_alert=True)
            return
        
        await query.answer()
        
        if data.startswith("fp"):
            parts = data[2:].split('_')
            step = int(parts[0])
            page = int(parts[1])
            
            session['page'] = page
            user = await get_user_safe(uid)
            chars = user.get('characters', [])
            
            await show_char_page(query.message, uid, chars, page, step, context, is_edit=True)
            return
        
        if data.startswith("fs1_"):
            cid = data[4:]
            user = await get_user_safe(uid)
            chars = user.get('characters', [])
            char1 = next((c for c in chars if c.get('id') == cid), None)
            
            if not char1:
                await query.edit_message_text("❌ character not found")
                return
            
            sessions[uid].update({
                'step': 2,
                'c1': cid,
                'c1_data': char1,
                'stones': 0,
                'page': 0
            })
            
            try:
                await query.delete_message()
            except:
                pass
            
            msg = await query.message.reply_photo(
                photo=char1.get('img_url', ''),
                caption=f"✅ {norm_rarity(char1.get('rarity'))} {char1.get('name')}\n\nselecting second character..."
            )
            
            await asyncio.sleep(0.5)
            await show_char_page(msg, uid, chars, 0, 2, context, is_edit=False)
            return
        
        if data.startswith("fs2_"):
            cid = data[4:]
            user = await get_user_safe(uid)
            chars = user.get('characters', [])
            char2 = next((c for c in chars if c.get('id') == cid), None)
            
            if not char2:
                await query.edit_message_text("❌ character not found")
                return
            
            session['c2'] = cid
            session['c2_data'] = char2
            
            try:
                await query.delete_message()
            except:
                pass
            
            try:
                await query.message.reply_photo(
                    photo=char2.get('img_url', ''),
                    caption=f"✅ {norm_rarity(char2.get('rarity'))} {char2.get('name')}\n\npreparing fusion..."
                )
            except:
                await query.message.reply_text(f"✅ {char2.get('name')}\n\npreparing...")
            
            await asyncio.sleep(0.5)
            await show_confirm(query.message, uid, context)
            return
        
        if data.startswith("fst_"):
            stones = int(data[4])
            user = await get_user_safe(uid)
            user_stones = user.get('fusion_stones', 0)
            
            if user_stones < stones:
                await query.answer(f"❌ need {stones} stones (have {user_stones})", show_alert=True)
                return
            
            session['stones'] = stones
            
            try:
                await query.delete_message()
            except:
                pass
            
            await show_confirm(query.message, uid, context)
            return
        
        if data == "fconf":
            await execute_fusion(query, uid, context)
            return
        
        if data == "fshop":
            await show_shop(query, uid)
            return
        
        if data.startswith("fb_"):
            amount = int(data[3:])
            prices = {1: 100, 5: 450, 10: 850, 20: 1600}
            cost = prices.get(amount, 0)
            
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
        logger.error(f"Callback error: {e}")
        await query.answer("⚠️ error occurred", show_alert=True)

async def show_confirm(message, uid: int, context: CallbackContext):
    try:
        session = sessions[uid]
        c1 = session['c1_data']
        c2 = session['c2_data']
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
        stone_btns = [InlineKeyboardButton(
            f"{'✅' if stones == i else '💎'} {i}",
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
            f"     ×\n"
            f"2️⃣ {r2} {c2.get('name')}\n"
            f"     ‖\n"
            f"     ⬇️\n"
            f"✨ {result_r}\n\n"
            f"━━━━━━━━━━━━━━\n"
            f"success: {rate*100:.0f}%{f' (+{pity*5}% pity)' if pity > 0 else ''}\n"
            f"cost: {cost:,} 💰\n"
            f"balance: {bal:,} 💰\n"
            f"stones: {stones}{f' (+{stones*15}%)' if stones else ''}"
        )
        
        try:
            await message.reply_photo(
                photo=c1.get('img_url', ''),
                caption=caption,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except:
            await message.reply_text(caption, reply_markup=InlineKeyboardMarkup(buttons))
            
    except Exception as e:
        logger.error(f"Show confirm error: {e}")
        await message.reply_text("⚠️ error preparing fusion")

async def execute_fusion(query, uid: int, context: CallbackContext):
    try:
        session = sessions.get(uid)
        if not session:
            await query.edit_message_text("❌ session expired")
            return
        
        c1, c2 = session['c1_data'], session['c2_data']
        stones = session.get('stones', 0)
        r1, r2 = norm_rarity(c1.get('rarity')), norm_rarity(c2.get('rarity'))
        cost = calc_cost(r1, r2)
        
        if not await atomic_balance_deduct(uid, cost):
            await query.edit_message_text("❌ insufficient balance")
            return
        
        if stones > 0 and not await atomic_stone_use(uid, stones):
            await user_collection.update_one({'id': uid}, {'$inc': {'balance': cost}})
            await query.edit_message_text("❌ insufficient stones (refunded)")
            return
        
        for i in range(5):
            await query.edit_message_text(f"{'⚡🌀✨💫🔮'[i]} fusing... {i*25}%")
            await asyncio.sleep(0.8)
        
        user = await get_user_safe(uid)
        pity = user.get('fusion_pity', 0)
        rate = calc_rate(r1, r2, stones, pity)
        success = random.random() < rate
        
        if success:
            result_r = get_result_rarity(r1, r2)
            new_chars = await collection.aggregate([
                {'$match': {'rarity': result_r}},
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
                    return
                
                await log_fusion(uid, c1.get('name'), c2.get('name'), True, new_char.get('name'))
                
                await query.message.reply_photo(
                    photo=new_char.get('img_url', ''),
                    caption=f"✨ success!\n\n{result_r}\n{new_char.get('name')}\n{new_char.get('anime', 'unknown')}\nid: {new_char.get('id')}"
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
                return
            
            await log_fusion(uid, c1.get('name'), c2.get('name'), False)
            await query.edit_message_text(
                f"💔 failed\n\nlost:\n{c1.get('name')}\n{c2.get('name')}\n\npity: +5%"
            )
        
        await set_cooldown(uid)
        sessions.pop(uid, None)
        
    except Exception as e:
        logger.error(f"Execute fusion error: {e}")
        await query.edit_message_text("⚠️ fusion error occurred")

async def show_shop(query, uid: int):
    try:
        user = await get_user_safe(uid)
        bal = user.get('balance', 0)
        stones = user.get('fusion_stones', 0)
        
        buttons = [
            [InlineKeyboardButton("💎 1 - 100", callback_data="fb_1"), InlineKeyboardButton("💎 5 - 450", callback_data="fb_5")],
            [InlineKeyboardButton("💎 10 - 850", callback_data="fb_10"), InlineKeyboardButton("💎 20 - 1600", callback_data="fb_20")],
            [InlineKeyboardButton("⬅️ back", callback_data="fc")]
        ]
        
        await query.edit_message_text(
            f"💎 stone shop\n\nbalance: {bal:,} 💰\nstones: {stones}\n\n"
            f"1 = 100 💰\n5 = 450 💰 (10% off)\n10 = 850 💰 (15% off)\n20 = 1600 💰 (20% off)\n\n"
            f"+15% success per stone (max 3)",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Show shop error: {e}")

async def info_cmd(update: Update, context: CallbackContext):
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
        
        await update.message.reply_text(
            f"⚗️ fusion stats\n\n"
            f"balance: {user.get('balance', 0):,} 💰\n"
            f"stones: {user.get('fusion_stones', 0)} 💎\n"
            f"characters: {len(chars)}\n"
            f"status: {status}\n\n"
            f"total fusions: {total}\n"
            f"success rate: {rate:.1f}%\n"
            f"pity bonus: +{pity*5}%\n\n"
            f"/fuse - start fusion\n/buystone - shop"
        )
    except Exception as e:
        logger.error(f"Info cmd error: {e}")
        await update.message.reply_text("⚠️ error occurred")

async def buystone_cmd(update: Update, context: CallbackContext):
    try:
        uid = update.effective_user.id
        user = await get_user_safe(uid)
        
        buttons = [
            [InlineKeyboardButton("💎 1 - 100", callback_data="fb_1"), InlineKeyboardButton("💎 5 - 450", callback_data="fb_5")],
            [InlineKeyboardButton("💎 10 - 850", callback_data="fb_10"), InlineKeyboardButton("💎 20 - 1600", callback_data="fb_20")],
            [InlineKeyboardButton("❌ close", callback_data="fc")]
        ]
        
        await update.message.reply_text(
            f"💎 stone shop\n\nbalance: {user.get('balance', 0):,} 💰\nstones: {user.get('fusion_stones', 0)}\n\n"
            f"1 = 100 💰\n5 = 450 💰 (save 50)\n10 = 850 💰 (save 150)\n20 = 1600 💰 (save 400)",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Buystone cmd error: {e}")
        await update.message.reply_text("⚠️ error occurred")

application.add_handler(CommandHandler(['fuse', 'fusion'], fuse_cmd, block=False))
application.add_handler(CommandHandler(['fusioninfo', 'finfo'], info_cmd, block=False))
application.add_handler(CommandHandler(['buystone', 'buystones'], buystone_cmd, block=False))
application.add_handler(CallbackQueryHandler(callback_handler, pattern='^f', block=False))