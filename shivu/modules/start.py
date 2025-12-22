import random
import time
from html import escape
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, LinkPreviewOptions
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from shivu import application, SUPPORT_CHAT, BOT_USERNAME, LOGGER, user_collection, collection
from shivu.modules.chatlog import track_bot_start
from shivu.modules.database.sudo import fetch_sudo_users
import asyncio

VIDEOS = [
    "https://files.catbox.moe/k3dhbe.mp4",
    "https://files.catbox.moe/iitev2.mp4",
    "https://files.catbox.moe/hs0e56.mp4"
]

REFERRER_REWARD = 1000
NEW_USER_BONUS = 500
LEADERBOARD_SIZE = 10
CACHE_DURATION = 300  # 5 minutes

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

# Anti-spam & Rate limiting
user_last_action = {}
RATE_LIMIT_SECONDS = 3

# Leaderboard cache
leaderboard_cache = {"data": None, "timestamp": 0}

# Fraud detection
suspicious_users = set()
MAX_REFERRALS_PER_HOUR = 10


class RateLimiter:
    """Rate limiting for preventing spam"""
    
    @staticmethod
    def check_rate_limit(user_id: int) -> bool:
        current_time = time.time()
        
        if user_id in user_last_action:
            time_diff = current_time - user_last_action[user_id]
            if time_diff < RATE_LIMIT_SECONDS:
                return False
        
        user_last_action[user_id] = current_time
        return True
    
    @staticmethod
    def get_cooldown_time(user_id: int) -> int:
        if user_id not in user_last_action:
            return 0
        
        elapsed = time.time() - user_last_action[user_id]
        remaining = max(0, RATE_LIMIT_SECONDS - elapsed)
        return int(remaining)


class FraudDetector:
    """Detect suspicious referral patterns"""
    
    @staticmethod
    async def check_suspicious_activity(user_id: int, referring_user_id: int) -> Dict[str, any]:
        try:
            # Check if referrer is making too many referrals quickly
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            
            # Get referring user's recent referrals
            referring_user = await user_collection.find_one({"id": referring_user_id})
            if not referring_user:
                return {"is_suspicious": False}
            
            invited_ids = referring_user.get('invited_user_ids', [])
            
            # Check if too many referrals in short time
            recent_count = 0
            if len(invited_ids) > 0:
                # Simple check: if more than MAX_REFERRALS_PER_HOUR in last entries
                recent_count = len(invited_ids[-MAX_REFERRALS_PER_HOUR:])
            
            is_suspicious = recent_count >= MAX_REFERRALS_PER_HOUR
            
            if is_suspicious:
                suspicious_users.add(referring_user_id)
                LOGGER.warning(f"Suspicious activity detected: User {referring_user_id} has {recent_count} recent referrals")
            
            return {
                "is_suspicious": is_suspicious,
                "recent_referrals": recent_count,
                "reason": "Too many referrals in short time" if is_suspicious else None
            }
            
        except Exception as e:
            LOGGER.error(f"Error in fraud detection: {e}")
            return {"is_suspicious": False}


async def get_leaderboard(force_refresh: bool = False) -> List[Dict]:
    """Get referral leaderboard with caching"""
    try:
        current_time = time.time()
        
        # Use cache if available and not expired
        if not force_refresh and leaderboard_cache["data"] and (current_time - leaderboard_cache["timestamp"]) < CACHE_DURATION:
            return leaderboard_cache["data"]
        
        # Fetch top referrers from database
        pipeline = [
            {"$match": {"referred_users": {"$gt": 0}}},
            {"$sort": {"referred_users": -1}},
            {"$limit": LEADERBOARD_SIZE},
            {"$project": {
                "id": 1,
                "first_name": 1,
                "username": 1,
                "referred_users": 1,
                "balance": 1
            }}
        ]
        
        cursor = user_collection.aggregate(pipeline)
        leaderboard = await cursor.to_list(LEADERBOARD_SIZE)
        
        # Update cache
        leaderboard_cache["data"] = leaderboard
        leaderboard_cache["timestamp"] = current_time
        
        return leaderboard
        
    except Exception as e:
        LOGGER.error(f"Error fetching leaderboard: {e}")
        return []


async def get_user_rank(user_id: int) -> Optional[int]:
    """Get user's rank in referral leaderboard"""
    try:
        # Count users with more referrals
        user_data = await user_collection.find_one({"id": user_id})
        if not user_data:
            return None
        
        user_referrals = user_data.get('referred_users', 0)
        
        higher_users = await user_collection.count_documents({
            "referred_users": {"$gt": user_referrals}
        })
        
        return higher_users + 1
        
    except Exception as e:
        LOGGER.error(f"Error getting user rank: {e}")
        return None


