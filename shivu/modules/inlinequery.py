import re
import time
from html import escape
from typing import List, Dict, Optional, Tuple, Set
from cachetools import TTLCache
from pymongo import ASCENDING, DESCENDING
from functools import lru_cache
from collections import defaultdict

from telegram import Update, InlineQueryResultPhoto, InlineQueryResultVideo, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import InlineQueryHandler, CallbackQueryHandler
from telegram.constants import ParseMode

from shivu import application, db

collection = db['anime_characters_lol']
user_collection = db['user_collection_lmaoooo']

HAREM_RARITY = {
    "common": "🟢 Common", "rare": "🟣 Rare", "legendary": "🟡 Legendary",
    "special": "💮 Special Edition", "neon": "💫 Neon", "manga": "✨ Manga",
    "cosplay": "🎭 Cosplay", "celestial": "🎐 Celestial", "premium": "🔮 Premium Edition",
    "erotic": "💋 Erotic", "summer": "🌤 Summer", "winter": "☃️ Winter",
    "monsoon": "☔️ Monsoon", "valentine": "💝 Valentine", "halloween": "🎃 Halloween",
    "christmas": "🎄 Christmas", "mythic": "🏵 Mythic", "events": "🎗 Special Events",
    "amv": "🎥 AMV", "tiny": "👼 Tiny", "default": None
}

RARITY_ORDER = {
    "🏵": 1, "🔮": 2, "🟡": 3, "🎗": 4, "💫": 5, "✨": 6, "🎐": 7,
    "🎭": 8, "💮": 9, "🎥": 10, "💋": 11, "👼": 12, "💝": 13, "🎃": 14,
    "🎄": 15, "🌤": 16, "☃️": 17, "☔️": 18, "🟣": 19, "🟢": 20
}

FILTERS = {
    'rare': ['🏵', '🔮', '🟡', '🎗', '💫', '✨', '🎐', '🎭', '💮', '🎥', '💋', '👼'],
    'video': True,
    'new': 'recent'
}

try:
    collection.create_index([('id', ASCENDING)])
    collection.create_index([('anime', ASCENDING)])
    collection.create_index([('name', ASCENDING)])
    collection.create_index([('rarity', ASCENDING)])
    collection.create_index([('img_url', ASCENDING)])
    collection.create_index([('is_video', ASCENDING)])
    user_collection.create_index([('id', ASCENDING)])
    user_collection.create_index([('characters.id', ASCENDING)])
    user_collection.create_index([('first_name', ASCENDING)])
except:
    pass

char_cache = TTLCache(maxsize=40000, ttl=14400)
user_cache = TTLCache(maxsize=40000, ttl=1200)
count_cache = TTLCache(maxsize=40000, ttl=3600)
owner_cache = TTLCache(maxsize=25000, ttl=1800)
search_cache = TTLCache(maxsize=10000, ttl=400)
stats_cache = TTLCache(maxsize=10000, ttl=2400)
rank_cache = TTLCache(maxsize=5000, ttl=3600)

CAPS = str.maketrans('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', 'ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ')

@lru_cache(maxsize=16384)
def sc(t: str) -> str:
    return t.translate(CAPS)

@lru_cache(maxsize=8192)
def parse_rar(r: str) -> Tuple[str, str]:
    if ' ' in r:
        p = r.split(' ', 1)
        return p[0], p[1] if len(p) > 1 else 'Common'
    return '🟢', 'Common'

def trunc(t: str, l: int = 20) -> str:
    return t[:l-2] + '..' if len(t) > l else t

def rar_val(c: Dict) -> int:
    r = c.get('rarity', '🟢 Common')
    e = r.split(' ')[0] if ' ' in r else '🟢'
    return RARITY_ORDER.get(e, 99)

def dedupe_chars(chars: List[Dict]) -> List[Dict]:
    seen = set()
    result = []
    for c in chars:
        cid = c.get('id')
        if cid and cid not in seen:
            seen.add(cid)
            result.append(c)
    return result

async def g_count(cid: str) -> int:
    k = f"gc{cid}"
    if k in count_cache:
        return count_cache[k]
    c = await user_collection.count_documents({'characters.id': cid})
    count_cache[k] = c
    return c

