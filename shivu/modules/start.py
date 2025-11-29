import random
from shivu.modules.database.sudo import fetch_sudo_users
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, LinkPreviewOptions
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from shivu import application, SUPPORT_CHAT, BOT_USERNAME, LOGGER, user_collection, user_totals_collection, collection
from shivu.modules.chatlog import track_bot_start
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

# Referral Milestone Rewards
REFERRAL_MILESTONES = {
    5: {
        "gold": 5000,
        "characters": 1,
        "rarity": ["common", "rare"]
    },
    10: {
        "gold": 15000,
        "characters": 2,
        "rarity": ["rare", "legendary"]
    },
    25: {
        "gold": 40000,
        "characters": 3,
        "rarity": ["legendary", "special", "neon"]
    },
    50: {
        "gold": 100000,
        "characters": 5,
        "rarity": ["special", "neon", "manga", "celestial"]
    },
    100: {
        "gold": 250000,
        "characters": 10,
        "rarity": ["celestial", "premium", "mythic"]
    }
}

HAREM_MODE_MAPPING = {
    "common": "🟢 Common",
    "rare": "🟣 Rare",
    "legendary": "🟡 Legendary",
    "special": "💮 Special Edition",
    "neon": "💫 Neon",
    "manga": "✨ Manga",
    "cosplay": "🎭 Cosplay",
    "celestial": "🎐 Celestial",
    "premium": "🔮 Premium Edition",
    "erotic": "💋 Erotic",
    "summer": "🌤 Summer",
    "winter": "☃️ Winter",
    "monsoon": "☔️ Monsoon",
    "valentine": "💝 Valentine",
    "halloween": "🎃 Halloween",
    "christmas": "🎄 Christmas",
    "mythic": "🏵 Mythic",
    "events": "🎗 Special Events",
    "amv": "🎥 AMV",
    "tiny": "👼 Tiny",
    "default": None
}


async def give_milestone_reward(user_id, milestone, context):
    """Give milestone rewards to user"""
    try:
        reward = REFERRAL_MILESTONES[milestone]
        gold = reward["gold"]
        char_count = reward["characters"]
        rarities = reward["rarity"]
        
        # Add gold
        await user_collection.update_one(
            {"id": user_id},
            {"$inc": {"balance": gold}}
        )
        
        # Get random characters
        characters = []
        for _ in range(char_count):
            rarity = random.choice(rarities)
            char = await collection.aggregate([
                {"$match": {"rarity": rarity}},
                {"$sample": {"size": 1}}
            ]).to_list(1)
            
            if char:
                character = char[0]
                characters.append(character)
                
                # Add to user collection
                await user_collection.update_one(
                    {"id": user_id},
                    {"$push": {"characters": character}}
                )
        
        # Send reward notification
        char_list = "\n".join([
            f"{HAREM_MODE_MAPPING.get(c.get('rarity', 'common'), '🟢')} {c.get('name', 'Unknown')}"
            for c in characters
        ])
        
        msg = f"""<b>🎉 ᴍɪʟᴇsᴛᴏɴᴇ ʀᴇᴀᴄʜᴇᴅ</b>

ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs ᴏɴ ʀᴇᴀᴄʜɪɴɢ <b>{milestone}</b> ʀᴇғᴇʀʀᴀʟs

<b>ʀᴇᴡᴀʀᴅs</b>
💰 ɢᴏʟᴅ: <code>{gold:,}</code>
🎴 ᴄʜᴀʀᴀᴄᴛᴇʀs: <code>{char_count}</code>

<b>ᴄʜᴀʀᴀᴄᴛᴇʀs ʀᴇᴄᴇɪᴠᴇᴅ</b>
{char_list}

ᴋᴇᴇᴘ ɪɴᴠɪᴛɪɴɢ ғᴏʀ ᴍᴏʀᴇ ʀᴇᴡᴀʀᴅs"""
        
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


