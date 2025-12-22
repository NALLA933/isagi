import random
import time
from html import escape
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

# Helper: Random video for preview
def get_random_video():
    return random.choice(VIDEOS)

# Helper: Progress bar
def get_progress_bar(current, target, length=10):
    filled = int((current / target) * length) if target > 0 else 0
    filled = min(filled, length)
    bar = "█" * filled + "░" * (length - filled)
    return f"`[{bar}]` {current}/{target}"

# Helper: Next milestone
def get_next_milestone(count):
    for m in sorted(REFERRAL_MILESTONES.keys()):
        if count < m:
            return m
    return None

# Helper: Daily invite task
DAILY_INVITE_TASK = {
    "required": 3,
    "reward": {"gold": 2000, "box": "Special Event Box"}
}

async def give_milestone_reward(user_id: int, milestone: int, context: CallbackContext) -> bool:
    try:
        reward = REFERRAL_MILESTONES[milestone]
        gold = reward["gold"]
        char_count = reward["characters"]
        rarities = reward["rarity"]

        # Use bulk_write for multiple characters
        bulk_ops = []
        bulk_ops.append(
            {"update_one": {
                "filter": {"id": user_id},
                "update": {"$inc": {"balance": gold}}
            }}
        )

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
                bulk_ops.append(
                    {"update_one": {
                        "filter": {"id": user_id},
                        "update": {"$push": {"characters": character}}
                    }}
                )

        if bulk_ops:
            await user_collection.bulk_write(bulk_ops)

        char_list_text = "
