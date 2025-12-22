import asyncio
import random
import time
from html import escape

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    LinkPreviewOptions,
)
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
)

from shivu import (
    application,
    SUPPORT_CHAT,
    BOT_USERNAME,
    LOGGER,
    user_collection,
    collection,
)
from shivu.modules.chatlog import track_bot_start
from shivu.modules.database.sudo import fetch_sudo_users

# =========================
# CONSTANTS & STATIC DATA
# =========================

VIDEOS = [
    "https://files.catbox.moe/k3dhbe.mp4",
    "https://files.catbox.moe/iitev2.mp4",
    "https://files.catbox.moe/hs0e56.mp4",
]

REFERRER_REWARD = 1000
NEW_USER_BONUS = 500

OWNERS = [
    {"name": "Thorfinn", "username": "ll_Thorfinn_ll"},
]

SUDO_USERS_STATIC = [
    {"name": "Shadwoo", "username": "I_shadwoo"},
]

REFERRAL_MILESTONES = {
    5: {"gold": 5000, "characters": 1, "rarity": ["common", "rare"]},
    10: {"gold": 15000, "characters": 2, "rarity": ["rare", "legendary"]},
    25: {"gold": 40000, "characters": 3, "rarity": ["legendary", "special", "neon"]},
    50: {"gold": 100000, "characters": 5, "rarity": ["special", "neon", "manga", "celestial"]},
    100: {"gold": 250000, "characters": 10, "rarity": ["celestial", "premium", "mythic"]},
}

HAREM_MODE_MAPPING = {
    "common": "🟢 Common",
    "rare": "🟣 Rare",
    "legendary": "🟡 Legendary",
    "special": "💮 Special",
    "neon": "💫 Neon",
    "manga": "✨ Manga",
    "cosplay": "🎭 Cosplay",
    "celestial": "🎐 Celestial",
    "premium": "🔮 Premium",
    "erotic": "💋 Erotic",
    "summer": "🌤 Summer",
    "winter": "☃️ Winter",
    "monsoon": "☔️ Monsoon",
    "valentine": "💝 Valentine",
    "halloween": "🎃 Halloween",
    "christmas": "🎄 Christmas",
    "mythic": "🏵 Mythic",
    "events": "🎗 Events",
    "amv": "🎥 AMV",
    "tiny": "👼 Tiny",
    "default": None,
}

# =========================
# SMALL HELPERS
# =========================


def _random_video() -> str:
    return random.choice(VIDEOS)


def _link_preview(url: str | None = None) -> LinkPreviewOptions:
    return LinkPreviewOptions(
        url=url or _random_video(),
        show_above_text=True,
        prefer_large_media=True,
    )


def _format_gold(amount: int) -> str:
    return f"{amount:,}"


def _unique_character_count(user_data: dict) -> int:
    try:
        characters = user_data.get("characters", [])
        unique_char_ids = {
            char.get("id")
            for char in characters
            if isinstance(char, dict) and char.get("id")
        }
        return len(unique_char_ids)
    except Exception as e:
        LOGGER.error("Error counting characters: %s", e)
        return 0


def _calculate_milestone_earnings(ref_count: int) -> int:
    """Total milestone gold user should have earned for all crossed milestones."""
    return sum(
        data["gold"]
        for m, data in REFERRAL_MILESTONES.items()
        if ref_count >= m
    )


def _next_milestone(ref_count: int) -> int | None:
    for milestone in sorted(REFERRAL_MILESTONES.keys()):
        if ref_count < milestone:
            return milestone
    return None


def _format_milestone_lines(ref_count: int, compact: bool = False) -> str:
    """
    Compact=False:
        🔒 5 refs → 5,000 gold + 1 chars
    Compact=True:
        🔒 5 → 5,000 + 1 ᴄʜᴀʀs
    """
    lines = []
    for m, data in sorted(REFERRAL_MILESTONES.items()):
        locked_icon = "✅" if ref_count >= m else "🔒"
        if compact:
            lines.append(
                f"{locked_icon} <b>{m}</b> → {data['gold']:,} + {data['characters']} ᴄʜᴀʀs"
            )
        else:
            lines.append(
                f"{locked_icon} <b>{m}</b> ʀᴇғs → {data['gold']:,} ɢᴏʟᴅ + {data['characters']} ᴄʜᴀʀs"
            )
    return "
