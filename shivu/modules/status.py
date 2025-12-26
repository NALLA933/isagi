from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from shivu import shivuu, SUPPORT_CHAT, user_collection, collection
import os
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
import random


class TextFormatter:
    
    @staticmethod
    def small_caps(text: str) -> str:
        small_caps_map = str.maketrans(
            'abcdefghijklmnopqrstuvwxyz',
            'ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ'
        )
        return text.translate(small_caps_map)
    
    @staticmethod
    def format_number(num: int) -> str:
        if num >= 1000000000:
            return f"{num/1000000000:.1f}ʙ"
        elif num >= 1000000:
            return f"{num/1000000:.1f}ᴍ"
        elif num >= 1000:
            return f"{num/1000:.1f}ᴋ"
        return str(num)


PROFILE_TITLES = {
    "rookie": {
        "name": "✦ ʀᴏᴏᴋɪᴇ ʜᴜɴᴛᴇʀ",
        "price": 0,
        "requirement": {"type": "grabs", "value": 0},
        "symbol": "◆",
        "color": "🟢"
    },
    "explorer": {
        "name": "⟡ ᴇxᴘʟᴏʀᴇʀ",
        "price": 0,
        "requirement": {"type": "grabs", "value": 50},
        "symbol": "◇",
        "color": "🔵"
    },
    "collector": {
        "name": "◈ ᴄᴏʟʟᴇᴄᴛᴏʀ",
        "price": 0,
        "requirement": {"type": "grabs", "value": 100},
        "symbol": "◊",
        "color": "🟡"
    },
    "master": {
        "name": "★ ᴍᴀsᴛᴇʀ ʜᴜɴᴛᴇʀ",
        "price": 0,
        "requirement": {"type": "grabs", "value": 250},
        "symbol": "☆",
        "color": "🟠"
    },
    "elite": {
        "name": "◆ ᴇʟɪᴛᴇ ʜᴜɴᴛᴇʀ",
        "price": 50000,
        "requirement": None,
        "symbol": "◈",
        "color": "🟣"
    },
    "legend": {
        "name": "⚔ ʟᴇɢᴇɴᴅᴀʀʏ",
        "price": 100000,
        "requirement": None,
        "symbol": "⚜",
        "color": "🔴"
    },
    "mythic": {
        "name": "✧ ᴍʏᴛʜɪᴄ ʟᴏʀᴅ",
        "price": 250000,
        "requirement": None,
        "symbol": "✦",
        "color": "🟪"
    },
    "shadow": {
        "name": "☾ sʜᴀᴅᴏᴡ ᴋɪɴɢ",
        "price": 500000,
        "requirement": None,
        "symbol": "☽",
        "color": "⚫"
    },
    "divine": {
        "name": "✶ ᴅɪᴠɪɴᴇ ᴇᴍᴘᴇʀᴏʀ",
        "price": 1000000,
        "requirement": None,
        "symbol": "✷",
        "color": "⚪"
    },
    "supreme": {
        "name": "⧫ sᴜᴘʀᴇᴍᴇ ᴏᴠᴇʀʟᴏʀᴅ",
        "price": 2500000,
        "requirement": None,
        "symbol": "⧈",
        "color": "🌟"
    },
    "cosmic": {
        "name": "✨ ᴄᴏsᴍɪᴄ ᴇɴᴛɪᴛʏ",
        "price": 5000000,
        "requirement": None,
        "symbol": "✧",
        "color": "💫"
    },
    "omega": {
        "name": "Ω ᴏᴍᴇɢᴀ ɢᴏᴅ",
        "price": 10000000,
        "requirement": None,
        "symbol": "Ω",
        "color": "🌌"
    }
}

PROFILE_THEMES = {
    "default": {
        "name": "ᴅᴇғᴀᴜʟᴛ",
        "price": 0,
        "divider": "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯",
        "bullet": "◦",
        "corner_tl": "╭",
        "corner_tr": "╮",
        "corner_bl": "╰",
        "corner_br": "╯",
        "vip": False
    },
    "neon": {
        "name": "ɴᴇᴏɴ ɢʟᴏᴡ",
        "price": 25000,
        "divider": "━━━━━━━━━━━━━━━━━",
        "bullet": "▸",
        "corner_tl": "┏",
        "corner_tr": "┓",
        "corner_bl": "┗",
        "corner_br": "┛",
        "vip": False
    },
    "luxury": {
        "name": "ʟᴜxᴜʀʏ ɢᴏʟᴅ",
        "price": 35000,
        "divider": "═══════════════════",
        "bullet": "◈",
        "corner_tl": "╔",
        "corner_tr": "╗",
        "corner_bl": "╚",
        "corner_br": "╝",
        "vip": False
    },
    "cyber": {
        "name": "ᴄʏʙᴇʀ ᴛᴇᴄʜ",
        "price": 50000,
        "divider": "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰",
        "bullet": "►",
        "corner_tl": "┌",
        "corner_tr": "┐",
        "corner_bl": "└",
        "corner_br": "┘",
        "vip": False
    },
    "royal": {
        "name": "ʀᴏʏᴀʟ ᴇʟᴇɢᴀɴᴄᴇ",
        "price": 75000,
        "divider": "◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆",
        "bullet": "♦",
        "corner_tl": "╔",
        "corner_tr": "╗",
        "corner_bl": "╚",
        "corner_br": "╝",
        "vip": True
    },
    "cosmic": {
        "name": "ᴄᴏsᴍɪᴄ ᴠᴏɪᴅ",
        "price": 100000,
        "divider": "✦━━━━━━━━━━━━━━━✦",
        "bullet": "✧",
        "corner_tl": "╔",
        "corner_tr": "╗",
        "corner_bl": "╚",
        "corner_br": "╝",
        "vip": True
    },
    "minimal": {
        "name": "ᴍɪɴɪᴍᴀʟ ᴄʟᴇᴀɴ",
        "price": 150000,
        "divider": "·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·",
        "bullet": "·",
        "corner_tl": " ",
        "corner_tr": " ",
        "corner_bl": " ",
        "corner_br": " ",
        "vip": True
    },
    "matrix": {
        "name": "ᴍᴀᴛʀɪx ᴄᴏᴅᴇ",
        "price": 200000,
        "divider": "▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓",
        "bullet": "▪",
        "corner_tl": "▓",
        "corner_tr": "▓",
        "corner_bl": "▓",
        "corner_br": "▓",
        "vip": True
    }
}

AVATAR_FRAMES = {
    "none": {"name": "ɴᴏ ғʀᴀᴍᴇ", "price": 0, "left": "", "right": "", "vip": False},
    "diamond": {"name": "ᴅɪᴀᴍᴏɴᴅ", "price": 20000, "left": "◆ ", "right": " ◆", "vip": False},
    "star": {"name": "sᴛᴀʀ", "price": 30000, "left": "★ ", "right": " ★", "vip": False},
    "moon": {"name": "ᴍᴏᴏɴ", "price": 40000, "left": "☾ ", "right": " ☽", "vip": False},
    "crown": {"name": "ᴄʀᴏᴡɴ", "price": 50000, "left": "♔ ", "right": " ♕", "vip": False},
    "wings": {"name": "ᴡɪɴɢs", "price": 75000, "left": "◄ ", "right": " ►", "vip": True},
    "flame": {"name": "ғʟᴀᴍᴇ", "price": 100000, "left": "◈ ", "right": " ◈", "vip": True},
    "cosmic": {"name": "ᴄᴏsᴍɪᴄ", "price": 150000, "left": "✦ ", "right": " ✦", "vip": True},
    "ultimate": {"name": "ᴜʟᴛɪᴍᴀᴛᴇ", "price": 250000, "left": "⧫ ", "right": " ⧫", "vip": True},
    "omega": {"name": "ᴏᴍᴇɢᴀ", "price": 500000, "left": "Ω ", "right": " Ω", "vip": True}
}

