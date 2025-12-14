from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Set
from enum import Enum
import asyncio
import random
from functools import wraps
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest, TimedOut, NetworkError
from telegram.constants import ParseMode, ChatAction

from shivu import application, db, user_collection

collection = db['anime_characters_lol']
giveaway_collection = db['giveaways']
participant_collection = db['giveaway_participants']

SUDO_USERS = {"8297659126", "8420981179", "5147822244"}

logger = logging.getLogger(__name__)


def typing_action(func):
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        if update.message:
            await update.message.chat.send_action(ChatAction.TYPING)
        return await func(update, context, *args, **kwargs)
    return wrapper


class GiveawayStatus(Enum):
    ACTIVE = "active"
    ENDED = "ended"
    CANCELLED = "cancelled"


class GiveawayType(Enum):
    RANDOM = "random"
    FIRST_COME = "first_come"
    REQUIREMENT = "requirement"


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
class Giveaway:
    character_id: str
    giveaway_type: str
    created_by: int
    start_time: datetime
    end_time: datetime
    status: str
    max_winners: int
    winners: List[int] = field(default_factory=list)
    participant_count: int = 0
    requirements: Dict[str, Any] = field(default_factory=dict)
    message_id: Optional[int] = None
    chat_id: Optional[int] = None
    
    @classmethod
    def from_db(cls, data: dict) -> 'Giveaway':
        return cls(
            character_id=data.get('character_id', ''),
            giveaway_type=data.get('giveaway_type', 'random'),
            created_by=data.get('created_by', 0),
            start_time=data.get('start_time', datetime.now(timezone.utc)),
            end_time=data.get('end_time', datetime.now(timezone.utc)),
            status=data.get('status', 'active'),
            max_winners=data.get('max_winners', 1),
            winners=data.get('winners', []),
            participant_count=data.get('participant_count', 0),
            requirements=data.get('requirements', {}),
            message_id=data.get('message_id'),
            chat_id=data.get('chat_id')
        )
    
    @property
    def time_remaining(self) -> timedelta:
        return self.end_time - datetime.now(timezone.utc)
    
    @property
    def is_active(self) -> bool:
        return (self.status == GiveawayStatus.ACTIVE.value and 
                datetime.now(timezone.utc) < self.end_time)
    
    @property
    def is_ending_soon(self) -> bool:
        return self.time_remaining.total_seconds() < 600
    
    def format_time_left(self) -> str:
        if not self.is_active:
            return "⏰ ENDED"
        
        td = self.time_remaining
        total_seconds = int(td.total_seconds())
        
        if total_seconds < 0:
            return "⏰ ENDED"
        
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        
        if days > 0:
            return f"🕐 {days}d {hours}h left"
        elif hours > 0:
            return f"🕐 {hours}h {minutes}m left"
        else:
            return f"🕐 {minutes}m left"
    
    def to_dict(self) -> dict:
        data = asdict(self)
        data['start_time'] = self.start_time.isoformat()
        data['end_time'] = self.end_time.isoformat()
        return data


@dataclass
class Participant:
    giveaway_id: str
    user_id: int
    user_name: str
    joined_at: datetime
    entries: int = 1
    
    @classmethod
    def from_db(cls, data: dict) -> 'Participant':
        return cls(
            giveaway_id=str(data.get('giveaway_id', '')),
            user_id=data.get('user_id', 0),
            user_name=data.get('user_name', 'Anonymous'),
            joined_at=data.get('joined_at', datetime.now(timezone.utc)),
            entries=data.get('entries', 1)
        )


