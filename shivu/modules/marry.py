import asyncio 
import time 
import random 
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup 
from telegram.ext import CommandHandler, CallbackContext 
from telegram.error import TelegramError 
from shivu import application, user_collection, collection 
 
# Configuration 
PROPOSAL_COST = 2000 
DICE_COOLDOWN = 1800  # 30 minutes 
PROPOSE_COOLDOWN = 300  # 5 minutes 
SUPPORT_GROUP_USERNAME = "THE_DRAGON_SUPPORT"  # Support group username 
SUPPORT_GROUP_LINK = "https://t.me/THE_DRAGON_SUPPORT" 
 
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
    try: 
        if user_id in cooldowns[cmd_type]: 
            elapsed = time.time() - cooldowns[cmd_type][user_id] 
            if elapsed < cooldown_time: 
                remaining = int(cooldown_time - elapsed) 
                return False, remaining 
        cooldowns[cmd_type][user_id] = time.time() 
        return True, 0 
    except Exception as e: 
        print(f"Cooldown check error: {e}") 
        return True, 0 
 
 
async def is_user_in_support_group(context: CallbackContext, user_id: int) -> bool: 
    """Check if user is member of support group""" 
    try: 
        chat = await context.bot.get_chat(f"@{SUPPORT_GROUP_USERNAME}") 
        member = await context.bot.get_chat_member(chat.id, user_id) 
        return member.status in ['member', 'administrator', 'creator'] 
    except TelegramError as e: 
        print(f"Error checking support group membership: {e}") 
        return False 
    except Exception as e: 
        print(f"Unexpected error checking membership: {e}") 
        return False 
 
 
def get_support_group_button(): 
    """Get inline keyboard button for support group""" 
    keyboard = [[InlineKeyboardButton("🔗 ᴊᴏɪɴ sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ", url=SUPPORT_GROUP_LINK)]] 
    return InlineKeyboardMarkup(keyboard) 
 
 
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
                'characters': [char], 
                'balance': 0 
            }) 
        return True 
    except Exception as e: 
        print(f"Error adding character: {e}") 
        return False 
 
 
