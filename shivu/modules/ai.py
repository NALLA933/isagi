from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional, List
from enum import Enum
import asyncio
from functools import wraps
import logging
import pytz

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler
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
        try:
            if update.message:
                await update.message.chat.send_action(ChatAction.TYPING)
        except:
            pass
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
    def from_db(cls, data: dict):
        return cls(
            id=data.get('id', ''),
            name=data.get('name', 'Unknown'),
            anime=data.get('anime', 'Unknown'),
            img_url=data.get('img_url', ''),
            rarity=data.get('rarity', '')
        )

    @property
    def is_video(self):
        return self.rarity == "🎥 AMV"

    def to_dict(self):
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
    chat_id: Optional[int] = None

    @classmethod
    def from_db(cls, data: dict):
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        
        if isinstance(start_time, datetime):
            if start_time.tzinfo is None:
                start_time = IST.localize(start_time)
            else:
                start_time = start_time.astimezone(IST)
        else:
            start_time = get_ist_now()
            
        if isinstance(end_time, datetime):
            if end_time.tzinfo is None:
                end_time = IST.localize(end_time)
            else:
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
            auto_extend=data.get('auto_extend', True),
            chat_id=data.get('chat_id')
        )

    @property
    def time_remaining(self):
        return self.end_time - get_ist_now()

    @property
    def is_active(self):
        return (self.status == AuctionStatus.ACTIVE.value and 
                get_ist_now() < self.end_time)

    @property
    def min_next_bid(self):
        return self.current_bid + max(self.bid_increment, int(self.current_bid * 0.05))

    @property
    def is_ending_soon(self):
        return self.time_remaining.total_seconds() < 300

    def format_time_left(self):
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

    def to_dict(self):
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
    def from_db(cls, data: dict):
        timestamp = data.get('timestamp', get_ist_now())
        if isinstance(timestamp, datetime):
            if timestamp.tzinfo is None:
                timestamp = IST.localize(timestamp)
            else:
                timestamp = timestamp.astimezone(IST)
            
        return cls(
            auction_id=str(data.get('auction_id', '')),
            user_id=data.get('user_id', 0),
            amount=data.get('amount', 0),
            timestamp=timestamp,
            user_name=data.get('user_name', 'Anonymous')
        )

    def to_dict(self):
        data = asdict(self)
        data['timestamp'] = self.timestamp
        return data


