import asyncio
import random
import time
from typing import List, Dict, Tuple, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext, ConversationHandler
from telegram.error import TelegramError
from shivu import application, user_collection, collection

HAREM_MODE_MAPPING = {
    "common": "🟢 Common",
    "rare": "🟣 Rare",
    "legendary": "🟡 Legendary",
    "special": "💮 Special Edition",
    "neon": "💫 Neon",
    "manga": "✨ Manga",
    "cosplay": "🎭 Cosplay",
    "celestial": "🎐 Celestial",
    "premium": "🔮 Premium Edition",
    "erotic": "💋 Erotic",
    "summer": "🌤 Summer",
    "winter": "☃️ Winter",
    "monsoon": "☔️ Monsoon",
    "valentine": "💝 Valentine",
    "halloween": "🎃 Halloween",
    "christmas": "🎄 Christmas",
    "mythic": "🏵 Mythic",
    "events": "🎗 Special Events",
    "amv": "🎥 AMV",
    "tiny": "👼 Tiny",
    "default": None
}

RARITY_TIERS = {
    "🟢 Common": 1, "🟣 Rare": 2, "🟡 Legendary": 3,
    "💮 Special Edition": 4, "💫 Neon": 5, "✨ Manga": 5,
    "🎭 Cosplay": 5, "🎐 Celestial": 6, "🔮 Premium Edition": 6,
    "💋 Erotic": 6, "🌤 Summer": 4, "☃️ Winter": 4,
    "☔️ Monsoon": 4, "💝 Valentine": 5, "🎃 Halloween": 5,
    "🎄 Christmas": 5, "🏵 Mythic": 7, "🎗 Special Events": 6,
    "🎥 AMV": 5, "👼 Tiny": 4
}

FUSION_COSTS = {1: 500, 2: 1000, 3: 2000, 4: 3500, 5: 5000, 6: 7500, 7: 10000}
FUSION_SUCCESS_RATES = {0: 0.85, 1: 0.70, 2: 0.55, 3: 0.40}
FUSION_STONE_BOOST = 0.15
FUSION_STONE_COST = 100
FUSION_COOLDOWN = 1800
FUSION_STONE_COOLDOWN = 3600

fusion_cooldowns = {}
fusion_stone_cooldowns = {}
pending_fusions = {}

FUSION_ANIMATIONS = [
    "⚡ Gathering energy...",
    "🌀 Characters merging...",
    "✨ Fusion in progress...",
    "💫 Creating new bond...",
    "🔮 Almost there..."
]

SUCCESS_GIFS = [
    "https://i.imgur.com/XyZ9abc.gif",
    "https://te.legra.ph/file/fusion-success-1.gif"
]

FAIL_GIFS = [
    "https://i.imgur.com/FailXyz.gif",
    "https://te.legra.ph/file/fusion-fail-1.gif"
]


def get_rarity_tier(rarity: str) -> int:
    return RARITY_TIERS.get(rarity, 1)


def calculate_fusion_cost(char1_rarity: str, char2_rarity: str) -> int:
    tier1 = get_rarity_tier(char1_rarity)
    tier2 = get_rarity_tier(char2_rarity)
    avg_tier = (tier1 + tier2) // 2
    return FUSION_COSTS.get(avg_tier, 1000)


def calculate_success_rate(char1_rarity: str, char2_rarity: str, stones: int = 0) -> float:
    tier1 = get_rarity_tier(char1_rarity)
    tier2 = get_rarity_tier(char2_rarity)
    tier_diff = abs(tier1 - tier2)
    base_rate = FUSION_SUCCESS_RATES.get(min(tier_diff, 3), 0.40)
    stone_bonus = min(stones, 3) * FUSION_STONE_BOOST
    return min(base_rate + stone_bonus, 0.95)


def get_fusion_result_rarity(char1_rarity: str, char2_rarity: str) -> str:
    tier1 = get_rarity_tier(char1_rarity)
    tier2 = get_rarity_tier(char2_rarity)
    max_tier = max(tier1, tier2)
    result_tier = min(max_tier + 1, 7)
    
    for rarity, tier in RARITY_TIERS.items():
        if tier == result_tier:
            return rarity
    return "🏵 Mythic"


def check_cooldown(user_id: int, cooldown_type: str) -> Tuple[bool, int]:
    cooldowns = fusion_cooldowns if cooldown_type == 'fusion' else fusion_stone_cooldowns
    cooldown_time = FUSION_COOLDOWN if cooldown_type == 'fusion' else FUSION_STONE_COOLDOWN
    
    if user_id in cooldowns:
        elapsed = time.time() - cooldowns[user_id]
        if elapsed < cooldown_time:
            remaining = int(cooldown_time - elapsed)
            return False, remaining
    return True, 0


