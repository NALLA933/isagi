import asyncio
import random
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
from enum import IntEnum

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
    Rarity.SPECIAL_EDITION: "💮 Special", Rarity.NEON: "💫 Neon", Rarity.MANGA: "✨ Manga",
    Rarity.COSPLAY: "🎭 Cosplay", Rarity.CELESTIAL: "🎐 Celestial", Rarity.PREMIUM: "🔮 Premium",
    Rarity.EROTIC: "💋 Erotic", Rarity.SUMMER: "🌤 Summer", Rarity.WINTER: "☃️ Winter",
    Rarity.MONSOON: "☔️ Monsoon", Rarity.VALENTINE: "💝 Valentine", Rarity.HALLOWEEN: "🎃 Halloween",
    Rarity.CHRISTMAS: "🎄 Christmas", Rarity.MYTHIC: "🏵 Mythic", Rarity.EVENTS: "🎗 Events",
    Rarity.AMV: "🎥 Amv", Rarity.TINY: "👼 Tiny"
}

OWNER_IDS = [8420981179, 5147822244]  # Changed to list
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

@dataclass
class ActiveRaid:
    raid_id: str
    chat_id: int
    starter_id: int
    participants: List[int] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True

class RaidDatabase:
    def __init__(self):
        self.settings = db['raid_settings']
        self.cooldowns = db['raid_cooldown']
        self.active = db['active_raids']
        self._cache: Optional[RaidConfig] = None
        self._cache_time: Optional[datetime] = None

    async def get_config(self) -> RaidConfig:
        if self._cache and self._cache_time and (datetime.utcnow() - self._cache_time).seconds < 300:
            return self._cache

        data = await self.settings.find_one({"_id": GLOBAL_ID})
        self._cache = RaidConfig(**data) if data else RaidConfig()
        if not data:
            await self.settings.insert_one(asdict(self._cache))
        self._cache_time = datetime.utcnow()
        return self._cache

    async def update_config(self, **kwargs) -> None:
        self._cache = None
        await self.settings.update_one({"_id": GLOBAL_ID}, {"$set": kwargs}, upsert=True)

    async def check_cooldown(self, user_id: int, chat_id: int) -> Tuple[bool, int]:
        cd = await self.cooldowns.find_one({"user": user_id, "chat": chat_id})
        if cd and cd.get("until") and datetime.utcnow() < cd["until"]:
            return False, int((cd["until"] - datetime.utcnow()).total_seconds())
        return True, 0

    async def set_cooldown(self, user_id: int, chat_id: int, minutes: int) -> None:
        await self.cooldowns.update_one(
            {"user": user_id, "chat": chat_id},
            {"$set": {"until": datetime.utcnow() + timedelta(minutes=minutes)}},
            upsert=True
        )

    async def create_raid(self, raid: ActiveRaid) -> None:
        await self.active.insert_one({
            "_id": raid.raid_id, "chat": raid.chat_id, "starter": raid.starter_id,
            "users": raid.participants, "time": raid.start_time, "active": True
        })

    async def get_raid(self, raid_id: str) -> Optional[ActiveRaid]:
        data = await self.active.find_one({"_id": raid_id, "active": True})
        return ActiveRaid(data["_id"], data["chat"], data["starter"], data["users"], data["time"]) if data else None

    async def add_participant(self, raid_id: str, user_id: int) -> None:
        await self.active.update_one({"_id": raid_id}, {"$addToSet": {"users": user_id}})

    async def end_raid(self, raid_id: str) -> None:
        await self.active.update_one({"_id": raid_id}, {"$set": {"active": False}})

    async def cleanup_old(self, chat_id: int) -> None:
        await self.active.delete_many({
            "chat": chat_id,
            "time": {"$lt": datetime.utcnow() - timedelta(minutes=10)}
        })

    async def get_active_for_chat(self, chat_id: int) -> Optional[ActiveRaid]:
        data = await self.active.find_one({"chat": chat_id, "active": True})
        if data and (datetime.utcnow() - data["time"]).seconds < 300:
            return ActiveRaid(data["_id"], data["chat"], data["starter"], data["users"], data["time"])
        await self.cleanup_old(chat_id)
        return None

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
        await user_collection.update_one({"id": user_id}, {"$inc": {"balance": amount}}, upsert=True)

    @staticmethod
    async def add_character(user_id: int, char: Dict) -> None:
        rarity = char.get("rarity")
        if isinstance(rarity, int):
            rarity = RARITY_DISPLAY.get(rarity, "🟢 Common")
        
        await user_collection.update_one(
            {"id": user_id},
            {"$push": {"characters": {
                "id": char.get("id"), "name": char.get("name"),
                "anime": char.get("anime"), "rarity": rarity, "img_url": char.get("img_url", "")
            }}},
            upsert=True
        )