async def process_referral(user_id, first_name, referring_user_id, context):
    try:
        if not user_id or not referring_user_id or user_id == referring_user_id:
            return False

        referring_user = await user_collection.find_one({"id": referring_user_id})
        if not referring_user:
            return False

        new_user = await user_collection.find_one({"id": user_id})
        if new_user and new_user.get('referred_by'):
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

        # Check for milestone rewards
        milestone_reached = None
        for milestone in sorted(REFERRAL_MILESTONES.keys()):
            if old_count < milestone <= new_count:
                milestone_reached = milestone
                break
        
        if milestone_reached:
            await give_milestone_reward(referring_user_id, milestone_reached, context)

        msg = f"""<b>✨ ʀᴇғᴇʀʀᴀʟ sᴜᴄᴄᴇss</b>

<b>{escape(first_name)}</b> ᴊᴏɪɴᴇᴅ ᴠɪᴀ ʏᴏᴜʀ ʟɪɴᴋ

<b>ʀᴇᴡᴀʀᴅs</b>
💰 ɢᴏʟᴅ: <code>{REFERRER_REWARD:,}</code>
📊 ɪɴᴠɪᴛᴇ ᴛᴀsᴋ: +1
👥 ᴛᴏᴛᴀʟ ʀᴇғᴇʀʀᴀʟs: <b>{new_count}</b>"""

        # Show next milestone
        next_milestone = None
        for milestone in sorted(REFERRAL_MILESTONES.keys()):
            if new_count < milestone:
                next_milestone = milestone
                break
        
        if next_milestone:
            remaining = next_milestone - new_count
            reward = REFERRAL_MILESTONES[next_milestone]
            msg += f"\n\n<b>🎯 ɴᴇxᴛ ᴍɪʟᴇsᴛᴏɴᴇ</b>\n{remaining} ᴍᴏʀᴇ ғᴏʀ {reward['gold']:,} ɢᴏʟᴅ + {reward['characters']} ᴄʜᴀʀᴀᴄᴛᴇʀs"

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

        return True

    except Exception as e:
        LOGGER.error(f"Referral processing error: {e}", exc_info=True)
        return False


