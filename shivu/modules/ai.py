from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
import asyncio
from functools import wraps
import logging
import pytz

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler
from telegram.constants import ParseMode, ChatAction

from shivu import application, db, user_collection

collection = db['anime_characters_lol']
auction_collection = db['auctions']
bid_collection = db['bids']

SUDO_USERS = {"8297659126", "8420981179", "5147822244"}
logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

def get_ist_now() -> datetime:
    return datetime.now(IST)

def typing_action(func):
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        try:
            if update.message:
                await update.message.chat.send_action(ChatAction.TYPING)
        except:
            pass
        return await func(update, context, *args, **kwargs)
    return wrapper

def sudo_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        if str(update.effective_user.id) not in SUDO_USERS:
            await update.message.reply_text("⛔️ ᴀᴜᴛʜᴏʀɪᴢᴀᴛɪᴏɴ ʀᴇǫᴜɪʀᴇᴅ")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

@dataclass
class Character:
    id: str
    name: str
    anime: str
    img_url: str
    rarity: str

    @classmethod
    def from_db(cls, data: dict):
        return cls(
            id=data.get('id', ''),
            name=data.get('name', 'Unknown'),
            anime=data.get('anime', 'Unknown'),
            img_url=data.get('img_url', ''),
            rarity=data.get('rarity', '')
        )

    @property
    def is_video(self) -> bool:
        return self.rarity == "🎥 AMV"

@dataclass
class Auction:
    character_id: str
    starting_bid: int
    current_bid: int
    highest_bidder: Optional[int]
    start_time: datetime
    end_time: datetime
    status: str
    created_by: int
    bid_count: int
    bid_increment: int = 100
    chat_id: Optional[int] = None
    auto_extend: bool = True

    @classmethod
    def from_db(cls, data: dict):
        start_time = data.get('start_time', get_ist_now())
        end_time = data.get('end_time', get_ist_now())
        
        if isinstance(start_time, datetime):
            start_time = IST.localize(start_time) if start_time.tzinfo is None else start_time.astimezone(IST)
        if isinstance(end_time, datetime):
            end_time = IST.localize(end_time) if end_time.tzinfo is None else end_time.astimezone(IST)
        
        return cls(
            character_id=data.get('character_id', ''),
            starting_bid=data.get('starting_bid', 0),
            current_bid=data.get('current_bid', 0),
            highest_bidder=data.get('highest_bidder'),
            start_time=start_time,
            end_time=end_time,
            status=data.get('status', 'active'),
            created_by=data.get('created_by', 0),
            bid_count=data.get('bid_count', 0),
            bid_increment=data.get('bid_increment', 100),
            chat_id=data.get('chat_id'),
            auto_extend=data.get('auto_extend', True)
        )

    @property
    def time_remaining(self) -> timedelta:
        return self.end_time - get_ist_now()

    @property
    def is_active(self) -> bool:
        return self.status == "active" and get_ist_now() < self.end_time

    @property
    def min_next_bid(self) -> int:
        increment = max(self.bid_increment, int(self.current_bid * 0.05))
        return self.current_bid + increment

    @property
    def is_ending_soon(self) -> bool:
        return 0 < self.time_remaining.total_seconds() < 300

    def format_time_left(self) -> str:
        if not self.is_active:
            return "⏰ ᴇɴᴅᴇᴅ"
        
        td = self.time_remaining
        s = int(td.total_seconds())
        
        if s < 0:
            return "⏰ ᴇɴᴅᴇᴅ"
        
        d, h, m = s // 86400, (s % 86400) // 3600, (s % 3600) // 60
        
        if d > 0:
            return f"🕐 {d}ᴅ {h}ʜ {m}ᴍ"
        elif h > 0:
            return f"🕐 {h}ʜ {m}ᴍ"
        elif m > 5:
            return f"🕐 {m}ᴍ"
        else:
            return f"⚡ {m}ᴍ {s % 60}ꜱ"

@dataclass
class Bid:
    auction_id: str
    user_id: int
    amount: int
    timestamp: datetime
    user_name: str = "Anonymous"

    @classmethod
    def from_db(cls, data: dict):
        timestamp = data.get('timestamp', get_ist_now())
        if isinstance(timestamp, datetime):
            timestamp = IST.localize(timestamp) if timestamp.tzinfo is None else timestamp.astimezone(IST)
        
        return cls(
            auction_id=str(data.get('auction_id', '')),
            user_id=data.get('user_id', 0),
            amount=data.get('amount', 0),
            timestamp=timestamp,
            user_name=data.get('user_name', 'Anonymous')
        )

