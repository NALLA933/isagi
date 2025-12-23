import re
import time
from html import escape
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from cachetools import TTLCache, LRUCache
from pymongo import ASCENDING, TEXT
from functools import lru_cache
import hashlib

from telegram import Update, InlineQueryResultPhoto, InlineQueryResultVideo, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, InlineQueryResultGif, InlineQueryResultCachedPhoto, SwitchInlineQueryChosenChat
from telegram.ext import InlineQueryHandler, CallbackQueryHandler, ChosenInlineResultHandler
from telegram.constants import ParseMode

from shivu import application, db

collection = db['anime_characters_lol']
user_collection = db['user_collection_lmaoooo']

@dataclass
class Rarity:
    emoji: str
    name: str
    value: int

@dataclass
class Character:
    id: str
    name: str
    anime: str
    img_url: str
    rarity: str
    is_video: bool = False
    
    @property
    def rarity_info(self) -> Rarity:
        return parse_rar(self.rarity)

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
    collection.create_index([('id', ASCENDING)], unique=True, background=True)
    collection.create_index([('rarity', ASCENDING), ('anime', ASCENDING)], background=True)
    collection.create_index([('name', TEXT), ('anime', TEXT)], background=True)
    user_collection.create_index([('id', ASCENDING)], unique=True, background=True)
    user_collection.create_index([('characters.id', ASCENDING)], background=True, sparse=True)
except:
    pass

char_cache = TTLCache(maxsize=80000, ttl=2400)
user_cache = TTLCache(maxsize=50000, ttl=1200)
query_cache = LRUCache(maxsize=15000)
count_cache = TTLCache(maxsize=30000, ttl=1800)
feedback_cache = TTLCache(maxsize=10000, ttl=3600)

CAPS = str.maketrans(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ',
    'ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ'
)

@lru_cache(maxsize=65536)
def sc(t: str) -> str:
    return t.translate(CAPS)

@lru_cache(maxsize=32768)
def parse_rar(r: str) -> Rarity:
    if not r or not isinstance(r, str):
        return Rarity("🟢", "Common", 20)
    
    r_lower = r.lower()
    for key, (emoji, val) in RARITY_MAP.items():
        if key in r_lower:
            name = r.split(' ', 1)[-1] if ' ' in r else key.title()
            return Rarity(emoji, name, val)
    
    parts = r.split(' ', 1)
    return Rarity(parts[0] if parts else "🟢", parts[1] if len(parts) > 1 else "Common", 20)

def trunc(t: str, l: int = 22) -> str:
    return t[:l-2] + '..' if len(t) > l else t

def cache_key(*args) -> str:
    return hashlib.md5(str(args).encode()).hexdigest()

async def get_user(uid: int) -> Optional[Dict]:
    k = f"u{uid}"
    if k in user_cache:
        return user_cache[k]
    u = await user_collection.find_one({'id': uid}, {'_id': 0})
    if u:
        user_cache[k] = u
    return u

async def bulk_count(ids: List[str]) -> Dict[str, int]:
    if not ids:
        return {}
    k = cache_key('bulk', tuple(sorted(ids[:150])))
    if k in count_cache:
        return count_cache[k]
    
    pipe = [
        {'$match': {'characters.id': {'$in': ids}}},
        {'$project': {'characters.id': 1}},
        {'$unwind': '$characters'},
        {'$match': {'characters.id': {'$in': ids}}},
        {'$group': {'_id': '$characters.id', 'count': {'$sum': 1}}}
    ]
    
    results = await user_collection.aggregate(pipe).to_list(None)
    counts = {r['_id']: r['count'] for r in results}
    count_cache[k] = counts
    return counts

async def get_owners(cid: str, lim: int = 100) -> List[Dict]:
    k = f"o{cid}{lim}"
    if k in count_cache:
        return count_cache[k]
    
    pipe = [
        {'$match': {'characters.id': cid}},
        {'$project': {
            'id': 1,
            'first_name': 1,
            'username': 1,
            'characters': {'$filter': {
                'input': '$characters',
                'as': 'c',
                'cond': {'$eq': ['$$c.id', cid]}
            }}
        }},
        {'$addFields': {'count': {'$size': '$characters'}}},
        {'$sort': {'count': -1}},
        {'$limit': lim},
        {'$project': {'characters': 0}}
    ]
    
    owners = await user_collection.aggregate(pipe).to_list(lim)
    count_cache[k] = owners
    return owners

