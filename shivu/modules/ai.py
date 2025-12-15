from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
import asyncio
from functools import wraps
import logging
import pytz

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.error import BadRequest, TimedOut, NetworkError
from telegram.constants import ParseMode, ChatAction

from shivu import application, db, user_collection

collection = db['anime_characters_lol']
auction_collection = db['auctions']
bid_collection = db['bids']

SUDO_USERS = {"8297659126", "8420981179", "5147822244"}

logger = logging.getLogger(__name__)

IST = pytz.timezone('Asia/Kolkata')


def get_ist_now():
    return datetime.now(IST)


def typing_action(func):
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        if update.message:
            await update.message.chat.send_action(ChatAction.TYPING)
        return await func(update, context, *args, **kwargs)
    return wrapper


class AuctionStatus(Enum):
    ACTIVE = "active"
    ENDED = "ended"
    CANCELLED = "cancelled"


@dataclass
class Character:
    id: str
    name: str
    anime: str
    img_url: str
    rarity: str

    @classmethod
    def from_db(cls, data: dict) -> 'Character':
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

    def to_dict(self) -> dict:
        return asdict(self)


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
    auto_extend: bool = True

    @classmethod
    def from_db(cls, data: dict) -> 'Auction':
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        
        if isinstance(start_time, datetime) and start_time.tzinfo is None:
            start_time = IST.localize(start_time)
        elif isinstance(start_time, datetime):
            start_time = start_time.astimezone(IST)
        else:
            start_time = get_ist_now()
            
        if isinstance(end_time, datetime) and end_time.tzinfo is None:
            end_time = IST.localize(end_time)
        elif isinstance(end_time, datetime):
            end_time = end_time.astimezone(IST)
        else:
            end_time = get_ist_now()
        
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
            auto_extend=data.get('auto_extend', True)
        )

    @property
    def time_remaining(self) -> timedelta:
        return self.end_time - get_ist_now()

    @property
    def is_active(self) -> bool:
        return (self.status == AuctionStatus.ACTIVE.value and 
                get_ist_now() < self.end_time)

    @property
    def min_next_bid(self) -> int:
        return self.current_bid + max(self.bid_increment, int(self.current_bid * 0.05))

    @property
    def is_ending_soon(self) -> bool:
        return self.time_remaining.total_seconds() < 300

    def format_time_left(self) -> str:
        if not self.is_active:
            return "⏰ ᴇɴᴅᴇᴅ"

        td = self.time_remaining
        total_seconds = int(td.total_seconds())

        if total_seconds < 0:
            return "⏰ ᴇɴᴅᴇᴅ"

        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if days > 0:
            return f"🕐 {days}ᴅ {hours}ʜ"
        elif hours > 0:
            return f"🕐 {hours}ʜ {minutes}ᴍ"
        elif minutes > 0:
            return f"🕐 {minutes}ᴍ {seconds}ꜱ"
        else:
            return f"⚡ {seconds}ꜱ"

    def to_dict(self) -> dict:
        data = asdict(self)
        data['start_time'] = self.start_time
        data['end_time'] = self.end_time
        return data


@dataclass
class Bid:
    auction_id: str
    user_id: int
    amount: int
    timestamp: datetime
    user_name: str = "Anonymous"

    @classmethod
    def from_db(cls, data: dict) -> 'Bid':
        timestamp = data.get('timestamp', get_ist_now())
        if isinstance(timestamp, datetime) and timestamp.tzinfo is None:
            timestamp = IST.localize(timestamp)
        elif isinstance(timestamp, datetime):
            timestamp = timestamp.astimezone(IST)
            
        return cls(
            auction_id=str(data.get('auction_id', '')),
            user_id=data.get('user_id', 0),
            amount=data.get('amount', 0),
            timestamp=timestamp,
            user_name=data.get('user_name', 'Anonymous')
        )