class GiveawayUI:
    
    @staticmethod
    def build_caption(character: Character, giveaway: Giveaway, 
                     user_id: Optional[int] = None,
                     is_participant: bool = False) -> str:
        
        header = "╔═══════════════════════╗\n"
        header += "║   🎁 <b>GIVEAWAY</b>    ║\n"
        header += "╚═══════════════════════╝\n\n"
        
        type_emoji = {
            "random": "🎲",
            "first_come": "⚡",
            "requirement": "📋"
        }
        
        type_name = {
            "random": "RANDOM DRAW",
            "first_come": "FIRST COME",
            "requirement": "REQUIREMENT"
        }
        
        status_indicator = "🔥 ENDING SOON!" if giveaway.is_ending_soon else "✅ ACTIVE"
        
        body_lines = [
            f"<b>{status_indicator}</b>\n",
            f"✨ <b>{character.name}</b>",
            f"🎭 <code>{character.anime}</code>",
            f"{character.rarity}\n",
            f"━━━━━━━━━━━━━━━━━━━━━\n",
            f"{type_emoji.get(giveaway.giveaway_type, '🎁')} Type: <b>{type_name.get(giveaway.giveaway_type, 'UNKNOWN')}</b>",
            f"🏆 Winners: <code>{giveaway.max_winners}</code>",
            f"👥 Participants: <code>{giveaway.participant_count}</code>\n",
            f"{giveaway.format_time_left()}\n"
        ]
        
        if giveaway.requirements:
            body_lines.append("━━━━━━━━━━━━━━━━━━━━━")
            body_lines.append("<b>📋 Requirements:</b>")
            if giveaway.requirements.get('min_balance'):
                body_lines.append(f"💰 Min Balance: {giveaway.requirements['min_balance']:,}")
            if giveaway.requirements.get('min_characters'):
                body_lines.append(f"👥 Min Characters: {giveaway.requirements['min_characters']}")
            body_lines.append("")
        
        if is_participant:
            body_lines.extend([
                "━━━━━━━━━━━━━━━━━━━━━",
                "✅ <b>YOU'RE ENTERED!</b>",
                ""
            ])
        
        footer = [
            "━━━━━━━━━━━━━━━━━━━━━",
            "💬 <b>To Enter:</b>",
            "Click the button below!"
        ]
        
        return "\n".join([header] + body_lines + footer)
    
    @staticmethod
    def build_keyboard(giveaway: Giveaway, is_participant: bool = False) -> InlineKeyboardMarkup:
        keyboard = []
        
        if giveaway.is_active:
            if not is_participant:
                keyboard.append([
                    InlineKeyboardButton("🎁 ENTER GIVEAWAY", callback_data=f"g8en_{giveaway.character_id}")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton("✅ ENTERED", callback_data="g4al")
                ])
            
            keyboard.append([
                InlineKeyboardButton(f"👥 {giveaway.participant_count} Participants", callback_data=f"g7pa_{giveaway.character_id}"),
                InlineKeyboardButton("🔄 Refresh", callback_data=f"g5rf_{giveaway.character_id}")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("⏰ GIVEAWAY ENDED", callback_data="g2ed")
            ])
            
            if giveaway.winners:
                keyboard.append([
                    InlineKeyboardButton("🏆 View Winners", callback_data=f"g6wn_{giveaway.character_id}")
                ])
        
        return InlineKeyboardMarkup(keyboard)


