from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
import asyncio
import logging
import pytz
from functools import wraps

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler
from telegram.constants import ParseMode

from shivu import application, db, user_collection

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

SUDO_USERS = {"8297659126", "8420981179", "5147822244"}
ANTI_SNIPE_SECONDS = 300
ANTI_SNIPE_EXTENSION = 300

collection = db['anime_characters_lol']
auction_collection = db['auctions']
bid_collection = db['bids']

FUNNY_MESSAGES = {
    'outbid': [
        "💔 Someone just crushed your bid!",
        "😅 Oops! You got outbid",
        "⚡ Plot twist! Higher bid incoming",
        "🎭 The auction just got spicy!"
    ],
    'winning': [
        "🔥 You're dominating this auction!",
        "👑 Crown secured... for now",
        "💪 Beast mode activated",
        "✨ Victory is close!"
    ],
    'low_bid': [
        "😂 That's it? Bid higher!",
        "🙄 Come on, be serious!",
        "💸 Show me the money!",
        "🤔 Is this a joke bid?"
    ]
}

def ist_now() -> datetime:
    return datetime.now(IST)

def sudo_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        if str(update.effective_user.id) not in SUDO_USERS:
            await update.message.reply_text("⛔️ ᴀᴜᴛʜᴏʀɪᴢᴀᴛɪᴏɴ ʀᴇǫᴜɪʀᴇᴅ")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

@dataclass(frozen=True)
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
    bid_count: int = 0
    bid_increment: int = 100
    chat_id: Optional[int] = None
    auto_extend: bool = True
    previous_bidder: Optional[int] = None

    @classmethod
    def from_db(cls, data: dict):
        start = data.get('start_time', ist_now())
        end = data.get('end_time', ist_now())
        
        if isinstance(start, datetime):
            start = IST.localize(start) if start.tzinfo is None else start.astimezone(IST)
        if isinstance(end, datetime):
            end = IST.localize(end) if end.tzinfo is None else end.astimezone(IST)
        
        return cls(
            character_id=data.get('character_id', ''),
            starting_bid=data.get('starting_bid', 0),
            current_bid=data.get('current_bid', 0),
            highest_bidder=data.get('highest_bidder'),
            start_time=start,
            end_time=end,
            status=data.get('status', 'active'),
            created_by=data.get('created_by', 0),
            bid_count=data.get('bid_count', 0),
            bid_increment=data.get('bid_increment', 100),
            chat_id=data.get('chat_id'),
            auto_extend=data.get('auto_extend', True),
            previous_bidder=data.get('previous_bidder')
        )

    @property
    def time_left(self) -> timedelta:
        return self.end_time - ist_now()

    @property
    def is_active(self) -> bool:
        return self.status == "active" and ist_now() < self.end_time

    @property
    def min_next_bid(self) -> int:
        return self.current_bid + max(self.bid_increment, int(self.current_bid * 0.05))

    @property
    def is_ending_soon(self) -> bool:
        return 0 < self.time_left.total_seconds() < ANTI_SNIPE_SECONDS

    def format_time(self) -> str:
        if not self.is_active:
            return "⏰ ᴇɴᴅᴇᴅ"
        
        s = int(self.time_left.total_seconds())
        if s < 0:
            return "⏰ ᴇɴᴅᴇᴅ"
        
        d, h, m = s // 86400, (s % 86400) // 3600, (s % 3600) // 60
        
        if d > 0:
            return f"🕐 {d}ᴅ {h}ʜ {m}ᴍ"
        elif h > 0:
            return f"🕐 {h}ʜ {m}ᴍ"
        elif m > 5:
            return f"🕐 {m}ᴍ"
        return f"⚡ {m}ᴍ {s % 60}ꜱ"

@dataclass(frozen=True)
class Bid:
    auction_id: str
    user_id: int
    amount: int
    timestamp: datetime
    user_name: str = "Anonymous"

    @classmethod
    def from_db(cls, data: dict):
        ts = data.get('timestamp', ist_now())
        if isinstance(ts, datetime):
            ts = IST.localize(ts) if ts.tzinfo is None else ts.astimezone(IST)
        
        return cls(
            auction_id=str(data.get('auction_id', '')),
            user_id=data.get('user_id', 0),
            amount=data.get('amount', 0),
            timestamp=ts,
            user_name=data.get('user_name', 'Anonymous')
        )