def format_char_msg(user_id, first_name, char, is_win=True, dice_val=None): 
    """Format character message""" 
    if is_win and char: 
        event_txt = f"\nᴇᴠᴇɴᴛ: <b>{char['event']['name']}</b>" if char.get('event', {}).get('name') else "" 
        msg = random.choice(SUCCESS_MSGS) 
        
        # Get additional character details
        origin = f"\nᴏʀɪɢɪɴ: <b>{char['origin']}</b>" if char.get('origin') else ""
        abilities = f"\nᴀʙɪʟɪᴛɪᴇs: <b>{char['abilities']}</b>" if char.get('abilities') else ""
        description = f"\nᴅᴇsᴄʀɪᴘᴛɪᴏɴ: <b>{char['description']}</b>" if char.get('description') else ""
        
        caption = f"""{"ᴅɪᴄᴇ ʀᴇsᴜʟᴛ: " + str(dice_val) if dice_val else ""}
ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs <a href='tg://user?id={user_id}'>{first_name}</a>
{char['name']} {msg}
ɴᴀᴍᴇ: <b>{char['name']}</b>
ʀᴀʀɪᴛʏ: <b>{char['rarity']}</b>
ᴀɴɪᴍᴇ: <b>{char['anime']}</b>
ɪᴅ: <code>{char['id']}</code>{event_txt}{origin}{abilities}{description}
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
    """Dice marry command - works in any group""" 
    try: 
        user_id = update.effective_user.id 
        first_name = update.effective_user.first_name 
        username = update.effective_user.username 
 
        # Check cooldown 
        can_use, remaining = check_cooldown(user_id, 'dice', DICE_COOLDOWN) 
        if not can_use: 
            mins = remaining // 60 
            secs = remaining % 60 
            await update.message.reply_text( 
                f"ᴡᴀɪᴛ <b>{mins}ᴍ {secs}s</b> ʙᴇғᴏʀᴇ ʀᴏʟʟɪɴɢ ᴀɢᴀɪɴ ⏳",  
                parse_mode='HTML' 
            ) 
            return 
 
        # Check if user exists 
        user_data = await user_collection.find_one({'id': user_id}) 
        if not user_data: 
            await update.message.reply_text( 
                "ʏᴏᴜ ɴᴇᴇᴅ ᴛᴏ ɢʀᴀʙ ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ғɪʀsᴛ\nᴜsᴇ /grab",  
                parse_mode='HTML' 
            ) 
            return 
 
        # Roll dice 
        dice_msg = await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='🎲') 
        dice_val = dice_msg.dice.value 
        await asyncio.sleep(3) 
 
        # Check if won 
        if dice_val in [1, 6]: 
            chars = await get_unique_chars(user_id) 
            if not chars: 
                await update.message.reply_text( 
                    "ɴᴏ ᴀᴠᴀɪʟᴀʙʟᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs\nᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ 💔",  
                    parse_mode='HTML' 
                ) 
                return 
 
            char = chars[0] 
            if not await add_char_to_user(user_id, username, first_name, char): 
                await update.message.reply_text("ᴇʀʀᴏʀ ᴀᴅᴅɪɴɢ ᴄʜᴀʀᴀᴄᴛᴇʀ ⚠️", parse_mode='HTML') 
                return 
 
            caption = format_char_msg(user_id, first_name, char, True, dice_val) 
            await update.message.reply_photo(
                photo=char['img_url'],
                caption=caption,
                parse_mode='HTML'
            )
        else: 
            caption = format_char_msg(user_id, first_name, None, False, dice_val) 
            await update.message.reply_text(caption, parse_mode='HTML') 
 
    except Exception as e: 
        print(f"Error in dice_marry: {e}") 
        await update.message.reply_text( 
            "ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ. ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ ⚠️", 
            parse_mode='HTML' 
        ) 
 
 
async def propose(update: Update, context: CallbackContext): 
    """Propose command - requires support group membership""" 
    try: 
        user_id = update.effective_user.id 
        first_name = update.effective_user.first_name 
        username = update.effective_user.username 
 
        # Check if user is in support group 
        is_member = await is_user_in_support_group(context, user_id) 
        if not is_member: 
            await update.message.reply_text( 
                "❌ ʏᴏᴜ ᴍᴜsᴛ ᴊᴏɪɴ ᴏᴜʀ sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ ᴛᴏ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ!\n\n" 
                "ᴊᴏɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ 💕", 
                reply_markup=get_support_group_button(), 
                parse_mode='HTML' 
            ) 
            return 
 
        # Check if user exists 
        user_data = await user_collection.find_one({'id': user_id}) 
        if not user_data: 
            await update.message.reply_text( 
                "ᴘʟᴇᴀsᴇ sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ ғɪʀsᴛ\nᴄʟɪᴄᴋ ➡️ /start",  
                parse_mode='HTML' 
            ) 
            return 
 
        # Check cooldown 
        can_use, remaining = check_cooldown(user_id, 'propose', PROPOSE_COOLDOWN) 
        if not can_use: 
            mins = remaining // 60 
            secs = remaining % 60 
            await update.message.reply_text( 
                f"ᴄᴏᴏʟᴅᴏᴡɴ: ᴡᴀɪᴛ <b>{mins}ᴍ {secs}s</b> ⏳",  
                parse_mode='HTML' 
            ) 
            return 
 
        # Check balance 
        balance = user_data.get('balance', 0) 
        if balance < PROPOSAL_COST: 
            await update.message.reply_text( 
                f"💰 ʏᴏᴜ ɴᴇᴇᴅ <b>{PROPOSAL_COST}</b> ɢᴏʟᴅ ᴄᴏɪɴs ᴛᴏ ᴘʀᴏᴘᴏsᴇ\n" 
                f"ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ: <b>{balance}</b>",  
                parse_mode='HTML' 
            ) 
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
 
        # 40% success rate 
        if random.random() > 0.4: 
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
                # Refund if no characters available 
                await user_collection.update_one({'id': user_id}, {'$inc': {'balance': PROPOSAL_COST}}) 
                await update.message.reply_text( 
                    "ɴᴏ ᴀᴠᴀɪʟᴀʙʟᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs\nᴄᴏɪɴs ʀᴇғᴜɴᴅᴇᴅ 💔",  
                    parse_mode='HTML' 
                ) 
                return 
 
            char = chars[0] 
            if not await add_char_to_user(user_id, username, first_name, char): 
                # Refund on error 
                await user_collection.update_one({'id': user_id}, {'$inc': {'balance': PROPOSAL_COST}}) 
                await update.message.reply_text( 
                    "ᴇʀʀᴏʀ ᴀᴅᴅɪɴɢ ᴄʜᴀʀᴀᴄᴛᴇʀ\nᴄᴏɪɴs ʀᴇғᴜɴᴅᴇᴅ ⚠️",  
                    parse_mode='HTML' 
                ) 
                return 
 
            caption = format_char_msg(user_id, first_name, char, True) 
            await update.message.reply_photo(
                photo=char['img_url'],
                caption=caption,
                parse_mode='HTML'
            )
 
    except Exception as e: 
        print(f"Error in propose: {e}") 
        # Refund on error 
        try: 
            await user_collection.update_one({'id': user_id}, {'$inc': {'balance': PROPOSAL_COST}}) 
        except: 
            pass 
        await update.message.reply_text( 
            "ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ. ᴄᴏɪɴs ʀᴇғᴜɴᴅᴇᴅ ⚠️", 
            parse_mode='HTML' 
        ) 
 
 
# Register handlers 
application.add_handler(CommandHandler(['dice', 'marry'], dice_marry, block=False)) 
application.add_handler(CommandHandler(['propose'], propose, block=False))