EMOJI_PACKS = {
    "basic": {"name": "ʙᴀsɪᴄ", "price": 0, "emojis": ["◦", "◇", "◆"]},
    "geometric": {"name": "ɢᴇᴏᴍᴇᴛʀɪᴄ", "price": 15000, "emojis": ["◆", "◇", "◈", "◊", "○", "●", "◐", "◑"]},
    "stars": {"name": "sᴛᴀʀs", "price": 25000, "emojis": ["★", "☆", "✦", "✧", "✶", "✷", "✸", "✹"]},
    "arrows": {"name": "ᴀʀʀᴏᴡs", "price": 35000, "emojis": ["►", "▸", "▹", "▻", "◄", "◂", "◃", "◅"]},
    "celestial": {"name": "ᴄᴇʟᴇsᴛɪᴀʟ", "price": 50000, "emojis": ["☾", "☽", "☼", "☀", "☁", "☂", "☃", "☄"]},
    "mystical": {"name": "ᴍʏsᴛɪᴄᴀʟ", "price": 75000, "emojis": ["⚜", "⚝", "⚞", "⚟", "⚠", "⚡", "⚢", "⚣"]},
    "royal": {"name": "ʀᴏʏᴀʟ", "price": 100000, "emojis": ["♔", "♕", "♖", "♗", "♘", "♙", "♚", "♛"]},
    "ultimate": {"name": "ᴜʟᴛɪᴍᴀᴛᴇ", "price": 250000, "emojis": ["Ω", "Ψ", "Φ", "Σ", "Δ", "Θ", "Λ", "Π"]}
}

BADGES = {
    "first_grab": {"name": "🌟 ғɪʀsᴛ ɢʀᴀʙ", "requirement": {"type": "grabs", "value": 1}},
    "collector_50": {"name": "📦 ᴄᴏʟʟᴇᴄᴛᴏʀ", "requirement": {"type": "grabs", "value": 50}},
    "hunter_100": {"name": "🎯 ʜᴜɴᴛᴇʀ", "requirement": {"type": "grabs", "value": 100}},
    "master_250": {"name": "⭐ ᴍᴀsᴛᴇʀ", "requirement": {"type": "grabs", "value": 250}},
    "legend_500": {"name": "🏆 ʟᴇɢᴇɴᴅ", "requirement": {"type": "grabs", "value": 500}},
    "whale": {"name": "💎 ᴡʜᴀʟᴇ", "requirement": {"type": "wealth", "value": 1000000}},
    "streak_7": {"name": "🔥 sᴛʀᴇᴀᴋ ᴡᴀʀʀɪᴏʀ", "requirement": {"type": "streak", "value": 7}},
    "streak_30": {"name": "⚡ sᴛʀᴇᴀᴋ ᴍᴀsᴛᴇʀ", "requirement": {"type": "streak", "value": 30}},
    "early_adopter": {"name": "🌸 ᴇᴀʀʟʏ ᴀᴅᴏᴘᴛᴇʀ", "requirement": {"type": "manual", "value": 0}},
    "vip": {"name": "👑 ᴠɪᴘ ᴍᴇᴍʙᴇʀ", "requirement": {"type": "manual", "value": 0}},
    "supporter": {"name": "💝 sᴜᴘᴘᴏʀᴛᴇʀ", "requirement": {"type": "manual", "value": 0}}
}

DAILY_REWARDS = [
    {"day": 1, "coins": 1000, "bonus": ""},
    {"day": 2, "coins": 1500, "bonus": ""},
    {"day": 3, "coins": 2000, "bonus": "🎁 +500 ʙᴏɴᴜs"},
    {"day": 4, "coins": 2500, "bonus": ""},
    {"day": 5, "coins": 3000, "bonus": ""},
    {"day": 6, "coins": 4000, "bonus": ""},
    {"day": 7, "coins": 10000, "bonus": "🎉 ᴡᴇᴇᴋʟʏ ʙᴏɴᴜs"},
]

BAD_WORDS = [
    "fuck", "shit", "ass", "bitch", "damn", "hell",
    "sex", "porn", "nude", "dick", "pussy", "nigger",
    "fag", "retard", "cunt", "cock", "whore", "rape"
]

BIO_COOLDOWN_MINUTES = 60
BIO_MAX_LENGTH = 100
BIO_EMOJI_LIMIT = 10


async def get_user_collection() -> List[Dict[str, Any]]:
    return await user_collection.find({}).to_list(length=None)


async def get_global_rank(user_id: int) -> int:
    pipeline = [
        {
            "$project": {
                "id": 1,
                "characters_count": {
                    "$cond": {
                        "if": {"$isArray": "$characters"},
                        "then": {"$size": "$characters"},
                        "else": 0
                    }
                }
            }
        },
        {"$sort": {"characters_count": -1}}
    ]

    cursor = user_collection.aggregate(pipeline)
    leaderboard_data = await cursor.to_list(length=None)

    for i, user in enumerate(leaderboard_data, start=1):
        if user.get('id') == user_id:
            return i

    return 0


async def get_user_balance(user_id: int) -> int:
    user_balance = await user_collection.find_one(
        {'id': user_id},
        projection={'balance': 1}
    )
    if user_balance:
        return user_balance.get('balance', 0)
    return 0


async def get_grab_stats(user_id: int) -> Dict[str, int]:
    user = await user_collection.find_one({'id': user_id})
    if not user:
        return {
            'total_grabs': 0,
            'today_grabs': 0,
            'weekly_grabs': 0,
            'monthly_grabs': 0
        }
    
    grab_stats = user.get('grab_stats', {})
    return {
        'total_grabs': len(user.get('characters', [])),
        'today_grabs': grab_stats.get('today', 0),
        'weekly_grabs': grab_stats.get('weekly', 0),
        'monthly_grabs': grab_stats.get('monthly', 0)
    }


async def get_streak(user_id: int) -> Dict[str, Any]:
    user = await user_collection.find_one({'id': user_id})
    if not user:
        return {'current': 0, 'longest': 0, 'last_claim': None}
    
    streak_data = user.get('streak_data', {})
    last_claim = streak_data.get('last_claim')
    current_streak = streak_data.get('current', 0)
    longest_streak = streak_data.get('longest', 0)
    
    if last_claim:
        last_claim_date = datetime.fromisoformat(last_claim).date()
        today = datetime.now().date()
        days_diff = (today - last_claim_date).days
        
        if days_diff > 1:
            current_streak = 0
    
    return {
        'current': current_streak,
        'longest': longest_streak,
        'last_claim': last_claim
    }


