import re
import time
import asyncio
from html import escape
from typing import List, Dict, Optional, Tuple, Set
from cachetools import TTLCache, LRUCache
from pymongo import ASCENDING, DESCENDING, UpdateOne
from functools import lru_cache, wraps
from collections import defaultdict
import hashlib

from telegram import Update, InlineQueryResultPhoto, InlineQueryResultVideo, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, InlineQueryResultCachedPhoto, InlineQueryResultCachedVideo
from telegram.ext import InlineQueryHandler, CallbackQueryHandler
from telegram.constants import ParseMode

from shivu import application, db

collection = db['anime_characters_lol']
user_collection = db['user_collection_lmaoooo']

RARITY_MAP = {
    "mythic": ("🏵", 1), "premium": ("🔮", 2), "legendary": ("🟡", 3),
    "events": ("🎗", 4), "neon": ("💫", 5), "manga": ("✨", 6),
    "celestial": ("🎐", 7), "cosplay": ("🎭", 8), "special": ("💮", 9),
    "amv": ("🎥", 10), "erotic": ("💋", 11), "tiny": ("👼", 12),
    "valentine": ("💝", 13), "halloween": ("🎃", 14), "christmas": ("🎄", 15),
    "summer": ("🌤", 16), "winter": ("☃️", 17), "monsoon": ("☔️", 18),
    "rare": ("🟣", 19), "common": ("🟢", 20)
}

try:
    collection.create_index([('id', ASCENDING)], background=True)
    collection.create_index([('anime', ASCENDING)], background=True)
    collection.create_index([('name', 'text'), ('anime', 'text')], background=True)
    collection.create_index([('rarity', ASCENDING)], background=True)
    collection.create_index([('is_video', ASCENDING)], background=True)
    user_collection.create_index([('id', ASCENDING)], background=True)
    user_collection.create_index([('characters.id', ASCENDING)], background=True)
except:
    pass

mega_cache = TTLCache(maxsize=100000, ttl=21600)
user_cache = TTLCache(maxsize=60000, ttl=2400)
query_cache = LRUCache(maxsize=25000)
result_cache = TTLCache(maxsize=40000, ttl=1200)
stat_cache = TTLCache(maxsize=20000, ttl=4800)
rank_cache = TTLCache(maxsize=10000, ttl=5400)

CAPS = str.maketrans('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', 'ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ')

def cache_key(*args):
    return hashlib.md5(str(args).encode()).hexdigest()

@lru_cache(maxsize=32768)
def sc(t: str) -> str:
    return t.translate(CAPS)

@lru_cache(maxsize=16384)
def parse_rar(r: str) -> Tuple[str, str, int]:
    if not r or not isinstance(r, str):
        return "🟢", "Common", 20
    
    for key, (emoji, val) in RARITY_MAP.items():
        if key in r.lower():
            return emoji, r.split(' ', 1)[-1] if ' ' in r else key.title(), val
    
    parts = r.split(' ', 1)
    return parts[0] if parts else "🟢", parts[1] if len(parts) > 1 else "Common", 20

def trunc(t: str, l: int = 18) -> str:
    return t[:l-2] + '..' if len(t) > l else t

def dedupe(chars: List[Dict]) -> List[Dict]:
    seen, result = set(), []
    for c in chars:
        cid = c.get('id')
        if cid and cid not in seen:
            seen.add(cid)
            result.append(c)
    return result

async def bulk_count(ids: List[str]) -> Dict[str, int]:
    k = cache_key('bulk', tuple(sorted(ids)))
    if k in result_cache:
        return result_cache[k]
    
    pipe = [
        {'$match': {'characters.id': {'$in': ids}}},
        {'$unwind': '$characters'},
        {'$match': {'characters.id': {'$in': ids}}},
        {'$group': {'_id': '$characters.id', 'count': {'$sum': 1}}}
    ]
    
    results = await user_collection.aggregate(pipe).to_list(None)
    counts = {r['_id']: r['count'] for r in results}
    result_cache[k] = counts
    return counts

