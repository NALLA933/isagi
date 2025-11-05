import os
import asyncio
import random
from datetime import datetime
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler

from shivu import application, OWNER_ID, user_collection, top_global_groups_collection, group_user_totals_collection
from shivu import sudo_users as SUDO_USERS

SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# Video URLs for random preview
VIDEOS = [
    "https://files.catbox.moe/csqqb2.mp4",
    "https://files.catbox.moe/dpeatb.mp4", 
   "https://files.catbox.moe/38b2an.mp4", 
   "https://files.catbox.moe/x3k8vj.mp4"
]

def sc(text): return text.translate(str.maketrans("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ", "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢABCDEFGHIJKLMNOPQRSTUVWXYZ"))

def badge(r): return "★ 1ꜱᴛ ★" if r==1 else "★ 2ɴᴅ ★" if r==2 else "★ 3ʀᴅ ★" if r==3 else f"ᴛᴏᴘ {r}" if r<=10 else f"#{r}"

def bar(c, m, l=10): f=int((c/m)*l) if m>0 else 0; return "▰"*f+"▱"*(l-f)

def get_video(): return random.choice(VIDEOS)

async def anim(msg, txt):
    try:
        for i in range(8): await msg.edit_text(f"{SPINNER[i%len(SPINNER)]} {sc(txt)}"); await asyncio.sleep(0.2)
    except: pass

async def global_leaderboard(update: Update, context: CallbackContext, edit=False):
    q = update.callback_query if edit else None
    msg = q.message if edit else await update.message.reply_text(sc("loading..."))
    if edit: await q.answer(sc("refreshing..."))
    
    task = asyncio.create_task(anim(msg, "fetching rankings"))
    try:
        data = await top_global_groups_collection.aggregate([
            {"$project": {"group_name": 1, "count": 1}}, {"$sort": {"count": -1}}, {"$limit": 10}
        ]).to_list(10)
        task.cancel()
        
        if not data: return await msg.edit_text(sc("no data available."))
        
        vid = get_video()
        cap = f"<a href='{vid}'>&#8205;</a><b>⸻ {sc('top global groups')} ⸻</b>\n\n"
        for i, g in enumerate(data, 1):
            n = escape(g.get('group_name', 'Unknown'))[:22]; c = g.get("count", 0)
            cap += f"<b>{badge(i)}</b>\n<blockquote>{sc(n)}\n{bar(c, data[0]['count'], 12)}\n{sc('chars')}: <b>{c:,}</b></blockquote>\n\n"
        cap += f"<b>⸻ {sc('leaderboard')} ⸻</b>\n<i>{sc('updated')}: {datetime.now().strftime('%H:%M:%S')}</i>"
        
        btns = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 ʀᴇғʀᴇꜱʜ", callback_data="lb_tg"), InlineKeyboardButton("📊 ᴍᴏʀᴇ", callback_data="lb_more")], [InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ", callback_data="lb_close")]])
        await msg.edit_text(cap, parse_mode='HTML', reply_markup=btns)
    except: pass

async def ctop(update: Update, context: CallbackContext, edit=False, cid=None):
    q = update.callback_query if edit else None
    msg = q.message if edit else await update.message.reply_text(sc("loading..."))
    cid = cid or update.effective_chat.id
    if edit: await q.answer(sc("refreshing..."))
    
    task = asyncio.create_task(anim(msg, "analyzing chat"))
    try:
        try: chat = await context.bot.get_chat(cid); title = escape(chat.title)[:30]
        except: title = "This Chat"
        
        data = await group_user_totals_collection.aggregate([
            {"$match": {"group_id": cid}}, {"$project": {"user_id": "$_id", "first_name": 1, "character_count": "$count"}},
            {"$sort": {"character_count": -1}}, {"$limit": 10}
        ]).to_list(10)
        task.cancel()
        
        if not data: return await msg.edit_text(sc("no data."))
        
        tot = sum(u['character_count'] for u in data)
        vid = get_video()
        cap = f"<a href='{vid}'>&#8205;</a><b>⸻ {sc('top chat')} ⸻</b>\n\n<b>{sc('chat')}</b>: {sc(title)}\n\n"
        for i, u in enumerate(data, 1):
            uid = u.get('user_id', u.get('_id')); n = escape(u.get('first_name', 'Unknown'))[:17]; c = u.get("character_count", 0)
            pct = (c/tot*100) if tot>0 else 0; m = f"<a href='tg://user?id={uid}'>{sc(n)}</a>"
            cap += f"<b>{badge(i)}</b>\n<blockquote>{m}\n{bar(c, data[0]['character_count'], 12)}\n{sc('count')}: <b>{c:,}</b> ({pct:.1f}%)</blockquote>\n\n"
        cap += f"<b>⸻ {sc('rankings')} ⸻</b>\n<i>{sc('total')}: {tot:,}</i>"
        
        btns = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 ʀᴇғʀᴇꜱʜ", callback_data=f"lb_ct_{cid}"), InlineKeyboardButton("📊 ꜱᴛᴀᴛꜱ", callback_data=f"lb_cs_{cid}")], [InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ", callback_data="lb_close")]])
        await msg.edit_text(cap, parse_mode='HTML', reply_markup=btns)
    except: pass

