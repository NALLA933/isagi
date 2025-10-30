import asyncio
import time
import random
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from shivu import application, user_collection, collection

# Configuration
PROPOSAL_COST = 2000
DICE_COOLDOWN = 1800  # 30 minutes
PROPOSE_COOLDOWN = 300  # 5 minutes
SUPPORT_GROUP_ID = -1001234567890  # Replace with your support group ID

# Cooldown storage
cooldowns = {'dice': {}, 'propose': {}}

# Messages
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


def check_cooldown(user_id, cmd_type, cooldown_time):
    """Check and update cooldown"""
    if user_id in cooldowns[cmd_type]:
        elapsed = time.time() - cooldowns[cmd_type][user_id]
        if elapsed < cooldown_time:
            remaining = int((cooldown_time - elapsed) / 60)
            return False, remaining
    cooldowns[cmd_type][user_id] = time.time()
    return True, 0


async def get_unique_chars(user_id, rarities=None, count=1):
    """Fetch unique characters not in user's collection"""
    try:
        rarities = rarities or ['🟢 Common', '🟣 Rare', '🟡 Legendary']
        user_data = await user_collection.find_one({'id': user_id})
        claimed_ids = [c.get('id') for c in user_data.get('characters', [])] if user_data else []
        
        pipeline = [
            {'$match': {'rarity': {'$in': rarities}, 'id': {'$nin': claimed_ids}}},
            {'$sample': {'size': count}}
        ]
        
        chars = await collection.aggregate(pipeline).to_list(length=None)
        return chars if chars else []
    except Exception as e:
        print(f"Error fetching characters: {e}")
        return []


async def add_char_to_user(user_id, username, first_name, char):
    """Add character to user's collection"""
    try:
        user_data = await user_collection.find_one({'id': user_id})
        if user_data:
            await user_collection.update_one(
                {'id': user_id},
                {'$push': {'characters': char}, '$set': {'username': username, 'first_name': first_name}}
            )
        else:
            await user_collection.insert_one({
                'id': user_id,
                'username': username,
                'first_name': first_name,
                'characters': [char]
            })
        return True
    except Exception as e:
        print(f"Error adding character: {e}")
        return False


def format_char_msg(user_id, first_name, char, is_win=True, dice_val=None):
    """Format character message with HTML preview"""
    event_txt = f"\nᴇᴠᴇɴᴛ: {char['event']['name']}" if char.get('event', {}).get('name') else ""
    
    if is_win:
        msg = random.choice(SUCCESS_MSGS)
        caption = f"""<a href='{char['img_url']}'>&#8205;</a>{"ᴅɪᴄᴇ ʀᴇsᴜʟᴛ: " + str(dice_val) if dice_val else ""}

ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs <a href='tg://user?id={user_id}'>{first_name}</a>

{char['name']} {msg}

ɴᴀᴍᴇ: <b>{char['name']}</b>
ʀᴀʀɪᴛʏ: <b>{char['rarity']}</b>
ᴀɴɪᴍᴇ: <b>{char['anime']}</b>
ɪᴅ: <code>{char['id']}</code>{event_txt}

ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ʜᴀʀᴇᴍ ✨"""
    else:
        msg = random.choice(FAIL_MSGS)
        caption = f"""ᴅɪᴄᴇ ʀᴇsᴜʟᴛ: <b>{dice_val}</b>

{msg}

ᴘʟᴀʏᴇʀ: <a href='tg://user?id={user_id}'>{first_name}</a>
ɴᴇᴇᴅᴇᴅ: <b>1</b> ᴏʀ <b>6</b>

ᴛʀʏ ᴀɢᴀɪɴ ɪɴ 30 ᴍɪɴᴜᴛᴇs ⏰"""
    
    return caption