async def search_chars(q: str, lim: int = 1000) -> List[Dict]:
    k = cache_key('search', q, lim)
    if k in query_cache:
        return query_cache[k]
    
    if q:
        chars = await collection.find(
            {'$text': {'$search': q}},
            {'_id': 0, 'score': {'$meta': 'textScore'}}
        ).sort([('score', {'$meta': 'textScore'})]).limit(lim).to_list(lim)
        
        if not chars:
            rx = re.compile(f'^{re.escape(q)}', re.IGNORECASE)
            chars = await collection.find(
                {'$or': [{'name': rx}, {'anime': rx}, {'id': q}]},
                {'_id': 0}
            ).limit(lim).to_list(lim)
    else:
        chars = await collection.find({}, {'_id': 0}).limit(lim).to_list(lim)
    
    query_cache[k] = chars
    return chars

async def filter_chars(chars: List[Dict], mode: str) -> List[Dict]:
    if mode == 'rare':
        return [c for c in chars if parse_rar(c.get('rarity', '')).value <= 12]
    elif mode == 'video':
        return [c for c in chars if c.get('is_video', False)]
    elif mode == 'new':
        return sorted(chars, key=lambda x: str(x.get('_id', '')), reverse=True)
    elif mode == 'popular':
        ids = [c.get('id') for c in chars if c.get('id')]
        if ids:
            counts = await bulk_count(ids)
            return sorted(chars, key=lambda x: counts.get(x.get('id'), 0), reverse=True)
    elif mode == 'trending':
        ids = [c.get('id') for c in chars if c.get('id')]
        if ids:
            recent_picks = {}
            for cid in ids:
                recent = feedback_cache.get(f'pick_{cid}', 0)
                if recent > 0:
                    recent_picks[cid] = recent
            return sorted(chars, key=lambda x: recent_picks.get(x.get('id'), 0), reverse=True)
    return chars

def dedupe(chars: List[Dict]) -> List[Dict]:
    seen, result = set(), []
    for c in chars:
        cid = c.get('id')
        if cid and cid not in seen:
            seen.add(cid)
            result.append(c)
    return result

def minimal_caption(ch: Dict, is_fav: bool = False, show_stats: bool = False, stats: Dict = None) -> str:
    cid = ch.get('id', '??')
    nm = ch.get('name', 'Unknown')
    an = ch.get('anime', 'Unknown')
    r = parse_rar(ch.get('rarity', ''))
    
    cap = f"""{'💖 ' if is_fav else ''}<b>{escape(nm)}</b>

{r.emoji} <code>{sc(r.name)}</code> • 🆔 <code>{cid}</code>
📺 <i>{escape(trunc(an, 38))}</i>"""
    
    if show_stats and stats:
        cap += f"\n\n👥 <code>{stats.get('owners', 0)}</code> ᴏᴡɴᴇʀs • 🎯 <code>{stats.get('total', 0)}×</code> ɢʀᴀʙʙᴇᴅ"
    
    return cap

def owners_caption(ch: Dict, owners: List[Dict]) -> str:
    nm = ch.get('name', 'Unknown')
    total = sum(o.get('count', 0) for o in owners)
    
    cap = f"<b>{escape(nm)}</b>\n\n👥 <b>{len(owners)}</b> ᴏᴡɴᴇʀs • <b>{total}×</b> ɢʀᴀʙʙᴇᴅ\n\n"
    
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, o in enumerate(owners[:30], 1):
        medal = medals.get(i, f"{i}.")
        fn = escape(trunc(o.get('first_name', 'User'), 18))
        cap += f"{medal} {fn} • <code>×{o.get('count', 0)}</code>\n"
    
    return cap

