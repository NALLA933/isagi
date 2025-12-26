from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from shivu import shivuu, SUPPORT_CHAT, user_collection, collection
import os
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any


PROFILE_TITLES = {
    "rookie": {
        "name": "🌱 Rookie Grabber",
        "price": 0,
        "requirement": {"type": "grabs", "value": 0}
    },
    "hunter": {
        "name": "🎯 Hunter",
        "price": 0,
        "requirement": {"type": "grabs", "value": 50}
    },
    "collector": {
        "name": "📦 Collector",
        "price": 0,
        "requirement": {"type": "grabs", "value": 100}
    },
    "master": {
        "name": "⭐ Master Hunter",
        "price": 0,
        "requirement": {"type": "grabs", "value": 250}
    },
    "elite": {
        "name": "💎 Elite Hunter",
        "price": 50000,
        "requirement": None
    },
    "legend": {
        "name": "🏆 Legendary",
        "price": 100000,
        "requirement": None
    },
    "mythic": {
        "name": "🌟 Mythic Lord",
        "price": 250000,
        "requirement": None
    },
    "shadow": {
        "name": "🌑 Shadow King",
        "price": 500000,
        "requirement": None
    },
    "divine": {
        "name": "✨ Divine Emperor",
        "price": 1000000,
        "requirement": None
    },
    "supreme": {
        "name": "👑 Supreme Overlord",
        "price": 2500000,
        "requirement": None
    }
}

PROFILE_THEMES = {
    "default": {
        "name": "Default",
        "price": 0,
        "divider": "───────────────────",
        "bullet": "•",
        "style": "standard"
    },
    "luxury": {
        "name": "💰 Luxury",
        "price": 25000,
        "divider": "═══════════════════",
        "bullet": "◈",
        "style": "elegant"
    },
    "neon": {
        "name": "⚡ Neon",
        "price": 35000,
        "divider": "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
        "bullet": "►",
        "style": "modern"
    },
    "royal": {
        "name": "👑 Royal",
        "price": 50000,
        "divider": "━━━━━━━━━━━━━━━━━━━",
        "bullet": "♦",
        "style": "premium"
    },
    "mystical": {
        "name": "🔮 Mystical",
        "price": 75000,
        "divider": "✦═════════════════✦",
        "bullet": "✧",
        "style": "mystical"
    },
    "fire": {
        "name": "🔥 Fire",
        "price": 100000,
        "divider": "▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂",
        "bullet": "►",
        "style": "intense"
    }
}

AVATAR_FRAMES = {
    "none": {
        "name": "No Frame",
        "price": 0,
        "left": "",
        "right": ""
    },
    "crown": {
        "name": "👑 Crown",
        "price": 20000,
        "left": "👑 ",
        "right": " 👑"
    },
    "fire": {
        "name": "🔥 Fire",
        "price": 30000,
        "left": "🔥 ",
        "right": " 🔥"
    },
    "lightning": {
        "name": "⚡ Lightning",
        "price": 40000,
        "left": "⚡ ",
        "right": " ⚡"
    },
    "star": {
        "name": "⭐ Star",
        "price": 50000,
        "left": "⭐ ",
        "right": " ⭐"
    },
    "diamond": {
        "name": "💎 Diamond",
        "price": 75000,
        "left": "💎 ",
        "right": " 💎"
    },
    "wings": {
        "name": "🦋 Wings",
        "price": 100000,
        "left": "🦋 ",
        "right": " 🦋"
    },
    "dragon": {
        "name": "🐉 Dragon",
        "price": 150000,
        "left": "🐉 ",
        "right": " 🐉"
    }
}