class RaidExecutor:
    def __init__(self, db_mgr: RaidDatabase, usr_mgr: UserManager):
        self.db = db_mgr
        self.usr = usr_mgr

    async def execute(self, client: Client, message: Message, raid_id: str) -> None:
        raid = await self.db.get_raid(raid_id)
        if not raid:
            return

        await self.db.end_raid(raid_id)
        config = await self.db.get_config()

        if not raid.participants:
            await message.edit_text("❌ ɴᴏ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs!")
            return

        results = await self._process_all(raid.participants, config)
        await self._send_results(client, message, raid, results, config)
        await self.db.cleanup_old(raid.chat_id)

    async def _process_all(self, participants: List[int], config: RaidConfig) -> List[Dict]:
        results = []
        for uid in participants:
            roll = random.randint(1, 100)
            threshold = 0
            
            if roll <= (threshold := config.crit_chance):
                char = await self._get_char(config.rarities)
                coins = random.randint(config.coin_min, config.coin_max)
                if char:
                    await self.usr.add_character(uid, char)
                    await self.usr.update_balance(uid, coins)
                    rarity = RARITY_DISPLAY.get(char.get("rarity"), "🟢 Common") if isinstance(char.get("rarity"), int) else char.get("rarity")
                    results.append({"uid": uid, "type": "crit", "char": char, "rarity": rarity, "coins": coins})
                else:
                    await self.usr.update_balance(uid, coins * 2)
                    results.append({"uid": uid, "type": "coins", "coins": coins * 2, "double": True})
            
            elif roll <= (threshold := threshold + config.char_chance):
                char = await self._get_char(config.rarities)
                if char:
                    await self.usr.add_character(uid, char)
                    rarity = RARITY_DISPLAY.get(char.get("rarity"), "🟢 Common") if isinstance(char.get("rarity"), int) else char.get("rarity")
                    results.append({"uid": uid, "type": "char", "char": char, "rarity": rarity})
                else:
                    coins = random.randint(config.coin_min, config.coin_max)
                    await self.usr.update_balance(uid, coins)
                    results.append({"uid": uid, "type": "coins", "coins": coins})
            
            elif roll <= (threshold := threshold + config.coin_chance):
                coins = random.randint(config.coin_min, config.coin_max)
                await self.usr.update_balance(uid, coins)
                results.append({"uid": uid, "type": "coins", "coins": coins})
            
            elif roll <= (threshold := threshold + config.loss_chance):
                loss = random.randint(config.loss_min, config.loss_max)
                await self.usr.update_balance(uid, -loss)
                results.append({"uid": uid, "type": "loss", "coins": loss})
            
            else:
                results.append({"uid": uid, "type": "nothing"})
        
        return results

    async def _get_char(self, rarities: List[int]) -> Optional[Dict]:
        chars = await collection.find({"rarity": {"$in": rarities}}).to_list(None)
        if not chars:
            rarity_strings = [RARITY_DISPLAY.get(r, f"R{r}") for r in rarities]
            chars = await collection.find({"rarity": {"$in": rarity_strings}}).to_list(None)
        return random.choice(chars) if chars else None

    async def _send_results(self, client: Client, msg: Message, raid: ActiveRaid, results: List[Dict], config: RaidConfig) -> None:
        total_coins = sum(r.get("coins", 0) for r in results if r["type"] in ("crit", "coins"))
        total_chars = sum(1 for r in results if r.get("char"))
        total_crits = sum(1 for r in results if r["type"] == "crit")

        text = (
            f"<blockquote>⚔️ <b>ʀᴀɪᴅ ᴄᴏᴍᴘʟᴇᴛᴇ</b> ⚔️</blockquote>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👥 <b>ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs:</b> <code>{len(results)}</code>\n\n"
            f"<b>🏆 ʟᴏᴏᴛ:</b>\n"
        )

        for r in results:
            user_text = await self._get_mention(client, r["uid"])
            
            if r["type"] == "crit":
                char_id = r["char"].get("id", "???")
                char_name = r["char"].get("name", "Unknown")
                text += (
                    f"• {user_text} — <b>💥 ᴄʀɪᴛɪᴄᴀʟ!</b>\n"
                    f"  └ 🎴 {r['rarity']} • <code>{char_id}</code> • {char_name}\n"
                    f"  └ 💰 <code>{r['coins']} ᴄᴏɪɴs</code>\n"
                )
            elif r["type"] == "char":
                char_id = r["char"].get("id", "???")
                char_name = r["char"].get("name", "Unknown")
                text += f"• {user_text} — 🎴\n  └ {r['rarity']} • <code>{char_id}</code> • {char_name}\n"
            elif r["type"] == "coins":
                double = " (2x!)" if r.get("double") else ""
                text += f"• {user_text} — 💰 <code>{r['coins']}{double}</code>\n"
            elif r["type"] == "loss":
                text += f"• {user_text} — 💀 <code>-{r['coins']}</code>\n"
            else:
                text += f"• {user_text} — ❌\n"

        text += (
            f"\n━━━━━━━━━━━━━━━\n"
            f"💰 <b>ᴛᴏᴛᴀʟ:</b> <code>{total_coins:,}</code>\n"
            f"🎴 <b>ᴄʜᴀʀs:</b> <code>{total_chars}</code>\n"
            f"💥 <b>ᴄʀɪᴛs:</b> <code>{total_crits}</code>\n\n"
            f"<i>ᴘᴏᴡᴇʀᴇᴅ ʙʏ</i> <a href='https://t.me/siyaprobot'>sɪʏᴀ</a>"
        )

        images = [r["char"].get("img_url") for r in results if r.get("char") and r["char"].get("img_url")]
        
        try:
            if images:
                await msg.delete()
                await client.send_photo(raid.chat_id, images[0], caption=text)
            else:
                await msg.edit_text(text)
        except (MessageNotModified, BadRequest):
            pass

    async def _get_mention(self, client: Client, user_id: int) -> str:
        try:
            user = await client.get_users(user_id)
            return f"@{user.username}" if user.username else user.first_name
        except:
            return "Unknown"

