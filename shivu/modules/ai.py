from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List
from enum import Enum

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest

from shivu import application, db, user_collection

collection = db['anime_characters_lol']
auction_collection = db['auctions']
bid_collection = db['bids']

SUDO_USERS = ["8297659126", "8420981179", "5147822244"]


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
    
    @classmethod
    def from_db(cls, data: dict):
        return cls(
            character_id=data.get('character_id', ''),
            starting_bid=data.get('starting_bid', 0),
            current_bid=data.get('current_bid', 0),
            highest_bidder=data.get('highest_bidder'),
            start_time=data.get('start_time', datetime.utcnow()),
            end_time=data.get('end_time', datetime.utcnow()),
            status=data.get('status', 'active'),
            created_by=data.get('created_by', 0),
            bid_count=data.get('bid_count', 0)
        )
    
    @property
    def time_remaining(self) -> timedelta:
        return self.end_time - datetime.utcnow()
    
    @property
    def is_active(self) -> bool:
        return (self.status == AuctionStatus.ACTIVE.value and 
                datetime.utcnow() < self.end_time)
    
    @property
    def min_next_bid(self) -> int:
        return int(self.current_bid * 1.05)
    
    def format_time_left(self) -> str:
        if not self.is_active:
            return "ENDED"
        
        td = self.time_remaining
        hours = int(td.total_seconds() / 3600)
        minutes = int((td.total_seconds() % 3600) / 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"


@dataclass
class Bid:
    auction_id: str
    user_id: int
    amount: int
    timestamp: datetime
    
    @classmethod
    def from_db(cls, data: dict):
        return cls(
            auction_id=str(data.get('auction_id', '')),
            user_id=data.get('user_id', 0),
            amount=data.get('amount', 0),
            timestamp=data.get('timestamp', datetime.utcnow())
        )


class AuctionUI:
    
    @staticmethod
    def build_caption(character: Character, auction: Auction) -> str:
        caption_lines = [
            "╭─「 🔨 <b>AUCTION</b> 」",
            "│",
            f"│ ✨ <b>{character.name}</b>",
            f"│ 🎭 <code>{character.anime}</code>",
            "│",
            f"│ 💰 Current: <b>{auction.current_bid:,}</b> gold",
            f"│ 📊 Min Next: <code>{auction.min_next_bid:,}</code>",
            f"│ 🔨 Bids: <code>{auction.bid_count}</code>",
            "│",
            f"│ ⏰ Time: <b>{auction.format_time_left()}</b>",
        ]
        
        if auction.highest_bidder:
            caption_lines.append(f"│ 👑 Leader: <code>User {auction.highest_bidder}</code>")
        
        caption_lines.extend([
            "│",
            "╰─────────"
        ])
        
        return "\n".join(caption_lines)
    
    @staticmethod
    def build_keyboard(auction: Auction, user_id: int) -> InlineKeyboardMarkup:
        keyboard = []
        
        if auction.is_active:
            if auction.highest_bidder != user_id:
                keyboard.append([
                    InlineKeyboardButton("🔨 PLACE BID", callback_data=f"auc_bid_{auction.character_id}"),
                    InlineKeyboardButton("📊 History", callback_data=f"auc_hist_{auction.character_id}")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton("👑 YOU'RE WINNING", callback_data="auc_winning"),
                    InlineKeyboardButton("📊 History", callback_data=f"auc_hist_{auction.character_id}")
                ])
            
            keyboard.append([
                InlineKeyboardButton("🔄 Refresh", callback_data="auc_refresh")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("⏰ AUCTION ENDED", callback_data="auc_ended")
            ])
        
        return InlineKeyboardMarkup(keyboard)


class AuctionManager:
    
    @staticmethod
    async def is_sudo(user_id: int) -> bool:
        return str(user_id) in SUDO_USERS
    
    @staticmethod
    async def get_active_auction() -> Optional[dict]:
        return await auction_collection.find_one({
            "status": "active",
            "end_time": {"$gt": datetime.utcnow()}
        })
    
    @staticmethod
    async def create_auction(char_id: str, starting_bid: int, 
                           duration_hours: int, created_by: int) -> tuple[bool, str]:
        
        character = await collection.find_one({"id": char_id})
        if not character:
            return False, "⚠️ Character not found"
        
        active = await AuctionManager.get_active_auction()
        if active:
            return False, "⚠️ Auction already active"
        
        end_time = datetime.utcnow() + timedelta(hours=duration_hours)
        
        await auction_collection.insert_one({
            "character_id": char_id,
            "starting_bid": starting_bid,
            "current_bid": starting_bid,
            "highest_bidder": None,
            "start_time": datetime.utcnow(),
            "end_time": end_time,
            "status": "active",
            "created_by": created_by,
            "bid_count": 0
        })
        
        return True, f"✅ Auction started for {character['name']}"
    
    @staticmethod
    async def place_bid(user_id: int, amount: int) -> tuple[bool, str]:
        auction_data = await AuctionManager.get_active_auction()
        if not auction_data:
            return False, "⚠️ No active auction"
        
        auction = Auction.from_db(auction_data)
        
        if amount < auction.min_next_bid:
            return False, f"⚠️ Minimum bid: {auction.min_next_bid:,} gold"
        
        user_data = await user_collection.find_one({"id": user_id})
        balance = user_data.get("balance", 0) if user_data else 0
        
        if balance < amount:
            return False, f"⚠️ Insufficient balance\n💰 Need: {amount:,}\n💳 Have: {balance:,}"
        
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
            "amount": amount,
            "timestamp": datetime.utcnow()
        })
        
        return True, f"✅ Bid placed: {amount:,} gold"
    
    @staticmethod
    async def end_auction() -> tuple[bool, str, Optional[int]]:
        auction_data = await auction_collection.find_one({"status": "active"})
        if not auction_data:
            return False, "⚠️ No active auction", None
        
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
                {"$set": {"status": "ended"}}
            )
            
            message = (
                f"🎊 <b>AUCTION WON!</b>\n\n"
                f"✨ {character['name']}\n"
                f"👑 Winner: <a href='tg://user?id={winner_id}'>User</a>\n"
                f"💰 Price: <b>{auction.current_bid:,}</b> gold"
            )
            return True, message, winner_id
        else:
            await auction_collection.update_one(
                {"_id": auction_data["_id"]},
                {"$set": {"status": "ended"}}
            )
            return True, "⚠️ No bids placed", None