async def get_user(uid: int) -> Optional[Dict]:
    k = f"u{uid}"
    if k in user_cache:
        return user_cache[k]
    
    u = await user_collection.find_one({'id': uid}, {'_id': 0})
    if u:
        user_cache[k] = u
    return u

async def get_stats(uid: int) -> Dict:
    k = f"s{uid}"
    if k in stat_cache:
        return stat_cache[k]
    
    pipe = [
        {'$match': {'id': uid}},
        {'$project': {
            'total': {'$size': {'$ifNull': ['$characters', []]}},
            'unique': {'$size': {'$setUnion': [{'$map': {'input': '$characters', 'as': 'c', 'in': '$$c.id'}}]}},
            'animes': {'$size': {'$setUnion': [{'$map': {'input': '$characters', 'as': 'c', 'in': '$$c.anime'}}]}}
        }}
    ]
    
    result = await user_collection.aggregate(pipe).to_list(1)
    stats = result[0] if result else {'total': 0, 'unique': 0, 'animes': 0}
    stat_cache[k] = stats
    return stats

async def get_rank(uid: int) -> Tuple[int, int, float]:
    k = f"r{uid}"
    if k in rank_cache:
        return rank_cache[k]
    
    pipe = [
        {'$project': {'id': 1, 'count': {'$size': {'$ifNull': ['$characters', []]}}}},
        {'$sort': {'count': -1}}
    ]
    
    rankings = await user_collection.aggregate(pipe).to_list(None)
    total = len(rankings)
    
    for idx, r in enumerate(rankings, 1):
        if r.get('id') == uid:
            pct = round((1 - idx/total) * 100, 1) if total > 0 else 0
            rank = (idx, total, pct)
            rank_cache[k] = rank
            return rank
    
    return (0, total, 0)

async def get_owners(cid: str, lim: int = 100) -> List[Dict]:
    k = f"o{cid}{lim}"
    if k in result_cache:
        return result_cache[k]
    
    pipe = [
        {'$match': {'characters.id': cid}},
        {'$project': {
            'id': 1, 'first_name': 1, 'username': 1,
            'count': {'$size': {'$filter': {'input': '$characters', 'as': 'c', 'cond': {'$eq': ['$$c.id', cid]}}}},
            'total': {'$size': {'$ifNull': ['$characters', []]}}
        }},
        {'$sort': {'count': -1, 'total': -1}},
        {'$limit': lim}
    ]
    
    owners = await user_collection.aggregate(pipe).to_list(lim)
    result_cache[k] = owners
    return owners

async def search_chars(q: str, lim: int = 500) -> List[Dict]:
    k = cache_key('search', q, lim)
    if k in query_cache:
        return query_cache[k]
    
    if q:
        rx = re.compile(re.escape(q), re.IGNORECASE)
        chars = await collection.find(
            {'$or': [{'name': rx}, {'anime': rx}, {'id': rx}]},
            {'_id': 0}
        ).limit(lim).to_list(lim)
    else:
        chars = await collection.find({}, {'_id': 0}).limit(lim).to_list(lim)
    
    query_cache[k] = chars
    return chars