class AuctionUI:

    @staticmethod
    def build_caption(character: Character, auction: Auction, 
                     top_bidders: List[Bid] = None) -> str:

        header = "🔨 <b>ʟɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ</b>\n\n"

        status_indicator = "🔥 ᴇɴᴅɪɴɢ ꜱᴏᴏɴ!" if auction.is_ending_soon else "✅ ᴀᴄᴛɪᴠᴇ"

        body_lines = [
            f"<b>{status_indicator}</b>\n",
            f"✨ <b>{character.name}</b>",
            f"🎭 <code>{character.anime}</code>\n",
            f"💰 ᴄᴜʀʀᴇɴᴛ ʙɪᴅ: <b>{auction.current_bid:,}</b> ɢᴏʟᴅ",
            f"📊 ɴᴇxᴛ ᴍɪɴ: <code>{auction.min_next_bid:,}</code> ɢᴏʟᴅ",
            f"🔨 ᴛᴏᴛᴀʟ ʙɪᴅꜱ: <code>{auction.bid_count}</code>",
            f"\n{auction.format_time_left()}\n"
        ]

        if auction.highest_bidder:
            body_lines.append(f"👑 ʟᴇᴀᴅᴇʀ: <code>ᴜꜱᴇʀ {auction.highest_bidder}</code>\n")
        else:
            body_lines.append("👑 ɴᴏ ʙɪᴅꜱ ʏᴇᴛ!\n")

        if top_bidders and len(top_bidders) > 1:
            body_lines.append("<b>🏆 ᴛᴏᴘ ʙɪᴅᴅᴇʀꜱ:</b>")
            for i, bid in enumerate(top_bidders[:3], 1):
                medal = ["🥇", "🥈", "🥉"][i-1]
                body_lines.append(f"{medal} {bid.amount:,} ɢᴏʟᴅ")
            body_lines.append("")

        footer = [
            "💬 <b>ǫᴜɪᴄᴋ ʙɪᴅ:</b>",
            f"<code>/bid {auction.min_next_bid}</code>",
            f"<code>/bid {auction.min_next_bid + auction.bid_increment}</code>",
            f"<code>/bid {auction.min_next_bid + (auction.bid_increment * 2)}</code>"
        ]

        return "\n".join([header] + body_lines + footer)