".join(lines)


async def _safe_send_message(
    context: CallbackContext,
    chat_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
            link_preview_options=_link_preview(),
        )
    except Exception as e:
        LOGGER.error("Error sending message to %s: %s", chat_id, e)


# =========================
# TRACKING
# =========================


async def safe_track_bot_start(
    user_id: int,
    first_name: str,
    username: str,
    is_new_user: bool,
) -> None:
    try:
        await asyncio.wait_for(
            track_bot_start(user_id, first_name, username, is_new_user),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        LOGGER.warning("track_bot_start timed out for user %s", user_id)
    except ImportError:
        LOGGER.warning("chatlog module not available, skipping bot start tracking")
    except Exception as e:
        LOGGER.error("Error in safe_track_bot_start: %s", e)


# =========================
# REFERRAL & REWARDS
# =========================


async def give_milestone_reward(
    user_id: int,
    milestone: int,
    context: CallbackContext,
) -> bool:
    try:
        reward = REFERRAL_MILESTONES[milestone]
        gold = reward["gold"]
        char_count = reward["characters"]
        rarities = reward["rarity"]

        await user_collection.update_one(
            {"id": user_id},
            {"$inc": {"balance": gold}},
        )

        characters = []
        for _ in range(char_count):
            rarity = random.choice(rarities)
            char_cursor = collection.aggregate(
                [
                    {"$match": {"rarity": rarity}},
                    {"$sample": {"size": 1}},
                ]
            )
            char_list = await char_cursor.to_list(1)
            if not char_list:
                continue

            character = char_list[0]
            characters.append(character)

            await user_collection.update_one(
                {"id": user_id},
                {"$push": {"characters": character}},
            )

        char_list_text = "
".join(
            f"{HAREM_MODE_MAPPING.get(c.get('rarity', 'common'), '🟢')} "
            f"{c.get('name', 'Unknown')}"
            for c in characters
        )

        msg = f"""<b>🎉 ᴍɪʟᴇsᴛᴏɴᴇ ʀᴇᴀᴄʜᴇᴅ</b>

ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs ᴏɴ ʀᴇᴀᴄʜɪɴɢ <b>{milestone}</b> ʀᴇғᴇʀʀᴀʟs

<b>ʀᴇᴡᴀʀᴅs</b>
💰 ɢᴏʟᴅ: <code>{_format_gold(gold)}</code>
🎴 ᴄʜᴀʀᴀᴄᴛᴇʀs: <code>{char_count}</code>

<b>ᴄʜᴀʀᴀᴄᴛᴇʀs ʀᴇᴄᴇɪᴠᴇᴅ</b>
{char_list_text}

ᴋᴇᴇᴘ ɪɴᴠɪᴛɪɴɢ ғᴏʀ ᴍᴏʀᴇ ʀᴇᴡᴀʀᴅs"""

        await _safe_send_message(context, user_id, msg)
        return True

    except Exception as e:
        LOGGER.error("Error giving milestone reward: %s", e, exc_info=True)
        return False