async def auction_view_command(update: Update, context: CallbackContext):
    auction_data = await AuctionManager.get_active_auction()
    
    if not auction_data:
        await update.message.reply_text(
            "╭─「 🔨 <b>AUCTION</b> 」\n"
            "│\n"
            "│ No active auction\n"
            "│ Check back later!\n"
            "│\n"
            "╰─────────",
            parse_mode="HTML"
        )
        return
    
    await render_auction(update.message, context, auction_data, update.effective_user.id)


async def render_auction(message, context: CallbackContext, 
                        auction_data: dict, user_id: int, edit: bool = False):
    auction = Auction.from_db(auction_data)
    character_data = await collection.find_one({"id": auction.character_id})
    
    if not character_data:
        return
    
    character = Character.from_db(character_data)
    caption = AuctionUI.build_caption(character, auction)
    keyboard = AuctionUI.build_keyboard(auction, user_id)
    
    try:
        if edit:
            await message.edit_caption(
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        else:
            send_func = message.reply_video if character.is_video else message.reply_photo
            media_param = "video" if character.is_video else "photo"
            await send_func(
                **{media_param: character.img_url},
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )
    except BadRequest:
        if not edit:
            await message.reply_text(caption, parse_mode="HTML", reply_markup=keyboard)


async def auction_start_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not await AuctionManager.is_sudo(user_id):
        await update.message.reply_text("⛔️ No permission")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ Usage:\n"
            "<code>/astart &lt;id&gt; &lt;starting_bid&gt; &lt;hours&gt;</code>",
            parse_mode="HTML"
        )
        return
    
    char_id = context.args[0]
    starting_bid = int(context.args[1])
    duration = int(context.args[2])
    
    success, message = await AuctionManager.create_auction(
        char_id, starting_bid, duration, user_id
    )
    
    if success:
        auction_data = await AuctionManager.get_active_auction()
        if auction_data:
            await render_auction(update.message, context, auction_data, user_id)
        else:
            await update.message.reply_text(message, parse_mode="HTML")
    else:
        await update.message.reply_text(message, parse_mode="HTML")


async def auction_end_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not await AuctionManager.is_sudo(user_id):
        await update.message.reply_text("⛔️ No permission")
        return
    
    success, message, winner_id = await AuctionManager.end_auction()
    await update.message.reply_text(message, parse_mode="HTML")


async def bid_command(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text(
            "⚠️ Usage: <code>/bid &lt;amount&gt;</code>",
            parse_mode="HTML"
        )
        return
    
    user_id = update.effective_user.id
    amount = int(context.args[0])
    
    success, message = await AuctionManager.place_bid(user_id, amount)
    await update.message.reply_text(message, parse_mode="HTML")
    
    if success:
        auction_data = await AuctionManager.get_active_auction()
        if auction_data:
            await render_auction(update.message, context, auction_data, user_id)


async def auction_callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "auc_refresh":
        auction_data = await AuctionManager.get_active_auction()
        if auction_data:
            await render_auction(query.message, context, auction_data, user_id, edit=True)
        else:
            await query.answer("⏰ Auction ended", show_alert=True)
    
    elif data.startswith("auc_bid_"):
        auction_data = await AuctionManager.get_active_auction()
        if auction_data:
            auction = Auction.from_db(auction_data)
            await query.answer(
                f"💰 Place bid via: /bid {auction.min_next_bid}\n"
                f"⚠️ Minimum: {auction.min_next_bid:,} gold",
                show_alert=True
            )
        else:
            await query.answer("⏰ Auction ended", show_alert=True)
    
    elif data.startswith("auc_hist_"):
        char_id = data.split("_", 2)[2]
        auction_data = await auction_collection.find_one({"character_id": char_id})
        
        if auction_data:
            bids = await bid_collection.find(
                {"auction_id": auction_data["_id"]}
            ).sort("timestamp", -1).limit(5).to_list(5)
            
            if bids:
                history = "📊 Recent Bids:\n\n"
                for i, bid in enumerate(bids, 1):
                    history += f"{i}. {bid['amount']:,} gold\n"
                await query.answer(history, show_alert=True)
            else:
                await query.answer("No bids yet", show_alert=False)
        else:
            await query.answer("Auction not found", show_alert=False)
    
    elif data == "auc_winning":
        await query.answer("👑 You're currently winning!", show_alert=False)
    
    elif data == "auc_ended":
        await query.answer("⏰ This auction has ended", show_alert=False)


application.add_handler(CommandHandler("auction", auction_view_command, block=False))
application.add_handler(CommandHandler("astart", auction_start_command, block=False))
application.add_handler(CommandHandler("aend", auction_end_command, block=False))
application.add_handler(CommandHandler("bid", bid_command, block=False))
application.add_handler(CallbackQueryHandler(auction_callback_handler, pattern=r"^auc_", block=False))