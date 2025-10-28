import random
import re
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler

from shivu import (
    application, SUPPORT_CHAT, BOT_USERNAME, db, GROUP_ID, LOGGER,
    user_collection, user_totals_collection
)

PHOTO_URL = [
    "https://files.catbox.moe/8722ku.jpeg",
    "https://files.catbox.moe/kgcrnb.jpeg"
]

REFERRER_REWARD = 1000
NEW_USER_BONUS = 500


def to_small_caps(text):
    """Convert text to small caps"""
    small_caps_map = {
        'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ғ', 'g': 'ɢ', 
        'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 
        'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ', 's': 's', 't': 'ᴛ', 'u': 'ᴜ', 
        'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ',
        'A': 'ᴀ', 'B': 'ʙ', 'C': 'ᴄ', 'D': 'ᴅ', 'E': 'ᴇ', 'F': 'ғ', 'G': 'ɢ', 
        'H': 'ʜ', 'I': 'ɪ', 'J': 'ᴊ', 'K': 'ᴋ', 'L': 'ʟ', 'M': 'ᴍ', 'N': 'ɴ', 
        'O': 'ᴏ', 'P': 'ᴘ', 'Q': 'ǫ', 'R': 'ʀ', 'S': 's', 'T': 'ᴛ', 'U': 'ᴜ', 
        'V': 'ᴠ', 'W': 'ᴡ', 'X': 'x', 'Y': 'ʏ', 'Z': 'ᴢ'
    }
    return ''.join(small_caps_map.get(c, c) for c in text)


async def process_referral(user_id: int, first_name: str, referring_user_id: int, context: CallbackContext):
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

        referrer_message = (
            f"╔═══════════════╗\n"
            f"  {to_small_caps('referral success')}\n"
            f"╚═══════════════╝\n\n"
            f"<b>{escape(first_name)}</b> {to_small_caps('joined via your link')}\n\n"
            f"💰 <code>{REFERRER_REWARD:,}</code> {to_small_caps('gold')}\n"
            f"✅ {to_small_caps('invite task')} +1"
        )

        try:
            await context.bot.send_message(
                chat_id=referring_user_id,
                text=referrer_message,
                parse_mode='HTML'
            )
        except Exception as e:
            LOGGER.error(f"Failed to notify referrer: {e}")

        return True

    except Exception as e:
        LOGGER.error(f"Referral error: {e}")
        return False


