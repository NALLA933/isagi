from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, Application
import os
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database collections (using your provided collections)
db = client['Character_catcher']
user_collection = db["user_collection_lmaoooo"]
collection = db['anime_characters_lol']
group_user_totals_collection = db['group_user_totalsssssss']
registered_users = db['registered_users']
BANNED_USERS = db['Banned_Users']

SUPPORT_CHAT = "PICK_X_SUPPORT"

async def get_global_rank(user_id: int) -> int:
    try:
        pipeline = [
            {"$project": {
                "id": 1,
                "characters_count": {"$cond": {
                    "if": {"$isArray": "$characters"}, 
                    "then": {"$size": "$characters"}, 
                    "else": 0
                }}
            }},
            {"$sort": {"characters_count": -1}}
        ]
        cursor = user_collection.aggregate(pipeline)
        leaderboard_data = await cursor.to_list(length=None)
        
        for rank, user in enumerate(leaderboard_data, 1):
            if user.get('id') == user_id:
                return rank
        return 0
    except Exception as e:
        logger.error(f"Error getting global rank: {e}")
        return 0

async def get_user_stats(user_id: int):
    try:
        user_data = await user_collection.find_one({'id': user_id})
        if not user_data:
            return {
                'balance': 0,
                'tokens': 0,
                'characters_count': 0,
                'has_pass': False,
                'profile_media': None,
                'custom_info': '',
                'registered_at': datetime.now()
            }
        
        return {
            'balance': user_data.get('balance', 0),
            'tokens': user_data.get('tokens', 0),
            'characters_count': len(user_data.get('characters', [])),
            'has_pass': bool(user_data.get('pass')),
            'profile_media': user_data.get('profile_media'),
            'custom_info': user_data.get('custom_info', ''),
            'registered_at': user_data.get('registered_at', datetime.now())
        }
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return None

