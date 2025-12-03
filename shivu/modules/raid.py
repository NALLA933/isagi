import asyncio
import random
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
from enum import IntEnum
from contextlib import asynccontextmanager

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import MessageNotModified, BadRequest

from shivu.config import Development as Config
from shivu import shivuu, db, user_collection, collection

class Rarity(IntEnum):
    COMMON = 1
    RARE = 2
    LEGENDARY = 3
    SPECIAL_EDITION = 4
    NEON = 5
    MANGA = 6
    COSPLAY = 7
    CELESTIAL = 8
    PREMIUM = 9
    EROTIC = 10
    SUMMER = 11
    WINTER = 12
    MONSOON = 13
    VALENTINE = 14
    HALLOWEEN = 15
    CHRISTMAS = 16
    MYTHIC = 17
    EVENTS = 18
    AMV = 19
    TINY = 20

RARITY_DISPLAY = {
    Rarity.COMMON: "🟢 Common", Rarity.RARE: "🟣 Rare", Rarity.LEGENDARY: "🟡 Legendary",
    Rarity.SPECIAL_EDITION: "💮 Special Edition", Rarity.NEON: "💫 Neon", Rarity.MANGA: "✨ Manga",
    Rarity.COSPLAY: "🎭 Cosplay", Rarity.CELESTIAL: "🎐 Celestial", Rarity.PREMIUM: "🔮 Premium",
    Rarity.EROTIC: "💋 Erotic", Rarity.SUMMER: "🌤 Summer", Rarity.WINTER: "☃️ Winter",
    Rarity.MONSOON: "☔️ Monsoon", Rarity.VALENTINE: "💝 Valentine", Rarity.HALLOWEEN: "🎃 Halloween",
    Rarity.CHRISTMAS: "🎄 Christmas", Rarity.MYTHIC: "🏵 Mythic", Rarity.EVENTS: "🎗 Events",
    Rarity.AMV: "🎥 Amv", Rarity.TINY: "👼 Tiny"
}

OWNER_IDS = {8420981179, 5147822244}
GLOBAL_ID = "global_raid"

@dataclass
class RaidConfig:
    _id: str = GLOBAL_ID
    charge: int = 500
    duration: int = 30
    cooldown: int = 5
    rarities: List[int] = field(default_factory=lambda: list(range(1, 11)))
    coin_min: int = 500
    coin_max: int = 2000
    loss_min: int = 200
    loss_max: int = 500
    char_chance: int = 25
    coin_chance: int = 35
    loss_chance: int = 20
    nothing_chance: int = 15
    crit_chance: int = 5

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'RaidConfig':
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})

    def validate_chances(self) -> bool:
        return sum([self.char_chance, self.coin_chance, self.loss_chance, 
                   self.nothing_chance, self.crit_chance]) == 100

@dataclass
class RaidResult:
    user_id: int
    result_type: str
    character: Optional[Dict] = None
    rarity: Optional[str] = None
    coins: int = 0
    is_critical: bool = False
    is_double: bool = False

@dataclass
class ActiveRaid:
    raid_id: str
    chat_id: int
    starter_id: int
    participants: List[int] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True

    def to_dict(self) -> Dict:
        return {
            "_id": self.raid_id,
            "chat": self.chat_id,
            "starter": self.starter_id,
            "users": self.participants,
            "time": self.start_time,
            "active": self.is_active
        }

