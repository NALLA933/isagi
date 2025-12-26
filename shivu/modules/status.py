from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from shivu import shivuu, SUPPORT_CHAT, user_collection, collection
import os
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any


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
        if num >= 1000000:
            return f"{num/1000000:.1f}ᴍ"
        elif num >= 1000:
            return f"{num/1000:.1f}ᴋ"
        return str(num)


PROFILE_TITLES = {
    "rookie": {
        "name": "✦ ʀᴏᴏᴋɪᴇ ʜᴜɴᴛᴇʀ",
        "price": 0,
        "requirement": {"type": "grabs", "value": 0},
        "symbol": "◆"
    },
    "explorer": {
        "name": "⟡ ᴇxᴘʟᴏʀᴇʀ",
        "price": 0,
        "requirement": {"type": "grabs", "value": 50},
        "symbol": "◇"
    },
    "collector": {
        "name": "◈ ᴄᴏʟʟᴇᴄᴛᴏʀ",
        "price": 0,
        "requirement": {"type": "grabs", "value": 100},
        "symbol": "◊"
    },
    "master": {
        "name": "★ ᴍᴀsᴛᴇʀ ʜᴜɴᴛᴇʀ",
        "price": 0,
        "requirement": {"type": "grabs", "value": 250},
        "symbol": "☆"
    },
    "elite": {
        "name": "◆ ᴇʟɪᴛᴇ ʜᴜɴᴛᴇʀ",
        "price": 50000,
        "requirement": None,
        "symbol": "◈"
    },
    "legend": {
        "name": "⚔ ʟᴇɢᴇɴᴅᴀʀʏ",
        "price": 100000,
        "requirement": None,
        "symbol": "⚜"
    },
    "mythic": {
        "name": "✧ ᴍʏᴛʜɪᴄ ʟᴏʀᴅ",
        "price": 250000,
        "requirement": None,
        "symbol": "✦"
    },
    "shadow": {
        "name": "☾ sʜᴀᴅᴏᴡ ᴋɪɴɢ",
        "price": 500000,
        "requirement": None,
        "symbol": "☽"
    },
    "divine": {
        "name": "✶ ᴅɪᴠɪɴᴇ ᴇᴍᴘᴇʀᴏʀ",
        "price": 1000000,
        "requirement": None,
        "symbol": "✷"
    },
    "supreme": {
        "name": "⧫ sᴜᴘʀᴇᴍᴇ ᴏᴠᴇʀʟᴏʀᴅ",
        "price": 2500000,
        "requirement": None,
        "symbol": "⧈"
    },
    "cosmic": {
        "name": "✨ ᴄᴏsᴍɪᴄ ᴇɴᴛɪᴛʏ",
        "price": 5000000,
        "requirement": None,
        "symbol": "✧"
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
        "corner_br": "╯"
    },
    "neon": {
        "name": "ɴᴇᴏɴ ɢʟᴏᴡ",
        "price": 25000,
        "divider": "━━━━━━━━━━━━━━━━━",
        "bullet": "▸",
        "corner_tl": "┏",
        "corner_tr": "┓",
        "corner_bl": "┗",
        "corner_br": "┛"
    },
    "luxury": {
        "name": "ʟᴜxᴜʀʏ ɢᴏʟᴅ",
        "price": 35000,
        "divider": "═══════════════════",
        "bullet": "◈",
        "corner_tl": "╔",
        "corner_tr": "╗",
        "corner_bl": "╚",
        "corner_br": "╝"
    },
    "cyber": {
        "name": "ᴄʏʙᴇʀ ᴛᴇᴄʜ",
        "price": 50000,
        "divider": "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰",
        "bullet": "►",
        "corner_tl": "┌",
        "corner_tr": "┐",
        "corner_bl": "└",
        "corner_br": "┘"
    },
    "royal": {
        "name": "ʀᴏʏᴀʟ ᴇʟᴇɢᴀɴᴄᴇ",
        "price": 75000,
        "divider": "◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆◆",
        "bullet": "♦",
        "corner_tl": "╔",
        "corner_tr": "╗",
        "corner_bl": "╚",
        "corner_br": "╝"
    },
    "cosmic": {
        "name": "ᴄᴏsᴍɪᴄ ᴠᴏɪᴅ",
        "price": 100000,
        "divider": "✦━━━━━━━━━━━━━━━✦",
        "bullet": "✧",
        "corner_tl": "╔",
        "corner_tr": "╗",
        "corner_bl": "╚",
        "corner_br": "╝"
    },
    "minimal": {
        "name": "ᴍɪɴɪᴍᴀʟ ᴄʟᴇᴀɴ",
        "price": 150000,
        "divider": "·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·",
        "bullet": "·",
        "corner_tl": " ",
        "corner_tr": " ",
        "corner_bl": " ",
        "corner_br": " "
    }
}

