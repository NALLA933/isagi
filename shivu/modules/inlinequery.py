import re
import time
import asyncio
from html import escape
from typing import List, Dict, Optional, Tuple
from cachetools import TTLCache
from pymongo import ASCENDING, DESCENDING
from functools import lru_cache
from datetime import datetime

from telegram import (
    Update, 
    InlineQueryResultPhoto,
    InlineQueryResultVideo,
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import InlineQueryHandler, CallbackQueryHandler
from telegram.constants import ParseMode

from shivu import application, db

collection = db['anime_characters_lol']
user_collection = db['user_collection_lmaoooo']

HAREM_MODE_MAPPING = {
    "common": "🟢 Common",
    "rare": "🟣 Rare",
    "legendary": "🟡 Legendary",
    "special": "💮 Special Edition",
    "neon": "💫 Neon",
    "manga": "✨ Manga",
    "cosplay": "🎭 Cosplay",
    "celestial": "🎐 Celestial",
    "premium": "🔮 Premium Edition",
    "erotic": "💋 Erotic",
    "summer": "🌤 Summer",
    "winter": "☃️ Winter",
    "monsoon": "☔️ Monsoon",
    "valentine": "💝 Valentine",
    "halloween": "🎃 Halloween",
    "christmas": "🎄 Christmas",
    "mythic": "🏵 Mythic",
    "events": "🎗 Special Events",
    "amv": "🎥 AMV",
    "tiny": "👼 Tiny",
    "default": None
}

RARITY_PRIORITY = {
    "🏵": 1, "🔮": 2, "🟡": 3, "🎗": 4, "💫": 5,
    "✨": 6, "🎐": 7, "🎭": 8, "💮": 9, "🎥": 10,
    "💋": 11, "👼": 12, "💝": 13, "🎃": 14, "🎄": 15,
    "🌤": 16, "☃️": 17, "☔️": 18, "🟣": 19, "🟢": 20
}

FILTER_TYPES = {
    'all': '🌟 All',
    'fav': '💖 Favorites',
    'rare': '💎 Rare+',
    'video': '🎥 Videos',
    'recent': '🆕 Recent'
}

SORT_TYPES = {
    'rarity': '💎 Rarity',
    'name': '🔤 Name',
    'anime': '📺 Anime',
    'recent': '🕐 Recent'
}

try:
    collection.create_index([('id', ASCENDING)])
    collection.create_index([('anime', ASCENDING)])
    collection.create_index([('name', ASCENDING)])
    collection.create_index([('rarity', ASCENDING)])
    collection.create_index([('name', 'text'), ('anime', 'text')])
    collection.create_index([('is_video', ASCENDING)])
    user_collection.create_index([('id', ASCENDING)])
    user_collection.create_index([('characters.id', ASCENDING)])
    user_collection.create_index([('first_name', ASCENDING)])
    user_collection.create_index([('username', ASCENDING)])
except:
    pass

all_characters_cache = TTLCache(maxsize=20000, ttl=43200)
user_collection_cache = TTLCache(maxsize=20000, ttl=300)
character_count_cache = TTLCache(maxsize=20000, ttl=900)
anime_count_cache = TTLCache(maxsize=10000, ttl=2400)
owners_cache = TTLCache(maxsize=10000, ttl=600)
search_cache = TTLCache(maxsize=3000, ttl=120)
stats_cache = TTLCache(maxsize=2000, ttl=1800)
leaderboard_cache = TTLCache(maxsize=500, ttl=3600)

SMALL_CAPS = str.maketrans(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ',
    'ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ'
)


@lru_cache(maxsize=2048)
def to_small_caps(text: str) -> str:
    return text.translate(SMALL_CAPS)


@lru_cache(maxsize=1024)
def parse_rarity(char_rarity: str) -> Tuple[str, str]:
    if isinstance(char_rarity, str) and ' ' in char_rarity:
        parts = char_rarity.split(' ', 1)
        return parts[0], parts[1] if len(parts) > 1 else 'Common'
    return '🟢', 'Common'


def truncate(text: str, length: int = 35) -> str:
    return text if len(text) <= length else f"{text[:length-3]}..."


def get_rarity_priority(char: Dict) -> int:
    rarity = char.get('rarity', '🟢 Common')
    emoji = rarity.split(' ')[0] if ' ' in rarity else '🟢'
    return RARITY_PRIORITY.get(emoji, 99)


def is_rare_or_above(rarity: str) -> bool:
    emoji = rarity.split(' ')[0] if ' ' in rarity else '🟢'
    return RARITY_PRIORITY.get(emoji, 99) <= 12


async def get_global_count(character_id: str) -> int:
    key = f"gc_{character_id}"
    if key in character_count_cache:
        return character_count_cache[key]
    count = await user_collection.count_documents({'characters.id': character_id})
    character_count_cache[key] = count
    return count


async def get_anime_count(anime: str) -> int:
    key = f"ac_{anime}"
    if key in anime_count_cache:
        return anime_count_cache[key]
    count = await collection.count_documents({'anime': anime})
    anime_count_cache[key] = count
    return count


async def get_user_stats(user_id: int) -> Dict:
    key = f"stats_{user_id}"
    if key in stats_cache:
        return stats_cache[key]
    
    user = await user_collection.find_one({'id': user_id})
    if not user:
        return {}
    
    chars = user.get('characters', [])
    unique_ids = set(c.get('id') for c in chars if c.get('id'))
    unique_animes = set(c.get('anime') for c in chars if c.get('anime'))
    
    rarity_counts = {}
    for c in chars:
        rarity = c.get('rarity', '🟢 Common')
        emoji = rarity.split(' ')[0] if ' ' in rarity else '🟢'
        rarity_counts[emoji] = rarity_counts.get(emoji, 0) + 1
    
    stats = {
        'total': len(chars),
        'unique': len(unique_ids),
        'animes': len(unique_animes),
        'rarity': rarity_counts
    }
    stats_cache[key] = stats
    return stats


async def get_owners(character_id: str, limit: int = 50) -> List[Dict]:
    key = f"own_{character_id}_{limit}"
    if key in owners_cache:
        return owners_cache[key]
    
    pipeline = [
        {'$match': {'characters.id': character_id}},
        {'$project': {
            '_id': 0,
            'id': 1,
            'first_name': 1,
            'username': 1,
            'count': {
                '$size': {
                    '$filter': {
                        'input': '$characters',
                        'as': 'char',
                        'cond': {'$eq': ['$$char.id', character_id]}
                    }
                }
            }
        }},
        {'$sort': {'count': DESCENDING}},
        {'$limit': limit}
    ]
    
    users = await user_collection.aggregate(pipeline).to_list(length=limit)
    owners_cache[key] = users
    return users


async def get_user_data(user_id: int) -> Optional[Dict]:
    key = str(user_id)
    if key in user_collection_cache:
        return user_collection_cache[key]
    user = await user_collection.find_one({'id': user_id})
    if user:
        user_collection_cache[key] = user
    return user


async def get_anime_leaderboard(anime: str, limit: int = 10) -> List[Dict]:
    key = f"lb_anime_{anime}_{limit}"
    if key in leaderboard_cache:
        return leaderboard_cache[key]
    
    pipeline = [
        {'$match': {'characters.anime': anime}},
        {'$project': {
            '_id': 0,
            'id': 1,
            'first_name': 1,
            'username': 1,
            'count': {
                '$size': {
                    '$filter': {
                        'input': '$characters',
                        'as': 'char',
                        'cond': {'$eq': ['$$char.anime', anime]}
                    }
                }
            }
        }},
        {'$sort': {'count': DESCENDING}},
        {'$limit': limit}
    ]
    
    users = await user_collection.aggregate(pipeline).to_list(length=limit)
    leaderboard_cache[key] = users
    return users


async def get_global_leaderboard(limit: int = 10) -> List[Dict]:
    key = f"lb_global_{limit}"
    if key in leaderboard_cache:
        return leaderboard_cache[key]
    
    pipeline = [
        {'$project': {
            '_id': 0,
            'id': 1,
            'first_name': 1,
            'username': 1,
            'count': {'$size': {'$ifNull': ['$characters', []]}}
        }},
        {'$sort': {'count': DESCENDING}},
        {'$limit': limit}
    ]
    
    users = await user_collection.aggregate(pipeline).to_list(length=limit)
    leaderboard_cache[key] = users
    return users


async def search_characters(query: str, limit: int = 250) -> List[Dict]:
    key = f"srch_{query}_{limit}"
    if key in search_cache:
        return search_cache[key]
    
    regex = re.compile(re.escape(query), re.IGNORECASE)
    chars = await collection.find({
        '$or': [
            {'name': regex},
            {'anime': regex},
            {'id': regex},
            {'rarity': regex}
        ]
    }).limit(limit).to_list(length=limit)
    
    search_cache[key] = chars
    return chars


async def get_all_characters(limit: int = 250) -> List[Dict]:
    if 'all_chars' in all_characters_cache:
        return all_characters_cache['all_chars']
    chars = await collection.find({}).limit(limit).to_list(length=limit)
    all_characters_cache['all_chars'] = chars
    return chars


def apply_filters(chars: List[Dict], filter_type: str, user: Optional[Dict] = None) -> List[Dict]:
    if filter_type == 'fav' and user:
        fav = user.get('favorites')
        if fav:
            fav_id = fav.get('id') if isinstance(fav, dict) else fav
            return [c for c in chars if c.get('id') == fav_id]
    
    elif filter_type == 'rare':
        return [c for c in chars if is_rare_or_above(c.get('rarity', '🟢 Common'))]
    
    elif filter_type == 'video':
        return [c for c in chars if c.get('is_video', False)]
    
    elif filter_type == 'recent':
        return sorted(chars, key=lambda x: x.get('_id', ''), reverse=True)[:100]
    
    return chars


def apply_sort(chars: List[Dict], sort_type: str) -> List[Dict]:
    if sort_type == 'rarity':
        return sorted(chars, key=get_rarity_priority)
    elif sort_type == 'name':
        return sorted(chars, key=lambda x: x.get('name', '').lower())
    elif sort_type == 'anime':
        return sorted(chars, key=lambda x: x.get('anime', '').lower())
    elif sort_type == 'recent':
        return sorted(chars, key=lambda x: x.get('_id', ''), reverse=True)
    return chars


async def build_collection_caption(char: Dict, user: Dict, is_fav: bool) -> str:
    cid = char.get('id', 'Unknown')
    name = char.get('name', 'Unknown')
    anime = char.get('anime', 'Unknown')
    rarity = char.get('rarity', '🟢 Common')
    is_vid = char.get('is_video', False)
    
    emoji, text = parse_rarity(rarity)
    user_char_count = sum(1 for c in user.get('characters', []) if c.get('id') == cid)
    user_anime_count = sum(1 for c in user.get('characters', []) if c.get('anime') == anime)
    anime_total = await get_anime_count(anime)
    
    fname = user.get('first_name', 'User')
    uid = user.get('id')
    fav = "💖 " if is_fav else ""
    media = "🎥" if is_vid else "🖼"
    
    stats = await get_user_stats(uid)
    
    caption = (
        f"<b>{fav}🔮 {to_small_caps('look at')} "
        f"<a href='tg://user?id={uid}'>{escape(fname)}</a>"
        f"{to_small_caps('s waifu')}</b>\n\n"
        f"<b>🆔 {to_small_caps('id')}</b> <code>{cid}</code>\n"
        f"<b>🧬 {to_small_caps('name')}</b> <code>{escape(name)}</code> <code>x{user_char_count}</code>\n"
        f"<b>📺 {to_small_caps('anime')}</b> <code>{escape(truncate(anime, 25))}</code> <code>{user_anime_count}/{anime_total}</code>\n"
        f"<b>{emoji} {to_small_caps('rarity')}</b> <code>{to_small_caps(text)}</code>\n"
        f"<b>{media} {to_small_caps('type')}</b> <code>{to_small_caps('video' if is_vid else 'image')}</code>\n\n"
        f"<b>📊 {to_small_caps('collection')}</b> <code>{stats.get('unique', 0)}/{stats.get('total', 0)}</code> • "
        f"<b>🎴 {to_small_caps('animes')}</b> <code>{stats.get('animes', 0)}</code>"
    )
    
    if is_fav:
        caption += f"\n\n💖 <b>{to_small_caps('favorite character')}</b>"
    
    return caption


async def build_global_caption(char: Dict) -> str:
    cid = char.get('id', 'Unknown')
    name = char.get('name', 'Unknown')
    anime = char.get('anime', 'Unknown')
    rarity = char.get('rarity', '🟢 Common')
    is_vid = char.get('is_video', False)
    
    emoji, text = parse_rarity(rarity)
    gcount = await get_global_count(cid)
    media = "🎥" if is_vid else "🖼"
    anime_total = await get_anime_count(anime)
    
    return (
        f"<b>🔮 {to_small_caps('look at this waifu')}</b>\n\n"
        f"<b>🆔 {to_small_caps('id')}</b> <code>{cid}</code>\n"
        f"<b>🧬 {to_small_caps('name')}</b> <code>{escape(name)}</code>\n"
        f"<b>📺 {to_small_caps('anime')}</b> <code>{escape(truncate(anime, 25))}</code>\n"
        f"<b>{emoji} {to_small_caps('rarity')}</b> <code>{to_small_caps(text)}</code>\n"
        f"<b>{media} {to_small_caps('type')}</b> <code>{to_small_caps('video' if is_vid else 'image')}</code>\n\n"
        f"<b>🌍 {to_small_caps('grabbed')}</b> <code>{gcount}x</code> • "
        f"<b>🎴 {to_small_caps('in anime')}</b> <code>{anime_total}</code>"
    )


async def build_owners_caption(char: Dict, users: List[Dict]) -> str:
    cid = char.get('id', 'Unknown')
    name = char.get('name', 'Unknown')
    anime = char.get('anime', 'Unknown')
    rarity = char.get('rarity', '🟢 Common')
    
    emoji, text = parse_rarity(rarity)
    gcount = await get_global_count(cid)
    
    caption = (
        f"<b>╭━━━━━━━━━━━━━━━━━╮</b>\n"
        f"<b>┃  🎴 {to_small_caps('character owners')}  ┃</b>\n"
        f"<b>╰━━━━━━━━━━━━━━━━━╯</b>\n\n"
        f"<b>🆔 {to_small_caps('id')}</b> <code>{cid}</code>\n"
        f"<b>🧬 {to_small_caps('name')}</b> <code>{escape(name)}</code>\n"
        f"<b>📺 {to_small_caps('anime')}</b> <code>{escape(truncate(anime, 25))}</code>\n"
        f"<b>{emoji} {to_small_caps('rarity')}</b> <code>{to_small_caps(text)}</code>\n\n"
        f"<b>━━━━━━━━━━━━━━━━━</b>\n"
    )
    
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, u in enumerate(users[:20], 1):
        medal = medals.get(i, f"{i}.")
        link = f"<a href='tg://user?id={u['id']}'>{escape(truncate(u.get('first_name', 'User'), 20))}</a>"
        if u.get('username'):
            link += f" <code>@{escape(u['username'])}</code>"
        caption += f"\n{medal} {link} <code>×{u.get('count', 0)}</code>"
    
    caption += f"\n\n<b>🔮 {to_small_caps('total grabbed')}</b> <code>{gcount}×</code>"
    
    if len(users) > 20:
        caption += f" • <i>+{len(users) - 20} {to_small_caps('more')}</i>"
    
    return caption


async def build_stats_caption(char: Dict, users: List[Dict]) -> str:
    cid = char.get('id', 'Unknown')
    name = char.get('name', 'Unknown')
    anime = char.get('anime', 'Unknown')
    rarity = char.get('rarity', '🟢 Common')
    
    emoji, text = parse_rarity(rarity)
    gcount = await get_global_count(cid)
    anime_total = await get_anime_count(anime)
    unique_owners = len(users)
    
    avg_per_owner = round(gcount / unique_owners, 2) if unique_owners > 0 else 0
    
    caption = (
        f"<b>╭━━━━━━━━━━━━━━━━━╮</b>\n"
        f"<b>┃  📊 {to_small_caps('character stats')}  ┃</b>\n"
        f"<b>╰━━━━━━━━━━━━━━━━━╯</b>\n\n"
        f"<b>🆔 {to_small_caps('id')}</b> <code>{cid}</code>\n"
        f"<b>🧬 {to_small_caps('name')}</b> <code>{escape(name)}</code>\n"
        f"<b>📺 {to_small_caps('anime')}</b> <code>{escape(truncate(anime, 25))}</code>\n"
        f"<b>{emoji} {to_small_caps('rarity')}</b> <code>{to_small_caps(text)}</code>\n\n"
        f"<b>━━━━━━━━━━━━━━━━━</b>\n\n"
        f"<b>🌍 {to_small_caps('global grabs')}</b> <code>{gcount}×</code>\n"
        f"<b>👥 {to_small_caps('unique owners')}</b> <code>{unique_owners}</code>\n"
        f"<b>📈 {to_small_caps('avg per owner')}</b> <code>{avg_per_owner}×</code>\n"
        f"<b>🎴 {to_small_caps('anime total')}</b> <code>{anime_total}</code>\n"
    )
    
    if users:
        caption += f"\n<b>🏆 {to_small_caps('top collectors')}</b>\n"
        for i, u in enumerate(users[:5], 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            fname = escape(truncate(u.get('first_name', 'User'), 18))
            count = u.get('count', 0)
            caption += f"{medal} {fname} <code>×{count}</code>\n"
    
    return caption


async def build_anime_leaderboard_caption(anime: str, users: List[Dict]) -> str:
    anime_total = await get_anime_count(anime)
    
    caption = (
        f"<b>╭━━━━━━━━━━━━━━━━━╮</b>\n"
        f"<b>┃  🏆 {to_small_caps('anime leaderboard')}  ┃</b>\n"
        f"<b>╰━━━━━━━━━━━━━━━━━╯</b>\n\n"
        f"<b>📺 {to_small_caps('anime')}</b> <code>{escape(truncate(anime, 25))}</code>\n"
        f"<b>🎴 {to_small_caps('total characters')}</b> <code>{anime_total}</code>\n\n"
        f"<b>━━━━━━━━━━━━━━━━━</b>\n"
    )
    
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, u in enumerate(users[:15], 1):
        medal = medals.get(i, f"{i}.")
        link = f"<a href='tg://user?id={u['id']}'>{escape(truncate(u.get('first_name', 'User'), 18))}</a>"
        count = u.get('count', 0)
        caption += f"\n{medal} {link} <code>×{count}</code>"
    
    return caption


async def inlinequery(update: Update, context) -> None:
    query = update.inline_query.query
    offset = int(update.inline_query.offset) if update.inline_query.offset else 0
    uid = update.inline_query.from_user.id
    
    try:
        all_chars = []
        user = None
        is_collection = False
        filter_type = 'all'
        sort_type = 'rarity'
        
        if query.startswith('collection.'):
            is_collection = True
            parts = query.split(' ', 1)
            target_id = parts[0].split('.')[1]
            
            remaining = parts[1].strip() if len(parts) > 1 else ''
            search = remaining
            
            for ft in FILTER_TYPES.keys():
                if remaining.startswith(f'-{ft}'):
                    filter_type = ft
                    search = remaining.replace(f'-{ft}', '').strip()
                    break
            
            for st in SORT_TYPES.keys():
                if search.startswith(f'-{st}'):
                    sort_type = st
                    search = search.replace(f'-{st}', '').strip()
                    break
            
            if not target_id.isdigit():
                await update.inline_query.answer([], cache_time=5)
                return
            
            tid = int(target_id)
            user = await get_user_data(tid)
            
            if not user:
                await update.inline_query.answer([
                    InlineQueryResultArticle(
                        id="no_user",
                        title="❌ User Not Found",
                        description="This user hasn't started collecting yet",
                        input_message_content=InputTextMessageContent(
                            f"<b>❌ {to_small_caps('user not found')}</b>",
                            parse_mode=ParseMode.HTML
                        )
                    )
                ], cache_time=5)
                return
            
            chars_dict = {}
            for c in user.get('characters', []):
                if isinstance(c, dict) and c.get('id'):
                    cid = c.get('id')
                    if cid not in chars_dict:
                        chars_dict[cid] = c
            
            all_chars = list(chars_dict.values())
            
            fav_data = user.get('favorites')
            fav_char = None
            
            if fav_data:
                if isinstance(fav_data, dict):
                    fid = fav_data.get('id')
                    if any(c.get('id') == fid for c in all_chars):
                        fav_char = fav_data
                    else:
                        await user_collection.update_one(
                            {'id': tid},
                            {'$unset': {'favorites': ""}}
                        )
                        user_collection_cache.pop(str(tid), None)
                elif isinstance(fav_data, str):
                    fav_char = next((c for c in all_chars if c.get('id') == fav_data), None)
                    if not fav_char:
                        await user_collection.update_one(
                            {'id': tid},
                            {'$unset': {'favorites': ""}}
                        )
                        user_collection_cache.pop(str(tid), None)
            
            all_chars = apply_filters(all_chars, filter_type, user)
            
            if search:
                regex = re.compile(re.escape(search), re.IGNORECASE)
                all_chars = [
                    c for c in all_chars 
                    if regex.search(c.get('name', ''))
                    or regex.search(c.get('anime', ''))
                    or regex.search(c.get('id', ''))
                    or regex.search(c.get('rarity', ''))
                ]
            
            if not search and fav_char and filter_type == 'all':
                all_chars = [c for c in all_chars if c.get('id') != fav_char.get('id')]
                all_chars.insert(0, fav_char)
            else:
                all_chars = apply_sort(all_chars, sort_type)
        
        else:
            search = query
            for ft in FILTER_TYPES.keys():
                if query.startswith(f'-{ft}'):
                    filter_type = ft
                    search = query.replace(f'-{ft}', '').strip()
                    break
            
            for st in SORT_TYPES.keys():
                if search.startswith(f'-{st}'):
                    sort_type = st
                    search = search.replace(f'-{st}', '').strip()
                    break
            
            all_chars = await search_characters(search) if search else await get_all_characters()
            all_chars = apply_filters(all_chars, filter_type)
            all_chars = apply_sort(all_chars, sort_type)
        
        chars = all_chars[offset:offset+50]
        has_more = len(all_chars) > offset + 50
        next_off = str(offset + 50) if has_more else ""
        
        results = []
        for char in chars:
            cid = char.get('id')
            if not cid:
                continue
            
            name = char.get('name', 'Unknown')
            anime = char.get('anime', 'Unknown')
            img = char.get('img_url', '')
            is_vid = char.get('is_video', False)
            rarity = char.get('rarity', '🟢 Common')
            
            emoji, _ = parse_rarity(rarity)
            
            is_fav = False
            if is_collection and user and user.get('favorites'):
                fav = user.get('favorites')
                if isinstance(fav, dict) and fav.get('id') == cid:
                    is_fav = True
                elif isinstance(fav, str) and fav == cid:
                    is_fav = True
            
            caption = await build_collection_caption(char, user, is_fav) if is_collection and user else await build_global_caption(char)
            
            kbd = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"🏆 {to_small_caps('owners')}", callback_data=f"show_owners_{cid}"),
                    InlineKeyboardButton(f"📊 {to_small_caps('stats')}", callback_data=f"char_stats_{cid}")
                ],
                [
                    InlineKeyboardButton(f"🎴 {to_small_caps('anime lb')}", callback_data=f"anime_lb_{cid}"),
                    InlineKeyboardButton(f"🔗 {to_small_caps('share')}", switch_inline_query=f"{cid}")
                ]
            ])
            
            rid = f"{cid}_{offset}_{int(time.time() * 1000)}"
            title = f"{'💖 ' if is_fav else ''}{emoji} {truncate(name)}"
            desc = f"{truncate(anime, 30)} • {'🎥' if is_vid else '🖼'}"
            
            if is_vid:
                results.append(InlineQueryResultVideo(
                    id=rid, video_url=img, mime_type="video/mp4",
                    thumbnail_url=img, title=title, description=desc,
                    caption=caption, parse_mode=ParseMode.HTML, reply_markup=kbd
                ))
            else:
                results.append(InlineQueryResultPhoto(
                    id=rid, photo_url=img, thumbnail_url=img,
                    title=title, description=desc, caption=caption,
                    parse_mode=ParseMode.HTML, reply_markup=kbd
                ))
        
        await update.inline_query.answer(
            results, next_offset=next_off, cache_time=5, is_personal=is_collection
        )
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        await update.inline_query.answer([], cache_time=5)