class AuctionManager:
    _lock = asyncio.Lock()

    @staticmethod
    async def is_sudo(user_id: int) -> bool:
        return str(user_id) in SUDO_USERS

    @staticmethod
    async def get_active_auction() -> Optional[dict]:
        return await auction_collection.find_one({
            "status": "active",
            "end_time": {"$gt": get_ist_now()}
        })

    @staticmethod
    async def create_auction(char_id: str, starting_bid: int, 
                           duration_hours: int, created_by: int,
                           bid_increment: int = 100,
                           auto_extend: bool = True) -> tuple[bool, str]:

        character = await collection.find_one({"id": char_id})
        if not character:
            return False, "⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ ɪɴ ᴅᴀᴛᴀʙᴀꜱᴇ"

        active = await AuctionManager.get_active_auction()
        if active:
            return False, "⚠️ ᴀɴᴏᴛʜᴇʀ ᴀᴜᴄᴛɪᴏɴ ɪꜱ ᴀʟʀᴇᴀᴅʏ ᴀᴄᴛɪᴠᴇ"

        start_time = get_ist_now()
        end_time = start_time + timedelta(hours=duration_hours)

        auction_data = {
            "character_id": char_id,
            "starting_bid": starting_bid,
            "current_bid": starting_bid,
            "highest_bidder": None,
            "start_time": start_time,
            "end_time": end_time,
            "status": "active",
            "created_by": created_by,
            "bid_count": 0,
            "bid_increment": bid_increment,
            "auto_extend": auto_extend
        }

        await auction_collection.insert_one(auction_data)

        return True, f"✅ ᴀᴜᴄᴛɪᴏɴ ꜱᴛᴀʀᴛᴇᴅ ꜰᴏʀ {character['name']}"

    @staticmethod
    async def place_bid(user_id: int, amount: int, user_name: str = "Anonymous") -> tuple[bool, str]:
        async with AuctionManager._lock:
            auction_data = await AuctionManager.get_active_auction()
            if not auction_data:
                return False, "⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ ʀᴜɴɴɪɴɢ"

            auction = Auction.from_db(auction_data)

            if not auction.is_active:
                return False, "⏰ ᴀᴜᴄᴛɪᴏɴ ʜᴀꜱ ᴇɴᴅᴇᴅ"

            if user_id == auction.highest_bidder:
                return False, "👑 ʏᴏᴜ'ʀᴇ ᴀʟʀᴇᴀᴅʏ ᴛʜᴇ ʜɪɢʜᴇꜱᴛ ʙɪᴅᴅᴇʀ!"

            if amount < auction.min_next_bid:
                return False, f"⚠️ ᴍɪɴɪᴍᴜᴍ ʙɪᴅ: <b>{auction.min_next_bid:,}</b> ɢᴏʟᴅ"

            user_data = await user_collection.find_one({"id": user_id})
            balance = user_data.get("balance", 0) if user_data else 0

            if balance < amount:
                deficit = amount - balance
                return False, (
                    f"⚠️ <b>ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ</b>\n\n"
                    f"💰 ʀᴇǫᴜɪʀᴇᴅ: <code>{amount:,}</code> ɢᴏʟᴅ\n"
                    f"💳 ʙᴀʟᴀɴᴄᴇ: <code>{balance:,}</code> ɢᴏʟᴅ\n"
                    f"📉 ɴᴇᴇᴅ: <code>{deficit:,}</code> ᴍᴏʀᴇ ɢᴏʟᴅ"
                )

            if auction.auto_extend and auction.is_ending_soon:
                new_end_time = get_ist_now() + timedelta(minutes=5)
                if new_end_time > auction.end_time:
                    await auction_collection.update_one(
                        {"_id": auction_data["_id"]},
                        {"$set": {"end_time": new_end_time}}
                    )

            await auction_collection.update_one(
                {"_id": auction_data["_id"]},
                {
                    "$set": {
                        "current_bid": amount,
                        "highest_bidder": user_id
                    },
                    "$inc": {"bid_count": 1}
                }
            )

            await bid_collection.insert_one({
                "auction_id": auction_data["_id"],
                "user_id": user_id,
                "user_name": user_name,
                "amount": amount,
                "timestamp": get_ist_now()
            })

            msg = "✅ <b>ʙɪᴅ ᴘʟᴀᴄᴇᴅ!</b>\n\n"
            msg += f"💰 ʏᴏᴜʀ ʙɪᴅ: <b>{amount:,}</b> ɢᴏʟᴅ\n"
            msg += f"👑 ʏᴏᴜ'ʀᴇ ɴᴏᴡ ʟᴇᴀᴅɪɴɢ!"

            return True, msg

    @staticmethod
    async def end_auction() -> tuple[bool, str, Optional[int]]:
        auction_data = await auction_collection.find_one({"status": "active"})
        if not auction_data:
            return False, "⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ ꜰᴏᴜɴᴅ", None

        auction = Auction.from_db(auction_data)
        winner_id = auction.highest_bidder

        if winner_id:
            character = await collection.find_one({"id": auction.character_id})

            await user_collection.update_one(
                {"id": winner_id},
                {
                    "$inc": {"balance": -auction.current_bid},
                    "$push": {"characters": character}
                }
            )

            await auction_collection.update_one(
                {"_id": auction_data["_id"]},
                {"$set": {"status": "ended", "end_time": get_ist_now()}}
            )

            message = (
                "🎊 <b>ᴀᴜᴄᴛɪᴏɴ ᴇɴᴅᴇᴅ!</b>\n\n"
                f"✨ <b>{character['name']}</b>\n"
                f"👑 ᴡɪɴɴᴇʀ: <a href='tg://user?id={winner_id}'>ᴜꜱᴇʀ {winner_id}</a>\n"
                f"💰 ꜰɪɴᴀʟ ᴘʀɪᴄᴇ: <b>{auction.current_bid:,}</b> ɢᴏʟᴅ\n"
                f"🔨 ᴛᴏᴛᴀʟ ʙɪᴅꜱ: <code>{auction.bid_count}</code>"
            )
            return True, message, winner_id
        else:
            await auction_collection.update_one(
                {"_id": auction_data["_id"]},
                {"$set": {"status": "ended"}}
            )
            return True, "⚠️ ᴀᴜᴄᴛɪᴏɴ ᴇɴᴅᴇᴅ ᴡɪᴛʜ ɴᴏ ʙɪᴅꜱ", None

    @staticmethod
    async def get_top_bidders(auction_id) -> List[Bid]:
        bids = await bid_collection.find(
            {"auction_id": auction_id}
        ).sort("amount", -1).limit(5).to_list(5)

        return [Bid.from_db(bid) for bid in bids]


@typing_action
async def auction_view_command(update: Update, context: CallbackContext):
    auction_data = await AuctionManager.get_active_auction()

    if not auction_data:
        msg = "🔨 <b>ɴᴏ ᴀᴜᴄᴛɪᴏɴ</b>\n\n"
        msg += "ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ\n"
        msg += "ᴄʜᴇᴄᴋ ʙᴀᴄᴋ ʟᴀᴛᴇʀ!"

        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    await render_auction(update.message, context, auction_data, update.effective_user.id)