class AuctionUI:
    @staticmethod
    def build_caption(character: Character, auction: Auction, top_bidders: Optional[List[Bid]] = None) -> str:
        status_emoji = "🔥" if auction.is_ending_soon else "✅"
        status_text = "ᴇɴᴅɪɴɢ ꜱᴏᴏɴ!" if auction.is_ending_soon else "ᴀᴄᴛɪᴠᴇ"
        
        lines = [
            "━━━━━━━━━━━━━━━━",
            f"🔨 <b>ʟɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ</b>",
            f"{status_emoji} <b>{status_text}</b>",
            "━━━━━━━━━━━━━━━━\n",
            f"✨ <b>{character.name}</b>",
            f"🎭 <code>{character.anime}</code>\n",
            f"💰 ᴄᴜʀʀᴇɴᴛ: <b>{auction.current_bid:,}</b> ɢᴏʟᴅ",
            f"📊 ᴍɪɴɪᴍᴜᴍ: <code>{auction.min_next_bid:,}</code>",
            f"🔨 ᴛᴏᴛᴀʟ ʙɪᴅꜱ: <code>{auction.bid_count}</code>",
            f"\n{auction.format_time_left()}\n"
        ]
        
        if auction.highest_bidder:
            lines.append(f"👑 ʟᴇᴀᴅᴇʀ: <code>{auction.highest_bidder}</code>\n")
        else:
            lines.append("👑 ɴᴏ ʙɪᴅꜱ ʏᴇᴛ\n")
        
        if top_bidders and len(top_bidders) > 0:
            lines.append("━━━━━━━━━━━━━━━━")
            lines.append("<b>🏆 ᴛᴏᴘ ʙɪᴅᴅᴇʀꜱ</b>")
            for i, bid in enumerate(top_bidders[:3], 1):
                medal = ["🥇", "🥈", "🥉"][i-1]
                lines.append(f"{medal} {bid.amount:,} ɢᴏʟᴅ")
            lines.append("━━━━━━━━━━━━━━━━\n")
        
        quick_bids = [
            auction.min_next_bid,
            auction.min_next_bid + auction.bid_increment,
            auction.min_next_bid + (auction.bid_increment * 2)
        ]
        
        lines.extend([
            "💬 <b>ǫᴜɪᴄᴋ ʙɪᴅ</b>",
            " • ".join([f"<code>/bid {b}</code>" for b in quick_bids])
        ])
        
        return "\n".join(lines)

    @staticmethod
    def build_stats_message(auction: Auction, character: Character, top_bidders: List[Bid]) -> str:
        lines = [
            "━━━━━━━━━━━━━━━━",
            "📊 <b>ᴀᴜᴄᴛɪᴏɴ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ</b>",
            "━━━━━━━━━━━━━━━━\n",
            f"✨ <b>{character.name}</b>",
            f"🎭 {character.anime}\n",
            f"💰 ᴄᴜʀʀᴇɴᴛ: <b>{auction.current_bid:,}</b>",
            f"📈 ɴᴇxᴛ ᴍɪɴ: <code>{auction.min_next_bid:,}</code>",
            f"🔨 ᴛᴏᴛᴀʟ ʙɪᴅꜱ: <code>{auction.bid_count}</code>",
            f"⏱ {auction.format_time_left()}\n"
        ]
        
        if top_bidders:
            lines.append("━━━━━━━━━━━━━━━━")
            lines.append("<b>🏆 ᴛᴏᴘ ʙɪᴅᴅᴇʀꜱ</b>\n")
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            for i, bid in enumerate(top_bidders[:5], 1):
                medal = medals[i-1] if i <= 5 else "•"
                lines.append(f"{medal} <b>{bid.amount:,}</b> • {bid.user_name}")
            lines.append("━━━━━━━━━━━━━━━━")
        
        return "\n".join(lines)

