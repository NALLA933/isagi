import asyncio
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Tuple, Any
from enum import Enum
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, User
from telegram.ext import CommandHandler, CallbackContext, ContextTypes
from telegram.error import TelegramError, BadRequest, Forbidden
from shivu import application, user_collection, collection, LOGGER
import random
from functools import wraps
from collections import defaultdict

class ClaimStatus(Enum):
    SUCCESS = "success"
    COOLDOWN = "cooldown"
    NO_BIO = "no_bio"
    NO_CHARACTERS = "no_characters"
    ERROR = "error"
    LOCKED = "locked"
    WRONG_CHAT = "wrong_chat"

class RarityTier(Enum):
    SPECIAL = ("💮 Special Edition", 100)
    NEON = ("💫 Neon", 75)
    MANGA = ("✨ Manga", 50)
    
    @property
    def display(self) -> str:
        return self.value[0]
    
    @property
    def weight(self) -> int:
        return self.value[1]

@dataclass
class ClaimConfig:
    MAIN_GROUP_ID: int = -1003100468240
    MAIN_GROUP_LINK: str = "https://t.me/PICK_X_SUPPORT"
    BOT_USERNAME: str = "@siyaprobot"
    CLAIM_COOLDOWN_DAYS: int = 7
    MAX_CONCURRENT_CLAIMS: int = 3
    CACHE_TTL_SECONDS: int = 300
    BIO_CHECK_TIMEOUT: int = 5
    
    @property
    def weekly_rarities(self) -> List[str]:
        return [tier.display for tier in RarityTier]
    
    @property
    def rarity_weights(self) -> Dict[str, int]:
        return {tier.display: tier.weight for tier in RarityTier}

@dataclass
class UserClaimData:
    user_id: int
    first_name: str
    username: Optional[str]
    last_weekly_claim: Optional[datetime]
    total_weekly_claims: int = 0
    characters: List[Dict] = field(default_factory=list)
    bio_verified_at: Optional[datetime] = None
    
    @property
    def has_claimed_today(self) -> bool:
        if not self.last_weekly_claim:
            return False
        return datetime.utcnow() - self.last_weekly_claim < timedelta(days=7)
    
    @property
    def next_claim_time(self) -> Optional[datetime]:
        if not self.last_weekly_claim:
            return None
        return self.last_weekly_claim + timedelta(days=7)

@dataclass
class ClaimResult:
    status: ClaimStatus
    message: str
    character: Optional[Dict] = None
    time_remaining: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class BioCacheManager:
    def __init__(self, ttl: int = 300):
        self.cache: Dict[int, Tuple[bool, datetime]] = {}
        self.ttl = ttl
    
    def get(self, user_id: int) -> Optional[bool]:
        if user_id in self.cache:
            verified, timestamp = self.cache[user_id]
            if datetime.utcnow() - timestamp < timedelta(seconds=self.ttl):
                return verified
            del self.cache[user_id]
        return None
    
    def set(self, user_id: int, verified: bool):
        self.cache[user_id] = (verified, datetime.utcnow())
    
    def invalidate(self, user_id: int):
        self.cache.pop(user_id, None)
    
    def cleanup(self):
        now = datetime.utcnow()
        expired = [
            uid for uid, (_, ts) in self.cache.items()
            if now - ts >= timedelta(seconds=self.ttl)
        ]
        for uid in expired:
            del self.cache[uid]

class RateLimiter:
    def __init__(self, max_calls: int, time_window: int = 60):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls: Dict[int, List[datetime]] = defaultdict(list)
    
    def is_allowed(self, user_id: int) -> Tuple[bool, Optional[int]]:
        now = datetime.utcnow()
        user_calls = self.calls[user_id]
        
        user_calls[:] = [call for call in user_calls if now - call < timedelta(seconds=self.time_window)]
        
        if len(user_calls) >= self.max_calls:
            oldest_call = min(user_calls)
            wait_time = int((oldest_call + timedelta(seconds=self.time_window) - now).total_seconds())
            return False, wait_time
        
        user_calls.append(now)
        return True, None

def async_retry(max_attempts: int = 3, delay: float = 1.0):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    LOGGER.warning(f"Retry {attempt + 1}/{max_attempts} for {func.__name__}: {e}")
                    await asyncio.sleep(delay * (attempt + 1))
            return None
        return wrapper
    return decorator