class AuctionUI:

    @staticmethod
    def build_caption(character, auction, top_bidders=None):
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
    async def is_sudo(user_id: int):
        return str(user_id) in SUDO_USERS

    @staticmethod
    async def get_active_auction():
        return await auction_collection.find_one({
            "status": "active",
            "end_time": {"$gt": get_ist_now()}
        })

    @staticmethod
    async def create_auction(char_id: str, starting_bid: int, 
                           duration_hours: int, created_by: int,
                           chat_id: int,
                           bid_increment: int = 100,
                           auto_extend: bool = True):
        try:
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
                "previous_bidder": None,
                "start_time": start_time,
                "end_time": end_time,
                "status": "active",
                "created_by": created_by,
                "chat_id": chat_id,
                "bid_count": 0,
                "bid_increment": bid_increment,
                "auto_extend": auto_extend
            }

            await auction_collection.insert_one(auction_data)

            return True, f"✅ ᴀᴜᴄᴛɪᴏɴ ꜱᴛᴀʀᴛᴇᴅ ꜰᴏʀ {character['name']}"
        except Exception as e:
            logger.error(f"Error creating auction: {e}")
            return False, f"⚠️ ᴇʀʀᴏʀ: {str(e)}"

    @staticmethod
    async def place_bid(user_id: int, amount: int, user_name: str = "Anonymous"):
        async with AuctionManager._lock:
            try:
                auction_data = await AuctionManager.get_active_auction()
                if not auction_data:
                    return False, "⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ ʀᴜɴɴɪɴɢ", None

                auction = Auction.from_db(auction_data)

                if not auction.is_active:
                    return False, "⏰ ᴀᴜᴄᴛɪᴏɴ ʜᴀꜱ ᴇɴᴅᴇᴅ", None

                if user_id == auction.highest_bidder:
                    return False, "👑 ʏᴏᴜ'ʀᴇ ᴀʟʀᴇᴀᴅʏ ᴛʜᴇ ʜɪɢʜᴇꜱᴛ ʙɪᴅᴅᴇʀ!", None

                if amount < auction.min_next_bid:
                    return False, f"⚠️ ᴍɪɴɪᴍᴜᴍ ʙɪᴅ: <b>{auction.min_next_bid:,}</b> ɢᴏʟᴅ", None

                user_data = await user_collection.find_one({"id": user_id})
                if not user_data:
                    return False, "⚠️ ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ. ᴘʟᴇᴀꜱᴇ ꜱᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ ꜰɪʀꜱᴛ.", None

                balance = user_data.get("balance", 0)
                reserved = user_data.get("auction_reserved", 0)
                available = balance - reserved

                if available < amount:
                    deficit = amount - available
                    return False, (
                        f"⚠️ <b>ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ</b>\n\n"
                        f"💰 ʀᴇǫᴜɪʀᴇᴅ: <code>{amount:,}</code> ɢᴏʟᴅ\n"
                        f"💳 ᴀᴠᴀɪʟᴀʙʟᴇ: <code>{available:,}</code> ɢᴏʟᴅ\n"
                        f"🔒 ʀᴇꜱᴇʀᴠᴇᴅ: <code>{reserved:,}</code> ɢᴏʟᴅ\n"
                        f"📉 ɴᴇᴇᴅ: <code>{deficit:,}</code> ᴍᴏʀᴇ ɢᴏʟᴅ"
                    ), None

                previous_bidder = auction.highest_bidder
                previous_bid = auction.current_bid

                # Free previous bidder's reserved funds
                if previous_bidder:
                    await user_collection.update_one(
                        {"id": previous_bidder},
                        {"$inc": {"auction_reserved": -previous_bid}}
                    )

                # Reserve new bidder's funds
                await user_collection.update_one(
                    {"id": user_id},
                    {"$inc": {"auction_reserved": amount}}
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
                            "highest_bidder": user_id,
                            "previous_bidder": previous_bidder
                        },
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

                msg = "✅ <b>ʙɪᴅ ᴘʟᴀᴄᴇᴅ!</b>\n\n"
                msg += f"💰 ʏᴏᴜʀ ʙɪᴅ: <b>{amount:,}</b> ɢᴏʟᴅ\n"
                msg += f"👑 ʏᴏᴜ'ʀᴇ ɴᴏᴡ ʟᴇᴀᴅɪɴɢ!"

                return True, msg, previous_bidder
            except Exception as e:
                logger.error(f"Error placing bid: {e}")
                return False, f"⚠️ ᴇʀʀᴏʀ: {str(e)}", None

    @staticmethod
    async def end_auction():
        try:
            auction_data = await auction_collection.find_one({"status": "active"})
            if not auction_data:
                return False, "⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ ꜰᴏᴜɴᴅ", None, None

            auction = Auction.from_db(auction_data)
            winner_id = auction.highest_bidder
            chat_id = auction.chat_id

            if winner_id:
                character = await collection.find_one({"id": auction.character_id})

                # Deduct reserved funds and add character (just ID)
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
                    "🎊 <b>ᴀᴜᴄᴛɪᴏɴ ᴇɴᴅᴇᴅ!</b>\n\n"
                    f"✨ <b>{character['name']}</b>\n"
                    f"👑 ᴡɪɴɴᴇʀ: <a href='tg://user?id={winner_id}'>ᴜꜱᴇʀ {winner_id}</a>\n"
                    f"💰 ꜰɪɴᴀʟ ᴘʀɪᴄᴇ: <b>{auction.current_bid:,}</b> ɢᴏʟᴅ\n"
                    f"🔨 ᴛᴏᴛᴀʟ ʙɪᴅꜱ: <code>{auction.bid_count}</code>"
                )
                return True, message, winner_id, chat_id
            else:
                await auction_collection.update_one(
                    {"_id": auction_data["_id"]},
                    {"$set": {"status": "ended"}}
                )
                return True, "⚠️ ᴀᴜᴄᴛɪᴏɴ ᴇɴᴅᴇᴅ ᴡɪᴛʜ ɴᴏ ʙɪᴅꜱ", None, chat_id
        except Exception as e:
            logger.error(f"Error ending auction: {e}")
            return False, f"⚠️ ᴇʀʀᴏʀ: {str(e)}", None, None

    @staticmethod
    async def get_top_bidders(auction_id):
        try:
            bids_cursor = bid_collection.find(
                {"auction_id": str(auction_id)}
            ).sort("amount", -1).limit(5)
            
            bids = await bids_cursor.to_list(length=5)
            return [Bid.from_db(bid) for bid in bids]
        except Exception as e:
            logger.error(f"Error getting top bidders: {e}")
            return []


# Background task to auto-end expired auctions
async def check_expired_auctions():
    """Background task to automatically end expired auctions"""
    await asyncio.sleep(10)  # Wait for bot to initialize
    
    while True:
        try:
            auction_data = await auction_collection.find_one({
                "status": "active",
                "end_time": {"$lt": get_ist_now()}
            })
            
            if auction_data:
                logger.info("Found expired auction, ending it...")
                success, message, winner_id, chat_id = await AuctionManager.end_auction()
                
                if success and chat_id:
                    try:
                        await application.bot.send_message(
                            chat_id=chat_id,
                            text=message,
                            parse_mode=ParseMode.HTML
                        )
                        logger.info(f"Auto-ended auction, notified chat {chat_id}")
                    except Exception as e:
                        logger.error(f"Failed to send auto-end notification: {e}")
                
        except Exception as e:
            logger.error(f"Error in auto-end task: {e}")
        
        await asyncio.sleep(60)  # Check every minute