async def check_badges(user_id: int) -> List[str]:
    user = await user_collection.find_one({'id': user_id})
    if not user:
        return []
    
    earned_badges = user.get('badges', [])
    total_grabs = len(user.get('characters', []))
    balance = user.get('balance', 0)
    streak_data = await get_streak(user_id)
    
    new_badges = []
    
    for badge_id, badge_data in BADGES.items():
        if badge_id in earned_badges:
            continue
        
        req = badge_data['requirement']
        if req['type'] == 'grabs' and total_grabs >= req['value']:
            new_badges.append(badge_id)
        elif req['type'] == 'wealth' and balance >= req['value']:
            new_badges.append(badge_id)
        elif req['type'] == 'streak' and streak_data['current'] >= req['value']:
            new_badges.append(badge_id)
    
    if new_badges:
        earned_badges.extend(new_badges)
        await user_collection.update_one(
            {'id': user_id},
            {'$set': {'badges': earned_badges}}
        )
    
    return earned_badges


async def initialize_profile_data(user_id: int) -> None:
    existing = await user_collection.find_one({'id': user_id})
    if existing and 'profile_data' not in existing:
        await user_collection.update_one(
            {'id': user_id},
            {
                '$set': {
                    'profile_data': {
                        'title': 'rookie',
                        'theme': 'default',
                        'frame': 'none',
                        'bio': '',
                        'bio_last_update': None,
                        'owned_titles': ['rookie'],
                        'owned_themes': ['default'],
                        'owned_frames': ['none'],
                        'owned_emoji_packs': ['basic']
                    }
                }
            }
        )
    
    if existing and 'grab_stats' not in existing:
        await user_collection.update_one(
            {'id': user_id},
            {
                '$set': {
                    'grab_stats': {
                        'today': 0,
                        'weekly': 0,
                        'monthly': 0,
                        'last_reset': datetime.now().isoformat()
                    }
                }
            }
        )
    
    if existing and 'streak_data' not in existing:
        await user_collection.update_one(
            {'id': user_id},
            {
                '$set': {
                    'streak_data': {
                        'current': 0,
                        'longest': 0,
                        'last_claim': None
                    }
                }
            }
        )
    
    if existing and 'badges' not in existing:
        await user_collection.update_one(
            {'id': user_id},
            {'$set': {'badges': []}}
        )


async def check_auto_unlocks(user_id: int, total_count: int) -> None:
    user = await user_collection.find_one({'id': user_id})
    if not user:
        return

    profile_data = user.get('profile_data', {})
    owned_titles = profile_data.get('owned_titles', ['rookie'])

    for title_id, title_data in PROFILE_TITLES.items():
        if title_data['requirement'] is None:
            continue

        req_type = title_data['requirement']['type']
        req_value = title_data['requirement']['value']

        if req_type == 'grabs' and total_count >= req_value:
            if title_id not in owned_titles:
                owned_titles.append(title_id)

    await user_collection.update_one(
        {'id': user_id},
        {'$set': {'profile_data.owned_titles': owned_titles}}
    )


async def get_user_info(user, already: bool = False) -> Tuple[str, Optional[str]]:
    if not already:
        user = await shivuu.get_users(user)
    
    if not user.first_name:
        return "ᴅᴇʟᴇᴛᴇᴅ ᴀᴄᴄᴏᴜɴᴛ", None

    user_id = user.id
    username = user.username or "ɴᴏɴᴇ"
    existing_user = await user_collection.find_one({'id': user_id})
    
    if not existing_user:
        return "ᴜsᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ ɪɴ ᴅᴀᴛᴀʙᴀsᴇ", None

    first_name = user.first_name
    global_rank = await get_global_rank(user_id)
    global_count = await collection.count_documents({})
    total_count = len(existing_user.get('characters', []))
    photo_id = user.photo.big_file_id if user.photo else None
    balance = await get_user_balance(user_id)
    global_coin_rank = await user_collection.count_documents({'balance': {'$gt': balance}}) + 1
    grab_stats = await get_grab_stats(user_id)
    streak_data = await get_streak(user_id)
    badges = await check_badges(user_id)

    await initialize_profile_data(user_id)
    await check_auto_unlocks(user_id, total_count)

    existing_user = await user_collection.find_one({'id': user_id})
    profile_data = existing_user.get('profile_data', {})

    active_title = PROFILE_TITLES.get(
        profile_data.get('title', 'rookie'),
        PROFILE_TITLES['rookie']
    )['name']

    active_theme = PROFILE_THEMES.get(
        profile_data.get('theme', 'default'),
        PROFILE_THEMES['default']
    )

    active_frame = AVATAR_FRAMES.get(
        profile_data.get('frame', 'none'),
        AVATAR_FRAMES['none']
    )

    has_pass = "✦" if existing_user.get('pass') else "◇"
    tokens = existing_user.get('tokens', 0)
    
    framed_name = f"{active_frame['left']}{first_name}{active_frame['right']}"
    bio = profile_data.get('bio', '')
    divider = active_theme['divider']
    corner_tl = active_theme['corner_tl']
    corner_tr = active_theme['corner_tr']
    corner_bl = active_theme['corner_bl']
    corner_br = active_theme['corner_br']
    
    badge_display = ""
    if badges:
        badge_list = [BADGES[b]['name'] for b in badges[:5]]
        badge_display = f"\n{'  '.join(badge_list)}"
    
    streak_emoji = "🔥" if streak_data['current'] > 0 else "◇"
    
    info_text = f"""{corner_tl}{divider}{corner_tr}
{framed_name}
{active_title}{badge_display}
{divider}
ᴜsᴇʀ ɪᴅ ◆ `{user_id}`
ᴜsᴇʀɴᴀᴍᴇ ◆ @{username}
{divider}
ᴄᴏʟʟᴇᴄᴛɪᴏɴ ◆ `{total_count}` / `{global_count}`
ɢʟᴏʙᴀʟ ʀᴀɴᴋ ◆ `#{global_rank}`
{divider}
ᴡᴇᴀʟᴛʜ ◆ ₩ `{balance:,}`
ᴡᴇᴀʟᴛʜ ʀᴀɴᴋ ◆ `#{global_coin_rank}`
{divider}
{streak_emoji} sᴛʀᴇᴀᴋ ◆ `{streak_data['current']}` ᴅᴀʏs
ʙᴇsᴛ sᴛʀᴇᴀᴋ ◆ `{streak_data['longest']}` ᴅᴀʏs
{divider}
ɢʀᴀʙs ᴛᴏᴅᴀʏ ◆ `{grab_stats['today_grabs']}`
ᴛʜɪs ᴡᴇᴇᴋ ◆ `{grab_stats['weekly_grabs']}`
ᴛʜɪs ᴍᴏɴᴛʜ ◆ `{grab_stats['monthly_grabs']}`
{divider}
ᴘᴀss {has_pass}  ◆  ᴛᴏᴋᴇɴs `{tokens:,}`
{divider}"""

    if bio:
        info_text += f"\n💭 {bio}\n"

    info_text += f"{corner_bl}{divider}{corner_br}"

    return info_text, photo_id


def contains_bad_words(text: str) -> bool:
    text_lower = text.lower()
    return any(bad_word in text_lower for bad_word in BAD_WORDS)


