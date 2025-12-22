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

        # Luck System
        if is_streak_bonus:
            target_rarity = "🟡 Legendary"
        else:
            luck = random.randint(1, 100)
            if luck <= 5: target_rarity = "🟡 Legendary"
            elif luck <= 25: target_rarity = "🟣 Rare"
            else: target_rarity = "🟢 Common"

        pipeline = [
            {'$match': {'rarity': target_rarity, 'id': {'$nin': claimed_ids}}},
            {'$sample': {'size': 1}}
        ]
        cursor = collection.aggregate(pipeline)
        result = await cursor.to_list(length=1)

        if not result:
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
        
        last_claimed = user_data.get('last_daily_claim')
        streak = user_data.get('claim_streak', 0)
        
        if last_claimed:
            if last_claimed.tzinfo is None: last_claimed = last_claimed.replace(tzinfo=timezone.utc)
            elapsed = now - last_claimed
            
            if elapsed < timedelta(hours=CONFIG.COOLDOWN_HOURS):
                remaining = timedelta(hours=CONFIG.COOLDOWN_HOURS) - elapsed
                h, r = divmod(int(remaining.total_seconds()), 3600)
                m, s = divmod(r, 60)
                await update.message.reply_text(f"🕒 <b>Sʟᴏᴡ Dᴏᴡɴ Bᴜᴅᴅʏ!</b>\n\n⌛ Nᴇxᴛ ᴄʟᴀɪᴍ ɪɴ: <code>{h}ʜ {m}ᴍ {s}s</code>", parse_mode=ParseMode.HTML)
                return
            
            if elapsed > timedelta(hours=48): streak = 0
        
        streak += 1
        is_bonus = (streak == 7)
        if streak > 7: streak = 1

        char = await get_pro_character(user.id, is_streak_bonus=is_bonus)
        if not char:
            await update.message.reply_text("❗ <b>Nᴏ ᴍᴏʀᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs ʟᴇғᴛ!</b>")
            return

        await user_collection.update_one(
            {'id': user.id},
            {
                '$push': {'characters': char},
                '$set': {'last_daily_claim': now, 'claim_streak': streak, 'first_name': user.first_name}
            },
            upsert=True
        )

        # --- 🎯 FIXED BUTTON FORMAT ---
        # Isse click karte hi @botname collection.{id} likha aayega
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎒 Mʏ Cᴏʟʟᴇᴄᴛɪᴏɴ", switch_inline_query_current_chat=f"collection.{user.id}")],
            [InlineKeyboardButton("🐉 Sᴜᴘᴘᴏʀᴛ", url=CONFIG.SUPPORT_LINK)]
        ])

        streak_bar = "🔥" * streak + "⏳" * (7 - streak)
        caption = (
            f"<b>🎊 Dᴀɪʟʏ Cʟᴀɪᴍ Sᴜᴄᴄᴇssғᴜʟ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Pʟᴀʏᴇʀ:</b> <a href='tg://user?id={user.id}'>{user.first_name}</a>\n"
            f"🎴 <b>Nᴀᴍᴇ:</b> <code>{char.get('name')}</code>\n"
            f"🎬 <b>Aɴɪᴍᴇ:</b> <code>{char.get('anime')}</code>\n"
            f"⭐ <b>Rᴀʀɪᴛʏ:</b> {char.get('rarity')}\n"
            f"🆔 <b>ID:</b> <code>{char.get('id')}</code>\n\n"
            f"📈 <b>Sᴛʀᴇᴀᴋ:</b> {streak}/7\n"
            f"{streak_bar}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎁 <i>Cᴏᴍᴇ ʙᴀᴄᴋ ᴛᴏᴍᴏʀʀᴏᴡ ғᴏʀ sᴛʀᴇᴀᴋ ʙᴏɴᴜs!</i>"
        )

        await update.message.reply_photo(
            photo=char.get('img_url'),
            caption=caption,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )

        # --- 📜 LOG SYSTEM WITH ALL DETAILS ---
        log_caption = (
            f"<b>#DAILY_CLAIM_LOG</b>\n\n"
            f"👤 <b>Usᴇʀ:</b> {user.first_name} (<code>{user.id}</code>)\n"
            f"🎴 <b>Cʜᴀʀᴀᴄᴛᴇʀ:</b> {char.get('name')}\n"
            f"🎬 <b>Aɴɪᴍᴇ:</b> {char.get('anime')}\n"
            f"⭐ <b>Rᴀʀɪᴛʏ:</b> {char.get('rarity')}\n"
            f"🆔 <b>ID:</b> <code>{char.get('id')}</code>\n"
            f"🔥 <b>Sᴛʀᴇᴀᴋ:</b> {streak}\n"
            f"📍 <b>Cʜᴀᴛ:</b> {update.effective_chat.title or 'Pʀɪᴠᴀᴛᴇ'}"
        )
        
        await context.bot.send_photo(
            chat_id=CONFIG.LOG_GROUP_ID,
            photo=char.get('img_url'),
            caption=log_caption,
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        await update.message.reply_text(f"⚠️ <b>Eʀʀᴏʀ:</b> <code>{e}</code>", parse_mode=ParseMode.HTML)
    finally:
        claim_lock.discard(user.id)

application.add_handler(CommandHandler(['hclaim', 'claim'], hclaim, block=False))