async def leaderboard(update: Update, context: CallbackContext, edit=False, lim=10):
    q = update.callback_query if edit else None
    msg = q.message if edit else await update.message.reply_text(sc("loading..."))
    if edit: await q.answer(sc("refreshing..."))
    
    task = asyncio.create_task(anim(msg, "fetching champions"))
    try:
        data = await user_collection.aggregate([
            {"$match": {"characters": {"$exists": True, "$type": "array"}}},
            {"$project": {"user_id": "$id", "first_name": 1, "character_count": {"$size": "$characters"}}},
            {"$sort": {"character_count": -1}}, {"$limit": lim}
        ]).to_list(lim)
        task.cancel()
        
        if not data: return await msg.edit_text(sc("no data."))
        
        vid = get_video()
        cap = f"<a href='{vid}'>&#8205;</a><b>⸻ {sc('global hall of fame' if lim==10 else f'top {lim}')} ⸻</b>\n\n"
        for i, u in enumerate(data, 1):
            uid = u.get('user_id', u.get('_id')); n = escape(u.get('first_name', 'Unknown'))[:17]; c = u.get("character_count", 0)
            m = f"<a href='tg://user?id={uid}'>{sc(n)}</a>"
            cap += f"<b>{badge(i)}</b>\n<blockquote>{m}\n{bar(c, data[0]['character_count'], 12)}\n{sc('collection')}: <b>{c:,}</b></blockquote>\n\n"
        cap += f"<b>⸻ {sc('rankings')} ⸻</b>\n<i>{sc('showing top')} {lim}</i>"
        
        if lim==10:
            btns = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 ʀᴇғʀᴇꜱʜ", callback_data="lb_g"), InlineKeyboardButton("📈 ᴛᴏᴘ 20", callback_data="lb_20")], [InlineKeyboardButton("👤 ᴍʏ ʀᴀɴᴋ", callback_data="lb_mr"), InlineKeyboardButton("🏆 ɢʀᴏᴜᴘꜱ", callback_data="lb_tg")], [InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ", callback_data="lb_close")]])
        else:
            btns = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 ʀᴇғʀᴇꜱʜ", callback_data="lb_20"), InlineKeyboardButton("🔙 ᴛᴏᴘ 10", callback_data="lb_g")], [InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ", callback_data="lb_close")]])
        await msg.edit_text(cap, parse_mode='HTML', reply_markup=btns)
    except: pass

async def my_rank(update: Update, context: CallbackContext, edit=False):
    q = update.callback_query if edit else None
    uid = update.effective_user.id
    msg = q.message if edit else await update.message.reply_text(sc("loading..."))
    if edit: await q.answer(sc("loading..."))
    
    task = asyncio.create_task(anim(msg, "calculating rank"))
    try:
        user = await user_collection.find_one({'id': uid})
        task.cancel()
        
        vid = get_video()
        if not user or 'characters' not in user:
            cap = f"<a href='{vid}'>&#8205;</a><b>⸻ {sc('no profile')} ⸻</b>\n\n<blockquote>{sc('start collecting!')}</blockquote>\n\n<b>⸻ {sc('system')} ⸻</b>"
            btns = InlineKeyboardMarkup([[InlineKeyboardButton("🏆 ᴠɪᴇᴡ ᴛᴏᴘ", callback_data="lb_g")], [InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ", callback_data="lb_close")]])
            return await msg.edit_text(cap, parse_mode='HTML', reply_markup=btns)
        
        cc = len(user.get('characters', []))
        hi = await user_collection.count_documents({"characters": {"$exists": True, "$type": "array"}, "$expr": {"$gt": [{"$size": "$characters"}, cc]}})
        r = hi+1; tot = await user_collection.count_documents({"characters": {"$exists": True, "$type": "array"}})
        n = escape(user.get('first_name', 'Unknown')); m = f"<a href='tg://user?id={uid}'>{sc(n)}</a>"
        pct = ((tot-r)/tot*100) if tot>0 else 0
        tier = "🌟 ʟᴇɢᴇɴᴅ" if r==1 else "💎 ᴍᴀꜱᴛᴇʀ" if r<=10 else "💠 ᴅɪᴀᴍᴏɴᴅ" if pct>=90 else "🔷 ᴘʟᴀᴛɪɴᴜᴍ" if pct>=75 else "🟡 ɢᴏʟᴅ" if pct>=50 else "⚪ ꜱɪʟᴠᴇʀ" if pct>=25 else "🟤 ʙʀᴏɴᴢᴇ"
        
        cap = f"<a href='{vid}'>&#8205;</a><b>⸻ {sc('your profile')} ⸻</b>\n\n<b>{sc('collector')}</b>\n<blockquote>{m}\n{sc('tier')}: {tier}</blockquote>\n\n<b>{sc('statistics')}</b>\n<blockquote>\n{sc('rank')}: <b>#{r:,}</b> / {tot:,}\n{sc('badge')}: <b>{badge(r)}</b>\n{sc('chars')}: <b>{cc:,}</b>\n{sc('percentile')}: <b>ᴛᴏᴘ {100-pct:.1f}%</b>\n</blockquote>\n\n<b>{sc('progress')}</b>\n<blockquote>{bar(pct, 100, 15)}</blockquote>\n\n<b>⸻ {sc('keep going!')} ⸻</b>"
        
        btns = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 ʀᴇғʀᴇꜱʜ", callback_data="lb_mr"), InlineKeyboardButton("🏆 ᴛᴏᴘ", callback_data="lb_g")], [InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ", callback_data="lb_close")]])
        await msg.edit_text(cap, parse_mode='HTML', reply_markup=btns)
    except: pass