async def col_cap(ch: Dict, u: Dict, fav: bool, stats: Dict, rank: Tuple) -> str:
    cid = ch.get('id', '?')
    nm = ch.get('name', '?')
    an = ch.get('anime', '?')
    rar = ch.get('rarity', '🟢 Common')
    vid = ch.get('is_video', False)
    
    e, rt, rv = parse_rar(rar)
    uc = sum(1 for c in u.get('characters', []) if c.get('id') == cid)
    ua = sum(1 for c in u.get('characters', []) if c.get('anime') == an)
    
    fn = u.get('first_name', 'User')
    uid = u.get('id')
    unique = stats.get('unique', 0)
    total = stats.get('total', 0)
    animes = stats.get('animes', 0)
    rank_pos, rank_tot, pct = rank
    
    anime_info = await collection.count_documents({'anime': an})
    
    cap = (
        f"{'💖 ' if fav else ''}<b><u>{escape(nm)}</u></b>\n"
        f"╰┈➤ ✨ <b>Character Info</b>\n\n"
        f"👤 <a href='tg://user?id={uid}'><b>{escape(trunc(fn, 12))}</b></a>\n"
        f"📊 <code>{unique}</code>/<code>{total}</code> chars • <code>{animes}</code> anime\n"
        f"🏆 Rank <b>#{rank_pos}</b> • Top <b>{pct}%</b>\n\n"
        f"<blockquote>🆔 <code>{cid}</code>\n"
        f"{e} <b>{sc(trunc(rt, 10))}</b>\n"
        f"📺 <i>{trunc(escape(an), 16)}</i></blockquote>\n"
        f"📦 Collection: <b>{ua}</b>/<code>{anime_info}</code>\n"
        f"{'🎬' if vid else '🖼'} {'Video' if vid else 'Image'} • Owned <b>×{uc}</b>"
    )
    
    return cap

async def glob_cap(ch: Dict, total: int) -> str:
    cid = ch.get('id', '?')
    nm = ch.get('name', '?')
    an = ch.get('anime', '?')
    rar = ch.get('rarity', '🟢 Common')
    vid = ch.get('is_video', False)
    
    e, rt, rv = parse_rar(rar)
    
    owners = await get_owners(cid, 1)
    top = owners[0] if owners else None
    gc = sum(o.get('count', 0) for o in owners[:50])
    
    anime_info = await collection.count_documents({'anime': an})
    
    cap = (
        f"<b><u>{escape(nm)}</u></b>\n"
        f"╰┈➤ 🌐 <b>Global Database</b>\n\n"
        f"📚 <code>{total}</code> characters available\n\n"
        f"<blockquote>🆔 <code>{cid}</code>\n"
        f"{e} <b>{sc(trunc(rt, 10))}</b>\n"
        f"📺 <i>{trunc(escape(an), 16)}</i></blockquote>\n"
        f"📦 Anime Total: <code>{anime_info}</code>\n"
        f"{'🎬' if vid else '🖼'} {'Video' if vid else 'Image'}\n"
        f"🎯 Grabbed <b>{gc}×</b> times"
    )
    
    if top:
        cap += f"\n\n👑 <b>Top Owner:</b> {trunc(escape(top.get('first_name', 'User')), 10)} <b>×{top.get('count', 0)}</b>"
    
    return cap

async def own_cap(ch: Dict, owners: List[Dict]) -> str:
    cid = ch.get('id', '?')
    nm = ch.get('name', '?')
    an = ch.get('anime', '?')
    e, rt, rv = parse_rar(ch.get('rarity', '🟢 Common'))
    
    gc = sum(o.get('count', 0) for o in owners)
    
    cap = (
        f"<b><u>{escape(nm)}</u></b>\n"
        f"╰┈➤ 👥 <b>TOP OWNERS</b> ({len(owners)} users)\n\n"
        f"<blockquote>🆔 <code>{cid}</code>\n"
        f"{e} <b>{sc(trunc(rt, 10))}</b>\n"
        f"📺 <i>{trunc(escape(an), 16)}</i></blockquote>\n\n"
    )
    
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, o in enumerate(owners[:40], 1):
        medal = medals.get(i, f"<b>{i}.</b>")
        fn = trunc(escape(o.get('first_name', 'User')), 11)
        cap += f"{medal} {fn} <b>×{o.get('count', 0)}</b> of <code>{o.get('total', 0)}</code>\n"
    
    cap += f"\n✦ Total grabbed <b>{gc}×</b>"
    return cap

