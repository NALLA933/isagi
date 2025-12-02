import asyncio
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Any, Set
from enum import IntEnum
import random
from functools import lru_cache, wraps
from collections import deque
import time
import hashlib

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from telegram.error import TelegramError, BadRequest, Forbidden, TimedOut, NetworkError
from telegram.constants import ParseMode, ChatAction
from shivu import application, user_collection, collection, LOGGER

import motor.motor_asyncio
from pymongo import UpdateOne, ReturnDocument

class ClaimStatus(IntEnum):
    SUCCESS = 0
    COOLDOWN = 1
    NO_BIO = 2
    NO_CHARACTERS = 3
    ERROR = 4
    RATE_LIMIT = 5
    WRONG_CHAT = 6

class RarityTier(IntEnum):
    SPECIAL = 100
    NEON = 75
    MANGA = 50
    
    @staticmethod
    @lru_cache(maxsize=1)
    def get_display_map() -> Dict[int, str]:
        return {
            RarityTier.SPECIAL: "💮 Special Edition",
            RarityTier.NEON: "💫 Neon",
            RarityTier.MANGA: "✨ Manga"
        }
    
    @staticmethod
    @lru_cache(maxsize=1)
    def get_all_displays() -> List[str]:
        return list(RarityTier.get_display_map().values())

@dataclass(frozen=True, slots=True)
class ClaimConfig:
    MAIN_GROUP_ID: int = -1003100468240
    MAIN_GROUP_LINK: str = "https://t.me/PICK_X_SUPPORT"
    BOT_USERNAME: str = "@siyaprobot"
    CLAIM_COOLDOWN_SECONDS: int = 604800
    BIO_CACHE_TTL: int = 180
    CHARACTER_CACHE_TTL: int = 300
    MAX_RETRIES: int = 2
    TIMEOUT: int = 3
    BATCH_SIZE: int = 100
    MAX_RATE_PER_MINUTE: int = 3
    PREFETCH_ENABLED: bool = True

@dataclass(slots=True)
class CacheEntry:
    value: Any
    timestamp: float
    hits: int = 0
    
    def is_valid(self, ttl: int) -> bool:
        return time.time() - self.timestamp < ttl

class UltraFastCache:
    __slots__ = ('_data', '_ttl', '_max_size', '_access_queue')
    
    def __init__(self, ttl: int, max_size: int = 10000):
        self._data: Dict[int, CacheEntry] = {}
        self._ttl = ttl
        self._max_size = max_size
        self._access_queue: deque = deque(maxlen=max_size)
    
    def get(self, key: int) -> Optional[Any]:
        entry = self._data.get(key)
        if entry and entry.is_valid(self._ttl):
            entry.hits += 1
            return entry.value
        if entry:
            del self._data[key]
        return None
    
    def set(self, key: int, value: Any) -> None:
        if len(self._data) >= self._max_size:
            self._evict_lru()
        self._data[key] = CacheEntry(value=value, timestamp=time.time())
        self._access_queue.append(key)
    
    def _evict_lru(self) -> None:
        if not self._access_queue:
            return
        key = self._access_queue.popleft()
        self._data.pop(key, None)
    
    def invalidate(self, key: int) -> None:
        self._data.pop(key, None)
    
    def bulk_invalidate(self, keys: Set[int]) -> None:
        for key in keys:
            self._data.pop(key, None)

class TokenBucket:
    __slots__ = ('_capacity', '_tokens', '_rate', '_last_update', '_lock')
    
    def __init__(self, capacity: int, rate: float):
        self._capacity = capacity
        self._tokens = capacity
        self._rate = rate
        self._last_update = time.time()
        self._lock = asyncio.Lock()
    
    async def consume(self, tokens: int = 1) -> Tuple[bool, float]:
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_update
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last_update = now
            
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True, 0.0
            
            wait_time = (tokens - self._tokens) / self._rate
            return False, wait_time