def count_emojis(text: str) -> int:
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE
    )
    return len(emoji_pattern.findall(text))


@shivuu.on_message(filters.command(["sinfo", "profile", "me"]))
async def profile(client: Client, message: Message) -> None:
    if message.reply_to_message:
        user = message.reply_to_message.from_user.id
    elif not message.reply_to_message and len(message.command) == 1:
        user = message.from_user.id
    elif not message.reply_to_message and len(message.command) != 1:
        user = message.text.split(None, 1)[1]
    
    m = await message.reply_text("◆ ʟᴏᴀᴅɪɴɢ ʏᴏᴜʀ ᴘʀᴏғɪʟᴇ...")
    
    try:
        info_text, photo_id = await get_user_info(user)
    except Exception as e:
        print(f"Error in profile command: {e}")
        return await m.edit(f"◇ sᴏᴍᴇᴛʜɪɴɢ ᴡᴇɴᴛ ᴡʀᴏɴɢ\nʀᴇᴘᴏʀᴛ ᴀᴛ @{SUPPORT_CHAT}")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✦ sʜᴏᴘ", callback_data="profile_shop"),
            InlineKeyboardButton("📊 sᴛᴀᴛs", callback_data="view_stats")
        ],
        [
            InlineKeyboardButton("🎁 ʀᴇᴡᴀʀᴅs", callback_data="daily_rewards"),
            InlineKeyboardButton("🏆 ʙᴀᴅɢᴇs", callback_data="view_badges")
        ],
        [InlineKeyboardButton("◇ sᴜᴘᴘᴏʀᴛ", url=f"https://t.me/{SUPPORT_CHAT}")]
    ])

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "◆ sᴛᴀʀᴛ ᴍᴇ ғɪʀsᴛ",
            url=f"https://t.me/{shivuu.me.username}?start=True"
        )]
    ])

    existing_user = await user_collection.find_one({'id': user if isinstance(user, int) else None})

    if photo_id is None:
        await m.edit(info_text, disable_web_page_preview=True, reply_markup=keyboard)
    elif not existing_user:
        await m.edit(info_text, disable_web_page_preview=True, reply_markup=reply_markup)
    else:
        photo = await shivuu.download_media(photo_id)
        await message.reply_photo(photo, caption=info_text, reply_markup=keyboard)
        await m.delete()
        if os.path.exists(photo):
            os.remove(photo)


@shivuu.on_callback_query(filters.regex("^daily_rewards$"))
async def daily_rewards_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    await initialize_profile_data(user_id)
    
    streak_data = await get_streak(user_id)
    last_claim = streak_data['last_claim']
    current_streak = streak_data['current']
    
    can_claim = True
    if last_claim:
        last_claim_date = datetime.fromisoformat(last_claim).date()
        today = datetime.now().date()
        if last_claim_date == today:
            can_claim = False
    
    day_index = current_streak % 7
    next_reward = DAILY_REWARDS[day_index]
    
    rewards_text = f"""╔═══════════════════╗
    🎁 ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅs 🎁
╚═══════════════════╝

🔥 ᴄᴜʀʀᴇɴᴛ sᴛʀᴇᴀᴋ ◆ {current_streak} ᴅᴀʏs
⭐ ʙᴇsᴛ sᴛʀᴇᴀᴋ ◆ {streak_data['longest']} ᴅᴀʏs

ɴᴇxᴛ ʀᴇᴡᴀʀᴅ ◆
💰 {next_reward['coins']:,} ᴄᴏɪɴs
{next_reward['bonus']}

━━━━━━━━━━━━━━━━━
ᴡᴇᴇᴋʟʏ ʀᴇᴡᴀʀᴅs ◆
"""
    
    for day_data in DAILY_REWARDS:
        day_num = day_data['day']
        coins = day_data['coins']
        status = "✅" if day_num <= (current_streak % 7 or 7) else "◇"
        rewards_text += f"\n{status} ᴅᴀʏ {day_num} ◆ ₩ {coins:,}"
    
    keyboard = []
    if can_claim:
        keyboard.append([InlineKeyboardButton("🎁 ᴄʟᴀɪᴍ ʀᴇᴡᴀʀᴅ", callback_data="claim_reward")])
    else:
        next_claim_time = datetime.combine(datetime.now().date() + timedelta(days=1), datetime.min.time())
        hours_left = int((next_claim_time - datetime.now()).total_seconds() / 3600)
        rewards_text += f"\n\n⏰ ɴᴇxᴛ ᴄʟᴀɪᴍ ɪɴ ◆ {hours_left}ʜ"
    
    keyboard.append([InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="back_to_profile")])
    
    await callback_query.message.edit_text(rewards_text, reply_markup=InlineKeyboardMarkup(keyboard))


@shivuu.on_callback_query(filters.regex("^claim_reward$"))
async def claim_reward_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    
    streak_data = await get_streak(user_id)
    last_claim = streak_data['last_claim']
    
    can_claim = True
    if last_claim:
        last_claim_date = datetime.fromisoformat(last_claim).date()
        today = datetime.now().date()
        if last_claim_date == today:
            can_claim = False
            await callback_query.answer("◇ ᴀʟʀᴇᴀᴅʏ ᴄʟᴀɪᴍᴇᴅ ᴛᴏᴅᴀʏ", show_alert=True)
            return
        
        days_diff = (today - last_claim_date).days
        if days_diff == 1:
            new_streak = streak_data['current'] + 1
        else:
            new_streak = 1
    else:
        new_streak = 1
    
    day_index = (new_streak - 1) % 7
    reward = DAILY_REWARDS[day_index]
    
    user = await user_collection.find_one({'id': user_id})
    current_balance = user.get('balance', 0)
    new_balance = current_balance + reward['coins']
    
    longest_streak = max(new_streak, streak_data['longest'])
    
    await user_collection.update_one(
        {'id': user_id},
        {
            '$set': {
                'balance': new_balance,
                'streak_data.current': new_streak,
                'streak_data.longest': longest_streak,
                'streak_data.last_claim': datetime.now().isoformat()
            }
        }
    )
    
    bonus_text = f"\n{reward['bonus']}" if reward['bonus'] else ""
    
    await callback_query.answer(
        f"✅ ᴄʟᴀɪᴍᴇᴅ\n💰 +{reward['coins']:,} ᴄᴏɪɴs\n🔥 {new_streak} ᴅᴀʏ sᴛʀᴇᴀᴋ{bonus_text}",
        show_alert=True
    )
    
    await daily_rewards_callback(client, callback_query)


@shivuu.on_callback_query(filters.regex("^view_badges$"))
async def view_badges_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    badges = await check_badges(user_id)
    
    badges_text = f"""╔═══════════════════╗
    🏆 ʙᴀᴅɢᴇs 🏆
╚═══════════════════╝

ᴇᴀʀɴᴇᴅ ◆ {len(badges)} / {len(BADGES)}

━━━━━━━━━━━━━━━━━
"""
    
    for badge_id, badge_data in BADGES.items():
        status = "✅" if badge_id in badges else "◇"
        badge_name = badge_data['name']
        req = badge_data['requirement']
        
        if req['type'] == 'grabs':
            requirement = f"{req['value']} ɢʀᴀʙs"
        elif req['type'] == 'wealth':
            requirement = f"₩ {req['value']:,}"
        elif req['type'] == 'streak':
            requirement = f"{req['value']} ᴅᴀʏs"
        else:
            requirement = "sᴘᴇᴄɪᴀʟ"
        
        badges_text += f"\n{status} {badge_name}\n   ◦ {requirement}\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="back_to_profile")]
    ])
    
    await callback_query.message.edit_text(badges_text, reply_markup=keyboard)