async def chat_stats(update: Update, context: CallbackContext, edit=False, cid=None):
    q = update.callback_query if edit else None
    msg = q.message if edit else await update.message.reply_text(sc("loading..."))
    cid = cid or update.effective_chat.id
    if edit: await q.answer(sc("loading..."))
    
    task = asyncio.create_task(anim(msg, "computing stats"))
    try:
        try: chat = await context.bot.get_chat(cid); title = escape(chat.title)[:40]
        except: title = "This Chat"
        
        uc = await group_user_totals_collection.count_documents({"group_id": cid})
        task.cancel()
        if uc==0: return await msg.edit_text(sc("no activity."))
        
        res = await group_user_totals_collection.aggregate([{"$match": {"group_id": cid}}, {"$group": {"_id": None, "total": {"$sum": "$count"}}}]).to_list(1)
        tot = res[0]['total'] if res else 0
        top = await group_user_totals_collection.find_one({"group_id": cid}, sort=[("count", -1)])
        
        vid = get_video()
        cap = f"<a href='{vid}'>&#8205;</a><b>⸻ {sc('chat stats')} ⸻</b>\n\n<b>{sc('chat')}</b>\n<blockquote>{sc(title)}</blockquote>\n\n<b>{sc('data')}</b>\n<blockquote>\n{sc('users')}: <b>{uc:,}</b>\n{sc('chars')}: <b>{tot:,}</b>\n{sc('avg')}: <b>{tot/uc:.1f}</b>\n</blockquote>"
        if top: cap += f"\n\n<b>{sc('top')}</b>\n<blockquote>{sc(escape(top.get('first_name', 'Unknown'))[:20])}\n{sc('count')}: <b>{top.get('count', 0):,}</b>\n</blockquote>"
        cap += f"\n\n<b>⸻ {sc('analytics')} ⸻</b>"
        
        btns = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 ʀᴇғʀᴇꜱʜ", callback_data=f"lb_cs_{cid}"), InlineKeyboardButton("👥 ᴛᴏᴘ", callback_data=f"lb_ct_{cid}")], [InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ", callback_data="lb_close")]])
        await msg.edit_text(cap, parse_mode='HTML', reply_markup=btns)
    except: pass