async def process_referral(
    user_id: int,
    first_name: str,
    referring_user_id: int,
    context: CallbackContext,
) -> bool:
    try:
        if not user_id or not referring_user_id or user_id == referring_user_id:
            LOGGER.warning(
                "Invalid referral: user=%s, referrer=%s",
                user_id,
                referring_user_id,
            )
            return False

        referring_user = await user_collection.find_one({"id": referring_user_id})
        if not referring_user:
            LOGGER.warning("Referring user %s not found", referring_user_id)
            return False

        new_user = await user_collection.find_one({"id": user_id})
        if new_user and new_user.get("referred_by"):
            LOGGER.info(
                "User %s already referred by %s",
                user_id,
                new_user.get("referred_by"),
            )
            return False

        # Mark new user + bonus
        await user_collection.update_one(
            {"id": user_id},
            {
                "$set": {"referred_by": referring_user_id},
                "$inc": {"balance": NEW_USER_BONUS},
            },
        )

        old_count = referring_user.get("referred_users", 0)
        new_count = old_count + 1

        # Update referrer
        await user_collection.update_one(
            {"id": referring_user_id},
            {
                "$inc": {
                    "balance": REFERRER_REWARD,
                    "referred_users": 1,
                    "pass_data.tasks.invites": 1,
                    "pass_data.total_invite_earnings": REFERRER_REWARD,
                },
                "$push": {"invited_user_ids": user_id},
            },
        )

        LOGGER.info(
            "Referral processed: %s -> %s (count: %s)",
            user_id,
            referring_user_id,
            new_count,
        )

        # Milestone check
        milestone_reached = None
        for milestone in sorted(REFERRAL_MILESTONES.keys()):
            if old_count < milestone <= new_count:
                milestone_reached = milestone
                break

        if milestone_reached:
            LOGGER.info(
                "Milestone %s reached for user %s",
                milestone_reached,
                referring_user_id,
            )
            await give_milestone_reward(referring_user_id, milestone_reached, context)

        msg = f"""<b>✨ ʀᴇғᴇʀʀᴀʟ sᴜᴄᴄᴇss</b>

<b>{escape(first_name)}</b> ᴊᴏɪɴᴇᴅ ᴠɪᴀ ʏᴏᴜʀ ʟɪɴᴋ

<b>ʀᴇᴡᴀʀᴅs</b>
💰 ɢᴏʟᴅ: <code>{_format_gold(REFERRER_REWARD)}</code>
📊 ɪɴᴠɪᴛᴇ ᴛᴀsᴋ: +1
👥 ᴛᴏᴛᴀʟ ʀᴇғᴇʀʀᴀʟs: <b>{new_count}</b>"""

        next_milestone_value = _next_milestone(new_count)
        if next_milestone_value:
            remaining = next_milestone_value - new_count
            reward = REFERRAL_MILESTONES[next_milestone_value]
            msg += (
                f"

<b>🎯 ɴᴇxᴛ ᴍɪʟᴇsᴛᴏɴᴇ</b>
"
                f"{remaining} ᴍᴏʀᴇ ғᴏʀ {reward['gold']:,} ɢᴏʟᴅ + {reward['characters']} ᴄʜᴀʀᴀᴄᴛᴇʀs"
            )

        await _safe_send_message(context, referring_user_id, msg)
        return True

    except Exception as e:
        LOGGER.error("Referral processing error: %s", e, exc_info=True)
        return False


# =========================
# /start COMMAND
# =========================


