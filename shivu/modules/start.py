import random
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from telegram.error import BadRequest

from shivu import (
    application, SUPPORT_CHAT, BOT_USERNAME, GROUP_ID, LOGGER,
    user_collection, user_totals_collection
)

PHOTO_URL = [
    "https://files.catbox.moe/8722ku.jpeg",
    "https://files.catbox.moe/kgcrnb.jpeg"
]

REFERRER_REWARD = 1000
NEW_USER_BONUS = 500


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


async def process_referral(user_id, first_name, referring_user_id, context):
    """Process referral rewards"""
    try:
        referring_user = await user_collection.find_one({"id": referring_user_id})
        if not referring_user:
            return False

        new_user = await user_collection.find_one({"id": user_id})
        if new_user and new_user.get('referred_by'):
            return False

        if user_id == referring_user_id:
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
        except:
            pass

        return True
    except Exception as e:
        LOGGER.error(f"Referral error: {e}")
        return False


async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    username = update.effective_user.username
    args = context.args

    referring_user_id = None
    if args and args[0].startswith('r_'):
        try:
            referring_user_id = int(args[0][2:])
        except:
            pass

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

        if referring_user_id:
            success = await process_referral(user_id, first_name, referring_user_id, context)
            if success:
                user_data['balance'] = NEW_USER_BONUS
                user_data['referred_by'] = referring_user_id

        try:
            total = await user_collection.count_documents({})
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=(
                    f"<b>{sc('new player')}</b>\n\n"
                    f"{sc('user')}: <a href='tg://user?id={user_id}'>{escape(first_name)}</a>\n"
                    f"{sc('id')}: <code>{user_id}</code>\n"
                    f"{sc('total')}: {total}"
                ),
                parse_mode='HTML'
            )
        except:
            pass
    else:
        updates = {}
        if user_data.get('first_name') != first_name:
            updates['first_name'] = first_name
        if user_data.get('username') != username:
            updates['username'] = username
        if 'pass_data' not in user_data:
            updates['pass_data'] = {
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
        if updates:
            await user_collection.update_one({"id": user_id}, {"$set": updates})
            user_data = await user_collection.find_one({"id": user_id})

    balance = user_data.get('balance', 0)
    totals = await user_totals_collection.find_one({'id': user_id})
    chars = totals.get('count', 0) if totals else 0
    refs = user_data.get('referred_users', 0)

    if update.effective_chat.type == "private":
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
            ]
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
            LOGGER.error(f"Photo send failed: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
    else:
        caption = f"<b>{sc('alive')}</b>\n{sc('pm me for details')}"

        keyboard = [
            [InlineKeyboardButton(sc("add to group"), url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
            [
                InlineKeyboardButton(sc("support"), url=f'https://t.me/{SUPPORT_CHAT}'),
                InlineKeyboardButton(sc("updates"), url='https://t.me/PICK_X_UPDATE')
            ]
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
            LOGGER.error(f"Photo send failed: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )


async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_data = await user_collection.find_one({"id": user_id})

    if not user_data:
        await query.answer(sc("start bot first"), show_alert=True)
        return

    if query.data == 'help':
        text = (
            f"<b>{sc('commands')}</b>\n\n"
            f"<b>{sc('gameplay')}</b>\n"
            f"/grab {sc('guess character')}\n"
            f"/fav {sc('set favorite')}\n"
            f"/harem {sc('view collection')}\n\n"
            f"<b>{sc('trading')}</b>\n"
            f"/trade {sc('trade characters')}\n"
            f"/gift {sc('gift character')}\n\n"
            f"<b>{sc('leaderboard')}</b>\n"
            f"/gstop {sc('top groups')}\n"
            f"/tophunters {sc('top users')}\n\n"
            f"<b>{sc('economy')}</b>\n"
            f"/bal {sc('check wallet')}\n"
            f"/pay {sc('send gold')}\n"
            f"/claim {sc('daily reward')}\n"
            f"/roll {sc('gamble gold')}\n\n"
            f"<b>{sc('pass system')}</b>\n"
            f"/pass {sc('pass status')}\n"
            f"/pclaim {sc('weekly rewards')}\n"
            f"/tasks {sc('task progress')}"
        )

        keyboard = [[InlineKeyboardButton(sc("back"), callback_data='back')]]
        
        try:
            await query.edit_message_caption(
                caption=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
        except BadRequest:
            await query.message.edit_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )

    elif query.data == 'referral':
        link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
        count = user_data.get('referred_users', 0)
        earned = count * REFERRER_REWARD

        text = (
            f"<b>{sc('invite and earn')}</b>\n\n"
            f"{sc('invited')}: <b>{count}</b>\n"
            f"{sc('earned')}: <b>{earned:,}</b>\n\n"
            f"<b>{sc('rewards')}</b>\n"
            f"{sc('you')}: <b>{REFERRER_REWARD:,}</b> {sc('gold')}\n"
            f"{sc('friend')}: <b>{NEW_USER_BONUS:,}</b> {sc('gold')}\n"
            f"{sc('counts for pass tasks')}\n\n"
            f"<b>{sc('your link')}</b>\n"
            f"<code>{link}</code>"
        )

        keyboard = [
            [InlineKeyboardButton(sc("share"), url=f"https://t.me/share/url?url={link}")],
            [InlineKeyboardButton(sc("back"), callback_data='back')]
        ]
        
        try:
            await query.edit_message_caption(
                caption=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
        except BadRequest:
            await query.message.edit_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )

    elif query.data == 'back':
        balance = user_data.get('balance', 0)
        totals = await user_totals_collection.find_one({'id': user_id})
        chars = totals.get('count', 0) if totals else 0
        refs = user_data.get('referred_users', 0)

        caption = (
            f"<b>{sc('welcome back')}</b>\n\n"
            f"{sc('collect anime characters in groups')}\n"
            f"{sc('add me to start')}\n\n"
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
            ]
        ]
        
        try:
            await query.edit_message_caption(
                caption=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
        except BadRequest:
            await query.message.edit_text(
                text=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )


application.add_handler(CommandHandler('start', start, block=False))
application.add_handler(CallbackQueryHandler(button_callback, block=False))