EMOJI_PACKS = {
    "basic": {
        "name": "Basic Pack",
        "price": 0,
        "emojis": ["⭐", "💫", "✨"]
    },
    "elements": {
        "name": "🌊 Elements",
        "price": 15000,
        "emojis": ["🔥", "💧", "🌪️", "⚡", "🌍"]
    },
    "cosmic": {
        "name": "🌌 Cosmic",
        "price": 25000,
        "emojis": ["🌟", "✨", "💫", "🌠", "🪐"]
    },
    "royal": {
        "name": "👑 Royal",
        "price": 35000,
        "emojis": ["👑", "💎", "🏆", "⚜️", "🔱"]
    },
    "mystical": {
        "name": "🔮 Mystical",
        "price": 50000,
        "emojis": ["🔮", "✨", "🌙", "⭐", "🔯"]
    }
}

BAD_WORDS = [
    "fuck", "shit", "ass", "bitch", "damn", "hell",
    "sex", "porn", "nude", "dick", "pussy", "nigger",
    "fag", "retard", "cunt", "cock", "whore"
]

BIO_COOLDOWN_MINUTES = 60
BIO_MAX_LENGTH = 60
BIO_EMOJI_LIMIT = 5


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
        return "Deleted account", None

    user_id = user.id
    username = user.username or "None"
    existing_user = await user_collection.find_one({'id': user_id})
    
    if not existing_user:
        return "User not found in database", None

    first_name = user.first_name
    global_rank = await get_global_rank(user_id)
    global_count = await collection.count_documents({})
    total_count = len(existing_user.get('characters', []))
    photo_id = user.photo.big_file_id if user.photo else None
    balance = await get_user_balance(user_id)
    global_coin_rank = await user_collection.count_documents({'balance': {'$gt': balance}}) + 1

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

    has_pass = "✅" if existing_user.get('pass') else "❌"
    tokens = existing_user.get('tokens', 0)
    balance_formatted = f"{balance:,}"
    tokens_formatted = f"{tokens:,}"

    framed_name = f"{active_frame['left']}{first_name}{active_frame['right']}"
    bio = profile_data.get('bio', '')
    divider = active_theme['divider']

    info_text = f"""
「 ✨ 𝙃𝙐𝙉𝙏𝙀𝙍 𝙇𝙄𝘾𝙀𝙉𝙎𝙀 ✨ 」
{divider}
{framed_name}
{active_title}
{divider}
𝙐𝙎𝙀𝙍 𝙄𝘿 : `{user_id}`
𝙐𝙎𝙀𝙍𝙉𝘼𝙈𝙀 : @{username}
{divider}
𝙎𝙇𝘼𝙑𝙀𝙎 𝗖𝗢𝗨𝗡𝗧 : `{total_count}` / `{global_count}`
𝙂𝙇𝙊𝘽𝘼𝙇 𝙍𝘼𝙉𝙆 : `{global_rank}`
{divider}
𝙒𝙀𝘼𝙇𝙏𝙃 : ₩`{balance_formatted}`
𝙂𝙇𝙊𝘽𝘼𝙇 𝙒𝙀𝘼𝙇𝙏𝙃 𝙍𝘼𝙉𝙆 : `{global_coin_rank}`
{divider}
𝙋𝙖𝙨𝙨 : {has_pass}
𝙏𝙊𝙆𝙀𝙉𝙎 : `{tokens_formatted}`
{divider}"""

    if bio:
        info_text += f"\n💭 {bio}\n{divider}"

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
    
    m = await message.reply_text("Getting Your Hunter License...")
    
    try:
        info_text, photo_id = await get_user_info(user)
    except Exception as e:
        print(f"Error in profile command: {e}")
        return await m.edit(f"Sorry something went wrong. Report at @{SUPPORT_CHAT}")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍️ Profile Shop", callback_data="profile_shop")],
        [InlineKeyboardButton("Support", url=f"https://t.me/{SUPPORT_CHAT}")]
    ])

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "Start Me in PM First",
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


