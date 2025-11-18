import random
from shivu.modules.database.sudo import fetch_sudo_users
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from shivu import application, SUPPORT_CHAT, BOT_USERNAME, LOGGER, user_collection, user_totals_collection
from shivu.modules.chatlog import track_bot_start

PHOTOS = ["https://files.catbox.moe/k3dhbe.mp4"]
REFERRER_REWARD = 1000
NEW_USER_BONUS = 500
OWNERS = [{"name": "Thorfinn", "username": "ll_Thorfinn_ll"}]
PARTNER_BOT_LINK = "https://t.me/Siyaprobot?start=_tgr_6Nl2njExN2Rl"

async def process_referral(user_id, first_name, referring_user_id, context):
    try:
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
        
        msg = f"""<b>Referral Confirmed</b>

New user <b>{escape(first_name)}</b> has joined through your referral link.

<b>Earned:</b> {REFERRER_REWARD:,} gold
<b>Progress:</b> Task completed +1

Continue sharing your link to earn more rewards."""
        
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
        await track_bot_start(user_id, first_name, username, is_new_user)
        if referring_user_id:
            await process_referral(user_id, first_name, referring_user_id, context)
    else:
        await track_bot_start(user_id, first_name, username, is_new_user)
    
    balance = user_data.get('balance', 0)
    totals = await user_totals_collection.find_one({'id': user_id})
    chars = totals.get('count', 0) if totals else 0
    refs = user_data.get('referred_users', 0)
    tier = user_data.get('pass_data', {}).get('tier', 'free').title()
    
    welcome_msg = "Welcome to Pick Catcher" if is_new_user else f"Welcome back, {first_name}"
    bonus_msg = f"\n\nYou've received a referral bonus of {NEW_USER_BONUS} gold." if (is_new_user and referring_user_id) else ""
    
    caption = f"""<b>{welcome_msg}</b>

Pick Catcher is an anime character collection bot. Add me to your group to start collecting rare characters, trade with other users, and build your ultimate collection.{bonus_msg}

<b>Account Overview</b>

Membership: {tier}
Balance: {balance:,} gold
Collection: {chars} characters
Referrals: {refs} users"""
    
    keyboard = [
        [InlineKeyboardButton("Add to Group", url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
        [InlineKeyboardButton("Try Our Partner Bot - Siyapro", url=PARTNER_BOT_LINK)],
        [
            InlineKeyboardButton("Support", url=f'https://t.me/{SUPPORT_CHAT}'),
            InlineKeyboardButton("Updates", url='https://t.me/PICK_X_UPDATE')
        ],
        [
            InlineKeyboardButton("Commands", callback_data='help'),
            InlineKeyboardButton("Statistics", callback_data='stats')
        ],
        [
            InlineKeyboardButton("Referral Program", callback_data='referral'),
            InlineKeyboardButton("Membership", callback_data='pass_info')
        ],
        [InlineKeyboardButton("About", callback_data='credits')]
    ]
    
    try:
        await update.message.reply_text(
            text=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML',
            disable_web_page_preview=False
        )
    except Exception as e:
        LOGGER.error(f"Start error: {e}")

async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = await user_collection.find_one({"id": user_id})
    
    if not user_data:
        await query.answer("Please start the bot first using /start", show_alert=True)
        return
    
    if query.data == 'credits':
        text = f"""<b>About Pick Catcher</b>

Pick Catcher is developed and maintained by a dedicated team committed to providing the best anime character collection experience.

<b>Development Team</b>"""
        buttons = []
        if OWNERS:
            for owner in OWNERS:
                buttons.append([InlineKeyboardButton(f"{owner['name']} - Owner", url=f"https://t.me/{owner['username']}")])
        
        try:
            sudo_users_db = await fetch_sudo_users()
            if sudo_users_db:
                text += "\n\n<b>Support Team</b>"
                for sudo in sudo_users_db:
                    sudo_title = sudo.get('sudo_title', 'Support Staff')
                    sudo_username = sudo.get('username', '')
                    if sudo_username:
                        buttons.append([InlineKeyboardButton(f"{sudo_title}", url=f"https://t.me/{sudo_username}")])
        except Exception as e:
            LOGGER.error(f"Error fetching sudo users: {e}")
        
        buttons.append([InlineKeyboardButton("Back", callback_data='back')])
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode='HTML', disable_web_page_preview=False)
    
    elif query.data == 'help':
        text = f"""<b>Available Commands</b>

<b>Character Management</b>
/grab - Identify and collect spawned characters
/fav - Set your favorite character for display
/harem - Browse your character collection

<b>Economy</b>
/balance - View your current gold balance
/pay - Transfer gold to another user
/claim - Collect your daily reward
/roll - Participate in gold gambling

<b>Trading</b>
/trade - Initiate a character trade
/gift - Send a character to another user

<b>Leaderboards</b>
/top - View global rankings

Use these commands in groups where the bot is added. For detailed information about any command, use /help followed by the command name.

<b>Recommended:</b> Check out our partner bot for more features."""
        keyboard = [
            [InlineKeyboardButton("Try Siyapro Bot", url=PARTNER_BOT_LINK)],
            [InlineKeyboardButton("Back", callback_data='back')]
        ]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)
    
    elif query.data == 'stats':
        balance = user_data.get('balance', 0)
        totals = await user_totals_collection.find_one({'id': user_id})
        chars = totals.get('count', 0) if totals else 0
        refs = user_data.get('referred_users', 0)
        pass_data = user_data.get('pass_data', {})
        tier = pass_data.get('tier', 'free').title()
        weekly_claims = pass_data.get('weekly_claims', 0)
        streak = pass_data.get('streak_count', 0)
        total_invited_earnings = pass_data.get('total_invite_earnings', 0)
        
        text = f"""<b>Account Statistics</b>

<b>Financial Overview</b>
Current Balance: {balance:,} gold
Referral Earnings: {total_invited_earnings:,} gold

<b>Collection Progress</b>
Total Characters: {chars}
Weekly Claims: {weekly_claims}

<b>Achievements</b>
Daily Streak: {streak} days
Total Referrals: {refs} users
Membership Tier: {tier}"""
        keyboard = [[InlineKeyboardButton("Back", callback_data='back')]]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)
    
    elif query.data == 'referral':
        link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
        count = user_data.get('referred_users', 0)
        earned = count * REFERRER_REWARD
        
        text = f"""<b>Referral Program</b>

Earn rewards by inviting new users to Pick Catcher. Share your unique referral link and receive gold for each successful registration.

<b>Reward Structure</b>
Your reward per referral: {REFERRER_REWARD:,} gold
New user signup bonus: {NEW_USER_BONUS:,} gold

<b>Your Performance</b>
Total referrals: {count} users
Total earned: {earned:,} gold

<b>Your Referral Link</b>
{link}

Share this link with friends to start earning rewards immediately."""
        keyboard = [
            [InlineKeyboardButton("Share Link", url=f"https://t.me/share/url?url={link}")],
            [InlineKeyboardButton("Back", callback_data='back')]
        ]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)
    
    elif query.data == 'pass_info':
        tier = user_data.get('pass_data', {}).get('tier', 'free').title()
        text = f"""<b>Membership Tiers</b>

Current tier: {tier}

<b>Free Membership</b>
Access to basic features
Standard reward rates
Community support

<b>Premium Membership</b>
2x daily reward multiplier
Access to exclusive characters
Priority customer support
Enhanced trading options

<b>Elite Membership</b>
3x daily reward multiplier
Mythic character collection unlocked
Custom profile customization
VIP event access
Dedicated support channel

To upgrade your membership, please contact our support team for pricing and payment options."""
        keyboard = [
            [InlineKeyboardButton("Contact Support", url=f'https://t.me/{SUPPORT_CHAT}')],
            [InlineKeyboardButton("Back", callback_data='back')]
        ]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)
    
    elif query.data == 'back':
        balance = user_data.get('balance', 0)
        totals = await user_totals_collection.find_one({'id': user_id})
        chars = totals.get('count', 0) if totals else 0
        refs = user_data.get('referred_users', 0)
        tier = user_data.get('pass_data', {}).get('tier', 'free').title()
        first_name = query.from_user.first_name
        
        caption = f"""<b>Welcome back, {first_name}</b>

Pick Catcher is an anime character collection bot. Add me to your group to start collecting rare characters, trade with other users, and build your ultimate collection.

<b>Account Overview</b>

Membership: {tier}
Balance: {balance:,} gold
Collection: {chars} characters
Referrals: {refs} users"""
        keyboard = [
            [InlineKeyboardButton("Add to Group", url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
            [InlineKeyboardButton("Try Our Partner Bot - Siyapro", url=PARTNER_BOT_LINK)],
            [
                InlineKeyboardButton("Support", url=f'https://t.me/{SUPPORT_CHAT}'),
                InlineKeyboardButton("Updates", url='https://t.me/PICK_X_UPDATE')
            ],
            [
                InlineKeyboardButton("Commands", callback_data='help'),
                InlineKeyboardButton("Statistics", callback_data='stats')
            ],
            [
                InlineKeyboardButton("Referral Program", callback_data='referral'),
                InlineKeyboardButton("Membership", callback_data='pass_info')
            ],
            [InlineKeyboardButton("About", callback_data='credits')]
        ]
        await query.edit_message_text(text=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)

application.add_handler(CommandHandler('start', start, block=False))
application.add_handler(CallbackQueryHandler(button_callback, pattern='^(help|stats|referral|pass_info|credits|back)$', block=False))