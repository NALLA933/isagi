import re
import time
from html import escape
from typing import List, Dict, Optional, Tuple
from cachetools import TTLCache, LRUCache
from pymongo import ASCENDING, TEXT
from functools import lru_cache
import hashlib

from telegram import Update, InlineQueryResultPhoto, InlineQueryResultVideo, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
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

# Initialize compound indexes for optimal query performance
# Using ESR (Equality, Sort, Range) rule for index field ordering
try:
    # Character collection indexes
    collection.create_index([('id', ASCENDING)], unique=True, background=True)
    collection.create_index([('rarity', ASCENDING), ('anime', ASCENDING)], background=True)
    collection.create_index([('name', TEXT), ('anime', TEXT)], background=True)
    
    # User collection indexes  
    user_collection.create_index([('id', ASCENDING)], unique=True, background=True)
    user_collection.create_index([('characters.id', ASCENDING)], background=True, sparse=True)
except:
    pass

# Optimized cache configuration with better TTL balance
char_cache = TTLCache(maxsize=30000, ttl=1800)  # Reduced size, reasonable TTL
user_cache = TTLCache(maxsize=20000, ttl=900)   # Faster invalidation for user data
query_cache = LRUCache(maxsize=5000)            # LRU for search patterns
count_cache = TTLCache(maxsize=15000, ttl=1200) # Moderate TTL for counts

CAPS = str.maketrans(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ',
    'ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ'
)

@lru_cache(maxsize=32768)
def sc(t: str) -> str:
    """Small caps transformation"""
    return t.translate(CAPS)

@lru_cache(maxsize=16384)
def parse_rar(r: str) -> Tuple[str, str, int]:
    """Parse rarity string into emoji, name, and value"""
    if not r or not isinstance(r, str):
        return "🟢", "Common", 20
    
    r_lower = r.lower()
    for key, (emoji, val) in RARITY_MAP.items():
        if key in r_lower:
            name = r.split(' ', 1)[-1] if ' ' in r else key.title()
            return emoji, name, val
    
    parts = r.split(' ', 1)
    return parts[0] if parts else "🟢", parts[1] if len(parts) > 1 else "Common", 20

def trunc(t: str, l: int = 18) -> str:
    """Truncate text with ellipsis"""
    return t[:l-2] + '..' if len(t) > l else t

def cache_key(*args) -> str:
    """Generate cache key from arguments"""
    return hashlib.md5(str(args).encode()).hexdigest()

async def get_user(uid: int) -> Optional[Dict]:
    """Get user with caching"""
    k = f"u{uid}"
    if k in user_cache:
        return user_cache[k]
    
    u = await user_collection.find_one({'id': uid}, {'_id': 0})
    if u:
        user_cache[k] = u
    return u

async def bulk_count(ids: List[str]) -> Dict[str, int]:
    """Bulk count character ownership with optimized aggregation"""
    if not ids:
        return {}
    
    k = cache_key('bulk', tuple(sorted(ids[:100])))  # Limit cache key size
    if k in count_cache:
        return count_cache[k]
    
    # Optimized pipeline with $match at the start for index usage
    pipe = [
        {'$match': {'characters.id': {'$in': ids}}},
        {'$project': {'characters.id': 1}},  # Project only needed field early
        {'$unwind': '$characters'},
        {'$match': {'characters.id': {'$in': ids}}},  # Filter again after unwind
        {'$group': {'_id': '$characters.id', 'count': {'$sum': 1}}}
    ]
    
    results = await user_collection.aggregate(pipe).to_list(None)
    counts = {r['_id']: r['count'] for r in results}
    count_cache[k] = counts
    return counts

async def get_owners(cid: str, lim: int = 100) -> List[Dict]:
    """Get top owners with optimized aggregation pipeline"""
    k = f"o{cid}{lim}"
    if k in count_cache:
        return count_cache[k]
    
    # Optimized pipeline with early projection and efficient grouping
    pipe = [
        {'$match': {'characters.id': cid}},
        {'$project': {  # Project early to reduce data size
            'id': 1,
            'first_name': 1,
            'username': 1,
            'characters': {'$filter': {
                'input': '$characters',
                'as': 'c',
                'cond': {'$eq': ['$$c.id', cid]}
            }}
        }},
        {'$addFields': {'count': {'$size': '$characters'}}},  # More efficient than $filter in separate stage
        {'$sort': {'count': -1}},
        {'$limit': lim},
        {'$project': {'characters': 0}}  # Remove characters array from final output
    ]
    
    owners = await user_collection.aggregate(pipe).to_list(lim)
    count_cache[k] = owners
    return owners

