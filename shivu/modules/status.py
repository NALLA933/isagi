from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.helpers import LinkPreviewOptions
from shivu import shivuu, SUPPORT_CHAT, user_collection, collection
import os
import re

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

async def get_global_coin_rank(balance: int) -> int:
    return await user_collection.count_documents({'balance': {'$gt': balance}}) + 1

async def get_user_info(user_identifier, already=False):
    if not already:
        user = await shivuu.get_users(user_identifier)
    else:
        user = user_identifier
    
    if not user.first_name:
        return None, None, None
    
    user_id = user.id
    username = user.username or "Not Set"
    existing_user = await user_collection.find_one({'id': user_id})
    
    if not existing_user:
        return None, None, None
    
    first_name = user.first_name
    global_rank = await get_global_rank(user_id)
    global_count = await collection.count_documents({})
    total_count = len(existing_user.get('characters', []))
    balance = await get_user_balance(user_id)
    global_coin_rank = await get_global_coin_rank(balance)
    tokens = existing_user.get('tokens', 0)
    has_pass = "✅" if existing_user.get('pass') else "❌"
    
    profile_settings = existing_user.get('profile_settings', {})
    show_username = profile_settings.get('show_username', True)
    show_balance = profile_settings.get('show_balance', True)
    show_tokens = profile_settings.get('show_tokens', True)
    show_rank = profile_settings.get('show_rank', True)
    custom_bio = profile_settings.get('bio', '')
    profile_video = existing_user.get('profile_video')
    
    balance_formatted = f"{balance:,}"
    tokens_formatted = f"{tokens:,}"
    
    info_parts = [
        f"<blockquote><b>✨ HUNTER LICENSE ✨</b></blockquote>",
        f"<blockquote expandable>",
        f"<b>👤 Name:</b> <code>{first_name}</code>",
        f"<b>🆔 User ID:</b> <code>{user_id}</code>"
    ]
    
    if show_username:
        info_parts.append(f"<b>📱 Username:</b> @{username}")
    
    info_parts.append(f"\n<b>🎴 Slaves Count:</b> <code>{total_count}</code> / <code>{global_count}</code>")
    
    if show_rank:
        info_parts.append(f"<b>🏆 Global Rank:</b> <code>#{global_rank}</code>")
    
    if show_balance:
        info_parts.append(f"\n<b>💰 Wealth:</b> <code>₩{balance_formatted}</code>")
        info_parts.append(f"<b>💎 Wealth Rank:</b> <code>#{global_coin_rank}</code>")
    
    info_parts.append(f"\n<b>🎫 Pass:</b> {has_pass}")
    
    if show_tokens:
        info_parts.append(f"<b>🪙 Tokens:</b> <code>{tokens_formatted}</code>")
    
    if custom_bio:
        info_parts.append(f"\n<b>📝 Bio:</b>\n<i>{custom_bio}</i>")
    
    info_parts.append("</blockquote>")
    
    info_text = "\n".join(info_parts)
    
    media_url = profile_video if profile_video else (f"https://t.me/{user.username}" if user.username else None)
    
    return info_text, media_url, user

@shivuu.on_message(filters.command("sinfo"))
async def profile_command(client, message):
    user_identifier = None
    
    if message.reply_to_message:
        user_identifier = message.reply_to_message.from_user.id
    elif len(message.command) == 1:
        user_identifier = message.from_user.id
    elif len(message.command) >= 2:
        arg = message.command[1]
        if arg.isdigit():
            user_identifier = int(arg)
        elif arg.startswith('@'):
            user_identifier = arg[1:]
        else:
            user_identifier = arg
    
    m = await message.reply_text("⏳ <i>Getting Hunter License...</i>", parse_mode='HTML')
    
    try:
        info_text, media_url, user_obj = await get_user_info(user_identifier)
        
        if not info_text:
            return await m.edit(
                "❌ <b>User not found or hasn't started the bot yet!</b>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Start Bot", url=f"https://t.me/{shivuu.me.username}?start=True")]
                ])
            )
        
        keyboard = [
            [InlineKeyboardButton("🔧 Customize Profile", callback_data=f"customize_profile:{user_obj.id}")],
            [InlineKeyboardButton("💬 Support", url=f"https://t.me/{SUPPORT_CHAT}")]
        ]
        
        await m.delete()
        
        if media_url:
            await message.reply_text(
                text=info_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML',
                link_preview_options=LinkPreviewOptions(
                    url=media_url,
                    show_above_text=True,
                    prefer_large_media=True
                )
            )
        else:
            await message.reply_text(
                text=info_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML',
                disable_web_page_preview=True
            )
    
    except Exception as e:
        await m.edit(f"❌ <b>Error:</b> <code>{str(e)}</code>\n\n<i>Report at</i> @{SUPPORT_CHAT}", parse_mode='HTML')