async def inline_show_owners(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    
    try:
        cid = query.data.split('_', 2)[2]
        char = await collection.find_one({'id': cid})
        
        if not char:
            await query.answer("ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        users = await get_owners(cid, limit=100)
        
        if not users:
            await query.answer("ɴᴏ ᴏɴᴇ ᴏᴡɴs ᴛʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ ʏᴇᴛ", show_alert=True)
            return
        
        caption = await build_owners_caption(char, users)
        kbd = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"⬅️ {to_small_caps('back')}", callback_data=f"back_to_card_{cid}"),
                InlineKeyboardButton(f"📊 {to_small_caps('stats')}", callback_data=f"char_stats_{cid}")
            ],
            [
                InlineKeyboardButton(f"🎴 {to_small_caps('anime lb')}", callback_data=f"anime_lb_{cid}"),
                InlineKeyboardButton(f"🌍 {to_small_caps('global lb')}", callback_data=f"global_lb")
            ]
        ])
        
        await query.edit_message_caption(caption=caption, parse_mode=ParseMode.HTML, reply_markup=kbd)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        await query.answer("ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ ᴏᴡɴᴇʀs", show_alert=True)


async def inline_back_to_card(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    
    try:
        cid = query.data.split('_', 3)[3]
        char = await collection.find_one({'id': cid})
        
        if not char:
            await query.answer("ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        caption = await build_global_caption(char)
        kbd = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"🏆 {to_small_caps('owners')}", callback_data=f"show_owners_{cid}"),
                InlineKeyboardButton(f"📊 {to_small_caps('stats')}", callback_data=f"char_stats_{cid}")
            ],
            [
                InlineKeyboardButton(f"🎴 {to_small_caps('anime lb')}", callback_data=f"anime_lb_{cid}"),
                InlineKeyboardButton(f"🔗 {to_small_caps('share')}", switch_inline_query=f"{cid}")
            ]
        ])
        
        await query.edit_message_caption(caption=caption, parse_mode=ParseMode.HTML, reply_markup=kbd)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        await query.answer("ᴇʀʀᴏʀ", show_alert=True)


