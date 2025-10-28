import random
from html import escape 

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler

from shivu import application, PHOTO_URL, SUPPORT_CHAT, UPDATE_CHAT, BOT_USERNAME, db, GROUP_ID, LOGGER
from shivu import user_collection, user_totals_collection


# Referral rewards configuration
REFERRER_REWARD = 1000  # Gold for person who invited
NEW_USER_BONUS = 500    # Gold for new user who joins


def to_small_caps(text):
    """Convert text to small caps"""
    small_caps_map = {
        'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ғ', 'g': 'ɢ', 'h': 'ʜ', 'i': 'ɪ',
        'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ',
        's': 's', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ',
        'A': 'ᴀ', 'B': 'ʙ', 'C': 'ᴄ', 'D': 'ᴅ', 'E': 'ᴇ', 'F': 'ғ', 'G': 'ɢ', 'H': 'ʜ', 'I': 'ɪ',
        'J': 'ᴊ', 'K': 'ᴋ', 'L': 'ʟ', 'M': 'ᴍ', 'N': 'ɴ', 'O': 'ᴏ', 'P': 'ᴘ', 'Q': 'ǫ', 'R': 'ʀ',
        'S': 's', 'T': 'ᴛ', 'U': 'ᴜ', 'V': 'ᴠ', 'W': 'ᴡ', 'X': 'x', 'Y': 'ʏ', 'Z': 'ᴢ'
    }
    return ''.join(small_caps_map.get(c, c) for c in text)


def is_video_url(url):
    """Check if URL is a video based on extension"""
    video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.m4v')
    return any(url.lower().endswith(ext) for ext in video_extensions)


async def send_media_with_caption(context, chat_id, media_url, caption, reply_markup):
    """Send photo or video based on URL type"""
    try:
        if is_video_url(media_url):
            await context.bot.send_video(
                chat_id=chat_id,
                video=media_url,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=media_url,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    except Exception as e:
        LOGGER.error(f"[MEDIA ERROR] Failed to send media: {e}")
        # Fallback to text message if media fails
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )


async def process_referral(user_id: int, first_name: str, referring_user_id: int, context: CallbackContext):
    """Process referral rewards for both users"""
    try:
        # Check if referring user exists
        referring_user = await user_collection.find_one({"id": referring_user_id})

        if not referring_user:
            LOGGER.warning(f"[REFERRAL] Referring user {referring_user_id} not found")
            return False

        # Check if user hasn't already been referred by someone
        new_user = await user_collection.find_one({"id": user_id})
        if new_user and new_user.get('referred_by'):
            LOGGER.info(f"[REFERRAL] User {user_id} already referred by someone")
            return False

        # Don't allow self-referral
        if user_id == referring_user_id:
            LOGGER.warning(f"[REFERRAL] Self-referral attempt by {user_id}")
            return False

        # Update new user - mark who referred them
        await user_collection.update_one(
            {"id": user_id},
            {
                "$set": {"referred_by": referring_user_id},
                "$inc": {"balance": NEW_USER_BONUS}
            }
        )

        # Update referring user - add to their referral list and rewards
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

        # Send notification to referrer
        referrer_first_name = referring_user.get('first_name', 'User')
        referrer_message = (
            f"╔═══════════════════╗\n"
            f"  {to_small_caps('referral success')}\n"
            f"╚═══════════════════╝\n\n"
            f"<b>{escape(first_name)}</b> {to_small_caps('joined using your link')}\n\n"
            f"<b>{to_small_caps('your rewards')}:</b>\n"
            f"💰 <code>{REFERRER_REWARD:,}</code> {to_small_caps('gold')}\n"
            f"✅ {to_small_caps('invite task progress')} +1\n\n"
            f"{to_small_caps('keep inviting to unlock more rewards')}"
        )

        try:
            await context.bot.send_message(
                chat_id=referring_user_id,
                text=referrer_message,
                parse_mode='HTML'
            )
        except Exception as e:
            LOGGER.error(f"[REFERRAL] Failed to notify referrer {referring_user_id}: {e}")

        LOGGER.info(f"[REFERRAL] User {user_id} referred by {referring_user_id}")
        return True

    except Exception as e:
        LOGGER.error(f"[REFERRAL ERROR] {e}")
        return False