async def dice_marry(update: Update, context: CallbackContext):
    """Dice marry command"""
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    username = update.effective_user.username

    # Check cooldown
    can_use, remaining = check_cooldown(user_id, 'dice', DICE_COOLDOWN)
    if not can_use:
        await update.message.reply_text(f"ᴡᴀɪᴛ <b>{remaining}ᴍ</b> ʙᴇғᴏʀᴇ ʀᴏʟʟɪɴɢ ᴀɢᴀɪɴ ⏳", parse_mode='HTML')
        return

    # Check if user exists
    user_data = await user_collection.find_one({'id': user_id})
    if not user_data:
        await update.message.reply_text("ʏᴏᴜ ɴᴇᴇᴅ ᴛᴏ ɢʀᴀʙ ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ғɪʀsᴛ\nᴜsᴇ /grab", parse_mode='HTML')
        return

    # Roll dice
    dice_msg = await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='🎲')
    dice_val = dice_msg.dice.value
    await asyncio.sleep(3)

    # Check if won
    if dice_val in [1, 6]:
        chars = await get_unique_chars(user_id)
        if not chars:
            await update.message.reply_text("ɴᴏ ᴀᴠᴀɪʟᴀʙʟᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs\nᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ 💔", parse_mode='HTML')
            return

        char = chars[0]
        if not await add_char_to_user(user_id, username, first_name, char):
            await update.message.reply_text("ᴇʀʀᴏʀ ᴀᴅᴅɪɴɢ ᴄʜᴀʀᴀᴄᴛᴇʀ ⚠️", parse_mode='HTML')
            return

        caption = format_char_msg(user_id, first_name, char, True, dice_val)
        await update.message.reply_text(caption, parse_mode='HTML')
    else:
        caption = format_char_msg(user_id, first_name, None, False, dice_val)
        await update.message.reply_text(caption, parse_mode='HTML')


async def propose(update: Update, context: CallbackContext):
    """Propose command"""
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    username = update.effective_user.username
    chat_id = update.effective_chat.id

    # Check if in support group
    if chat_id != SUPPORT_GROUP_ID:
        await update.message.reply_text("ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴄᴀɴ ᴏɴʟʏ ʙᴇ ᴜsᴇᴅ ɪɴ ᴛʜᴇ sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ 🚫", parse_mode='HTML')
        return

    # Check if user exists
    user_data = await user_collection.find_one({'id': user_id})
    if not user_data:
        await update.message.reply_text("ᴘʟᴇᴀsᴇ sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ ғɪʀsᴛ\nᴄʟɪᴄᴋ ➡️ /start", parse_mode='HTML')
        return

    # Check cooldown
    can_use, remaining = check_cooldown(user_id, 'propose', PROPOSE_COOLDOWN)
    if not can_use:
        mins, secs = remaining, 0
        await update.message.reply_text(f"ᴄᴏᴏʟᴅᴏᴡɴ: ᴡᴀɪᴛ <b>{mins}ᴍ {secs}s</b> ⏳", parse_mode='HTML')
        return

    # Check balance
    balance = user_data.get('balance', 0)
    if balance < PROPOSAL_COST:
        await update.message.reply_text(f"💰 ʏᴏᴜ ɴᴇᴇᴅ <b>{PROPOSAL_COST}</b> ɢᴏʟᴅ ᴄᴏɪɴs ᴛᴏ ᴘʀᴏᴘᴏsᴇ", parse_mode='HTML')
        return

    # Deduct cost
    await user_collection.update_one({'id': user_id}, {'$inc': {'balance': -PROPOSAL_COST}})

    # Propose sequence
    await update.message.reply_photo(
        photo='https://te.legra.ph/file/4d0f83726fe8cd637d3ff.jpg',
        caption='ғɪɴᴀʟʟʏ ᴛʜᴇ ᴛɪᴍᴇ ᴛᴏ ᴘʀᴏᴘᴏsᴇ 💍'
    )
    await asyncio.sleep(2)
    await update.message.reply_text("ᴘʀᴏᴘᴏsɪɴɢ... 💕")
    await asyncio.sleep(2)

    # 60% success rate
    if random.random() > 0.6:
        await update.message.reply_photo(
            photo='https://graph.org/file/48c147582d2742105e6ec.jpg',
            caption='sʜᴇ ʀᴇᴊᴇᴄᴛᴇᴅ ʏᴏᴜʀ ᴘʀᴏᴘᴏsᴀʟ ᴀɴᴅ ʀᴀɴ ᴀᴡᴀʏ 💔'
        )
    else:
        chars = await get_unique_chars(
            user_id,
            rarities=['💮 Special Edition', '💫 Neon', '✨ Manga', '🎐 Celestial']
        )
        if not chars:
            await update.message.reply_text("ɴᴏ ᴀᴠᴀɪʟᴀʙʟᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs\nᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ 💔", parse_mode='HTML')
            return

        char = chars[0]
        if not await add_char_to_user(user_id, username, first_name, char):
            await update.message.reply_text("ᴇʀʀᴏʀ ᴀᴅᴅɪɴɢ ᴄʜᴀʀᴀᴄᴛᴇʀ ⚠️", parse_mode='HTML')
            return

        caption = format_char_msg(user_id, first_name, char, True)
        await update.message.reply_text(caption, parse_mode='HTML')


# Register handlers
application.add_handler(CommandHandler(['dice', 'marry'], dice_marry, block=False))
application.add_handler(CommandHandler(['propose'], propose, block=False))