@shivuu.on_callback_query(filters.regex("^view_stats$"))
async def view_stats_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    user = await user_collection.find_one({'id': user_id})
    
    if not user:
        await callback_query.answer("ᴜsᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
        return

    grab_stats = await get_grab_stats(user_id)
    total_count = len(user.get('characters', []))
    balance = user.get('balance', 0)
    
    rarity_counts = {}
    for char in user.get('characters', []):
        rarity = char.get('rarity', '🟢 Common')
        rarity_emoji = rarity.split(' ')[0] if ' ' in rarity else rarity
        rarity_counts[rarity_emoji] = rarity_counts.get(rarity_emoji, 0) + 1
    
    sorted_rarities = sorted(rarity_counts.items(), key=lambda x: x[1], reverse=True)
    
    stats_text = f"""╔═══════════════════╗
    📊 ᴅᴇᴛᴀɪʟᴇᴅ sᴛᴀᴛs 📊
╚═══════════════════╝

◆ ɢʀᴀʙ sᴛᴀᴛɪsᴛɪᴄs
━━━━━━━━━━━━━━━━━
◦ ᴛᴏᴛᴀʟ ɢʀᴀʙs ◆ {grab_stats['total_grabs']}
◦ ᴛᴏᴅᴀʏ ◆ {grab_stats['today_grabs']}
◦ ᴛʜɪs ᴡᴇᴇᴋ ◆ {grab_stats['weekly_grabs']}
◦ ᴛʜɪs ᴍᴏɴᴛʜ ◆ {grab_stats['monthly_grabs']}

◆ ʀᴀʀɪᴛʏ ʙʀᴇᴀᴋᴅᴏᴡɴ
━━━━━━━━━━━━━━━━━
"""
    
    for rarity_emoji, count in sorted_rarities[:10]:
        percentage = (count / total_count * 100) if total_count > 0 else 0
        bar_length = int(percentage / 10)
        bar = "█" * bar_length + "░" * (10 - bar_length)
        stats_text += f"{rarity_emoji} {bar} {count} ({percentage:.1f}%)\n"
    
    stats_text += f"\n◆ ᴡᴇᴀʟᴛʜ sᴛᴀᴛs\n━━━━━━━━━━━━━━━━━\n"
    stats_text += f"◦ ᴛᴏᴛᴀʟ ◆ ₩ {balance:,}\n"
    
    profile_data = user.get('profile_data', {})
    owned_items = len(profile_data.get('owned_titles', [])) + len(profile_data.get('owned_themes', [])) + len(profile_data.get('owned_frames', []))
    stats_text += f"◦ ɪᴛᴇᴍs ᴏᴡɴᴇᴅ ◆ {owned_items}\n"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏆 ᴛᴏᴘ", callback_data="leaderboard"),
            InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="back_to_profile")
        ]
    ])
    
    await callback_query.message.edit_text(stats_text, reply_markup=keyboard)


@shivuu.on_callback_query(filters.regex("^leaderboard$"))
async def leaderboard_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    
    pipeline = [
        {
            "$project": {
                "id": 1,
                "first_name": 1,
                "characters_count": {
                    "$cond": {
                        "if": {"$isArray": "$characters"},
                        "then": {"$size": "$characters"},
                        "else": 0
                    }
                }
            }
        },
        {"$sort": {"characters_count": -1}},
        {"$limit": 10}
    ]
    
    cursor = user_collection.aggregate(pipeline)
    leaderboard = await cursor.to_list(length=None)
    
    leaderboard_text = f"""╔═══════════════════╗
    🏆 ᴛᴏᴘ ɢʀᴀʙʙᴇʀs 🏆
╚═══════════════════╝

"""
    
    medals = ["🥇", "🥈", "🥉"]
    user_rank = None
    
    for i, user_data in enumerate(leaderboard, start=1):
        medal = medals[i-1] if i <= 3 else f"#{i}"
        name = user_data.get('first_name', 'Unknown')[:15]
        count = user_data.get('characters_count', 0)
        
        if user_data.get('id') == user_id:
            user_rank = i
            leaderboard_text += f"➤ {medal} {name} ◆ {count}\n"
        else:
            leaderboard_text += f"{medal} {name} ◆ {count}\n"
    
    if user_rank is None:
        user_rank = await get_global_rank(user_id)
        if user_rank > 10:
            leaderboard_text += f"\n━━━━━━━━━━━━━━━━━\nʏᴏᴜʀ ʀᴀɴᴋ ◆ #{user_rank}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="view_stats")]
    ])
    
    await callback_query.message.edit_text(leaderboard_text, reply_markup=keyboard)


@shivuu.on_callback_query(filters.regex("^profile_shop$"))
async def profile_shop_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    balance = await get_user_balance(user_id)
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("◆ ᴛɪᴛʟᴇs", callback_data="shop_titles"),
            InlineKeyboardButton("◇ ᴛʜᴇᴍᴇs", callback_data="shop_themes")
        ],
        [
            InlineKeyboardButton("◈ ғʀᴀᴍᴇs", callback_data="shop_frames"),
            InlineKeyboardButton("◊ ᴇᴍᴏᴊɪs", callback_data="shop_emojis")
        ],
        [InlineKeyboardButton("✦ ᴇᴅɪᴛ ʙɪᴏ", callback_data="shop_bio")],
        [InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="back_to_profile")]
    ])

    shop_text = f"""╔═══════════════════╗
    ✦ ᴘʀᴏғɪʟᴇ sʜᴏᴘ ✦
╚═══════════════════╝

ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ ᴄᴜsᴛᴏᴍɪᴢᴀᴛɪᴏɴ sʜᴏᴘ
ᴜɴʟᴏᴄᴋ ᴘʀᴇᴍɪᴜᴍ ɪᴛᴇᴍs ᴀɴᴅ
sᴛᴀɴᴅ ᴏᴜᴛ ғʀᴏᴍ ᴛʜᴇ ᴄʀᴏᴡᴅ

💰 ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ ◆ ₩ {balance:,}

sᴇʟᴇᴄᴛ ᴀ ᴄᴀᴛᴇɢᴏʀʏ ʙᴇʟᴏᴡ ◆
"""

    await callback_query.message.edit_text(shop_text, reply_markup=keyboard)