class AuctionManager:
    _lock = asyncio.Lock()

    @staticmethod
    async def get_active_auction() -> Optional[dict]:
        return await auction_collection.find_one({
            "status": "active",
            "end_time": {"$gt": get_ist_now()}
        })

    @staticmethod
    async def create_auction(
        char_id: str,
        starting_bid: int,
        duration_hours: int,
        created_by: int,
        chat_id: int,
        bid_increment: int = 100
    ) -> Tuple[bool, str]:
        try:
            character = await collection.find_one({"id": char_id})
            if not character:
                return False, "⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ"

            active = await AuctionManager.get_active_auction()
            if active:
                return False, "⚠️ ᴀɴᴏᴛʜᴇʀ ᴀᴜᴄᴛɪᴏɴ ɪꜱ ᴀᴄᴛɪᴠᴇ"

            if starting_bid < 100:
                return False, "⚠️ ᴍɪɴɪᴍᴜᴍ ꜱᴛᴀʀᴛɪɴɢ ʙɪᴅ: 100"

            if duration_hours < 1 or duration_hours > 168:
                return False, "⚠️ ᴅᴜʀᴀᴛɪᴏɴ ᴍᴜꜱᴛ ʙᴇ 1-168 ʜᴏᴜʀꜱ"

            start_time = get_ist_now()
            auction_data = {
                "character_id": char_id,
                "starting_bid": starting_bid,
                "current_bid": starting_bid,
                "highest_bidder": None,
                "previous_bidder": None,
                "start_time": start_time,
                "end_time": start_time + timedelta(hours=duration_hours),
                "status": "active",
                "created_by": created_by,
                "chat_id": chat_id,
                "bid_count": 0,
                "bid_increment": bid_increment,
                "auto_extend": True
            }

            await auction_collection.insert_one(auction_data)
            return True, f"✅ ᴀᴜᴄᴛɪᴏɴ ꜱᴛᴀʀᴛᴇᴅ ꜰᴏʀ <b>{character['name']}</b>"
        except Exception as e:
            logger.error(f"Create auction error: {e}")
            return False, "⚠️ ꜰᴀɪʟᴇᴅ ᴛᴏ ᴄʀᴇᴀᴛᴇ ᴀᴜᴄᴛɪᴏɴ"

    @staticmethod
    async def place_bid(user_id: int, amount: int, user_name: str = "Anonymous") -> Tuple[bool, str, Optional[int]]:
        async with AuctionManager._lock:
            try:
                auction_data = await AuctionManager.get_active_auction()
                if not auction_data:
                    return False, "⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ", None

                auction = Auction.from_db(auction_data)

                if not auction.is_active:
                    return False, "⏰ ᴀᴜᴄᴛɪᴏɴ ʜᴀꜱ ᴇɴᴅᴇᴅ", None

                if user_id == auction.highest_bidder:
                    return False, "👑 ʏᴏᴜ'ʀᴇ ᴀʟʀᴇᴀᴅʏ ᴡɪɴɴɪɴɢ", None

                if amount < auction.min_next_bid:
                    return False, f"⚠️ ᴍɪɴɪᴍᴜᴍ: <b>{auction.min_next_bid:,}</b> ɢᴏʟᴅ", None

                user_data = await user_collection.find_one({"id": user_id})
                if not user_data:
                    return False, "⚠️ ᴜꜱᴇʀ ɴᴏᴛ ʀᴇɢɪꜱᴛᴇʀᴇᴅ", None

                balance = user_data.get("balance", 0)
                reserved = user_data.get("auction_reserved", 0)
                available = balance - reserved

                if available < amount:
                    return False, (
                        f"⚠️ <b>ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ</b>\n\n"
                        f"💰 ʀᴇǫᴜɪʀᴇᴅ: <code>{amount:,}</code>\n"
                        f"💳 ᴀᴠᴀɪʟᴀʙʟᴇ: <code>{available:,}</code>\n"
                        f"🔒 ʀᴇꜱᴇʀᴠᴇᴅ: <code>{reserved:,}</code>"
                    ), None

                previous_bidder = auction.highest_bidder
                previous_bid = auction.current_bid

                if previous_bidder:
                    await user_collection.update_one(
                        {"id": previous_bidder},
                        {"$inc": {"auction_reserved": -previous_bid}}
                    )

                await user_collection.update_one(
                    {"id": user_id},
                    {"$inc": {"auction_reserved": amount}}
                )

                update_data = {
                    "current_bid": amount,
                    "highest_bidder": user_id,
                    "previous_bidder": previous_bidder
                }

                if auction.auto_extend and auction.is_ending_soon:
                    extension_time = get_ist_now() + timedelta(minutes=5)
                    if extension_time > auction.end_time:
                        update_data["end_time"] = extension_time

                await auction_collection.update_one(
                    {"_id": auction_data["_id"]},
                    {
                        "$set": update_data,
                        "$inc": {"bid_count": 1}
                    }
                )

                await bid_collection.insert_one({
                    "auction_id": str(auction_data["_id"]),
                    "user_id": user_id,
                    "user_name": user_name,
                    "amount": amount,
                    "timestamp": get_ist_now()
                })

                return True, f"✅ <b>ʙɪᴅ ᴘʟᴀᴄᴇᴅ</b>\n\n💰 <b>{amount:,}</b> ɢᴏʟᴅ\n👑 ʏᴏᴜ'ʀᴇ ʟᴇᴀᴅɪɴɢ!", previous_bidder
            except Exception as e:
                logger.error(f"Bid error: {e}")
                return False, "⚠️ ʙɪᴅ ꜰᴀɪʟᴇᴅ", None

    @staticmethod
    async def end_auction() -> Tuple[bool, str, Optional[int], Optional[int]]:
        try:
            auction_data = await auction_collection.find_one({"status": "active"})
            if not auction_data:
                return False, "⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ", None, None

            auction = Auction.from_db(auction_data)
            winner_id = auction.highest_bidder
            chat_id = auction.chat_id

            if winner_id:
                character = await collection.find_one({"id": auction.character_id})

                await user_collection.update_one(
                    {"id": winner_id},
                    {
                        "$inc": {
                            "balance": -auction.current_bid,
                            "auction_reserved": -auction.current_bid
                        },
                        "$push": {"characters": character['id']}
                    }
                )

                await auction_collection.update_one(
                    {"_id": auction_data["_id"]},
                    {"$set": {"status": "ended", "end_time": get_ist_now()}}
                )

                message = (
                    "━━━━━━━━━━━━━━━━\n"
                    "🎊 <b>ᴀᴜᴄᴛɪᴏɴ ᴇɴᴅᴇᴅ</b>\n"
                    "━━━━━━━━━━━━━━━━\n\n"
                    f"✨ <b>{character['name']}</b>\n"
                    f"🎭 {character['anime']}\n\n"
                    f"👑 <b>ᴡɪɴɴᴇʀ:</b> <a href='tg://user?id={winner_id}'>{winner_id}</a>\n"
                    f"💰 <b>ꜰɪɴᴀʟ ʙɪᴅ:</b> {auction.current_bid:,} ɢᴏʟᴅ\n"
                    f"🔨 <b>ᴛᴏᴛᴀʟ ʙɪᴅꜱ:</b> {auction.bid_count}\n"
                    "━━━━━━━━━━━━━━━━"
                )
                return True, message, winner_id, chat_id
            else:
                await auction_collection.update_one(
                    {"_id": auction_data["_id"]},
                    {"$set": {"status": "ended", "end_time": get_ist_now()}}
                )
                return True, "⚠️ ᴀᴜᴄᴛɪᴏɴ ᴇɴᴅᴇᴅ • ɴᴏ ʙɪᴅꜱ", None, chat_id
        except Exception as e:
            logger.error(f"End auction error: {e}")
            return False, "⚠️ ꜰᴀɪʟᴇᴅ ᴛᴏ ᴇɴᴅ ᴀᴜᴄᴛɪᴏɴ", None, None

    @staticmethod
    async def get_top_bidders(auction_id: str, limit: int = 5) -> List[Bid]:
        try:
            bids = await bid_collection.find(
                {"auction_id": str(auction_id)}
            ).sort("amount", -1).limit(limit).to_list(length=limit)
            return [Bid.from_db(bid) for bid in bids]
        except Exception as e:
            logger.error(f"Get top bidders error: {e}")
            return []