async def get_user_info(user_obj, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not user_obj:
            return "❌ User not found", None
        
        user_id = user_obj.id
        username = f"@{user_obj.username}" if user_obj.username else "No Username"
        first_name = user_obj.first_name or "Unknown"
        
        user_stats = await get_user_stats(user_id)
        if not user_stats:
            return "❌ Error fetching user data", None
        
        global_rank = await get_global_rank(user_id)
        total_characters = await collection.count_documents({})
        
        # Format numbers with commas
        balance_formatted = f"{user_stats['balance']:,}"
        tokens_formatted = f"{user_stats['tokens']:,}"
        characters_count = user_stats['characters_count']
        
        # Calculate wealth rank
        wealth_rank = await user_collection.count_documents({
            'balance': {'$gt': user_stats['balance']}
        }) + 1
        
        # Get registration date
        reg_date = user_stats['registered_at'].strftime("%Y-%m-%d") if isinstance(user_stats['registered_at'], datetime) else "Unknown"
        
        info_text = f"""
<blockquote expandable>
🏆 <b>HUNTER PROFILE CARD</b> 🏆
┌────────────────────
├ <b>Name:</b> <code>{first_name}</code>
├ <b>ID:</b> <code>{user_id}</code>
├ <b>Username:</b> {username}
├ <b>Registered:</b> <code>{reg_date}</code>
└────────────────────

📊 <b>STATISTICS</b>
┌────────────────────
├ <b>Slaves Collected:</b> <code>{characters_count}/{total_characters}</code>
├ <b>Global Rank:</b> <code>#{global_rank}</code>
└────────────────────

💎 <b>ECONOMY</b>
┌────────────────────
├ <b>Wealth:</b> ₩<code>{balance_formatted}</code>
├ <b>Wealth Rank:</b> <code>#{wealth_rank}</code>
├ <b>Tokens:</b> <code>{tokens_formatted}</code>
├ <b>Hunter Pass:</b> {'✅' if user_stats['has_pass'] else '❌'}
└────────────────────

{user_stats['custom_info'] if user_stats['custom_info'] else '💬 <i>No custom bio set</i>'}
</blockquote>

<b>🔰 Use /setprofile to customize your profile!</b>
"""
        
        return info_text, user_stats['profile_media']
        
    except Exception as e:
        logger.error(f"Error in get_user_info: {e}")
        return f"❌ Error generating profile: {str(e)}", None

async def sinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        message = update.message
        
        # Determine which user to show info for
        target_user = user  # Default to command user
        
        if context.args:
            # Check if argument is user ID or username
            arg = context.args[0]
            if arg.isdigit():
                target_user_id = int(arg)
                try:
                    target_user = await context.bot.get_chat(target_user_id)
                except:
                    await message.reply_text("❌ User not found!")
                    return
            elif arg.startswith('@'):
                username = arg[1:]
                # This is simplified - you might need a different approach for username lookup
                await message.reply_text("🔍 Username lookup requires advanced implementation")
                return
        elif message.reply_to_message:
            target_user = message.reply_to_message.from_user
        
        loading_msg = await message.reply_text("📇 Generating Hunter License...")
        
        info_text, profile_media = await get_user_info(target_user, context)
        
        keyboard = [
            [InlineKeyboardButton("🏪 Support", url=f"https://t.me/{SUPPORT_CHAT}")],
            [InlineKeyboardButton("✨ Set Profile", callback_data="set_profile")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Check if user exists in database
        user_exists = await user_collection.find_one({'id': target_user.id})
        
        if not user_exists:
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Start Bot", url=f"https://t.me/{context.bot.username}?start=True")]
            ])
            await loading_msg.edit_text(info_text, reply_markup=reply_markup, parse_mode='HTML')
            return
        
        # Handle profile media
        if profile_media and profile_media.get('type') == 'photo':
            await loading_msg.delete()
            await message.reply_photo(
                photo=profile_media['file_id'],
                caption=info_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        elif profile_media and profile_media.get('type') in ['video', 'gif']:
            await loading_msg.delete()
            await message.reply_video(
                video=profile_media['file_id'],
                caption=info_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            await loading_msg.edit_text(info_text, reply_markup=reply_markup, parse_mode='HTML')
            
    except Exception as e:
        logger.error(f"Error in sinfo_command: {e}")
        await update.message.reply_text("❌ An error occurred while fetching profile!")

async def set_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        message = update.message
        
        if not message.reply_to_message:
            help_text = """
📝 <b>Profile Customization Guide</b>

<b>To set profile media:</b>
1. Reply to a photo/video/GIF with /setprofile

<b>To set custom bio:</b>
/setbio Your custom bio text here

<b>Available commands:</b>
• /setprofile - Set profile media (reply to media)
• /setbio - Set custom biography
• /sinfo - View your profile
• /sinfo @username - View other's profile
• /sinfo [user_id] - View profile by ID
"""
            await message.reply_text(help_text, parse_mode='HTML')
            return
        
        replied_message = message.reply_to_message
        media_type = None
        file_id = None
        
        if replied_message.photo:
            media_type = 'photo'
            file_id = replied_message.photo[-1].file_id
        elif replied_message.video:
            media_type = 'video'
            file_id = replied_message.video.file_id
        elif replied_message.animation:
            media_type = 'gif'
            file_id = replied_message.animation.file_id
        else:
            await message.reply_text("❌ Please reply to a photo, video, or GIF!")
            return
        
        # Update user profile media in database
        await user_collection.update_one(
            {'id': user.id},
            {'$set': {
                'profile_media': {
                    'type': media_type,
                    'file_id': file_id
                }
            }},
            upsert=True
        )
        
        await message.reply_text("✅ Profile media updated successfully!")
        
    except Exception as e:
        logger.error(f"Error in set_profile_command: {e}")
        await update.message.reply_text("❌ Failed to set profile media!")

async def set_bio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        
        if not context.args:
            await update.message.reply_text("❌ Please provide your bio text!\nExample: /setbio I'm a professional hunter! 🎯")
            return
        
        bio_text = ' '.join(context.args)
        
        # Limit bio length
        if len(bio_text) > 200:
            await update.message.reply_text("❌ Bio too long! Maximum 200 characters.")
            return
        
        # Update user custom info in database
        await user_collection.update_one(
            {'id': user.id},
            {'$set': {'custom_info': bio_text}},
            upsert=True
        )
        
        await update.message.reply_text("✅ Bio updated successfully!")
        
    except Exception as e:
        logger.error(f"Error in set_bio_command: {e}")
        await update.message.reply_text("❌ Failed to set bio!")

def setup_handlers(application: Application):
    application.add_handler(CommandHandler("sinfo", sinfo_command))
    application.add_handler(CommandHandler("setprofile", set_profile_command))
    application.add_handler(CommandHandler("setbio", set_bio_command))