class RaidDatabase:
    def __init__(self):
        self.settings = db['raid_settings']
        self.cooldowns = db['raid_cooldown']
        self.active = db['active_raids']
        self._config_cache: Optional[RaidConfig] = None
        self._cache_time: Optional[datetime] = None

    async def get_config(self, force_refresh: bool = False) -> RaidConfig:
        if not force_refresh and self._config_cache and self._cache_time:
            if (datetime.utcnow() - self._cache_time).seconds < 300:
                return self._config_cache

        data = await self.settings.find_one({"_id": GLOBAL_ID})
        if not data:
            config = RaidConfig()
            await self.settings.insert_one(config.to_dict())
            self._config_cache = config
        else:
            self._config_cache = RaidConfig.from_dict(data)
        
        self._cache_time = datetime.utcnow()
        return self._config_cache

    async def update_config(self, **kwargs) -> None:
        self._config_cache = None
        await self.settings.update_one(
            {"_id": GLOBAL_ID},
            {"$set": kwargs},
            upsert=True
        )

    async def check_cooldown(self, user_id: int, chat_id: int) -> Tuple[bool, int]:
        cd = await self.cooldowns.find_one({"user": user_id, "chat": chat_id})
        if cd and cd.get("until") and datetime.utcnow() < cd["until"]:
            return False, int((cd["until"] - datetime.utcnow()).total_seconds())
        return True, 0

    async def set_cooldown(self, user_id: int, chat_id: int, minutes: int) -> None:
        until = datetime.utcnow() + timedelta(minutes=minutes)
        await self.cooldowns.update_one(
            {"user": user_id, "chat": chat_id},
            {"$set": {"until": until}},
            upsert=True
        )

    async def create_raid(self, raid: ActiveRaid) -> None:
        await self.active.insert_one(raid.to_dict())

    async def get_raid(self, raid_id: str) -> Optional[ActiveRaid]:
        data = await self.active.find_one({"_id": raid_id, "active": True})
        if not data:
            return None
        return ActiveRaid(
            raid_id=data["_id"],
            chat_id=data["chat"],
            starter_id=data["starter"],
            participants=data["users"],
            start_time=data["time"],
            is_active=data["active"]
        )

    async def add_participant(self, raid_id: str, user_id: int) -> None:
        await self.active.update_one(
            {"_id": raid_id},
            {"$addToSet": {"users": user_id}}
        )

    async def deactivate_raid(self, raid_id: str) -> None:
        await self.active.update_one(
            {"_id": raid_id},
            {"$set": {"active": False}}
        )

    async def cleanup_old_raids(self, chat_id: int) -> None:
        cutoff = datetime.utcnow() - timedelta(minutes=10)
        await self.active.delete_many({
            "chat": chat_id,
            "time": {"$lt": cutoff}
        })

    async def get_active_raid_for_chat(self, chat_id: int) -> Optional[ActiveRaid]:
        data = await self.active.find_one({"chat": chat_id, "active": True})
        if not data:
            return None
        
        elapsed = (datetime.utcnow() - data.get("time", datetime.utcnow())).total_seconds()
        if elapsed > 300:
            await self.cleanup_old_raids(chat_id)
            return None
        
        return ActiveRaid(
            raid_id=data["_id"],
            chat_id=data["chat"],
            starter_id=data["starter"],
            participants=data["users"],
            start_time=data["time"],
            is_active=data["active"]
        )

class UserManager:
    @staticmethod
    async def get_user(user_id: int) -> Dict:
        user = await user_collection.find_one({"id": user_id})
        if not user:
            user = {"id": user_id, "balance": 0, "characters": []}
            await user_collection.insert_one(user)
        return user

    @staticmethod
    async def update_balance(user_id: int, amount: int) -> None:
        await user_collection.update_one(
            {"id": user_id},
            {"$inc": {"balance": amount}},
            upsert=True
        )

    @staticmethod
    async def add_character(user_id: int, char: Dict) -> None:
        rarity = char.get("rarity")
        if isinstance(rarity, int):
            rarity = RARITY_DISPLAY.get(rarity, "🟢 Common")
        
        data = {
            "id": char.get("id"),
            "name": char.get("name"),
            "anime": char.get("anime"),
            "rarity": rarity,
            "img_url": char.get("img_url", "")
        }
        await user_collection.update_one(
            {"id": user_id},
            {"$push": {"characters": data}},
            upsert=True
        )

class CharacterPool:
    @staticmethod
    async def get_random_character(rarities: List[int]) -> Optional[Dict]:
        try:
            chars = await collection.find({"rarity": {"$in": rarities}}).to_list(None)
            if not chars:
                rarity_strings = [RARITY_DISPLAY.get(r, f"Rarity {r}") for r in rarities]
                chars = await collection.find({"rarity": {"$in": rarity_strings}}).to_list(None)
            return random.choice(chars) if chars else None
        except Exception:
            return None

class RaidRewardCalculator:
    def __init__(self, config: RaidConfig):
        self.config = config

    def calculate_reward(self) -> Tuple[str, Optional[int]]:
        roll = random.randint(1, 100)
        
        if roll <= self.config.crit_chance:
            return "critical", None
        
        threshold = self.config.crit_chance
        if roll <= threshold + self.config.char_chance:
            return "character", None
        
        threshold += self.config.char_chance
        if roll <= threshold + self.config.coin_chance:
            coins = random.randint(self.config.coin_min, self.config.coin_max)
            return "coins", coins
        
        threshold += self.config.coin_chance
        if roll <= threshold + self.config.loss_chance:
            loss = random.randint(self.config.loss_min, self.config.loss_max)
            return "loss", loss
        
        return "nothing", None

