from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import asyncio
import logging
import pytz

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatAction, ParseMode

from shivu import shivuu as app, db, user_collection

collection = db['anime_characters_lol']
auction_collection = db['auctions']
bid_collection = db['bids']

SUDO_USERS = {8297659126, 8420981179, 5147822244}
logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

def get_ist_now():
    return datetime.now(IST)

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
            chat_id=data.get('chat_id')
        )

    @property
    def time_remaining(self):
        return self.end_time - get_ist_now()

    @property
    def is_active(self):
        return self.status == "active" and get_ist_now() < self.end_time

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
        s = int(td.total_seconds())
        
        if s < 0:
            return "⏰ ᴇɴᴅᴇᴅ"
        
        d, h, m = s // 86400, (s % 86400) // 3600, (s % 3600) // 60
        
        if d > 0:
            return f"🕐 {d}ᴅ {h}ʜ"
        elif h > 0:
            return f"🕐 {h}ʜ {m}ᴍ"
        elif m > 0:
            return f"🕐 {m}ᴍ {s % 60}ꜱ"
        else:
            return f"⚡ {s}ꜱ"

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
    def build_caption(character, auction, top_bidders=None):
        status = "🔥 ᴇɴᴅɪɴɢ ꜱᴏᴏɴ!" if auction.is_ending_soon else "✅ ᴀᴄᴛɪᴠᴇ"
        
        lines = [
            "🔨 <b>ʟɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ</b>\n",
            f"<b>{status}</b>\n",
            f"✨ <b>{character.name}</b>",
            f"🎭 <code>{character.anime}</code>\n",
            f"💰 ᴄᴜʀʀᴇɴᴛ ʙɪᴅ: <b>{auction.current_bid:,}</b> ɢᴏʟᴅ",
            f"📊 ɴᴇxᴛ ᴍɪɴ: <code>{auction.min_next_bid:,}</code> ɢᴏʟᴅ",
            f"🔨 ᴛᴏᴛᴀʟ ʙɪᴅꜱ: <code>{auction.bid_count}</code>",
            f"\n{auction.format_time_left()}\n"
        ]
        
        if auction.highest_bidder:
            lines.append(f"👑 ʟᴇᴀᴅᴇʀ: <code>ᴜꜱᴇʀ {auction.highest_bidder}</code>\n")
        else:
            lines.append("👑 ɴᴏ ʙɪᴅꜱ ʏᴇᴛ!\n")
        
        if top_bidders and len(top_bidders) > 1:
            lines.append("<b>🏆 ᴛᴏᴘ ʙɪᴅᴅᴇʀꜱ:</b>")
            for i, bid in enumerate(top_bidders[:3], 1):
                medal = ["🥇", "🥈", "🥉"][i-1]
                lines.append(f"{medal} {bid.amount:,} ɢᴏʟᴅ")
            lines.append("")
        
        lines.extend([
            "💬 <b>ǫᴜɪᴄᴋ ʙɪᴅ:</b>",
            f"<code>/bid {auction.min_next_bid}</code>",
            f"<code>/bid {auction.min_next_bid + auction.bid_increment}</code>",
            f"<code>/bid {auction.min_next_bid + (auction.bid_increment * 2)}</code>"
        ])
        
        return "\n".join(lines)