AVATAR_FRAMES = {
    "none": {
        "name": "ɴᴏ ғʀᴀᴍᴇ",
        "price": 0,
        "left": "",
        "right": ""
    },
    "diamond": {
        "name": "ᴅɪᴀᴍᴏɴᴅ",
        "price": 20000,
        "left": "◆ ",
        "right": " ◆"
    },
    "star": {
        "name": "sᴛᴀʀ",
        "price": 30000,
        "left": "★ ",
        "right": " ★"
    },
    "moon": {
        "name": "ᴍᴏᴏɴ",
        "price": 40000,
        "left": "☾ ",
        "right": " ☽"
    },
    "crown": {
        "name": "ᴄʀᴏᴡɴ",
        "price": 50000,
        "left": "♔ ",
        "right": " ♕"
    },
    "wings": {
        "name": "ᴡɪɴɢs",
        "price": 75000,
        "left": "◄ ",
        "right": " ►"
    },
    "flame": {
        "name": "ғʟᴀᴍᴇ",
        "price": 100000,
        "left": "◈ ",
        "right": " ◈"
    },
    "cosmic": {
        "name": "ᴄᴏsᴍɪᴄ",
        "price": 150000,
        "left": "✦ ",
        "right": " ✦"
    },
    "ultimate": {
        "name": "ᴜʟᴛɪᴍᴀᴛᴇ",
        "price": 250000,
        "left": "⧫ ",
        "right": " ⧫"
    }
}

EMOJI_PACKS = {
    "basic": {
        "name": "ʙᴀsɪᴄ",
        "price": 0,
        "emojis": ["◦", "◇", "◆"]
    },
    "geometric": {
        "name": "ɢᴇᴏᴍᴇᴛʀɪᴄ",
        "price": 15000,
        "emojis": ["◆", "◇", "◈", "◊", "○", "●", "◐", "◑"]
    },
    "stars": {
        "name": "sᴛᴀʀs",
        "price": 25000,
        "emojis": ["★", "☆", "✦", "✧", "✶", "✷", "✸", "✹"]
    },
    "arrows": {
        "name": "ᴀʀʀᴏᴡs",
        "price": 35000,
        "emojis": ["►", "▸", "▹", "▻", "◄", "◂", "◃", "◅"]
    },
    "celestial": {
        "name": "ᴄᴇʟᴇsᴛɪᴀʟ",
        "price": 50000,
        "emojis": ["☾", "☽", "☼", "☀", "☁", "☂", "☃", "☄"]
    },
    "mystical": {
        "name": "ᴍʏsᴛɪᴄᴀʟ",
        "price": 75000,
        "emojis": ["⚜", "⚝", "⚞", "⚟", "⚠", "⚡", "⚢", "⚣"]
    },
    "royal": {
        "name": "ʀᴏʏᴀʟ",
        "price": 100000,
        "emojis": ["♔", "♕", "♖", "♗", "♘", "♙", "♚", "♛"]
    }
}

BAD_WORDS = [
    "fuck", "shit", "ass", "bitch", "damn", "hell",
    "sex", "porn", "nude", "dick", "pussy", "nigger",
    "fag", "retard", "cunt", "cock", "whore", "rape"
]