def set_cooldown(user_id: int, cooldown_type: str):
    cooldowns = fusion_cooldowns if cooldown_type == 'fusion' else fusion_stone_cooldowns
    cooldowns[user_id] = time.time()


async def get_user_characters(user_id: int) -> List[Dict]:
    try:
        user_data = await user_collection.find_one({'id': user_id})
        if user_data and 'characters' in user_data:
            return user_data['characters']
        return []
    except Exception as e:
        print(f"Error fetching characters: {e}")
        return []


async def get_character_by_id(char_id: str) -> Optional[Dict]:
    try:
        char = await collection.find_one({'id': char_id})
        return char
    except Exception as e:
        print(f"Error fetching character: {e}")
        return None


async def remove_characters_from_user(user_id: int, char_ids: List[str]) -> bool:
    try:
        user_data = await user_collection.find_one({'id': user_id})
        if not user_data:
            return False
        
        characters = user_data.get('characters', [])
        for char_id in char_ids:
            for i, char in enumerate(characters):
                if char.get('id') == char_id:
                    characters.pop(i)
                    break
        
        await user_collection.update_one(
            {'id': user_id},
            {'$set': {'characters': characters}}
        )
        return True
    except Exception as e:
        print(f"Error removing characters: {e}")
        return False


async def add_character_to_user(user_id: int, character: Dict) -> bool:
    try:
        await user_collection.update_one(
            {'id': user_id},
            {'$push': {'characters': character}}
        )
        return True
    except Exception as e:
        print(f"Error adding character: {e}")
        return False


async def deduct_balance(user_id: int, amount: int) -> bool:
    try:
        user_data = await user_collection.find_one({'id': user_id})
        if not user_data or user_data.get('balance', 0) < amount:
            return False
        
        await user_collection.update_one(
            {'id': user_id},
            {'$inc': {'balance': -amount}}
        )
        return True
    except Exception as e:
        print(f"Error deducting balance: {e}")
        return False


async def get_user_fusion_stones(user_id: int) -> int:
    try:
        user_data = await user_collection.find_one({'id': user_id})
        return user_data.get('fusion_stones', 0) if user_data else 0
    except Exception as e:
        print(f"Error fetching fusion stones: {e}")
        return 0


async def use_fusion_stones(user_id: int, amount: int) -> bool:
    try:
        stones = await get_user_fusion_stones(user_id)
        if stones < amount:
            return False
        
        await user_collection.update_one(
            {'id': user_id},
            {'$inc': {'fusion_stones': -amount}}
        )
        return True
    except Exception as e:
        print(f"Error using fusion stones: {e}")
        return False


async def add_fusion_stones(user_id: int, amount: int) -> bool:
    try:
        await user_collection.update_one(
            {'id': user_id},
            {'$inc': {'fusion_stones': amount}},
            upsert=True
        )
        return True
    except Exception as e:
        print(f"Error adding fusion stones: {e}")
        return False


async def fusion_start(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id
        first_name = update.effective_user.first_name
        
        can_fuse, remaining = check_cooldown(user_id, 'fusion')
        if not can_fuse:
            mins = remaining // 60
            secs = remaining % 60
            await update.message.reply_text(
                f"⏳ <b>Fusion Cooldown</b>\n\nWait <b>{mins}m {secs}s</b> before fusing again!",
                parse_mode='HTML'
            )
            return
        
        characters = await get_user_characters(user_id)
        if len(characters) < 2:
            await update.message.reply_text(
                "❌ <b>Not Enough Characters</b>\n\nYou need at least 2 characters to fuse!\nUse /grab to collect more characters.",
                parse_mode='HTML'
            )
            return
        
        await show_fusion_menu(update, context, user_id, first_name, characters)
        
    except Exception as e:
        print(f"Error in fusion_start: {e}")
        await update.message.reply_text(
            "⚠️ An error occurred. Please try again later.",
            parse_mode='HTML'
        )


async def show_fusion_menu(update, context, user_id: int, first_name: str, characters: List[Dict]):
    rarity_groups = {}
    for char in characters:
        rarity = char.get('rarity', '🟢 Common')
        if rarity not in rarity_groups:
            rarity_groups[rarity] = []
        rarity_groups[rarity].append(char)
    
    buttons = []
    char_list = []
    
    for idx, char in enumerate(characters[:20]):
        char_name = char.get('name', 'Unknown')[:15]
        char_rarity = char.get('rarity', '🟢 Common')
        char_list.append(f"{idx+1}. {char_rarity} {char_name}")
        
        if idx < 8:
            buttons.append([InlineKeyboardButton(
                f"{char_rarity} {char_name}",
                callback_data=f"fuse_select1_{char.get('id')}"
            )])
    
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="fuse_cancel")])
    
    caption = (
        f"⚡ <b>CHARACTER FUSION LABORATORY</b> ⚡\n\n"
        f"👤 Player: {first_name}\n"
        f"📊 Total Characters: {len(characters)}\n\n"
        f"<b>Select First Character:</b>\n"
        + "\n".join(char_list[:8])
    )
    
    if len(characters) > 8:
        caption += f"\n\n<i>Showing first 8 characters...</i>"
    
    await update.message.reply_text(
        caption,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode='HTML'
    )


