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
PARTNER_BOT = "https://t.me/Siyaprobot?start=_tgr_6Nl2njExN2Rl"

async def process_referral(user_id, first_name, referring_user_id, context):
    try:
        if user_id == referring_user_id:
            return False
        
        referring_user = await user_collection.find_one({"id": referring_user_id}, {"id": 1})
        if not referring_user:
            return False
        
        new_user = await user_collection.find_one({"id": user_id}, {"referred_by": 1})
        if new_user and new_user.get('referred_by'):
            return False
        
        await user_collection.bulk_write([
            {"updateOne": {
                "filter": {"id": user_id},
                "update": {"$set": {"referred_by": referring_user_id}, "$inc": {"balance": NEW_USER_BONUS}}
            }},
            {"updateOne": {
                "filter": {"id": referring_user_id},
                "update": {
                    "$inc": {
                        "balance": REFERRER_REWARD,
                        "referred_users": 1,
                        "pass_data.tasks.invites": 1,
                        "pass_data.total_invite_earnings": REFERRER_REWARD
                    },
                    "$push": {"invited_user_ids": user_id}
                }
            }}
        ])
        
        msg = f"<b>Referral Confirmed</b>\n\nNew user <b>{escape(first_name)}</b> joined via your link.\n\n<b>Earned:</b> {REFERRER_REWARD:,} gold\n<b>Progress:</b> +1 task"
        
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
        context.application.create_task(track_bot_start(user_id, first_name, username, is_new_user))
        if referring_user_id:
            context.application.create_task(process_referral(user_id, first_name, referring_user_id, context))
    else:
        context.application.create_task(track_bot_start(user_id, first_name, username, is_new_user))
    
    balance = user_data.get('balance', 0)
    chars = 0
    refs = user_data.get('referred_users', 0)
    tier = user_data.get('pass_data', {}).get('tier', 'free').title()
    
    welcome_msg = "Welcome to Pick Catcher" if is_new_user else f"Welcome back, {first_name}"
    bonus_msg = f"\n\nReferral bonus: {NEW_USER_BONUS} gold received." if (is_new_user and referring_user_id) else ""
    
    caption = f"<b>{welcome_msg}</b>\n\nCollect rare anime characters, trade with users, and build your ultimate collection.{bonus_msg}\n\n<b>Account Overview</b>\n\nTier: {tier}\nGold: {balance:,}\nCharacters: {chars}\nReferrals: {refs}"
    
    keyboard = [
        [InlineKeyboardButton("Add to Group", url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
        [InlineKeyboardButton("Try Partner Bot", url=PARTNER_BOT)],
        [InlineKeyboardButton("Support", url=f'https://t.me/{SUPPORT_CHAT}'), InlineKeyboardButton("Updates", url='https://t.me/PICK_X_UPDATE')],
        [InlineKeyboardButton("Commands", callback_data='help'), InlineKeyboardButton("Stats", callback_data='stats')],
        [InlineKeyboardButton("Referral", callback_data='referral'), InlineKeyboardButton("Premium", callback_data='pass_info')],
        [InlineKeyboardButton("About", callback_data='credits')]
    ]
    
    try:
        await update.message.reply_text(text=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)
    except Exception as e:
        LOGGER.error(f"Start error: {e}")

async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = await user_collection.find_one({"id": user_id})
    
    if not user_data:
        await query.answer("Start bot first with /start", show_alert=True)
        return
    
    if query.data == 'credits':
        text = "<b>About Pick Catcher</b>\n\nDeveloped by a dedicated team for anime collectors.\n\n<b>Development Team</b>"
        buttons = []
        
        if OWNERS:
            for owner in OWNERS:
                buttons.append([InlineKeyboardButton(f"{owner['name']} - Owner", url=f"https://t.me/{owner['username']}")])
        
        try:
            sudo_users_db = await fetch_sudo_users()
            if sudo_users_db:
                text += "\n\n<b>Support Team</b>"
                for sudo in sudo_users_db:
                    sudo_title = sudo.get('sudo_title', 'Support')
                    sudo_username = sudo.get('username', '')
                    if sudo_username:
                        buttons.append([InlineKeyboardButton(sudo_title, url=f"https://t.me/{sudo_username}")])
        except Exception as e:
            LOGGER.error(f"Error fetching sudo: {e}")
        
        buttons.append([InlineKeyboardButton("Back", callback_data='back')])
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode='HTML', disable_web_page_preview=False)
    
    elif query.data == 'help':
        text = "<b>Commands</b>\n\n<b>Gameplay</b>\n/grab - Collect characters\n/fav - Set favorite\n/harem - View collection\n\n<b>Economy</b>\n/balance - Check gold\n/pay - Send gold\n/claim - Daily reward\n/roll - Gamble\n\n<b>Social</b>\n/trade - Trade characters\n/gift - Gift character\n/top - Leaderboards"
        keyboard = [
            [InlineKeyboardButton("Partner Bot", url=PARTNER_BOT)],
            [InlineKeyboardButton("Back", callback_data='back')]
        ]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)
    
    elif query.data == 'stats':
        balance = user_data.get('balance', 0)
        refs = user_data.get('referred_users', 0)
        pass_data = user_data.get('pass_data', {})
        tier = pass_data.get('tier', 'free').title()
        weekly_claims = pass_data.get('weekly_claims', 0)
        streak = pass_data.get('streak_count', 0)
        total_earnings = pass_data.get('total_invite_earnings', 0)
        
        text = f"<b>Statistics</b>\n\n<b>Financial</b>\nBalance: {balance:,} gold\nReferral Earnings: {total_earnings:,}\n\n<b>Collection</b>\nWeekly Claims: {weekly_claims}\n\n<b>Progress</b>\nStreak: {streak} days\nReferrals: {refs}\nTier: {tier}"
        keyboard = [[InlineKeyboardButton("Back", callback_data='back')]]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)
    
    elif query.data == 'referral':
        link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
        count = user_data.get('referred_users', 0)
        earned = count * REFERRER_REWARD
        
        text = f"<b>Referral Program</b>\n\nEarn {REFERRER_REWARD:,} gold per referral.\nNew users get {NEW_USER_BONUS:,} gold.\n\n<b>Your Stats</b>\nReferrals: {count}\nEarned: {earned:,} gold\n\n<b>Your Link</b>\n{link}"
        keyboard = [
            [InlineKeyboardButton("Share", url=f"https://t.me/share/url?url={link}")],
            [InlineKeyboardButton("Back", callback_data='back')]
        ]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)
    
    elif query.data == 'pass_info':
        tier = user_data.get('pass_data', {}).get('tier', 'free').title()
        text = f"<b>Membership</b>\n\nCurrent: {tier}\n\n<b>Free</b>\nBasic features\n\n<b>Premium</b>\n2x rewards\nExclusive characters\n\n<b>Elite</b>\n3x rewards\nMythic characters\nCustom badges\nVIP access"
        keyboard = [
            [InlineKeyboardButton("Upgrade", url=f'https://t.me/{SUPPORT_CHAT}')],
            [InlineKeyboardButton("Back", callback_data='back')]
        ]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)
    
    elif query.data == 'back':
        balance = user_data.get('balance', 0)
        refs = user_data.get('referred_users', 0)
        tier = user_data.get('pass_data', {}).get('tier', 'free').title()
        first_name = query.from_user.first_name
        
        caption = f"<b>Welcome back, {first_name}</b>\n\nCollect rare anime characters, trade with users, and build your ultimate collection.\n\n<b>Account</b>\n\nTier: {tier}\nGold: {balance:,}\nCharacters: 0\nReferrals: {refs}"
        keyboard = [
            [InlineKeyboardButton("Add to Group", url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
            [InlineKeyboardButton("Try Partner Bot", url=PARTNER_BOT)],
            [InlineKeyboardButton("Support", url=f'https://t.me/{SUPPORT_CHAT}'), InlineKeyboardButton("Updates", url='https://t.me/PICK_X_UPDATE')],
            [InlineKeyboardButton("Commands", callback_data='help'), InlineKeyboardButton("Stats", callback_data='stats')],
            [InlineKeyboardButton("Referral", callback_data='referral'), InlineKeyboardButton("Premium", callback_data='pass_info')],
            [InlineKeyboardButton("About", callback_data='credits')]
        ]
        await query.edit_message_text(text=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)

application.add_handler(CommandHandler('start', start, block=False))
application.add_handler(CallbackQueryHandler(button_callback, pattern='^(help|stats|referral|pass_info|credits|back)$', block=False))