BIO_COOLDOWN_MINUTES = 60
BIO_MAX_LENGTH = 80
BIO_EMOJI_LIMIT = 8


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

    has_pass = "◆" if existing_user.get('pass') else "◇"
    tokens = existing_user.get('tokens', 0)
    
    framed_name = f"{active_frame['left']}{first_name}{active_frame['right']}"
    bio = profile_data.get('bio', '')
    divider = active_theme['divider']
    corner_tl = active_theme['corner_tl']
    corner_tr = active_theme['corner_tr']
    corner_bl = active_theme['corner_bl']
    corner_br = active_theme['corner_br']

    info_text = f"""{corner_tl}{divider}{corner_tr}
{framed_name}
{active_title}
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
ɢʀᴀʙ sᴛᴀᴛs ◆
◦ ᴛᴏᴛᴀʟ ◆ `{grab_stats['total_grabs']}`
◦ ᴛᴏᴅᴀʏ ◆ `{grab_stats['today_grabs']}`
◦ ᴡᴇᴇᴋʟʏ ◆ `{grab_stats['weekly_grabs']}`
◦ ᴍᴏɴᴛʜʟʏ ◆ `{grab_stats['monthly_grabs']}`
{divider}
ᴘᴀss ◆ {has_pass}  ◆  ᴛᴏᴋᴇɴs ◆ `{tokens:,}`
{divider}"""

    if bio:
        info_text += f"\n{bio}\n"

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


@shivuu.on_message(filters.command("sinfo"))
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
        return await m.edit(f"◇ sᴏᴍᴇᴛʜɪɴɢ ᴡᴇɴᴛ ᴡʀᴏɴɢ ◇\nʀᴇᴘᴏʀᴛ ᴀᴛ @{SUPPORT_CHAT}")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✦ sʜᴏᴘ", callback_data="profile_shop"),
            InlineKeyboardButton("◆ sᴛᴀᴛs", callback_data="view_stats")
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