class AuctionManager:
    _lock = asyncio.Lock()

    @staticmethod
    async def is_sudo(user_id: int):
        return user_id in SUDO_USERS

    @staticmethod
    async def get_active_auction():
        return await auction_collection.find_one({"status": "active", "end_time": {"$gt": get_ist_now()}})

    @staticmethod
    async def create_auction(char_id: str, starting_bid: int, duration_hours: int, 
                           created_by: int, chat_id: int, bid_increment: int = 100):
        try:
            character = await collection.find_one({"id": char_id})
            if not character:
                return False, "⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ"

            active = await AuctionManager.get_active_auction()
            if active:
                return False, "⚠️ ᴀɴᴏᴛʜᴇʀ ᴀᴜᴄᴛɪᴏɴ ɪꜱ ᴀᴄᴛɪᴠᴇ"

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
                "bid_increment": bid_increment
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
                    return False, "⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ", None

                auction = Auction.from_db(auction_data)

                if not auction.is_active:
                    return False, "⏰ ᴀᴜᴄᴛɪᴏɴ ʜᴀꜱ ᴇɴᴅᴇᴅ", None

                if user_id == auction.highest_bidder:
                    return False, "👑 ʏᴏᴜ'ʀᴇ ᴀʟʀᴇᴀᴅʏ ʜɪɢʜᴇꜱᴛ ʙɪᴅᴅᴇʀ!", None

                if amount < auction.min_next_bid:
                    return False, f"⚠️ ᴍɪɴɪᴍᴜᴍ ʙɪᴅ: <b>{auction.min_next_bid:,}</b> ɢᴏʟᴅ", None

                user_data = await user_collection.find_one({"id": user_id})
                if not user_data:
                    return False, "⚠️ ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ", None

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

                if auction.is_ending_soon:
                    new_end = get_ist_now() + timedelta(minutes=5)
                    if new_end > auction.end_time:
                        await auction_collection.update_one(
                            {"_id": auction_data["_id"]},
                            {"$set": {"end_time": new_end}}
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

                msg = f"✅ <b>ʙɪᴅ ᴘʟᴀᴄᴇᴅ!</b>\n\n💰 ʏᴏᴜʀ ʙɪᴅ: <b>{amount:,}</b> ɢᴏʟᴅ\n👑 ʏᴏᴜ'ʀᴇ ɴᴏᴡ ʟᴇᴀᴅɪɴɢ!"
                return True, msg, previous_bidder
            except Exception as e:
                logger.error(f"Error placing bid: {e}")
                return False, f"⚠️ ᴇʀʀᴏʀ: {str(e)}", None

    @staticmethod
    async def end_auction():
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
                    "🎊 <b>ᴀᴜᴄᴛɪᴏɴ ᴇɴᴅᴇᴅ!</b>\n\n"
                    f"✨ <b>{character['name']}</b>\n"
                    f"👑 ᴡɪɴɴᴇʀ: <a href='tg://user?id={winner_id}'>ᴜꜱᴇʀ {winner_id}</a>\n"
                    f"💰 ꜰɪɴᴀʟ: <b>{auction.current_bid:,}</b> ɢᴏʟᴅ\n"
                    f"🔨 ʙɪᴅꜱ: <code>{auction.bid_count}</code>"
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
            bids = await bid_collection.find({"auction_id": str(auction_id)}).sort("amount", -1).limit(5).to_list(length=5)
            return [Bid.from_db(bid) for bid in bids]
        except Exception as e:
            logger.error(f"Error getting top bidders: {e}")
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
                logger.info("Ending expired auction...")
                success, message, winner_id, chat_id = await AuctionManager.end_auction()
                
                if success and chat_id:
                    try:
                        await app.send_message(
                            chat_id=chat_id, 
                            text=message, 
                            parse_mode=ParseMode.HTML
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify: {e}")
        except Exception as e:
            logger.error(f"Error in auto-end: {e}")
        
        await asyncio.sleep(60)

async def render_auction(message: Message, auction_data: dict, edit: bool = False):
    try:
        await app.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        auction = Auction.from_db(auction_data)
        character_data = await collection.find_one({"id": auction.character_id})

        if not character_data:
            await message.reply_text("⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ")
            return

        character = Character.from_db(character_data)
        top_bidders = await AuctionManager.get_top_bidders(auction_data["_id"])
        caption = AuctionUI.build_caption(character, auction, top_bidders)

        if edit and message.photo or message.video:
            await message.edit_caption(caption=caption, parse_mode=ParseMode.HTML)
        else:
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
        logger.error(f"Error rendering: {e}")

@app.on_message(filters.command("auction", prefixes=[".", ",", ":", "'", '"', "*", "!", ";", "_", "/"]))
async def auction_view_command(client: Client, message: Message):
    try:
        await app.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        auction_data = await AuctionManager.get_active_auction()
        if not auction_data:
            await message.reply_text(
                "🔨 <b>ɴᴏ ᴀᴜᴄᴛɪᴏɴ</b>\n\nɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ", 
                parse_mode=ParseMode.HTML
            )
            return
        await render_auction(message, auction_data)
    except Exception as e:
        logger.error(f"Error: {e}")

@app.on_message(filters.command("astart", prefixes=[".", ",", ":", "'", '"', "*", "!", ";", "_", "/"]) | filters.regex(r"^astart\s"))
async def auction_start_command(client: Client, message: Message):
    try:
        await app.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        user_id = message.from_user.id
        if not await AuctionManager.is_sudo(user_id):
            await message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪꜱꜱɪᴏɴ")
            return

        args = message.text.split()[1:]
        if len(args) < 3:
            await message.reply_text(
                "⚠️ <b>ᴜꜱᴀɢᴇ:</b>\n<code>/astart &lt;id&gt; &lt;bid&gt; &lt;hours&gt;</code>",
                parse_mode=ParseMode.HTML
            )
            return

        char_id = args[0]
        starting_bid = int(args[1])
        duration = int(args[2])
        bid_increment = int(args[3]) if len(args) >= 4 else 100

        success, msg = await AuctionManager.create_auction(
            char_id, starting_bid, duration, user_id, message.chat.id, bid_increment
        )
        await message.reply_text(msg, parse_mode=ParseMode.HTML)

        if success:
            auction_data = await AuctionManager.get_active_auction()
            if auction_data:
                await render_auction(message, auction_data)
    except ValueError:
        await message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀꜱ")
    except Exception as e:
        logger.error(f"Error: {e}")

@app.on_message(filters.command("aend", prefixes=[".", ",", ":", "'", '"', "*", "!", ";", "_", "/"]) | filters.regex(r"^aend$"))
async def auction_end_command(client: Client, message: Message):
    try:
        await app.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        if not await AuctionManager.is_sudo(message.from_user.id):
            await message.reply_text("⛔️ ɴᴏ ᴘᴇʀᴍɪꜱꜱɪᴏɴ")
            return
        success, msg, winner_id, chat_id = await AuctionManager.end_auction()
        await message.reply_text(msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error: {e}")

@app.on_message(filters.command("bid", prefixes=[".", ",", ":", "'", '"', "*", "!", ";", "_", "/"]) | filters.regex(r"^bid\s"))
async def bid_command(client: Client, message: Message):
    try:
        await app.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        args = message.text.split()[1:]
        if not args:
            await message.reply_text(
                "⚠️ <b>ᴜꜱᴀɢᴇ:</b>\n<code>/bid &lt;amount&gt;</code>",
                parse_mode=ParseMode.HTML
            )
            return

        user_id = message.from_user.id
        user_name = message.from_user.first_name or "Anonymous"
        amount = int(args[0])

        if amount < 0:
            await message.reply_text("⚠️ ʙɪᴅ ᴍᴜꜱᴛ ʙᴇ ᴘᴏꜱɪᴛɪᴠᴇ")
            return

        success, msg, previous_bidder = await AuctionManager.place_bid(user_id, amount, user_name)
        await message.reply_text(msg, parse_mode=ParseMode.HTML)

        if success and previous_bidder:
            try:
                await app.send_message(
                    chat_id=previous_bidder,
                    text=f"⚠️ <b>ᴏᴜᴛʙɪᴅ!</b>\n\n💰 ɴᴇᴡ: <b>{amount:,}</b> ɢᴏʟᴅ",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Failed to notify: {e}")

        if success:
            await asyncio.sleep(1)
            auction_data = await AuctionManager.get_active_auction()
            if auction_data:
                await render_auction(message, auction_data)
    except ValueError:
        await message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ")
    except Exception as e:
        logger.error(f"Error: {e}")

@app.on_message(filters.command("astats", prefixes=[".", ",", ":", "'", '"', "*", "!", ";", "_", "/"]) | filters.regex(r"^astats$"))
async def auction_stats_command(client: Client, message: Message):
    try:
        await app.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        auction_data = await AuctionManager.get_active_auction()
        if not auction_data:
            await message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ")
            return

        auction = Auction.from_db(auction_data)
        top_bidders = await AuctionManager.get_top_bidders(auction_data["_id"])

        msg = f"📊 <b>ᴀᴜᴄᴛɪᴏɴ ꜱᴛᴀᴛꜱ</b>\n\n💰 {auction.current_bid:,} ɢᴏʟᴅ\n📊 ᴍɪɴ: {auction.min_next_bid:,}\n🔨 ʙɪᴅꜱ: {auction.bid_count}\n{auction.format_time_left()}\n\n"

        if top_bidders:
            msg += "<b>🏆 ᴛᴏᴘ 5:</b>\n"
            for i, bid in enumerate(top_bidders, 1):
                medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
                msg += f"{medal} {bid.amount:,} - {bid.user_name}\n"

        await message.reply_text(msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error: {e}")

@app.on_message(filters.command("mybids", prefixes=[".", ",", ":", "'", '"', "*", "!", ";", "_", "/"]))
async def my_bids_command(client: Client, message: Message):
    try:
        await app.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        user_id = message.from_user.id
        user_data = await user_collection.find_one({"id": user_id})
        
        if not user_data:
            await message.reply_text("⚠️ ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ")
            return

        balance = user_data.get("balance", 0)
        reserved = user_data.get("auction_reserved", 0)
        available = balance - reserved

        msg = f"💼 <b>ʏᴏᴜʀ ꜱᴛᴀᴛᴜꜱ</b>\n\n💰 ʙᴀʟᴀɴᴄᴇ: <b>{balance:,}</b>\n🔒 ʀᴇꜱᴇʀᴠᴇᴅ: {reserved:,}\n✅ ᴀᴠᴀɪʟᴀʙʟᴇ: <b>{available:,}</b>\n\n"

        auction_data = await AuctionManager.get_active_auction()
        if auction_data:
            auction = Auction.from_db(auction_data)
            if auction.highest_bidder == user_id:
                msg += f"👑 <b>ʏᴏᴜ'ʀᴇ ʟᴇᴀᴅɪɴɢ!</b>\n💎 {auction.current_bid:,} ɢᴏʟᴅ\n{auction.format_time_left()}"
            else:
                user_bid = await bid_collection.find_one({
                    "auction_id": str(auction_data["_id"]),
                    "user_id": user_id
                })
                if user_bid:
                    msg += f"📊 <b>ʏᴏᴜ ʜᴀᴠᴇ ʙɪᴅ</b>\n💰 ᴄᴜʀʀᴇɴᴛ: {auction.current_bid:,}\n📈 ɴᴇxᴛ: {auction.min_next_bid:,}"
                else:
                    msg += "ℹ️ ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ʙɪᴅ ʏᴇᴛ"
        else:
            msg += "ℹ️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ"

        await message.reply_text(msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error: {e}")


# Initialize the background task
asyncio.create_task(check_expired_auctions())