def create_progress_bar(current: int, target: int, length: int = 10) -> str:
    """Create a visual progress bar"""
    if target == 0:
        return "░" * length
    
    percentage = min(current / target, 1.0)
    filled = int(percentage * length)
    empty = length - filled
    
    bar = "█" * filled + "░" * empty
    return f"{bar} {int(percentage * 100)}%"


async def give_milestone_reward(user_id: int, milestone: int, context: CallbackContext) -> bool:
    """Give milestone rewards with better error handling"""
    try:
        reward = REFERRAL_MILESTONES[milestone]
        gold = reward["gold"]
        char_count = reward["characters"]
        rarities = reward["rarity"]

        # Update gold balance
        result = await user_collection.update_one(
            {"id": user_id},
            {"$inc": {"balance": gold}}
        )
        
        if result.modified_count == 0:
            LOGGER.warning(f"Failed to update balance for user {user_id}")
            return False

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

        char_list_text = "\n".join([
            f"{HAREM_MODE_MAPPING.get(c.get('rarity', 'common'), '🟢')} {c.get('name', 'Unknown')}"
            for c in characters
        ]) if characters else "ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴀᴠᴀɪʟᴀʙʟᴇ"

        msg = f"""<b>🎉 ᴍɪʟᴇsᴛᴏɴᴇ ᴀᴄʜɪᴇᴠᴇᴅ</b>

ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs ᴏɴ ʀᴇᴀᴄʜɪɴɢ <b>{milestone}</b> ʀᴇғᴇʀʀᴀʟs 🎊

<b>🎁 ʀᴇᴡᴀʀᴅs</b>
💰 ɢᴏʟᴅ: <code>{gold:,}</code>
🎴 ᴄʜᴀʀᴀᴄᴛᴇʀs: <code>{char_count}</code>

<b>✨ ᴄʜᴀʀᴀᴄᴛᴇʀs ʀᴇᴄᴇɪᴠᴇᴅ</b>
{char_list_text}

ᴋᴇᴇᴘ ɪɴᴠɪᴛɪɴɢ ғᴏʀ ᴍᴏʀᴇ ʀᴇᴡᴀʀᴅs 🚀"""

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
        except Exception as e:
            LOGGER.error(f"Could not send milestone notification to {user_id}: {e}")

        return True

    except Exception as e:
        LOGGER.error(f"Error giving milestone reward: {e}", exc_info=True)
        return False


async def process_referral(user_id: int, first_name: str, referring_user_id: int, context: CallbackContext) -> Dict[str, any]:
    """Process referral with fraud detection"""
    try:
        if not user_id or not referring_user_id or user_id == referring_user_id:
            LOGGER.warning(f"Invalid referral: user={user_id}, referrer={referring_user_id}")
            return {"success": False, "reason": "Invalid referral data"}

        # Check for fraud
        fraud_check = await FraudDetector.check_suspicious_activity(user_id, referring_user_id)
        
        if fraud_check["is_suspicious"]:
            LOGGER.warning(f"Suspicious referral blocked: {user_id} -> {referring_user_id}")
            return {
                "success": False,
                "reason": "Suspicious activity detected",
                "is_suspicious": True
            }

        referring_user = await user_collection.find_one({"id": referring_user_id})
        if not referring_user:
            LOGGER.warning(f"Referring user {referring_user_id} not found")
            return {"success": False, "reason": "Referrer not found"}

        new_user = await user_collection.find_one({"id": user_id})
        if new_user and new_user.get('referred_by'):
            LOGGER.info(f"User {user_id} already referred by {new_user.get('referred_by')}")
            return {"success": False, "reason": "Already referred"}

        # Process referral
        await user_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "referred_by": referring_user_id,
                    "referral_date": datetime.utcnow()
                },
                "$inc": {"balance": NEW_USER_BONUS}
            }
        )

        old_count = referring_user.get('referred_users', 0)
        new_count = old_count + 1

        await user_collection.update_one(
            {"id": referring_user_id},
            {
                "$inc": {
                    "balance": REFERRER_REWARD,
                    "referred_users": 1,
                    "pass_data.tasks.invites": 1,
                    "pass_data.total_invite_earnings": REFERRER_REWARD
                },
                "$push": {"invited_user_ids": user_id}
            }
        )

        LOGGER.info(f"Referral processed: {user_id} -> {referring_user_id} (count: {new_count})")

        # Check for milestones
        milestone_reached = None
        for milestone in sorted(REFERRAL_MILESTONES.keys()):
            if old_count < milestone <= new_count:
                milestone_reached = milestone
                break

        if milestone_reached:
            LOGGER.info(f"Milestone {milestone_reached} reached for user {referring_user_id}")
            await give_milestone_reward(referring_user_id, milestone_reached, context)

        # Calculate next milestone progress
        next_milestone = next(
            (m for m in sorted(REFERRAL_MILESTONES.keys()) if new_count < m),
            None
        )
        
        progress_bar = ""
        if next_milestone:
            progress_bar = create_progress_bar(new_count, next_milestone)

        msg = f"""<b>✨ ʀᴇғᴇʀʀᴀʟ sᴜᴄᴄᴇss</b>

<b>{escape(first_name)}</b> ᴊᴏɪɴᴇᴅ ᴠɪᴀ ʏᴏᴜʀ ʟɪɴᴋ 🎉

<b>💰 ʀᴇᴡᴀʀᴅs</b>
• ɢᴏʟᴅ: <code>{REFERRER_REWARD:,}</code>
• ɪɴᴠɪᴛᴇ ᴛᴀsᴋ: +1
• ᴛᴏᴛᴀʟ ʀᴇғᴇʀʀᴀʟs: <b>{new_count}</b>"""

        if next_milestone:
            remaining = next_milestone - new_count
            reward = REFERRAL_MILESTONES[next_milestone]
            msg += f"\n\n<b>🎯 ɴᴇxᴛ ᴍɪʟᴇsᴛᴏɴᴇ</b>"
            msg += f"\n{progress_bar}"
            msg += f"\n{remaining} ᴍᴏʀᴇ ғᴏʀ {reward['gold']:,} ɢᴏʟᴅ + {reward['characters']} ᴄʜᴀʀs"

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
        except Exception as e:
            LOGGER.error(f"Could not notify referrer {referring_user_id}: {e}")

        return {
            "success": True,
            "new_count": new_count,
            "milestone_reached": milestone_reached
        }

    except Exception as e:
        LOGGER.error(f"Referral processing error: {e}", exc_info=True)
        return {"success": False, "reason": str(e)}


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
        LOGGER.warning("chatlog module not available, skipping bot start tracking")
    except Exception as e:
        LOGGER.error(f"Error in safe_track_bot_start: {e}")