async def render_auction(message, context: CallbackContext, 
                        auction_data: dict, user_id: int, edit: bool = False):
    auction = Auction.from_db(auction_data)
    character_data = await collection.find_one({"id": auction.character_id})

    if not character_data:
        return

    character = Character.from_db(character_data)
    top_bidders = await AuctionManager.get_top_bidders(auction_data["_id"])
    caption = AuctionUI.build_caption(character, auction, top_bidders)

    try:
        if edit:
            await message.edit_caption(
                caption=caption,
                parse_mode=ParseMode.HTML
            )
        else:
            send_func = message.reply_video if character.is_video else message.reply_photo
            media_param = "video" if character.is_video else "photo"
            await send_func(
                **{media_param: character.img_url},
                caption=caption,
                parse_mode=ParseMode.HTML
            )
    except (BadRequest, TimedOut, NetworkError) as e:
        logger.error(f"Error rendering auction: {e}")
        if not edit:
            await message.reply_text(caption, parse_mode=ParseMode.HTML)


@typing_action
async def auction_start_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if not await AuctionManager.is_sudo(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪꜱꜱɪᴏɴ")
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ <b>ᴜꜱᴀɢᴇ:</b>\n"
            "<code>/astart &lt;id&gt; &lt;starting_bid&gt; &lt;hours&gt; [increment] [auto_extend]</code>\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇꜱ:</b>\n"
            "<code>/astart char123 1000 24</code>\n"
            "<code>/astart char123 1000 24 200 yes</code>",
            parse_mode=ParseMode.HTML
        )
        return

    char_id = context.args[0]
    starting_bid = int(context.args[1])
    duration = int(context.args[2])
    bid_increment = int(context.args[3]) if len(context.args) >= 4 else 100
    auto_extend = len(context.args) >= 5 and context.args[4].lower() in ["yes", "true", "1"]

    success, message = await AuctionManager.create_auction(
        char_id, starting_bid, duration, user_id, bid_increment, auto_extend
    )

    if success:
        auction_data = await AuctionManager.get_active_auction()
        if auction_data:
            await render_auction(update.message, context, auction_data, user_id)
        else:
            await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)


@typing_action
async def auction_end_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if not await AuctionManager.is_sudo(user_id):
        await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪꜱꜱɪᴏɴ")
        return

    success, message, winner_id = await AuctionManager.end_auction()
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)


@typing_action
async def bid_command(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>ᴜꜱᴀɢᴇ:</b>\n<code>/bid &lt;amount&gt;</code>\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b>\n<code>/bid 5000</code>",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or "Anonymous"
        amount = int(context.args[0])

        if amount < 0:
            await update.message.reply_text("⚠️ ʙɪᴅ ᴀᴍᴏᴜɴᴛ ᴍᴜꜱᴛ ʙᴇ ᴘᴏꜱɪᴛɪᴠᴇ")
            return

        success, message = await AuctionManager.place_bid(user_id, amount, user_name)
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)

        if success:
            await asyncio.sleep(1)
            auction_data = await AuctionManager.get_active_auction()
            if auction_data:
                await render_auction(update.message, context, auction_data, user_id)

    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ. ᴜꜱᴇ ɴᴜᴍʙᴇʀꜱ ᴏɴʟʏ.")
    except Exception as e:
        logger.error(f"Bid error: {e}")
        await update.message.reply_text("⚠️ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ᴘʟᴀᴄɪɴɢ ʏᴏᴜʀ ʙɪᴅ")


@typing_action
async def auction_stats_command(update: Update, context: CallbackContext):
    auction_data = await AuctionManager.get_active_auction()

    if not auction_data:
        await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ")
        return

    auction = Auction.from_db(auction_data)
    top_bidders = await AuctionManager.get_top_bidders(auction_data["_id"])

    msg = "📊 <b>ᴀᴜᴄᴛɪᴏɴ ꜱᴛᴀᴛꜱ</b>\n\n"
    msg += f"💰 ᴄᴜʀʀᴇɴᴛ: <b>{auction.current_bid:,}</b> ɢᴏʟᴅ\n"
    msg += f"📊 ᴍɪɴ ɴᴇxᴛ: <code>{auction.min_next_bid:,}</code> ɢᴏʟᴅ\n"
    msg += f"🔨 ʙɪᴅꜱ: <code>{auction.bid_count}</code>\n"
    msg += f"{auction.format_time_left()}\n\n"

    if top_bidders:
        msg += "<b>🏆 ᴛᴏᴘ 5 ʙɪᴅᴅᴇʀꜱ:</b>\n"
        for i, bid in enumerate(top_bidders, 1):
            medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
            msg += f"{medal} <code>{bid.amount:,}</code> ɢᴏʟᴅ\n"

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


application.add_handler(CommandHandler("auction", auction_view_command, block=False))
application.add_handler(CommandHandler("astart", auction_start_command, block=False))
application.add_handler(CommandHandler("aend", auction_end_command, block=False))
application.add_handler(CommandHandler("bid", bid_command, block=False))
application.add_handler(CommandHandler("astats", auction_stats_command, block=False))