async def a_count(anime: str) -> int:
    k = f"ac{anime}"
    if k in count_cache:
        return count_cache[k]
    c = await collection.count_documents({'anime': anime})
    count_cache[k] = c
    return c

async def get_char_rank(cid: str) -> int:
    k = f"rk{cid}"
    if k in rank_cache:
        return rank_cache[k]
    
    char = await collection.find_one({'id': cid})
    if not char:
        return 0
    
    rar = char.get('rarity', '🟢 Common')
    e = rar.split(' ')[0] if ' ' in rar else '🟢'
    rv = RARITY_ORDER.get(e, 99)
    
    higher = await collection.count_documents({
        '$expr': {
            '$lt': [
                {'$indexOfArray': [list(RARITY_ORDER.values()), {'$arrayElemAt': [{'$split': ['$rarity', ' ']}, 0]}]},
                rv
            ]
        }
    })
    
    rank = higher + 1
    rank_cache[k] = rank
    return rank

async def get_owners(cid: str, lim: int = 150) -> List[Dict]:
    k = f"ow{cid}{lim}"
    if k in owner_cache:
        return owner_cache[k]
    
    pipe = [
        {'$match': {'characters.id': cid}},
        {'$project': {
            'id': 1, 'first_name': 1, 'username': 1,
            'count': {'$size': {'$filter': {'input': '$characters', 'as': 'c', 'cond': {'$eq': ['$$c.id', cid]}}}},
            'total': {'$size': {'$ifNull': ['$characters', []]}}
        }},
        {'$sort': {'count': DESCENDING, 'total': DESCENDING}},
        {'$limit': lim}
    ]
    
    u = await user_collection.aggregate(pipe).to_list(length=lim)
    owner_cache[k] = u
    return u

async def get_user(uid: int) -> Optional[Dict]:
    k = f"u{uid}"
    if k in user_cache:
        return user_cache[k]
    u = await user_collection.find_one({'id': uid})
    if u:
        user_cache[k] = u
    return u

async def get_user_stats(uid: int) -> Dict:
    k = f"st{uid}"
    if k in stats_cache:
        return stats_cache[k]
    
    usr = await get_user(uid)
    if not usr:
        return {'unique': 0, 'total': 0, 'animes': 0, 'rarity_dist': {}}
    
    chars = usr.get('characters', [])
    uids = set()
    animes = set()
    rar_dist = defaultdict(int)
    
    for c in chars:
        if c.get('id'):
            uids.add(c.get('id'))
        if c.get('anime'):
            animes.add(c.get('anime'))
        r = c.get('rarity', '🟢 Common')
        e = r.split(' ')[0] if ' ' in r else '🟢'
        rar_dist[e] += 1
    
    stats = {
        'unique': len(uids),
        'total': len(chars),
        'animes': len(animes),
        'rarity_dist': dict(rar_dist)
    }
    stats_cache[k] = stats
    return stats

async def get_user_rank(uid: int) -> Tuple[int, int]:
    k = f"ur{uid}"
    if k in rank_cache:
        return rank_cache[k]
    
    pipe = [
        {'$project': {'id': 1, 'count': {'$size': {'$ifNull': ['$characters', []]}}}},
        {'$sort': {'count': DESCENDING}}
    ]
    
    all_users = await user_collection.aggregate(pipe).to_list(length=None)
    
    for idx, u in enumerate(all_users, 1):
        if u.get('id') == uid:
            rank = (idx, len(all_users))
            rank_cache[k] = rank
            return rank
    
    return (0, 0)

async def search_char(q: str, lim: int = 400) -> List[Dict]:
    k = f"s{q}{lim}"
    if k in search_cache:
        return search_cache[k]
    
    rx = re.compile(re.escape(q), re.IGNORECASE)
    ch = await collection.find({'$or': [{'name': rx}, {'anime': rx}, {'id': rx}]}).limit(lim).to_list(length=lim)
    search_cache[k] = ch
    return ch

async def get_all(lim: int = 400) -> List[Dict]:
    if 'all' in char_cache:
        return char_cache['all']
    ch = await collection.find({}).limit(lim).to_list(length=lim)
    char_cache['all'] = ch
    return ch