async def check_expired_auctions():
    await asyncio.sleep(10)
    
    while True:
        try:
            auction_data = await auction_collection.find_one({
                "status": "active",
                "end_time": {"$lt": get_ist_now()}
            })
            
            if auction_data:
                logger.info("Auto-ending expired auction")
                success, message, winner_id, chat_id = await AuctionManager.end_auction()
                
                if success and chat_id:
                    try:
                        await application.bot.send_message(
                            chat_id=chat_id,
                            text=message,
                            parse_mode=ParseMode.HTML
                        )
                    except Exception as e:
                        logger.error(f"Notification failed: {e}")
        except Exception as e:
            logger.error(f"Auto-end check error: {e}")
        
        await asyncio.sleep(60)

async def send_auction_media(message, character: Character, caption: str):
    try:
        if character.is_video:
            await message.reply_video(
                video=character.img_url,
                caption=caption,
                parse_mode=ParseMode.HTML
            )
        else:
            await message.reply_photo(
                photo=character.img_url,
                caption=caption,
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Media send error: {e}")
        await message.reply_text(caption, parse_mode=ParseMode.HTML)

@typing_action
async def auction_command(update: Update, context: CallbackContext):
    try:
        auction_data = await AuctionManager.get_active_auction()
        if not auction_data:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━\n"
                "🔨 <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ</b>\n"
                "━━━━━━━━━━━━━━━━",
                parse_mode=ParseMode.HTML
            )
            return

        auction = Auction.from_db(auction_data)
        character_data = await collection.find_one({"id": auction.character_id})
        
        if not character_data:
            await update.message.reply_text("⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ")
            return

        character = Character.from_db(character_data)
        top_bidders = await AuctionManager.get_top_bidders(auction_data["_id"])
        caption = AuctionUI.build_caption(character, auction, top_bidders)
        
        await send_auction_media(update.message, character, caption)
    except Exception as e:
        logger.error(f"Auction view error: {e}")
        await update.message.reply_text("⚠️ ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ ᴀᴜᴄᴛɪᴏɴ")