@shivuu.on_callback_query(filters.regex("^view_stats$"))
async def view_stats_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    user = await user_collection.find_one({'id': user_id})
    
    if not user:
        await callback_query.answer("ᴜsᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
        return

    grab_stats = await get_grab_stats(user_id)
    total_count = len(user.get('characters', []))
    
    rarity_counts = {}
    for char in user.get('characters', []):
        rarity = char.get('rarity', '🟢 Common')
        rarity_emoji = rarity.split(' ')[0] if ' ' in rarity else rarity
        rarity_counts[rarity_emoji] = rarity_counts.get(rarity_emoji, 0) + 1
    
    sorted_rarities = sorted(rarity_counts.items(), key=lambda x: x[1], reverse=True)
    
    stats_text = f"""╔═══════════════════╗
    ✦ ᴅᴇᴛᴀɪʟᴇᴅ sᴛᴀᴛs ✦
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
        stats_text += f"{rarity_emoji} ◆ {count} ({percentage:.1f}%)\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="back_to_profile")]
    ])
    
    await callback_query.message.edit_text(stats_text, reply_markup=keyboard)


@shivuu.on_callback_query(filters.regex("^profile_shop$"))
async def profile_shop_callback(client: Client, callback_query: CallbackQuery) -> None:
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

    shop_text = """╔═══════════════════╗
    ✦ ᴘʀᴏғɪʟᴇ sʜᴏᴘ ✦
╚═══════════════════╝

ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ ᴄᴜsᴛᴏᴍɪᴢᴀᴛɪᴏɴ sʜᴏᴘ
ᴘᴇʀsᴏɴᴀʟɪᴢᴇ ʏᴏᴜʀ ᴘʀᴏғɪʟᴇ ᴡɪᴛʜ
ᴇxᴄʟᴜsɪᴠᴇ ᴘʀᴇᴍɪᴜᴍ ɪᴛᴇᴍs

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

    titles_text = "╔═══════════════════╗\n    ✦ ᴛɪᴛʟᴇ sʜᴏᴘ ✦\n╚═══════════════════╝\n\n"

    for title_id, title_data in PROFILE_TITLES.items():
        title_name = title_data['name']
        price = title_data['price']
        requirement = title_data['requirement']

        if title_id in owned_titles:
            status = "◆ ᴏᴡɴᴇᴅ"
        elif requirement:
            req_value = requirement['value']
            status = f"◇ ᴜɴʟᴏᴄᴋ ᴀᴛ {req_value} ɢʀᴀʙs"
        elif balance >= price:
            status = f"◈ ₩ {price:,}"
        else:
            status = f"◊ ₩ {price:,}"

        titles_text += f"{title_name}\n{status}\n\n"

    titles_text += f"◆ ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ ◆ ₩ {balance:,}"

    keyboard = []
    row = []
    for title_id, title_data in PROFILE_TITLES.items():
        if title_id not in owned_titles and title_data['requirement'] is None:
            if balance >= title_data['price']:
                btn_text = f"◈ {title_data['name'].split()[1][:8]}"
                row.append(InlineKeyboardButton(btn_text, callback_data=f"buy_title_{title_id}"))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
    
    if row:
        keyboard.append(row)

    row = []
    for title_id in owned_titles:
        btn_text = f"✦ {PROFILE_TITLES[title_id]['name'].split()[1][:8]}"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"equip_title_{title_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="profile_shop")])

    await callback_query.message.edit_text(titles_text, reply_markup=InlineKeyboardMarkup(keyboard))


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
        await callback_query.answer("◇ ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ᴏᴡɴ ᴛʜɪs", show_alert=True)
        return

    if balance < price:
        await callback_query.answer(f"◇ ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ\nɴᴇᴇᴅ ₩ {price:,}", show_alert=True)
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

    await callback_query.answer(f"◆ ᴘᴜʀᴄʜᴀsᴇᴅ ғᴏʀ ₩ {price:,}", show_alert=True)
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
        await callback_query.answer("◇ ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴛʜɪs", show_alert=True)
        return

    await user_collection.update_one(
        {'id': user_id},
        {'$set': {'profile_data.title': title_id}}
    )

    await callback_query.answer(f"◆ ᴇǫᴜɪᴘᴘᴇᴅ", show_alert=True)
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

        if theme_id in owned_themes:
            status = "◆ ᴏᴡɴᴇᴅ"
        elif balance >= price:
            status = f"◈ ₩ {price:,}"
        else:
            status = f"◊ ₩ {price:,}"

        themes_text += f"{theme_name}\n{theme_data['divider'][:17]}...\n{status}\n\n"

    themes_text += f"◆ ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ ◆ ₩ {balance:,}"

    keyboard = []
    row = []
    for theme_id, theme_data in PROFILE_THEMES.items():
        if theme_id not in owned_themes and theme_data['price'] > 0:
            if balance >= theme_data['price']:
                btn_text = f"◈ {theme_data['name'].split()[0][:8]}"
                row.append(InlineKeyboardButton(btn_text, callback_data=f"buy_theme_{theme_id}"))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
    
    if row:
        keyboard.append(row)

    row = []
    for theme_id in owned_themes:
        btn_text = f"✦ {PROFILE_THEMES[theme_id]['name'].split()[0][:8]}"
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
        await callback_query.answer("◇ ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ᴏᴡɴ ᴛʜɪs", show_alert=True)
        return

    if balance < price:
        await callback_query.answer(f"◇ ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ\nɴᴇᴇᴅ ₩ {price:,}", show_alert=True)
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

    await callback_query.answer(f"◆ ᴘᴜʀᴄʜᴀsᴇᴅ ғᴏʀ ₩ {price:,}", show_alert=True)
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
        await callback_query.answer("◇ ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴛʜɪs", show_alert=True)
        return

    await user_collection.update_one(
        {'id': user_id},
        {'$set': {'profile_data.theme': theme_id}}
    )

    await callback_query.answer(f"◆ ᴇǫᴜɪᴘᴘᴇᴅ", show_alert=True)
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

        if frame_id in owned_frames:
            status = "◆ ᴏᴡɴᴇᴅ"
        elif balance >= price:
            status = f"◈ ₩ {price:,}"
        else:
            status = f"◊ ₩ {price:,}"

        preview = f"{frame_data['left']}ɴᴀᴍᴇ{frame_data['right']}" if frame_id != "none" else "ɴᴀᴍᴇ"
        frames_text += f"{frame_name}\n{preview}\n{status}\n\n"

    frames_text += f"◆ ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ ◆ ₩ {balance:,}"

    keyboard = []
    row = []
    for frame_id, frame_data in AVATAR_FRAMES.items():
        if frame_id not in owned_frames and frame_data['price'] > 0:
            if balance >= frame_data['price']:
                btn_text = f"◈ {frame_data['name'].split()[0][:8]}"
                row.append(InlineKeyboardButton(btn_text, callback_data=f"buy_frame_{frame_id}"))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
    
    if row:
        keyboard.append(row)

    row = []
    for frame_id in owned_frames:
        btn_text = f"✦ {AVATAR_FRAMES[frame_id]['name'].split()[0][:8]}"
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
        await callback_query.answer("◇ ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ᴏᴡɴ ᴛʜɪs", show_alert=True)
        return

    if balance < price:
        await callback_query.answer(f"◇ ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ\nɴᴇᴇᴅ ₩ {price:,}", show_alert=True)
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

    await callback_query.answer(f"◆ ᴘᴜʀᴄʜᴀsᴇᴅ ғᴏʀ ₩ {price:,}", show_alert=True)
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
        await callback_query.answer("◇ ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴛʜɪs", show_alert=True)
        return

    await user_collection.update_one(
        {'id': user_id},
        {'$set': {'profile_data.frame': frame_id}}
    )

    await callback_query.answer(f"◆ ᴇǫᴜɪᴘᴘᴇᴅ", show_alert=True)
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
            status = "◆ ᴏᴡɴᴇᴅ"
        elif balance >= price:
            status = f"◈ ₩ {price:,}"
        else:
            status = f"◊ ₩ {price:,}"

        emojis_text += f"{pack_name}\n{emojis}\n{status}\n\n"

    emojis_text += f"◆ ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ ◆ ₩ {balance:,}"

    keyboard = []
    row = []
    for pack_id, pack_data in EMOJI_PACKS.items():
        if pack_id not in owned_packs and pack_data['price'] > 0:
            if balance >= pack_data['price']:
                btn_text = f"◈ {pack_data['name'].split()[0][:8]}"
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
        await callback_query.answer("◇ ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ᴏᴡɴ ᴛʜɪs", show_alert=True)
        return

    if balance < price:
        await callback_query.answer(f"◇ ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ\nɴᴇᴇᴅ ₩ {price:,}", show_alert=True)
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

    await callback_query.answer(f"◆ ᴘᴜʀᴄʜᴀsᴇᴅ ғᴏʀ ₩ {price:,}", show_alert=True)
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
            cooldown_remaining = f"\n◆ ᴄᴏᴏʟᴅᴏᴡɴ ◆ {int(cooldown_minutes)} ᴍɪɴs"

    bio_text = f"""╔═══════════════════╗
    ✦ ʙɪᴏ ᴇᴅɪᴛᴏʀ ✦
╚═══════════════════╝

ᴄᴜʀʀᴇɴᴛ ʙɪᴏ ◆ {current_bio}

◇ ʀᴜʟᴇs ◇
◦ ᴍᴀx {BIO_MAX_LENGTH} ᴄʜᴀʀs
◦ ᴍᴀx {BIO_EMOJI_LIMIT} ᴇᴍᴏᴊɪs
◦ ɴᴏ ʙᴀᴅ ᴡᴏʀᴅs
◦ {BIO_COOLDOWN_MINUTES} ᴍɪɴ ᴄᴏᴏʟᴅᴏᴡɴ{cooldown_remaining}

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
            await message.reply_text(f"◇ ᴄᴏᴏʟᴅᴏᴡɴ\nᴡᴀɪᴛ {int(cooldown_minutes)} ᴍɪɴs")
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

    await message.reply_text(f"◆ ʙɪᴏ ᴜᴘᴅᴀᴛᴇᴅ\n\n{bio_text}")


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
            InlineKeyboardButton("◆ sᴛᴀᴛs", callback_data="view_stats")
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