# Initialize
db_mgr = RaidDatabase()
usr_mgr = UserManager()
executor = RaidExecutor(db_mgr, usr_mgr)

@shivuu.on_message(filters.command("setraidloss") & filters.user(OWNER_IDS))
async def set_loss(_, m: Message):
    if len(m.command) < 3:
        return await m.reply_text("Usage: /setraidloss <min> <max>")
    try:
        loss_min, loss_max = int(m.command[1]), int(m.command[2])
        if loss_min >= loss_max:
            return await m.reply_text("❌ ᴍɪɴ ᴍᴜsᴛ ʙᴇ ʟᴇss ᴛʜᴀɴ ᴍᴀx")
        await db_mgr.update_config(loss_min=loss_min, loss_max=loss_max)
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
        await db_mgr.update_config(duration=duration)
        await m.reply_text(f"✅ ᴅᴜʀᴀᴛɪᴏɴ sᴇᴛ ᴛᴏ: <code>{duration}</code> sᴇᴄᴏɴᴅs")
    except ValueError:
        await m.reply_text("❌ ɪɴᴠᴀʟɪᴅ ᴠᴀʟᴜᴇ")

@shivuu.on_message(filters.command("raidsettings") & filters.user(OWNER_IDS))
async def show_settings(_, m: Message):
    config = await db_mgr.get_config()
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
    await db_mgr.update_config(**asdict(RaidConfig()))
    await m.reply_text("✅ ʀᴀɪᴅ sᴇᴛᴛɪɴɢs ʀᴇsᴇᴛ ᴛᴏ ᴅᴇғᴀᴜʟᴛ")