async def search_chars(q: str, lim: int = 500) -> List[Dict]:
    """Search characters with optimized text search and caching"""
    k = cache_key('search', q, lim)
    if k in query_cache:
        return query_cache[k]
    
    if q:
        # Try text search first (uses TEXT index for better performance)
        chars = await collection.find(
            {'$text': {'$search': q}},
            {'_id': 0, 'score': {'$meta': 'textScore'}}
        ).sort([('score', {'$meta': 'textScore'})]).limit(lim).to_list(lim)
        
        # Fallback to regex only if text search returns no results
        if not chars:
            # Use case-insensitive regex with index hint
            rx = re.compile(f'^{re.escape(q)}', re.IGNORECASE)  # Prefix match for better index usage
            chars = await collection.find(
                {'$or': [{'name': rx}, {'anime': rx}, {'id': q}]},
                {'_id': 0}
            ).limit(lim).to_list(lim)
    else:
        # For empty queries, use projection to reduce data transfer
        chars = await collection.find(
            {},
            {'_id': 0}
        ).limit(lim).to_list(lim)
    
    query_cache[k] = chars
    return chars

async def filter_chars(chars: List[Dict], mode: str) -> List[Dict]:
    """Filter characters by mode"""
    if mode == 'rare':
        return [c for c in chars if parse_rar(c.get('rarity', ''))[2] <= 12]
    elif mode == 'video':
        return [c for c in chars if c.get('is_video', False)]
    elif mode == 'new':
        return sorted(chars, key=lambda x: str(x.get('_id', '')), reverse=True)
    elif mode == 'popular':
        ids = [c.get('id') for c in chars if c.get('id')]
        if ids:
            counts = await bulk_count(ids)
            return sorted(chars, key=lambda x: counts.get(x.get('id'), 0), reverse=True)
    return chars

def dedupe(chars: List[Dict]) -> List[Dict]:
    """Remove duplicate characters"""
    seen, result = set(), []
    for c in chars:
        cid = c.get('id')
        if cid and cid not in seen:
            seen.add(cid)
            result.append(c)
    return result

async def collection_caption(ch: Dict, u: Dict, fav: bool) -> str:
    """Generate caption for collection view"""
    cid = ch.get('id', '??')
    nm = ch.get('name', 'Unknown')
    an = ch.get('anime', 'Unknown')
    vid = ch.get('is_video', False)
    e, rt, _ = parse_rar(ch.get('rarity', '🟢 Common'))
    
    # Count ownership
    uc = sum(1 for c in u.get('characters', []) if c.get('id') == cid)
    
    return f"""{'💖 ' if fav else ''}<b>{escape(nm)}</b>

<b>📋 ᴄʜᴀʀᴀᴄᴛᴇʀ</b>
┣ 🆔 <code>{cid}</code>
┣ {e} <code>{sc(rt)}</code>
┣ 📺 <i>{escape(trunc(an, 30))}</i>
┗ {'🎬' if vid else '🖼'} {'ᴠɪᴅᴇᴏ' if vid else 'ɪᴍᴀɢᴇ'}

<b>👤 ᴏᴡɴᴇʀsʜɪᴘ</b>
┗ 🎯 ʏᴏᴜ ᴏᴡɴ <code>×{uc}</code>"""

