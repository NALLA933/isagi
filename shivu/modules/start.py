import random
import time
from html import escape
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, LinkPreviewOptions
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from telegram.error import TelegramError, Forbidden, BadRequest
from shivu import application, SUPPORT_CHAT, BOT_USERNAME, LOGGER, user_collection, collection
from shivu.modules.chatlog import track_bot_start
from shivu.modules.database.sudo import fetch_sudo_users
import asyncio

# ==================== CONFIGURATION ====================
VIDEOS = [
    "https://files.catbox.moe/k3dhbe.mp4",
    "https://files.catbox.moe/iitev2.mp4",
    "https://files.catbox.moe/hs0e56.mp4"
]

REFERRER_REWARD = 1000
NEW_USER_BONUS = 500
REFERRAL_COOLDOWN = 5  # seconds between referral processing
MAX_REFERRALS_PER_HOUR = 10  # Anti-spam limit

OWNERS = [{"name": "Thorfinn", "username": "ll_Thorfinn_ll"}]
SUDO_USERS = [{"name": "Shadwoo", "username": "I_shadwoo"}]

REFERRAL_MILESTONES = {
    5: {"gold": 5000, "characters": 1, "rarity": ["common", "rare"]},
    10: {"gold": 15000, "characters": 2, "rarity": ["rare", "legendary"]},
    25: {"gold": 40000, "characters": 3, "rarity": ["legendary", "special", "neon"]},
    50: {"gold": 100000, "characters": 5, "rarity": ["special", "neon", "manga", "celestial"]},
    100: {"gold": 250000, "characters": 10, "rarity": ["celestial", "premium", "mythic"]}
}

HAREM_MODE_MAPPING = {
    "common": "🟢 Common", "rare": "🟣 Rare", "legendary": "🟡 Legendary",
    "special": "💮 Special", "neon": "💫 Neon", "manga": "✨ Manga",
    "cosplay": "🎭 Cosplay", "celestial": "🎐 Celestial", "premium": "🔮 Premium",
    "erotic": "💋 Erotic", "summer": "🌤 Summer", "winter": "☃️ Winter",
    "monsoon": "☔️ Monsoon", "valentine": "💝 Valentine", "halloween": "🎃 Halloween",
    "christmas": "🎄 Christmas", "mythic": "🏵 Mythic", "events": "🎗 Events",
    "amv": "🎥 AMV", "tiny": "👼 Tiny", "default": None
}

# Cache for recent referrals (user_id: timestamp)
referral_cache = {}

# ==================== UTILITY FUNCTIONS ====================

def clean_referral_cache():
    """Clean old entries from referral cache"""
    current_time = time.time()
    expired = [uid for uid, timestamp in referral_cache.items() 
               if current_time - timestamp > 3600]  # 1 hour
    for uid in expired:
        del referral_cache[uid]


async def check_spam_protection(user_id: int, referring_user_id: int) -> tuple[bool, str]:
    """
    Check if referral is spam or fraud
    Returns: (is_valid, error_message)
    """
    current_time = time.time()
    
    # Clean old cache entries
    clean_referral_cache()
    
    # Check if referrer has too many recent referrals
    referrer_key = f"ref_{referring_user_id}"
    if referrer_key in referral_cache:
        time_diff = current_time - referral_cache[referrer_key]
        if time_diff < REFERRAL_COOLDOWN:
            return False, f"⏳ ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ {int(REFERRAL_COOLDOWN - time_diff)} sᴇᴄᴏɴᴅs"
    
    # Check hourly limit
    referring_user = await user_collection.find_one({"id": referring_user_id})
    if referring_user:
        last_hour_refs = referring_user.get('referrals_last_hour', [])
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_refs = [r for r in last_hour_refs if r > one_hour_ago]
        
        if len(recent_refs) >= MAX_REFERRALS_PER_HOUR:
            return False, "⚠️ ʀᴇғᴇʀʀᴀʟ ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ. ᴛʀʏ ʟᴀᴛᴇʀ"
    
    # Update cache
    referral_cache[referrer_key] = current_time
    
    return True, ""


