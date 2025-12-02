import asyncio
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext
from shivu import application, user_collection, collection, LOGGER
import random

@dataclass
class ClaimConfig:
    MAIN_GROUP_ID: int = -1003100468240
    MAIN_GROUP_LINK: str = "https://t.me/PICK_X_SUPPORT"
    BOT_USERNAME: str = "@siyaprobot"
    WEEKLY_RARITIES: List[str] = field(default_factory=lambda: [
        "💮 Special Edition",
        "💫 Neon",
        "✨ Manga"
    ])
    CLAIM_COOLDOWN_DAYS: int = 7

@dataclass
class ClaimResponse:
    success: bool
    message: str
    character: Optional[Dict] = None
    time_remaining: Optional[str] = None

class WeeklyClaimSystem:
    def __init__(self, config: ClaimConfig):
        self.config = config
        self.claim_lock: Dict[int, bool] = {}

    async def format_time_delta(self, delta: timedelta) -> str:
        seconds = delta.total_seconds()
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if days > 0:
            return f"{int(days)}ᴅ {int(hours)}ʜ {int(minutes)}ᴍ"
        return f"{int(hours)}ʜ {int(minutes)}ᴍ {int(seconds)}s"

    async def check_user_bio(self, user_id: int, context: CallbackContext) -> bool:
        try:
            user = await context.bot.get_chat(user_id)
            bio = user.bio or ""
            return self.config.BOT_USERNAME.lower() in bio.lower()
        except Exception as e:
            LOGGER.error(f"[WCLAIM] Bio check error: {e}")
            return False

    async def get_unique_weekly_character(self, user_id: int) -> Optional[Dict]:
        try:
            user_data = await user_collection.find_one({'id': user_id})
            claimed_ids = [c.get('id') for c in user_data.get('characters', [])] if user_data else []

            available = []
            async for char in collection.find({'rarity': {'$in': self.config.WEEKLY_RARITIES}}):
                if char.get('id') not in claimed_ids:
                    available.append(char)

            return random.choice(available) if available else None
        except Exception as e:
            LOGGER.error(f"[WCLAIM] Character fetch error: {e}")
            return None

    async def validate_claim(self, user_id: int, user_data: Optional[Dict]) -> ClaimResponse:
        if not user_data:
            return ClaimResponse(
                success=False,
                message="❌ ᴜsᴇʀ ᴅᴀᴛᴀ ɴᴏᴛ ғᴏᴜɴᴅ. ᴜsᴇ /start ғɪʀsᴛ"
            )

        last_weekly_claim = user_data.get('last_weekly_claim')
        
        if last_weekly_claim and isinstance(last_weekly_claim, datetime):
            time_since_claim = datetime.utcnow() - last_weekly_claim
            if time_since_claim < timedelta(days=self.config.CLAIM_COOLDOWN_DAYS):
                remaining = timedelta(days=self.config.CLAIM_COOLDOWN_DAYS) - time_since_claim
                formatted_time = await self.format_time_delta(remaining)
                return ClaimResponse(
                    success=False,
                    message=f"⏰ ᴡᴇᴇᴋʟʏ ᴄʟᴀɪᴍ ᴀʟʀᴇᴀᴅʏ ᴜsᴇᴅ\n⏳ ɴᴇxᴛ ᴄʟᴀɪᴍ ɪɴ: `{formatted_time}`",
                    time_remaining=formatted_time
                )

        return ClaimResponse(success=True, message="")

    async def process_claim(self, user_id: int, first_name: str, username: str, character: Dict) -> bool:
        try:
            await user_collection.update_one(
                {'id': user_id},
                {
                    '$push': {'characters': character},
                    '$set': {
                        'last_weekly_claim': datetime.utcnow(),
                        'first_name': first_name,
                        'username': username
                    }
                }
            )
            return True
        except Exception as e:
            LOGGER.error(f"[WCLAIM] Database update error: {e}")
            return False

    def generate_character_caption(self, user_id: int, first_name: str, character: Dict) -> str:
        event = f"\n🎪 ᴇᴠᴇɴᴛ: <b>{character['event']['name']}</b>" if character.get('event', {}).get('name') else ""
        origin = f"\n🌍 ᴏʀɪɢɪɴ: <b>{character['origin']}</b>" if character.get('origin') else ""
        abilities = f"\n⚔️ ᴀʙɪʟɪᴛɪᴇs: <b>{character['abilities']}</b>" if character.get('abilities') else ""
        description = f"\n📝 ᴅᴇsᴄʀɪᴘᴛɪᴏɴ: <b>{character['description']}</b>" if character.get('description') else ""

        return f"""🎁 ᴡᴇᴇᴋʟʏ ᴄʟᴀɪᴍ sᴜᴄᴄᴇss!
💎 ᴄᴏɴɢʀᴀᴛs <a href='tg://user?id={user_id}'>{first_name}</a>

🎴 ɴᴀᴍᴇ: <b>{character.get('name', 'Unknown')}</b>
⭐ ʀᴀʀɪᴛʏ: <b>{character.get('rarity', 'Unknown')}</b>
🎯 ᴀɴɪᴍᴇ: <b>{character.get('anime', 'Unknown')}</b>
🆔 ɪᴅ: <code>{character.get('id', 'N/A')}</code>{event}{origin}{abilities}{description}

✨ ᴄᴏᴍᴇ ʙᴀᴄᴋ ɪɴ 7 ᴅᴀʏs!
⚠️ ᴋᴇᴇᴘ {self.config.BOT_USERNAME} ɪɴ ʏᴏᴜʀ ʙɪᴏ ᴛᴏ ᴄʟᴀɪᴍ ɴᴇxᴛ ᴡᴇᴇᴋ"""

    async def handle_weekly_claim(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id

        if chat_id != self.config.MAIN_GROUP_ID:
            keyboard = [[InlineKeyboardButton("🔗 ᴊᴏɪɴ ᴍᴀɪɴ ɢʀᴏᴜᴘ", url=self.config.MAIN_GROUP_LINK)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "⚠️ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴄᴀɴ ᴏɴʟʏ ʙᴇ ᴜsᴇᴅ ɪɴ ᴛʜᴇ ᴍᴀɪɴ ɢʀᴏᴜᴘ!\n\n"
                "📍 ᴘʟᴇᴀsᴇ ᴊᴏɪɴ ᴏᴜʀ ᴍᴀɪɴ ɢʀᴏᴜᴘ ᴛᴏ ᴜsᴇ ᴛʜɪs ғᴇᴀᴛᴜʀᴇ.",
                reply_markup=reply_markup
            )
            return

        user_id = update.effective_user.id
        first_name = update.effective_user.first_name
        username = update.effective_user.username

        if user_id in self.claim_lock:
            await update.message.reply_text("⏳ ᴄʟᴀɪᴍ ɪɴ ᴘʀᴏɢʀᴇss, ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...")
            return

        self.claim_lock[user_id] = True

        try:
            has_bot_in_bio = await self.check_user_bio(user_id, context)
            
            if not has_bot_in_bio:
                keyboard = [[InlineKeyboardButton("📖 ʜᴏᴡ ᴛᴏ ᴀᴅᴅ ʙɪᴏ", url="https://t.me/telegram/153")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"❌ ᴡᴇᴇᴋʟʏ ᴄʟᴀɪᴍ ʀᴇǫᴜɪʀᴇs {self.config.BOT_USERNAME} ɪɴ ʏᴏᴜʀ ʙɪᴏ!\n\n"
                    f"📝 sᴛᴇᴘs ᴛᴏ ᴄʟᴀɪᴍ:\n"
                    f"1️⃣ ᴀᴅᴅ <code>{self.config.BOT_USERNAME}</code> ᴛᴏ ʏᴏᴜʀ ᴛᴇʟᴇɢʀᴀᴍ ʙɪᴏ\n"
                    f"2️⃣ ᴜsᴇ /wclaim ᴄᴏᴍᴍᴀɴᴅ\n"
                    f"3️⃣ ᴋᴇᴇᴘ ɪᴛ ɪɴ ʏᴏᴜʀ ʙɪᴏ ғᴏʀ 7 ᴅᴀʏs\n\n"
                    f"💎 ʀᴇᴡᴀʀᴅs: {', '.join(self.config.WEEKLY_RARITIES)}",
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
                return

            user_data = await user_collection.find_one({'id': user_id})
            
            if not user_data:
                user_data = {
                    'id': user_id,
                    'first_name': first_name,
                    'username': username,
                    'characters': [],
                    'last_weekly_claim': None
                }
                await user_collection.insert_one(user_data)

            validation = await self.validate_claim(user_id, user_data)
            
            if not validation.success:
                await update.message.reply_text(validation.message, parse_mode='Markdown')
                return

            character = await self.get_unique_weekly_character(user_id)
            
            if not character:
                await update.message.reply_text(
                    "❌ ɴᴏ ɴᴇᴡ ᴡᴇᴇᴋʟʏ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴀᴠᴀɪʟᴀʙʟᴇ\n"
                    "💫 ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ!"
                )
                return

            success = await self.process_claim(user_id, first_name, username, character)
            
            if not success:
                await update.message.reply_text("❌ ғᴀɪʟᴇᴅ ᴛᴏ ᴘʀᴏᴄᴇss ᴄʟᴀɪᴍ. ᴛʀʏ ᴀɢᴀɪɴ!")
                return

            caption = self.generate_character_caption(user_id, first_name, character)
            
            await update.message.reply_photo(
                photo=character.get('img_url', 'https://i.imgur.com/placeholder.png'),
                caption=caption,
                parse_mode='HTML'
            )

        except Exception as e:
            LOGGER.error(f"[WCLAIM] Unexpected error: {e}")
            await update.message.reply_text("❌ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ. ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ!")
        finally:
            self.claim_lock.pop(user_id, None)

config = ClaimConfig()
weekly_claim_system = WeeklyClaimSystem(config)

application.add_handler(
    CommandHandler(['wclaim', 'weeklyclaim'], weekly_claim_system.handle_weekly_claim, block=False)
)