class GiveawayManager:
    _lock = asyncio.Lock()
    
    @staticmethod
    async def is_sudo(user_id: int) -> bool:
        return str(user_id) in SUDO_USERS
    
    @staticmethod
    async def get_active_giveaway(character_id: Optional[str] = None) -> Optional[dict]:
        query = {"status": "active", "end_time": {"$gt": datetime.now(timezone.utc)}}
        if character_id:
            query["character_id"] = character_id
        return await giveaway_collection.find_one(query)
    
    @staticmethod
    async def get_all_active_giveaways() -> List[dict]:
        return await giveaway_collection.find({
            "status": "active",
            "end_time": {"$gt": datetime.now(timezone.utc)}
        }).to_list(None)
    
    @staticmethod
    async def create_giveaway(char_id: str, giveaway_type: str, 
                            duration_hours: int, max_winners: int,
                            created_by: int, requirements: Dict[str, Any] = None,
                            chat_id: Optional[int] = None,
                            message_id: Optional[int] = None) -> tuple[bool, str]:
        
        character = await collection.find_one({"id": char_id})
        if not character:
            return False, "⚠️ Character not found in database"
        
        existing = await giveaway_collection.find_one({
            "character_id": char_id,
            "status": "active"
        })
        if existing:
            return False, "⚠️ Giveaway already exists for this character"
        
        end_time = datetime.now(timezone.utc) + timedelta(hours=duration_hours)
        
        giveaway_data = {
            "character_id": char_id,
            "giveaway_type": giveaway_type,
            "created_by": created_by,
            "start_time": datetime.now(timezone.utc),
            "end_time": end_time,
            "status": "active",
            "max_winners": max_winners,
            "winners": [],
            "participant_count": 0,
            "requirements": requirements or {},
            "message_id": message_id,
            "chat_id": chat_id
        }
        
        await giveaway_collection.insert_one(giveaway_data)
        
        msg = "╔═══════════════════════╗\n"
        msg += "║ ✅ <b>GIVEAWAY CREATED</b> ║\n"
        msg += "╚═══════════════════════╝\n\n"
        msg += f"✨ <b>{character['name']}</b>\n"
        msg += f"🏆 Winners: <code>{max_winners}</code>\n"
        msg += f"⏰ Duration: <code>{duration_hours}h</code>"
        
        return True, msg
    
    @staticmethod
    async def join_giveaway(user_id: int, char_id: str, 
                          user_name: str = "Anonymous") -> tuple[bool, str]:
        async with GiveawayManager._lock:
            giveaway_data = await GiveawayManager.get_active_giveaway(char_id)
            if not giveaway_data:
                return False, "⚠️ No active giveaway found"
            
            giveaway = Giveaway.from_db(giveaway_data)
            
            if not giveaway.is_active:
                return False, "⏰ Giveaway has ended"
            
            existing = await participant_collection.find_one({
                "giveaway_id": giveaway_data["_id"],
                "user_id": user_id
            })
            
            if existing:
                return False, "✅ You're already entered in this giveaway!"
            
            if giveaway.requirements:
                user_data = await user_collection.find_one({"id": user_id})
                if not user_data:
                    return False, "⚠️ User data not found"
                
                if giveaway.requirements.get('min_balance'):
                    balance = user_data.get('balance', 0)
                    if balance < giveaway.requirements['min_balance']:
                        return False, f"⚠️ Minimum balance required: {giveaway.requirements['min_balance']:,} gold"
                
                if giveaway.requirements.get('min_characters'):
                    char_count = len(user_data.get('characters', []))
                    if char_count < giveaway.requirements['min_characters']:
                        return False, f"⚠️ Minimum {giveaway.requirements['min_characters']} characters required"
            
            await participant_collection.insert_one({
                "giveaway_id": giveaway_data["_id"],
                "user_id": user_id,
                "user_name": user_name,
                "joined_at": datetime.now(timezone.utc),
                "entries": 1
            })
            
            await giveaway_collection.update_one(
                {"_id": giveaway_data["_id"]},
                {"$inc": {"participant_count": 1}}
            )
            
            msg = "╔═══════════════════════╗\n"
            msg += "║  ✅ <b>ENTRY SUCCESS!</b> ║\n"
            msg += "╚═══════════════════════╝\n\n"
            msg += f"🎁 You're now entered!\n"
            msg += f"👥 Total Entries: <b>{giveaway.participant_count + 1}</b>\n"
            msg += f"🍀 Good luck!"
            
            return True, msg
    
    @staticmethod
    async def end_giveaway(char_id: str) -> tuple[bool, str, List[int]]:
        giveaway_data = await giveaway_collection.find_one({
            "character_id": char_id,
            "status": "active"
        })
        
        if not giveaway_data:
            return False, "⚠️ No active giveaway found", []
        
        giveaway = Giveaway.from_db(giveaway_data)
        
        participants = await participant_collection.find({
            "giveaway_id": giveaway_data["_id"]
        }).to_list(None)
        
        if not participants:
            await giveaway_collection.update_one(
                {"_id": giveaway_data["_id"]},
                {"$set": {"status": "ended"}}
            )
            return True, "⚠️ No participants in giveaway", []
        
        character = await collection.find_one({"id": char_id})
        
        if giveaway.giveaway_type == "random":
            num_winners = min(giveaway.max_winners, len(participants))
            winners = random.sample(participants, num_winners)
        elif giveaway.giveaway_type == "first_come":
            sorted_participants = sorted(participants, key=lambda x: x['joined_at'])
            num_winners = min(giveaway.max_winners, len(sorted_participants))
            winners = sorted_participants[:num_winners]
        else:
            num_winners = min(giveaway.max_winners, len(participants))
            winners = random.sample(participants, num_winners)
        
        winner_ids = [w['user_id'] for w in winners]
        
        for winner in winners:
            await user_collection.update_one(
                {"id": winner['user_id']},
                {"$push": {"characters": character}},
                upsert=True
            )
        
        await giveaway_collection.update_one(
            {"_id": giveaway_data["_id"]},
            {
                "$set": {
                    "status": "ended",
                    "winners": winner_ids,
                    "end_time": datetime.now(timezone.utc)
                }
            }
        )
        
        message = "╔═══════════════════════╗\n"
        message += "║ 🎊 <b>GIVEAWAY ENDED!</b> ║\n"
        message += "╚═══════════════════════╝\n\n"
        message += f"✨ <b>{character['name']}</b>\n\n"
        message += f"🏆 <b>WINNERS:</b>\n"
        for i, winner in enumerate(winners, 1):
            message += f"{i}. <a href='tg://user?id={winner['user_id']}'>{winner['user_name']}</a>\n"
        message += f"\n👥 Total Participants: <code>{len(participants)}</code>"
        
        return True, message, winner_ids
    
    @staticmethod
    async def is_participant(user_id: int, giveaway_id) -> bool:
        existing = await participant_collection.find_one({
            "giveaway_id": giveaway_id,
            "user_id": user_id
        })
        return existing is not None
    
    @staticmethod
    async def get_participants(giveaway_id, limit: int = 10) -> List[Participant]:
        participants = await participant_collection.find({
            "giveaway_id": giveaway_id
        }).sort("joined_at", -1).limit(limit).to_list(limit)
        
        return [Participant.from_db(p) for p in participants]