async def start(update: Update, context: CallbackContext):
    try:
        if not update or not update.effective_user:
            return

        user_id = update.effective_user.id
        first_name = update.effective_user.first_name or "User"
        username = update.effective_user.username or ""
        args = context.args

        referring_user_id = None
        if args and len(args) > 0 and args[0].startswith('r_'):
            try:
                referring_user_id = int(args[0][2:])
            except (ValueError, IndexError):
                referring_user_id = None

        user_data = await user_collection.find_one({"id": user_id})
        is_new_user = user_data is None

        if is_new_user:
            new_user = {
                "id": user_id,
                "first_name": first_name,
                "username": username,
                "balance": NEW_USER_BONUS if referring_user_id else 500,
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

            asyncio.create_task(safe_track_bot_start(user_id, first_name, username, is_new_user))

            if referring_user_id:
                await process_referral(user_id, first_name, referring_user_id, context)

        else:
            await user_collection.update_one(
                {"id": user_id},
                {
                    "$set": {
                        "first_name": first_name,
                        "username": username
                    }
                }
            )

            asyncio.create_task(safe_track_bot_start(user_id, first_name, username, is_new_user))

        balance = user_data.get('balance', 0)

        try:
            totals = await user_totals_collection.find_one({'id': user_id})
            chars = totals.get('count', 0) if totals else 0
        except:
            chars = 0

        refs = user_data.get('referred_users', 0)

        welcome = "ᴡᴇʟᴄᴏᴍᴇ" if is_new_user else "ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ"
        bonus = f"\n\n<b>🎁 +{NEW_USER_BONUS}</b> ɢᴏʟᴅ ʙᴏɴᴜs" if (is_new_user and referring_user_id) else ""

        video_url = random.choice(VIDEOS)
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

    except Exception as e:
        LOGGER.error(f"Critical error in start command: {e}", exc_info=True)
        try:
            await update.message.reply_text("⚠️ An error occurred while processing your request. Please try again later.")
        except:
            pass


async def safe_track_bot_start(user_id, first_name, username, is_new_user):
    """Wrapper to safely call track_bot_start without blocking the main flow"""
    try:
        await asyncio.wait_for(
            track_bot_start(user_id, first_name, username, is_new_user),
            timeout=5.0
        )
    except asyncio.TimeoutError:
        LOGGER.warning(f"track_bot_start timed out for user {user_id}")
    except Exception as e:
        LOGGER.error(f"Error in safe_track_bot_start: {e}", exc_info=True)


async def refer_command(update: Update, context: CallbackContext):
    """Dedicated referral command with detailed information"""
    try:
        user_id = update.effective_user.id
        user_data = await user_collection.find_one({"id": user_id})
        
        if not user_data:
            await update.message.reply_text("⚠️ sᴛᴀʀᴛ ʙᴏᴛ ғɪʀsᴛ ᴜsɪɴɢ /start")
            return
        
        link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
        count = user_data.get('referred_users', 0)
        base_earned = count * REFERRER_REWARD
        milestone_earned = 0
        
        # Calculate milestone earnings
        for milestone in sorted(REFERRAL_MILESTONES.keys()):
            if count >= milestone:
                milestone_earned += REFERRAL_MILESTONES[milestone]["gold"]
        
        total_earned = base_earned + milestone_earned
        
        # Find next milestone
        next_milestone = None
        next_reward = None
        for milestone in sorted(REFERRAL_MILESTONES.keys()):
            if count < milestone:
                next_milestone = milestone
                next_reward = REFERRAL_MILESTONES[milestone]
                break
        
        # Build milestone list
        milestone_text = ""
        for milestone in sorted(REFERRAL_MILESTONES.keys()):
            reward = REFERRAL_MILESTONES[milestone]
            status = "✅" if count >= milestone else "🔒"
            milestone_text += f"\n{status} <b>{milestone}</b> ʀᴇғs → {reward['gold']:,} ɢᴏʟᴅ + {reward['characters']} ᴄʜᴀʀs"
        
        text = f"""<b>🎁 ɪɴᴠɪᴛᴇ & ᴇᴀʀɴ ʀᴇᴡᴀʀᴅs</b>

<b>📊 ʏᴏᴜʀ sᴛᴀᴛs</b>
👥 ɪɴᴠɪᴛᴇᴅ: <b>{count}</b> ᴜsᴇʀs
💰 ᴛᴏᴛᴀʟ ᴇᴀʀɴᴇᴅ: <b>{total_earned:,}</b> ɢᴏʟᴅ

<b>💎 ᴘᴇʀ ʀᴇғᴇʀʀᴀʟ</b>
• ʏᴏᴜ ɢᴇᴛ: <b>{REFERRER_REWARD:,}</b> ɢᴏʟᴅ
• ғʀɪᴇɴᴅ ɢᴇᴛs: <b>{NEW_USER_BONUS:,}</b> ɢᴏʟᴅ

<b>🏆 ᴍɪʟᴇsᴛᴏɴᴇ ʀᴇᴡᴀʀᴅs</b>{milestone_text}"""

        if next_milestone:
            remaining = next_milestone - count
            text += f"\n\n<b>🎯 ɴᴇxᴛ ɢᴏᴀʟ</b>\n{remaining} ᴍᴏʀᴇ ғᴏʀ <b>{next_reward['gold']:,}</b> ɢᴏʟᴅ + <b>{next_reward['characters']}</b> ᴄʜᴀʀᴀᴄᴛᴇʀs"
        
        text += f"\n\n<b>🔗 ʏᴏᴜʀ ʀᴇғᴇʀʀᴀʟ ʟɪɴᴋ</b>\n<code>{link}</code>"
        
        keyboard = [
            [InlineKeyboardButton("📤 sʜᴀʀᴇ ʟɪɴᴋ", url=f"https://t.me/share/url?url={link}&text=Join me on Pick Catcher and get {NEW_USER_BONUS} gold bonus!")],
            [InlineKeyboardButton("👥 ᴠɪᴇᴡ ɪɴᴠɪᴛᴇs", callback_data='view_invites')]
        ]
        
        await update.message.reply_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML',
            link_preview_options=LinkPreviewOptions(
                url=random.choice(VIDEOS),
                show_above_text=True,
                prefer_large_media=True
            )
        )
        
    except Exception as e:
        LOGGER.error(f"Error in refer command: {e}", exc_info=True)
        await update.message.reply_text("⚠️ An error occurred. Please try again.")