async def stat_cap(ch: Dict, owners: List[Dict]) -> str:
    cid = ch.get('id', '?')
    nm = ch.get('name', '?')
    an = ch.get('anime', '?')
    e, rt, rv = parse_rar(ch.get('rarity', '🟢 Common'))
    
    gc = sum(o.get('count', 0) for o in owners)
    uo = len(owners)
    avg = round(gc / uo, 1) if uo > 0 else 0
    anime_total = await collection.count_documents({'anime': an})
    
    cap = (
        f"<b><u>{escape(nm)}</u></b>\n"
        f"╰┈➤ 📊 <b>STATISTICS</b>\n\n"
        f"<blockquote>🆔 <code>{cid}</code>\n"
        f"{e} <b>{sc(trunc(rt, 10))}</b>\n"
        f"📺 <i>{trunc(escape(an), 16)}</i></blockquote>\n\n"
        f"🎯 Grabbed: <b>{gc}×</b>\n"
        f"👥 Owners: <code>{uo}</code> users\n"
        f"📈 Average: <b>{avg}×</b> per user\n"
        f"📚 Anime Total: <code>{anime_total}</code> chars"
    )
    
    if owners:
        cap += f"\n\n╰┈➤ 🏆 <b>Top Collectors</b>\n\n"
        for i, o in enumerate(owners[:15], 1):
            fn = trunc(escape(o.get('first_name', 'User')), 10)
            cap += f"<b>{i}.</b> {fn} <b>×{o.get('count', 0)}</b>\n"
    
    return cap

async def comp_cap(ch: Dict, u1: Dict, u2: Dict) -> str:
    cid = ch.get('id', '?')
    nm = ch.get('name', '?')
    
    u1c = sum(1 for c in u1.get('characters', []) if c.get('id') == cid)
    u2c = sum(1 for c in u2.get('characters', []) if c.get('id') == cid)
    
    s1 = await get_stats(u1.get('id'))
    s2 = await get_stats(u2.get('id'))
    
    r1 = await get_rank(u1.get('id'))
    r2 = await get_rank(u2.get('id'))
    
    cap = (
        f"<b><u>{escape(nm)}</u></b>\n"
        f"╰┈➤ ⚔️ <b>COMPARISON</b>\n\n"
        f"<blockquote expandable>👤 <a href='tg://user?id={u1['id']}'><b>{escape(trunc(u1.get('first_name', 'User1'), 9))}</b></a>\n"
        f"   • Owned: <b>×{u1c}</b>\n"
        f"   • Collection: <code>{s1['unique']}</code>/<code>{s1['total']}</code>\n"
        f"   • Rank: <b>#{r1[0]}</b></blockquote>\n\n"
        f"<b>VS</b>\n\n"
        f"<blockquote expandable>👤 <a href='tg://user?id={u2['id']}'><b>{escape(trunc(u2.get('first_name', 'User2'), 9))}</b></a>\n"
        f"   • Owned: <b>×{u2c}</b>\n"
        f"   • Collection: <code>{s2['unique']}</code>/<code>{s2['total']}</code>\n"
        f"   • Rank: <b>#{r2[0]}</b></blockquote>"
    )
    
    return cap

async def filter_chars(chars: List[Dict], mode: str) -> List[Dict]:
    if mode == 'rare':
        return [c for c in chars if parse_rar(c.get('rarity', ''))[2] <= 12]
    elif mode == 'video':
        return [c for c in chars if c.get('is_video', False)]
    elif mode == 'new':
        return sorted(chars, key=lambda x: str(x.get('_id', '')), reverse=True)
    elif mode == 'popular':
        ids = [c.get('id') for c in chars if c.get('id')]
        counts = await bulk_count(ids)
        return sorted(chars, key=lambda x: counts.get(x.get('id'), 0), reverse=True)
    return chars

