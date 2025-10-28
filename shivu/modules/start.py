import random
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from telegram.error import BadRequest
from shivu import (
    application, SUPPORT_CHAT, BOT_USERNAME, GROUP_ID, LOGGER,
    user_collection, user_totals_collection
)

# ------------------ CONFIG ------------------
PHOTO_URL = [
    "https://files.catbox.moe/8722ku.jpeg",
    "https://files.catbox.moe/kgcrnb.jpeg"
]
REFERRER_REWARD = 1000
NEW_USER_BONUS = 500

# OWNER & SUDO DATA
OWNERS = [
    {"name": "Thorfinn", "username": "ll_Thorfinn_ll", "id": 8420981179},
]
SUDO_USERS = [
    {"name": "Shadwoo", "username": "I_shadwoo", "id": 5147822244},
]

# ------------------ UTILITIES ------------------
def sc(text):
    """Convert to small caps"""
    m = {
        'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ғ', 'g': 'ɢ',
        'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ',
        'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ', 's': 's', 't': 'ᴛ', 'u': 'ᴜ',
        'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ',
        'A': 'ᴀ', 'B': 'ʙ', 'C': 'ᴄ', 'D': 'ᴅ', 'E': 'ᴇ', 'F': 'ғ', 'G': 'ɢ',
        'H': 'ʜ', 'I': 'ɪ', 'J': 'ᴊ', 'K': 'ᴋ', 'L': 'ʟ', 'M': 'ᴍ', 'N': 'ɴ',
        'O': 'ᴏ', 'P': 'ᴘ', 'Q': 'ǫ', 'R': 'ʀ', 'S': 's', 'T': 'ᴛ', 'U': 'ᴜ',
        'V': 'ᴠ', 'W': 'ᴡ', 'X': 'x', 'Y': 'ʏ', 'Z': 'ᴢ'
    }
    return ''.join(m.get(c, c) for c in text)


# ------------------ REFERRAL PROCESS ------------------
async def process_referral(user_id, first_name, referring_user_id, context):
    """Handle referral rewards."""
    try:
        LOGGER.info(f"[START] Processing referral: {user_id} referred by {referring_user_id}")

        if user_id == referring_user_id:
            return False

        referring_user = await user_collection.find_one({"id": referring_user_id})
        if not referring_user:
            return False

        new_user = await user_collection.find_one({"id": user_id})
        if new_user and new_user.get('referred_by'):
            return False

        await user_collection.update_one(
            {"id": user_id},
            {"$set": {"referred_by": referring_user_id}, "$inc": {"balance": NEW_USER_BONUS}}
        )

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

        msg = (
            f"<b>{sc('referral success')}</b>\n\n"
            f"<b>{escape(first_name)}</b> {sc('joined via your link')}\n\n"
            f"{sc('gold')}: <code>{REFERRER_REWARD:,}</code>\n"
            f"{sc('invite task')}: +1"
        )

        try:
            await context.bot.send_message(chat_id=referring_user_id, text=msg, parse_mode='HTML')
        except Exception:
            pass

        return True
    except Exception as e:
        LOGGER.error(f"[START ERROR] Referral process failed: {e}")
        return False