async def col_caption(ch: Dict, u: Dict, fav: bool, stats: Dict, rank: Tuple[int, int]) -> str:
    cid = ch.get('id', '?')
    nm = ch.get('name', '?')
    an = ch.get('anime', '?')
    rar = ch.get('rarity', '🟢 Common')
    vid = ch.get('is_video', False)
    
    e, t = parse_rar(rar)
    uc = sum(1 for c in u.get('characters', []) if c.get('id') == cid)
    ua = sum(1 for c in u.get('characters', []) if c.get('anime') == an)
    at = await a_count(an)
    gc = await g_count(cid)
    
    fn = u.get('first_name', 'User')
    uid = u.get('id')
    
    unique = stats.get('unique', 0)
    total = stats.get('total', 0)
    animes = stats.get('animes', 0)
    
    rank_pos, rank_total = rank
    rank_pct = int((1 - (rank_pos / rank_total)) * 100) if rank_total > 0 else 0
    
    cap = (
        f"<b>{'💖 ' if fav else ''}{escape(nm)}</b>\n"
        f"<a href='tg://user?id={uid}'>{escape(trunc(fn, 15))}</a> "
        f"<code>{unique}/{total}</code> <code>{animes}🎴</code>\n"
        f"#{rank_pos} {sc('top')} {rank_pct}%\n\n"
        f"<code>{cid}</code> {e} {sc(trunc(t, 12))}\n"
        f"<code>{trunc(escape(an), 18)}</code> {ua}/{at}\n"
        f"{'🎥' if vid else '🖼'} x{uc} • {sc('grabbed')} {gc}x"
    )
    
    if fav:
        cap += f" 💖"
    
    return cap

async def glob_caption(ch: Dict, total_chars: int) -> str:
    cid = ch.get('id', '?')
    nm = ch.get('name', '?')
    an = ch.get('anime', '?')
    rar = ch.get('rarity', '🟢 Common')
    vid = ch.get('is_video', False)
    
    e, t = parse_rar(rar)
    gc = await g_count(cid)
    at = await a_count(an)
    char_rank = await get_char_rank(cid)
    
    owners = await get_owners(cid, lim=1)
    top_owner = None
    if owners:
        top_owner = owners[0]
    
    cap = (
        f"<b>{escape(nm)}</b>\n"
        f"<code>{total_chars}</code> {sc('available')} • #{char_rank} {sc('rank')}\n\n"
        f"<code>{cid}</code> {e} {sc(trunc(t, 12))}\n"
        f"<code>{trunc(escape(an), 18)}</code> {at}🎴\n"
        f"{'🎥' if vid else '🖼'} • {sc('grabbed')} {gc}x\n"
    )
    
    if top_owner:
        tfn = trunc(escape(top_owner.get('first_name', 'User')), 12)
        tc = top_owner.get('count', 0)
        cap += f"\n🏆 {tfn} x{tc}"
    
    return cap

async def own_caption(ch: Dict, us: List[Dict]) -> str:
    cid = ch.get('id', '?')
    nm = ch.get('name', '?')
    an = ch.get('anime', '?')
    e, t = parse_rar(ch.get('rarity', '🟢 Common'))
    gc = await g_count(cid)
    
    cap = (
        f"<b>{escape(nm)}</b>\n"
        f"{sc('top owners')} {len(us)}\n\n"
        f"<code>{cid}</code> {e} {sc(trunc(t, 12))}\n"
        f"<code>{trunc(escape(an), 18)}</code>\n\n"
    )
    
    med = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, u in enumerate(us[:35], 1):
        m = med.get(i, f"{i}.")
        fn = trunc(escape(u.get('first_name', 'User')), 13)
        tc = u.get('total', 0)
        cap += f"{m} {fn} x{u.get('count', 0)} ({tc})\n"
    
    cap += f"\n{sc('total grabbed')} {gc}x"
    if len(us) > 35:
        cap += f" +{len(us)-35}"
    
    return cap