async def fusion_callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    try:
        if data == "fuse_cancel":
            if user_id in pending_fusions:
                del pending_fusions[user_id]
            await query.edit_message_text(
                "❌ <b>Fusion Cancelled</b>\n\nYou can start again with /fuse",
                parse_mode='HTML'
            )
            return
        
        if data.startswith("fuse_select1_"):
            char1_id = data.replace("fuse_select1_", "")
            characters = await get_user_characters(user_id)
            
            pending_fusions[user_id] = {'char1_id': char1_id, 'stones': 0}
            
            buttons = []
            char_list = []
            
            for idx, char in enumerate(characters[:8]):
                if char.get('id') == char1_id:
                    continue
                
                char_name = char.get('name', 'Unknown')[:15]
                char_rarity = char.get('rarity', '🟢 Common')
                char_list.append(f"{len(char_list)+1}. {char_rarity} {char_name}")
                
                buttons.append([InlineKeyboardButton(
                    f"{char_rarity} {char_name}",
                    callback_data=f"fuse_select2_{char.get('id')}"
                )])
            
            buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="fuse_cancel")])
            
            char1 = next((c for c in characters if c.get('id') == char1_id), None)
            char1_name = char1.get('name', 'Unknown') if char1 else 'Unknown'
            char1_rarity = char1.get('rarity', '🟢 Common') if char1 else '🟢 Common'
            
            await query.edit_message_text(
                f"⚡ <b>CHARACTER FUSION</b> ⚡\n\n"
                f"✅ First Character: {char1_rarity} {char1_name}\n\n"
                f"<b>Select Second Character:</b>\n"
                + "\n".join(char_list),
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode='HTML'
            )
            return
        
        if data.startswith("fuse_select2_"):
            char2_id = data.replace("fuse_select2_", "")
            
            if user_id not in pending_fusions:
                await query.edit_message_text("❌ Session expired. Use /fuse to start again.")
                return
            
            pending_fusions[user_id]['char2_id'] = char2_id
            await show_fusion_confirmation(query, context, user_id)
            return
        
        if data.startswith("fuse_stones_"):
            stone_count = int(data.replace("fuse_stones_", ""))
            
            if user_id not in pending_fusions:
                await query.edit_message_text("❌ Session expired. Use /fuse to start again.")
                return
            
            user_stones = await get_user_fusion_stones(user_id)
            if user_stones < stone_count:
                await query.answer(f"❌ You only have {user_stones} fusion stones!", show_alert=True)
                return
            
            pending_fusions[user_id]['stones'] = stone_count
            await show_fusion_confirmation(query, context, user_id)
            return
        
        if data == "fuse_confirm":
            await execute_fusion(query, context, user_id)
            return
        
        if data == "fuse_buy_stones":
            await show_stone_shop(query, context, user_id)
            return
        
        if data.startswith("buy_stones_"):
            amount = int(data.replace("buy_stones_", ""))
            await buy_fusion_stones(query, context, user_id, amount)
            return
        
    except Exception as e:
        print(f"Error in fusion callback: {e}")
        await query.edit_message_text(
            "⚠️ An error occurred. Please try /fuse again.",
            parse_mode='HTML'
        )