async def start(update: Update, context: CallbackContext) -> None:
    try:
        if not update or not update.effective_user:
            LOGGER.error("No update or effective_user in start command")
            return

        user = update.effective_user
        user_id = user.id
        first_name = user.first_name or "User"
        username = user.username or ""
        args = context.args

        LOGGER.info("Start from user %s (@%s) args=%s", user_id, username, args)

        # Parse referral from /start r_<id>
        referring_user_id = None
        if args and args[0].startswith("r_"):
            try:
                referring_user_id = int(args[0][2:])
                LOGGER.info("Detected referral link: referrer=%s", referring_user_id)
            except (ValueError, IndexError) as e:
                LOGGER.error("Invalid referral code %s: %s", args[0], e)
                referring_user_id = None

        user_data = await user_collection.find_one({"id": user_id})
        is_new_user = user_data is None

        if is_new_user:
            LOGGER.info("Creating new user %s", user_id)

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
                    "total_invite_earnings": 0,
                },
            }

            await user_collection.insert_one(new_user)
            user_data = new_user

            context.application.create_task(
                safe_track_bot_start(user_id, first_name, username, True)
            )

            if referring_user_id:
                LOGGER.info(
                    "Processing referral for new user %s from %s",
                    user_id,
                    referring_user_id,
                )
                await process_referral(
                    user_id, first_name, referring_user_id, context
                )

        else:
            LOGGER.info("Existing user %s started bot", user_id)

            await user_collection.update_one(
                {"id": user_id},
                {"$set": {"first_name": first_name, "username": username}},
            )

            context.application.create_task(
                safe_track_bot_start(user_id, first_name, username, False)
            )

        balance = user_data.get("balance", 0)
        chars = _unique_character_count(user_data)
        refs = user_data.get("referred_users", 0)

        welcome = "ᴡᴇʟᴄᴏᴍᴇ" if is_new_user else "ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ"
        bonus_line = (
            f"

<b>🎁 +{NEW_USER_BONUS}</b> ɢᴏʟᴅ ʙᴏɴᴜs"
            if (is_new_user and referring_user_id)
            else ""
        )

        caption = f"""<b>{welcome}</b>

ɪ ᴀᴍ ᴘɪᴄᴋ ᴄᴀᴛᴄʜᴇʀ
ɪ sᴘᴀᴡɴ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘs ᴀɴᴅ ʟᴇᴛ ᴜsᴇʀs ᴄᴏʟʟᴇᴄᴛ ᴛʜᴇᴍ
sᴏ ᴡʜᴀᴛ ᴀʀᴇ ʏᴏᴜ ᴡᴀɪᴛɪɴɢ ғᴏʀ ᴀᴅᴅ ᴍᴇ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ ʙʏ ᴄʟɪᴄᴋ ᴏɴ ᴛʜᴇ ʙᴇʟᴏᴡ ʙᴜᴛᴛᴏɴ

<b>ʏᴏᴜʀ sᴛᴀᴛs</b>
💰 ɢᴏʟᴅ: <b>{_format_gold(balance)}</b>
🎴 ᴄʜᴀʀᴀᴄᴛᴇʀs: <b>{chars}</b>
👥 ʀᴇғᴇʀʀᴀʟs: <b>{refs}</b>{bonus_line}"""

        keyboard = [
            [
                InlineKeyboardButton(
                    "ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ",
                    url=f"https://t.me/{BOT_USERNAME}?startgroup=new",
                )
            ],
            [
                InlineKeyboardButton("sᴜᴘᴘᴏʀᴛ", url=f"https://t.me/{SUPPORT_CHAT}"),
                InlineKeyboardButton("ᴜᴘᴅᴀᴛᴇs", url="https://t.me/PICK_X_UPDATE"),
            ],
            [
                InlineKeyboardButton("ʜᴇʟᴘ", callback_data="help"),
                InlineKeyboardButton("ɪɴᴠɪᴛᴇ", callback_data="referral"),
            ],
            [InlineKeyboardButton("ᴄʀᴇᴅɪᴛs", callback_data="credits")],
        ]

        await update.message.reply_text(
            text=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
            link_preview_options=_link_preview(),
        )

        LOGGER.info("Start command completed for user %s", user_id)

    except Exception as e:
        LOGGER.error("Critical error in start command: %s", e, exc_info=True)
        try:
            await update.message.reply_text(
                "⚠️ An error occurred. Please try again later."
            )
        except Exception:
            pass


# =========================
# /refer COMMAND
# =========================