async def stat_caption(ch: Dict, us: List[Dict]) -> str:
    cid = ch.get('id', '?')
    nm = ch.get('name', '?')
    an = ch.get('anime', '?')
    e, t = parse_rar(ch.get('rarity', '🟢 Common'))
    gc = await g_count(cid)
    at = await a_count(an)
    uo = len(us)
    avg = round(gc / uo, 1) if uo > 0 else 0
    char_rank = await get_char_rank(cid)
    
    cap = (
        f"<b>{escape(nm)}</b>\n"
        f"{sc('statistics')} #{char_rank}\n\n"
        f"<code>{cid}</code> {e} {sc(trunc(t, 12))}\n"
        f"<code>{trunc(escape(an), 18)}</code>\n\n"
        f"{sc('grabbed')} {gc}x {sc('owners')} {uo}\n"
        f"{sc('average')} {avg}x {sc('in anime')} {at}\n"
    )
    
    if us:
        cap += f"\n{sc('top')}\n"
        for i, u in enumerate(us[:12], 1):
            fn = trunc(escape(u.get('first_name', 'User')), 11)
            cap += f"{i}. {fn} x{u.get('count', 0)}\n"
    
    return cap

async def compare_caption(ch: Dict, uid1: int, uid2: int) -> str:
    cid = ch.get('id', '?')
    nm = ch.get('name', '?')
    
    u1 = await get_user(uid1)
    u2 = await get_user(uid2)
    
    if not u1 or not u2:
        return "Users not found"
    
    u1c = sum(1 for c in u1.get('characters', []) if c.get('id') == cid)
    u2c = sum(1 for c in u2.get('characters', []) if c.get('id') == cid)
    
    s1 = await get_user_stats(uid1)
    s2 = await get_user_stats(uid2)
    
    cap = (
        f"<b>{escape(nm)}</b>\n{sc('comparison')}\n\n"
        f"<a href='tg://user?id={uid1}'>{escape(trunc(u1.get('first_name', 'User1'), 10))}</a> x{u1c} ({s1['unique']}/{s1['total']})\n"
        f"<a href='tg://user?id={uid2}'>{escape(trunc(u2.get('first_name', 'User2'), 10))}</a> x{u2c} ({s2['unique']}/{s2['total']})\n"
    )
    
    return cap