async def start(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    username = update.effective_user.username
    args = context.args

    referring_user_id = None
    if args and args[0].startswith('r_'):
        try:
            referring_user_id = int(args[0][2:])
        except ValueError:
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
            referral_success = await process_referral(user_id, first_name, referring_user_id, context)
            if referral_success:
                user_data['balance'] = NEW_USER_BONUS
                user_data['referred_by'] = referring_user_id

        try:
            total_users = await user_collection.count_documents({})
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=(
                    f"╔═══════════════╗\n"
                    f"  {to_small_caps('new player')}\n"
                    f"╚═══════════════╝\n\n"
                    f"{to_small_caps('user')}: <a href='tg://user?id={user_id}'>{escape(first_name)}</a>\n"
                    f"{to_small_caps('id')}: <code>{user_id}</code>\n"
                    f"{to_small_caps('total')}: <b>{total_users}</b>"
                ),
                parse_mode='HTML'
            )
        except Exception as e:
            LOGGER.error(f"Group notify failed: {e}")

    else:
        update_fields = {}
        if user_data.get('first_name') != first_name:
            update_fields['first_name'] = first_name
        if user_data.get('username') != username:
            update_fields['username'] = username

        if 'pass_data' not in user_data:
            update_fields['pass_data'] = {
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

        if update_fields:
            await user_collection.update_one({"id": user_id}, {"$set": update_fields})
            user_data = await user_collection.find_one({"id": user_id})

    user_balance = user_data.get('balance', 0)
    user_totals = await user_totals_collection.find_one({'id': user_id})
    total_characters = user_totals.get('count', 0) if user_totals else 0
    referred_count = user_data.get('referred_users', 0)

    if update.effective_chat.type == "private":
        welcome = to_small_caps('welcome back') if not is_new_user else to_small_caps('welcome')
        bonus_msg = ""

        if is_new_user and referring_user_id:
            bonus_msg = f"\n🎁 <b>+{NEW_USER_BONUS}</b> {to_small_caps('gold bonus')}"

        caption = (
            f"<b>{welcome}</b>\n\n"
            f"{to_small_caps('collect anime characters in groups')}\n"
            f"{to_small_caps('add me to your group to start')}{bonus_msg}\n\n"
            f"━━━━━━━━━━━━\n"
            f"💰 {to_small_caps('gold')}: <b>{user_balance:,}</b>\n"
            f"🎴 {to_small_caps('characters')}: <b>{total_characters}</b>\n"
            f"👥 {to_small_caps('referrals')}: <b>{referred_count}</b>"
        )

        keyboard = [
            [InlineKeyboardButton(to_small_caps("add to group"), url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
            [
                InlineKeyboardButton(to_small_caps("support"), url=f'https://t.me/{SUPPORT_CHAT}'),
                InlineKeyboardButton(to_small_caps("updates"), url=f'https://t.me/PICK_X_UPDATE')
            ],
            [
                InlineKeyboardButton(to_small_caps("help"), callback_data='help'),
                InlineKeyboardButton(to_small_caps("invite"), callback_data='referral')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=random.choice(PHOTO_URL),
            caption=caption,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    else:
        caption = f"<b>{to_small_caps('alive')}</b>\n{to_small_caps('pm me for details')}"

        keyboard = [
            [InlineKeyboardButton(to_small_caps("add to group"), url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
            [
                InlineKeyboardButton(to_small_caps("support"), url=f'https://t.me/{SUPPORT_CHAT}'),
                InlineKeyboardButton(to_small_caps("updates"), url=f'https://t.me/PICK_X_UPDATE')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=random.choice(PHOTO_URL),
            caption=caption,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )


async def button_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_data = await user_collection.find_one({"id": user_id})

    if not user_data:
        await query.answer(to_small_caps("start bot first"), show_alert=True)
        return

    if query.data == 'help':
        help_text = (
            f"╔═══════════════╗\n"
            f"  {to_small_caps('commands')}\n"
            f"╚═══════════════╝\n\n"
            f"<b>{to_small_caps('gameplay')}</b>\n"
            f"/grab - {to_small_caps('guess character')}\n"
            f"/fav - {to_small_caps('set favorite')}\n"
            f"/harem - {to_small_caps('view collection')}\n\n"
            f"<b>{to_small_caps('trading')}</b>\n"
            f"/trade - {to_small_caps('trade characters')}\n"
            f"/gift - {to_small_caps('gift character')}\n\n"
            f"<b>{to_small_caps('leaderboard')}</b>\n"
            f"/gstop - {to_small_caps('top groups')}\n"
            f"/tophunters - {to_small_caps('top users')}\n\n"
            f"<b>{to_small_caps('economy')}</b>\n"
            f"/bal - {to_small_caps('check wallet')}\n"
            f"/pay - {to_small_caps('send gold')}\n"
            f"/claim - {to_small_caps('daily reward')}\n"
            f"/roll - {to_small_caps('gamble gold')}\n\n"
            f"<b>{to_small_caps('pass system')}</b>\n"
            f"/pass - {to_small_caps('pass status')}\n"
            f"/pclaim - {to_small_caps('weekly rewards')}\n"
            f"/tasks - {to_small_caps('task progress')}"
        )

        keyboard = [[InlineKeyboardButton(to_small_caps("back"), callback_data='back')]]
        await query.edit_message_caption(
            caption=help_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    elif query.data == 'referral':
        referral_link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
        referred_count = user_data.get('referred_users', 0)
        total_earnings = referred_count * REFERRER_REWARD

        referral_text = (
            f"╔═══════════════╗\n"
            f"  {to_small_caps('invite & earn')}\n"
            f"╚═══════════════╝\n\n"
            f"👥 {to_small_caps('invited')}: <b>{referred_count}</b>\n"
            f"💰 {to_small_caps('earned')}: <b>{total_earnings:,}</b>\n\n"
            f"━━━━━━━━━━━━\n"
            f"<b>{to_small_caps('rewards')}</b>\n"
            f"━━━━━━━━━━━━\n"
            f"💎 {to_small_caps('you')}: <b>{REFERRER_REWARD:,}</b> {to_small_caps('gold')}\n"
            f"🎁 {to_small_caps('friend')}: <b>{NEW_USER_BONUS:,}</b> {to_small_caps('gold')}\n"
            f"✅ {to_small_caps('counts for pass tasks')}\n\n"
            f"<b>{to_small_caps('your link')}</b>\n"
            f"<code>{referral_link}</code>"
        )

        keyboard = [
            [InlineKeyboardButton(to_small_caps("share"), url=f"https://t.me/share/url?url={referral_link}")],
            [InlineKeyboardButton(to_small_caps("back"), callback_data='back')]
        ]
        await query.edit_message_caption(
            caption=referral_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    elif query.data == 'back':
        user_balance = user_data.get('balance', 0)
        user_totals = await user_totals_collection.find_one({'id': user_id})
        total_characters = user_totals.get('count', 0) if user_totals else 0
        referred_count = user_data.get('referred_users', 0)

        caption = (
            f"<b>{to_small_caps('welcome back')}</b>\n\n"
            f"{to_small_caps('collect anime characters in groups')}\n"
            f"{to_small_caps('add me to your group to start')}\n\n"
            f"━━━━━━━━━━━━\n"
            f"💰 {to_small_caps('gold')}: <b>{user_balance:,}</b>\n"
            f"🎴 {to_small_caps('characters')}: <b>{total_characters}</b>\n"
            f"👥 {to_small_caps('referrals')}: <b>{referred_count}</b>"
        )

        keyboard = [
            [InlineKeyboardButton(to_small_caps("add to group"), url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
            [
                InlineKeyboardButton(to_small_caps("support"), url=f'https://t.me/{SUPPORT_CHAT}'),
                InlineKeyboardButton(to_small_caps("updates"), url=f'https://t.me/PICK_X_UPDATE')
            ],
            [
                InlineKeyboardButton(to_small_caps("help"), callback_data='help'),
                InlineKeyboardButton(to_small_caps("invite"), callback_data='referral')
            ]
        ]
        await query.edit_message_caption(
            caption=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )


application.add_handler(CommandHandler('start', start, block=False))
application.add_handler(CallbackQueryHandler(button_callback, block=False))