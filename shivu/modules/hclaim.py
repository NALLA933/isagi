import random
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext
from telegram.constants import ParseMode

from shivu import application, user_collection, collection

@dataclass(frozen=True)
class ClaimConfig:
    LOG_GROUP_ID: int = -1002956939145
    SUPPORT_LINK: str = "https://t.me/THE_DRAGON_SUPPORT"
    COOLDOWN_HOURS: int = 24

CONFIG = ClaimConfig()
claim_lock = set()

async def get_pro_character(user_id: int, is_streak_bonus: bool = False) -> dict | None:
    try:
        user_data = await user_collection.find_one({'id': user_id}, {'characters.id': 1})
        claimed_ids = [c['id'] for c in user_data.get('characters', [])] if user_data else []

        # --- LUCK SYSTEM (Idea 2) ---
        if is_streak_bonus:
            target_rarity = "🟡 Legendary" # 7th day bonus
        else:
            luck = random.randint(1, 100)
            if luck <= 5: target_rarity = "🟡 Legendary"
            elif luck <= 30: target_rarity = "🟣 Rare"
            else: target_rarity = "🟢 Common"

        # --- MONGODB AGGREGATION (Idea 1) ---
        pipeline = [
            {'$match': {'rarity': target_rarity, 'id': {'$nin': claimed_ids}}},
            {'$sample': {'size': 1}}
        ]
        
        cursor = collection.aggregate(pipeline)
        result = await cursor.to_list(length=1)

        if not result: # Fallback
            cursor = collection.aggregate([{'$match': {'id': {'$nin': claimed_ids}}}, {'$sample': {'size': 1}}])
            result = await cursor.to_list(length=1)

        return result[0] if result else None
    except Exception as e:
        logging.error(f"Fetch error: {e}")
        return None

async def hclaim(update: Update, context: CallbackContext):
    user = update.effective_user
    if user.id in claim_lock: return
    claim_lock.add(user.id)
    
    try:
        now = datetime.now(timezone.utc)
        user_data = await user_collection.find_one({'id': user.id}) or {}
        
        # --- COOLDOWN & STREAK LOGIC (Idea 3) ---
        last_claimed = user_data.get('last_daily_claim')
        streak = user_data.get('claim_streak', 0)
        
        if last_claimed:
            if last_claimed.tzinfo is None: last_claimed = last_claimed.replace(tzinfo=timezone.utc)
            elapsed = now - last_claimed
            
            if elapsed < timedelta(hours=CONFIG.COOLDOWN_HOURS):
                remaining = timedelta(hours=CONFIG.COOLDOWN_HOURS) - elapsed
                h, r = divmod(int(remaining.total_seconds()), 3600)
                m, s = divmod(r, 60)
                await update.message.reply_text(f"⏰ <b>Wait!</b>\nNext claim in: <code>{h}h {m}m {s}s</code>", parse_mode=ParseMode.HTML)
                return
            
            # Agar 48 hours se zyada ho gaye toh streak reset
            if elapsed > timedelta(hours=48):
                streak = 0
        
        streak += 1
        is_bonus = (streak == 7)
        if streak > 7: streak = 1 # Reset streak after bonus

        char = await get_pro_character(user.id, is_streak_bonus=is_bonus)
        if not char:
            await update.message.reply_text("❌ No characters left to claim!")
            return

        # --- DATABASE UPDATE ---
        await user_collection.update_one(
            {'id': user.id},
            {
                '$push': {'characters': char},
                '$set': {
                    'last_daily_claim': now,
                    'claim_streak': streak,
                    'first_name': user.first_name
                }
            },
            upsert=True
        )

        # --- UI/UX BUTTONS (Idea 5) ---
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎒 My Collection", switch_inline_query_current_chat="/collection")],
            [InlineKeyboardButton("🌍 Support Group", url=CONFIG.SUPPORT_LINK)]
        ])

        streak_msg = f"🔥 <b>Streak:</b> {streak}/7" + (" (BONUS! 🎁)" if is_bonus else "")
        caption = (
            f"<b>🎊 DAILY CLAIM SUCCESS</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Player:</b> <a href='tg://user?id={user.id}'>{user.first_name}</a>\n"
            f"🎴 <b>Name:</b> {char.get('name')}\n"
            f"⭐ <b>Rarity:</b> {char.get('rarity')}\n"
            f"🆔 <b>ID:</b> <code>{char.get('id')}</code>\n"
            f"{streak_msg}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✨ Come back tomorrow for more!"
        )

        await update.message.reply_photo(
            photo=char.get('img_url'),
            caption=caption,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )

        # --- LOG SYSTEM ---
        log_msg = f"#CLAIM\n👤 {user.first_name}\n🎴 {char.get('name')}\n⭐ {char.get('rarity')}\n🔥 Streak: {streak}"
        await context.bot.send_message(chat_id=CONFIG.LOG_GROUP_ID, text=log_msg)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        claim_lock.discard(user.id)

application.add_handler(CommandHandler(['hclaim', 'claim'], hclaim, block=False))