async def start(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    username = update.effective_user.username
    args = context.args

    # Check for referral parameter
    referring_user_id = None
    if args and len(args) > 0 and args[0].startswith('r_'):
        try:
            referring_user_id = int(args[0][2:])
        except ValueError:
            LOGGER.warning(f"[START] Invalid referral code: {args[0]}")
            referring_user_id = None

    # Check if user exists
    user_data = await user_collection.find_one({"id": user_id})
    total_users = await user_collection.count_documents({})
    is_new_user = user_data is None

    if is_new_user:
        # Create new user with pass_data structure
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
                "tasks": {
                    "invites": 0,
                    "weekly_claims": 0,
                    "grabs": 0
                },
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

        # Process referral if valid
        if referring_user_id:
            referral_success = await process_referral(user_id, first_name, referring_user_id, context)

            if referral_success:
                # Update the new user data to reflect referral bonus
                user_data['balance'] = NEW_USER_BONUS
                user_data['referred_by'] = referring_user_id

        # Notify group about new user
        try:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=(
                    f"╔═══════════════════╗\n"
                    f"  {to_small_caps('new player')}\n"
                    f"╚═══════════════════╝\n\n"
                    f"{to_small_caps('user')}: <a href='tg://user?id={user_id}'>{escape(first_name)}</a>\n"
                    f"{to_small_caps('id')}: <code>{user_id}</code>\n"
                    f"{to_small_caps('total users')}: <b>{total_users + 1}</b>"
                ),
                parse_mode='HTML'
            )
        except Exception as e:
            LOGGER.error(f"[START] Failed to notify group: {e}")

    else:
        # Update existing user info if changed
        update_fields = {}
        if user_data.get('first_name') != first_name:
            update_fields['first_name'] = first_name
        if user_data.get('username') != username:
            update_fields['username'] = username

        # Ensure pass_data exists for old users
        if 'pass_data' not in user_data:
            update_fields['pass_data'] = {
                "tier": "free",
                "weekly_claims": 0,
                "last_weekly_claim": None,
                "streak_count": 0,
                "last_streak_claim": None,
                "tasks": {
                    "invites": 0,
                    "weekly_claims": 0,
                    "grabs": 0
                },
                "mythic_unlocked": False,
                "premium_expires": None,
                "elite_expires": None,
                "pending_elite_payment": None,
                "invited_users": [],
                "total_invite_earnings": 0
            }

        if update_fields:
            await user_collection.update_one(
                {"id": user_id},
                {"$set": update_fields}
            )
            # Refresh user data
            user_data = await user_collection.find_one({"id": user_id})

    # Get user stats
    user_balance = user_data.get('balance', 0)
    user_totals = await user_totals_collection.find_one({'id': user_id})
    total_characters = user_totals.get('count', 0) if user_totals else 0
    referred_count = user_data.get('referred_users', 0)

    # Generate referral link
    referral_link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"

    # Build caption
    if update.effective_chat.type == "private":
        welcome_msg = to_small_caps('welcome back') if not is_new_user else to_small_caps('welcome')
        bonus_msg = ""

        if is_new_user and referring_user_id:
            bonus_msg = f"\n\n🎁 {to_small_caps('bonus')}: <b>+{NEW_USER_BONUS}</b> {to_small_caps('gold for joining via referral')}"

        caption = f"""<b>{welcome_msg}</b>

{to_small_caps('hey pick catcher')}

{to_small_caps('i am pick catcher')}
{to_small_caps('i spawn anime characters in your groups and let users collect them')}
{to_small_caps('so what are you waiting for add me in your group by click on the below button')}

{to_small_caps('tap the help button for details')}

{to_small_caps('hit help to find out more about how to use me')}{bonus_msg}

━━━━━━━━━━━━━━━━━━━
<b>{to_small_caps('your stats')}</b>
━━━━━━━━━━━━━━━━━━━
💰 {to_small_caps('wallet')}: <b>{user_balance:,}</b> {to_small_caps('gold')}
🎴 {to_small_caps('characters')}: <b>{total_characters}</b>
👥 {to_small_caps('referrals')}: <b>{referred_count}</b>
"""

        keyboard = [
            [InlineKeyboardButton(to_small_caps("start guessing"), url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
            [
                InlineKeyboardButton(to_small_caps("support"), url=f'https://t.me/{SUPPORT_CHAT}'),
                InlineKeyboardButton(to_small_caps("channel"), url=f'https://t.me/PICK_X_UPDATE')
            ],
            [InlineKeyboardButton(to_small_caps("help"), callback_data='help')],
            [InlineKeyboardButton(to_small_caps("referral"), callback_data='referral')],
            [InlineKeyboardButton(to_small_caps("credits"), callback_data='credits')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        media_url = random.choice(PHOTO_URL)

        await send_media_with_caption(
            context=context,
            chat_id=update.effective_chat.id,
            media_url=media_url,
            caption=caption,
            reply_markup=reply_markup
        )

    else:
        # Group message
        media_url = random.choice(PHOTO_URL)
        caption = f"<b>{to_small_caps('alive')}</b>\n\n{to_small_caps('connect to me in pm for more information')}"

        keyboard = [
            [InlineKeyboardButton(to_small_caps("start guessing"), url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
            [
                InlineKeyboardButton(to_small_caps("support"), url=f'https://t.me/{SUPPORT_CHAT}'),
                InlineKeyboardButton(to_small_caps("channel"), url=f'https://t.me/PICK_X_UPDATE')
            ],
            [InlineKeyboardButton(to_small_caps("help"), callback_data='help')],
            [InlineKeyboardButton(to_small_caps("credits"), callback_data='credits')]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await send_media_with_caption(
            context=context,
            chat_id=update.effective_chat.id,
            media_url=media_url,
            caption=caption,
            reply_markup=reply_markup
        )


async def button_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_data = await user_collection.find_one({"id": user_id})

    if not user_data:
        await query.answer(to_small_caps("please start the bot first"), show_alert=True)
        return

    user_totals = await user_totals_collection.find_one({'id': user_id})

    if query.data == 'help':
        help_text = f"""╔═══════════════════╗
  {to_small_caps('help section')}
╚═══════════════════╝

<b>{to_small_caps('gameplay commands')}</b>
/grab - {to_small_caps('to guess character only works in group')}
/fav - {to_small_caps('add your fav')}
/harem - {to_small_caps('to see your collection')}

<b>{to_small_caps('trading commands')}</b>
/trade - {to_small_caps('to trade characters')}
/gift - {to_small_caps('give any character from your collection to another user only works in groups')}

<b>{to_small_caps('leaderboard commands')}</b>
/gstop - {to_small_caps('see top groups ppl guesses most in that groups')}
/tophunters - {to_small_caps('to see top users')}
/ctop - {to_small_caps('your chat top adding soon')}

<b>{to_small_caps('settings commands')}</b>
/changetime - {to_small_caps('change character appear time only works in groups')}

<b>{to_small_caps('economy commands')}</b>
/bal - {to_small_caps('check wallet')}
/pay - {to_small_caps('send gold')}
/claim - {to_small_caps('daily reward')}
/roll - {to_small_caps('gamble gold')}

<b>{to_small_caps('pass system')}</b>
/pass - {to_small_caps('view pass status')}
/pclaim - {to_small_caps('claim weekly rewards')}
/tasks - {to_small_caps('view task progress')}
"""
        help_keyboard = [[InlineKeyboardButton(to_small_caps("back"), callback_data='back')]]
        reply_markup = InlineKeyboardMarkup(help_keyboard)

        await query.edit_message_caption(
            caption=help_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    elif query.data == 'referral':
        referral_link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
        referred_count = user_data.get('referred_users', 0)
        total_earnings = referred_count * REFERRER_REWARD

        referral_text = f"""╔═══════════════════╗
  {to_small_caps('invite program')}
╚═══════════════════╝

<b>{to_small_caps('your stats')}</b>
👥 {to_small_caps('referrals')}: <b>{referred_count}</b>
💰 {to_small_caps('earned')}: <b>{total_earnings:,}</b> {to_small_caps('gold')}

━━━━━━━━━━━━━━━━━━━
<b>{to_small_caps('how to invite')}</b>
━━━━━━━━━━━━━━━━━━━
1️⃣ {to_small_caps('copy link below')}
2️⃣ {to_small_caps('share with friends')}
3️⃣ {to_small_caps('they click and start bot')}
4️⃣ {to_small_caps('instant rewards')}

━━━━━━━━━━━━━━━━━━━
<b>{to_small_caps('reward breakdown')}</b>
━━━━━━━━━━━━━━━━━━━
💎 {to_small_caps('you get')}: <b>{REFERRER_REWARD:,}</b> {to_small_caps('gold')}
🎁 {to_small_caps('friend gets')}: <b>{NEW_USER_BONUS:,}</b> {to_small_caps('gold')}
✅ {to_small_caps('counts toward pass tasks')}

━━━━━━━━━━━━━━━━━━━
<b>{to_small_caps('your invite link')}</b>
━━━━━━━━━━━━━━━━━━━
<code>{referral_link}</code>

{to_small_caps('tap to copy link')}
"""
        referral_keyboard = [
            [InlineKeyboardButton(to_small_caps("share link"), url=f"https://t.me/share/url?url={referral_link}")],
            [InlineKeyboardButton(to_small_caps("back"), callback_data='back')]
        ]
        reply_markup = InlineKeyboardMarkup(referral_keyboard)

        await query.edit_message_caption(
            caption=referral_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    elif query.data == 'credits':
        credits_text = f"""╔═══════════════════╗
  {to_small_caps('credits')}
╚═══════════════════╝

{to_small_caps('this bot was created and maintained by our dedicated team')}

{to_small_caps('special thanks to all contributors and users who made this project possible')}

{to_small_caps('tap below to see owner and sudo users')}
"""
        credits_keyboard = [
            [InlineKeyboardButton(to_small_caps("owner"), callback_data='owner')],
            [InlineKeyboardButton(to_small_caps("sudo users"), callback_data='sudo')],
            [InlineKeyboardButton(to_small_caps("back"), callback_data='back')]
        ]
        reply_markup = InlineKeyboardMarkup(credits_keyboard)

        await query.edit_message_caption(
            caption=credits_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    elif query.data == 'sudo':
        sudo_text = f"""╔═══════════════════╗
  {to_small_caps('sudo users')}
╚═══════════════════╝

{to_small_caps('these are the sudo users who help manage this bot')}

{to_small_caps('tap on their names to contact them')}
"""
        sudo_keyboard = [
            [InlineKeyboardButton("参┊ＹＯＩＣＨＩ→ ＩＳＡＧＩএ", url='https://t.me/ll_Yoichi_Isagi_ll')],
            [InlineKeyboardButton("꧁ღ⊱✨Kaizen ✨⊱ღ꧂", url='https://t.me/digital_paradoxx')],
            [InlineKeyboardButton("ｋｉｌｌｕａ", url='https://t.me/notkilluafr')],
            [InlineKeyboardButton("─°✧Sʜ༏ᵏ༏ɱⲟɾ༏♡︎³↳°─⋆", url='https://t.me/avinashs_sun')],
            [InlineKeyboardButton(to_small_caps("back to credits"), callback_data='credits')]
        ]
        reply_markup = InlineKeyboardMarkup(sudo_keyboard)

        await query.edit_message_caption(
            caption=sudo_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    elif query.data == 'owner':
        owner_text = f"""╔═══════════════════╗
  {to_small_caps('owner')}
╚═══════════════════╝

{to_small_caps('the owner of this bot is')}

{to_small_caps('tap on the button below to contact the owner')}
"""
        owner_keyboard = [
            [InlineKeyboardButton("々 Ꭲʜᴏʀꜰɪɴɴ ⸙", url='https://t.me/ll_Thorfinn_ll')],
            [InlineKeyboardButton(to_small_caps("back to credits"), callback_data='credits')]
        ]
        reply_markup = InlineKeyboardMarkup(owner_keyboard)

        await query.edit_message_caption(
            caption=owner_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    elif query.data == 'back':
        user_balance = user_data.get('balance', 0)
        total_characters = user_totals.get('count', 0) if user_totals else 0
        referred_count = user_data.get('referred_users', 0)

        caption = f"""<b>{to_small_caps('hallo')}</b>

{to_small_caps('hey pick catcher')}

{to_small_caps('i am pick catcher')}
{to_small_caps('i spawn anime characters in your groups and let users collect them')}
{to_small_caps('so what are you waiting for add me in your group by click on the below button')}

{to_small_caps('tap the help button for details')}

{to_small_caps('hit help to find out more about how to use me')}

━━━━━━━━━━━━━━━━━━━
<b>{to_small_caps('your stats')}</b>
━━━━━━━━━━━━━━━━━━━
💰 {to_small_caps('wallet')}: <b>{user_balance:,}</b> {to_small_caps('gold')}
🎴 {to_small_caps('characters')}: <b>{total_characters}</b>
👥 {to_small_caps('referrals')}: <b>{referred_count}</b>
"""

        keyboard = [
            [InlineKeyboardButton(to_small_caps("start guessing"), url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
            [
                InlineKeyboardButton(to_small_caps("support"), url=f'https://t.me/{SUPPORT_CHAT}'),
                InlineKeyboardButton(to_small_caps("channel"), url=f'https://t.me/PICK_X_UPDATE')
            ],
            [InlineKeyboardButton(to_small_caps("help"), callback_data='help')],
            [InlineKeyboardButton(to_small_caps("referral"), callback_data='referral')],
            [InlineKeyboardButton(to_small_caps("credits"), callback_data='credits')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_caption(
            caption=caption,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )


# Register handlers
start_handler = CommandHandler('start', start, block=False)
application.add_handler(start_handler)

callback_handler = CallbackQueryHandler(button_callback, block=False)
application.add_handler(callback_handler)

LOGGER.info("[START] Referral system handlers registered")