class WeeklyClaimSystem:
    def __init__(self, config: ClaimConfig):
        self.config = config
        self.claim_lock: Dict[int, asyncio.Lock] = {}
        self.bio_cache = BioCacheManager(config.CACHE_TTL_SECONDS)
        self.rate_limiter = RateLimiter(max_calls=5, time_window=60)
        self.stats = defaultdict(int)
        asyncio.create_task(self._periodic_cleanup())
    
    async def _periodic_cleanup(self):
        while True:
            await asyncio.sleep(300)
            self.bio_cache.cleanup()
            inactive_locks = [
                uid for uid, lock in self.claim_lock.items()
                if not lock.locked()
            ]
            for uid in inactive_locks:
                del self.claim_lock[uid]
    
    def _get_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self.claim_lock:
            self.claim_lock[user_id] = asyncio.Lock()
        return self.claim_lock[user_id]
    
    async def format_time_delta(self, delta: timedelta) -> str:
        seconds = int(delta.total_seconds())
        if seconds < 0:
            return "0s"
        
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}ᴅ")
        if hours > 0 or days > 0:
            parts.append(f"{hours}ʜ")
        if minutes > 0 or hours > 0 or days > 0:
            parts.append(f"{minutes}ᴍ")
        if not parts or (days == 0 and hours == 0):
            parts.append(f"{seconds}s")
        
        return " ".join(parts[:3])
    
    @async_retry(max_attempts=3, delay=1.0)
    async def check_user_bio(self, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
        cached = self.bio_cache.get(user_id)
        if cached is not None:
            return cached
        
        try:
            user = await asyncio.wait_for(
                context.bot.get_chat(user_id),
                timeout=self.config.BIO_CHECK_TIMEOUT
            )
            bio = (user.bio or "").lower()
            has_bot = self.config.BOT_USERNAME.lower() in bio
            
            self.bio_cache.set(user_id, has_bot)
            self.stats['bio_checks'] += 1
            
            return has_bot
        except asyncio.TimeoutError:
            LOGGER.warning(f"Bio check timeout for user {user_id}")
            return False
        except (BadRequest, Forbidden) as e:
            LOGGER.error(f"Bio check failed for user {user_id}: {e}")
            return False
        except Exception as e:
            LOGGER.error(f"Unexpected bio check error for user {user_id}: {e}")
            return False
    
    async def fetch_user_data(self, user_id: int, first_name: str, username: Optional[str]) -> UserClaimData:
        user_doc = await user_collection.find_one({'id': user_id})
        
        if not user_doc:
            data = UserClaimData(
                user_id=user_id,
                first_name=first_name,
                username=username,
                last_weekly_claim=None
            )
            await user_collection.insert_one({
                'id': user_id,
                'first_name': first_name,
                'username': username,
                'characters': [],
                'last_weekly_claim': None,
                'total_weekly_claims': 0
            })
            return data
        
        return UserClaimData(
            user_id=user_id,
            first_name=first_name,
            username=username,
            last_weekly_claim=user_doc.get('last_weekly_claim'),
            total_weekly_claims=user_doc.get('total_weekly_claims', 0),
            characters=user_doc.get('characters', []),
            bio_verified_at=user_doc.get('bio_verified_at')
        )
    
    async def get_weighted_character(self, user_id: int) -> Optional[Dict]:
        try:
            user_data = await user_collection.find_one({'id': user_id})
            claimed_ids = {c.get('id') for c in user_data.get('characters', [])} if user_data else set()
            
            available_by_rarity = {tier.display: [] for tier in RarityTier}
            
            async for char in collection.find({'rarity': {'$in': self.config.weekly_rarities}}):
                if char.get('id') not in claimed_ids:
                    rarity = char.get('rarity')
                    if rarity in available_by_rarity:
                        available_by_rarity[rarity].append(char)
            
            all_available = []
            weights = []
            
            for tier in RarityTier:
                chars = available_by_rarity[tier.display]
                for char in chars:
                    all_available.append(char)
                    weights.append(tier.weight)
            
            if not all_available:
                return None
            
            selected = random.choices(all_available, weights=weights, k=1)[0]
            self.stats['characters_claimed'] += 1
            
            return selected
        except Exception as e:
            LOGGER.error(f"Character fetch error: {e}")
            return None
    
    async def validate_claim(self, user_data: UserClaimData) -> ClaimResult:
        if user_data.has_claimed_today:
            remaining = user_data.next_claim_time - datetime.utcnow()
            formatted_time = await self.format_time_delta(remaining)
            return ClaimResult(
                status=ClaimStatus.COOLDOWN,
                message=f"⏰ ᴡᴇᴇᴋʟʏ ᴄʟᴀɪᴍ ᴀʟʀᴇᴀᴅʏ ᴜsᴇᴅ\n⏳ ɴᴇxᴛ ᴄʟᴀɪᴍ ɪɴ: `{formatted_time}`",
                time_remaining=formatted_time,
                metadata={'next_claim': user_data.next_claim_time.isoformat()}
            )
        
        return ClaimResult(status=ClaimStatus.SUCCESS, message="")
    
    @async_retry(max_attempts=2, delay=0.5)
    async def process_claim(self, user_data: UserClaimData, character: Dict) -> bool:
        try:
            result = await user_collection.update_one(
                {'id': user_data.user_id},
                {
                    '$push': {'characters': character},
                    '$set': {
                        'last_weekly_claim': datetime.utcnow(),
                        'first_name': user_data.first_name,
                        'username': user_data.username,
                        'bio_verified_at': datetime.utcnow()
                    },
                    '$inc': {'total_weekly_claims': 1}
                }
            )
            return result.modified_count > 0
        except Exception as e:
            LOGGER.error(f"Database update error: {e}")
            return False
    
    def generate_character_caption(self, user_data: UserClaimData, character: Dict) -> str:
        event = f"\n🎪 ᴇᴠᴇɴᴛ: <b>{character['event']['name']}</b>" if character.get('event', {}).get('name') else ""
        origin = f"\n🌍 ᴏʀɪɢɪɴ: <b>{character['origin']}</b>" if character.get('origin') else ""
        abilities = f"\n⚔️ ᴀʙɪʟɪᴛɪᴇs: <b>{character['abilities']}</b>" if character.get('abilities') else ""
        description = f"\n📝 ᴅᴇsᴄʀɪᴘᴛɪᴏɴ: <b>{character['description']}</b>" if character.get('description') else ""
        
        claim_count = user_data.total_weekly_claims + 1
        streak_emoji = "🔥" if claim_count >= 5 else "✨"
        
        return f"""🎁 ᴡᴇᴇᴋʟʏ ᴄʟᴀɪᴍ sᴜᴄᴄᴇss!
💎 ᴄᴏɴɢʀᴀᴛs <a href='tg://user?id={user_data.user_id}'>{user_data.first_name}</a>

🎴 ɴᴀᴍᴇ: <b>{character.get('name', 'Unknown')}</b>
⭐ ʀᴀʀɪᴛʏ: <b>{character.get('rarity', 'Unknown')}</b>
🎯 ᴀɴɪᴍᴇ: <b>{character.get('anime', 'Unknown')}</b>
🆔 ɪᴅ: <code>{character.get('id', 'N/A')}</code>{event}{origin}{abilities}{description}

{streak_emoji} ᴛᴏᴛᴀʟ ᴡᴇᴇᴋʟʏ ᴄʟᴀɪᴍs: <b>{claim_count}</b>
⏰ ɴᴇxᴛ ᴄʟᴀɪᴍ: <b>7 ᴅᴀʏs</b>
⚠️ ᴋᴇᴇᴘ <code>{self.config.BOT_USERNAME}</code> ɪɴ ʏᴏᴜʀ ʙɪᴏ!"""
    
    def generate_help_message(self) -> Tuple[str, InlineKeyboardMarkup]:
        rarities = "\n".join([f"  • {tier.display}" for tier in RarityTier])
        
        message = f"""❌ ᴡᴇᴇᴋʟʏ ᴄʟᴀɪᴍ ʀᴇǫᴜɪʀᴇs {self.config.BOT_USERNAME} ɪɴ ʏᴏᴜʀ ʙɪᴏ!

📝 <b>ʜᴏᴡ ᴛᴏ ᴄʟᴀɪᴍ:</b>
1️⃣ ᴀᴅᴅ <code>{self.config.BOT_USERNAME}</code> ᴛᴏ ʏᴏᴜʀ ᴛᴇʟᴇɢʀᴀᴍ ʙɪᴏ
2️⃣ ᴜsᴇ /wclaim ᴄᴏᴍᴍᴀɴᴅ ʜᴇʀᴇ
3️⃣ ᴋᴇᴇᴘ ɪᴛ ɪɴ ʏᴏᴜʀ ʙɪᴏ ғᴏʀ 7 ᴅᴀʏs

💎 <b>ʀᴇᴡᴀʀᴅs:</b>
{rarities}

⏰ <b>ᴄᴏᴏʟᴅᴏᴡɴ:</b> 7 ᴅᴀʏs
🎯 <b>ʟᴏᴄᴀᴛɪᴏɴ:</b> ᴍᴀɪɴ ɢʀᴏᴜᴘ ᴏɴʟʏ"""
        
        keyboard = [
            [InlineKeyboardButton("📖 ʜᴏᴡ ᴛᴏ ᴀᴅᴅ ʙɪᴏ", url="https://telegram.org/blog/edit-profile")],
            [InlineKeyboardButton("💬 sᴜᴘᴘᴏʀᴛ", url=self.config.MAIN_GROUP_LINK)]
        ]
        
        return message, InlineKeyboardMarkup(keyboard)
    
    async def handle_weekly_claim(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.effective_user:
            return
        
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        first_name = update.effective_user.first_name
        username = update.effective_user.username
        
        if chat_id != self.config.MAIN_GROUP_ID:
            keyboard = [[InlineKeyboardButton("🔗 ᴊᴏɪɴ ᴍᴀɪɴ ɢʀᴏᴜᴘ", url=self.config.MAIN_GROUP_LINK)]]
            await update.message.reply_text(
                "⚠️ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴏɴʟʏ ᴡᴏʀᴋs ɪɴ ᴛʜᴇ ᴍᴀɪɴ ɢʀᴏᴜᴘ!\n\n"
                "📍 ᴊᴏɪɴ ᴏᴜʀ ᴍᴀɪɴ ɢʀᴏᴜᴘ ᴛᴏ ᴜsᴇ ᴛʜɪs ғᴇᴀᴛᴜʀᴇ.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        allowed, wait_time = self.rate_limiter.is_allowed(user_id)
        if not allowed:
            await update.message.reply_text(
                f"⚠️ ʀᴀᴛᴇ ʟɪᴍɪᴛ ᴇxᴄᴇᴇᴅᴇᴅ!\n"
                f"⏳ ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ {wait_time} sᴇᴄᴏɴᴅs."
            )
            return
        
        lock = self._get_lock(user_id)
        
        if lock.locked():
            await update.message.reply_text("⏳ ᴄʟᴀɪᴍ ɪɴ ᴘʀᴏɢʀᴇss, ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...")
            return
        
        async with lock:
            try:
                has_bot_in_bio = await self.check_user_bio(user_id, context)
                
                if not has_bot_in_bio:
                    message, keyboard = self.generate_help_message()
                    await update.message.reply_text(message, parse_mode='HTML', reply_markup=keyboard)
                    return
                
                user_data = await self.fetch_user_data(user_id, first_name, username)
                validation = await self.validate_claim(user_data)
                
                if validation.status != ClaimStatus.SUCCESS:
                    await update.message.reply_text(validation.message, parse_mode='Markdown')
                    return
                
                character = await self.get_weighted_character(user_id)
                
                if not character:
                    await update.message.reply_text(
                        "❌ ɴᴏ ɴᴇᴡ ᴡᴇᴇᴋʟʏ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴀᴠᴀɪʟᴀʙʟᴇ\n"
                        "💫 ʏᴏᴜ'ᴠᴇ ᴄᴏʟʟᴇᴄᴛᴇᴅ ᴀʟʟ ᴡᴇᴇᴋʟʏ ᴄʜᴀʀᴀᴄᴛᴇʀs!"
                    )
                    return
                
                success = await self.process_claim(user_data, character)
                
                if not success:
                    await update.message.reply_text("❌ ғᴀɪʟᴇᴅ ᴛᴏ ᴘʀᴏᴄᴇss ᴄʟᴀɪᴍ. ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ!")
                    return
                
                caption = self.generate_character_caption(user_data, character)
                
                await update.message.reply_photo(
                    photo=character.get('img_url', 'https://i.imgur.com/placeholder.png'),
                    caption=caption,
                    parse_mode='HTML'
                )
                
                self.stats['successful_claims'] += 1
                
            except TelegramError as e:
                LOGGER.error(f"Telegram error in weekly claim: {e}")
                await update.message.reply_text("❌ ᴛᴇʟᴇɢʀᴀᴍ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ. ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ!")
            except Exception as e:
                LOGGER.error(f"Unexpected error in weekly claim: {e}", exc_info=True)
                await update.message.reply_text("❌ ᴀɴ ᴜɴᴇxᴘᴇᴄᴛᴇᴅ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ!")

config = ClaimConfig()
weekly_claim_system = WeeklyClaimSystem(config)

application.add_handler(
    CommandHandler(['wclaim', 'weeklyclaim', 'wc'], weekly_claim_system.handle_weekly_claim, block=False)
)