@typing_action
async def giveaway_view_command(update: Update, context: CallbackContext):
    giveaways = await GiveawayManager.get_all_active_giveaways()
    
    if not giveaways:
        msg = "╔═══════════════════════╗\n"
        msg += "║ 🎁 <b>NO GIVEAWAYS</b>  ║\n"
        msg += "╚═══════════════════════╝\n\n"
        msg += "No active giveaways\n"
        msg += "Check back later!"
        
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return
    
    if len(giveaways) == 1:
        await render_giveaway(update.message, context, giveaways[0], update.effective_user.id)
    else:
        context.user_data['giveaway_ids'] = [g['character_id'] for g in giveaways]
        context.user_data['giveaway_page'] = 0
        await render_giveaway_list(update.message, context, update.effective_user.id)


async def render_giveaway(message, context: CallbackContext, 
                         giveaway_data: dict, user_id: int, edit: bool = False):
    giveaway = Giveaway.from_db(giveaway_data)
    character_data = await collection.find_one({"id": giveaway.character_id})
    
    if not character_data:
        return
    
    character = Character.from_db(character_data)
    is_participant = await GiveawayManager.is_participant(user_id, giveaway_data["_id"])
    
    caption = GiveawayUI.build_caption(character, giveaway, user_id, is_participant)
    keyboard = GiveawayUI.build_keyboard(giveaway, is_participant)
    
    try:
        if edit:
            await message.edit_caption(
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
        else:
            send_func = message.reply_video if character.is_video else message.reply_photo
            media_param = "video" if character.is_video else "photo"
            await send_func(
                **{media_param: character.img_url},
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
    except (BadRequest, TimedOut, NetworkError) as e:
        logger.error(f"Error rendering giveaway: {e}")
        if not edit:
            await message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def render_giveaway_list(message, context: CallbackContext, user_id: int):
    giveaway_ids = context.user_data.get('giveaway_ids', [])
    page = context.user_data.get('giveaway_page', 0)
    
    if not giveaway_ids or page >= len(giveaway_ids):
        return
    
    char_id = giveaway_ids[page]
    giveaway_data = await GiveawayManager.get_active_giveaway(char_id)
    
    if giveaway_data:
        await render_giveaway(message, context, giveaway_data, user_id)


@typing_action
async def giveaway_start_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not await GiveawayManager.is_sudo(user_id):
        await update.message.reply_text("⛔️ No permission")
        return
    
    if len(context.args) < 4:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b>\n"
            "<code>/gstart &lt;id&gt; &lt;type&gt; &lt;hours&gt; &lt;winners&gt; [min_bal] [min_chars]</code>\n\n"
            "<b>Types:</b> random, first_come, requirement\n\n"
            "<b>Examples:</b>\n"
            "<code>/gstart char123 random 24 1</code>\n"
            "<code>/gstart char123 requirement 48 3 5000 10</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    char_id = context.args[0]
    giveaway_type = context.args[1].lower()
    duration = int(context.args[2])
    max_winners = int(context.args[3])
    
    if giveaway_type not in ["random", "first_come", "requirement"]:
        await update.message.reply_text("⚠️ Invalid type. Use: random, first_come, or requirement")
        return
    
    requirements = {}
    if len(context.args) >= 5:
        requirements['min_balance'] = int(context.args[4])
    if len(context.args) >= 6:
        requirements['min_characters'] = int(context.args[5])
    
    success, message = await GiveawayManager.create_giveaway(
        char_id, giveaway_type, duration, max_winners, user_id, requirements
    )
    
    if success:
        giveaway_data = await GiveawayManager.get_active_giveaway(char_id)
        if giveaway_data:
            await render_giveaway(update.message, context, giveaway_data, user_id)
        else:
            await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)


@typing_action
async def giveaway_end_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not await GiveawayManager.is_sudo(user_id):
        await update.message.reply_text("⛔️ No permission")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/gend &lt;character_id&gt;</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    char_id = context.args[0]
    success, message, winners = await GiveawayManager.end_giveaway(char_id)
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)