# ------------------ START COMMAND ------------------
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    username = update.effective_user.username
    args = context.args

    LOGGER.info(f"[START] Command called by {user_id} ({first_name})")

    referring_user_id = None
    if args and args[0].startswith('r_'):
        try:
            referring_user_id = int(args[0][2:])
        except Exception:
            pass

    user_data = await user_collection.find_one({"id": user_id})
    is_new_user = user_data is None

    # Register new user
    if is_new_user:
        LOGGER.info(f"[START] Registering new user {user_id}")
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

        if referring_user_id:
            await process_referral(user_id, first_name, referring_user_id, context)

    # Message caption
    balance = user_data.get('balance', 0)
    totals = await user_totals_collection.find_one({'id': user_id})
    chars = totals.get('count', 0) if totals else 0
    refs = user_data.get('referred_users', 0)

    welcome = sc('welcome back') if not is_new_user else sc('welcome')
    bonus = f"\n\n<b>+{NEW_USER_BONUS}</b> {sc('gold bonus')}" if (is_new_user and referring_user_id) else ""

    caption = (
        f"<b>{welcome}</b>\n\n"
        f"{sc('collect anime characters in groups')}\n"
        f"{sc('add me to start')}{bonus}\n\n"
        f"<b>{sc('your stats')}</b>\n"
        f"{sc('gold')}: <b>{balance:,}</b>\n"
        f"{sc('characters')}: <b>{chars}</b>\n"
        f"{sc('referrals')}: <b>{refs}</b>"
    )

    keyboard = [
        [InlineKeyboardButton(sc("add to group"), url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
        [
            InlineKeyboardButton(sc("support"), url=f'https://t.me/{SUPPORT_CHAT}'),
            InlineKeyboardButton(sc("updates"), url='https://t.me/PICK_X_UPDATE')
        ],
        [
            InlineKeyboardButton(sc("help"), callback_data='help'),
            InlineKeyboardButton(sc("invite"), callback_data='referral')
        ],
        [InlineKeyboardButton(sc("credits"), callback_data='credits')]
    ]

    try:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=random.choice(PHOTO_URL),
            caption=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    except Exception as e:
        LOGGER.error(f"[START ERROR] Failed to send photo: {e}")
        await update.message.reply_text(caption, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


# ------------------ BUTTON HANDLER ------------------
async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = await user_collection.find_one({"id": user_id})

    if not user_data:
        await query.answer(sc("start bot first"), show_alert=True)
        return

    if query.data == 'credits':
        text = "<b>🩵 " + sc("bot credits") + "</b>\n\n"
        text += f"{sc('special thanks to everyone who made this possible')}\n"

        # Create button rows for owners and sudo users
        buttons = []

        # Owner buttons
        if OWNERS:
            text += f"\n<b>{sc('owners')}</b>\n"
            owner_row = []
            for o in OWNERS:
                owner_row.append(
                    InlineKeyboardButton(
                        text=f"👑 {o['name']}",
                        url=f"https://t.me/{o['username']}"
                    )
                )
            buttons.append(owner_row)

        # Sudo buttons
        if SUDO_USERS:
            text += f"\n<b>{sc('sudo users')}</b>\n"
            sudo_row = []
            for s in SUDO_USERS:
                sudo_row.append(
                    InlineKeyboardButton(
                        text=f"⚡ {s['name']}",
                        url=f"https://t.me/{s['username']}"
                    )
                )
            buttons.append(sudo_row)

        # Back button
        buttons.append([InlineKeyboardButton(sc("back"), callback_data='back')])

        await query.edit_message_caption(
            caption=text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode='HTML'
        )

    elif query.data == 'help':
        text = (
            f"<b>{sc('commands')}</b>\n\n"
            f"/grab {sc('guess character')}\n"
            f"/fav {sc('set favorite')}\n"
            f"/harem {sc('view collection')}\n"
            f"/trade {sc('trade characters')}\n"
            f"/gift {sc('gift character')}\n"
            f"/bal {sc('check wallet')}\n"
            f"/pay {sc('send gold')}\n"
            f"/claim {sc('daily reward')}\n"
            f"/roll {sc('gamble gold')}\n"
        )
        keyboard = [[InlineKeyboardButton(sc("back"), callback_data='back')]]
        await query.edit_message_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    elif query.data == 'referral':
        link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
        count = user_data.get('referred_users', 0)
        earned = count * REFERRER_REWARD
        text = (
            f"<b>{sc('invite and earn')}</b>\n\n"
            f"{sc('invited')}: <b>{count}</b>\n"
            f"{sc('earned')}: <b>{earned:,}</b>\n\n"
            f"<code>{link}</code>"
        )
        keyboard = [
            [InlineKeyboardButton(sc("share"), url=f"https://t.me/share/url?url={link}")],
            [InlineKeyboardButton(sc("back"), callback_data='back')]
        ]
        await query.edit_message_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    elif query.data == 'back':
        # Go back to main panel
        balance = user_data.get('balance', 0)
        totals = await user_totals_collection.find_one({'id': user_id})
        chars = totals.get('count', 0) if totals else 0
        refs = user_data.get('referred_users', 0)
        caption = (
            f"<b>{sc('welcome back')}</b>\n\n"
            f"{sc('collect anime characters in groups')}\n\n"
            f"<b>{sc('your stats')}</b>\n"
            f"{sc('gold')}: <b>{balance:,}</b>\n"
            f"{sc('characters')}: <b>{chars}</b>\n"
            f"{sc('referrals')}: <b>{refs}</b>"
        )
        keyboard = [
            [InlineKeyboardButton(sc("add to group"), url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
            [
                InlineKeyboardButton(sc("support"), url=f'https://t.me/{SUPPORT_CHAT}'),
                InlineKeyboardButton(sc("updates"), url='https://t.me/PICK_X_UPDATE')
            ],
            [
                InlineKeyboardButton(sc("help"), callback_data='help'),
                InlineKeyboardButton(sc("invite"), callback_data='referral')
            ],
            [InlineKeyboardButton(sc("credits"), callback_data='credits')]
        ]
        await query.edit_message_caption(caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


# ------------------ HANDLER REGISTRATION ------------------
def register_start_handler():
    """Register /start and callback handlers"""
    start_handler = CommandHandler('start', start, block=False)
    callback_handler = CallbackQueryHandler(button_callback, block=False)

    application.add_handler(start_handler)
    application.add_handler(callback_handler)

    LOGGER.info("[START] Handlers registered successfully")


# Initialize on import
register_start_handler()