async def inline_char_stats(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    
    try:
        cid = query.data.split('_', 2)[2]
        char = await collection.find_one({'id': cid})
        
        if not char:
            await query.answer("ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        users = await get_owners(cid, limit=100)
        caption = await build_stats_caption(char, users)
        
        kbd = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"⬅️ {to_small_caps('back')}", callback_data=f"back_to_card_{cid}"),
                InlineKeyboardButton(f"🏆 {to_small_caps('owners')}", callback_data=f"show_owners_{cid}")
            ],
            [
                InlineKeyboardButton(f"🎴 {to_small_caps('anime lb')}", callback_data=f"anime_lb_{cid}"),
                InlineKeyboardButton(f"🔗 {to_small_caps('share')}", switch_inline_query=f"{cid}")
            ]
        ])
        
        await query.edit_message_caption(caption=caption, parse_mode=ParseMode.HTML, reply_markup=kbd)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        await query.answer("ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ sᴛᴀᴛs", show_alert=True)


async def inline_anime_leaderboard(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    
    try:
        cid = query.data.split('_', 2)[2]
        char = await collection.find_one({'id': cid})
        
        if not char:
            await query.answer("ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        anime = char.get('anime', 'Unknown')
        users = await get_anime_leaderboard(anime, limit=50)
        
        if not users:
            await query.answer("ɴᴏ ᴅᴀᴛᴀ ᴀᴠᴀɪʟᴀʙʟᴇ", show_alert=True)
            return
        
        caption = await build_anime_leaderboard_caption(anime, users)
        kbd = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"⬅️ {to_small_caps('back')}", callback_data=f"back_to_card_{cid}"),
                InlineKeyboardButton(f"📊 {to_small_caps('stats')}", callback_data=f"char_stats_{cid}")
            ],
            [
                InlineKeyboardButton(f"🏆 {to_small_caps('owners')}", callback_data=f"show_owners_{cid}"),
                InlineKeyboardButton(f"🌍 {to_small_caps('global lb')}", callback_data=f"global_lb")
            ]
        ])
        
        await query.edit_message_caption(caption=caption, parse_mode=ParseMode.HTML, reply_markup=kbd)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        await query.answer("ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ", show_alert=True)