async def giveaway_callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_name = query.from_user.first_name or "Anonymous"
    data = query.data
    
    try:
        if data.startswith("g8en_"):
            char_id = data.split("_", 1)[1]
            success, message = await GiveawayManager.join_giveaway(user_id, char_id, user_name)
            await query.answer(message, show_alert=True)
            
            if success:
                await asyncio.sleep(1)
                giveaway_data = await GiveawayManager.get_active_giveaway(char_id)
                if giveaway_data:
                    await render_giveaway(query.message, context, giveaway_data, user_id, edit=True)
        
        elif data.startswith("g5rf_"):
            char_id = data.split("_", 1)[1]
            giveaway_data = await GiveawayManager.get_active_giveaway(char_id)
            if giveaway_data:
                await render_giveaway(query.message, context, giveaway_data, user_id, edit=True)
            else:
                await query.answer("⏰ Giveaway ended", show_alert=True)
        
        elif data.startswith("g7pa_"):
            char_id = data.split("_", 1)[1]
            giveaway_data = await GiveawayManager.get_active_giveaway(char_id)
            
            if giveaway_data:
                participants = await GiveawayManager.get_participants(giveaway_data["_id"], 5)
                
                if participants:
                    msg = "👥 <b>Recent Participants:</b>\n\n"
                    for i, p in enumerate(participants, 1):
                        msg += f"{i}. {p.user_name}\n"
                    msg += f"\n<b>Total: {giveaway_data['participant_count']}</b>"
                    await query.answer(msg, show_alert=True)
                else:
                    await query.answer("No participants yet", show_alert=False)
            else:
                await query.answer("Giveaway not found", show_alert=False)
        
        elif data.startswith("g6wn_"):
            char_id = data.split("_", 1)[1]
            giveaway_data = await giveaway_collection.find_one({
                "character_id": char_id,
                "status": "ended"
            })
            
            if giveaway_data and giveaway_data.get('winners'):
                msg = "🏆 <b>WINNERS:</b>\n\n"
                for i, winner_id in enumerate(giveaway_data['winners'], 1):
                    msg += f"{i}. User {winner_id}\n"
                await query.answer(msg, show_alert=True)
            else:
                await query.answer("No winners found", show_alert=False)
        
        elif data == "g4al":
            await query.answer("✅ You're already entered!", show_alert=False)
        
        elif data == "g2ed":
            await query.answer("⏰ This giveaway has ended", show_alert=False)
    
    except Exception as e:
        logger.error(f"Giveaway callback error: {e}")
        await query.answer("⚠️ An error occurred", show_alert=True)


application.add_handler(CommandHandler("giveaway", giveaway_view_command, block=False))
application.add_handler(CommandHandler("gstart", giveaway_start_command, block=False))
application.add_handler(CommandHandler("gend", giveaway_end_command, block=False))
application.add_handler(CallbackQueryHandler(giveaway_callback_handler, pattern=r"^g[0-9][a-z]{2}", block=False))