import random
from shivu.modules.database.sudo import fetch_sudo_users
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from shivu import application, SUPPORT_CHAT, BOT_USERNAME, LOGGER, user_collection, user_totals_collection
from shivu.modules.chatlog import track_bot_start
import asyncio

PHOTOS = ["https://files.catbox.moe/k3dhbe.mp4"]
REFERRER_REWARD = 1000
NEW_USER_BONUS = 500
OWNERS = [{"name": "Thorfinn", "username": "ll_Thorfinn_ll"}]
PARTNER_BOT = "https://t.me/Siyaprobot?start=_tgr_6Nl2njExN2Rl"
MINI_APP_URL = "https://shadow-rot.github.io/Just/"

# Cache for sudo users to avoid repeated DB calls
_sudo_cache = {"data": None, "timestamp": 0}
CACHE_TTL = 300  # 5 minutes

async def get_cached_sudo():
    import time
    current_time = time.time()
    if _sudo_cache["data"] is None or (current_time - _sudo_cache["timestamp"]) > CACHE_TTL:
        try:
            _sudo_cache["data"] = await fetch_sudo_users()
            _sudo_cache["timestamp"] = current_time
        except:
            _sudo_cache["data"] = []
    return _sudo_cache["data"]

async def process_referral(user_id, first_name, referring_user_id, context):
    try:
        if user_id == referring_user_id:
            return
        
        results = await asyncio.gather(
            user_collection.find_one({"id": referring_user_id}, {"id": 1}),
            user_collection.find_one({"id": user_id}, {"referred_by": 1}),
            return_exceptions=True
        )
        
        if not results[0] or (results[1] and results[1].get('referred_by')):
            return
        
        asyncio.create_task(user_collection.bulk_write([
            {"updateOne": {"filter": {"id": user_id}, "update": {"$set": {"referred_by": referring_user_id}, "$inc": {"balance": NEW_USER_BONUS}}}},
            {"updateOne": {"filter": {"id": referring_user_id}, "update": {"$inc": {"balance": REFERRER_REWARD, "referred_users": 1, "pass_data.tasks.invites": 1, "pass_data.total_invite_earnings": REFERRER_REWARD}, "$push": {"invited_user_ids": user_id}}}}
        ]))
        
        asyncio.create_task(context.bot.send_message(
            chat_id=referring_user_id, 
            text=f"<b>Referral!</b>\n\n<b>{escape(first_name)}</b> joined\n\n+{REFERRER_REWARD:,} gold", 
            parse_mode='HTML'
        ))
    except:
        pass