class RaidExecutor:
    def __init__(self, db_manager: RaidDatabase, user_manager: UserManager, 
                 char_pool: CharacterPool):
        self.db = db_manager
        self.users = user_manager
        self.chars = char_pool

    async def execute_raid(self, client: Client, message: Message, raid_id: str) -> None:
        raid = await self.db.get_raid(raid_id)
        if not raid:
            return

        await self.db.deactivate_raid(raid_id)
        config = await self.db.get_config()

        if not raid.participants:
            await message.edit_text("❌ ɴᴏ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs!")
            return

        calculator = RaidRewardCalculator(config)
        results = await self._process_participants(raid.participants, calculator, config)
        
        await self._send_results(client, message, raid, results, config)
        await self.db.cleanup_old_raids(raid.chat_id)

    async def _process_participants(self, participants: List[int], 
                                   calculator: RaidRewardCalculator,
                                   config: RaidConfig) -> List[RaidResult]:
        results = []
        for user_id in participants:
            result_type, value = calculator.calculate_reward()
            result = await self._process_reward(user_id, result_type, value, config)
            results.append(result)
        return results

    async def _process_reward(self, user_id: int, result_type: str, 
                             value: Optional[int], config: RaidConfig) -> RaidResult:
        if result_type == "critical":
            char = await self.chars.get_random_character(config.rarities)
            coins = random.randint(config.coin_min, config.coin_max)
            
            if char:
                await self.users.add_character(user_id, char)
                await self.users.update_balance(user_id, coins)
                rarity = char.get("rarity")
                if isinstance(rarity, int):
                    rarity = RARITY_DISPLAY.get(rarity, "🟢 Common")
                return RaidResult(user_id, "critical", char, rarity, coins, True)
            else:
                coins *= 2
                await self.users.update_balance(user_id, coins)
                return RaidResult(user_id, "coins", None, None, coins, False, True)

        elif result_type == "character":
            char = await self.chars.get_random_character(config.rarities)
            if char:
                await self.users.add_character(user_id, char)
                rarity = char.get("rarity")
                if isinstance(rarity, int):
                    rarity = RARITY_DISPLAY.get(rarity, "🟢 Common")
                return RaidResult(user_id, "character", char, rarity)
            else:
                coins = random.randint(config.coin_min, config.coin_max)
                await self.users.update_balance(user_id, coins)
                return RaidResult(user_id, "coins", None, None, coins)

        elif result_type == "coins":
            await self.users.update_balance(user_id, value)
            return RaidResult(user_id, "coins", None, None, value)

        elif result_type == "loss":
            await self.users.update_balance(user_id, -value)
            return RaidResult(user_id, "loss", None, None, value)

        return RaidResult(user_id, "nothing")

    async def _send_results(self, client: Client, message: Message, 
                          raid: ActiveRaid, results: List[RaidResult],
                          config: RaidConfig) -> None:
        stats = self._calculate_stats(results)
        text = await self._format_results(client, results, stats)
        images = [r.character.get("img_url") for r in results 
                 if r.character and r.character.get("img_url")]

        try:
            if images:
                await message.delete()
                await client.send_photo(raid.chat_id, images[0], caption=text)
            else:
                await message.edit_text(text)
        except (MessageNotModified, BadRequest):
            pass

    def _calculate_stats(self, results: List[RaidResult]) -> Dict:
        return {
            "total_coins": sum(r.coins for r in results if r.result_type in ("critical", "coins")),
            "total_chars": sum(1 for r in results if r.character),
            "total_crits": sum(1 for r in results if r.is_critical),
            "participants": len(results)
        }

    async def _format_results(self, client: Client, results: List[RaidResult], 
                             stats: Dict) -> str:
        text = (
            f"<blockquote>⚔️ <b>ʀᴀɪᴅ ᴄᴏᴍᴘʟᴇᴛᴇ</b> ⚔️</blockquote>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👥 <b>ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs:</b> <code>{stats['participants']}</code>\n\n"
            f"<b>🏆 ʟᴏᴏᴛ:</b>\n"
        )

        for result in results:
            user_text = await self._get_user_mention(client, result.user_id)
            text += self._format_user_result(user_text, result)

        text += (
            f"\n━━━━━━━━━━━━━━━\n"
            f"💰 <b>ᴛᴏᴛᴀʟ:</b> <code>{stats['total_coins']:,}</code>\n"
            f"🎴 <b>ᴄʜᴀʀs:</b> <code>{stats['total_chars']}</code>\n"
            f"💥 <b>ᴄʀɪᴛs:</b> <code>{stats['total_crits']}</code>\n\n"
            f"<i>ᴘᴏᴡᴇʀᴇᴅ ʙʏ</i> <a href='https://t.me/siyaprobot'>sɪʏᴀ</a>"
        )
        return text

    async def _get_user_mention(self, client: Client, user_id: int) -> str:
        try:
            user = await client.get_users(user_id)
            return f"@{user.username}" if user.username else user.first_name
        except:
            return "Unknown"

    def _format_user_result(self, user_text: str, result: RaidResult) -> str:
        if result.result_type == "critical":
            char_id = result.character.get("id", "???")
            char_name = result.character.get("name", "Unknown")
            return (
                f"• {user_text} — <b>💥 ᴄʀɪᴛɪᴄᴀʟ!</b>\n"
                f"  └ 🎴 {result.rarity} • <code>{char_id}</code> • {char_name}\n"
                f"  └ 💰 <code>{result.coins} ᴄᴏɪɴs</code>\n"
            )
        elif result.result_type == "character":
            char_id = result.character.get("id", "???")
            char_name = result.character.get("name", "Unknown")
            return f"• {user_text} — 🎴\n  └ {result.rarity} • <code>{char_id}</code> • {char_name}\n"
        elif result.result_type == "coins":
            double = " (2x!)" if result.is_double else ""
            return f"• {user_text} — 💰 <code>{result.coins}{double}</code>\n"
        elif result.result_type == "loss":
            return f"• {user_text} — 💀 <code>-{result.coins}</code>\n"
        return f"• {user_text} — ❌\n"