async def inline_global_leaderboard(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    
    try:
        users = await get_global_leaderboard(limit=50)
        
        if not users:
            await query.answer("ɴᴏ ᴅᴀᴛᴀ ᴀᴠᴀɪʟᴀʙʟᴇ", show_alert=True)
            return
        
        caption = (
            f"<b>╭━━━━━━━━━━━━━━━━━╮</b>\n"
            f"<b>┃  🌍 {to_small_caps('global leaderboard')}  ┃</b>\n"
            f"<b>╰━━━━━━━━━━━━━━━━━╯</b>\n\n"
            f"<b>{to_small_caps('top collectors worldwide')}</b>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━</b>\n"
        )
        
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        for i, u in enumerate(users[:20], 1):
            medal = medals.get(i, f"{i}.")
            link = f"<a href='tg://user?id={u['id']}'>{escape(truncate(u.get('first_name', 'User'), 18))}</a>"
            count = u.get('count', 0)
            caption += f"\n{medal} {link} <code>×{count}</code>"
        
        kbd = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"🔄 {to_small_caps('refresh')}", callback_data=f"global_lb")
        ]])
        
        await query.edit_message_caption(caption=caption, parse_mode=ParseMode.HTML, reply_markup=kbd)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        await query.answer("ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ ɢʟᴏʙᴀʟ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ", show_alert=True)


application.add_handler(InlineQueryHandler(inlinequery, block=False))
application.add_handler(CallbackQueryHandler(inline_show_owners, pattern=r'^show_owners_', block=False))
application.add_handler(CallbackQueryHandler(inline_back_to_card, pattern=r'^back_to_card_', block=False))
application.add_handler(CallbackQueryHandler(inline_char_stats, pattern=r'^char_stats_', block=False))
application.add_handler(CallbackQueryHandler(inline_anime_leaderboard, pattern=r'^anime_lb_', block=False))
application.add_handler(CallbackQueryHandler(inline_global_leaderboard, pattern=r'^global_lb', block=False))