async def start(update: Update, context: CallbackContext):
    """Enhanced start command with rate limiting"""
    try:
        if not update or not update.effective_user:
            LOGGER.error("No update or effective_user in start command")
            return

        user_id = update.effective_user.id
        first_name = update.effective_user.first_name or "User"
        username = update.effective_user.username or ""
        args = context.args

        # Rate limiting check
        if not RateLimiter.check_rate_limit(user_id):
            cooldown = RateLimiter.get_cooldown_time(user_id)
            await update.message.reply_text(
                f"⏳ ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ {cooldown} sᴇᴄᴏɴᴅs ʙᴇғᴏʀᴇ ᴜsɪɴɢ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴀɢᴀɪɴ"
            )
            return

        LOGGER.info(f"Start command from user {user_id} (@{username}) with args: {args}")

        referring_user_id = None
        if args and len(args) > 0 and args[0].startswith('r_'):
            try:
                referring_user_id = int(args[0][2:])
                LOGGER.info(f"Detected referral link: referrer={referring_user_id}")
            except (ValueError, IndexError) as e:
                LOGGER.error(f"Invalid referral code {args[0]}: {e}")
                referring_user_id = None

        user_data = await user_collection.find_one({"id": user_id})
        is_new_user = user_data is None

        if is_new_user:
            LOGGER.info(f"Creating new user {user_id}")
            
            new_user = {
                "id": user_id,
                "first_name": first_name,
                "username": username,
                "balance": 500,
                "characters": [],
                "referred_users": 0,
                "referred_by": None,
                "invited_user_ids": [],
                "registration_date": datetime.utcnow(),
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

            context.application.create_task(
                safe_track_bot_start(user_id, first_name, username, True)
            )

            if referring_user_id:
                LOGGER.info(f"Processing referral for new user {user_id} from {referring_user_id}")
                result = await process_referral(user_id, first_name, referring_user_id, context)
                
                if not result["success"] and result.get("is_suspicious"):
                    await update.message.reply_text(
                        "⚠️ sᴜsᴘɪᴄɪᴏᴜs ᴀᴄᴛɪᴠɪᴛʏ ᴅᴇᴛᴇᴄᴛᴇᴅ. ᴘʟᴇᴀsᴇ ᴄᴏɴᴛᴀᴄᴛ sᴜᴘᴘᴏʀᴛ."
                    )

        else:
            LOGGER.info(f"Existing user {user_id} started bot")
            
            await user_collection.update_one(
                {"id": user_id},
                {
                    "$set": {
                        "first_name": first_name,
                        "username": username,
                        "last_interaction": datetime.utcnow()
                    }
                }
            )

            context.application.create_task(
                safe_track_bot_start(user_id, first_name, username, False)
            )

        balance = user_data.get('balance', 0)

        try:
            characters = user_data.get('characters', [])
            unique_char_ids = set()
            for char in characters:
                if isinstance(char, dict):
                    char_id = char.get('id')
                    if char_id:
                        unique_char_ids.add(char_id)
            chars = len(unique_char_ids)
        except Exception as e:
            LOGGER.error(f"Error counting characters: {e}")
            chars = 0

        refs = user_data.get('referred_users', 0)

        # Get user's rank if they have referrals
        rank_text = ""
        if refs > 0:
            rank = await get_user_rank(user_id)
            if rank:
                rank_text = f"\n🏆 ʀᴀɴᴋ: <b>#{rank}</b>"

        welcome = "ᴡᴇʟᴄᴏᴍᴇ" if is_new_user else "ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ"
        bonus = f"\n\n<b>🎁 +{NEW_USER_BONUS}</b> ɢᴏʟᴅ ʙᴏɴᴜs" if (is_new_user and referring_user_id) else ""

        video_url = random.choice(VIDEOS)
        caption = f"""<b>{welcome}</b>

ɪ ᴀᴍ ᴘɪᴄᴋ ᴄᴀᴛᴄʜᴇʀ
ɪ sᴘᴀᴡɴ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘs ᴀɴᴅ ʟᴇᴛ ᴜsᴇʀs ᴄᴏʟʟᴇᴄᴛ ᴛʜᴇᴍ
sᴏ ᴡʜᴀᴛ ᴀʀᴇ ʏᴏᴜ ᴡᴀɪᴛɪɴɢ ғᴏʀ ᴀᴅᴅ ᴍᴇ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ ʙʏ ᴄʟɪᴄᴋ ᴏɴ ᴛʜᴇ ʙᴇʟᴏᴡ ʙᴜᴛᴛᴏɴ

<b>📊 ʏᴏᴜʀ sᴛᴀᴛs</b>
💰 ɢᴏʟᴅ: <b>{balance:,}</b>
🎴 ᴄʜᴀʀᴀᴄᴛᴇʀs: <b>{chars}</b>
👥 ʀᴇғᴇʀʀᴀʟs: <b>{refs}</b>{rank_text}{bonus}"""

        keyboard = [
            [InlineKeyboardButton("ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ", url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
            [
                InlineKeyboardButton("sᴜᴘᴘᴏʀᴛ", url=f'https://t.me/{SUPPORT_CHAT}'),
                InlineKeyboardButton("ᴜᴘᴅᴀᴛᴇs", url='https://t.me/PICK_X_UPDATE')
            ],
            [
                InlineKeyboardButton("ʜᴇʟᴘ", callback_data='help'),
                InlineKeyboardButton("ɪɴᴠɪᴛᴇ", callback_data='referral')
            ],
            [InlineKeyboardButton("ᴄʀᴇᴅɪᴛs", callback_data='credits')]
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

        LOGGER.info(f"Start command completed for user {user_id}")

    except Exception as e:
        LOGGER.error(f"Critical error in start command: {e}", exc_info=True)
        try:
            await update.message.reply_text("⚠️ An error occurred. Please try again later.")
        except:
            pass


async def refer_command(update: Update, context: CallbackContext):
    """Enhanced refer command with analytics"""
    try:
        user_id = update.effective_user.id
        
        # Rate limiting
        if not RateLimiter.check_rate_limit(user_id):
            cooldown = RateLimiter.get_cooldown_time(user_id)
            await update.message.reply_text(
                f"⏳ ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ {cooldown} sᴇᴄᴏɴᴅs"
            )
            return

        user_data = await user_collection.find_one({"id": user_id})

        if not user_data:
            await update.message.reply_text("⚠️ sᴛᴀʀᴛ ʙᴏᴛ ғɪʀsᴛ ᴜsɪɴɢ /start")
            return

        link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
        count = user_data.get('referred_users', 0)
        base_earned = count * REFERRER_REWARD
        milestone_earned = sum(
            REFERRAL_MILESTONES[m]["gold"] 
            for m in sorted(REFERRAL_MILESTONES.keys()) 
            if count >= m
        )
        total_earned = base_earned + milestone_earned

        # Get user rank
        rank = await get_user_rank(user_id)
        rank_text = f"🏆 ʀᴀɴᴋ: <b>#{rank}</b>\n" if rank else ""

        next_milestone = next(
            (m for m in sorted(REFERRAL_MILESTONES.keys()) if count < m),
            None
        )
        
        milestone_text = "\n".join([
            f"{'✅' if count >= m else '🔒'} <b>{m}</b> ʀᴇғs → {r['gold']:,} ɢᴏʟᴅ + {r['characters']} ᴄʜᴀʀs"
            for m, r in sorted(REFERRAL_MILESTONES.items())
        ])

        # Progress bar for next milestone
        progress_text = ""
        if next_milestone:
            progress_bar = create_progress_bar(count, next_milestone)
            progress_text = f"\n\n<b>📈 ᴘʀ