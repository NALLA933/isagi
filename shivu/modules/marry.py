import asyncio
import time
import random
from dataclasses import dataclass, field
from enum import Enum
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext
from telegram.error import TelegramError, BadRequest, Forbidden

from shivu import application, user_collection, collection


class ProposalResult(Enum):
    SUCCESS = "success"
    REJECTED = "rejected"
    NO_CHARS = "no_chars"
    ERROR = "error"


@dataclass(frozen=True)
class MarryConfig:
    proposal_cost: int = 2000
    dice_cooldown: int = 1800
    propose_cooldown: int = 300
    support_group: str = "THE_DRAGON_SUPPORT"
    support_link: str = "https://t.me/THE_DRAGON_SUPPORT"
    common_rarities: tuple = ('🟢 Common', '🟣 Rare', '🟡 Legendary')
    rare_rarities: tuple = ('💮 Special Edition', '💫 Neon', '✨ Manga', '🎐 Celestial')
    proposal_success_rate: float = 0.4
    min_balance: int = 0
    max_cooldown_display: int = 3600


@dataclass
class Cooldowns:
    dice: dict = field(default_factory=dict)
    propose: dict = field(default_factory=dict)
    
    def cleanup_old(self, max_age: int = 7200):
        """Remove cooldowns older than max_age seconds"""
        current = time.time()
        self.dice = {k: v for k, v in self.dice.items() if current - v < max_age}
        self.propose = {k: v for k, v in self.propose.items() if current - v < max_age}


CONFIG = MarryConfig()
cooldowns = Cooldowns()

SUCCESS_MSGS = [
    "ᴀᴄᴄᴇᴘᴛᴇᴅ ʏᴏᴜʀ ᴘʀᴏᴘᴏsᴀʟ",
    "sᴀɪᴅ ʏᴇs ᴛᴏ ʏᴏᴜʀ ʜᴇᴀʀᴛ",
    "ɪs ɴᴏᴡ ʏᴏᴜʀs ғᴏʀᴇᴠᴇʀ",
    "ᴊᴏɪɴᴇᴅ ʏᴏᴜʀ ʜᴀʀᴇᴍ",
    "ғᴇʟʟ ғᴏʀ ʏᴏᴜ"
]

FAIL_MSGS = [
    "sʜᴇ ʀᴇᴊᴇᴄᴛᴇᴅ ʏᴏᴜ ᴀɴᴅ ʀᴀɴ ᴀᴡᴀʏ",
    "sʜᴇ sᴀɪᴅ ɴᴏ ᴀɴᴅ ʟᴇғᴛ",
    "sʜᴇ ᴡᴀʟᴋᴇᴅ ᴀᴡᴀʏ ғʀᴏᴍ ʏᴏᴜ",
    "sʜᴇ ᴅɪsᴀᴘᴘᴇᴀʀᴇᴅ ɪɴ ᴛʜᴇ ᴡɪɴᴅ",
    "ʙᴇᴛᴛᴇʀ ʟᴜᴄᴋ ɴᴇxᴛ ᴛɪᴍᴇ"
]


def check_cooldown(user_id: int, cmd_type: str, cooldown_time: int) -> int | None:
    """Check cooldown and return remaining seconds or None"""
    try:
        cd = cooldowns.dice if cmd_type == 'dice' else cooldowns.propose
        
        if user_id in cd:
            elapsed = time.time() - cd[user_id]
            if elapsed < cooldown_time:
                remaining = int(cooldown_time - elapsed)
                return min(remaining, CONFIG.max_cooldown_display)
        
        cd[user_id] = time.time()
        
        if len(cd) > 10000:
            cooldowns.cleanup_old()
        
        return None
    except Exception:
        return None


async def is_in_support(context: CallbackContext, user_id: int) -> bool:
    """Check if user is in support group with proper error handling"""
    try:
        chat = await context.bot.get_chat(f"@{CONFIG.support_group}")
        member = await context.bot.get_chat_member(chat.id, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Forbidden:
        return False
    except BadRequest:
        return False
    except TelegramError:
        return False
    except Exception:
        return False


def support_button() -> InlineKeyboardMarkup:
    """Generate support group button"""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔗 ᴊᴏɪɴ sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ", url=CONFIG.support_link)
    ]])


async def get_unique_char(user_id: int, rarities: tuple = None) -> dict | None:
    """Fetch unique character with enhanced error handling"""
    try:
        rarities = rarities or CONFIG.common_rarities
        
        if not isinstance(rarities, (list, tuple)) or not rarities:
            return None
        
        user_data = await user_collection.find_one({'id': user_id})
        claimed_ids = [c.get('id') for c in user_data.get('characters', [])] if user_data else []
        
        if not isinstance(claimed_ids, list):
            claimed_ids = []
        
        pipeline = [
            {'$match': {'rarity': {'$in': list(rarities)}, 'id': {'$nin': claimed_ids}}},
            {'$sample': {'size': 1}}
        ]
        
        chars = await collection.aggregate(pipeline).to_list(length=1)
        
        if chars and len(chars) > 0:
            char = chars[0]
            if all(k in char for k in ['id', 'name', 'anime', 'rarity', 'img_url']):
                return char
        
        return None
    except Exception:
        return None


async def add_char(user_id: int, username: str | None, first_name: str, char: dict) -> bool:
    """Add character to user with transaction-like behavior"""
    try:
        if not char or not isinstance(char, dict):
            return False
        
        if not all(k in char for k in ['id', 'name']):
            return False
        
        user_exists = await user_collection.find_one({'id': user_id})
        
        if user_exists:
            result = await user_collection.update_one(
                {'id': user_id},
                {
                    '$push': {'characters': char},
                    '$set': {
                        'username': username,
                        'first_name': first_name,
                        'last_updated': time.time()
                    }
                }
            )
            return result.modified_count > 0
        else:
            result = await user_collection.insert_one({
                'id': user_id,
                'username': username,
                'first_name': first_name,
                'characters': [char],
                'balance': 0,
                'created_at': time.time(),
                'last_updated': time.time()
            })
            return result.inserted_id is not None
    except Exception:
        return False


def format_caption(user_id: int, first_name: str, char: dict | None, is_win: bool, dice_val: int | None = None) -> str:
    """Format message caption with sanitization"""
    try:
        first_name = first_name[:50] if first_name else "Player"
        
        if is_win and char:
            event = f"\nᴇᴠᴇɴᴛ: <b>{char['event']['name'][:50]}</b>" if char.get('event', {}).get('name') else ""
            origin = f"\nᴏʀɪɢɪɴ: <b>{char.get('origin', '')[:50]}</b>" if char.get('origin') else ""
            abilities = f"\nᴀʙɪʟɪᴛɪᴇs: <b>{char.get('abilities', '')[:100]}</b>" if char.get('abilities') else ""
            description = f"\nᴅᴇsᴄʀɪᴘᴛɪᴏɴ: <b>{char.get('description', '')[:150]}</b>" if char.get('description') else ""
            
            return (
                f"{'ᴅɪᴄᴇ ʀᴇsᴜʟᴛ: ' + str(dice_val) + '\n' if dice_val else ''}"
                f"ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs <a href='tg://user?id={user_id}'>{first_name}</a>\n"
                f"{char.get('name', 'Unknown')[:50]} {random.choice(SUCCESS_MSGS)}\n"
                f"ɴᴀᴍᴇ: <b>{char.get('name', 'Unknown')[:50]}</b>\n"
                f"ʀᴀʀɪᴛʏ: <b>{char.get('rarity', 'Unknown')[:30]}</b>\n"
                f"ᴀɴɪᴍᴇ: <b>{char.get('anime', 'Unknown')[:50]}</b>\n"
                f"ɪᴅ: <code>{char.get('id', 'N/A')}</code>{event}{origin}{abilities}{description}\n"
                f"ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ʜᴀʀᴇᴍ ✨"
            )
        
        return (
            f"ᴅɪᴄᴇ ʀᴇsᴜʟᴛ: <b>{dice_val}</b>\n"
            f"{random.choice(FAIL_MSGS)}\n"
            f"ᴘʟᴀʏᴇʀ: <a href='tg://user?id={user_id}'>{first_name}</a>\n"
            f"ɴᴇᴇᴅᴇᴅ: <b>1</b> ᴏʀ <b>6</b>\n"
            f"ᴛʀʏ ᴀɢᴀɪɴ ɪɴ 30 ᴍɪɴᴜᴛᴇs ⏰"
        )
    except Exception:
        return "ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ғᴏʀᴍᴀᴛᴛɪɴɢ ᴍᴇssᴀɢᴇ"


async def refund_coins(user_id: int, amount: int) -> bool:
    """Safely refund coins to user"""
    try:
        result = await user_collection.update_one(
            {'id': user_id},
            {'$inc': {'balance': amount}}
        )
        return result.modified_count > 0
    except Exception:
        return False


async def deduct_coins(user_id: int, amount: int) -> bool:
    """Safely deduct coins from user"""
    try:
        result = await user_collection.update_one(
            {'id': user_id, 'balance': {'$gte': amount}},
            {'$inc': {'balance': -amount}}
        )
        return result.modified_count > 0
    except Exception:
        return False


async def dice_marry(update: Update, context: CallbackContext):
    """Dice marry command with enhanced error handling"""
    if not update.message or not update.effective_user:
        return
    
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "Player"
    username = update.effective_user.username
    
    if remaining := check_cooldown(user_id, 'dice', CONFIG.dice_cooldown):
        try:
            await update.message.reply_text(
                f"⏳ ᴄᴏᴏʟᴅᴏᴡɴ ᴀᴄᴛɪᴠᴇ\n\n"
                f"ᴡᴀɪᴛ <b>{remaining // 60}ᴍ {remaining % 60}s</b> ʙᴇғᴏʀᴇ ʀᴏʟʟɪɴɢ ᴀɢᴀɪɴ",
                parse_mode='HTML'
            )
        except (BadRequest, Forbidden):
            pass
        return
    
    try:
        if not await user_collection.find_one({'id': user_id}):
            await update.message.reply_text(
                "❌ ɴᴏ ᴀᴄᴄᴏᴜɴᴛ ғᴏᴜɴᴅ\n\n"
                "ʏᴏᴜ ɴᴇᴇᴅ ᴛᴏ ɢʀᴀʙ ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ғɪʀsᴛ\nᴜsᴇ /grab",
                parse_mode='HTML'
            )
            return
    except Exception:
        await update.message.reply_text("❌ ᴅᴀᴛᴀʙᴀsᴇ ᴇʀʀᴏʀ. ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ")
        return
    
    try:
        dice_msg = await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='🎲')
        
        if not dice_msg or not dice_msg.dice:
            await update.message.reply_text("❌ ғᴀɪʟᴇᴅ ᴛᴏ ʀᴏʟʟ ᴅɪᴄᴇ")
            return
        
        dice_val = dice_msg.dice.value
        await asyncio.sleep(3)
        
        if dice_val in [1, 6]:
            char = await get_unique_char(user_id)
            
            if not char:
                await update.message.reply_text(
                    "💔 ɴᴏ ᴀᴠᴀɪʟᴀʙʟᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs\n\n"
                    "ᴀʟʟ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴀʀᴇ ᴄʟᴀɪᴍᴇᴅ ᴏʀ ʏᴏᴜ ᴏᴡɴ ᴛʜᴇᴍ ᴀʟʟ\n"
                    "ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ",
                    parse_mode='HTML'
                )
                return
            
            if not await add_char(user_id, username, first_name, char):
                await update.message.reply_text(
                    "⚠️ ғᴀɪʟᴇᴅ ᴛᴏ ᴀᴅᴅ ᴄʜᴀʀᴀᴄᴛᴇʀ\n\n"
                    "ᴘʟᴇᴀsᴇ ᴄᴏɴᴛᴀᴄᴛ sᴜᴘᴘᴏʀᴛ ɪғ ᴛʜɪs ᴘᴇʀsɪsᴛs",
                    parse_mode='HTML'
                )
                return
            
            caption = format_caption(user_id, first_name, char, True, dice_val)
            img_url = char.get('img_url', 'https://i.imgur.com/placeholder.png')
            
            try:
                await update.message.reply_photo(photo=img_url, caption=caption, parse_mode='HTML')
            except BadRequest:
                await update.message.reply_text(f"{caption}\n\n⚠️ ɪᴍᴀɢᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ", parse_mode='HTML')
        else:
            caption = format_caption(user_id, first_name, None, False, dice_val)
            await update.message.reply_text(caption, parse_mode='HTML')
    
    except Forbidden:
        pass
    except BadRequest as e:
        await update.message.reply_text(f"❌ ʀᴇǫᴜᴇsᴛ ᴇʀʀᴏʀ: {str(e)[:50]}")
    except Exception as e:
        await update.message.reply_text(f"❌ ᴜɴᴇxᴘᴇᴄᴛᴇᴅ ᴇʀʀᴏʀ: <code>{str(e)[:100]}</code>", parse_mode='HTML')


async def propose(update: Update, context: CallbackContext):
    """Propose command with comprehensive error handling"""
    if not update.message or not update.effective_user:
        return
    
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "Player"
    username = update.effective_user.username
    
    try:
        is_member = await is_in_support(context, user_id)
    except Exception:
        is_member = False
    
    if not is_member:
        try:
            await update.message.reply_text(
                "❌ sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ ʀᴇǫᴜɪʀᴇᴅ\n\n"
                "ʏᴏᴜ ᴍᴜsᴛ ᴊᴏɪɴ ᴏᴜʀ sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ ᴛᴏ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ\n"
                "ᴊᴏɪɴ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ 💕",
                reply_markup=support_button()
            )
        except (BadRequest, Forbidden):
            pass
        return
    
    try:
        user_data = await user_collection.find_one({'id': user_id})
        
        if not user_data:
            await update.message.reply_text(
                "❌ ɴᴏ ᴀᴄᴄᴏᴜɴᴛ ғᴏᴜɴᴅ\n\n"
                "ᴘʟᴇᴀsᴇ sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ ғɪʀsᴛ ➡️ /start"
            )
            return
    except Exception:
        await update.message.reply_text("❌ ᴅᴀᴛᴀʙᴀsᴇ ᴇʀʀᴏʀ. ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ")
        return
    
    if remaining := check_cooldown(user_id, 'propose', CONFIG.propose_cooldown):
        await update.message.reply_text(
            f"⏳ ᴄᴏᴏʟᴅᴏᴡɴ ᴀᴄᴛɪᴠᴇ\n\n"
            f"ᴡᴀɪᴛ <b>{remaining // 60}ᴍ {remaining % 60}s</b>",
            parse_mode='HTML'
        )
        return
    
    balance = user_data.get('balance', 0)
    
    if not isinstance(balance, (int, float)) or balance < CONFIG.proposal_cost:
        await update.message.reply_text(
            f"💰 ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ\n\n"
            f"ʀᴇǫᴜɪʀᴇᴅ: <b>{CONFIG.proposal_cost:,}</b> ᴄᴏɪɴs\n"
            f"ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ: <b>{int(balance):,}</b> ᴄᴏɪɴs",
            parse_mode='HTML'
        )
        return
    
    if not await deduct_coins(user_id, CONFIG.proposal_cost):
        await update.message.reply_text("❌ ғᴀɪʟᴇᴅ ᴛᴏ ᴅᴇᴅᴜᴄᴛ ᴄᴏɪɴs. ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ")
        return
    
    try:
        await update.message.reply_photo(
            photo='https://te.legra.ph/file/4d0f83726fe8cd637d3ff.jpg',
            caption='💍 ᴘʀᴇᴘᴀʀɪɴɢ ᴛᴏ ᴘʀᴏᴘᴏsᴇ...\n\nғɪɴᴀʟʟʏ ᴛʜᴇ ᴛɪᴍᴇ ʜᴀs ᴄᴏᴍᴇ'
        )
        await asyncio.sleep(2)
        
        await update.message.reply_text("💕 ᴘʀᴏᴘᴏsɪɴɢ...\n\nʏᴏᴜʀ ʜᴇᴀʀᴛ ɪs ʀᴀᴄɪɴɢ")
        await asyncio.sleep(2)
        
        if random.random() > CONFIG.proposal_success_rate:
            await update.message.reply_photo(
                photo='https://graph.org/file/48c147582d2742105e6ec.jpg',
                caption='💔 ʀᴇᴊᴇᴄᴛᴇᴅ\n\nsʜᴇ ʀᴇᴊᴇᴄᴛᴇᴅ ʏᴏᴜʀ ᴘʀᴏᴘᴏsᴀʟ ᴀɴᴅ ʀᴀɴ ᴀᴡᴀʏ\nʙᴇᴛᴛᴇʀ ʟᴜᴄᴋ ɴᴇxᴛ ᴛɪᴍᴇ'
            )
            return
        
        char = await get_unique_char(user_id, CONFIG.rare_rarities)
        
        if not char:
            await refund_coins(user_id, CONFIG.proposal_cost)
            await update.message.reply_text(
                "💔 ɴᴏ ᴀᴠᴀɪʟᴀʙʟᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs\n\n"
                "ᴀʟʟ ʀᴀʀᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴀʀᴇ ᴄʟᴀɪᴍᴇᴅ\n"
                f"ᴄᴏɪɴs ʀᴇғᴜɴᴅᴇᴅ: <b>{CONFIG.proposal_cost:,}</b>",
                parse_mode='HTML'
            )
            return
        
        if not await add_char(user_id, username, first_name, char):
            await refund_coins(user_id, CONFIG.proposal_cost)
            await update.message.reply_text(
                "⚠️ ᴇʀʀᴏʀ ᴀᴅᴅɪɴɢ ᴄʜᴀʀᴀᴄᴛᴇʀ\n\n"
                f"ᴄᴏɪɴs ʀᴇғᴜɴᴅᴇᴅ: <b>{CONFIG.proposal_cost:,}</b>\n"
                "ᴘʟᴇᴀsᴇ ᴄᴏɴᴛᴀᴄᴛ sᴜᴘᴘᴏʀᴛ ɪғ ᴛʜɪs ᴘᴇʀsɪsᴛs",
                parse_mode='HTML'
            )
            return
        
        caption = format_caption(user_id, first_name, char, True)
        img_url = char.get('img_url', 'https://i.imgur.com/placeholder.png')
        
        try:
            await update.message.reply_photo(photo=img_url, caption=caption, parse_mode='HTML')
        except BadRequest:
            await update.message.reply_text(f"{caption}\n\n⚠️ ɪᴍᴀɢᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ", parse_mode='HTML')
    
    except Forbidden:
        await refund_coins(user_id, CONFIG.proposal_cost)
    except BadRequest as e:
        await refund_coins(user_id, CONFIG.proposal_cost)
        await update.message.reply_text(f"❌ ʀᴇǫᴜᴇsᴛ ᴇʀʀᴏʀ. ᴄᴏɪɴs ʀᴇғᴜɴᴅᴇᴅ")
    except Exception as e:
        await refund_coins(user_id, CONFIG.proposal_cost)
        await update.message.reply_text(
            f"❌ ᴜɴᴇxᴘᴇᴄᴛᴇᴅ ᴇʀʀᴏʀ\n\n"
            f"ᴄᴏɪɴs ʀᴇғᴜɴᴅᴇᴅ: <b>{CONFIG.proposal_cost:,}</b>\n"
            f"ᴇʀʀᴏʀ: <code>{str(e)[:100]}</code>",
            parse_mode='HTML'
        )


application.add_handler(CommandHandler(['dice', 'marry'], dice_marry, block=False))
application.add_handler(CommandHandler('propose', propose, block=False))