async def get_user_stats(user_id: int) -> Dict:
    """Get comprehensive user statistics"""
    try:
        user_data = await user_collection.find_one({"id": user_id})
        if not user_data:
            return {}
        
        balance = user_data.get('balance', 0)
        
        # Count unique characters
        characters = user_data.get('characters', [])
        unique_char_ids = set()
        for char in characters:
            if isinstance(char, dict) and char.get('id'):
                unique_char_ids.add(char.get('id'))
        
        refs = user_data.get('referred_users', 0)
        
        # Calculate total earnings from referrals
        base_earned = refs * REFERRER_REWARD
        milestone_earned = sum(
            REFERRAL_MILESTONES[m]["gold"]
            for m in sorted(REFERRAL_MILESTONES.keys())
            if refs >= m
        )
        total_earned = base_earned + milestone_earned
        
        return {
            'balance': balance,
            'characters': len(unique_char_ids),
            'referrals': refs,
            'total_earned': total_earned,
            'user_data': user_data
        }
    except Exception as e:
        LOGGER.error(f"Error getting user stats: {e}")
        return {}


async def get_referral_leaderboard(limit: int = 10) -> List[Dict]:
    """Get top referrers"""
    try:
        pipeline = [
            {"$match": {"referred_users": {"$gt": 0}}},
            {"$sort": {"referred_users": -1}},
            {"$limit": limit},
            {"$project": {
                "id": 1,
                "first_name": 1,
                "username": 1,
                "referred_users": 1
            }}
        ]
        
        leaderboard = await user_collection.aggregate(pipeline).to_list(limit)
        return leaderboard
    except Exception as e:
        LOGGER.error(f"Error fetching leaderboard: {e}")
        return []


def create_progress_bar(current: int, target: int, length: int = 10) -> str:
    """Create a visual progress bar"""
    if target == 0:
        return "▱" * length
    
    filled = int((current / target) * length)
    filled = min(filled, length)
    
    bar = "▰" * filled + "▱" * (length - filled)
    percentage = int((current / target) * 100)
    
    return f"{bar} {percentage}%"


# ==================== CORE FUNCTIONS ====================

async def give_milestone_reward(user_id: int, milestone: int, context: CallbackContext) -> bool:
    """Give milestone rewards with enhanced error handling"""
    try:
        reward = REFERRAL_MILESTONES[milestone]
        gold = reward["gold"]
        char_count = reward["characters"]
        rarities = reward["rarity"]

        # Update gold
        result = await user_collection.update_one(
            {"id": user_id},
            {"$inc": {"balance": gold}}
        )
        
        if result.modified_count == 0:
            LOGGER.warning(f"Failed to update balance for user {user_id}")

        # Give characters
        characters = []
        for _ in range(char_count):
            rarity = random.choice(rarities)
            char_cursor = collection.aggregate([
                {"$match": {"rarity": rarity}},
                {"$sample": {"size": 1}}
            ])
            char_list = await char_cursor.to_list(1)

            if char_list:
                character = char_list[0]
                characters.append(character)

                await user_collection.update_one(
                    {"id": user_id},
                    {"$push": {"characters": character}}
                )

        # Create reward message
        char_list_text = "\n".join([
            f"{HAREM_MODE_MAPPING.get(c.get('rarity', 'common'), '🟢')} {c.get('name', 'Unknown')}"
            for c in characters
        ]) or "• ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs"

        msg = f"""<b>🎉 ᴍɪʟᴇsᴛᴏɴᴇ ʀᴇᴀᴄʜᴇᴅ!</b>

ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs ᴏɴ ʀᴇᴀᴄʜɪɴɢ <b>{milestone}</b> ʀᴇғᴇʀʀᴀʟs! 🎊

<b>🎁 ʀᴇᴡᴀʀᴅs</b>
💰 ɢᴏʟᴅ: <code>{gold:,}</code>
🎴 ᴄʜᴀʀᴀᴄᴛᴇʀs: <code>{char_count}</code>

<b>📦 ᴄʜᴀʀᴀᴄᴛᴇʀs ʀᴇᴄᴇɪᴠᴇᴅ</b>
{char_list_text}

<i>ᴋᴇᴇᴘ ɪɴᴠɪᴛɪɴɢ ғᴏʀ ᴍᴏʀᴇ ʀᴇᴡᴀʀᴅs!</i> 🌟"""

        # Send notification
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=msg,
                parse_mode='HTML',
                link_preview_options=LinkPreviewOptions(
                    url=random.choice(VIDEOS),
                    show_above_text=True,
                    prefer_large_media=True
                )
            )
            
            # Log milestone achievement
            await user_collection.update_one(
                {"id": user_id},
                {"$push": {
                    "milestone_history": {
                        "milestone": milestone,
                        "timestamp": datetime.utcnow(),
                        "gold": gold,
                        "characters": char_count
                    }
                }}
            )
            
            LOGGER.info(f"✓ Milestone {milestone} reward sent to user {user_id}")
            return True
            
        except Forbidden:
            LOGGER.warning(f"User {user_id} blocked the bot")
            return False
        except Exception as e:
            LOGGER.error(f"Could not send milestone notification to {user_id}: {e}")
            return False

    except Exception as e:
        LOGGER.error(f"Error giving milestone reward: {e}", exc_info=True)
        return False