async def inlinequery(update: Update, context) -> None:
    q = update.inline_query.query
    off = int(update.inline_query.offset) if update.inline_query.offset else 0
    uid = update.inline_query.from_user.id

    try:
        all_ch = []
        usr = None
        is_col = False
        stats = None
        rank = (0, 0, 0)
        fmode = None

        if q.startswith('collection.'):
            is_col = True
            pts = q.split(' ', 1)
            tid = pts[0].split('.')[1]
            srch = pts[1].strip() if len(pts) > 1 else ''

            for fm in ['rare', 'video', 'new', 'popular']:
                if srch.startswith(f'-{fm}'):
                    fmode = fm
                    srch = srch.replace(f'-{fm}', '').strip()
                    break

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
                        description="Start collecting characters",
                        input_message_content=InputTextMessageContent(
                            "user not found start collecting",
                            parse_mode=ParseMode.HTML
                        )
                    )
                ], cache_time=5)
                return

            stats = await get_stats(ti)
            rank = await get_rank(ti)

            cd = {}
            for c in usr.get('characters', []):
                if isinstance(c, dict) and c.get('id'):
                    ci = c.get('id')
                    if ci not in cd:
                        cd[ci] = c

            all_ch = list(cd.values())

            # ✨ APPLY SMODE RARITY FILTER FROM USER SETTINGS
            user_smode = usr.get('smode', 'default')
            
            if user_smode and user_smode != 'default':
                # Get rarity value from HAREM_MODE_MAPPING
                from shivu.modules.harem import HAREM_MODE_MAPPING
                rarity_value = HAREM_MODE_MAPPING.get(user_smode, None)
                
                if rarity_value:
                    # Filter characters by rarity
                    all_ch = [
                        c for c in all_ch 
                        if c.get('rarity') == rarity_value
                    ]

            if fmode:
                all_ch = await filter_chars(all_ch, fmode)

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

            if not srch and fvc and not fmode:
                all_ch = [c for c in all_ch if c.get('id') != fvc.get('id')]
                all_ch.insert(0, fvc)
            else:
                all_ch.sort(key=lambda x: parse_rar(x.get('rarity', ''))[2])
        else:
            srch = q

            for fm in ['rare', 'video', 'new', 'popular']:
                if srch.startswith(f'-{fm}'):
                    fmode = fm
                    srch = srch.replace(f'-{fm}', '').strip()
                    break

            all_ch = await search_chars(srch)

            if fmode:
                all_ch = await filter_chars(all_ch, fmode)

            all_ch.sort(key=lambda x: parse_rar(x.get('rarity', ''))[2])

        all_ch = dedupe(all_ch)

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
            e, rt, rv = parse_rar(ch.get('rarity', ''))

            fav = False
            if is_col and usr and usr.get('favorites'):
                fv = usr.get('favorites')
                if isinstance(fv, dict) and fv.get('id') == ci:
                    fav = True
                elif isinstance(fv, str) and fv == ci:
                    fav = True

            if is_col and usr and stats:
                cap = await col_cap(ch, usr, fav, stats, rank)
            else:
                cap = await glob_cap(ch, total_chars)

            kbd = InlineKeyboardMarkup([
                [InlineKeyboardButton(sc("owners"), callback_data=f"o.{ci}"),
                 InlineKeyboardButton(sc("stats"), callback_data=f"s.{ci}")],
                [InlineKeyboardButton(sc("share"), switch_inline_query=f"{ci}"),
                 InlineKeyboardButton(sc("compare"), callback_data=f"c.{ci}.{uid}")]
            ])

            rid = f"{ci}{off}{int(time.time()*1000)}"
            ttl = f"{'💖' if fav else ''}{e} {trunc(nm, 24)}"
            dsc = f"{trunc(an, 18)} {'video' if vid else 'image'} {trunc(rt, 8)}"

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
        ch = await collection.find_one({'id': ci}, {'_id': 0})
        
        if not ch:
            await q.answer("character not found", show_alert=True)
            return
        
        owners = await get_owners(ci, 150)
        
        if not owners:
            await q.answer("no owners yet", show_alert=True)
            return
        
        cap = await own_cap(ch, owners)
        kbd = InlineKeyboardMarkup([
            [InlineKeyboardButton(sc("back"), callback_data=f"b.{ci}"),
             InlineKeyboardButton(sc("stats"), callback_data=f"s.{ci}")],
            [InlineKeyboardButton(sc("share"), switch_inline_query=f"{ci}")]
        ])
        
        await q.edit_message_caption(caption=cap, parse_mode=ParseMode.HTML, reply_markup=kbd)
    except:
        import traceback
        traceback.print_exc()
        await q.answer("error", show_alert=True)