def stats_caption(ch: Dict, owners: List[Dict]) -> str:
    nm = ch.get('name', 'Unknown')
    total = sum(o.get('count', 0) for o in owners)
    avg = round(total / len(owners), 1) if owners else 0
    
    cap = f"<b>{escape(nm)}</b>\n\n📊 <b>sᴛᴀᴛɪsᴛɪᴄs</b>\n"
    cap += f"🎯 <code>{total}×</code> ɢʀᴀʙʙᴇᴅ\n"
    cap += f"👥 <code>{len(owners)}</code> ᴏᴡɴᴇʀs\n"
    cap += f"📈 <code>{avg}×</code> ᴀᴠɢ\n"
    
    if owners:
        cap += f"\n🏆 <b>ᴛᴏᴘ ᴄᴏʟʟᴇᴄᴛᴏʀs</b>\n"
        for i, o in enumerate(owners[:10], 1):
            fn = escape(trunc(o.get('first_name', 'User'), 18))
            cap += f"{i}. {fn} • <code>×{o.get('count', 0)}</code>\n"
    
    return cap

def create_inline_keyboard(cid: str, show_share_options: bool = True) -> InlineKeyboardMarkup:
    buttons = [[
        InlineKeyboardButton("👥 ᴏᴡɴᴇʀs", callback_data=f"o.{cid}"),
        InlineKeyboardButton("📊 sᴛᴀᴛs", callback_data=f"s.{cid}")
    ]]
    
    if show_share_options:
        buttons.append([
            InlineKeyboardButton(
                "📤 sʜᴀʀᴇ ᴛᴏ ᴄʜᴀᴛ",
                switch_inline_query_chosen_chat=SwitchInlineQueryChosenChat(
                    query=cid,
                    allow_user_chats=True,
                    allow_group_chats=True,
                    allow_channel_chats=False
                )
            )
        ])
        buttons.append([
            InlineKeyboardButton("🔍 sᴇᴀʀᴄʜ sɪᴍɪʟᴀʀ", switch_inline_query_current_chat=f"{cid} ")
        ])
    
    return InlineKeyboardMarkup(buttons)