class AuctionUI:
    @staticmethod
    def build_caption(char: Character, auction: Auction, top_bids: Optional[List[Bid]] = None) -> str:
        emoji = "🔥" if auction.is_ending_soon else "✅"
        status = "ᴇɴᴅɪɴɢ ꜱᴏᴏɴ" if auction.is_ending_soon else "ᴀᴄᴛɪᴠᴇ"
        
        lines = [
            "━━━━━━━━━━━━━━━━",
            f"🔨 <b>ʟɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ</b>",
            f"{emoji} <b>{status}</b>",
            "━━━━━━━━━━━━━━━━\n",
            f"✨ <b>{char.name}</b>",
            f"🎭 <code>{char.anime}</code>\n",
            f"💰 ᴄᴜʀʀᴇɴᴛ: <b>{auction.current_bid:,}</b>",
            f"📊 ᴍɪɴɪᴍᴜᴍ: <code>{auction.min_next_bid:,}</code>",
            f"🔨 ʙɪᴅꜱ: <code>{auction.bid_count}</code>",
            f"\n{auction.format_time()}\n"
        ]
        
        if auction.highest_bidder:
            lines.append(f"👑 ʟᴇᴀᴅᴇʀ: <code>{auction.highest_bidder}</code>\n")
        else:
            lines.append("👑 ɴᴏ ʙɪᴅꜱ ʏᴇᴛ\n")
        
        if top_bids:
            lines.extend([
                "━━━━━━━━━━━━━━━━",
                "<b>🏆 ᴛᴏᴘ ʙɪᴅᴅᴇʀꜱ</b>"
            ])
            for i, bid in enumerate(top_bids[:3], 1):
                medal = ["🥇", "🥈", "🥉"][i-1]
                lines.append(f"{medal} {bid.amount:,}")
            lines.append("━━━━━━━━━━━━━━━━\n")
        
        quick = [
            auction.min_next_bid,
            auction.min_next_bid + auction.bid_increment,
            auction.min_next_bid + (auction.bid_increment * 2)
        ]
        
        lines.extend([
            "💬 <b>ǫᴜɪᴄᴋ ʙɪᴅ</b>",
            " • ".join([f"<code>/bid {b}</code>" for b in quick])
        ])
        
        return "\n".join(lines)