async def show_fusion_confirmation(query, context, user_id: int):
    try:
        fusion_data = pending_fusions[user_id]
        char1_id = fusion_data['char1_id']
        char2_id = fusion_data['char2_id']
        stones = fusion_data.get('stones', 0)
        
        characters = await get_user_characters(user_id)
        char1 = next((c for c in characters if c.get('id') == char1_id), None)
        char2 = next((c for c in characters if c.get('id') == char2_id), None)
        
        if not char1 or not char2:
            await query.edit_message_text("❌ Characters not found. Please try again.")
            return
        
        char1_rarity = char1.get('rarity', '🟢 Common')
        char2_rarity = char2.get('rarity', '🟢 Common')
        result_rarity = get_fusion_result_rarity(char1_rarity, char2_rarity)
        cost = calculate_fusion_cost(char1_rarity, char2_rarity)
        success_rate = calculate_success_rate(char1_rarity, char2_rarity, stones)
        
        user_data = await user_collection.find_one({'id': user_id})
        balance = user_data.get('balance', 0) if user_data else 0
        user_stones = await get_user_fusion_stones(user_id)
        
        buttons = []
        
        stone_buttons = []
        for i in range(1, 4):
            if user_stones >= i:
                stone_buttons.append(InlineKeyboardButton(
                    f"{'✅' if stones == i else ''} Use {i} Stone{'s' if i > 1 else ''}",
                    callback_data=f"fuse_stones_{i}"
                ))
        
        if stone_buttons:
            buttons.append(stone_buttons[:2])
            if len(stone_buttons) > 2:
                buttons.append([stone_buttons[2]])
        
        if balance >= cost:
            buttons.append([
                InlineKeyboardButton("✅ FUSE NOW", callback_data="fuse_confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="fuse_cancel")
            ])
        else:
            buttons.append([InlineKeyboardButton("❌ Insufficient Coins", callback_data="fuse_cancel")])
        
        buttons.append([InlineKeyboardButton("💎 Buy Fusion Stones", callback_data="fuse_buy_stones")])
        
        caption = (
            f"⚡ <b>FUSION CONFIRMATION</b> ⚡\n\n"
            f"<b>Sacrificing:</b>\n"
            f"1️⃣ {char1_rarity} {char1.get('name', 'Unknown')}\n"
            f"2️⃣ {char2_rarity} {char2.get('name', 'Unknown')}\n\n"
            f"<b>Result Rarity:</b> {result_rarity}\n"
            f"<b>Success Rate:</b> {success_rate*100:.1f}%\n"
            f"<b>Cost:</b> 💰 {cost:,} coins\n"
            f"<b>Your Balance:</b> 💰 {balance:,} coins\n"
            f"<b>Fusion Stones:</b> 💎 {user_stones}\n"
            f"<b>Using Stones:</b> {stones} {'(+'+str(int(stones*FUSION_STONE_BOOST*100))+'%)' if stones > 0 else ''}\n\n"
            f"⚠️ <i>Failed fusions lose both characters!</i>"
        )
        
        await query.edit_message_text(
            caption,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode='HTML'
        )
        
    except Exception as e:
        print(f"Error showing confirmation: {e}")
        await query.edit_message_text("⚠️ An error occurred.")


async def execute_fusion(query, context, user_id: int):
    try:
        fusion_data = pending_fusions.get(user_id)
        if not fusion_data:
            await query.edit_message_text("❌ Session expired.")
            return
        
        char1_id = fusion_data['char1_id']
        char2_id = fusion_data['char2_id']
        stones = fusion_data.get('stones', 0)
        
        characters = await get_user_characters(user_id)
        char1 = next((c for c in characters if c.get('id') == char1_id), None)
        char2 = next((c for c in characters if c.get('id') == char2_id), None)
        
        if not char1 or not char2:
            await query.edit_message_text("❌ Characters not found.")
            return
        
        cost = calculate_fusion_cost(char1.get('rarity'), char2.get('rarity'))
        if not await deduct_balance(user_id, cost):
            await query.edit_message_text("❌ Insufficient balance!")
            return
        
        if stones > 0:
            if not await use_fusion_stones(user_id, stones):
                await user_collection.update_one({'id': user_id}, {'$inc': {'balance': cost}})
                await query.edit_message_text("❌ Failed to use fusion stones!")
                return
        
        if not await remove_characters_from_user(user_id, [char1_id, char2_id]):
            await user_collection.update_one(
                {'id': user_id},
                {'$inc': {'balance': cost, 'fusion_stones': stones}}
            )
            await query.edit_message_text("❌ Error removing characters!")
            return
        
        for frame in FUSION_ANIMATIONS:
            await query.edit_message_text(
                f"⚡ <b>FUSION IN PROGRESS</b> ⚡\n\n{frame}",
                parse_mode='HTML'
            )
            await asyncio.sleep(1.5)
        
        success_rate = calculate_success_rate(char1.get('rarity'), char2.get('rarity'), stones)
        is_success = random.random() < success_rate
        
        if is_success:
            result_rarity = get_fusion_result_rarity(char1.get('rarity'), char2.get('rarity'))
            
            new_chars = await collection.aggregate([
                {'$match': {'rarity': result_rarity}},
                {'$sample': {'size': 1}}
            ]).to_list(length=None)
            
            if new_chars:
                new_char = new_chars[0]
                await add_character_to_user(user_id, new_char)
                
                caption = (
                    f"✨ <b>FUSION SUCCESS!</b> ✨\n\n"
                    f"🎉 You created:\n"
                    f"{result_rarity} <b>{new_char.get('name', 'Unknown')}</b>\n\n"
                    f"<b>Anime:</b> {new_char.get('anime', 'Unknown')}\n"
                    f"<b>ID:</b> <code>{new_char.get('id')}</code>\n\n"
                    f"Added to your harem! 💕"
                )
                
                try:
                    await query.message.reply_photo(
                        photo=new_char.get('img_url', ''),
                        caption=caption,
                        parse_mode='HTML'
                    )
                except:
                    await query.message.reply_text(caption, parse_mode='HTML')
                
                await query.edit_message_text("✅ Fusion completed successfully!", parse_mode='HTML')
            else:
                await user_collection.update_one(
                    {'id': user_id},
                    {
                        '$inc': {'balance': cost},
                        '$push': {'characters': {'$each': [char1, char2]}}
                    }
                )
                await query.edit_message_text("❌ No characters available. Refunded!")
        else:
            caption = (
                f"💔 <b>FUSION FAILED!</b> 💔\n\n"
                f"Lost characters:\n"
                f"• {char1.get('rarity')} {char1.get('name')}\n"
                f"• {char2.get('rarity')} {char2.get('name')}\n\n"
                f"Better luck next time! 🍀"
            )
            
            await query.edit_message_text(caption, parse_mode='HTML')
        
        set_cooldown(user_id, 'fusion')
        
        if user_id in pending_fusions:
            del pending_fusions[user_id]
        
    except Exception as e:
        print(f"Error executing fusion: {e}")
        await query.edit_message_text("⚠️ Fusion error occurred!")


async def show_stone_shop(query, context, user_id: int):
    try:
        user_data = await user_collection.find_one({'id': user_id})
        balance = user_data.get('balance', 0) if user_data else 0
        current_stones = await get_user_fusion_stones(user_id)
        
        buttons = [
            [
                InlineKeyboardButton("💎 Buy 1 Stone - 100 💰", callback_data="buy_stones_1"),
                InlineKeyboardButton("💎 Buy 5 Stones - 450 💰", callback_data="buy_stones_5")
            ],
            [
                InlineKeyboardButton("💎 Buy 10 Stones - 850 💰", callback_data="buy_stones_10"),
                InlineKeyboardButton("💎 Buy 20 Stones - 1600 💰", callback_data="buy_stones_20")
            ],
            [InlineKeyboardButton("⬅️ Back to Fusion", callback_data="stone_back")]
        ]
        
        caption = (
            f"💎 <b>FUSION STONE SHOP</b> 💎\n\n"
            f"<b>Your Balance:</b> 💰 {balance:,} coins\n"
            f"<b>Current Stones:</b> 💎 {current_stones}\n\n"
            f"<b>What are Fusion Stones?</b>\n"
            f"• Increase fusion success rate by 15% per stone\n"
            f"• Use up to 3 stones per fusion\n"
            f"• Never expire!\n\n"
            f"<b>Shop Prices:</b>\n"
            f"1 Stone = 100 💰\n"
            f"5 Stones = 450 💰 (10% OFF)\n"
            f"10 Stones = 850 💰 (15% OFF)\n"
            f"20 Stones = 1,600 💰 (20% OFF)"
        )
        
        await query.edit_message_text(
            caption,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode='HTML'
        )
        
    except Exception as e:
        print(f"Error showing stone shop: {e}")
        await query.edit_message_text("⚠️ An error occurred.")


async def buy_fusion_stones(query, context, user_id: int, amount: int):
    try:
        stone_prices = {1: 100, 5: 450, 10: 850, 20: 1600}
        cost = stone_prices.get(amount, 0)
        
        if cost == 0:
            await query.answer("❌ Invalid amount!", show_alert=True)
            return
        
        user_data = await user_collection.find_one({'id': user_id})
        balance = user_data.get('balance', 0) if user_data else 0
        
        if balance < cost:
            await query.answer(f"❌ You need {cost:,} coins! You have {balance:,} coins.", show_alert=True)
            return
        
        if not await deduct_balance(user_id, cost):
            await query.answer("❌ Transaction failed!", show_alert=True)
            return
        
        if not await add_fusion_stones(user_id, amount):
            await user_collection.update_one({'id': user_id}, {'$inc': {'balance': cost}})
            await query.answer("❌ Failed to add stones!", show_alert=True)
            return
        
        await query.answer(f"✅ Successfully purchased {amount} fusion stones!", show_alert=True)
        await show_stone_shop(query, context, user_id)
        
    except Exception as e:
        print(f"Error buying stones: {e}")
        await query.answer("⚠️ Purchase failed!", show_alert=True)


async def fusion_info(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id
        user_data = await user_collection.find_one({'id': user_id})
        balance = user_data.get('balance', 0) if user_data else 0
        stones = await get_user_fusion_stones(user_id)
        characters = await get_user_characters(user_id)
        
        can_fuse, remaining = check_cooldown(user_id, 'fusion')
        cooldown_text = "Ready to fuse!" if can_fuse else f"Cooldown: {remaining//60}m {remaining%60}s"
        
        rarity_count = {}
        for char in characters:
            rarity = char.get('rarity', '🟢 Common')
            rarity_count[rarity] = rarity_count.get(rarity, 0) + 1
        
        rarity_list = "\n".join([f"{rarity}: {count}" for rarity, count in sorted(rarity_count.items(), key=lambda x: get_rarity_tier(x[0]))])
        
        info_text = (
            f"⚡ <b>FUSION SYSTEM INFO</b> ⚡\n\n"
            f"👤 <b>Your Stats:</b>\n"
            f"💰 Balance: {balance:,} coins\n"
            f"💎 Fusion Stones: {stones}\n"
            f"📊 Total Characters: {len(characters)}\n"
            f"⏱ Status: {cooldown_text}\n\n"
            f"<b>Character Collection:</b>\n{rarity_list or 'No characters yet!'}\n\n"
            f"<b>How Fusion Works:</b>\n"
            f"• Select 2 characters to fuse\n"
            f"• Pay fusion cost in coins\n"
            f"• Success creates higher rarity character\n"
            f"• Failure loses both characters\n"
            f"• Use fusion stones to boost success rate\n\n"
            f"<b>Success Rates:</b>\n"
            f"• Same tier: 85%\n"
            f"• 1 tier diff: 70%\n"
            f"• 2 tier diff: 55%\n"
            f"• 3+ tier diff: 40%\n\n"
            f"<b>Commands:</b>\n"
            f"/fuse - Start fusion\n"
            f"/fusioninfo - Show this info\n"
            f"/buystones - Quick buy fusion stones"
        )
        
        await update.message.reply_text(info_text, parse_mode='HTML')
        
    except Exception as e:
        print(f"Error in fusion_info: {e}")
        await update.message.reply_text("⚠️ An error occurred.", parse_mode='HTML')


async def buy_stones_command(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id
        user_data = await user_collection.find_one({'id': user_id})
        balance = user_data.get('balance', 0) if user_data else 0
        current_stones = await get_user_fusion_stones(user_id)
        
        buttons = [
            [
                InlineKeyboardButton("💎 1 Stone - 100 💰", callback_data="buy_stones_1"),
                InlineKeyboardButton("💎 5 Stones - 450 💰", callback_data="buy_stones_5")
            ],
            [
                InlineKeyboardButton("💎 10 Stones - 850 💰", callback_data="buy_stones_10"),
                InlineKeyboardButton("💎 20 Stones - 1600 💰", callback_data="buy_stones_20")
            ],
            [InlineKeyboardButton("❌ Close", callback_data="fuse_cancel")]
        ]
        
        caption = (
            f"💎 <b>FUSION STONE SHOP</b> 💎\n\n"
            f"<b>Your Balance:</b> 💰 {balance:,} coins\n"
            f"<b>Current Stones:</b> 💎 {current_stones}\n\n"
            f"<b>Benefits:</b>\n"
            f"• +15% success rate per stone\n"
            f"• Stack up to 3 stones per fusion\n"
            f"• Permanent - never expire\n\n"
            f"<b>Available Packages:</b>\n"
            f"1 Stone = 100 💰\n"
            f"5 Stones = 450 💰 (Save 50 💰)\n"
            f"10 Stones = 850 💰 (Save 150 💰)\n"
            f"20 Stones = 1,600 💰 (Save 400 💰)"
        )
        
        await update.message.reply_text(
            caption,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode='HTML'
        )
        
    except Exception as e:
        print(f"Error in buy_stones_command: {e}")
        await update.message.reply_text("⚠️ An error occurred.", parse_mode='HTML')


async def fusion_leaderboard(update: Update, context: CallbackContext):
    try:
        pipeline = [
            {'$match': {'fusion_count': {'$exists': True}}},
            {'$sort': {'fusion_count': -1}},
            {'$limit': 10}
        ]
        
        top_users = await user_collection.aggregate(pipeline).to_list(length=None)
        
        if not top_users:
            await update.message.reply_text(
                "📊 <b>Fusion Leaderboard</b>\n\nNo fusion data yet!\nBe the first to fuse characters!",
                parse_mode='HTML'
            )
            return
        
        leaderboard_text = "🏆 <b>TOP FUSION MASTERS</b> 🏆\n\n"
        
        medals = ["🥇", "🥈", "🥉"]
        for idx, user in enumerate(top_users):
            medal = medals[idx] if idx < 3 else f"{idx+1}."
            username = user.get('first_name', 'Unknown')
            fusion_count = user.get('fusion_count', 0)
            success_count = user.get('fusion_success', 0)
            success_rate = (success_count / fusion_count * 100) if fusion_count > 0 else 0
            
            leaderboard_text += (
                f"{medal} <b>{username}</b>\n"
                f"   Fusions: {fusion_count} | Success: {success_rate:.1f}%\n\n"
            )
        
        await update.message.reply_text(leaderboard_text, parse_mode='HTML')
        
    except Exception as e:
        print(f"Error in fusion_leaderboard: {e}")
        await update.message.reply_text("⚠️ An error occurred.", parse_mode='HTML')


async def fusion_history(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id
        user_data = await user_collection.find_one({'id': user_id})
        
        if not user_data:
            await update.message.reply_text("❌ No data found!", parse_mode='HTML')
            return
        
        fusion_count = user_data.get('fusion_count', 0)
        success_count = user_data.get('fusion_success', 0)
        fail_count = fusion_count - success_count
        success_rate = (success_count / fusion_count * 100) if fusion_count > 0 else 0
        
        history = user_data.get('fusion_history', [])
        recent = history[-5:] if history else []
        
        history_text = (
            f"📜 <b>YOUR FUSION HISTORY</b> 📜\n\n"
            f"<b>Statistics:</b>\n"
            f"Total Fusions: {fusion_count}\n"
            f"✅ Success: {success_count}\n"
            f"❌ Failed: {fail_count}\n"
            f"📊 Success Rate: {success_rate:.1f}%\n\n"
        )
        
        if recent:
            history_text += "<b>Recent Fusions:</b>\n"
            for entry in reversed(recent):
                status = "✅" if entry.get('success') else "❌"
                result = entry.get('result_char', 'Lost')
                history_text += f"{status} {result}\n"
        else:
            history_text += "<i>No fusion history yet!</i>"
        
        await update.message.reply_text(history_text, parse_mode='HTML')
        
    except Exception as e:
        print(f"Error in fusion_history: {e}")
        await update.message.reply_text("⚠️ An error occurred.", parse_mode='HTML')


async def track_fusion_stats(user_id: int, success: bool, char1_name: str, char2_name: str, result_name: str = None):
    try:
        fusion_entry = {
            'timestamp': time.time(),
            'success': success,
            'char1': char1_name,
            'char2': char2_name,
            'result_char': result_name if success else 'Failed'
        }
        
        update_data = {
            '$inc': {
                'fusion_count': 1,
                'fusion_success': 1 if success else 0
            },
            '$push': {
                'fusion_history': {
                    '$each': [fusion_entry],
                    '$slice': -50
                }
            }
        }
        
        await user_collection.update_one(
            {'id': user_id},
            update_data,
            upsert=True
        )
        
    except Exception as e:
        print(f"Error tracking fusion stats: {e}")


async def execute_fusion_updated(query, context, user_id: int):
    try:
        fusion_data = pending_fusions.get(user_id)
        if not fusion_data:
            await query.edit_message_text("❌ Session expired.")
            return
        
        char1_id = fusion_data['char1_id']
        char2_id = fusion_data['char2_id']
        stones = fusion_data.get('stones', 0)
        
        characters = await get_user_characters(user_id)
        char1 = next((c for c in characters if c.get('id') == char1_id), None)
        char2 = next((c for c in characters if c.get('id') == char2_id), None)
        
        if not char1 or not char2:
            await query.edit_message_text("❌ Characters not found.")
            return
        
        cost = calculate_fusion_cost(char1.get('rarity'), char2.get('rarity'))
        if not await deduct_balance(user_id, cost):
            await query.edit_message_text("❌ Insufficient balance!")
            return
        
        if stones > 0:
            if not await use_fusion_stones(user_id, stones):
                await user_collection.update_one({'id': user_id}, {'$inc': {'balance': cost}})
                await query.edit_message_text("❌ Failed to use fusion stones!")
                return
        
        if not await remove_characters_from_user(user_id, [char1_id, char2_id]):
            await user_collection.update_one(
                {'id': user_id},
                {'$inc': {'balance': cost, 'fusion_stones': stones}}
            )
            await query.edit_message_text("❌ Error removing characters!")
            return
        
        for frame in FUSION_ANIMATIONS:
            await query.edit_message_text(
                f"⚡ <b>FUSION IN PROGRESS</b> ⚡\n\n{frame}",
                parse_mode='HTML'
            )
            await asyncio.sleep(1.5)
        
        success_rate = calculate_success_rate(char1.get('rarity'), char2.get('rarity'), stones)
        is_success = random.random() < success_rate
        
        if is_success:
            result_rarity = get_fusion_result_rarity(char1.get('rarity'), char2.get('rarity'))
            
            new_chars = await collection.aggregate([
                {'$match': {'rarity': result_rarity}},
                {'$sample': {'size': 1}}
            ]).to_list(length=None)
            
            if new_chars:
                new_char = new_chars[0]
                await add_character_to_user(user_id, new_char)
                
                await track_fusion_stats(
                    user_id, True,
                    char1.get('name'), char2.get('name'),
                    new_char.get('name')
                )
                
                caption = (
                    f"✨ <b>FUSION SUCCESS!</b> ✨\n\n"
                    f"🎉 You created:\n"
                    f"{result_rarity} <b>{new_char.get('name', 'Unknown')}</b>\n\n"
                    f"<b>Anime:</b> {new_char.get('anime', 'Unknown')}\n"
                    f"<b>ID:</b> <code>{new_char.get('id')}</code>\n\n"
                    f"Added to your harem! 💕"
                )
                
                try:
                    await query.message.reply_photo(
                        photo=new_char.get('img_url', ''),
                        caption=caption,
                        parse_mode='HTML'
                    )
                except:
                    await query.message.reply_text(caption, parse_mode='HTML')
                
                await query.edit_message_text("✅ Fusion completed successfully!", parse_mode='HTML')
            else:
                await user_collection.update_one(
                    {'id': user_id},
                    {
                        '$inc': {'balance': cost},
                        '$push': {'characters': {'$each': [char1, char2]}}
                    }
                )
                await query.edit_message_text("❌ No characters available. Refunded!")
        else:
            await track_fusion_stats(
                user_id, False,
                char1.get('name'), char2.get('name')
            )
            
            caption = (
                f"💔 <b>FUSION FAILED!</b> 💔\n\n"
                f"Lost characters:\n"
                f"• {char1.get('rarity')} {char1.get('name')}\n"
                f"• {char2.get('rarity')} {char2.get('name')}\n\n"
                f"Better luck next time! 🍀"
            )
            
            await query.edit_message_text(caption, parse_mode='HTML')
        
        set_cooldown(user_id, 'fusion')
        
        if user_id in pending_fusions:
            del pending_fusions[user_id]
        
    except Exception as e:
        print(f"Error executing fusion: {e}")
        await query.edit_message_text("⚠️ Fusion error occurred!")


application.add_handler(CommandHandler(['fuse', 'fusion'], fusion_start, block=False))
application.add_handler(CommandHandler(['fusioninfo', 'finfo'], fusion_info, block=False))
application.add_handler(CommandHandler(['buystones', 'buystone'], buy_stones_command, block=False))
application.add_handler(CommandHandler(['fusionlb', 'flb'], fusion_leaderboard, block=False))
application.add_handler(CommandHandler(['fusionhistory', 'fhistory'], fusion_history, block=False))
application.add_handler(CallbackQueryHandler(fusion_callback_handler, pattern='^fuse_', block=False))
application.add_handler(CallbackQueryHandler(fusion_callback_handler, pattern='^buy_stones_', block=False))
application.add_handler(CallbackQueryHandler(fusion_callback_handler, pattern='^stone_back$', block=False))