async def refer_command(update: Update, context: CallbackContext) -> None:
    try:
        user_id = update.effective_user.id
        user_data = await user_collection.find_one({"id": user_id})

        if not user_data:
            await update.message.reply_text("⚠️ sᴛᴀʀᴛ ʙᴏᴛ ғɪʀsᴛ ᴜsɪɴɢ /start")
            return

        link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
        count = user_data.get("referred_users", 0)

        base_earned = count * REFERRER_REWARD
        milestone_earned = _calculate_milestone_earnings(count)
        total_earned = base_earned + milestone_earned

        next_m = _next_milestone(count)
        milestone_text = _format_milestone_lines(count, compact=False)

        text = f"""<b>🎁 ɪɴᴠɪᴛᴇ & ᴇᴀʀɴ ʀᴇᴡᴀʀᴅs</b>

<b>📊 ʏᴏᴜʀ sᴛᴀᴛs</b>
👥 ɪɴᴠɪᴛᴇᴅ: <b>{count}</b> ᴜsᴇʀs
💰 ᴛᴏᴛᴀʟ ᴇᴀʀɴᴇᴅ: <b>{_format_gold(total_earned)}</b> ɢᴏʟᴅ

<b>💎 ᴘᴇʀ ʀᴇғᴇʀʀᴀʟ</b>
• ʏᴏᴜ ɢᴇᴛ: <b>{_format_gold(REFERRER_REWARD)}</b> ɢᴏʟᴅ
• ғʀɪᴇɴᴅ ɢᴇᴛs: <b>{_format_gold(NEW_USER_BONUS)}</b> ɢᴏʟᴅ

<b>🏆 ᴍɪʟᴇsᴛᴏɴᴇ ʀᴇᴡᴀʀᴅs</b>
{milestone_text}"""

        if next_m:
            remaining = next_m - count
            next_reward = REFERRAL_MILESTONES[next_m]
            text += (
                f"

<b>🎯 ɴᴇxᴛ ɢᴏᴀʟ</b>
"
                f"{remaining} ᴍᴏʀᴇ ғᴏʀ <b>{next_reward['gold']:,}</b> ɢᴏʟᴅ + "
                f"<b>{next_reward['characters']}</b> ᴄʜᴀʀᴀᴄᴛᴇʀs"
            )

        text += f"

<b>🔗 ʏᴏᴜʀ ʀᴇғᴇʀʀᴀʟ ʟɪɴᴋ</b>
<code>{link}</code>"

        keyboard = [
            [
                InlineKeyboardButton(
                    "📤 sʜᴀʀᴇ ʟɪɴᴋ",
                    url=(
                        "https://t.me/share/url"
                        f"?url={link}&text=Join me on Pick Catcher and get {NEW_USER_BONUS} gold bonus!"
                    ),
                )
            ],
            [InlineKeyboardButton("👥 ᴠɪᴇᴡ ɪɴᴠɪᴛᴇs", callback_data="view_invites")],
        ]

        await update.message.reply_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
            link_preview_options=_link_preview(),
        )

    except Exception as e:
        LOGGER.error("Error in refer command: %s", e, exc_info=True)
        await update.message.reply_text("⚠️ An error occurred. Please try again.")


# =========================
# CALLBACK HANDLER
# =========================


async def button_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query

    try:
        await query.answer()
    except Exception as e:
        LOGGER.error("Error answering callback query: %s", e)
        return

    try:
        user_id = query.from_user.id
        user_data = await user_collection.find_one({"id": user_id})

        if not user_data:
            await query.answer("⚠️ sᴛᴀʀᴛ ʙᴏᴛ ғɪʀsᴛ", show_alert=True)
            return

        data = query.data
        video_url = _random_video()

        # ----- CREDITS -----
        if data == "credits":
            text = "<b>🩵 ʙᴏᴛ ᴄʀᴇᴅɪᴛs</b>

"
            text += "sᴘᴇᴄɪᴀʟ ᴛʜᴀɴᴋs ᴛᴏ ᴇᴠᴇʀʏᴏɴᴇ ᴡʜᴏ ᴍᴀᴅᴇ ᴛʜɪs ᴘᴏssɪʙʟᴇ

"
            text += "<b>ᴏᴡɴᴇʀs</b>"

            buttons: list[list[InlineKeyboardButton]] = []

            # Owners
            for i in range(0, len(OWNERS), 2):
                row = [
                    InlineKeyboardButton(
                        f"👑 {o['name']}",
                        url=f"https://t.me/{o['username'].replace('@', '')}",
                    )
                    for o in OWNERS[i : i + 2]
                ]
                if row:
                    buttons.append(row)

            # Dynamic sudo users
            try:
                sudo_users_db = await fetch_sudo_users()
                if sudo_users_db:
                    text += "

