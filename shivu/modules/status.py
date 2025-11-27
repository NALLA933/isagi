from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions
from shivu import shivuu, SUPPORT_CHAT, user_collection, collection
import os

async def get_user_collection():
    return await user_collection.find({}).to_list(length=None)

async def get_global_rank(user_id: int) -> int:
    pipeline = [
        {"$project": {
            "id": 1,
            "characters_count": {"$cond": {"if": {"$isArray": "$characters"}, "then": {"$size": "$characters"}, "else": 0}}
        }},
        {"$sort": {"characters_count": -1}}
    ]
    cursor = user_collection.aggregate(pipeline)
    leaderboard_data = await cursor.to_list(length=None)
    for i, user in enumerate(leaderboard_data, start=1):
        if user.get('id') == user_id:
            return i
    return 0

async def get_user_balance(user_id: int) -> int:
    user_balance = await user_collection.find_one({'id': user_id}, projection={'balance': 1})
    return user_balance.get('balance', 0) if user_balance else 0

async def get_user_info(user, already=False):
    if not already:
        user = await shivuu.get_users(user)
    if not user.first_name:
        return ["Deleted account", None, None]

    user_id = user.id
    username = user.username
    existing_user = await user_collection.find_one({'id': user_id})
    first_name = user.first_name
    global_rank = await get_global_rank(user_id)
    global_count = await collection.count_documents({})
    total_count = len(existing_user.get('characters', [])) if existing_user else 0
    balance = await get_user_balance(user_id)
    global_coin_rank = await user_collection.count_documents({'balance': {'$gt': balance}}) + 1
    has_pass = "✅" if existing_user and existing_user.get('pass') else "❌"
    tokens = existing_user.get('tokens', 0) if existing_user else 0
    
    profile_media = existing_user.get('profile_media') if existing_user else None
    custom_info = existing_user.get('custom_info', '') if existing_user else ''

    info_text = f"""
<blockquote>
<b>✨ 𝙃𝙐𝙉𝙏𝙀𝙍 𝙇𝙄𝘾𝙀𝙉𝙎𝙀 ✨</b>

<b>𝙉𝘼𝙈𝙀:</b> <code>{first_name}</code>
<b>𝙄𝘿:</b> <code>{user_id}</code>
<b>𝙐𝙎𝙀𝙍𝙉𝘼𝙈𝙀:</b> @{username if username else 'None'}

<b>𝙎𝙇𝘼𝙑𝙀𝙎 𝘾𝙊𝙐𝙉𝙏:</b> <code>{total_count}/{global_count}</code>
<b>𝙂𝙇𝙊𝘽𝘼𝙇 𝙍𝘼𝙉𝙆:</b> <code>#{global_rank}</code>

<b>𝙒𝙀𝘼𝙇𝙏𝙃:</b> ₩<code>{balance:,}</code>
<b>𝙒𝙀𝘼𝙇𝙏𝙃 𝙍𝘼𝙉𝙆:</b> <code>#{global_coin_rank}</code>

<b>𝙋𝘼𝙎𝙎:</b> {has_pass}
<b>𝙏𝙊𝙆𝙀𝙉𝙎:</b> <code>{tokens:,}</code>

{custom_info}
</blockquote>
"""
    return info_text, profile_media

@shivuu.on_message(filters.command("sinfo"))
async def profile(client, message):
    if message.reply_to_message:
        user = message.reply_to_message.from_user.id
    elif not message.reply_to_message and len(message.command) == 1:
        user = message.from_user.id
    else:
        try:
            user_input = message.text.split(None, 1)[1]
            if user_input.isdigit():
                user = int(user_input)
            else:
                user = user_input.lstrip('@')
        except:
            user = message.from_user.id

    m = await message.reply_text("📇 Getting Hunter License...")
    
    try:
        info_text, profile_media = await get_user_info(user)
    except Exception as e:
        return await m.edit(f"❌ Error: {e}")

    keyboard = [[InlineKeyboardButton("Support", url=f"https://t.me/{SUPPORT_CHAT}")]]
    
    if not profile_media:
        existing_user = await user_collection.find_one({'id': user if isinstance(user, int) else None})
        if not existing_user:
            keyboard = [[InlineKeyboardButton("Start Me in PM", url=f"https://t.me/{shivuu.me.username}?start=True")]]
        return await m.edit(info_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    if profile_media.get('type') in ['video', 'gif']:
        video_url = profile_media.get('file_id')
        await m.delete()
        await message.reply_text(
            text=info_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML',
            link_preview_options=LinkPreviewOptions(
                url=video_url,
                show_above_text=True,
                prefer_large_media=True
            )
        )
    elif profile_media.get('type') == 'photo':
        await m.delete()
        await message.reply_photo(
            photo=profile_media.get('file_id'),
            caption=info_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )