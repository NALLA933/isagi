import asyncio
import time
import random
from dataclasses import dataclass, field
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext
from telegram.error import TelegramError

from shivu import application, user_collection, collection


@dataclass(frozen=True)
class MarryConfig:
    proposal_cost: int = 2000
    dice_cooldown: int = 1800
    propose_cooldown: int = 300
    support_group: str = "THE_DRAGON_SUPPORT"
    support_link: str = "https://t.me/THE_DRAGON_SUPPORT"
    common_rarities: tuple = ('🟢 Common', '🟣 Rare', '🟡 Legendary')
    rare_rarities: tuple = ('💮 Special Edition', '💫 Neon', '✨ Manga', '🎐 Celestial')


@dataclass
class Cooldowns:
    dice: dict = field(default_factory=dict)
    propose: dict = field(default_factory=dict)


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
    cd = cooldowns.dice if cmd_type == 'dice' else cooldowns.propose
    if user_id in cd:
        elapsed = time.time() - cd[user_id]
        if elapsed < cooldown_time:
            return int(cooldown_time - elapsed)
    cd[user_id] = time.time()
    return None


async def is_in_support(context: CallbackContext, user_id: int) -> bool:
    try:
        chat = await context.bot.get_chat(f"@{CONFIG.support_group}")
        member = await context.bot.get_chat_member(chat.id, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except (TelegramError, Exception):
        return False


def support_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔗 ᴊᴏɪɴ sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ", url=CONFIG.support_link)
    ]])


async def get_unique_char(user_id: int, rarities: tuple = None) -> dict | None:
    try:
        rarities = rarities or CONFIG.common_rarities
        user_data = await user_collection.find_one({'id': user_id})
        claimed_ids = [c.get('id') for c in user_data.get('characters', [])] if user_data else []
        
        pipeline = [
            {'$match': {'rarity': {'$in': rarities}, 'id': {'$nin': claimed_ids}}},
            {'$sample': {'size': 1}}
        ]
        
        if chars := await collection.aggregate(pipeline).to_list(length=1):
            return chars[0]
        return None
    except Exception:
        return None


async def add_char(user_id: int, username: str, first_name: str, char: dict) -> bool:
    try:
        if await user_collection.find_one({'id': user_id}):
            await user_collection.update_one(
                {'id': user_id},
                {'$push': {'characters': char}, '$set': {'username': username, 'first_name': first_name}}
            )
        else:
            await user_collection.insert_one({
                'id': user_id,
                'username': username,
                'first_name': first_name,
                'characters': [char],
                'balance': 0
            })
        return True
    except Exception:
        return False


def format_caption(user_id: int, first_name: str, char: dict | None, is_win: bool, dice_val: int | None = None) -> str:
    if is_win and char:
        event = f"\nᴇᴠᴇɴᴛ: <b>{char['event']['name']}</b>" if char.get('event', {}).get('name') else ""
        origin = f"\nᴏʀɪɢɪɴ: <b>{char['origin']}</b>" if char.get('origin') else ""
        abilities = f"\nᴀʙɪʟɪᴛɪᴇs: <b>{char['abilities']}</b>" if char.get('abilities') else ""
        description = f"\nᴅᴇsᴄʀɪᴘᴛɪᴏɴ: <b>{char['description']}</b>" if char.get('description') else ""
        
        return (
            f"{'ᴅɪᴄᴇ ʀᴇsᴜʟᴛ: ' + str(dice_val) if dice_val else ''}\n"
            f"ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs <a href='tg://user?id={user_id}'>{first_name}</a>\n"
            f"{char['name']} {random.choice(SUCCESS_MSGS)}\n"
            f"ɴᴀᴍᴇ: <b>{char['name']}</b>\n"
            f"ʀᴀʀɪᴛʏ: <b>{char['rarity']}</b>\n"
            f"ᴀɴɪᴍᴇ: <b>{char['anime']}</b>\n"
            f"ɪᴅ: <code>{char['id']}</code>{event}{origin}{abilities}{description}\n"
            f"ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ʜᴀʀᴇᴍ ✨"
        )
    
    return (
        f"ᴅɪᴄᴇ ʀᴇsᴜʟᴛ: <b>{dice_val}</b>\n"
        f"{random.choice(FAIL_MSGS)}\n"
        f"ᴘʟᴀʏᴇʀ: <a href='tg://user?id={user_id}'>{first_name}</a>\n"
        f"ɴᴇᴇᴅᴇᴅ: <b>1</b> ᴏʀ <b>6</b>\n"
        f"ᴛʀʏ ᴀɢᴀɪɴ ɪɴ 30 ᴍɪɴᴜᴛᴇs ⏰"
    )