@shivuu.on_callback_query(filters.regex("^shop_titles$"))
async def shop_titles_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    await initialize_profile_data(user_id)
    
    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    owned_titles = profile_data.get('owned_titles', ['rookie'])
    balance = await get_user_balance(user_id)
    total_grabs = len(user.get('characters', []))

    titles_text = "╔═══════════════════╗\n    ✦ ᴛɪᴛʟᴇ sʜᴏᴘ ✦\n╚═══════════════════╝\n\n"

    free_titles = []
    buyable_titles = []
    
    for title_id, title_data in PROFILE_TITLES.items():
        title_name = title_data['name']
        price = title_data['price']
        requirement = title_data['requirement']
        color = title_data.get('color', '◇')

        if title_id in owned_titles:
            status = f"{color} ᴏᴡɴᴇᴅ"
        elif requirement:
            req_value = requirement['value']
            if total_grabs >= req_value:
                status = f"✅ ʀᴇᴀᴅʏ ᴛᴏ ᴜɴʟᴏᴄᴋ"
                free_titles.append(title_id)
            else:
                status = f"◇ {req_value - total_grabs} ᴍᴏʀᴇ ɢʀᴀʙs"
        elif balance >= price:
            status = f"💰 ₩ {price:,}"
            buyable_titles.append(title_id)
        else:
            status = f"🔒 ₩ {price:,}"

        titles_text += f"{title_name}\n{status}\n\n"

    titles_text += f"💰 ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ ◆ ₩ {balance:,}"

    keyboard = []
    
    if free_titles:
        row = []
        for title_id in free_titles:
            btn_text = f"✅ {PROFILE_TITLES[title_id]['name'].split()[1][:7]}"
            row.append(InlineKeyboardButton(btn_text, callback_data=f"unlock_title_{title_id}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
    
    row = []
    for title_id in buyable_titles[:4]:
        btn_text = f"💰 {PROFILE_TITLES[title_id]['name'].split()[1][:7]}"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"buy_title_{title_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    row = []
    for title_id in owned_titles[:6]:
        btn_text = f"✦ {PROFILE_TITLES[title_id]['name'].split()[1][:7]}"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"equip_title_{title_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="profile_shop")])

    await callback_query.message.edit_text(titles_text, reply_markup=InlineKeyboardMarkup(keyboard))


@shivuu.on_callback_query(filters.regex("^unlock_title_(.+)$"))
async def unlock_title_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    title_id = callback_query.data.split("_", 2)[2]

    if title_id not in PROFILE_TITLES:
        await callback_query.answer("◇ ɪɴᴠᴀʟɪᴅ ᴛɪᴛʟᴇ", show_alert=True)
        return

    title_data = PROFILE_TITLES[title_id]
    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    owned_titles = profile_data.get('owned_titles', [])

    if title_id in owned_titles:
        await callback_query.answer("◇ ᴀʟʀᴇᴀᴅʏ ᴜɴʟᴏᴄᴋᴇᴅ", show_alert=True)
        return

    owned_titles.append(title_id)

    await user_collection.update_one(
        {'id': user_id},
        {'$set': {'profile_data.owned_titles': owned_titles}}
    )

    await callback_query.answer(f"✅ ᴜɴʟᴏᴄᴋᴇᴅ {title_data['name']}", show_alert=True)
    await shop_titles_callback(client, callback_query)


@shivuu.on_callback_query(filters.regex("^buy_title_(.+)$"))
async def buy_title_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    title_id = callback_query.data.split("_", 2)[2]

    if title_id not in PROFILE_TITLES:
        await callback_query.answer("◇ ɪɴᴠᴀʟɪᴅ ᴛɪᴛʟᴇ", show_alert=True)
        return

    title_data = PROFILE_TITLES[title_id]
    price = title_data['price']

    user = await user_collection.find_one({'id': user_id})
    balance = user.get('balance', 0)
    profile_data = user.get('profile_data', {})
    owned_titles = profile_data.get('owned_titles', [])

    if title_id in owned_titles:
        await callback_query.answer("◇ ᴀʟʀᴇᴀᴅʏ ᴏᴡɴᴇᴅ", show_alert=True)
        return

    if balance < price:
        needed = price - balance
        await callback_query.answer(f"◇ ɴᴇᴇᴅ ₩ {needed:,} ᴍᴏʀᴇ", show_alert=True)
        return

    new_balance = balance - price
    owned_titles.append(title_id)

    await user_collection.update_one(
        {'id': user_id},
        {
            '$set': {
                'balance': new_balance,
                'profile_data.owned_titles': owned_titles
            }
        }
    )

    await callback_query.answer(f"✅ ᴘᴜʀᴄʜᴀsᴇᴅ\n-₩ {price:,}", show_alert=True)
    await shop_titles_callback(client, callback_query)


@shivuu.on_callback_query(filters.regex("^equip_title_(.+)$"))
async def equip_title_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    title_id = callback_query.data.split("_", 2)[2]

    if title_id not in PROFILE_TITLES:
        await callback_query.answer("◇ ɪɴᴠᴀʟɪᴅ ᴛɪᴛʟᴇ", show_alert=True)
        return

    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    owned_titles = profile_data.get('owned_titles', [])

    if title_id not in owned_titles:
        await callback_query.answer("◇ ɴᴏᴛ ᴏᴡɴᴇᴅ", show_alert=True)
        return

    await user_collection.update_one(
        {'id': user_id},
        {'$set': {'profile_data.title': title_id}}
    )

    await callback_query.answer(f"✦ ᴇǫᴜɪᴘᴘᴇᴅ", show_alert=True)
    await shop_titles_callback(client, callback_query)


@shivuu.on_callback_query(filters.regex("^shop_themes$"))
async def shop_themes_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    await initialize_profile_data(user_id)
    
    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    owned_themes = profile_data.get('owned_themes', ['default'])
    balance = await get_user_balance(user_id)

    themes_text = "╔═══════════════════╗\n    ✦ ᴛʜᴇᴍᴇ sʜᴏᴘ ✦\n╚═══════════════════╝\n\n"

    for theme_id, theme_data in PROFILE_THEMES.items():
        theme_name = theme_data['name']
        price = theme_data['price']
        vip_badge = " 👑" if theme_data.get('vip', False) else ""

        if theme_id in owned_themes:
            status = "✦ ᴏᴡɴᴇᴅ"
        elif balance >= price:
            status = f"💰 ₩ {price:,}"
        else:
            status = f"🔒 ₩ {price:,}"

        themes_text += f"{theme_name}{vip_badge}\n{theme_data['divider'][:17]}...\n{status}\n\n"

    themes_text += f"💰 ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ ◆ ₩ {balance:,}"

    keyboard = []
    row = []
    for theme_id, theme_data in PROFILE_THEMES.items():
        if theme_id not in owned_themes and theme_data['price'] > 0:
            if balance >= theme_data['price']:
                btn_text = f"💰 {theme_data['name'].split()[0][:7]}"
                row.append(InlineKeyboardButton(btn_text, callback_data=f"buy_theme_{theme_id}"))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
    
    if row:
        keyboard.append(row)

    row = []
    for theme_id in owned_themes:
        btn_text = f"✦ {PROFILE_THEMES[theme_id]['name'].split()[0][:7]}"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"equip_theme_{theme_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="profile_shop")])

    await callback_query.message.edit_text(themes_text, reply_markup=InlineKeyboardMarkup(keyboard))


@shivuu.on_callback_query(filters.regex("^buy_theme_(.+)$"))
async def buy_theme_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    theme_id = callback_query.data.split("_", 2)[2]

    if theme_id not in PROFILE_THEMES:
        await callback_query.answer("◇ ɪɴᴠᴀʟɪᴅ ᴛʜᴇᴍᴇ", show_alert=True)
        return

    theme_data = PROFILE_THEMES[theme_id]
    price = theme_data['price']

    user = await user_collection.find_one({'id': user_id})
    balance = user.get('balance', 0)
    profile_data = user.get('profile_data', {})
    owned_themes = profile_data.get('owned_themes', [])

    if theme_id in owned_themes:
        await callback_query.answer("◇ ᴀʟʀᴇᴀᴅʏ ᴏᴡɴᴇᴅ", show_alert=True)
        return

    if balance < price:
        needed = price - balance
        await callback_query.answer(f"◇ ɴᴇᴇᴅ ₩ {needed:,} ᴍᴏʀᴇ", show_alert=True)
        return

    new_balance = balance - price
    owned_themes.append(theme_id)

    await user_collection.update_one(
        {'id': user_id},
        {
            '$set': {
                'balance': new_balance,
                'profile_data.owned_themes': owned_themes
            }
        }
    )

    await callback_query.answer(f"✅ ᴘᴜʀᴄʜᴀsᴇᴅ\n-₩ {price:,}", show_alert=True)
    await shop_themes_callback(client, callback_query)


@shivuu.on_callback_query(filters.regex("^equip_theme_(.+)$"))
async def equip_theme_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    theme_id = callback_query.data.split("_", 2)[2]

    if theme_id not in PROFILE_THEMES:
        await callback_query.answer("◇ ɪɴᴠᴀʟɪᴅ ᴛʜᴇᴍᴇ", show_alert=True)
        return

    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    owned_themes = profile_data.get('owned_themes', [])

    if theme_id not in owned_themes:
        await callback_query.answer("◇ ɴᴏᴛ ᴏᴡɴᴇᴅ", show_alert=True)
        return

    await user_collection.update_one(
        {'id': user_id},
        {'$set': {'profile_data.theme': theme_id}}
    )

    await callback_query.answer(f"✦ ᴇǫᴜɪᴘᴘᴇᴅ", show_alert=True)
    await shop_themes_callback(client, callback_query)


@shivuu.on_callback_query(filters.regex("^shop_frames$"))
async def shop_frames_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    await initialize_profile_data(user_id)
    
    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    owned_frames = profile_data.get('owned_frames', ['none'])
    balance = await get_user_balance(user_id)

    frames_text = "╔═══════════════════╗\n    ✦ ғʀᴀᴍᴇ sʜᴏᴘ ✦\n╚═══════════════════╝\n\n"

    for frame_id, frame_data in AVATAR_FRAMES.items():
        frame_name = frame_data['name']
        price = frame_data['price']
        vip_badge = " 👑" if frame_data.get('vip', False) else ""

        if frame_id in owned_frames:
            status = "✦ ᴏᴡɴᴇᴅ"
        elif balance >= price:
            status = f"💰 ₩ {price:,}"
        else:
            status = f"🔒 ₩ {price:,}"

        preview = f"{frame_data['left']}ɴᴀᴍᴇ{frame_data['right']}" if frame_id != "none" else "ɴᴀᴍᴇ"
        frames_text += f"{frame_name}{vip_badge}\n{preview}\n{status}\n\n"

    frames_text += f"💰 ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ ◆ ₩ {balance:,}"

    keyboard = []
    row = []
    for frame_id, frame_data in AVATAR_FRAMES.items():
        if frame_id not in owned_frames and frame_data['price'] > 0:
            if balance >= frame_data['price']:
                btn_text = f"💰 {frame_data['name'].split()[0][:7]}"
                row.append(InlineKeyboardButton(btn_text, callback_data=f"buy_frame_{frame_id}"))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
    
    if row:
        keyboard.append(row)

    row = []
    for frame_id in owned_frames:
        btn_text = f"✦ {AVATAR_FRAMES[frame_id]['name'].split()[0][:7]}"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"equip_frame_{frame_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="profile_shop")])

    await callback_query.message.edit_text(frames_text, reply_markup=InlineKeyboardMarkup(keyboard))


@shivuu.on_callback_query(filters.regex("^buy_frame_(.+)$"))
async def buy_frame_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    frame_id = callback_query.data.split("_", 2)[2]

    if frame_id not in AVATAR_FRAMES:
        await callback_query.answer("◇ ɪɴᴠᴀʟɪᴅ ғʀᴀᴍᴇ", show_alert=True)
        return

    frame_data = AVATAR_FRAMES[frame_id]
    price = frame_data['price']

    user = await user_collection.find_one({'id': user_id})
    balance = user.get('balance', 0)
    profile_data = user.get('profile_data', {})
    owned_frames = profile_data.get('owned_frames', [])

    if frame_id in owned_frames:
        await callback_query.answer("◇ ᴀʟʀᴇᴀᴅʏ ᴏᴡɴᴇᴅ", show_alert=True)
        return

    if balance < price:
        needed = price - balance
        await callback_query.answer(f"◇ ɴᴇᴇᴅ ₩ {needed:,} ᴍᴏʀᴇ", show_alert=True)
        return

    new_balance = balance - price
    owned_frames.append(frame_id)

    await user_collection.update_one(
        {'id': user_id},
        {
            '$set': {
                'balance': new_balance,
                'profile_data.owned_frames': owned_frames
            }
        }
    )

    await callback_query.answer(f"✅ ᴘᴜʀᴄʜᴀsᴇᴅ\n-₩ {price:,}", show_alert=True)
    await shop_frames_callback(client, callback_query)


@shivuu.on_callback_query(filters.regex("^equip_frame_(.+)$"))
async def equip_frame_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    frame_id = callback_query.data.split("_", 2)[2]

    if frame_id not in AVATAR_FRAMES:
        await callback_query.answer("◇ ɪɴᴠᴀʟɪᴅ ғʀᴀᴍᴇ", show_alert=True)
        return

    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    owned_frames = profile_data.get('owned_frames', [])

    if frame_id not in owned_frames:
        await callback_query.answer("◇ ɴᴏᴛ ᴏᴡɴᴇᴅ", show_alert=True)
        return

    await user_collection.update_one(
        {'id': user_id},
        {'$set': {'profile_data.frame': frame_id}}
    )

    await callback_query.answer(f"✦ ᴇǫᴜɪᴘᴘᴇᴅ", show_alert=True)
    await shop_frames_callback(client, callback_query)


@shivuu.on_callback_query(filters.regex("^shop_emojis$"))
async def shop_emojis_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    await initialize_profile_data(user_id)
    
    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    owned_packs = profile_data.get('owned_emoji_packs', ['basic'])
    balance = await get_user_balance(user_id)

    emojis_text = "╔═══════════════════╗\n    ✦ ᴇᴍᴏᴊɪ sʜᴏᴘ ✦\n╚═══════════════════╝\n\n"

    for pack_id, pack_data in EMOJI_PACKS.items():
        pack_name = pack_data['name']
        price = pack_data['price']
        emojis = ' '.join(pack_data['emojis'][:8])

        if pack_id in owned_packs:
            status = "✦ ᴏᴡɴᴇᴅ"
        elif balance >= price:
            status = f"💰 ₩ {price:,}"
        else:
            status = f"🔒 ₩ {price:,}"

        emojis_text += f"{pack_name}\n{emojis}\n{status}\n\n"

    emojis_text += f"💰 ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ ◆ ₩ {balance:,}"

    keyboard = []
    row = []
    for pack_id, pack_data in EMOJI_PACKS.items():
        if pack_id not in owned_packs and pack_data['price'] > 0:
            if balance >= pack_data['price']:
                btn_text = f"💰 {pack_data['name'].split()[0][:7]}"
                row.append(InlineKeyboardButton(btn_text, callback_data=f"buy_emoji_{pack_id}"))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
    
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="profile_shop")])

    await callback_query.message.edit_text(emojis_text, reply_markup=InlineKeyboardMarkup(keyboard))


