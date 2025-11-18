import random
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from shivu import application, SUPPORT_CHAT, BOT_USERNAME, user_collection
import asyncio
from functools import lru_cache

# Constants
PHOTOS = ["https://files.catbox.moe/k3dhbe.mp4"]
RR, NUB = 1000, 500
OWNERS = [{"name": "Thorfinn", "username": "ll_Thorfinn_ll"}]
PB = "https://t.me/Siyaprobot?start=_tgr_6Nl2njExN2Rl"
MA = "https://shadow-rot.github.io/Just/"

# Static keyboards (pre-built for instant response)
BASE_KB = [
    [InlineKeyboardButton("🎮 Play Mini Game", web_app=WebAppInfo(url=MA))],
    [InlineKeyboardButton("Add to Group", url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
    [InlineKeyboardButton("Partner Bot", url=PB)],
    [InlineKeyboardButton("Support", url=f'https://t.me/{SUPPORT_CHAT}'), InlineKeyboardButton("Updates", url='https://t.me/PICK_X_UPDATE')],
    [InlineKeyboardButton("Help", callback_data='h'), InlineKeyboardButton("Stats", callback_data='s')],
    [InlineKeyboardButton("Refer", callback_data='r'), InlineKeyboardButton("Premium", callback_data='p')],
    [InlineKeyboardButton("About", callback_data='c')]
]

HELP_KB = [
    [InlineKeyboardButton("🎮 Mini Game", web_app=WebAppInfo(url=MA))],
    [InlineKeyboardButton("Partner", url=PB)],
    [InlineKeyboardButton("Back", callback_data='b')]
]

BACK_KB = [[InlineKeyboardButton("Back", callback_data='b')]]

# User cache with TTL
_user_cache = {}
_cache_lock = asyncio.Lock()

async def get_user_fast(uid):
    if uid in _user_cache:
        return _user_cache[uid]
    u = await user_collection.find_one({"id": uid}, {"balance": 1, "referred_users": 1, "pass_data.tier": 1, "pass_data.weekly_claims": 1, "pass_data.streak_count": 1, "pass_data.total_invite_earnings": 1})
    if u:
        _user_cache[uid] = u
        asyncio.create_task(clear_cache_later(uid))
    return u

async def clear_cache_later(uid):
    await asyncio.sleep(10)
    _user_cache.pop(uid, None)

def ref_task(uid, fn, ruid, ctx):
    asyncio.create_task(_proc_ref(uid, fn, ruid, ctx))

async def _proc_ref(uid, fn, ruid, ctx):
    try:
        if uid == ruid:
            return
        r = await user_collection.find_one({"id": ruid}, {"id": 1})
        if not r:
            return
        n = await user_collection.find_one({"id": uid}, {"referred_by": 1})
        if n and n.get('referred_by'):
            return
        asyncio.create_task(user_collection.bulk_write([
            {"updateOne": {"filter": {"id": uid}, "update": {"$set": {"referred_by": ruid}, "$inc": {"balance": NUB}}}},
            {"updateOne": {"filter": {"id": ruid}, "update": {"$inc": {"balance": RR, "referred_users": 1, "pass_data.tasks.invites": 1, "pass_data.total_invite_earnings": RR}, "$push": {"invited_user_ids": uid}}}}
        ]))
        asyncio.create_task(ctx.bot.send_message(ruid, f"<b>Referral!</b>\n\n<b>{escape(fn)}</b> joined\n\n+{RR:,} gold", parse_mode='HTML'))
    except:
        pass

async def start(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    fn = update.effective_user.first_name
    un = update.effective_user.username
    
    ruid = None
    if context.args and context.args[0].startswith('r_'):
        try:
            ruid = int(context.args[0][2:])
        except:
            pass
    
    u = await user_collection.find_one({"id": uid}, {"balance": 1, "referred_users": 1, "pass_data.tier": 1})
    
    if not u:
        u = {"id": uid, "first_name": fn, "username": un, "balance": NUB if ruid else 500, "characters": [], "referred_users": 0, "referred_by": None, "invited_user_ids": [], "pass_data": {"tier": "free", "weekly_claims": 0, "last_weekly_claim": None, "streak_count": 0, "last_streak_claim": None, "tasks": {"invites": 0, "weekly_claims": 0, "grabs": 0}, "mythic_unlocked": False, "premium_expires": None, "elite_expires": None, "pending_elite_payment": None, "invited_users": [], "total_invite_earnings": 0}}
        asyncio.create_task(user_collection.insert_one(u))
        if ruid:
            ref_task(uid, fn, ruid, context)
        w = "Welcome!"
        b = f"\n\n+{NUB} gold!" if ruid else ""
    else:
        w = f"Hey {fn}!"
        b = ""
    
    bal = u.get('balance', 0)
    refs = u.get('referred_users', 0)
    tier = u.get('pass_data', {}).get('tier', 'free').title()
    
    cap = f"<b>{w}</b>\n\nCollect anime characters!{b}\n\n<b>Account</b>\nTier: {tier}\nGold: {bal:,}\nRefs: {refs}"
    
    await update.message.reply_text(cap, reply_markup=InlineKeyboardMarkup(BASE_KB), parse_mode='HTML', disable_web_page_preview=False)

async def button_callback(update: Update, context: CallbackContext):
    q = update.callback_query
    uid = q.from_user.id
    
    u = await get_user_fast(uid)
    if not u:
        return await q.answer("Start /start", show_alert=True)
    
    await q.answer()
    d = q.data
    
    if d == 'c':
        t = "<b>Pick Catcher</b>\n\nFor anime collectors.\n\n<b>Team</b>"
        b = [[InlineKeyboardButton(f"{o['name']} - Owner", url=f"https://t.me/{o['username']}")] for o in OWNERS]
        
        try:
            from shivu.modules.database.sudo import fetch_sudo_users
            s = await fetch_sudo_users()
            if s:
                t += "\n\n<b>Support</b>"
                b.extend([[InlineKeyboardButton(x.get('sudo_title', 'Support'), url=f"https://t.me/{x.get('username', '')}")] for x in s[:3] if x.get('username')])
        except:
            pass
        
        b.append([InlineKeyboardButton("Back", callback_data='b')])
        await q.edit_message_text(t, reply_markup=InlineKeyboardMarkup(b), parse_mode='HTML', disable_web_page_preview=False)
    
    elif d == 'h':
        t = "<b>Commands</b>\n\n/grab - Collect\n/fav - Favorite\n/harem - Collection\n/balance - Gold\n/pay - Send\n/claim - Daily\n/trade - Trade\n/gift - Gift\n/top - Ranks"
        await q.edit_message_text(t, reply_markup=InlineKeyboardMarkup(HELP_KB), parse_mode='HTML', disable_web_page_preview=False)
    
    elif d == 's':
        bal = u.get('balance', 0)
        refs = u.get('referred_users', 0)
        pd = u.get('pass_data', {})
        tier = pd.get('tier', 'free').title()
        wc = pd.get('weekly_claims', 0)
        st = pd.get('streak_count', 0)
        e = pd.get('total_invite_earnings', 0)
        
        t = f"<b>Stats</b>\n\nBalance: {bal:,}\nEarnings: {e:,}\nWeekly: {wc}\nStreak: {st}d\nRefs: {refs}\nTier: {tier}"
        await q.edit_message_text(t, reply_markup=InlineKeyboardMarkup(BACK_KB), parse_mode='HTML', disable_web_page_preview=False)
    
    elif d == 'r':
        link = f"https://t.me/{BOT_USERNAME}?start=r_{uid}"
        cnt = u.get('referred_users', 0)
        ern = cnt * RR
        
        t = f"<b>Referral</b>\n\n{RR:,} gold/invite\n{NUB:,} for new users\n\nRefs: {cnt}\nEarned: {ern:,}\n\n{link}"
        kb = [
            [InlineKeyboardButton("Share", url=f"https://t.me/share/url?url={link}")],
            [InlineKeyboardButton("Back", callback_data='b')]
        ]
        await q.edit_message_text(t, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML', disable_web_page_preview=False)
    
    elif d == 'p':
        tier = u.get('pass_data', {}).get('tier', 'free').title()
        t = f"<b>Membership</b>\n\nCurrent: {tier}\n\n<b>Free</b> Basic\n<b>Premium</b> 2x rewards\n<b>Elite</b> 3x + Mythic"
        kb = [
            [InlineKeyboardButton("Upgrade", url=f'https://t.me/{SUPPORT_CHAT}')],
            [InlineKeyboardButton("Back", callback_data='b')]
        ]
        await q.edit_message_text(t, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML', disable_web_page_preview=False)
    
    elif d == 'b':
        bal = u.get('balance', 0)
        refs = u.get('referred_users', 0)
        tier = u.get('pass_data', {}).get('tier', 'free').title()
        
        cap = f"<b>Hey {q.from_user.first_name}!</b>\n\nCollect anime characters!\n\n<b>Account</b>\nTier: {tier}\nGold: {bal:,}\nRefs: {refs}"
        await q.edit_message_text(cap, reply_markup=InlineKeyboardMarkup(BASE_KB), parse_mode='HTML', disable_web_page_preview=False)

application.add_handler(CommandHandler('start', start, block=False))
application.add_handler(CallbackQueryHandler(button_callback, pattern='^(h|s|r|p|c|b)$', block=False))