async def process_referral(user_id: int, first_name: str, referring_user_id: int, context: CallbackContext) -> bool:
    """Process referral with spam protection and validation"""
    try:
        # Basic validation
        if not user_id or not referring_user_id or user_id == referring_user_id:
            LOGGER.warning(f"Invalid referral: user={user_id}, referrer={referring_user_id}")
            return False

        # Check spam protection
        is_valid, error_msg = await check_spam_protection(user_id, referring_user_id)
        if not is_valid:
            LOGGER.warning(f"Spam protection triggered: {error_msg}")
            return False

        # Check if referring user exists
        referring_user = await user_collection.find_one({"id": referring_user_id})
        if not referring_user:
            LOGGER.warning(f"Referring user {referring_user_id} not found")
            return False

        # Check if new user already referred
        new_user = await user_collection.find_one({"id": user_id})
        if new_user and new_user.get('referred_by'):
            LOGGER.info(f"User {user_id} already referred by {new_user.get('referred_by')}")
            return False

        # Update new user
        await user_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "referred_by": referring_user_id,
                    "referral_timestamp": datetime.utcnow()
                },
                "$inc": {"balance": NEW_USER_BONUS}
            }
        )

        old_count = referring_user.get('referred_users', 0)
        new_count = old_count + 1

        # Update referring user with hourly tracking
        await user_collection.update_one(
            {"id": referring_user_id},
            {
                "$inc": {
                    "balance": REFERRER_REWARD,
                    "referred_users": 1,
                    "pass_data.tasks.invites": 1,
                    "pass_data.total_invite_earnings": REFERRER_REWARD
                },
                "$push": {
                    "invited_user_ids": user_id,
                    "referrals_last_hour": datetime.utcnow()
                }
            }
        )

        LOGGER.info(f"✓ Referral processed: {user_id} -> {referring_user_id} (count: {new_count})")

        # Check for milestone
        milestone_reached = None
        for milestone in sorted(REFERRAL_MILESTONES.keys()):
            if old_count < milestone <= new_count:
                milestone_reached = milestone
                break

        if milestone_reached:
            LOGGER.info(f"🏆 Milestone {milestone_reached} reached for user {referring_user_id}")
            await give_milestone_reward(referring_user_id, milestone_reached, context)

        # Get next milestone info
        next_milestone = next(
            (m for m in sorted(REFERRAL_MILESTONES.keys()) if new_count < m),
            None
        )

        # Create notification message
        msg = f"""<b>✨ ʀᴇғᴇʀʀᴀʟ sᴜᴄᴄᴇss!</b>

<b>{escape(first_name)}</b> ᴊᴏɪɴᴇᴅ ᴠɪᴀ ʏᴏᴜʀ ʟɪɴᴋ! 🎉

<b>💰 ʀᴇᴡᴀʀᴅs</b>
• ɢᴏʟᴅ: <code>+{REFERRER_REWARD:,}</code>
• ɪɴᴠɪᴛᴇ ᴛᴀsᴋ: <code>+1</code>

<b>📊 ʏᴏᴜʀ sᴛᴀᴛs</b>
👥 ᴛᴏᴛᴀʟ ʀᴇғᴇʀʀᴀʟs: <b>{new_count}</b>"""

        if next_milestone:
            remaining = next_milestone - new_count
            reward = REFERRAL_MILESTONES[next_milestone]
            progress = create_progress_bar(new_count, next_milestone, 10)
            
            msg += f"""

<b>🎯 ɴᴇxᴛ ᴍɪʟᴇsᴛᴏɴᴇ</b>
{progress}
<code>{remaining}</code> ᴍᴏʀᴇ ғᴏʀ <b>{reward['gold']:,}</b> ɢᴏʟᴅ + <b>{reward['characters']}</b> ᴄʜᴀʀᴀᴄᴛᴇʀs"""

        # Send notification to referrer
        try:
            await context.bot.send_message(
                chat_id=referring_user_id,
                text=msg,
                parse_mode='HTML',
                link_preview_options=LinkPreviewOptions(
                    url=random.choice(VIDEOS),
                    show_above_text=True,
                    prefer_large_media=True
                )
            )
        except Forbidden:
            LOGGER.warning(f"Referrer {referring_user_id} blocked the bot")
        except Exception as e:
            LOGGER.error(f"Could not notify referrer {referring_user_id}: {e}")

        return True

    except Exception as e:
        LOGGER.error(f"Referral processing error: {e}", exc_info=True)
        return False