@shivuu.on_callback_query(filters.regex("^profile_shop$"))
async def profile_shop_callback(client: Client, callback_query: CallbackQuery) -> None:
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏷️ Titles", callback_data="shop_titles")],
        [InlineKeyboardButton("🎨 Themes", callback_data="shop_themes")],
        [InlineKeyboardButton("🖼️ Frames", callback_data="shop_frames")],
        [InlineKeyboardButton("😀 Emoji Packs", callback_data="shop_emojis")],
        [InlineKeyboardButton("📝 Edit Bio", callback_data="shop_bio")],
        [InlineKeyboardButton("« Back", callback_data="back_to_profile")]
    ])

    shop_text = """
🛍️ **PROFILE SHOP** 🛍️

Welcome to the Profile Customization Shop!
Personalize your profile with exclusive items.

Select a category to browse:
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

    titles_text = "🏷️ **TITLE SHOP** 🏷️\n\n"

    for title_id, title_data in PROFILE_TITLES.items():
        title_name = title_data['name']
        price = title_data['price']
        requirement = title_data['requirement']

        if title_id in owned_titles:
            status = "✅ Owned"
        elif requirement:
            req_value = requirement['value']
            status = f"🔒 Unlock at {req_value} grabs"
        elif balance >= price:
            status = f"💰 ₩{price:,}"
        else:
            status = f"🔒 ₩{price:,}"

        titles_text += f"{title_name}\n{status}\n\n"

    titles_text += f"\n💵 Your Balance: ₩{balance:,}"

    keyboard = []
    for title_id, title_data in PROFILE_TITLES.items():
        if title_id not in owned_titles and title_data['requirement'] is None:
            if balance >= title_data['price']:
                keyboard.append([
                    InlineKeyboardButton(
                        f"Buy {title_data['name']}",
                        callback_data=f"buy_title_{title_id}"
                    )
                ])

    for title_id in owned_titles:
        keyboard.append([
            InlineKeyboardButton(
                f"Equip {PROFILE_TITLES[title_id]['name']}",
                callback_data=f"equip_title_{title_id}"
            )
        ])

    keyboard.append([InlineKeyboardButton("« Back", callback_data="profile_shop")])

    await callback_query.message.edit_text(
        titles_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@shivuu.on_callback_query(filters.regex("^buy_title_(.+)$"))
async def buy_title_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    title_id = callback_query.data.split("_", 2)[2]

    if title_id not in PROFILE_TITLES:
        await callback_query.answer("Invalid title!", show_alert=True)
        return

    title_data = PROFILE_TITLES[title_id]
    price = title_data['price']

    user = await user_collection.find_one({'id': user_id})
    balance = user.get('balance', 0)
    profile_data = user.get('profile_data', {})
    owned_titles = profile_data.get('owned_titles', [])

    if title_id in owned_titles:
        await callback_query.answer("You already own this title!", show_alert=True)
        return

    if balance < price:
        await callback_query.answer(
            f"Insufficient balance! Need ₩{price:,}",
            show_alert=True
        )
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

    await callback_query.answer(
        f"✅ Purchased {title_data['name']} for ₩{price:,}!",
        show_alert=True
    )
    await shop_titles_callback(client, callback_query)


@shivuu.on_callback_query(filters.regex("^equip_title_(.+)$"))
async def equip_title_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    title_id = callback_query.data.split("_", 2)[2]

    if title_id not in PROFILE_TITLES:
        await callback_query.answer("Invalid title!", show_alert=True)
        return

    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    owned_titles = profile_data.get('owned_titles', [])

    if title_id not in owned_titles:
        await callback_query.answer("You don't own this title!", show_alert=True)
        return

    await user_collection.update_one(
        {'id': user_id},
        {'$set': {'profile_data.title': title_id}}
    )

    await callback_query.answer(
        f"✅ Equipped {PROFILE_TITLES[title_id]['name']}!",
        show_alert=True
    )
    await shop_titles_callback(client, callback_query)


@shivuu.on_callback_query(filters.regex("^shop_themes$"))
async def shop_themes_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    await initialize_profile_data(user_id)
    
    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    owned_themes = profile_data.get('owned_themes', ['default'])
    balance = await get_user_balance(user_id)

    themes_text = "🎨 **THEME SHOP** 🎨\n\n"

    for theme_id, theme_data in PROFILE_THEMES.items():
        theme_name = theme_data['name']
        price = theme_data['price']

        if theme_id in owned_themes:
            status = "✅ Owned"
        elif balance >= price:
            status = f"💰 ₩{price:,}"
        else:
            status = f"🔒 ₩{price:,}"

        themes_text += f"{theme_name}\n{theme_data['divider'][:15]}...\n{status}\n\n"

    themes_text += f"\n💵 Your Balance: ₩{balance:,}"

    keyboard = []
    for theme_id, theme_data in PROFILE_THEMES.items():
        if theme_id not in owned_themes and theme_data['price'] > 0:
            if balance >= theme_data['price']:
                keyboard.append([
                    InlineKeyboardButton(
                        f"Buy {theme_data['name']}",
                        callback_data=f"buy_theme_{theme_id}"
                    )
                ])

    for theme_id in owned_themes:
        keyboard.append([
            InlineKeyboardButton(
                f"Equip {PROFILE_THEMES[theme_id]['name']}",
                callback_data=f"equip_theme_{theme_id}"
            )
        ])

    keyboard.append([InlineKeyboardButton("« Back", callback_data="profile_shop")])

    await callback_query.message.edit_text(
        themes_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@shivuu.on_callback_query(filters.regex("^buy_theme_(.+)$"))
async def buy_theme_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    theme_id = callback_query.data.split("_", 2)[2]

    if theme_id not in PROFILE_THEMES:
        await callback_query.answer("Invalid theme!", show_alert=True)
        return

    theme_data = PROFILE_THEMES[theme_id]
    price = theme_data['price']

    user = await user_collection.find_one({'id': user_id})
    balance = user.get('balance', 0)
    profile_data = user.get('profile_data', {})
    owned_themes = profile_data.get('owned_themes', [])

    if theme_id in owned_themes:
        await callback_query.answer("You already own this theme!", show_alert=True)
        return

    if balance < price:
        await callback_query.answer(
            f"Insufficient balance! Need ₩{price:,}",
            show_alert=True
        )
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

    await callback_query.answer(
        f"✅ Purchased {theme_data['name']} for ₩{price:,}!",
        show_alert=True
    )
    await shop_themes_callback(client, callback_query)


@shivuu.on_callback_query(filters.regex("^equip_theme_(.+)$"))
async def equip_theme_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    theme_id = callback_query.data.split("_", 2)[2]

    if theme_id not in PROFILE_THEMES:
        await callback_query.answer("Invalid theme!", show_alert=True)
        return

    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    owned_themes = profile_data.get('owned_themes', [])

    if theme_id not in owned_themes:
        await callback_query.answer("You don't own this theme!", show_alert=True)
        return

    await user_collection.update_one(
        {'id': user_id},
        {'$set': {'profile_data.theme': theme_id}}
    )

    await callback_query.answer(
        f"✅ Equipped {PROFILE_THEMES[theme_id]['name']}!",
        show_alert=True
    )
    await shop_themes_callback(client, callback_query)


@shivuu.on_callback_query(filters.regex("^shop_frames$"))
async def shop_frames_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    await initialize_profile_data(user_id)
    
    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    owned_frames = profile_data.get('owned_frames', ['none'])
    balance = await get_user_balance(user_id)

    frames_text = "🖼️ **FRAME SHOP** 🖼️\n\n"

    for frame_id, frame_data in AVATAR_FRAMES.items():
        frame_name = frame_data['name']
        price = frame_data['price']

        if frame_id in owned_frames:
            status = "✅ Owned"
        elif balance >= price:
            status = f"💰 ₩{price:,}"
        else:
            status = f"🔒 ₩{price:,}"

        preview = f"{frame_data['left']}Username{frame_data['right']}" if frame_id != "none" else "Username"
        frames_text += f"{frame_name}\n{preview}\n{status}\n\n"

    frames_text += f"\n💵 Your Balance: ₩{balance:,}"

    keyboard = []
    for frame_id, frame_data in AVATAR_FRAMES.items():
        if frame_id not in owned_frames and frame_data['price'] > 0:
            if balance >= frame_data['price']:
                keyboard.append([
                    InlineKeyboardButton(
                        f"Buy {frame_data['name']}",
                        callback_data=f"buy_frame_{frame_id}"
                    )
                ])

    for frame_id in owned_frames:
        keyboard.append([
            InlineKeyboardButton(
                f"Equip {AVATAR_FRAMES[frame_id]['name']}",
                callback_data=f"equip_frame_{frame_id}"
            )
        ])

    keyboard.append([InlineKeyboardButton("« Back", callback_data="profile_shop")])

    await callback_query.message.edit_text(
        frames_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@shivuu.on_callback_query(filters.regex("^buy_frame_(.+)$"))
async def buy_frame_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    frame_id = callback_query.data.split("_", 2)[2]

    if frame_id not in AVATAR_FRAMES:
        await callback_query.answer("Invalid frame!", show_alert=True)
        return

    frame_data = AVATAR_FRAMES[frame_id]
    price = frame_data['price']

    user = await user_collection.find_one({'id': user_id})
    balance = user.get('balance', 0)
    profile_data = user.get('profile_data', {})
    owned_frames = profile_data.get('owned_frames', [])

    if frame_id in owned_frames:
        await callback_query.answer("You already own this frame!", show_alert=True)
        return

    if balance < price:
        await callback_query.answer(
            f"Insufficient balance! Need ₩{price:,}",
            show_alert=True
        )
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

    await callback_query.answer(
        f"✅ Purchased {frame_data['name']} for ₩{price:,}!",
        show_alert=True
    )
    await shop_frames_callback(client, callback_query)


@shivuu.on_callback_query(filters.regex("^equip_frame_(.+)$"))
async def equip_frame_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    frame_id = callback_query.data.split("_", 2)[2]

    if frame_id not in AVATAR_FRAMES:
        await callback_query.answer("Invalid frame!", show_alert=True)
        return

    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    owned_frames = profile_data.get('owned_frames', [])

    if frame_id not in owned_frames:
        await callback_query.answer("You don't own this frame!", show_alert=True)
        return

    await user_collection.update_one(
        {'id': user_id},
        {'$set': {'profile_data.frame': frame_id}}
    )

    await callback_query.answer(
        f"✅ Equipped {AVATAR_FRAMES[frame_id]['name']}!",
        show_alert=True
    )
    await shop_frames_callback(client, callback_query)


@shivuu.on_callback_query(filters.regex("^shop_emojis$"))
async def shop_emojis_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    await initialize_profile_data(user_id)
    
    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    owned_packs = profile_data.get('owned_emoji_packs', ['basic'])
    balance = await get_user_balance(user_id)

    emojis_text = "😀 **EMOJI PACK SHOP** 😀\n\n"

    for pack_id, pack_data in EMOJI_PACKS.items():
        pack_name = pack_data['name']
        price = pack_data['price']
        emojis = ' '.join(pack_data['emojis'])

        if pack_id in owned_packs:
            status = "✅ Owned"
        elif balance >= price:
            status = f"💰 ₩{price:,}"
        else:
            status = f"🔒 ₩{price:,}"

        emojis_text += f"{pack_name}\n{emojis}\n{status}\n\n"

    emojis_text += f"\n💵 Your Balance: ₩{balance:,}"

    keyboard = []
    for pack_id, pack_data in EMOJI_PACKS.items():
        if pack_id not in owned_packs and pack_data['price'] > 0:
            if balance >= pack_data['price']:
                keyboard.append([
                    InlineKeyboardButton(
                        f"Buy {pack_data['name']}",
                        callback_data=f"buy_emoji_{pack_id}"
                    )
                ])

    keyboard.append([InlineKeyboardButton("« Back", callback_data="profile_shop")])

    await callback_query.message.edit_text(
        emojis_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@shivuu.on_callback_query(filters.regex("^buy_emoji_(.+)$"))
async def buy_emoji_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    pack_id = callback_query.data.split("_", 2)[2]

    if pack_id not in EMOJI_PACKS:
        await callback_query.answer("Invalid emoji pack!", show_alert=True)
        return

    pack_data = EMOJI_PACKS[pack_id]
    price = pack_data['price']

    user = await user_collection.find_one({'id': user_id})
    balance = user.get('balance', 0)
    profile_data = user.get('profile_data', {})
    owned_packs = profile_data.get('owned_emoji_packs', [])

    if pack_id in owned_packs:
        await callback_query.answer("You already own this pack!", show_alert=True)
        return

    if balance < price:
        await callback_query.answer(
            f"Insufficient balance! Need ₩{price:,}",
            show_alert=True
        )
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

    await callback_query.answer(
        f"✅ Purchased {pack_data['name']} for ₩{price:,}!",
        show_alert=True
    )
    await shop_emojis_callback(client, callback_query)


@shivuu.on_callback_query(filters.regex("^shop_bio$"))
async def shop_bio_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    await initialize_profile_data(user_id)
    
    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    current_bio = profile_data.get('bio', 'Not set')
    last_update = profile_data.get('bio_last_update')

    cooldown_remaining = ""
    if last_update:
        time_diff = datetime.now() - datetime.fromisoformat(last_update)
        cooldown_minutes = BIO_COOLDOWN_MINUTES - (time_diff.total_seconds() / 60)
        if cooldown_minutes > 0:
            cooldown_remaining = f"\n⏰ Cooldown: {int(cooldown_minutes)} minutes"

    bio_text = f"""