@typing_action
async def auction_view_command(update: Update, context: CallbackContext):
    try:
        auction_data = await AuctionManager.get_active_auction()

        if not auction_data:
            msg = "🔨 <b>ɴᴏ ᴀᴜᴄᴛɪᴏɴ</b>\n\nɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ\nᴄʜᴇᴄᴋ ʙᴀᴄᴋ ʟᴀᴛᴇʀ!"
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            return

        await render_auction(update.message, context, auction_data, update.effective_user.id)
    except Exception as e:
        logger.error(f"Error in auction view: {e}")
        await update.message.reply_text("⚠️ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ")


async def render_auction(message, context, auction_data, user_id, edit=False):
    try:
        auction = Auction.from_db(auction_data)
        character_data = await collection.find_one({"id": auction.character_id})

        if not character_data:
            await message.reply_text("⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ")
            return

        character = Character.from_db(character_data)
        top_bidders = await AuctionManager.get_top_bidders(auction_data["_id"])
        caption = AuctionUI.build_caption(character, auction, top_bidders)

        if edit:
            await message.edit_caption(caption=caption, parse_mode=ParseMode.HTML)
        else:
            if character.is_video:
                await message.reply_video(video=character.img_url, caption=caption, parse_mode=ParseMode.HTML)
            else:
                await message.reply_photo(photo=character.img_url, caption=caption, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error rendering auction: {e}")
        await message.reply_text("⚠️ ᴇʀʀᴏʀ ʀᴇɴᴅᴇʀɪɴɢ ᴀᴜᴄᴛɪᴏɴ")


@typing_action
async def auction_start_command(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id

        if not await AuctionManager.is_sudo(user_id):
            await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪꜱꜱɪᴏɴ")
            return

        if len(context.args) < 3:
            await update.message.reply_text(
                "⚠️ <b>ᴜꜱᴀɢᴇ:</b>\n"
                "<code>/astart &lt;id&gt; &lt;starting_bid&gt; &lt;hours&gt; [bid_increment] [auto_extend]</code>\n\n"
                "<b>ᴇxᴀᴍᴘʟᴇꜱ:</b>\n"
                "<code>/astart char123 1000 24</code>\n"
                "<code>/astart char456 5000 12 200 yes</code>",
                parse_mode=ParseMode.HTML
            )
            return

        char_id = context.args[0]
        starting_bid = int(context.args[1])
        duration = int(context.args[2])
        bid_increment = int(context.args[3]) if len(context.args) >= 4 else 100
        auto_extend = len(context.args) >= 5 and context.args[4].lower() in ["yes", "true", "1"]
        chat_id = update.effective_chat.id

        success, message = await AuctionManager.create_auction(
            char_id, starting_bid, duration, user_id, chat_id, bid_increment, auto_extend
        )

        await update.message.reply_text(message, parse_mode=ParseMode.HTML)

        if success:
            auction_data = await AuctionManager.get_active_auction()
            if auction_data:
                await render_auction(update.message, context, auction_data, user_id)

    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀꜱ")
    except Exception as e:
        logger.error(f"Error in auction start: {e}")
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")


@typing_action
async def auction_end_command(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id

        if not await AuctionManager.is_sudo(user_id):
            await update.message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪꜱꜱɪᴏɴ")
            return

        success, message, winner_id, chat_id = await AuctionManager.end_auction()
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error in auction end: {e}")
        await update.message.reply_text("⚠️ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ")


@typing_action
async def bid_command(update: Update, context: CallbackContext):
    try:
        if not context.args:
            await update.message.reply_text(
                "⚠️ <b>ᴜꜱᴀɢᴇ:</b>\n<code>/bid &lt;amount&gt;</code>\n\n"
                "<b>ᴇxᴀᴍᴘʟᴇ:</b>\n<code>/bid 5000</code>",
                parse_mode=ParseMode.HTML
            )
            return

        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or "Anonymous"
        amount = int(context.args[0])

        if amount < 0:
            await update.message.reply_text("⚠️ ʙɪᴅ ᴀᴍᴏᴜɴᴛ ᴍᴜꜱᴛ ʙᴇ ᴘᴏꜱɪᴛɪᴠᴇ")
            return

        success, message, previous_bidder = await AuctionManager.place_bid(user_id, amount, user_name)
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)

        # Notify previous bidder they were outbid
        if success and previous_bidder:
            try:
                outbid_msg = (
                    "⚠️ <b>ʏᴏᴜ'ᴠᴇ ʙᴇᴇɴ ᴏᴜᴛʙɪᴅ!</b>\n\n"
                    f"💰 ɴᴇᴡ ʙɪᴅ: <b>{amount:,}</b> ɢᴏʟᴅ\n"
                    f"👤 ʙʏ: <code>{user_name}</code>\n\n"
                    "🔥 ᴘʟᴀᴄᴇ ᴀ ɴᴇᴡ ʙɪᴅ ᴛᴏ ʀᴇᴄʟᴀɪᴍ ᴛʜᴇ ʟᴇᴀᴅ!"
                )
                await context.bot.send_message(
                    chat_id=previous_bidder,
                    text=outbid_msg,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Failed to notify previous bidder: {e}")

        if success:
            await asyncio.sleep(1)
            auction_data = await AuctionManager.get_active_auction()
            if auction_data:
                await render_auction(update.message, context, auction_data, user_id)

    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ. ᴜꜱᴇ ɴᴜᴍʙᴇʀꜱ ᴏɴʟʏ")
    except Exception as e:
        logger.error(f"Bid error: {e}")
        await update.message.reply_text("⚠️ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ")


@typing_action
async def auction_stats_command(update: Update, context: CallbackContext):
    try:
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
                msg += f"{medal} <code>{bid.amount:,}</code> ɢᴏʟᴅ - {bid.user_name}\n"

        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error in auction stats: {e}")
        await update.message.reply_text("⚠️ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ")


@typing_action
async def my_bids_command(update: Update, context: CallbackContext):
    """Show user's current auction status and reserved funds"""
    try:
        user_id = update.effective_user.id
        user_data = await user_collection.find_one({"id": user_id})
        
        if not user_data:
            await update.message.reply_text("⚠️ ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ")
            return

        balance = user_data.get("balance", 0)
        reserved = user_data.get("auction_reserved", 0)
        available = balance - reserved

        auction_data = await AuctionManager.get_active_auction()
        
        msg = "💼 <b>ʏᴏᴜʀ ᴀᴜᴄᴛɪᴏɴ ꜱᴛᴀᴛᴜꜱ</b>\n\n"
        msg += f"💰 ᴛᴏᴛᴀʟ ʙᴀʟᴀɴᴄᴇ: <b>{balance:,}</b> ɢᴏʟᴅ\n"
        msg += f"🔒 ʀᴇꜱᴇʀᴠᴇᴅ: <code>{reserved:,}</code> ɢᴏʟᴅ\n"
        msg += f"✅ ᴀᴠᴀɪʟᴀʙʟᴇ: <b>{available:,}</b> ɢᴏʟᴅ\n\n"

        if auction_data:
            auction = Auction.from_db(auction_data)
            if auction.highest_bidder == user_id:
                msg += "👑 <b>ʏᴏᴜ'ʀᴇ ᴛʜᴇ ʜɪɢʜᴇꜱᴛ ʙɪᴅᴅᴇʀ!</b>\n"
                msg += f"💎 ʏᴏᴜʀ ʙɪᴅ: <b>{auction.current_bid:,}</b> ɢᴏʟᴅ\n"
                msg += f"{auction.format_time_left()}"
            else:
                # Check if user has bid on this auction
                user_bid = await bid_collection.find_one({
                    "auction_id": str(auction_data["_id"]),
                    "user_id": user_id
                })
                if user_bid:
                    msg += "📊 <b>ʏᴏᴜ ʜᴀᴠᴇ ʙɪᴅ ᴏɴ ᴛʜɪꜱ ᴀᴜᴄᴛɪᴏɴ</b>\n"
                    msg += f"💰 ᴄᴜʀʀᴇɴᴛ ʜɪɢʜᴇꜱᴛ: <b>{auction.current_bid:,}</b> ɢᴏʟᴅ\n"
                    msg += f"📈 ɴᴇxᴛ ᴍɪɴ: <code>{auction.min_next_bid:,}</code> ɢᴏʟᴅ"
                else:
                    msg += "ℹ️ ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ʙɪᴅ ʏᴇᴛ"
        else:
            msg += "ℹ️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ"

        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error in my bids: {e}")
        await update.message.reply_text("⚠️ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ")


# Command handlers
application.add_handler(CommandHandler("auction", auction_view_command, block=False))
application.add_handler(CommandHandler("astart", auction_start_command, block=False))
application.add_handler(CommandHandler("aend", auction_end_command, block=False))
application.add_handler(CommandHandler("bid", bid_command, block=False))
application.add_handler(CommandHandler("astats", auction_stats_command, block=False))
application.add_handler(CommandHandler("mybids", my_bids_command, block=False))

# Start background task
asyncio.create_task(check_expired_auctions())