async def back_card(update: Update, context) -> None:
    q = update.callback_query
    await q.answer()
    
    try:
        ci = q.data.split('.')[1]
        ch = await collection.find_one({'id': ci}, {'_id': 0})
        
        if not ch:
            await q.answer("character not found", show_alert=True)
            return
        
        total = len(await search_chars(''))
        cap = await glob_cap(ch, total)
        kbd = InlineKeyboardMarkup([
            [InlineKeyboardButton(sc("owners"), callback_data=f"o.{ci}"),
             InlineKeyboardButton(sc("stats"), callback_data=f"s.{ci}")],
            [InlineKeyboardButton(sc("share"), switch_inline_query=f"{ci}"),
             InlineKeyboardButton(sc("compare"), callback_data=f"c.{ci}.{q.from_user.id}")]
        ])
        
        await q.edit_message_caption(caption=cap, parse_mode=ParseMode.HTML, reply_markup=kbd)
    except:
        import traceback
        traceback.print_exc()
        await q.answer("error", show_alert=True)

async def show_stats(update: Update, context) -> None:
    q = update.callback_query
    await q.answer()
    
    try:
        ci = q.data.split('.')[1]
        ch = await collection.find_one({'id': ci}, {'_id': 0})
        
        if not ch:
            await q.answer("character not found", show_alert=True)
            return
        
        owners = await get_owners(ci, 150)
        cap = await stat_cap(ch, owners)
        
        kbd = InlineKeyboardMarkup([
            [InlineKeyboardButton(sc("back"), callback_data=f"b.{ci}"),
             InlineKeyboardButton(sc("owners"), callback_data=f"o.{ci}")],
            [InlineKeyboardButton(sc("share"), switch_inline_query=f"{ci}")]
        ])
        
        await q.edit_message_caption(caption=cap, parse_mode=ParseMode.HTML, reply_markup=kbd)
    except:
        import traceback
        traceback.print_exc()
        await q.answer("error", show_alert=True)

async def compare_users(update: Update, context) -> None:
    q = update.callback_query
    await q.answer()
    
    try:
        parts = q.data.split('.')
        ci = parts[1]
        uid1 = int(parts[2])
        uid2 = q.from_user.id
        
        ch = await collection.find_one({'id': ci}, {'_id': 0})
        
        if not ch:
            await q.answer("character not found", show_alert=True)
            return
        
        u1 = await get_user(uid1)
        u2 = await get_user(uid2)
        
        if not u1 or not u2:
            await q.answer("user not found", show_alert=True)
            return
        
        cap = await comp_cap(ch, u1, u2)
        kbd = InlineKeyboardMarkup([
            [InlineKeyboardButton(sc("back"), callback_data=f"b.{ci}"),
             InlineKeyboardButton(sc("stats"), callback_data=f"s.{ci}")],
            [InlineKeyboardButton(sc("share"), switch_inline_query=f"{ci}")]
        ])
        
        await q.edit_message_caption(caption=cap, parse_mode=ParseMode.HTML, reply_markup=kbd)
    except:
        import traceback
        traceback.print_exc()
        await q.answer("error", show_alert=True)

application.add_handler(InlineQueryHandler(inlinequery, block=False))
application.add_handler(CallbackQueryHandler(show_owners, pattern=r'^o\.', block=False))
application.add_handler(CallbackQueryHandler(back_card, pattern=r'^b\.', block=False))
application.add_handler(CallbackQueryHandler(show_stats, pattern=r'^s\.', block=False))
application.add_handler(CallbackQueryHandler(compare_users, pattern=r'^c\.', block=False))