class Manager:
    _lock = asyncio.Lock()

    @staticmethod
    async def get_active():
        return await auction_collection.find_one({
            "status": "active",
            "end_time": {"$gt": ist_now()}
        })

    @staticmethod
    async def create(char_id: str, start_bid: int, hours: int, creator: int, chat: int, increment: int = 100) -> Tuple[bool, str]:
        try:
            char = await collection.find_one({"id": char_id})
            if not char:
                return False, "⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ"

            if await Manager.get_active():
                return False, "⚠️ ᴀɴᴏᴛʜᴇʀ ᴀᴜᴄᴛɪᴏɴ ɪꜱ ʀᴜɴɴɪɴɢ"

            if start_bid < 100 or hours < 1 or hours > 168:
                return False, "⚠️ ɪɴᴠᴀʟɪᴅ ᴘᴀʀᴀᴍᴇᴛᴇʀꜱ"

            now = ist_now()
            await auction_collection.insert_one({
                "character_id": char_id,
                "starting_bid": start_bid,
                "current_bid": start_bid,
                "highest_bidder": None,
                "previous_bidder": None,
                "start_time": now,
                "end_time": now + timedelta(hours=hours),
                "status": "active",
                "created_by": creator,
                "chat_id": chat,
                "bid_count": 0,
                "bid_increment": increment,
                "auto_extend": True
            })

            return True, f"✅ ᴀᴜᴄᴛɪᴏɴ ꜱᴛᴀʀᴛᴇᴅ: <b>{char['name']}</b>"
        except Exception as e:
            logger.error(f"Create error: {e}")
            return False, "⚠️ ᴄʀᴇᴀᴛɪᴏɴ ꜰᴀɪʟᴇᴅ"

    @staticmethod
    async def place_bid(user_id: int, amount: int, name: str = "Anonymous") -> Tuple[bool, str, Optional[int]]:
        async with Manager._lock:
            try:
                data = await Manager.get_active()
                if not data:
                    return False, "⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ", None

                auction = Auction.from_db(data)
                if not auction.is_active:
                    return False, "⏰ ᴀᴜᴄᴛɪᴏɴ ᴇɴᴅᴇᴅ", None

                if user_id == auction.highest_bidder:
                    import random
                    return False, random.choice(FUNNY_MESSAGES['winning']), None

                if amount < auction.min_next_bid:
                    import random
                    return False, f"{random.choice(FUNNY_MESSAGES['low_bid'])}\n\n⚠️ ᴍɪɴɪᴍᴜᴍ: <b>{auction.min_next_bid:,}</b>", None

                user = await user_collection.find_one({"id": user_id})
                if not user:
                    return False, "⚠️ ɴᴏᴛ ʀᴇɢɪꜱᴛᴇʀᴇᴅ", None

                balance = user.get("balance", 0)
                reserved = user.get("auction_reserved", 0)
                available = balance - reserved

                if available < amount:
                    return False, (
                        f"⚠️ <b>ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ</b>\n\n"
                        f"💰 ɴᴇᴇᴅᴇᴅ: <code>{amount:,}</code>\n"
                        f"💳 ᴀᴠᴀɪʟᴀʙʟᴇ: <code>{available:,}</code>"
                    ), None

                prev = auction.highest_bidder
                prev_bid = auction.current_bid

                if prev:
                    await user_collection.update_one(
                        {"id": prev},
                        {"$inc": {"auction_reserved": -prev_bid}}
                    )

                await user_collection.update_one(
                    {"id": user_id},
                    {"$inc": {"auction_reserved": amount}}
                )

                update_data = {
                    "current_bid": amount,
                    "highest_bidder": user_id,
                    "previous_bidder": prev
                }

                if auction.auto_extend and auction.is_ending_soon:
                    new_end = ist_now() + timedelta(seconds=ANTI_SNIPE_EXTENSION)
                    if new_end > auction.end_time:
                        update_data["end_time"] = new_end

                await auction_collection.update_one(
                    {"_id": data["_id"]},
                    {
                        "$set": update_data,
                        "$inc": {"bid_count": 1}
                    }
                )

                await bid_collection.insert_one({
                    "auction_id": str(data["_id"]),
                    "user_id": user_id,
                    "user_name": name,
                    "amount": amount,
                    "timestamp": ist_now()
                })

                return True, f"✅ <b>ʙɪᴅ ᴘʟᴀᴄᴇᴅ</b>\n\n💰 <b>{amount:,}</b>\n👑 ʏᴏᴜ'ʀᴇ ʟᴇᴀᴅɪɴɢ!", prev
            except Exception as e:
                logger.error(f"Bid error: {e}")
                return False, "⚠️ ʙɪᴅ ꜰᴀɪʟᴇᴅ", None

    @staticmethod
    async def end() -> Tuple[bool, str, Optional[int], Optional[int]]:
        try:
            data = await auction_collection.find_one({"status": "active"})
            if not data:
                return False, "⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ", None, None

            auction = Auction.from_db(data)
            winner = auction.highest_bidder
            chat = auction.chat_id

            if winner:
                char = await collection.find_one({"id": auction.character_id})
                await user_collection.update_one(
                    {"id": winner},
                    {
                        "$inc": {
                            "balance": -auction.current_bid,
                            "auction_reserved": -auction.current_bid
                        },
                        "$push": {"characters": char['id']}
                    }
                )

                await auction_collection.update_one(
                    {"_id": data["_id"]},
                    {"$set": {"status": "ended", "end_time": ist_now()}}
                )

                msg = (
                    "━━━━━━━━━━━━━━━━\n"
                    "🎊 <b>ᴀᴜᴄᴛɪᴏɴ ᴇɴᴅᴇᴅ</b>\n"
                    "━━━━━━━━━━━━━━━━\n\n"
                    f"✨ <b>{char['name']}</b>\n"
                    f"🎭 {char['anime']}\n\n"
                    f"👑 <b>ᴡɪɴɴᴇʀ:</b> <a href='tg://user?id={winner}'>{winner}</a>\n"
                    f"💰 <b>ᴘʀɪᴄᴇ:</b> {auction.current_bid:,}\n"
                    f"🔨 <b>ʙɪᴅꜱ:</b> {auction.bid_count}\n"
                    "━━━━━━━━━━━━━━━━"
                )
                return True, msg, winner, chat
            
            await auction_collection.update_one(
                {"_id": data["_id"]},
                {"$set": {"status": "ended", "end_time": ist_now()}}
            )
            return True, "⚠️ ᴇɴᴅᴇᴅ • ɴᴏ ʙɪᴅꜱ", None, chat
        except Exception as e:
            logger.error(f"End error: {e}")
            return False, "⚠️ ᴇɴᴅ ꜰᴀɪʟᴇᴅ", None, None

    @staticmethod
    async def get_top_bids(auction_id: str, limit: int = 5) -> List[Bid]:
        try:
            docs = await bid_collection.find(
                {"auction_id": str(auction_id)}
            ).sort("amount", -1).limit(limit).to_list(length=limit)
            return [Bid.from_db(d) for d in docs]
        except:
            return []