".join([
            f"{HAREM_MODE_MAPPING.get(c.get('rarity', 'common'), '🟢')} {c.get('name', 'Unknown')}"
            for c in characters
        ])

        msg = f"""<b>🎉 ᴍɪʟᴇsᴛᴏɴᴇ ʀᴇᴀᴄʜᴇᴅ</b>

ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs ᴏɴ ʀᴇᴀᴄʜɪɴɢ <b>{milestone}</b> ʀᴇғᴇʀʀᴀʟs

<b>ʀᴇᴡᴀʀᴅs</b>
💰 ɢᴏʟᴅ: <code>{gold:,}</code>
🎴 ᴄʜᴀʀᴀᴄᴛᴇʀs: <code>{char_count}</code>

<b>ᴄʜᴀʀᴀᴄᴛᴇʀs ʀᴇᴄᴇɪᴠᴇᴅ</b>
{char_list_text}

ᴋᴇᴇᴘ ɪɴᴠɪᴛɪɴɢ ғᴏʀ ᴍᴏʀᴇ ʀᴇᴡᴀʀᴅs"""

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=msg,
                parse_mode='HTML',
                link_preview_options=LinkPreviewOptions(
                    url=get_random_video(),
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

async def process_referral(user_id: int, first_name: str, referring_user_id: int, context: CallbackContext) -> bool:
    try:
        if not user_id or not referring_user_id or user_id == referring_user_id:
            LOGGER.warning(f"Invalid referral: user={user_id}, referrer={referring_user_id}")
            return False

        referring_user = await user_collection.find_one({"id": referring_user_id})
        if not referring_user:
            LOGGER.warning(f"Referring user {referring_user_id} not found")
            return False

        new_user = await user_collection.find_one({"id": user_id})
        if new_user and new_user.get('referred_by'):
            LOGGER.info(f"User {user_id} already referred by {new_user.get('referred_by')}")
            return False

        await user_collection.update_one(
            {"id": user_id},
            {
                "$set": {"referred_by": referring_user_id},
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

        milestone_reached = None
        for milestone in sorted(REFERRAL_MILESTONES.keys()):
            if old_count < milestone <= new_count:
                milestone_reached = milestone
                break

        if milestone_reached:
            LOGGER.info(f"Milestone {milestone_reached} reached for user {referring_user_id}")
            await give_milestone_reward(referring_user_id, milestone_reached, context)

        msg = f"""<b>✨ ʀᴇғᴇʀʀᴀʟ sᴜᴄᴄᴇss</b>

<b>{escape(first_name)}</b> ᴊᴏɪɴᴇᴅ ᴠɪᴀ ʏᴏᴜʀ ʟɪɴᴋ

<b>ʀᴇᴡᴀʀᴅs</b>
💰 ɢᴏʟᴅ: <code>{REFERRER_REWARD:,}</code>
📊 ɪɴᴠɪᴛᴇ ᴛᴀsᴋ: +1
👥 ᴛᴏᴛᴀʟ ʀᴇғᴇʀʀᴀʟs: <b>{new_count}</b>"""

        next_milestone = get_next_milestone(new_count)
        if next_milestone:
            remaining = next_milestone - new_count
            reward = REFERRAL_MILESTONES[next_milestone]
            msg += f"

<b>🎯 ɴᴇxᴛ ᴍɪʟᴇsᴛᴏɴᴇ</b>
{remaining} ᴍᴏʀᴇ ғᴏʀ {reward['gold']:,} ɢᴏʟᴅ + {reward['characters']} ᴄʜᴀʀᴀᴄᴛᴇʀs"

        try:
            await context.bot.send_message(
                chat_id=referring_user_id,
                text=msg,
                parse_mode='HTML',
                link_preview_options=LinkPreviewOptions(
                    url=get_random_video(),
                    show_above_text=True,
                    prefer_large_media=True
                )
            )
        except Exception as e:
            LOGGER.error(f"Could not notify referrer {referring_user_id}: {e}")

        return True

    except Exception as e:
        LOGGER.error(f"Referral processing error: {e}", exc_info=True)
        return False

async def safe_track_bot_start(user_id: int, first_name: str, username: str, is_new_user: bool):
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
    try:
        if not update or not update.effective_user:
            LOGGER.error("No update or effective_user in start command")
            return

        user_id = update.effective_user.id
        first_name = update.effective_user.first_name or "User"
        username = update.effective_user.username or ""
        args = context.args

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
                await process_referral(user_id, first_name, referring_user_id, context)

        else:
            LOGGER.info(f"Existing user {user_id} started bot")
            
            await user_collection.update_one(
                {"id": user_id},
                {"$set": {"first_name": first_name, "username": username}}
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

        welcome = "ᴡᴇʟᴄᴏᴍᴇ" if is_new_user else "ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ"
        bonus = f"

<b>🎁 +{NEW_USER_BONUS}</b> ɢᴏʟᴅ ʙᴏɴᴜs" if (is_new_user and referring_user_id) else ""

        video_url = get_random_video()
        caption = f"""<b>{welcome}</b>

ɪ ᴀᴍ ᴘɪᴄᴋ ᴄᴀᴛᴄʜᴇʀ
ɪ sᴘᴀᴡɴ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘs ᴀɴᴅ ʟᴇᴛ ᴜsᴇʀs ᴄᴏʟʟᴇᴄᴛ ᴛʜᴇᴍ
sᴏ ᴡʜᴀᴛ ᴀʀᴇ ʏᴏᴜ ᴡᴀɪᴛɪɴɢ ғᴏʀ ᴀᴅᴅ ᴍᴇ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ ʙʏ ᴄʟɪᴄᴋ ᴏɴ ᴛʜᴇ ʙᴇʟᴏᴡ ʙᴜᴛᴛᴏɴ

<b>ʏᴏᴜʀ sᴛᴀᴛs</b>
💰 ɢᴏʟᴅ: <b>{balance:,}</b>
🎴 ᴄʜᴀʀᴀᴄᴛᴇʀs: <b>{chars}</b>
👥 ʀᴇғᴇʀʀᴀʟs: <b>{refs}</b>{bonus}"""

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
    try:
        user_id = update.effective_user.id
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

        next_milestone = get_next_milestone(count)
        
        milestone_text = "
".join([
            f"{'✅' if count >= m else '🔒'} <b>{m}</b> ʀᴇғs → {r['gold']:,} ɢᴏʟᴅ + {r['characters']} ᴄʜᴀʀs"
            for m, r in sorted(REFERRAL_MILESTONES.items())
        ])

        # Progress bar
        if next_milestone