<b>sᴜᴅᴏ ᴜsᴇʀs</b>"
                    for i in range(0, len(sudo_users_db), 2):
                        row = []
                        for s in sudo_users_db[i : i + 2]:
                            username = s.get("username")
                            if not username:
                                continue
                            title = (
                                s.get("sudo_title")
                                or s.get("name")
                                or s.get("first_name")
                                or "Sudo"
                            )
                            row.append(
                                InlineKeyboardButton(
                                    title,
                                    url=f"https://t.me/{username.replace('@', '')}",
                                )
                            )
                        if row:
                            buttons.append(row)
            except ImportError:
                LOGGER.warning("sudo module not available")
            except Exception as e:
                LOGGER.error("Error fetching sudo users: %s", e)

            text += "

<b>🔐 ᴅᴇᴠᴇʟᴏᴘᴇʀ</b>"
            buttons.append(
                [
                    InlineKeyboardButton(
                        "💎 @siyaprobot",
                        url="https://t.me/siyaprobot",
                    )
                ]
            )
            buttons.append([InlineKeyboardButton("ʙᴀᴄᴋ", callback_data="back")])

            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="HTML",
                link_preview_options=_link_preview(video_url),
            )

        # ----- HELP -----
        elif data == "help":
            text = """<b>📖 ᴄᴏᴍᴍᴀɴᴅs</b>

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

            keyboard = [[InlineKeyboardButton("ʙᴀᴄᴋ", callback_data="back")]]

            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML",
                link_preview_options=_link_preview(video_url),
            )

        # ----- REFERRAL (INLINE BUTTON) -----
        elif data == "referral":
            count = user_data.get("referred_users", 0)
            link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"

            base_earned = count * REFERRER_REWARD
            milestone_earned = _calculate_milestone_earnings(count)
            total_earned = base_earned + milestone_earned

            next_m = _next_milestone(count)
            milestone_text = _format_milestone_lines(count, compact=True)

            text = f"""<b>🎁 ɪɴᴠɪᴛᴇ & ᴇᴀʀɴ</b>

<b>📊 ʏᴏᴜʀ sᴛᴀᴛs</b>
👥 ɪɴᴠɪᴛᴇᴅ: <b>{count}</b>
💰 ᴇᴀʀɴᴇᴅ: <b>{_format_gold(total_earned)}</b> ɢᴏʟᴅ

<b>💎 ʀᴇᴡᴀʀᴅs</b>
• ʏᴏᴜ: <b>{_format_gold(REFERRER_REWARD)}</b> ɢᴏʟᴅ
• ғʀɪᴇɴᴅ: <b>{_format_gold(NEW_USER_BONUS)}</b> ɢᴏʟᴅ

<b>🏆 ᴍɪʟᴇsᴛᴏɴᴇs</b>
{milestone_text}"""

            if next_m:
                remaining = next_m - count
                reward = REFERRAL_MILESTONES[next_m]
                text += (
                    f"

<b>🎯 ɴᴇxᴛ</b>
"
                    f"{remaining} ᴍᴏʀᴇ → <b>{reward['gold']:,}</b> + <b>{reward['characters']}</b> ᴄʜᴀʀs"
                )

            text += f"

<code>{link}</code>"

            keyboard = [
                [
                    InlineKeyboardButton(
                        "📤 sʜᴀʀᴇ",
                        url=(
                            "https://t.me/share/url"
                            f"?url={link}&text=Join Pick Catcher! Get {NEW_USER_BONUS:,} gold bonus 🎁"
                        ),
                    )
                ],
                [InlineKeyboardButton("👥 ᴠɪᴇᴡ ɪɴᴠɪᴛᴇs", callback_data="view_invites")],
                [InlineKeyboardButton("ʙᴀᴄᴋ", callback_data="back")],
            ]

            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML",
                link_preview_options=_link_preview(video_url),
            )

        # ----- VIEW INVITES -----
        elif data == "view_invites":
            count = user_data.get("referred_users", 0)
            invited_ids = user_data.get("invited_user_ids", [])

            if count == 0:
                text = """<b>👥 ʏᴏᴜʀ ɪɴᴠɪᴛᴇs</b>

ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ɪɴᴠɪᴛᴇᴅ ᴀɴʏᴏɴᴇ ʏᴇᴛ