async def monitor_auctions():
    await asyncio.sleep(10)
    while True:
        try:
            data = await auction_collection.find_one({
                "status": "active",
                "end_time": {"$lt": ist_now()}
            })
            
            if data:
                success, msg, winner, chat = await Manager.end()
                if success and chat:
                    try:
                        await application.bot.send_message(
                            chat_id=chat,
                            text=msg,
                            parse_mode=ParseMode.HTML
                        )
                    except Exception as e:
                        logger.error(f"Notify failed: {e}")
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        
        await asyncio.sleep(60)

async def send_media(msg, char: Character, caption: str):
    try:
        if char.is_video:
            await msg.reply_video(video=char.img_url, caption=caption, parse_mode=ParseMode.HTML)
        else:
            await msg.reply_photo(photo=char.img_url, caption=caption, parse_mode=ParseMode.HTML)
    except:
        await msg.reply_text(caption, parse_mode=ParseMode.HTML)

async def auction_cmd(update: Update, context: CallbackContext):
    try:
        data = await Manager.get_active()
        if not data:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━\n🔨 <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ᴀᴜᴄᴛɪᴏɴ</b>\n━━━━━━━━━━━━━━━━",
                parse_mode=ParseMode.HTML
            )
            return

        auction = Auction.from_db(data)
        char_data = await collection.find_one({"id": auction.character_id})
        
        if not char_data:
            await update.message.reply_text("⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ")
            return

        char = Character.from_db(char_data)
        top = await Manager.get_top_bids(data["_id"])
        caption = AuctionUI.build_caption(char, auction, top)
        
        await send_media(update.message, char, caption)
    except Exception as e:
        logger.error(f"View error: {e}")
        await update.message.reply_text("⚠️ ᴇʀʀᴏʀ")

@sudo_only
async def start_cmd(update: Update, context: CallbackContext):
    try:
        if len(context.args) < 3:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━\n"
                "📋 <b>ᴜꜱᴀɢᴇ</b>\n"
                "━━━━━━━━━━━━━━━━\n\n"
                "<code>/astart &lt;id&gt; &lt;bid&gt; &lt;hours&gt; [increment]</code>",
                parse_mode=ParseMode.HTML
            )
            return

        char_id = context.args[0]
        start_bid = int(context.args[1])
        hours = int(context.args[2])
        increment = int(context.args[3]) if len(context.args) >= 4 else 100

        success, msg = await Manager.create(
            char_id, start_bid, hours,
            update.effective_user.id,
            update.effective_chat.id,
            increment
        )
        
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

        if success:
            await asyncio.sleep(0.5)
            data = await Manager.get_active()
            if data:
                auction = Auction.from_db(data)
                char_data = await collection.find_one({"id": auction.character_id})
                if char_data:
                    char = Character.from_db(char_data)
                    caption = AuctionUI.build_caption(char, auction)
                    await send_media(update.message, char, caption)
    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀꜱ")
    except Exception as e:
        logger.error(f"Start error: {e}")
        await update.message.reply_text("⚠️ ꜰᴀɪʟᴇᴅ")