async def inlinequery(update: Update, context) -> None:
    q = update.inline_query.query
    off = int(update.inline_query.offset) if update.inline_query.offset else 0
    uid = update.inline_query.from_user.id
    
    try:
        all_ch = []
        usr = None
        is_col = False
        stats = None
        rank = (0, 0)
        filter_mode = None
        
        if q.startswith('collection.'):
            is_col = True
            pts = q.split(' ', 1)
            tid = pts[0].split('.')[1]
            srch = pts[1].strip() if len(pts) > 1 else ''
            
            if srch.startswith('-rare'):
                filter_mode = 'rare'
                srch = srch.replace('-rare', '').strip()
            elif srch.startswith('-video'):
                filter_mode = 'video'
                srch = srch.replace('-video', '').strip()
            elif srch.startswith('-new'):
                filter_mode = 'new'
                srch = srch.replace('-new', '').strip()
            
            if not tid.isdigit():
                await update.inline_query.answer([], cache_time=5)
                return
            
            ti = int(tid)
            usr = await get_user(ti)
            
            if not usr:
                await update.inline_query.answer([
                    InlineQueryResultArticle(
                        id="nouser",
                        title="User Not Found",
                        description="Start collecting characters first",
                        input_message_content=InputTextMessageContent(
                            f"<b>{sc('user not found')}</b>\n{sc('start collecting characters')}",
                            parse_mode=ParseMode.HTML
                        )
                    )
                ], cache_time=5)
                return
            
            stats = await get_user_stats(ti)
            rank = await get_user_rank(ti)
            
            cd = {}
            for c in usr.get('characters', []):
                if isinstance(c, dict) and c.get('id'):
                    ci = c.get('id')
                    if ci not in cd:
                        cd[ci] = c
            
            all_ch = list(cd.values())
            
            if filter_mode == 'rare':
                all_ch = [c for c in all_ch if parse_rar(c.get('rarity', '🟢 Common'))[0] in FILTERS['rare']]
            elif filter_mode == 'video':
                all_ch = [c for c in all_ch if c.get('is_video', False)]
            elif filter_mode == 'new':
                all_ch = sorted(all_ch, key=lambda x: str(x.get('_id', '')), reverse=True)
            
            fv = usr.get('favorites')
            fvc = None
            
            if fv:
                if isinstance(fv, dict):
                    fi = fv.get('id')
                    if any(c.get('id') == fi for c in all_ch):
                        fvc = fv
                    else:
                        await user_collection.update_one({'id': ti}, {'$unset': {'favorites': ""}})
                        user_cache.pop(f"u{ti}", None)
                elif isinstance(fv, str):
                    fvc = next((c for c in all_ch if c.get('id') == fv), None)
                    if not fvc:
                        await user_collection.update_one({'id': ti}, {'$unset': {'favorites': ""}})
                        user_cache.pop(f"u{ti}", None)
            
            if srch:
                rx = re.compile(re.escape(srch), re.IGNORECASE)
                all_ch = [c for c in all_ch if rx.search(c.get('name', '')) or rx.search(c.get('anime', '')) or rx.search(c.get('id', ''))]
            
            if not srch and fvc and not filter_mode:
                all_ch = [c for c in all_ch if c.get('id') != fvc.get('id')]
                all_ch.insert(0, fvc)
            else:
                all_ch.sort(key=rar_val)
        else:
            srch = q
            
            if srch.startswith('-rare'):
                filter_mode = 'rare'
                srch = srch.replace('-rare', '').strip()
            elif srch.startswith('-video'):
                filter_mode = 'video'
                srch = srch.replace('-video', '').strip()
            elif srch.startswith('-new'):
                filter_mode = 'new'
                srch = srch.replace('-new', '').strip()
            
            all_ch = await search_char(srch) if srch else await get_all()
            
            if filter_mode == 'rare':
                all_ch = [c for c in all_ch if parse_rar(c.get('rarity', '🟢 Common'))[0] in FILTERS['rare']]
            elif filter_mode == 'video':
                all_ch = [c for c in all_ch if c.get('is_video', False)]
            elif filter_mode == 'new':
                all_ch = sorted(all_ch, key=lambda x: str(x.get('_id', '')), reverse=True)
            
            all_ch.sort(key=rar_val)
        
        all_ch = dedupe_chars(all_ch)
        
        total_chars = len(all_ch)
        chs = all_ch[off:off+50]
        
        more = len(all_ch) > off + 50
        nxt = str(off + 50) if more else ""
        
        res = []
        for ch in chs:
            ci = ch.get('id')
            if not ci:
                continue
            
            nm = ch.get('name', '?')
            an = ch.get('anime', '?')
            img = ch.get('img_url', '')
            vid = ch.get('is_video', False)
            e, rt = parse_rar(ch.get('rarity', '🟢 Common'))
            
            fav = False
            if is_col and usr and usr.get('favorites'):
                fv = usr.get('favorites')
                if isinstance(fv, dict) and fv.get('id') == ci:
                    fav = True
                elif isinstance(fv, str) and fv == ci:
                    fav = True
            
            if is_col and usr and stats:
                cap = await col_caption(ch, usr, fav, stats, rank)
            else:
                cap = await glob_caption(ch, total_chars)
            
            kbd = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"🏆 {sc('owners')}", callback_data=f"o.{ci}"),
                 InlineKeyboardButton(f"📊 {sc('stats')}", callback_data=f"s.{ci}")],
                [InlineKeyboardButton(f"🔗 {sc('share')}", switch_inline_query=f"{ci}"),
                 InlineKeyboardButton(f"🆚 {sc('compare')}", callback_data=f"c.{ci}.{uid}")]
            ])
            
            rid = f"{ci}{off}{int(time.time()*1000)}"
            ttl = f"{'💖' if fav else ''}{e} {trunc(nm, 26)}"
            dsc = f"{trunc(an, 20)} {'🎥' if vid else '🖼'} {trunc(rt, 10)}"
            
            if vid:
                res.append(InlineQueryResultVideo(
                    id=rid, video_url=img, mime_type="video/mp4", thumbnail_url=img,
                    title=ttl, description=dsc, caption=cap, parse_mode=ParseMode.HTML, reply_markup=kbd
                ))
            else:
                res.append(InlineQueryResultPhoto(
                    id=rid, photo_url=img, thumbnail_url=img,
                    title=ttl, description=dsc, caption=cap, parse_mode=ParseMode.HTML, reply_markup=kbd
                ))
        
        await update.inline_query.answer(res, next_offset=nxt, cache_time=5, is_personal=is_col)
    
    except:
        import traceback
        traceback.print_exc()
        await update.inline_query.answer([], cache_time=5)