@shivuu.on_message(filters.command("setprofilevideo"))
async def set_profile_video(client, message):
    user_id = message.from_user.id
    
    if len(message.command) < 2:
        return await message.reply_text(
            "📹 <b>Set Profile Video/GIF</b>\n\n"
            "<b>Usage:</b> <code>/setprofilevideo [URL]</code>\n\n"
            "<i>Supported: Direct video/GIF links, Telegram file links</i>",
            parse_mode='HTML'
        )
    
    video_url = message.text.split(None, 1)[1]
    
    await user_collection.update_one(
        {'id': user_id},
        {'$set': {'profile_video': video_url}},
        upsert=True
    )
    
    await message.reply_text(
        "✅ <b>Profile video set successfully!</b>\n\n"
        f"🔗 <b>URL:</b> <code>{video_url}</code>",
        parse_mode='HTML'
    )

@shivuu.on_message(filters.command("setbio"))
async def set_bio(client, message):
    user_id = message.from_user.id
    
    if len(message.command) < 2:
        return await message.reply_text(
            "📝 <b>Set Profile Bio</b>\n\n"
            "<b>Usage:</b> <code>/setbio [Your bio text]</code>\n\n"
            "<i>Maximum 200 characters</i>",
            parse_mode='HTML'
        )
    
    bio = message.text.split(None, 1)[1][:200]
    
    await user_collection.update_one(
        {'id': user_id},
        {'$set': {'profile_settings.bio': bio}},
        upsert=True
    )
    
    await message.reply_text(
        f"✅ <b>Bio updated successfully!</b>\n\n<i>{bio}</i>",
        parse_mode='HTML'
    )

@shivuu.on_message(filters.command("profilesettings"))
async def profile_settings(client, message):
    user_id = message.from_user.id
    user_data = await user_collection.find_one({'id': user_id})
    
    if not user_data:
        return await message.reply_text("❌ <b>Start the bot first!</b>", parse_mode='HTML')
    
    settings = user_data.get('profile_settings', {})
    
    keyboard = [
        [InlineKeyboardButton(
            f"{'✅' if settings.get('show_username', True) else '❌'} Username",
            callback_data="toggle_username"
        )],
        [InlineKeyboardButton(
            f"{'✅' if settings.get('show_balance', True) else '❌'} Balance",
            callback_data="toggle_balance"
        )],
        [InlineKeyboardButton(
            f"{'✅' if settings.get('show_tokens', True) else '❌'} Tokens",
            callback_data="toggle_tokens"
        )],
        [InlineKeyboardButton(
            f"{'✅' if settings.get('show_rank', True) else '❌'} Rank",
            callback_data="toggle_rank"
        )],
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_settings")]
    ]
    
    await message.reply_text(
        "<b>⚙️ Profile Display Settings</b>\n\n"
        "<i>Toggle what you want to show in your profile:</i>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

@shivuu.on_callback_query(filters.regex(r"^toggle_"))
async def toggle_setting(client, callback_query):
    user_id = callback_query.from_user.id
    setting = callback_query.data.replace("toggle_", "show_")
    
    user_data = await user_collection.find_one({'id': user_id})
    current_value = user_data.get('profile_settings', {}).get(setting, True)
    
    await user_collection.update_one(
        {'id': user_id},
        {'$set': {f'profile_settings.{setting}': not current_value}},
        upsert=True
    )
    
    await callback_query.answer(f"{'Disabled' if current_value else 'Enabled'} {setting.replace('show_', '').title()}")
    
    user_data = await user_collection.find_one({'id': user_id})
    settings = user_data.get('profile_settings', {})
    
    keyboard = [
        [InlineKeyboardButton(
            f"{'✅' if settings.get('show_username', True) else '❌'} Username",
            callback_data="toggle_username"
        )],
        [InlineKeyboardButton(
            f"{'✅' if settings.get('show_balance', True) else '❌'} Balance",
            callback_data="toggle_balance"
        )],
        [InlineKeyboardButton(
            f"{'✅' if settings.get('show_tokens', True) else '❌'} Tokens",
            callback_data="toggle_tokens"
        )],
        [InlineKeyboardButton(
            f"{'✅' if settings.get('show_rank', True) else '❌'} Rank",
            callback_data="toggle_rank"
        )],
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_settings")]
    ]
    
    await callback_query.message.edit_reply_markup(InlineKeyboardMarkup(keyboard))

@shivuu.on_callback_query(filters.regex("refresh_settings"))
async def refresh_settings(client, callback_query):
    await callback_query.answer("Settings refreshed!")
    await toggle_setting(client, callback_query)