@shivuu.on_message(filters.command("raid") & filters.group)
async def start_raid(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if await db_mgr.get_active_for_chat(chat_id):
        return await message.reply_text("⚠️ ᴀ ʀᴀɪᴅ ɪs ᴀʟʀᴇᴀᴅʏ ᴀᴄᴛɪᴠᴇ!")

    config = await db_mgr.get_config()
    can_raid, remaining = await db_mgr.check_cooldown(user_id, chat_id)
    
    if not can_raid:
        return await message.reply_text(f"⏳ ᴄᴏᴏʟᴅᴏᴡɴ: `{remaining // 60}m {remaining % 60}s`")

    user = await usr_mgr.get_user(user_id)
    if user.get("balance", 0) < config.charge:
        return await message.reply_text(f"💰 ɴᴇᴇᴅ `{config.charge}` ᴄᴏɪɴs ᴛᴏ sᴛᴀʀᴛ ʀᴀɪᴅ")

    await usr_mgr.update_balance(user_id, -config.charge)

    raid_id = f"{chat_id}_{int(datetime.utcnow().timestamp() * 1000)}"
    raid = ActiveRaid(raid_id, chat_id, user_id, [user_id])
    await db_mgr.create_raid(raid)
    await db_mgr.set_cooldown(user_id, chat_id, config.cooldown)

    text = (
        f"<blockquote>⚔️ <b>sʜᴀᴅᴏᴡ ʀᴀɪᴅ ʙᴇɢɪɴs!</b> ⚔️</blockquote>\n\n"
        f"<code>ᴊᴏɪɴ ɴᴏᴡ ᴀɴᴅ ᴄᴏʟʟᴇᴄᴛ ᴛʀᴇᴀsᴜʀᴇs!</code>\n\n"
        f"⏱ <b>ᴛɪᴍᴇ:</b> <code>{config.duration}s</code>\n"
        f"💰 <b>ғᴇᴇ:</b> <code>{config.charge} ᴄᴏɪɴs</code>\n"
        f"👥 <b>ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs:</b> <code>1</code>\n\n"
        f"━━━━━━━━━━━━━━━\n<i>ʙʏ</i> {message.from_user.mention}"
    )
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("⚔️ ᴊᴏɪɴ ʀᴀɪᴅ", callback_data=f"jr:{raid_id}")]])
    msg = await message.reply_text(text, reply_markup=btn)

    asyncio.create_task(countdown_updater(client, msg, raid_id, config.duration))
    await asyncio.sleep(config.duration)

    if await db_mgr.get_raid(raid_id):
        await executor.execute(client, msg, raid_id)

async def countdown_updater(client: Client, message: Message, raid_id: str, duration: int):
    config = await db_mgr.get_config()
    start_time = datetime.utcnow()
    
    for i in range(duration):
        await asyncio.sleep(1)
        
        raid = await db_mgr.get_raid(raid_id)
        if not raid:
            break

        elapsed = int((datetime.utcnow() - start_time).total_seconds())
        time_left = max(0, duration - elapsed)
        
        if time_left == 0:
            break

        try:
            starter = await client.get_users(raid.starter_id)
            mention = starter.mention
        except:
            mention = "Unknown"

        text = (
            f"<blockquote>⚔️ <b>sʜᴀᴅᴏᴡ ʀᴀɪᴅ ʙᴇɢɪɴs!</b> ⚔️</blockquote>\n\n"
            f"<code>ᴊᴏɪɴ ɴᴏᴡ ᴀɴᴅ ᴄᴏʟʟᴇᴄᴛ ᴛʀᴇᴀsᴜʀᴇs!</code>\n\n"
            f"⏱ <b>ᴛɪᴍᴇ:</b> <code>{time_left}s</code>\n"
            f"💰 <b>ғᴇᴇ:</b> <code>{config.charge} ᴄᴏɪɴs</code>\n"
            f"👥 <b>ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs:</b> <code>{len(raid.participants)}</code>\n\n"
            f"━━━━━━━━━━━━━━━\n<i>ʙʏ</i> {mention}"
        )
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("⚔️ ᴊᴏɪɴ ʀᴀɪᴅ", callback_data=f"jr:{raid_id}")]])
        
        try:
            await message.edit_text(text, reply_markup=btn)
        except (MessageNotModified, BadRequest):
            pass