async def dice_marry(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if remaining := check_cooldown(user_id, 'dice', CONFIG.dice_cooldown):
        await update.message.reply_text(
            f"ᴡᴀɪᴛ <b>{remaining // 60}ᴍ {remaining % 60}s</b> ʙᴇғᴏʀᴇ ʀᴏʟʟɪɴɢ ᴀɢᴀɪɴ ⏳",
            parse_mode='HTML'
        )
        return
    
    if not await user_collection.find_one({'id': user_id}):
        await update.message.reply_text("ʏᴏᴜ ɴᴇᴇᴅ ᴛᴏ ɢʀᴀʙ ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ғɪʀsᴛ\nᴜsᴇ /grab", parse_mode='HTML')
        return
    
    try:
        dice_msg = await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='🎲')
        dice_val = dice_msg.dice.value
        await asyncio.sleep(3)
        
        if dice_val in [1, 6]:
            if not (char := await get_unique_char(user_id)):
                await update.message.reply_text("ɴᴏ ᴀᴠᴀɪʟᴀʙʟᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs\nᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ 💔")
                return
            
            if not await add_char(user_id, update.effective_user.username, update.effective_user.first_name, char):
                await update.message.reply_text("ᴇʀʀᴏʀ ᴀᴅᴅɪɴɢ ᴄʜᴀʀᴀᴄᴛᴇʀ ⚠️")
                return
            
            await update.message.reply_photo(
                photo=char['img_url'],
                caption=format_caption(user_id, update.effective_user.first_name, char, True, dice_val),
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                format_caption(user_id, update.effective_user.first_name, None, False, dice_val),
                parse_mode='HTML'
            )
    
    except Exception as e:
        await update.message.reply_text(f"ᴇʀʀᴏʀ: <code>{str(e)}</code>", parse_mode='HTML')


async def propose(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not await is_in_support(context, user_id):
        await update.message.reply_text(
            "❌ ʏᴏᴜ ᴍᴜsᴛ ᴊᴏɪɴ ᴏᴜʀ sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ ᴛᴏ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ!\n\n"
            "ᴊᴏɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ 💕",
            reply_markup=support_button()
        )
        return
    
    if not (user_data := await user_collection.find_one({'id': user_id})):
        await update.message.reply_text("ᴘʟᴇᴀsᴇ sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ ғɪʀsᴛ\nᴄʟɪᴄᴋ ➡️ /start")
        return
    
    if remaining := check_cooldown(user_id, 'propose', CONFIG.propose_cooldown):
        await update.message.reply_text(f"ᴄᴏᴏʟᴅᴏᴡɴ: ᴡᴀɪᴛ <b>{remaining // 60}ᴍ {remaining % 60}s</b> ⏳", parse_mode='HTML')
        return
    
    balance = user_data.get('balance', 0)
    if balance < CONFIG.proposal_cost:
        await update.message.reply_text(
            f"💰 ʏᴏᴜ ɴᴇᴇᴅ <b>{CONFIG.proposal_cost}</b> ɢᴏʟᴅ ᴄᴏɪɴs ᴛᴏ ᴘʀᴏᴘᴏsᴇ\n"
            f"ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ: <b>{balance}</b>",
            parse_mode='HTML'
        )
        return
    
    await user_collection.update_one({'id': user_id}, {'$inc': {'balance': -CONFIG.proposal_cost}})
    
    try:
        await update.message.reply_photo(
            photo='https://te.legra.ph/file/4d0f83726fe8cd637d3ff.jpg',
            caption='ғɪɴᴀʟʟʏ ᴛʜᴇ ᴛɪᴍᴇ ᴛᴏ ᴘʀᴏᴘᴏsᴇ 💍'
        )
        await asyncio.sleep(2)
        await update.message.reply_text("ᴘʀᴏᴘᴏsɪɴɢ... 💕")
        await asyncio.sleep(2)
        
        if random.random() > 0.4:
            await update.message.reply_photo(
                photo='https://graph.org/file/48c147582d2742105e6ec.jpg',
                caption='sʜᴇ ʀᴇᴊᴇᴄᴛᴇᴅ ʏᴏᴜʀ ᴘʀᴏᴘᴏsᴀʟ ᴀɴᴅ ʀᴀɴ ᴀᴡᴀʏ 💔'
            )
        else:
            if not (char := await get_unique_char(user_id, CONFIG.rare_rarities)):
                await user_collection.update_one({'id': user_id}, {'$inc': {'balance': CONFIG.proposal_cost}})
                await update.message.reply_text("ɴᴏ ᴀᴠᴀɪʟᴀʙʟᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs\nᴄᴏɪɴs ʀᴇғᴜɴᴅᴇᴅ 💔")
                return
            
            if not await add_char(user_id, update.effective_user.username, update.effective_user.first_name, char):
                await user_collection.update_one({'id': user_id}, {'$inc': {'balance': CONFIG.proposal_cost}})
                await update.message.reply_text("ᴇʀʀᴏʀ ᴀᴅᴅɪɴɢ ᴄʜᴀʀᴀᴄᴛᴇʀ\nᴄᴏɪɴs ʀᴇғᴜɴᴅᴇᴅ ⚠️")
                return
            
            await update.message.reply_photo(
                photo=char['img_url'],
                caption=format_caption(user_id, update.effective_user.first_name, char, True),
                parse_mode='HTML'
            )
    
    except Exception as e:
        await user_collection.update_one({'id': user_id}, {'$inc': {'balance': CONFIG.proposal_cost}})
        await update.message.reply_text(f"ᴇʀʀᴏʀ: <code>{str(e)}</code>\nᴄᴏɪɴs ʀᴇғᴜɴᴅᴇᴅ", parse_mode='HTML')


application.add_handler(CommandHandler(['dice', 'marry'], dice_marry, block=False))
application.add_handler(CommandHandler('propose', propose, block=False))