@shivuu.on_callback_query(filters.regex("^buy_emoji_(.+)$"))
async def buy_emoji_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    pack_id = callback_query.data.split("_", 2)[2]

    if pack_id not in EMOJI_PACKS:
        await callback_query.answer("◇ ɪɴᴠᴀʟɪᴅ ᴘᴀᴄᴋ", show_alert=True)
        return

    pack_data = EMOJI_PACKS[pack_id]
    price = pack_data['price']

    user = await user_collection.find_one({'id': user_id})
    balance = user.get('balance', 0)
    profile_data = user.get('profile_data', {})
    owned_packs = profile_data.get('owned_emoji_packs', [])

    if pack_id in owned_packs:
        await callback_query.answer("◇ ᴀʟʀᴇᴀᴅʏ ᴏᴡɴᴇᴅ", show_alert=True)
        return

    if balance < price:
        needed = price - balance
        await callback_query.answer(f"◇ ɴᴇᴇᴅ ₩ {needed:,} ᴍᴏʀᴇ", show_alert=True)
        return

    new_balance = balance - price
    owned_packs.append(pack_id)

    await user_collection.update_one(
        {'id': user_id},
        {
            '$set': {
                'balance': new_balance,
                'profile_data.owned_emoji_packs': owned_packs
            }
        }
    )

    await callback_query.answer(f"✅ ᴘᴜʀᴄʜᴀsᴇᴅ\n-₩ {price:,}", show_alert=True)
    await shop_emojis_callback(client, callback_query)