async def stats(update: Update, context: CallbackContext, edit=False):
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text(sc("unauthorized."))
    
    q = update.callback_query if edit else None
    msg = q.message if edit else await update.message.reply_text(sc("loading..."))
    if edit: await q.answer(sc("refreshing..."))
    
    task = asyncio.create_task(anim(msg, "computing"))
    try:
        u = await user_collection.count_documents({})
        g = len(await group_user_totals_collection.distinct('group_id'))
        c = await user_collection.count_documents({"characters": {"$exists": True, "$type": "array"}})
        res = await user_collection.aggregate([{"$match": {"characters": {"$exists": True, "$type": "array"}}}, {"$project": {"cc": {"$size": "$characters"}}}, {"$group": {"_id": None, "tot": {"$sum": "$cc"}}}]).to_list(1)
        tc = res[0]['tot'] if res else 0
        task.cancel()
        
        vid = get_video()
        cap = f"<a href='{vid}'>&#8205;</a><b>⸻ {sc('system stats')} ⸻</b>\n\n<b>{sc('database')}</b>\n<blockquote>\n{sc('users')}: <b>{u:,}</b>\n{sc('collectors')}: <b>{c:,}</b>\n{sc('groups')}: <b>{g:,}</b>\n{sc('chars')}: <b>{tc:,}</b>\n</blockquote>\n\n<b>{sc('analytics')}</b>\n<blockquote>\n{sc('avg')}: <b>{tc/c:.1f}</b>\n{sc('rate')}: <b>{(c/u*100):.1f}%</b>\n</blockquote>\n\n<b>⸻ {sc('bot system')} ⸻</b>\n<i>{sc('updated')}: {datetime.now().strftime('%H:%M:%S')}</i>"
        
        btns = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 ʀᴇғʀᴇꜱʜ", callback_data="lb_st")], [InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ", callback_data="lb_close")]])
        await msg.edit_text(cap, parse_mode='HTML', reply_markup=btns)
    except: pass

async def export_users(update: Update, context: CallbackContext):
    if str(update.effective_user.id) not in SUDO_USERS: return await update.message.reply_text(sc('unauthorized.'))
    msg = await update.message.reply_text(sc('exporting...'))
    task = asyncio.create_task(anim(msg, "generating"))
    try:
        users = await user_collection.find({}).to_list(None)
        task.cancel()
        cont = f"⸻ USER EXPORT ⸻\n\n{datetime.now()}\nTotal: {len(users):,}\n{'='*50}\n\n"
        for u in users: cont += f"[{u.get('id')}] {u.get('first_name')} | @{u.get('username')} | {len(u.get('characters', []))} chars\n"
        with open('users.txt', 'w', encoding='utf-8') as f: f.write(cont)
        await msg.edit_text(sc("✓ complete!"))
        with open('users.txt', 'rb') as f: await context.bot.send_document(update.effective_chat.id, f, caption=f"<b>{sc('users')}</b>: {len(users):,}", parse_mode='HTML')
        os.remove('users.txt'); await msg.delete()
    except: pass

async def export_groups(update: Update, context: CallbackContext):
    if str(update.effective_user.id) not in SUDO_USERS: return await update.message.reply_text(sc('unauthorized.'))
    msg = await update.message.reply_text(sc('exporting...'))
    task = asyncio.create_task(anim(msg, "generating"))
    try:
        grps = await top_global_groups_collection.find({}).to_list(None)
        grps.sort(key=lambda x: x.get('count', 0), reverse=True)
        task.cancel()
        cont = f"⸻ GROUP EXPORT ⸻\n\n{datetime.now()}\nTotal: {len(grps):,}\n{'='*50}\n\n"
        for i, g in enumerate(grps, 1): cont += f"[{i}] {g.get('group_name')} | {g.get('count', 0):,}\n"
        with open('groups.txt', 'w', encoding='utf-8') as f: f.write(cont)
        await msg.edit_text(sc("✓ complete!"))
        with open('groups.txt', 'rb') as f: await context.bot.send_document(update.effective_chat.id, f, caption=f"<b>{sc('groups')}</b>: {len(grps):,}", parse_mode='HTML')
        os.remove('groups.txt'); await msg.delete()
    except: pass

async def cb(update: Update, context: CallbackContext):
    q = update.callback_query; await q.answer()
    d = q.data
    try:
        if d=="lb_g": await leaderboard(update, context, True)
        elif d=="lb_20": await leaderboard(update, context, True, 20)
        elif d=="lb_tg": await global_leaderboard(update, context, True)
        elif d=="lb_mr": await my_rank(update, context, True)
        elif d.startswith("lb_ct_"): await ctop(update, context, True, int(d.split("_")[2]))
        elif d.startswith("lb_cs_"): await chat_stats(update, context, True, int(d.split("_")[2]))
        elif d=="lb_st": await stats(update, context, True)
        elif d=="lb_close": await q.message.delete()
    except: pass

application.add_handler(CommandHandler('topgroups', global_leaderboard, block=False))
application.add_handler(CommandHandler('topchat', ctop, block=False))
application.add_handler(CommandHandler(['gstop', 'top'], leaderboard, block=False))
application.add_handler(CommandHandler(['myrank', 'rank'], my_rank, block=False))
application.add_handler(CommandHandler('chatstats', chat_stats, block=False))
application.add_handler(CommandHandler('stats', stats, block=False))
application.add_handler(CommandHandler('list', export_users, block=False))
application.add_handler(CommandHandler('groups', export_groups, block=False))
application.add_handler(CallbackQueryHandler(cb, pattern="^lb_"))