async def safe_track_bot_start(user_id: int, first_name: str, username: str, is_new_user: bool):
    """Safely track bot start with timeout"""
    try:
        from shivu.modules.chatlog import track_bot_start
        await asyncio.wait_for(
            track_bot_start(user_id, first_name, username, is_new_user),
            timeout=5.0
        )
    except asyncio.TimeoutError:
        LOGGER.warning(f"track_bot_start timed out for user {user_id}")
    except ImportError:
        pass
    except Exception as e:
        LOGGER.error(f"Error in safe_track_bot_start: {e}")


# ==================== COMMAND HANDLERS ====================

async def start(update: Update, context: CallbackContext):
    """Enhanced start command with better error handling"""
    try:
        if not update or not update.effective_user:
            LOGGER.error("No update or effective_user in start command")
            return

        user_id = update.effective_user.id
        first_name = update.effective_user.first_name or "User"
        username = update.effective_user.username or ""
        args = context.args

        LOGGER.info(f"📍 Start command: user={user_id} (@{username}) args={args}")

        # Parse referral code
        referring_user_id = None
        if args and len(args) > 0 and args[0].startswith('r_'):
            try:
                referring_user_id = int(args[0][2:])
                LOGGER.info(f"🔗 Referral detected: referrer={referring_user_id}")
            except (ValueError, IndexError) as e:
                LOGGER.error(f"Invalid referral code {args[0]}: {e}")
                referring_user_id = None

        # Get or create user
        user_data = await user_collection.find_one({"id": user_id})
        is_new_user = user_data is None

        if is_new_user:
            LOGGER.info(f"➕ Creating new user {user_id}")
            
            new_user = {
                "id": user_id,
                "first_name": first_name,
                "username": username,
                "balance": 500,
                "characters": [],
                "referred_users": 0,
                "referred_by": None,
                "invited_user_ids": [],
                "referrals_last_hour": [],
                "milestone_history": [],
                "created_at": datetime.utcnow(),
                "pass_data": {
                    "tier": "free",
                    "weekly_claims": 0,
                    "last_weekly_claim": None,
                    "streak_count": 0,
                    "last_streak_claim": None,
                    "tasks": {"invites": 0, "weekly_claims": 0, "grabs": 0},
                    "mythic_unlocked": False,
                    "premium_expires": None,
                    "elite_expires": None,
                    "pending_elite_payment": None,
                    "invited_users": [],
                    "total_invite_earnings": 0
                }
            }

            await user_collection.insert_one(new_user)
            user_data = new_user

            # Track bot start asynchronously
            context.application.create_task(
                safe_track_bot_start(user_id, first_name, username, True)
            )

            # Process referral if exists
            if referring_user_id:
                LOGGER.info(f"🎁 Processing referral: {user_id} <- {referring_user_id}")
                await process_referral(user_id, first_name, referring_user_id, context)

        else:
            LOGGER.info(f"👤 Existing user {user_id} started bot")
            
            # Update user info
            await user_collection.update_one(
                {"id": user_id},
                {
                    "$set": {
                        "first_name": first_name,
                        "username": username,
                        "last_seen": datetime.utcnow()
                    }
                }
            )

            context.application.create_task(
                safe_track_bot_start(user_id, first_name, username, False)
            )

        # Get user stats
        stats = await get_user_stats(user_id)
        balance = stats.get('balance', 0)
        chars = stats.get('characters', 0)
        refs = stats.get('referrals', 0)

        # Create welcome message
        welcome = "ᴡᴇʟᴄᴏᴍᴇ" if is_new_user else "ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ"
        bonus = f"\n\n<b>🎁 ʙᴏɴᴜs</b>\n💰 +{NEW_USER_BONUS} ɢᴏʟᴅ ʀᴇᴄᴇɪᴠᴇᴅ!" if (is_new_user and referring_user_id) else ""

        video_url = random.choice(VIDEOS)
        caption = f"""<b>✨ {welcome}!</b>

ɪ ᴀᴍ <b>ᴘɪᴄᴋ ᴄᴀᴛᴄʜᴇʀ</b> 🎴

ɪ sᴘᴀᴡɴ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs ɪɴ ɢʀᴏᴜᴘs ᴀɴᴅ ʟᴇᴛ ᴜsᴇʀs ᴄᴏʟʟᴇᴄᴛ ᴛʜᴇᴍ. ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ ᴀɴᴅ sᴛᴀʀᴛ ᴄᴏʟʟᴇᴄᴛɪɴɢ!

<b>📊 ʏᴏᴜʀ sᴛᴀᴛs</b>
💰 ɢᴏʟᴅ: <code>{balance:,}</code>
🎴 ᴄʜᴀʀᴀᴄᴛᴇʀs: <code>{chars}</code>
👥 ʀᴇғᴇʀʀᴀʟs: <code>{refs}</code>{bonus}"""

        keyboard = [
            [InlineKeyboardButton("➕ ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ", url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
            [
                InlineKeyboardButton("💬 sᴜᴘᴘᴏʀᴛ", url=f'https://t.me/{SUPPORT_CHAT}'),
                InlineKeyboardButton("📢 ᴜᴘᴅᴀᴛᴇs", url='https://t.me/PICK_X_UPDATE')
            ],
            [
                InlineKeyboardButton("❓ ʜᴇʟᴘ", callback_data='help'),
                InlineKeyboardButton("🎁 ɪɴᴠɪᴛᴇ", callback_data='referral')
            ],
            [
                InlineKeyboardButton("🏆 ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ", callback_data='leaderboard'),
                InlineKeyboardButton("👥 ᴄʀᴇᴅɪᴛs", callback_data='credits')
            ]
        ]

        await update.message.reply_text(
            text=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML',
            link_preview_options=LinkPreviewOptions(
                url=video_url,
                show_above_text=True,
                prefer_large_media=True
            )
        )

        LOGGER.info(f"✓ Start command completed for user {user_id}")

    except Exception as e:
        LOGGER.error(f"❌ Critical error in start command: {e}", exc_info=True)
        try:
            await update.message.reply_text(
                "⚠️ <b>ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ</b>\n\nᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ ᴏʀ ᴄᴏɴᴛᴀᴄᴛ sᴜᴘᴘᴏʀᴛ.",
                parse_mode='HTML'
            )
        except:
            pass


async def refer_command(update: Update, context: CallbackContext):
    """Enhanced refer command with analytics"""
    try:
        user_id = update.effective_user.id
        stats = await get_user_stats(user_id)
        
        if not stats:
            await update.message.reply_text(
                "⚠️ <b>sᴛᴀʀᴛ ʙᴏᴛ ғɪʀsᴛ</b>\n\nᴜsᴇ /start ᴛᴏ ʙᴇɢɪɴ",
                parse_mode='HTML'
            )
            return

        link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
        count = stats.get('referrals', 0)
        total_earned = stats.get('total_earned', 0)

        # Get next milestone
        next_milestone = next(
            (m for m in sorted(REFERRAL_MILESTONES.keys()) if count < m),
            None
        )
        
        # Create milestone list
        milestone_text = "\n".join([
            f"{'✅' if count >= m else '🔒'} <b>{m}</b> ʀᴇғs → <code>{r['gold']:,}</code> ɢᴏʟᴅ + <code>{r['characters']}</code> ᴄʜᴀʀs"
            for m, r in sorted(REFERRAL_MILESTONES.items())
        ])

        # Progress to next milestone
        progress_text = ""
        if next_milestone:
            remaining = next_milestone - count
            progress = create_progress_bar(count, next_milestone, 12)
            reward = REFERRAL_MILESTONES[next_milestone]
            
            progress_text = f"""
<b>🎯 ɴᴇxᴛ ᴍɪʟᴇsᴛᴏɴᴇ</b>
{progress}
<code>{remaining}</code> ᴍᴏʀᴇ ғᴏʀ <b>{reward['gold']:,}</b> ɢᴏʟᴅ + <b>{reward['characters']}</b> ᴄʜᴀʀs"""

        text = f"""<b>🎁 ɪɴᴠɪᴛᴇ & ᴇᴀʀɴ ʀᴇᴡᴀʀᴅs</b>

<b>📊 ʏᴏᴜʀ sᴛᴀᴛs</b>
👥 ɪɴᴠɪᴛᴇᴅ: <b>{count}</b> ᴜsᴇʀs
💰 ᴛᴏᴛᴀʟ ᴇᴀʀɴᴇᴅ: <code>{total_earned:,}</code> ɢᴏʟᴅ

<b>💎 ᴘᴇʀ ʀ