async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query

    try:
        await query.answer()
    except Exception as e:
        LOGGER.error(f"Error answering callback query: {e}")
        return

    try:
        user_id = query.from_user.id
        user_data = await user_collection.find_one({"id": user_id})

        if not user_data:
            await query.answer("⚠️ sᴛᴀʀᴛ ʙᴏᴛ ғɪʀsᴛ", show_alert=True)
            return

        video_url = random.choice(VIDEOS)

        if query.data == 'credits':
            text = f"""<b>🩵 ʙᴏᴛ ᴄʀᴇᴅɪᴛs</b>

sᴘᴇᴄɪᴀʟ ᴛʜᴀɴᴋs ᴛᴏ ᴇᴠᴇʀʏᴏɴᴇ ᴡʜᴏ ᴍᴀᴅᴇ ᴛʜɪs ᴘᴏssɪʙʟᴇ

<b>ᴏᴡɴᴇʀs</b>"""

            buttons = []

            if OWNERS:
                for i in range(0, len(OWNERS), 2):
                    owner_row = []
                    for owner in OWNERS[i:i+2]:
                        owner_name = owner.get('name', 'Owner')
                        owner_username = owner.get('username', '').replace('@', '')
                        if owner_username:
                            owner_row.append(
                                InlineKeyboardButton(
                                    f"👑 {owner_name}",
                                    url=f"https://t.me/{owner_username}"
                                )
                            )
                    if owner_row:
                        buttons.append(owner_row)

            sudo_users_db = []
            try:
                sudo_users_db = await fetch_sudo_users()
            except Exception as e:
                LOGGER.error(f"Error fetching sudo users from database: {e}")

            if sudo_users_db and len(sudo_users_db) > 0:
                text += "\n\n<b>sᴜᴅᴏ ᴜsᴇʀs</b>"

                for i in range(0, len(sudo_users_db), 2):
                    sudo_row = []
                    for sudo in sudo_users_db[i:i+2]:
                        sudo_title = sudo.get('sudo_title') or sudo.get('name') or sudo.get('first_name', 'Sudo User')
                        sudo_username = sudo.get('username', '').replace('@', '')

                        if sudo_username:
                            sudo_row.append(
                                InlineKeyboardButton(
                                    sudo_title,
                                    url=f"https://t.me/{sudo_username}"
                                )
                            )
                    if sudo_row:
                        buttons.append(sudo_row)

            elif SUDO_USERS:
                text += "\n\n<b>sᴜᴅᴏ ᴜsᴇʀs</b>"
                for i in range(0, len(SUDO_USERS), 2):
                    sudo_row = []
                    for sudo in SUDO_USERS[i:i+2]:
                        sudo_name = sudo.get('name', 'Sudo User')
                        sudo_username = sudo.get('username', '').replace('@', '')
                        if sudo_username:
                            sudo_row.append(
                                InlineKeyboardButton(
                                    sudo_name,
                                    url=f"https://t.me/{sudo_username}"
                                )
                            )
                    if sudo_row:
                        buttons.append(sudo_row)

            buttons.append([InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='back')])

            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode='HTML',
                link_preview_options=LinkPreviewOptions(
                    url=video_url,
                    show_above_text=True,
                    prefer_large_media=True
                )
            )

        elif query.data == 'help':
            text = f"""<b>📖 ᴄᴏᴍᴍᴀɴᴅs</b>

/grab - ɢᴜᴇss ᴄʜᴀʀᴀᴄᴛᴇʀ
/fav - sᴇᴛ ғᴀᴠᴏʀɪᴛᴇ
/harem - ᴠɪᴇᴡ ᴄᴏʟʟᴇᴄᴛɪᴏɴ
/trade - ᴛʀᴀᴅᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs
/gift - ɢɪғᴛ ᴄʜᴀʀᴀᴄᴛᴇʀ
/bal - ᴄʜᴇᴄᴋ ᴡᴀʟʟᴇᴛ
/pay - sᴇɴᴅ ɢᴏʟᴅ
/claim - ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅ
/roll - ɢᴀᴍʙʟᴇ ɢᴏʟᴅ
/refer - ɪɴᴠɪᴛᴇ ғʀɪᴇɴᴅs"""

            keyboard = [[InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='back')]]

            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML',
                link_preview_options=LinkPreviewOptions(
                    url=video_url,
                    show_above_text=True,
                    prefer_large_media=True
                )
            )

        elif query.data == 'referral':
            link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
            count = user_data.get('referred_users', 0)
            base_earned = count * REFERRER_REWARD
            milestone_earned = 0
            
            for milestone in sorted(REFERRAL_MILESTONES.keys()):
                if count >= milestone:
                    milestone_earned += REFERRAL_MILESTONES[milestone]["gold"]
            
            total_earned = base_earned + milestone_earned
            
            next_milestone = None
            next_reward = None
            for milestone in sorted(REFERRAL_MILESTONES.keys()):
                if count < milestone:
                    next_milestone = milestone
                    next_reward = REFERRAL_MILESTONES[milestone]
                    break
            
            milestone_text = ""
            for milestone in sorted(REFERRAL_MILESTONES.keys()):
                reward = REFERRAL_MILESTONES[milestone]
                status = "✅" if count >= milestone else "🔒"
                milestone_text += f"\n{status} <b>{milestone}</b> → {reward['gold']:,} + {reward['characters']} ᴄʜᴀʀs"

            text = f"""<b>🎁 ɪɴᴠɪᴛᴇ & ᴇᴀʀɴ</b>

<b>📊 ʏᴏᴜʀ sᴛᴀᴛs</b>
👥 ɪɴᴠɪᴛᴇᴅ: <b>{count}</b>
💰 ᴇᴀʀɴᴇᴅ: <b>{total_earned:,}</b> ɢᴏʟᴅ

<b>💎 ʀᴇᴡᴀʀᴅs</b>
• ʏᴏᴜ: <b>{REFERRER_REWARD:,}</b> ɢᴏʟᴅ
• ғʀɪᴇɴᴅ: <b>{NEW_USER_BONUS:,}</b> ɢᴏʟᴅ

<b>🏆 ᴍɪʟᴇsᴛᴏɴᴇs</b>{milestone_text}"""

            if next_milestone:
                remaining = next_milestone - count
                text += f"\n\n<b>🎯 ɴᴇxᴛ</b>\n{remaining} ᴍᴏʀᴇ → <b>{next_reward['gold']:,}</b> + <b>{next_reward['characters']}</b> ᴄʜᴀʀs"
            
            text += f"\n\n<code>{link}</code>"

            keyboard = [
                [InlineKeyboardButton("📤 sʜᴀʀᴇ", url=f"https://t.me/share/url?url={link}&text=Join Pick Catcher! Get {NEW_USER_BONUS:,} gold bonus 🎁")],
                [InlineKeyboardButton("👥 ᴠɪᴇᴡ ɪɴᴠɪᴛᴇs", callback_data='view_invites')],
                [InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='back')]
            ]

            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML',
                link_preview_options=LinkPreviewOptions(
                    url=video_url,
                    show_above_text=True,
                    prefer_large_media=True
                )
            )

        elif query.data == 'view_invites':
            count = user_data.get('referred_users', 0)
            invited_ids = user_data.get('invited_user_ids', [])
            
            if count == 0:
                text = """<b>👥 ʏᴏᴜʀ ɪɴᴠɪᴛᴇs</b>

ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ɪɴᴠɪᴛᴇᴅ ᴀɴʏᴏɴᴇ ʏᴇᴛ

sᴛᴀʀᴛ sʜᴀʀɪɴɢ ʏᴏᴜʀ ʟɪɴᴋ ᴛᴏ ᴇᴀʀɴ ʀᴇᴡᴀʀᴅs"""
            else:
                invited_users = []
                for uid in invited_ids[:10]:  # Show last 10
                    try:
                        invited = await user_collection.find_one({"id": uid})
                        if invited:
                            name = invited.get('first_name', 'User')
                            invited_users.append(f"• {escape(name)}")
                    except:
                        pass
                
                users_text = "\n".join(invited_users) if invited_users else "• ɴᴏ ᴅᴀᴛᴀ"
                more = f"\n\n<i>+{count - 10} ᴍᴏʀᴇ...</i>" if count > 10 else ""
                
                text = f"""<b>👥 ʏᴏᴜʀ ɪɴᴠɪᴛᴇs</b>

<b>ᴛᴏᴛᴀʟ:</b> {count} ᴜsᴇʀs
<b>ᴇᴀʀɴᴇᴅ:</b> {count * REFERRER_REWARD:,} ɢᴏʟᴅ

<b>ʀᴇᴄᴇɴᴛ ɪɴᴠɪᴛᴇs</b>
{users_text}{more}"""
            
            keyboard = [[InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='referral')]]
            
            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML',
                link_preview_options=LinkPreviewOptions(
                    url=video_url,
                    show_above_text=True,
                    prefer_large_media=True
                )
            )

        elif query.data == 'back':
            balance = user_data.get('balance', 0)

            try:
                totals = await user_totals_collection.find_one({'id': user_id})
                chars = totals.get('count', 0) if totals else 0
            except:
                chars = 0

            refs = user_data.get('referred_users', 0)

            caption = f"""<b>ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ</b>

ɪ ᴀᴍ ᴘɪᴄᴋ ᴄᴀᴛᴄʜᴇʀ
ᴄᴏʟʟᴇᴄᴛ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs ɪɴ ɢʀᴏᴜᴘs

<b>ʏᴏᴜʀ sᴛᴀᴛs</b>
💰 ɢᴏʟᴅ: <b>{balance:,}</b>
🎴 ᴄʜᴀʀᴀᴄᴛᴇʀs: <b>{chars}</b>
👥 ʀᴇғᴇʀʀᴀʟs: <b>{refs}</b>"""

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

            await query.edit_message_text(
                text=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML',
                link_preview_options=LinkPreviewOptions(
                    url=video_url,
                    show_above_text=True,
                    prefer_large_media=True
                )
            )

    except Exception as e:
        LOGGER.error(f"Error in button callback: {e}", exc_info=True)
        try:
            await query.answer("⚠️ An error occurred. Please try again.", show_alert=True)
        except:
            pass


# Register handlers
application.add_handler(CommandHandler('start', start, block=False))
application.add_handler(CommandHandler('refer', refer_command, block=False))
application.add_handler(CallbackQueryHandler(button_callback, pattern='^(help|referral|credits|back|view_invites)$', block=False))