sᴛᴀʀᴛ sʜᴀʀɪɴɢ ʏᴏᴜʀ ʟɪɴᴋ ᴛᴏ ᴇᴀʀɴ ʀᴇᴡᴀʀᴅs"""
            else:
                invited_users_lines = []
                for uid in invited_ids[:10]:
                    try:
                        invited = await user_collection.find_one({"id": uid})
                        if invited:
                            name = invited.get("first_name", "User")
                            invited_users_lines.append(f"• {escape(name)}")
                    except Exception:
                        continue

                users_text = (
                    "
".join(invited_users_lines) if invited_users_lines else "• ɴᴏ ᴅᴀᴛᴀ"
                )
                more = (
                    f"

<i>+{count - 10} ᴍᴏʀᴇ...</i>" if count > 10 else ""
                )

                text = f"""<b>👥 ʏᴏᴜʀ ɪɴᴠɪᴛᴇs</b>

<b>ᴛᴏᴛᴀʟ:</b> {count} ᴜsᴇʀs
<b>ᴇᴀʀɴᴇᴅ:</b> {count * REFERRER_REWARD:,} ɢᴏʟᴅ

<b>ʀᴇᴄᴇɴᴛ ɪɴᴠɪᴛᴇs</b>
{users_text}{more}"""

            keyboard = [[InlineKeyboardButton("ʙᴀᴄᴋ", callback_data="referral")]]

            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML",
                link_preview_options=_link_preview(video_url),
            )

        # ----- BACK -----
        elif data == "back":
            balance = user_data.get("balance", 0)
            chars = _unique_character_count(user_data)
            refs = user_data.get("referred_users", 0)

            caption = f"""<b>ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ</b>

ɪ ᴀᴍ ᴘɪᴄᴋ ᴄᴀᴛᴄʜᴇʀ
ᴄᴏʟʟᴇᴄᴛ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs ɪɴ ɢʀᴏᴜᴘs

<b>ʏᴏᴜʀ sᴛᴀᴛs</b>
💰 ɢᴏʟᴅ: <b>{_format_gold(balance)}</b>
🎴 ᴄʜᴀʀᴀᴄᴛᴇʀs: <b>{chars}</b>
👥 ʀᴇғᴇʀʀᴀʟs: <b>{refs}</b>"""

            keyboard = [
                [
                    InlineKeyboardButton(
                        "ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ",
                        url=f"https://t.me/{BOT_USERNAME}?startgroup=new",
                    )
                ],
                [
                    InlineKeyboardButton("sᴜᴘᴘᴏʀᴛ", url=f"https://t.me/{SUPPORT_CHAT}"),
                    InlineKeyboardButton("ᴜᴘᴅᴀᴛᴇs", url="https://t.me/PICK_X_UPDATE"),
                ],
                [
                    InlineKeyboardButton("ʜᴇʟᴘ", callback_data="help"),
                    InlineKeyboardButton("ɪɴᴠɪᴛᴇ", callback_data="referral"),
                ],
                [InlineKeyboardButton("ᴄʀᴇᴅɪᴛs", callback_data="credits")],
            ]

            await query.edit_message_text(
                text=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML",
                link_preview_options=_link_preview(video_url),
            )

    except Exception as e:
        LOGGER.error("Error in button callback: %s", e, exc_info=True)
        try:
            await query.answer(
                "⚠️ An error occurred. Please try again.",
                show_alert=True,
            )
        except Exception:
            pass


# =========================
# HANDLER REGISTRATION
# =========================

application.add_handler(CommandHandler("start", start, block=False))
application.add_handler(CommandHandler("refer", refer_command, block=False))
application.add_handler(
    CallbackQueryHandler(
        button_callback,
        pattern="^(help|referral|credits|back|view_invites)$",
        block=False,
    )
)

LOGGER.info("✓ Start module loaded successfully")