async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    username = update.effective_user.username
    
    referring_user_id = None
    if context.args and context.args[0].startswith('r_'):
        try:
            referring_user_id = int(context.args[0][2:])
        except:
            pass
    
    user_data = await user_collection.find_one({"id": user_id}, {"balance": 1, "referred_users": 1, "pass_data.tier": 1})
    is_new = not user_data
    
    if is_new:
        user_data = {
            "id": user_id,
            "first_name": first_name,
            "username": username,
            "balance": NEW_USER_BONUS if referring_user_id else 500,
            "characters": [],
            "referred_users": 0,
            "referred_by": None,
            "invited_user_ids": [],
            "pass_data": {"tier": "free", "weekly_claims": 0, "last_weekly_claim": None, "streak_count": 0, "last_streak_claim": None, "tasks": {"invites": 0, "weekly_claims": 0, "grabs": 0}, "mythic_unlocked": False, "premium_expires": None, "elite_expires": None, "pending_elite_payment": None, "invited_users": [], "total_invite_earnings": 0}
        }
        asyncio.create_task(user_collection.insert_one(user_data))
        asyncio.create_task(track_bot_start(user_id, first_name, username, True))
        if referring_user_id:
            asyncio.create_task(process_referral(user_id, first_name, referring_user_id, context))
    else:
        asyncio.create_task(track_bot_start(user_id, first_name, username, False))
    
    balance = user_data.get('balance', 0)
    refs = user_data.get('referred_users', 0)
    tier = user_data.get('pass_data', {}).get('tier', 'free').title()
    
    welcome = "Welcome!" if is_new else f"Hey {first_name}!"
    bonus = f"\n\n+{NEW_USER_BONUS} gold bonus!" if (is_new and referring_user_id) else ""
    
    caption = f"<b>{welcome}</b>\n\nCollect anime characters, trade & compete!{bonus}\n\n<b>Account</b>\nTier: {tier}\nGold: {balance:,}\nReferrals: {refs}"
    
    keyboard = [
        [InlineKeyboardButton("🎮 Play Mini Game", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("Add to Group", url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
        [InlineKeyboardButton("Partner Bot", url=PARTNER_BOT)],
        [InlineKeyboardButton("Support", url=f'https://t.me/{SUPPORT_CHAT}'), InlineKeyboardButton("Updates", url='https://t.me/PICK_X_UPDATE')],
        [InlineKeyboardButton("Help", callback_data='help'), InlineKeyboardButton("Stats", callback_data='stats')],
        [InlineKeyboardButton("Refer", callback_data='referral'), InlineKeyboardButton("Premium", callback_data='pass_info')],
        [InlineKeyboardButton("About", callback_data='credits')]
    ]
    
    asyncio.create_task(update.message.reply_text(text=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False))

async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    user_data = await user_collection.find_one({"id": user_id}, {"balance": 1, "referred_users": 1, "pass_data": 1})
    
    if not user_data:
        return await query.answer("Start bot first /start", show_alert=True)
    
    await query.answer()
    
    if query.data == 'credits':
        text = "<b>Pick Catcher</b>\n\nDeveloped for anime collectors.\n\n<b>Team</b>"
        buttons = [[InlineKeyboardButton(f"{o['name']} - Owner", url=f"https://t.me/{o['username']}")] for o in OWNERS]
        
        sudo_users = await get_cached_sudo()
        if sudo_users:
            text += "\n\n<b>Support</b>"
            buttons.extend([[InlineKeyboardButton(s.get('sudo_title', 'Support'), url=f"https://t.me/{s.get('username', '')}")] for s in sudo_users if s.get('username')])
        
        buttons.append([InlineKeyboardButton("Back", callback_data='back')])
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode='HTML', disable_web_page_preview=False)
    
    elif query.data == 'help':
        text = "<b>Commands</b>\n\n/grab - Collect\n/fav - Favorite\n/harem - Collection\n/balance - Gold\n/pay - Send\n/claim - Daily\n/trade - Trade\n/gift - Gift\n/top - Ranks"
        keyboard = [
            [InlineKeyboardButton("🎮 Mini Game", web_app=WebAppInfo(url=MINI_APP_URL))],
            [InlineKeyboardButton("Partner", url=PARTNER_BOT)],
            [InlineKeyboardButton("Back", callback_data='back')]
        ]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)
    
    elif query.data == 'stats':
        balance = user_data.get('balance', 0)
        refs = user_data.get('referred_users', 0)
        pd = user_data.get('pass_data', {})
        tier = pd.get('tier', 'free').title()
        wc = pd.get('weekly_claims', 0)
        streak = pd.get('streak_count', 0)
        earn = pd.get('total_invite_earnings', 0)
        
        text = f"<b>Stats</b>\n\nBalance: {balance:,}\nEarnings: {earn:,}\nWeekly: {wc}\nStreak: {streak}d\nRefs: {refs}\nTier: {tier}"
        keyboard = [[InlineKeyboardButton("Back", callback_data='back')]]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)
    
    elif query.data == 'referral':
        link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
        count = user_data.get('referred_users', 0)
        earned = count * REFERRER_REWARD
        
        text = f"<b>Referral</b>\n\n{REFERRER_REWARD:,} gold/invite\n{NEW_USER_BONUS:,} for new users\n\nRefs: {count}\nEarned: {earned:,}\n\n{link}"
        keyboard = [
            [InlineKeyboardButton("Share", url=f"https://t.me/share/url?url={link}")],
            [InlineKeyboardButton("Back", callback_data='back')]
        ]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)
    
    elif query.data == 'pass_info':
        tier = user_data.get('pass_data', {}).get('tier', 'free').title()
        text = f"<b>Membership</b>\n\nCurrent: {tier}\n\n<b>Free</b> Basic\n<b>Premium</b> 2x rewards\n<b>Elite</b> 3x + Mythic"
        keyboard = [
            [InlineKeyboardButton("Upgrade", url=f'https://t.me/{SUPPORT_CHAT}')],
            [InlineKeyboardButton("Back", callback_data='back')]
        ]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)
    
    elif query.data == 'back':
        balance = user_data.get('balance', 0)
        refs = user_data.get('referred_users', 0)
        tier = user_data.get('pass_data', {}).get('tier', 'free').title()
        
        caption = f"<b>Hey {query.from_user.first_name}!</b>\n\nCollect anime characters!\n\n<b>Account</b>\nTier: {tier}\nGold: {balance:,}\nRefs: {refs}"
        keyboard = [
            [InlineKeyboardButton("🎮 Play Mini Game", web_app=WebAppInfo(url=MINI_APP_URL))],
            [InlineKeyboardButton("Add to Group", url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
            [InlineKeyboardButton("Partner Bot", url=PARTNER_BOT)],
            [InlineKeyboardButton("Support", url=f'https://t.me/{SUPPORT_CHAT}'), InlineKeyboardButton("Updates", url='https://t.me/PICK_X_UPDATE')],
            [InlineKeyboardButton("Help", callback_data='help'), InlineKeyboardButton("Stats", callback_data='stats')],
            [InlineKeyboardButton("Refer", callback_data='referral'), InlineKeyboardButton("Premium", callback_data='pass_info')],
            [InlineKeyboardButton("About", callback_data='credits')]
        ]
        await query.edit_message_text(text=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=False)

application.add_handler(CommandHandler('start', start, block=False))
application.add_handler(CallbackQueryHandler(button_callback, pattern='^(help|stats|referral|pass_info|credits|back)$', block=False))