async def inlinequery(update: Update, context) -> None:
    q = update.inline_query.query
    off = int(update.inline_query.offset) if update.inline_query.offset else 0
    uid = update.inline_query.from_user.id
    query_id = update.inline_query.id
    
    try:
        is_collection = False
        usr = None
        search_query = q
        filter_mode = None
        
        if q.startswith('collection.'):
            is_collection = True
            parts = q.split(' ', 1)
            target_id = parts[0].split('.')[1]
            search_query = parts[1].strip() if len(parts) > 1 else ''
            
            for mode in ['rare', 'video', 'new', 'popular', 'trending']:
                if search_query.startswith(f'-{mode}'):
                    filter_mode = mode
                    search_query = search_query.replace(f'-{mode}', '').strip()
                    break
            
            if not target_id.isdigit():
                await update.inline_query.answer([], cache_time=5)
                return
            
            target_uid = int(target_id)
            usr = await get_user(target_uid)
            
            if not usr:
                button_data = {
                    "text": "🎮 sᴛᴀʀᴛ ᴄᴏʟʟᴇᴄᴛɪɴɢ",
                    "start_parameter": "start_collecting"
                }
                
                await update.inline_query.answer([
                    InlineQueryResultArticle(
                        id="nouser",
                        title="❌ ɴᴏ ᴄᴏʟʟᴇᴄᴛɪᴏɴ ғᴏᴜɴᴅ",
                        description="ᴛᴀᴘ ᴛᴏ sᴛᴀʀᴛ ʏᴏᴜʀ ᴊᴏᴜʀɴᴇʏ",
                        thumbnail_url="https://i.imgur.com/placeholder.png",
                        input_message_content=InputTextMessageContent(
                            "<b>🎮 sᴛᴀʀᴛ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ!</b>",
                            parse_mode=ParseMode.HTML
                        )
                    )
                ], button=button_data, cache_time=5)
                return
            
            char_dict = {}
            for c in usr.get('characters', []):
                if isinstance(c, dict) and c.get('id'):
                    char_dict[c['id']] = c
            
            all_chars = list(char_dict.values())
            
            if search_query:
                rx = re.compile(re.escape(search_query), re.IGNORECASE)
                all_chars = [c for c in all_chars if 
                            rx.search(c.get('name', '')) or 
                            rx.search(c.get('anime', '')) or 
                            rx.search(c.get('id', ''))]
            
            if filter_mode:
                all_chars = await filter_chars(all_chars, filter_mode)
            
            fav_char = None
            favorites = usr.get('favorites')
            if favorites and not search_query and not filter_mode:
                fav_id = favorites.get('id') if isinstance(favorites, dict) else favorites
                fav_char = next((c for c in all_chars if c.get('id') == fav_id), None)
                
                if fav_char:
                    all_chars = [c for c in all_chars if c.get('id') != fav_id]
                    all_chars.insert(0, fav_char)
            
            if not filter_mode or filter_mode not in ['new', 'popular', 'trending']:
                all_chars.sort(key=lambda x: parse_rar(x.get('rarity', '')).value)
        
        else:
            for mode in ['rare', 'video', 'new', 'popular', 'trending']:
                if search_query.startswith(f'-{mode}'):
                    filter_mode = mode
                    search_query = search_query.replace(f'-{mode}', '').strip()
                    break
            
            all_chars = await search_chars(search_query)
            
            if filter_mode:
                all_chars = await filter_chars(all_chars, filter_mode)
            
            if not filter_mode or filter_mode not in ['new', 'popular', 'trending']:
                all_chars.sort(key=lambda x: parse_rar(x.get('rarity', '')).value)
        
        all_chars = dedupe(all_chars)
        
        chars = all_chars[off:off+50]
        has_more = len(all_chars) > off + 50
        next_offset = str(off + 50) if has_more else ""
        
        char_ids = [c.get('id') for c in chars if c.get('id')]
        bulk_stats = {}
        if char_ids and not is_collection:
            owners_data = await bulk_count(char_ids)
            for cid in char_ids:
                owners_list = await get_owners(cid, 10)
                bulk_stats[cid] = {
                    'owners': len(owners_list),
                    'total': owners_data.get(cid, 0)
                }
        
        results = []
        for ch in chars:
            cid = ch.get('id')
            if not cid:
                continue
            
            nm = ch.get('name', '?')
            an = ch.get('anime', '?')
            img = ch.get('img_url', '')
            vid = ch.get('is_video', False)
            r = parse_rar(ch.get('rarity', ''))
            
            is_fav = False
            if is_collection and usr:
                fav = usr.get('favorites')
                fav_id = fav.get('id') if isinstance(fav, dict) else fav
                is_fav = (fav_id == cid)
            
            stats = bulk_stats.get(cid)
            cap = minimal_caption(ch, is_fav, show_stats=(stats is not None), stats=stats)
            kbd = create_inline_keyboard(cid, show_share_options=True)
            
            rid = f"{cid}{off}{query_id[:8]}"
            title = f"{'💖 ' if is_fav else ''}{r.emoji} {trunc(nm, 28)}"
            
            popularity = ""
            if stats and stats.get('owners', 0) > 10:
                popularity = f"🔥 {stats['owners']} ᴏᴡɴᴇʀs"
            elif stats and stats.get('total', 0) > 5:
                popularity = f"⭐ {stats['total']}× ɢʀᴀʙʙᴇᴅ"
            
            desc = f"{r.name} • {trunc(an, 20)}"
            if popularity:
                desc = f"{popularity} • {desc}"
            
            if vid:
                results.append(InlineQueryResultVideo(
                    id=rid,
                    video_url=img,
                    mime_type="video/mp4",
                    thumbnail_url=img,
                    title=title,
                    description=desc,
                    caption=cap,
                    parse_mode=ParseMode.HTML,
                    reply_markup=kbd
                ))
            else:
                results.append(InlineQueryResultPhoto(
                    id=rid,
                    photo_url=img,
                    thumbnail_url=img,
                    title=title,
                    description=desc,
                    caption=cap,
                    parse_mode=ParseMode.HTML,
                    reply_markup=kbd
                ))
        
        await update.inline_query.answer(
            results,
            next_offset=next_offset,
            cache_time=90,
            is_personal=is_collection
        )
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        await update.inline_query.answer([], cache_time=5)