@shivuu.on_callback_query(filters.regex("^shop_bio$"))
async def shop_bio_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    await initialize_profile_data(user_id)
    
    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    current_bio = profile_data.get('bio', 'ɴᴏᴛ sᴇᴛ')
    last_update = profile_data.get('bio_last_update')

    cooldown_remaining = ""
    if last_update:
        time_diff = datetime.now() - datetime.fromisoformat(last_update)
        cooldown_minutes = BIO_COOLDOWN_MINUTES - (time_diff.total_seconds() / 60)
        if cooldown_minutes > 0:
            cooldown_remaining = f"\n⏰ {int(cooldown_minutes)}ᴍ ʟᴇғᴛ"

    bio_text = f"""╔═══════════════════╗
    ✦ ʙɪᴏ ᴇᴅɪᴛᴏʀ ✦
╚═══════════════════╝

ᴄᴜʀʀᴇɴᴛ ʙɪᴏ ◆
💭 {current_bio}

━━━━━━━━━━━━━━━━━
◇ ʀᴜʟᴇs ◇
◦ ᴍᴀx {BIO_MAX_LENGTH} ᴄʜᴀʀs
◦ ᴍᴀx {BIO_EMOJI_LIMIT} ᴇᴍᴏᴊɪs
◦ ɴᴏ ʙᴀᴅ ᴡᴏʀᴅs
◦ {BIO_COOLDOWN_MINUTES}ᴍ ᴄᴏᴏʟᴅᴏᴡɴ{cooldown_remaining}

ᴜsᴇ ◆ /setbio <text>
"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="profile_shop")]
    ])

    await callback_query.message.edit_text(bio_text, reply_markup=keyboard)


@shivuu.on_message(filters.command("setbio"))
async def set_bio_command(client: Client, message: Message) -> None:
    user_id = message.from_user.id
    await initialize_profile_data(user_id)

    if len(message.command) < 2:
        await message.reply_text("◇ ᴘʀᴏᴠɪᴅᴇ ʙɪᴏ ᴛᴇxᴛ\nᴜsᴀɢᴇ ◆ /setbio <text>")
        return

    bio_text = message.text.split(None, 1)[1]

    if len(bio_text) > BIO_MAX_LENGTH:
        await message.reply_text(f"◇ ʙɪᴏ ᴛᴏᴏ ʟᴏɴɢ\nᴍᴀx {BIO_MAX_LENGTH} ᴄʜᴀʀs")
        return

    if contains_bad_words(bio_text):
        await message.reply_text("◇ ɪɴᴀᴘᴘʀᴏᴘʀɪᴀᴛᴇ ʟᴀɴɢᴜᴀɢᴇ")
        return

    emoji_count = count_emojis(bio_text)
    if emoji_count > BIO_EMOJI_LIMIT:
        await message.reply_text(f"◇ ᴛᴏᴏ ᴍᴀɴʏ ᴇᴍᴏᴊɪs\nᴍᴀx {BIO_EMOJI_LIMIT}")
        return

    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    last_update = profile_data.get('bio_last_update')

    if last_update:
        time_diff = datetime.now() - datetime.fromisoformat(last_update)
        cooldown_minutes = BIO_COOLDOWN_MINUTES - (time_diff.total_seconds() / 60)
        if cooldown_minutes > 0:
            await message.reply_text(f"⏰ ᴡᴀɪᴛ {int(cooldown_minutes)}ᴍ")
            return

    await user_collection.update_one(
        {'id': user_id},
        {
            '$set': {
                'profile_data.bio': bio_text,
                'profile_data.bio_last_update': datetime.now().isoformat()
            }
        }
    )

    await message.reply_text(f"✅ ʙɪᴏ ᴜᴘᴅᴀᴛᴇᴅ\n\n💭 {bio_text}")


@shivuu.on_callback_query(filters.regex("^back_to_profile$"))
async def back_to_profile_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    
    try:
        info_text, photo_id = await get_user_info(user_id)
    except Exception as e:
        await callback_query.answer("◇ ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✦ sʜᴏᴘ", callback_data="profile_shop"),
            InlineKeyboardButton("📊 sᴛᴀᴛs", callback_data="view_stats")
        ],
        [
            InlineKeyboardButton("🎁 ʀᴇᴡᴀʀᴅs", callback_data="daily_rewards"),
            InlineKeyboardButton("🏆 ʙᴀᴅɢᴇs", callback_data="view_badges")
        ],
        [InlineKeyboardButton("◇ sᴜᴘᴘᴏʀᴛ", url=f"https://t.me/{SUPPORT_CHAT}")]
    ])

    if photo_id:
        photo = await shivuu.download_media(photo_id)
        await callback_query.message.delete()
        await client.send_photo(
            callback_query.message.chat.id,
            photo,
            caption=info_text,
            reply_markup=keyboard
        )
        if os.path.exists(photo):
            os.remove(photo)
    else:
        await callback_query.message.edit_text(
            info_text,
            disable_web_page_preview=True,
            reply_markup=keyboard
        )