@typing_action
@sudo_required
async def start_auction_command(update: Update, context: CallbackContext):
    try:
        if len(context.args) < 3:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━\n"
                "📋 <b>ᴜꜱᴀɢᴇ</b>\n"
                "━━━━━━━━━━━━━━━━\n\n"
                "<code>/astart &lt;id&gt; &lt;starting_bid&gt; &lt;hours&gt; [increment]</code>\n\n"
                "• <b>id:</b> character ID\n"
                "• <b>starting_bid:</b> minimum 100\n"
                "• <b>hours:</b> 1-168\n"
                "• <b>increment:</b> optional (default: 100)",
                parse_mode=ParseMode.HTML
            )
            return

        char_id = context.args[0]
        starting_bid = int(context.args[1])
        duration = int(context.args[2])
        bid_increment = int(context.args[3]) if len(context.args) >= 4 else 100

        success, message = await AuctionManager.create_auction(
            char_id, starting_bid, duration,
            update.effective_user.id,
            update.effective_chat.id,
            bid_increment
        )
        
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)

        if success:
            await asyncio.sleep(0.5)
            auction_data = await AuctionManager.get_active_auction()
            if auction_data:
                auction = Auction.from_db(auction_data)
                character_data = await collection.find_one({"id": auction.character_id})
                if character_data:
                    character = Character.from_db(character_data)
                    caption = AuctionUI.build_caption(character, auction)
                    await send_auction_media(update.message, character, caption)
    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ꜰᴏʀᴍᴀᴛ")
    except Exception as e:
        logger.error(f"Start auction error: {e}")
        await update.message.reply_text("⚠️ ꜰᴀɪʟᴇᴅ ᴛᴏ ꜱᴛᴀʀᴛ ᴀᴜᴄᴛɪᴏɴ")

@typing_action
@sudo_required
async def end_auction_command(update: Update, context: CallbackContext):
    try:
        success, message, winner_id, chat_id = await AuctionManager.end_auction()
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"End auction command error: {e}")
        await update.message.reply_text("⚠️ ꜰᴀɪʟᴇᴅ ᴛᴏ ᴇɴᴅ ᴀᴜᴄᴛɪᴏɴ")