async def chosen_inline_result(update: Update, context) -> None:
    result = update.chosen_inline_result
    cid = result.result_id.split('][')[0] if '][' in result.result_id else result.result_id[:20]
    
    cid_clean = ''.join(filter(str.isalnum, cid))
    
    feedback_key = f'pick_{cid_clean}'
    current_count = feedback_cache.get(feedback_key, 0)
    feedback_cache[feedback_key] = current_count + 1
    
    query_key = f'query_{result.from_user.id}'
    feedback_cache[query_key] = result.query

async def show_owners(update: Update, context) -> None:
    q = update.callback_query
    await q.answer()
    
    try:
        cid = q.data.split('.')[1]
        ch = await collection.find_one({'id': cid}, {'_id': 0})
        
        if not ch:
            await q.answer("❌ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        owners = await get_owners(cid, 100)
        
        if not owners:
            await q.answer("ℹ️ ɴᴏ ᴏᴡɴᴇʀs ʏᴇᴛ", show_alert=True)
            return
        
        cap = owners_caption(ch, owners)
        kbd = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data=f"b.{cid}"),
                InlineKeyboardButton("📊 sᴛᴀᴛs", callback_data=f"s.{cid}")
            ],
            [
                InlineKeyboardButton(
                    "📤 sʜᴀʀᴇ",
                    switch_inline_query_chosen_chat=SwitchInlineQueryChosenChat(
                        query=cid,
                        allow_user_chats=True,
                        allow_group_chats=True,
                        allow_channel_chats=False
                    )
                )
            ]
        ])
        
        await q.edit_message_caption(caption=cap, parse_mode=ParseMode.HTML, reply_markup=kbd)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        await q.answer("❌ ᴇʀʀᴏʀ", show_alert=True)

async def back_card(update: Update, context) -> None:
    q = update.callback_query
    await q.answer()
    
    try:
        cid = q.data.split('.')[1]
        ch = await collection.find_one({'id': cid}, {'_id': 0})
        
        if not ch:
            await q.answer("❌ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        cap = minimal_caption(ch)
        kbd = create_inline_keyboard(cid)
        
        await q.edit_message_caption(caption=cap, parse_mode=ParseMode.HTML, reply_markup=kbd)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        await q.answer("❌ ᴇʀʀᴏʀ", show_alert=True)

async def show_stats(update: Update, context) -> None:
    q = update.callback_query
    await q.answer()
    
    try:
        cid = q.data.split('.')[1]
        ch = await collection.find_one({'id': cid}, {'_id': 0})
        
        if not ch:
            await q.answer("❌ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        owners = await get_owners(cid, 100)
        cap = stats_caption(ch, owners)
        
        kbd = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data=f"b.{cid}"),
                InlineKeyboardButton("👥 ᴏᴡɴᴇʀs", callback_data=f"o.{cid}")
            ],
            [
                InlineKeyboardButton(
                    "📤 sʜᴀʀᴇ",
                    switch_inline_query_chosen_chat=SwitchInlineQueryChosenChat(
                        query=cid,
                        allow_user_chats=True,
                        allow_group_chats=True,
                        allow_channel_chats=False
                    )
                )
            ]
        ])
        
        await q.edit_message_caption(caption=cap, parse_mode=ParseMode.HTML, reply_markup=kbd)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        await q.answer("❌ ᴇʀʀᴏʀ", show_alert=True)

application.add_handler(InlineQueryHandler(inlinequery, block=False))
application.add_handler(ChosenInlineResultHandler(chosen_inline_result, block=False))
application.add_handler(CallbackQueryHandler(show_owners, pattern=r'^o\.', block=False))
application.add_handler(CallbackQueryHandler(back_card, pattern=r'^b\.', block=False))
application.add_handler(CallbackQueryHandler(show_stats, pattern=r'^s\.', block=False))