class HyperRateLimiter:
    __slots__ = ('_buckets', '_capacity', '_rate')
    
    def __init__(self, capacity: int = 3, rate: float = 0.05):
        self._buckets: Dict[int, TokenBucket] = {}
        self._capacity = capacity
        self._rate = rate
    
    async def check(self, user_id: int) -> Tuple[bool, float]:
        if user_id not in self._buckets:
            self._buckets[user_id] = TokenBucket(self._capacity, self._rate)
        return await self._buckets[user_id].consume()

class DatabasePool:
    __slots__ = ('_user_cache', '_char_cache', '_write_buffer', '_flush_task')
    
    def __init__(self):
        self._user_cache: Dict[int, Dict] = {}
        self._char_cache: List[Dict] = []
        self._write_buffer: List[UpdateOne] = []
        self._flush_task = None
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        
        user = await user_collection.find_one(
            {'id': user_id},
            projection={'id': 1, 'first_name': 1, 'username': 1, 'last_weekly_claim': 1, 
                       'total_weekly_claims': 1, 'characters': 1}
        )
        
        if user:
            self._user_cache[user_id] = user
        return user
    
    async def batch_update_user(self, user_id: int, update_doc: Dict) -> None:
        operation = UpdateOne(
            {'id': user_id},
            update_doc,
            upsert=True
        )
        self._write_buffer.append(operation)
        
        if len(self._write_buffer) >= 10:
            await self._flush_writes()
    
    async def _flush_writes(self) -> None:
        if not self._write_buffer:
            return
        
        try:
            await user_collection.bulk_write(self._write_buffer, ordered=False)
            self._write_buffer.clear()
        except Exception as e:
            LOGGER.error(f"Bulk write error: {e}")
    
    async def prefetch_characters(self, rarities: List[str]) -> None:
        if self._char_cache:
            return
        
        cursor = collection.find(
            {'rarity': {'$in': rarities}},
            projection={'id': 1, 'name': 1, 'rarity': 1, 'anime': 1, 'img_url': 1, 
                       'event': 1, 'origin': 1, 'abilities': 1, 'description': 1}
        )
        self._char_cache = await cursor.to_list(length=None)
    
    def get_cached_characters(self) -> List[Dict]:
        return self._char_cache
    
    def invalidate_user_cache(self, user_id: int) -> None:
        self._user_cache.pop(user_id, None)

def ultra_fast_hash(user_id: int, salt: str = "wclaim") -> str:
    return hashlib.blake2b(f"{user_id}{salt}".encode(), digest_size=16).hexdigest()

def async_timeout(seconds: int):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                LOGGER.warning(f"Timeout in {func.__name__}")
                return None
        return wrapper
    return decorator