@shivuu.on_callback_query(filters.regex(r"^jr:"))
async def join_raid(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    raid_id = query.data.split(":")[1]

    raid = await db_mgr.get_raid(raid_id)
    if not raid:
        return await query.answer("⚠️ ʀᴀɪᴅ ᴇɴᴅᴇᴅ!", show_alert=True)

    if user_id in raid.participants:
        return await query.answer("✅ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ!")

    config = await db_mgr.get_config()
    can_raid, remaining = await db_mgr.check_cooldown(user_id, raid.chat_id)
    
    if not can_raid:
        return await query.answer(f"⏳ ᴄᴏᴏʟᴅᴏᴡɴ: {remaining // 60}m {remaining % 60}s", show_alert=True)

    user = await usr_mgr.get_user(user_id)
    if user.get("balance", 0) < config.charge:
        return await query.answer(f"💰 ɴᴇᴇᴅ {config.charge} ᴄᴏɪɴs", show_alert=True)

    await usr_mgr.update_balance(user_id, -config.charge)
    await db_mgr.add_participant(raid_id, user_id)
    await db_mgr.set_cooldown(user_id, raid.chat_id, config.cooldown)
    await query.answer("⚔️ ᴊᴏɪɴᴇᴅ ʀᴀɪᴅ!")

@shivuu.on_message(filters.command("setraidcharge") & filters.user(OWNER_IDS))
async def set_charge(_, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /setraidcharge <amount>")
    try:
        amount = int(m.command[1])
        await db_mgr.update_config(charge=amount)
        await m.reply_text(f"✅ ᴄʜᴀʀɢᴇ sᴇᴛ ᴛᴏ: <code>{amount}</code> ᴄᴏɪɴs")
    except ValueError:
        await m.reply_text("❌ ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ")

@shivuu.on_message(filters.command("setraidcooldown") & filters.user(OWNER_IDS))
async def set_cooldown_cmd(_, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /setraidcooldown <minutes>")
    try:
        minutes = int(m.command[1])
        await db_mgr.update_config(cooldown=minutes)
        await m.reply_text(f"✅ ᴄᴏᴏʟᴅᴏᴡɴ sᴇᴛ ᴛᴏ: <code>{minutes}</code> ᴍɪɴᴜᴛᴇs")
    except ValueError:
        await m.reply_text("❌ ɪɴᴠᴀʟɪᴅ ᴠᴀʟᴜᴇ")

@shivuu.on_message(filters.command("setraidrarities") & filters.user(OWNER_IDS))
async def set_rarities(_, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /setraidrarities <1,2,3...>")
    try:
        rarities = [int(r.strip()) for r in m.command[1].split(",")]
        await db_mgr.update_config(rarities=rarities)
        names = [RARITY_DISPLAY.get(r, f"R{r}") for r in rarities]
        await m.reply_text(f"✅ ʀᴀʀɪᴛɪᴇs sᴇᴛ:\n" + "\n".join(f"• {n}" for n in names))
    except ValueError:
        await m.reply_text("❌ ɪɴᴠᴀʟɪᴅ ғᴏʀᴍᴀᴛ")

@shivuu.on_message(filters.command("setraidchances") & filters.user(OWNER_IDS))
async def set_chances(_, m: Message):
    if len(m.command) < 6:
        return await m.reply_text("Usage: /setraidchances <char> <coin> <loss> <nothing> <crit>")
    try:
        vals = [int(m.command[i]) for i in range(1, 6)]
        if sum(vals) != 100:
            return await m.reply_text(f"❌ ᴛᴏᴛᴀʟ: {sum(vals)}% (ᴍᴜsᴛ ʙᴇ 100%)")
        
        await db_mgr.update_config(char_chance=vals[0], coin_chance=vals[1], loss_chance=vals[2], 
                                   nothing_chance=vals[3], crit_chance=vals[4])
        await m.reply_text(
            f"✅ ᴄʜᴀɴᴄᴇs ᴜᴘᴅᴀᴛᴇᴅ:\n"
            f"🎴 ᴄʜᴀʀ: {vals[0]}%\n💰 ᴄᴏɪɴ: {vals[1]}%\n"
            f"💀 ʟᴏss: {vals[2]}%\n❌ ɴᴏᴛʜɪɴɢ: {vals[3]}%\n💥 ᴄʀɪᴛ: {vals[4]}%"
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
        await db_mgr.update_config(coin_min=coin_min, coin_max=coin_max)
        await m.reply_text(f"✅ ᴄᴏɪɴ ʀᴀɴɢᴇ: <code>{coin_min}</code> - <code>{coin_max}</code>")
    except ValueError:
        await m.reply_text("❌ ɪɴᴠᴀʟɪᴅ ᴠᴀʟᴜᴇs")