async def global_caption(ch: Dict) -> str:
    """Generate caption for global view"""
    cid = ch.get('id', '??')
    nm = ch.get('name', 'Unknown')
    an = ch.get('anime', 'Unknown')
    vid = ch.get('is_video', False)
    e, rt, _ = parse_rar(ch.get('rarity', '🟢 Common'))
    
    # Get ownership stats
    owners = await get_owners(cid, 10)
    total_grabbed = sum(o.get('count', 0) for o in owners)
    unique_owners = len(owners)
    
    cap = f"""<b>{escape(nm)}</b>

<b>📋 ᴄʜᴀʀᴀᴄᴛᴇʀ</b>
┣ 🆔 <code>{cid}</code>
┣ {e} <code>{sc(rt)}</code>
┣ 📺 <i>{escape(trunc(an, 30))}</i>
┗ {'🎬' if vid else '🖼'} {'ᴠɪᴅᴇᴏ' if vid else 'ɪᴍᴀɢᴇ'}

<b>🌐 ɢʟᴏʙᴀʟ sᴛᴀᴛs</b>
┣ 🎯 <code>{total_grabbed}×</code> ɢʀᴀʙʙᴇᴅ
┗ 👥 <code>{unique_owners}</code> ᴏᴡɴᴇʀs"""
    
    if owners:
        top = owners[0]
        cap += f"\n\n<b>👑 ᴛᴏᴘ ᴏᴡɴᴇʀ</b>\n┗ {escape(trunc(top.get('first_name', 'User'), 15))} • <code>×{top.get('count', 0)}</code>"
    
    return cap

async def owners_caption(ch: Dict, owners: List[Dict]) -> str:
    """Generate caption for owners list"""
    cid = ch.get('id', '??')
    nm = ch.get('name', 'Unknown')
    e, rt, _ = parse_rar(ch.get('rarity', '🟢 Common'))
    
    total_grabbed = sum(o.get('count', 0) for o in owners)
    unique_owners = len(owners)
    
    cap = f"""<b>{escape(nm)}</b>

<b>📋 ᴄʜᴀʀᴀᴄᴛᴇʀ</b>
┣ 🆔 <code>{cid}</code>
┗ {e} <code>{sc(rt)}</code>

<b>👥 ᴛᴏᴘ ᴏᴡɴᴇʀs</b>
┣ <code>{unique_owners}</code> ᴜsᴇʀs
┗ <code>{total_grabbed}×</code> ᴛᴏᴛᴀʟ

"""
    
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, o in enumerate(owners[:30], 1):
        medal = medals.get(i, f"{i}.")
        fn = escape(trunc(o.get('first_name', 'User'), 15))
        cap += f"{medal} {fn} • <code>×{o.get('count', 0)}</code>\n"
    
    return cap

async def stats_caption(ch: Dict, owners: List[Dict]) -> str:
    """Generate caption for stats view"""
    cid = ch.get('id', '??')
    nm = ch.get('name', 'Unknown')
    an = ch.get('anime', 'Unknown')
    e, rt, _ = parse_rar(ch.get('rarity', '🟢 Common'))
    
    total_grabbed = sum(o.get('count', 0) for o in owners)
    unique_owners = len(owners)
    avg = round(total_grabbed / unique_owners, 1) if unique_owners > 0 else 0
    
    cap = f"""<b>{escape(nm)}</b>

<b>📋 ᴄʜᴀʀᴀᴄᴛᴇʀ</b>
┣ 🆔 <code>{cid}</code>
┣ {e} <code>{sc(rt)}</code>
┗ 📺 <i>{escape(trunc(an, 30))}</i>

<b>📊 sᴛᴀᴛɪsᴛɪᴄs</b>
┣ 🎯 <code>{total_grabbed}×</code> ɢʀᴀʙʙᴇᴅ
┣ 👥 <code>{unique_owners}</code> ᴏᴡɴᴇʀs
┗ 📈 <code>{avg}×</code> ᴘᴇʀ ᴜsᴇʀ"""
    
    if owners:
        cap += "\n\n<b>🏆 ᴛᴏᴘ ᴄᴏʟʟᴇᴄᴛᴏʀs</b>\n"
        for i, o in enumerate(owners[:10], 1):
            fn = escape(trunc(o.get('first_name', 'User'), 15))
            cap += f"{i}. {fn} • <code>×{o.get('count', 0)}</code>\n"
    
    return cap