class HyperWeeklyClaimSystem:
    __slots__ = ('config', '_bio_cache', '_cooldown_cache', '_rate_limiter', 
                 '_db_pool', '_locks', '_stats', '_char_pool')
    
    def __init__(self, config: ClaimConfig):
        self.config = config
        self._bio_cache = UltraFastCache(ttl=config.BIO_CACHE_TTL)
        self._cooldown_cache = UltraFastCache(ttl=60)
        self._rate_limiter = HyperRateLimiter()
        self._db_pool = DatabasePool()
        self._locks: Dict[int, asyncio.Lock] = {}
        self._stats = {'claims': 0, 'cache_hits': 0, 'errors': 0}
        self._char_pool: List[Tuple[Dict, int]] = []
        
        if config.PREFETCH_ENABLED:
            asyncio.create_task(self._initialize())
    
    async def _initialize(self) -> None:
        try:
            await self._db_pool.prefetch_characters(RarityTier.get_all_displays())
            await self._build_character_pool()
            LOGGER.info("HyperWeeklyClaimSystem initialized")
        except Exception as e:
            LOGGER.error(f"Initialization error: {e}")
    
    async def _build_character_pool(self) -> None:
        chars = self._db_pool.get_cached_characters()
        rarity_map = {v: k for k, v in RarityTier.get_display_map().items()}
        
        self._char_pool = [
            (char, rarity_map.get(char['rarity'], RarityTier.MANGA))
            for char in chars
        ]
    
    def _get_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]
    
    @staticmethod
    @lru_cache(maxsize=1024)
    def _format_time(seconds: int) -> str:
        if seconds < 60:
            return f"{seconds}s"
        
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        
        if days > 0:
            return f"{days}ᴅ {hours}ʜ"
        if hours > 0:
            return f"{hours}ʜ {minutes}ᴍ"
        return f"{minutes}ᴍ {secs}s"
    
    @async_timeout(3)
    async def _check_bio_fast(self, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
        cached = self._bio_cache.get(user_id)
        if cached is not None:
            self._stats['cache_hits'] += 1
            return cached
        
        try:
            user = await context.bot.get_chat(user_id)
            has_bot = self.config.BOT_USERNAME.lower() in (user.bio or "").lower()
            self._bio_cache.set(user_id, has_bot)
            return has_bot
        except (BadRequest, Forbidden, TimedOut, NetworkError):
            return False
        except Exception as e:
            LOGGER.error(f"Bio check error {user_id}: {e}")
            return False
    
    async def _get_weighted_character_fast(self, user_id: int, claimed_ids: Set[int]) -> Optional[Dict]:
        if not self._char_pool:
            await self._build_character_pool()
        
        available = [(char, weight) for char, weight in self._char_pool if char['id'] not in claimed_ids]
        
        if not available:
            return None
        
        chars, weights = zip(*available)
        return random.choices(chars, weights=weights, k=1)[0]
    
    @lru_cache(maxsize=512)
    def _generate_caption_cached(self, name: str, rarity: str, anime: str, 
                                  char_id: str, user_id: int, first_name: str, 
                                  claim_count: int) -> str:
        streak = "🔥" if claim_count >= 5 else "✨"
        
        return f"""🎁 ᴡᴇᴇᴋʟʏ ᴄʟᴀɪᴍ sᴜᴄᴄᴇss!
💎 ᴄᴏɴɢʀᴀᴛs <a href='tg://user?id={user_id}'>{first_name}</a>

🎴 ɴᴀᴍᴇ: <b>{name}</b>
⭐ ʀᴀʀɪᴛʏ: <b>{rarity}</b>
🎯 ᴀɴɪᴍᴇ: <b>{anime}</b>
🆔 ɪᴅ: <code>{char_id}</code>

{streak} ᴛᴏᴛᴀʟ ᴄʟᴀɪᴍs: <b>{claim_count}</b>
⏰ ɴᴇxᴛ: <b>7 ᴅᴀʏs</b>
⚠️ ᴋᴇᴇᴘ <code>{self.config.BOT_USERNAME}</code> ɪɴ ʙɪᴏ!</a>"""
    
    async def _process_claim_fast(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        first_name = update.effective_user.first_name
        username = update.effective_user.username
        
        allowed, wait = await self._rate_limiter.check(user_id)
        if not allowed:
            await update.message.reply_text(
                f"⚠️ ʀᴀᴛᴇ ʟɪᴍɪᴛ! ᴡᴀɪᴛ {int(wait)}s",
                parse_mode=ParseMode.HTML
            )
            return
        
        lock = self._get_lock(user_id)
        if lock.locked():
            return
        
        async with lock:
            try:
                await context.bot.send_chat_action(
                    chat_id=update.effective_chat.id,
                    action=ChatAction.TYPING
                )
                
                has_bio, user_data = await asyncio.gather(
                    self._check_bio_fast(user_id, context),
                    self._db_pool.get_user(user_id),
                    return_exceptions=True
                )
                
                if isinstance(has_bio, Exception):
                    has_bio = False
                if isinstance(user_data, Exception):
                    user_data = None
                
                if not has_bio:
                    msg = f"""❌ ᴀᴅᴅ <code>{self.config.BOT_USERNAME}</code> ᴛᴏ ʏᴏᴜʀ ʙɪᴏ!

📝 sᴛᴇᴘs:
1️⃣ ᴀᴅᴅ ʙᴏᴛ ᴜsᴇʀɴᴀᴍᴇ ᴛᴏ ʙɪᴏ
2️⃣ ᴜsᴇ /wclaim
3️⃣ ᴋᴇᴇᴘ ɪᴛ ғᴏʀ 7 ᴅᴀʏs

💎 ʀᴇᴡᴀʀᴅs: {', '.join(RarityTier.get_all_displays())}"""
                    
                    keyboard = [[InlineKeyboardButton("📖 ʜᴇʟᴘ", url="https://telegram.org/blog/edit-profile")]]
                    await update.message.reply_text(
                        msg,
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    return
                
                if not user_data:
                    user_data = {
                        'id': user_id,
                        'first_name': first_name,
                        'username': username,
                        'characters': [],
                        'last_weekly_claim': None,
                        'total_weekly_claims': 0
                    }
                
                last_claim = user_data.get('last_weekly_claim')
                if last_claim:
                    elapsed = (datetime.utcnow() - last_claim).total_seconds()
                    if elapsed < self.config.CLAIM_COOLDOWN_SECONDS:
                        remaining = int(self.config.CLAIM_COOLDOWN_SECONDS - elapsed)
                        time_str = self._format_time(remaining)
                        await update.message.reply_text(
                            f"⏰ ᴀʟʀᴇᴀᴅʏ ᴄʟᴀɪᴍᴇᴅ\n⏳ ɴᴇxᴛ: `{time_str}`",
                            parse_mode=ParseMode.MARKDOWN
                        )
                        return
                
                claimed_ids = {c.get('id') for c in user_data.get('characters', [])}
                character = await self._get_weighted_character_fast(user_id, claimed_ids)
                
                if not character:
                    await update.message.reply_text("❌ ɴᴏ ɴᴇᴡ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴀᴠᴀɪʟᴀʙʟᴇ!")
                    return
                
                claim_count = user_data.get('total_weekly_claims', 0) + 1
                
                update_doc = {
                    '$push': {'characters': character},
                    '$set': {
                        'last_weekly_claim': datetime.utcnow(),
                        'first_name': first_name,
                        'username': username,
                        'total_weekly_claims': claim_count
                    }
                }
                
                await self._db_pool.batch_update_user(user_id, update_doc)
                self._bio_cache.invalidate(user_id)
                self._db_pool.invalidate_user_cache(user_id)
                
                caption = self._generate_caption_cached(
                    character.get('name', 'Unknown'),
                    character.get('rarity', 'Unknown'),
                    character.get('anime', 'Unknown'),
                    str(character.get('id', 'N/A')),
                    user_id,
                    first_name,
                    claim_count
                )
                
                await update.message.reply_photo(
                    photo=character.get('img_url'),
                    caption=caption,
                    parse_mode=ParseMode.HTML
                )
                
                self._stats['claims'] += 1
                
            except TelegramError as e:
                LOGGER.error(f"Telegram error: {e}")
                self._stats['errors'] += 1
            except Exception as e:
                LOGGER.error(f"Claim error: {e}", exc_info=True)
                self._stats['errors'] += 1
    
    async def handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        
        if update.effective_chat.id != self.config.MAIN_GROUP_ID:
            keyboard = [[InlineKeyboardButton("🔗 ᴊᴏɪɴ ɢʀᴏᴜᴘ", url=self.config.MAIN_GROUP_LINK)]]
            await update.message.reply_text(
                "⚠️ ᴜsᴇ ɪɴ ᴍᴀɪɴ ɢʀᴏᴜᴘ ᴏɴʟʏ!",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        await self._process_claim_fast(update, context)

config = ClaimConfig()
hyper_system = HyperWeeklyClaimSystem(config)

application.add_handler(
    CommandHandler(['wclaim', 'weeklyclaim', 'wc'], hyper_system.handle_command, block=False)
)