class RaidUI:
    @staticmethod
    def create_join_button(raid_id: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("⚔️ ᴊᴏɪɴ ʀᴀɪᴅ", callback_data=f"jr:{raid_id}")
        ]])

    @staticmethod
    async def format_raid_message(config: RaidConfig, participant_count: int,
                                  time_left: int, starter_mention: str) -> str:
        return (
            f"<blockquote>⚔️ <b>sʜᴀᴅᴏᴡ ʀᴀɪᴅ ʙᴇɢɪɴs!</b> ⚔️</blockquote>\n\n"
            f"<code>ᴊᴏɪɴ ɴᴏᴡ ᴀɴᴅ ᴄᴏʟʟᴇᴄᴛ ᴛʀᴇᴀsᴜʀᴇs!</code>\n\n"
            f"⏱ <b>ᴛɪᴍᴇ:</b> <code>{time_left}s</code>\n"
            f"💰 <b>ғᴇᴇ:</b> <code>{config.charge} ᴄᴏɪɴs</code>\n"
            f"👥 <b>ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs:</b> <code>{participant_count}</code>\n\n"
            f"━━━━━━━━━━━━━━━\n<i>ʙʏ</i> {starter_mention}"
        )

db_manager = RaidDatabase()
user_manager = UserManager()
char_pool = CharacterPool()
raid_executor = RaidExecutor(db_manager, user_manager, char_pool)
raid_ui = RaidUI()