async def inlinequery(update: Update, context) -> None:
    """Handle inline queries"""
    q = update.inline_query.query
    off = int(update.inline_query.offset) if update.inline_query.offset else 0
    uid = update.inline_query.from_user.id
    
    try:
        is_collection = False
        usr = None
        search_query = q
        filter_mode = None
        
        # Check if it's a collection query
        if q.startswith('collection.'):
            is_collection = True
            parts = q.split(' ', 1)
            target_id = parts[0].split('.')[1]
            search_query = parts[1].strip() if len(parts) > 1 else ''
            
            # Parse filter mode
            for mode in ['rare', 'video', 'new', 'popular']:
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
                await update.inline_query.answer([
                    InlineQueryResultArticle(
                        id="nouser",
                        title="❌ ᴜsᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ",
                        description="sᴛᴀʀᴛ ᴄᴏʟʟᴇᴄᴛɪɴɢ ᴄʜᴀʀᴀᴄᴛᴇʀs ғɪʀsᴛ",
                        input_message_content=InputTextMessageContent(
                            "<b>❌ ᴜsᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ</b>\n\nsᴛᴀʀᴛ ᴄᴏʟʟᴇᴄᴛɪɴɢ ᴄʜᴀʀᴀᴄᴛᴇʀs!",
                            parse_mode=ParseMode.HTML
                        )
                    )
                ], cache_time=5)
                return
            
            # Get unique characters from collection
            char_dict = {}
            for c in usr.get('characters', []):
                if isinstance(c, dict) and c.get('id'):
                    char_dict[c['id']] = c
            
            all_chars = list(char_dict.values())
            
            # Filter by search query
            if search_query:
                rx = re.compile(re.escape(search_query), re.IGNORECASE)
                all_chars = [c for c in all_chars if 
                            rx.search(c.get('name', '')) or 
                            rx.search(c.get('anime', '')) or 
                            rx.search(c.get('id', ''))]
            
            # Apply filter mode
            if filter_mode:
                all_chars = await filter_chars(all_chars, filter_mode)
            
            # Handle favorites
            fav_char = None
            favorites = usr.get('favorites')
            if favorites and not search_query and not filter_mode:
                fav_id = favorites.get('id') if isinstance(favorites, dict) else favorites
                fav_char = next((c for c in all_chars if c.get('id') == fav_id), None)
                
                if fav_char:
                    all_chars = [c for c in all_chars if c.get('id') != fav_id]
                    all_chars.insert(0, fav_char)
            
            # Sort by rarity
            if not filter_mode or filter_mode not in ['new', 'popular']:
                all_chars.sort(key=lambda x: parse_rar(x.get('rarity', ''))[2])
        
        else:
            # Global search
            for mode in ['rare', 'video', 'new', 'popular']:
                if search_query.startswith(f'-{mode}'):
                    filter_mode = mode
                    search_query = search_query.replace(f'-{mode}', '').strip()
                    break
            
            all_chars = await search_chars(search_query)
            
            if filter_mode:
                all_chars = await filter_chars(all_chars, filter_mode)
            
            # Sort by rarity
            if not filter_mode or filter_mode not in ['new', 'popular']:
                all_chars.sort(key=lambda x: parse_rar(x.get('rarity', ''))[2])
        
        # Deduplicate
        all_chars = dedupe(all_chars)
        
        # Pagination
        chars = all_chars[off:off+50]
        has_more = len(all_chars) > off + 50
        next_offset = str(off + 50) if has_more else ""
        
        # Build results
        results = []
        for ch in chars:
            cid = ch.get('id')
            if not cid:
                continue
            
            nm = ch.get('name', '?')
            an = ch.get('anime', '?')
            img = ch.get('img_url', '')
            vid = ch.get('is_video', False)
            e, rt, _ = parse_rar(ch.get('rarity', ''))
            
            # Check if favorite
            is_fav = False
            if is_collection and usr:
                fav = usr.get('favorites')
                fav_id = fav.get('id') if isinstance(fav, dict) else fav
                is_fav = (fav_id == cid)
            
            # Generate caption
            if is_collection:
                cap = await collection_caption(ch, usr, is_fav)
            else:
                cap = await global_caption(ch)
            
            # Create keyboard
            kbd = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(sc("👥 ᴏᴡɴᴇʀs"), callback_data=f"o.{cid}"),
                    InlineKeyboardButton(sc("📊 sᴛᴀᴛs"), callback_data=f"s.{cid}")
                ],
                [
                    InlineKeyboardButton(sc("🔗 sʜᴀʀᴇ"), switch_inline_query=f"{cid}")
                ]
            ])
            
            # Generate unique result ID
            rid = f"{cid}{off}{int(time.time()*1000)}"
            title = f"{'💖 ' if is_fav else ''}{e} {trunc(nm, 24)}"
            desc = f"{trunc(an, 20)} • {trunc(rt, 10)}"
            
            # Create result
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
            cache_time=30,  # Increased cache time for better client-side caching
            is_personal=is_collection
        )
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        await update.inline_query.answer([], cache_time=5)