📝 **BIO EDITOR** 📝

Current Bio: {current_bio}

**Rules:**
• Max {BIO_MAX_LENGTH} characters
• Max {BIO_EMOJI_LIMIT} emojis
• No offensive language
• {BIO_COOLDOWN_MINUTES} minute cooldown between edits{cooldown_remaining}

Use command: `/setbio <your bio text>`
"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("« Back", callback_data="profile_shop")]
    ])

    await callback_query.message.edit_text(bio_text, reply_markup=keyboard)


@shivuu.on_message(filters.command("setbio"))
async def set_bio_command(client: Client, message: Message) -> None:
    user_id = message.from_user.id
    await initialize_profile_data(user_id)

    if len(message.command) < 2:
        await message.reply_text(
            "❌ Please provide bio text!\n\nUsage: `/setbio <your bio>`"
        )
        return

    bio_text = message.text.split(None, 1)[1]

    if len(bio_text) > BIO_MAX_LENGTH:
        await message.reply_text(
            f"❌ Bio too long! Max {BIO_MAX_LENGTH} characters."
        )
        return

    if contains_bad_words(bio_text):
        await message.reply_text("❌ Bio contains inappropriate language!")
        return

    emoji_count = count_emojis(bio_text)
    if emoji_count > BIO_EMOJI_LIMIT:
        await message.reply_text(
            f"❌ Too many emojis! Max {BIO_EMOJI_LIMIT} emojis allowed."
        )
        return

    user = await user_collection.find_one({'id': user_id})
    profile_data = user.get('profile_data', {})
    last_update = profile_data.get('bio_last_update')

    if last_update:
        time_diff = datetime.now() - datetime.fromisoformat(last_update)
        cooldown_minutes = BIO_COOLDOWN_MINUTES - (time_diff.total_seconds() / 60)
        if cooldown_minutes > 0:
            await message.reply_text(
                f"⏰ Bio on cooldown! Wait {int(cooldown_minutes)} more minutes."
            )
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

    await message.reply_text(f"✅ Bio updated successfully!\n\n💭 {bio_text}")


@shivuu.on_callback_query(filters.regex("^back_to_profile$"))
async def back_to_profile_callback(client: Client, callback_query: CallbackQuery) -> None:
    user_id = callback_query.from_user.id
    
    try:
        info_text, photo_id = await get_user_info(user_id)
    except Exception as e:
        await callback_query.answer("Error loading profile", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍️ Profile Shop", callback_data="profile_shop")],
        [InlineKeyboardButton("Support", url=f"https://t.me/{SUPPORT_CHAT}")]
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