@typing_action
async def bid_command(update: Update, context: CallbackContext):
    try:
        if not context.args:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━\n"
                "💰 <b>ᴘʟᴀᴄᴇ ʏᴏᴜʀ ʙɪᴅ</b>\n"
                "━━━━━━━━━━━━━━━━\n\n"
                "<code>/bid &lt;amount&gt;</code>\n\n"
                "ᴇxᴀᴍᴘʟᴇ: <code>/bid 5000</code>",
                parse_mode=ParseMode.HTML
            )
            return

        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or "Anonymous"
        amount = int(context.args[0])

        if amount <= 0:
            await update.message.reply_text("⚠️ ʙɪᴅ ᴍᴜꜱᴛ ʙᴇ ᴘᴏꜱɪᴛɪᴠᴇ")
            return

        success, message, previous_bidder = await AuctionManager.place_bid(user_id, amount, user_name)
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)

        if success and previous_bidder:
            try:
                await context.bot.send_message(
                    chat_id=previous_bidder,
                    text=f"⚠️ <b>ᴏᴜᴛʙɪᴅ</b>\n\n💰 ɴᴇᴡ ʙɪᴅ: <b>{amount:,}</b> ɢᴏʟᴅ\n\n🔨 ʀᴇᴛᴜʀɴ ᴛᴏ ᴀᴜᴄᴛɪᴏɴ ᴛᴏ ʙɪᴅ ᴀɢᴀɪɴ!",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Outbid notification error: {e}")
    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ")
    except Exception as e:
        logger.error(f"Bid command error: {e}")
        await update.message.reply_text("⚠️ ʙɪᴅ ꜰᴀɪʟᴇᴅ")

@typing_action
async def auction_stats_command(update: Update, context: CallbackContext):
    try:
        auction_data = await AuctionManager.get_active_auction()
        if not auction_data:
            await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ")
            return

        auction = Auction.from_db(auction_data)
        character_data = await collection.find_one({"id": auction.character_id})
        
        if not character_data:
            await update.message.reply_text("⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ")
            return

        character = Character.from_db(character_data)
        top_bidders = await AuctionManager.get_top_bidders(auction_data["_id"], 5)
        message = AuctionUI.build_stats_message(auction, character, top_bidders)
        
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Stats error: {e}")
        await update.message.reply_text("⚠️ ꜰᴀɪʟᴇᴅ ᴛᴏ ʟᴏᴀᴅ ꜱᴛᴀᴛꜱ")

@typing_action
async def my_bids_command(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id
        user_data = await user_collection.find_one({"id": user_id})
        
        if not user_data:
            await update.message.reply_text("⚠️ ᴜꜱᴇʀ ɴᴏᴛ ʀᴇɢɪꜱᴛᴇʀᴇᴅ")
            return

        balance = user_data.get("balance", 0)
        reserved = user_data.get("auction_reserved", 0)
        available = balance - reserved

        lines = [
            "━━━━━━━━━━━━━━━━",
            "💼 <b>ʏᴏᴜʀ ꜱᴛᴀᴛᴜꜱ</b>",
            "━━━━━━━━━━━━━━━━\n",
            f"💰 ʙᴀʟᴀɴᴄᴇ: <b>{balance:,}</b> ɢᴏʟᴅ",
            f"🔒 ʀᴇꜱᴇʀᴠᴇᴅ: <code>{reserved:,}</code>",
            f"✅ ᴀᴠᴀɪʟᴀʙʟᴇ: <b>{available:,}</b>\n",
            "━━━━━━━━━━━━━━━━\n"
        ]

        auction_data = await AuctionManager.get_active_auction()
        if auction_data:
            auction = Auction.from_db(auction_data)
            if auction.highest_bidder == user_id:
                lines.extend([
                    "👑 <b>ʏᴏᴜ'ʀᴇ ᴡɪɴɴɪɴɢ</b>\n",
                    f"💎 ʏᴏᴜʀ ʙɪᴅ: <b>{auction.current_bid:,}</b>",
                    f"⏱ {auction.format_time_left()}"
                ])
            else:
                user_bid = await bid_collection.find_one({
                    "auction_id": str(auction_data["_id"]),
                    "user_id": user_id
                })
                if user_bid:
                    lines.extend([
                        "📊 <b>ʏᴏᴜʀ ʙɪᴅ ꜱᴛᴀᴛᴜꜱ</b>\n",
                        f"💰 ᴄᴜʀʀᴇɴᴛ ʜɪɢʜ: <b>{auction.current_bid:,}</b>",
                        f"📈 ɴᴇxᴛ ᴍɪɴ: <code>{auction.min_next_bid:,}</code>",
                        f"🔨 ʏᴏᴜʀ ʟᴀꜱᴛ: <code>{user_bid['amount']:,}</code>"
                    ])
                else:
                    lines.append("ℹ️ ɴᴏ ʙɪᴅꜱ ʏᴇᴛ • ᴜꜱᴇ /auction")
        else:
            lines.append("ℹ️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ")

        lines.append("━━━━━━━━━━━━━━━━")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"My bids error: {e}")
        await update.message.reply_text("⚠️ ꜰᴀɪʟᴇᴅ ᴛᴏ ʟᴏᴀᴅ ꜱᴛᴀᴛᴜꜱ")

application.add_handler(CommandHandler("auction", auction_command, block=False))
application.add_handler(CommandHandler("astart", start_auction_command, block=False))
application.add_handler(CommandHandler("aend", end_auction_command, block=False))
application.add_handler(CommandHandler("bid", bid_command, block=False))
application.add_handler(CommandHandler("astats", auction_stats_command, block=False))
application.add_handler(CommandHandler("mybids", my_bids_command, block=False))