async def show_owners(update: Update, context) -> None:
    """Show character owners"""
    q = update.callback_query
    await q.answer()
    
    try:
        cid = q.data.split('.')[1]
        ch = await collection.find_one({'id': cid}, {'_id': 0})
        
        if not ch:
            await q.answer("❌ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        owners = await get_owners(cid, 100)
        
        if not owners:
            await q.answer("ℹ️ ɴᴏ ᴏɴᴇ ᴏᴡɴs ᴛʜɪs ʏᴇᴛ", show_alert=True)
            return
        
        cap = await owners_caption(ch, owners)
        kbd = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(sc("⬅️ ʙᴀᴄᴋ"), callback_data=f"b.{cid}"),
                InlineKeyboardButton(sc("📊 sᴛᴀᴛs"), callback_data=f"s.{cid}")
            ],
            [
                InlineKeyboardButton(sc("🔗 sʜᴀʀᴇ"), switch_inline_query=f"{cid}")
            ]
        ])
        
        await q.edit_message_caption(caption=cap, parse_mode=ParseMode.HTML, reply_markup=kbd)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        await q.answer("❌ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ", show_alert=True)

async def back_card(update: Update, context) -> None:
    """Return to character card"""
    q = update.callback_query
    await q.answer()
    
    try:
        cid = q.data.split('.')[1]
        ch = await collection.find_one({'id': cid}, {'_id': 0})
        
        if not ch:
            await q.answer("❌ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        cap = await global_caption(ch)
        kbd = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(sc("👥 ᴏᴡɴᴇʀs"), callback_data=f"o.{cid}"),
                InlineKeyboardButton(sc("📊 sᴛᴀᴛs"), callback_data=f"s.{cid}")
            ],
            [
                InlineKeyboardButton(sc("🔗 sʜᴀʀᴇ"), switch_inline_query=f"{cid}")
            ]
        ])
        
        await q.edit_message_caption(caption=cap, parse_mode=ParseMode.HTML, reply_markup=kbd)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        await q.answer("❌ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ", show_alert=True)

async def show_stats(update: Update, context) -> None:
    """Show character statistics"""
    q = update.callback_query
    await q.answer()
    
    try:
        cid = q.data.split('.')[1]
        ch = await collection.find_one({'id': cid}, {'_id': 0})
        
        if not ch:
            await q.answer("❌ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        owners = await get_owners(cid, 100)
        cap = await stats_caption(ch, owners)
        
        kbd = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(sc("⬅️ ʙᴀᴄᴋ"), callback_data=f"b.{cid}"),
                InlineKeyboardButton(sc("👥 ᴏᴡɴᴇʀs"), callback_data=f"o.{cid}")
            ],
            [
                InlineKeyboardButton(sc("🔗 sʜᴀʀᴇ"), switch_inline_query=f"{cid}")
            ]
        ])
        
        await q.edit_message_caption(caption=cap, parse_mode=ParseMode.HTML, reply_markup=kbd)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        await q.answer("❌ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ", show_alert=True)

# Register handlers
application.add_handler(InlineQueryHandler(inlinequery, block=False))
application.add_handler(CallbackQueryHandler(show_owners, pattern=r'^o\.', block=False))
application.add_handler(CallbackQueryHandler(back_card, pattern=r'^b\.', block=False))
application.add_handler(CallbackQueryHandler(show_stats, pattern=r'^s\.', block=False))