@sudo_only
async def end_cmd(update: Update, context: CallbackContext):
    try:
        success, msg, _, _ = await Manager.end()
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"End error: {e}")
        await update.message.reply_text("⚠️ ꜰᴀɪʟᴇᴅ")

async def bid_cmd(update: Update, context: CallbackContext):
    try:
        if not context.args:
            await update.message.reply_text(
                "━━━━━━━━━━━━━━━━\n"
                "💰 <b>ᴘʟᴀᴄᴇ ʙɪᴅ</b>\n"
                "━━━━━━━━━━━━━━━━\n\n"
                "<code>/bid &lt;amount&gt;</code>",
                parse_mode=ParseMode.HTML
            )
            return

        amount = int(context.args[0])
        if amount <= 0:
            await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ")
            return

        user_id = update.effective_user.id
        name = update.effective_user.first_name or "Anonymous"

        success, msg, prev = await Manager.place_bid(user_id, amount, name)
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

        if success and prev:
            try:
                import random
                await context.bot.send_message(
                    chat_id=prev,
                    text=f"{random.choice(FUNNY_MESSAGES['outbid'])}\n\n💰 ɴᴇᴡ ʙɪᴅ: <b>{amount:,}</b>\n\n🔨 ʙɪᴅ ᴀɢᴀɪɴ!",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Notify error: {e}")
    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ")
    except Exception as e:
        logger.error(f"Bid error: {e}")
        await update.message.reply_text("⚠️ ꜰᴀɪʟᴇᴅ")

async def status_cmd(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id
        user = await user_collection.find_one({"id": user_id})
        
        if not user:
            await update.message.reply_text("⚠️ ɴᴏᴛ ʀᴇɢɪꜱᴛᴇʀᴇᴅ")
            return

        balance = user.get("balance", 0)
        reserved = user.get("auction_reserved", 0)
        available = balance - reserved

        lines = [
            "━━━━━━━━━━━━━━━━",
            "💼 <b>ʏᴏᴜʀ ꜱᴛᴀᴛᴜꜱ</b>",
            "━━━━━━━━━━━━━━━━\n",
            f"💰 ʙᴀʟᴀɴᴄᴇ: <b>{balance:,}</b>",
            f"🔒 ʀᴇꜱᴇʀᴠᴇᴅ: <code>{reserved:,}</code>",
            f"✅ ᴀᴠᴀɪʟᴀʙʟᴇ: <b>{available:,}</b>\n",
            "━━━━━━━━━━━━━━━━"
        ]

        data = await Manager.get_active()
        if data:
            auction = Auction.from_db(data)
            if auction.highest_bidder == user_id:
                lines.extend([
                    "\n👑 <b>ʏᴏᴜ'ʀᴇ ᴡɪɴɴɪɴɢ</b>\n",
                    f"💎 ʙɪᴅ: <b>{auction.current_bid:,}</b>",
                    f"⏱ {auction.format_time()}"
                ])

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Status error: {e}")
        await update.message.reply_text("⚠️ ꜰᴀɪʟᴇᴅ")

application.add_handler(CommandHandler("auction", auction_cmd, block=False))
application.add_handler(CommandHandler("astart", start_cmd, block=False))
application.add_handler(CommandHandler("aend", end_cmd, block=False))
application.add_handler(CommandHandler("bid", bid_cmd, block=False))
application.add_handler(CommandHandler("status", status_cmd, block=False))

asyncio.create_task(monitor_auctions())