async def show_owners(update: Update, context) -> None:
    q = update.callback_query
    await q.answer()
    
    try:
        ci = q.data.split('.')[1]
        ch = await collection.find_one({'id': ci})
        
        if not ch:
            await q.answer("Character not found", show_alert=True)
            return
        
        us = await get_owners(ci)
        
        if not us:
            await q.answer("No owners yet", show_alert=True)
            return
        
        cap = await own_caption(ch, us)
        kbd = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"⬅️ {sc('back')}", callback_data=f"b.{ci}"),
             InlineKeyboardButton(f"📊 {sc('stats')}", callback_data=f"s.{ci}")],
            [InlineKeyboardButton(f"🔗 {sc('share')}", switch_inline_query=f"{ci}")]
        ])
        
        await q.edit_message_caption(caption=cap, parse_mode=ParseMode.HTML, reply_markup=kbd)
    except:
        import traceback
        traceback.print_exc()
        await q.answer("Error loading owners", show_alert=True)

async def back_card(update: Update, context) -> None:
    q = update.callback_query
    await q.answer()
    
    try:
        ci = q.data.split('.')[1]
        ch = await collection.find_one({'id': ci})
        
        if not ch:
            await q.answer("Character not found", show_alert=True)
            return
        
        total = len(await get_all())
        cap = await glob_caption(ch, total)
        kbd = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🏆 {sc('owners')}", callback_data=f"o.{ci}"),
             InlineKeyboardButton(f"📊 {sc('stats')}", callback_data=f"s.{ci}")],
            [InlineKeyboardButton(f"🔗 {sc('share')}", switch_inline_query=f"{ci}"),
             InlineKeyboardButton(f"🆚 {sc('compare')}", callback_data=f"c.{ci}.{q.from_user.id}")]
        ])
        
        await q.edit_message_caption(caption=cap, parse_mode=ParseMode.HTML, reply_markup=kbd)
    except:
        import traceback
        traceback.print_exc()
        await q.answer("Error", show_alert=True)

async def show_stats(update: Update, context) -> None:
    q = update.callback_query
    await q.answer()
    
    try:
        ci = q.data.split('.')[1]
        ch = await collection.find_one({'id': ci})
        
        if not ch:
            await q.answer("Character not found", show_alert=True)
            return
        
        us = await get_owners(ci)
        cap = await stat_caption(ch, us)
        
        kbd = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"⬅️ {sc('back')}", callback_data=f"b.{ci}"),
             InlineKeyboardButton(f"🏆 {sc('owners')}", callback_data=f"o.{ci}")],
            [InlineKeyboardButton(f"🔗 {sc('share')}", switch_inline_query=f"{ci}")]
        ])
        
        await q.edit_message_caption(caption=cap, parse_mode=ParseMode.HTML, reply_markup=kbd)
    except:
        import traceback
        traceback.print_exc()
        await q.answer("Error loading stats", show_alert=True)

async def compare_users(update: Update, context) -> None:
    q = update.callback_query
    await q.answer()
    
    try:
        parts = q.data.split('.')
        ci = parts[1]
        uid1 = int(parts[2])
        uid2 = q.from_user.id
        
        ch = await collection.find_one({'id': ci})
        
        if not ch:
            await q.answer("Character not found", show_alert=True)
            return
        
        cap = await compare_caption(ch, uid1, uid2)
        kbd = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"⬅️ {sc('back')}", callback_data=f"b.{ci}"),
             InlineKeyboardButton(f"📊 {sc('stats')}", callback_data=f"s.{ci}")],
            [InlineKeyboardButton(f"🔗 {sc('share')}", switch_inline_query=f"{ci}")]
        ])
        
        await q.edit_message_caption(caption=cap, parse_mode=ParseMode.HTML, reply_markup=kbd)
    except:
        import traceback
        traceback.print_exc()
        await q.answer("Error comparing", show_alert=True)

application.add_handler(InlineQueryHandler(inlinequery, block=False))
application.add_handler(CallbackQueryHandler(show_owners, pattern=r'^o\.', block=False))
application.add_handler(CallbackQueryHandler(back_card, pattern=r'^b\.', block=False))
application.add_handler(CallbackQueryHandler(show_stats, pattern=r'^s\.', block=False))
application.add_handler(CallbackQueryHandler(compare_users, pattern=r'^c\.', block=False))