@shivuu.on_message(filters.command("raid") & filters.group)
async def start_raid(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    existing = await db_manager.get_active_raid_for_chat(chat_id)
    if existing:
        return await message.reply_text("⚠️ ᴀ ʀᴀɪᴅ ɪs ᴀʟʀᴇᴀᴅʏ ᴀᴄᴛɪᴠᴇ!")

    config = await db_manager.get_config()
    can_raid, remaining = await db_manager.check_cooldown(user_id, chat_id)
    
    if not can_raid:
        return await message.reply_text(
            f"⏳ ᴄᴏᴏʟᴅᴏᴡɴ: `{remaining // 60}m {remaining % 60}s`"
        )

    user = await user_manager.get_user(user_id)
    if user.get("balance", 0) < config.charge:
        return await message.reply_text(
            f"💰 ɴᴇᴇᴅ `{config.charge}` ᴄᴏɪɴs ᴛᴏ sᴛᴀʀᴛ ʀᴀɪᴅ"
        )

    await user_manager.update_balance(user_id, -config.charge)

    raid_id = f"{chat_id}_{int(datetime.utcnow().timestamp() * 1000)}"
    raid = ActiveRaid(raid_id, chat_id, user_id, [user_id])
    await db_manager.create_raid(raid)
    await db_manager.set_cooldown(user_id, chat_id, config.cooldown)

    text = await raid_ui.format_raid_message(
        config, 1, config.duration, message.from_user.mention
    )
    btn = raid_ui.create_join_button(raid_id)
    msg = await message.reply_text(text, reply_markup=btn)

    asyncio.create_task(countdown_updater(client, msg, raid_id, config.duration))
    await asyncio.sleep(config.duration)

    check = await db_manager.get_raid(raid_id)
    if check:
        await raid_executor.execute_raid(client, msg, raid_id)

async def countdown_updater(client: Client, message: Message, 
                           raid_id: str, duration: int):
    config = await db_manager.get_config()
    start_time = datetime.utcnow()
    
    for _ in range(duration // 5):
        await asyncio.sleep(5)
        
        raid = await db_manager.get_raid(raid_id)
        if not raid:
            break

        elapsed = (datetime.utcnow() - start_time).total_seconds()
        time_left = max(0, int(duration - elapsed))
        
        if time_left == 0:
            break

        try:
            starter = await client.get_users(raid.starter_id)
            mention = starter.mention
        except:
            mention = "Unknown"

        text = await raid_ui.format_raid_message(
            config, len(raid.participants), time_left, mention
        )
        btn = raid_ui.create_join_button(raid_id)
        
        try:
            await message.edit_text(text, reply_markup=btn)
        except (MessageNotModified, BadRequest):
            pass

@shivuu.on_callback_query(filters.regex(r"^jr:"))
async def join_raid(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    raid_id = query.data.split(":")[1]

    raid = await db_manager.get_raid(raid_id)
    if not raid:
        return await query.answer("⚠️ ʀᴀɪᴅ ᴇɴᴅᴇᴅ!", show_alert=True)

    if user_id in raid.participants:
        return await query.answer("✅ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ!")

    config = await db_manager.get_config()
    can_raid, remaining = await db_manager.check_cooldown(user_id, raid.chat_id)
    
    if not can_raid:
        return await query.answer(
            f"⏳ ᴄᴏᴏʟᴅᴏᴡɴ: {remaining // 60}m {remaining % 60}s",
            show_alert=True
        )

    user = await user_manager.get_user(user_id)
    if user.get("balance", 0) < config.charge:
        return await query.answer(
            f"💰 ɴᴇᴇᴅ {config.charge} ᴄᴏɪɴs",
            show_alert=True
        )

    await user_manager.update_balance(user_id, -config.charge)
    await db_manager.add_participant(raid_id, user_id)
    await db_manager.set_cooldown(user_id, raid.chat_id, config.cooldown)
    await query.answer("⚔️ ᴊᴏɪɴᴇᴅ ʀᴀɪᴅ!")

    try:
        updated_raid = await db_manager.get_raid(raid_id)
        if not updated_raid:
            return

        elapsed = (datetime.utcnow() - raid.start_time).total_seconds()
        time_left = max(0, int(config.duration - elapsed))

        try:
            starter = await client.get_users(raid.starter_id)
            mention = starter.mention
        except:
            mention = "Unknown"

        text = await raid_ui.format_raid_message(
            config, len(updated_raid.participants), time_left, mention
        )
        btn = raid_ui.create_join_button(raid_id)
        await query.message.edit_text(text, reply_markup=btn)
    except (MessageNotModified, BadRequest):
        pass

@shivuu.on_message(filters.command("setraidcharge") & filters.user(OWNER_IDS))
async def set_charge(_, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /setraidcharge <amount>")
    try:
        amount = int(m.command[1])
        await db_manager.update_config(charge=amount)
        await m.reply_text(f"✅ ᴄʜᴀʀɢᴇ sᴇᴛ ᴛᴏ: <code>{amount}</code> ᴄᴏɪɴs")
    except ValueError:
        await m.reply_text("❌ ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ")

@shivuu.on_message(filters.command("setraidcooldown") & filters.user(OWNER_IDS))
async def set_cooldown(_, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /setraidcooldown <minutes>")
    try:
        minutes = int(m.command[1])
        await db_manager.update_config(cooldown=minutes)
        await m.reply_text(f"✅ ᴄᴏᴏʟᴅᴏᴡɴ sᴇᴛ ᴛᴏ: <code>{minutes}</code> ᴍɪɴᴜᴛᴇs")
    except ValueError:
        await m.reply_text("❌ ɪɴᴠᴀʟɪᴅ ᴠᴀʟᴜᴇ")

@shivuu.on_message(filters.command("setraidrarities") & filters.user(OWNER_IDS))
async def set_rarities(_, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /setraidrarities <1,2,3...>")
    try:
        rarities = [int(r.strip()) for r in m.command[1].split(",")]
        await db_manager.update_config(rarities=rarities)
        names = [RARITY_DISPLAY.get(r, f"R{r}") for r in rarities]
        await m.reply_text(f"✅ ʀᴀʀɪᴛɪᴇs sᴇᴛ:\n" + "\n".join(f"• {n}" for n in names))
    except ValueError:
        await m.reply_text("❌ ɪɴᴠᴀʟɪᴅ ғᴏʀᴍᴀᴛ")

@shivuu.on_message(filters.command("setraidchances") & filters.user(OWNER_IDS))
async def set_chances(_, m: Message):
    if len(m.command) < 6:
        return await m.reply_text(
            "Usage: /setraidchances <char> <coin> <loss> <nothing> <crit>"
        )
    try:
        char_c, coin_c, loss_c, nothing_c, crit_c = [int(m.command[i]) for i in range(1, 6)]
        total = char_c + coin_c + loss_c + nothing_c + crit_c
        
        if total != 100:
            return await m.reply_text(f"❌ ᴛᴏᴛᴀʟ: {total}% (ᴍᴜsᴛ ʙᴇ 100%)")
        
        await db_manager.update_config(
            char_chance=char_c,
            coin_chance=coin_c,
            loss_chance=loss_c,
            nothing_chance=nothing_c,
            crit_chance=crit_c
        )
        await m.reply_text(
            f"✅ ᴄʜᴀɴᴄᴇs ᴜᴘᴅᴀᴛᴇᴅ:\n"
            f"🎴 ᴄʜᴀʀ: {char_c}%\n"
            f"💰 ᴄᴏɪɴ: {coin_c}%\n"
            f"💀 ʟᴏss: {loss_c}%\n"
            f"❌ ɴᴏᴛʜɪɴɢ: {nothing_c}%\n"
            f"💥 ᴄʀɪᴛ: {crit_c}%"
        )
    except ValueError:
        await m.reply_text("❌ ɪɴᴠᴀʟɪᴅ ᴠᴀʟᴜᴇs")

@shivuu.on_message(filters.command("setraidcoins") & filters.user(OWNER_IDS))
async def set_coins(_, m: Message):
    if len(m.command) < 3:
        return await m.reply_text("Usage: /setraidcoins <min> <max>")
    try:
        coin_min, coin_max = int(m.command[1]), int(m.command[2])
        if coin_min >= coin_max:
            return await m.reply_text("❌ ᴍɪɴ ᴍᴜsᴛ ʙᴇ ʟᴇss ᴛʜᴀɴ ᴍᴀx")
        
        await db_manager.update_config(coin_min=coin_min, coin_max=coin_max)
        await m.reply_text(f"✅ ᴄᴏɪɴ ʀᴀɴɢᴇ: <code>{coin_min}</code> - <code>{coin_max}</code>")
    except ValueError:
        await m.reply_text("❌ ɪɴᴠᴀʟɪᴅ ᴠᴀʟᴜᴇs")

@shivuu.on_message(filters.command("setraidloss") & filters.user(OWNER_IDS))
async def set_loss(_, m: Message):
    if len(m.command) < 3:
        return await m.reply_text("Usage: /setraidloss <min> <max>")
    try:
        loss_min, loss_max = int(m.command[1]), int(m.command[2])
        if loss_min >= loss_max:
            return await m.reply_text("❌ ᴍɪɴ ᴍᴜsᴛ ʙᴇ ʟᴇss ᴛʜᴀɴ ᴍᴀx")
        
        await db_manager.update_config(loss_min=loss_min, loss_max=loss_max)
        await m.reply_text(f"✅ ʟᴏss ʀᴀɴɢᴇ: <code>{loss_min}</code> - <code>{loss_max}</code>")
    except ValueError:
        await m.reply_text("❌ ɪɴᴠᴀʟɪᴅ ᴠᴀʟᴜᴇs")

@shivuu.on_message(filters.command("setraidduration") & filters.user(OWNER_IDS))
async def set_duration(_, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /setraidduration <seconds>")
    try:
        duration = int(m.command[1])
        if duration < 10 or duration > 300:
            return await m.reply_text("❌ ᴅᴜʀᴀᴛɪᴏɴ ᴍᴜsᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ 10-300 sᴇᴄᴏɴᴅs")
        
        await db_manager.update_config(duration=duration)
        await m.reply_text(f"✅ ᴅᴜʀᴀᴛɪᴏɴ sᴇᴛ ᴛᴏ: <code>{duration}</code> sᴇᴄᴏɴᴅs")
    except ValueError:
        await m.reply_text("❌ ɪɴᴠᴀʟɪᴅ ᴠᴀʟᴜᴇ")

@shivuu.on_message(filters.command("raidsettings") & filters.user(OWNER_IDS))
async def show_settings(_, m: Message):
    config = await db_manager.get_config()
    rarity_names = [RARITY_DISPLAY.get(r, f"R{r}") for r in config.rarities]
    
    text = (
        f"<blockquote>🌐 <b>ɢʟᴏʙᴀʟ ʀᴀɪᴅ sᴇᴛᴛɪɴɢs</b></blockquote>\n\n"
        f"<b>⚙️ ʙᴀsɪᴄ sᴇᴛᴛɪɴɢs:</b>\n"
        f"💰 ᴄʜᴀʀɢᴇ: <code>{config.charge}</code> ᴄᴏɪɴs\n"
        f"⏱ ᴅᴜʀᴀᴛɪᴏɴ: <code>{config.duration}</code> sᴇᴄᴏɴᴅs\n"
        f"⏳ ᴄᴏᴏʟᴅᴏᴡɴ: <code>{config.cooldown}</code> ᴍɪɴᴜᴛᴇs\n\n"
        f"<b>💎 ʀᴇᴡᴀʀᴅ ʀᴀɴɢᴇs:</b>\n"
        f"💰 ᴄᴏɪɴs: <code>{config.coin_min}</code> - <code>{config.coin_max}</code>\n"
        f"💀 ʟᴏss: <code>{config.loss_min}</code> - <code>{config.loss_max}</code>\n\n"
        f"<b>🎲 ᴘʀᴏʙᴀʙɪʟɪᴛɪᴇs:</b>\n"
        f"🎴 ᴄʜᴀʀᴀᴄᴛᴇʀ: <code>{config.char_chance}%</code>\n"
        f"💰 ᴄᴏɪɴs: <code>{config.coin_chance}%</code>\n"
        f"💀 ʟᴏss: <code>{config.loss_chance}%</code>\n"
        f"❌ ɴᴏᴛʜɪɴɢ: <code>{config.nothing_chance}%</code>\n"
        f"💥 ᴄʀɪᴛɪᴄᴀʟ: <code>{config.crit_chance}%</code>\n\n"
        f"<b>✨ ᴀᴠᴀɪʟᴀʙʟᴇ ʀᴀʀɪᴛɪᴇs:</b> <code>{len(rarity_names)}</code>\n"
    )
    
    for i, rarity in enumerate(rarity_names[:10], 1):
        text += f"{i}. {rarity}\n"
    
    if len(rarity_names) > 10:
        text += f"<i>... ᴀɴᴅ {len(rarity_names) - 10} ᴍᴏʀᴇ</i>\n"
    
    text += f"\n<i>ᴘᴏᴡᴇʀᴇᴅ ʙʏ</i> <a href='https://t.me/siyaprobot'>sɪʏᴀ</a>"
    
    await m.reply_text(text, disable_web_page_preview=True)

@shivuu.on_message(filters.command("resetraidsettings") & filters.user(OWNER_IDS))
async def reset_settings(_, m: Message):
    default_config = RaidConfig()
    await db_manager.update_config(**default_config.to_dict())
    await m.reply_text("✅ ʀᴀɪᴅ sᴇᴛᴛɪɴɢs ʀᴇsᴇᴛ ᴛᴏ ᴅᴇғᴀᴜʟᴛ")

@shivuu.on_message(filters.command("raidstats") & filters.group)
async def raid_stats(client: Client, m: Message):
    user_id = m.from_user.id
    user = await user_manager.get_user(user_id)
    
    total_chars = len(user.get("characters", []))
    balance = user.get("balance", 0)
    
    rarity_count = {}
    for char in user.get("characters", []):
        rarity = char.get("rarity", "Unknown")
        rarity_count[rarity] = rarity_count.get(rarity, 0) + 1
    
    text = (
        f"<blockquote>📊 <b>ʏᴏᴜʀ ʀᴀɪᴅ sᴛᴀᴛs</b></blockquote>\n\n"
        f"👤 <b>ᴜsᴇʀ:</b> {m.from_user.mention}\n"
        f"💰 <b>ʙᴀʟᴀɴᴄᴇ:</b> <code>{balance:,}</code> ᴄᴏɪɴs\n"
        f"🎴 <b>ᴛᴏᴛᴀʟ ᴄʜᴀʀᴀᴄᴛᴇʀs:</b> <code>{total_chars}</code>\n"
    )
    
    if rarity_count:
        text += f"\n<b>📈 ʙʏ ʀᴀʀɪᴛʏ:</b>\n"
        sorted_rarities = sorted(rarity_count.items(), key=lambda x: x[1], reverse=True)
        for rarity, count in sorted_rarities[:5]:
            text += f"• {rarity}: <code>{count}</code>\n"
    
    await m.reply_text(text)

@shivuu.on_message(filters.command("raidleaderboard") & filters.group)
async def raid_leaderboard(_, m: Message):
    chat_id = m.chat.id
    
    users = await user_collection.find({}).sort("balance", -1).limit(10).to_list(length=10)
    
    if not users:
        return await m.reply_text("❌ ɴᴏ ᴅᴀᴛᴀ ᴀᴠᴀɪʟᴀʙʟᴇ")
    
    text = (
        f"<blockquote>🏆 <b>ʀᴀɪᴅ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b></blockquote>\n\n"
        f"<b>💰 ᴛᴏᴘ 10 ʀɪᴄʜᴇsᴛ ᴘʟᴀʏᴇʀs</b>\n\n"
    )
    
    medals = ["🥇", "🥈", "🥉"]
    
    for idx, user in enumerate(users, 1):
        medal = medals[idx - 1] if idx <= 3 else f"{idx}."
        balance = user.get("balance", 0)
        char_count = len(user.get("characters", []))
        
        try:
            user_obj = await shivuu.get_users(user["id"])
            name = user_obj.first_name
        except:
            name = "Unknown"
        
        text += (
            f"{medal} <b>{name}</b>\n"
            f"   💰 <code>{balance:,}</code> | 🎴 <code>{char_count}</code>\n"
        )
    
    text += f"\n<i>ᴘᴏᴡᴇʀᴇᴅ ʙʏ</i> <a href='https://t.me/siyaprobot'>sɪʏᴀ</a>"
    
    await m.reply_text(text, disable_web_page_preview=True)

@shivuu.on_message(filters.command("raidhelp"))
async def raid_help(_, m: Message):
    text = (
        f"<blockquote>⚔️ <b>ʀᴀɪᴅ sʏsᴛᴇᴍ ʜᴇʟᴘ</b></blockquote>\n\n"
        f"<b>👥 ᴜsᴇʀ ᴄᴏᴍᴍᴀɴᴅs:</b>\n"
        f"• /raid - sᴛᴀʀᴛ ᴀ ɴᴇᴡ ʀᴀɪᴅ\n"
        f"• /raidstats - ᴠɪᴇᴡ ʏᴏᴜʀ sᴛᴀᴛs\n"
        f"• /raidleaderboard - ᴛᴏᴘ ᴘʟᴀʏᴇʀs\n"
        f"• /raidhelp - sʜᴏᴡ ᴛʜɪs ʜᴇʟᴘ\n\n"
        f"<b>🎮 ʜᴏᴡ ᴛᴏ ᴘʟᴀʏ:</b>\n"
        f"1️⃣ sᴛᴀʀᴛ ᴀ ʀᴀɪᴅ ᴡɪᴛʜ /raid\n"
        f"2️⃣ ᴏᴛʜᴇʀs ᴄᴀɴ ᴊᴏɪɴ ʙʏ ᴄʟɪᴄᴋɪɴɢ ᴛʜᴇ ʙᴜᴛᴛᴏɴ\n"
        f"3️⃣ ᴡᴀɪᴛ ғᴏʀ ᴛʜᴇ ʀᴀɪᴅ ᴛᴏ ᴇɴᴅ\n"
        f"4️⃣ ɢᴇᴛ ʏᴏᴜʀ ʀᴇᴡᴀʀᴅs!\n\n"
        f"<b>🎁 ᴘᴏssɪʙʟᴇ ʀᴇᴡᴀʀᴅs:</b>\n"
        f"💥 ᴄʀɪᴛɪᴄᴀʟ - ᴄʜᴀʀᴀᴄᴛᴇʀ + ᴄᴏɪɴs\n"
        f"🎴 ᴄʜᴀʀᴀᴄᴛᴇʀ - ʀᴀɴᴅᴏᴍ ᴄʜᴀʀᴀᴄᴛᴇʀ\n"
        f"💰 ᴄᴏɪɴs - ʀᴀɴᴅᴏᴍ ᴀᴍᴏᴜɴᴛ\n"
        f"💀 ʟᴏss - ʟᴏsᴇ sᴏᴍᴇ ᴄᴏɪɴs\n"
        f"❌ ɴᴏᴛʜɪɴɢ - ɴᴏ ʀᴇᴡᴀʀᴅ\n"
    )
    
    if m.from_user.id in OWNER_IDS:
        text += (
            f"\n<b>👑 ᴀᴅᴍɪɴ ᴄᴏᴍᴍᴀɴᴅs:</b>\n"
            f"• /raidsettings - ᴠɪᴇᴡ sᴇᴛᴛɪɴɢs\n"
            f"• /setraidcharge <amount>\n"
            f"• /setraidcooldown <minutes>\n"
            f"• /setraidduration <seconds>\n"
            f"• /setraidrarities <1,2,3...>\n"
            f"• /setraidchances <char> <coin> <loss> <nothing> <crit>\n"
            f"• /setraidcoins <min> <max>\n"
            f"• /setraidloss <min> <max>\n"
            f"• /resetraidsettings\n"
        )
    
    text += f"\n<i>ᴘᴏᴡᴇʀᴇᴅ ʙʏ</i> <a href='https://t.me/siyaprobot'>sɪʏᴀ</a>"
    
    await m.reply_text(text, disable_web_page_preview=True)