from html import escape
from cachetools import TTLCache
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from pyrogram import filters
from pyrogram import types as t

from shivu import application, db
from shivu import shivuu as bot

collection = db['anime_characters_lol']
user_collection = db['user_collection_lmaoooo']
character_cache = TTLCache(maxsize=1000, ttl=300)
anime_cache = TTLCache(maxsize=500, ttl=600)

USERS_PER_PAGE = 10

def get_rarity_parts(rarity):
    if isinstance(rarity, str):
        parts = rarity.split(' ', 1)
        return parts[0] if parts else '🟢', parts[1] if len(parts) > 1 else 'Common'
    return '🟢', 'Common'

async def get_character_by_id(character_id):
    if character_id in character_cache:
        return character_cache[character_id]
    character = await collection.find_one({'id': character_id})
    if character:
        character_cache[character_id] = character
    return character

async def get_global_count(character_id):
    try:
        return await user_collection.count_documents({'characters.id': character_id})
    except:
        return 0

async def get_users_by_character(character_id):
    try:
        cursor = user_collection.find(
            {'characters.id': character_id},
            {'_id': 0, 'id': 1, 'first_name': 1, 'username': 1, 'characters': 1}
        )
        users = await cursor.to_list(length=None)
        user_data = []
        for user in users:
            count = sum(1 for c in user.get('characters', []) if c.get('id') == character_id)
            if count > 0:
                user_data.append({
                    'id': user.get('id'),
                    'first_name': user.get('first_name', 'Unknown'),
                    'username': user.get('username'),
                    'count': count
                })
        return sorted(user_data, key=lambda x: x['count'], reverse=True)
    except:
        return []

def format_character_card(character, global_count=None, page=0, owners_list=None):
    char_id = character.get('id', 'Unknown')
    char_name = character.get('name', 'Unknown')
    char_anime = character.get('anime', 'Unknown')
    rarity_emoji, rarity_text = get_rarity_parts(character.get('rarity', '🟢 Common'))

    if owners_list:
        start_idx = page * USERS_PER_PAGE
        end_idx = start_idx + USERS_PER_PAGE
        page_users = owners_list[start_idx:end_idx]
        total_pages = (len(owners_list) + USERS_PER_PAGE - 1) // USERS_PER_PAGE

        caption = f"""<b>╭━━━━━━━━━━━━━━━━━╮</b>
<b>┃  🎴 ᴄʜᴀʀᴀᴄᴛᴇʀ ᴏᴡɴᴇʀs  ┃</b>
<b>╰━━━━━━━━━━━━━━━━━╯</b>

<b>🆔 ɪᴅ</b> : <code>{char_id}</code>
<b>🧬 ɴᴀᴍᴇ</b> : <code>{escape(char_name)}</code>
<b>📺 ᴀɴɪᴍᴇ</b> : <code>{escape(char_anime)}</code>
<b>{rarity_emoji} ʀᴀʀɪᴛʏ</b> : <code>{rarity_text.lower()}</code>

<b>━━━━━━━━━━━━━━━━━</b>
"""
        for i, user in enumerate(page_users, start=start_idx + 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            user_link = f"<a href='tg://user?id={user['id']}'>{escape(user['first_name'])}</a>"
            if user.get('username'):
                user_link += f" (@{escape(user['username'])})"
            caption += f"\n{medal} {user_link} <code>x{user['count']}</code>"

        caption += f"\n\n<b>📄 ᴘᴀɢᴇ</b> <code>{page + 1}/{total_pages}</code>"
        caption += f"\n<b>🔮 ᴛᴏᴛᴀʟ ɢʀᴀʙʙᴇᴅ</b> <code>{global_count}x</code>"
    else:
        caption = f"""<b>╭━━━━━━━━━━━━━━━━━╮</b>
<b>┃  🎴 ᴄʜᴀʀᴀᴄᴛᴇʀ ᴄᴀʀᴅ  ┃</b>
<b>╰━━━━━━━━━━━━━━━━━╯</b>

<b>🆔 ɪᴅ</b> : <code>{char_id}</code>
<b>🧬 ɴᴀᴍᴇ</b> : <code>{escape(char_name)}</code>
<b>📺 ᴀɴɪᴍᴇ</b> : <code>{escape(char_anime)}</code>
<b>{rarity_emoji} ʀᴀʀɪᴛʏ</b> : <code>{rarity_text.lower()}</code>"""

        if global_count is not None:
            caption += f"\n\n<b>🌍 ɢʟᴏʙᴀʟʟʏ ɢʀᴀʙʙᴇᴅ</b> <code>{global_count}x</code>"

        caption += f"\n\n<b>━━━━━━━━━━━━━━━━━</b>"
        caption += f"\n<i>ᴀ ᴘʀᴇᴄɪᴏᴜs ᴄʜᴀʀᴀᴄᴛᴇʀ ᴡᴀɪᴛɪɴɢ ᴛᴏ ᴊᴏɪɴ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ</i>"

    return caption

def create_pagination_keyboard(character_id, page, total_pages, show_back=False):
    keyboard = []
    
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ ᴘʀᴇᴠ", callback_data=f"owners_{character_id}_{page-1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("ɴᴇxᴛ ➡️", callback_data=f"owners_{character_id}_{page+1}"))
        if nav_buttons:
            keyboard.append(nav_buttons)
    
    if show_back:
        keyboard.append([InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data=f"back_{character_id}")])
    else:
        keyboard.append([InlineKeyboardButton("🏆 sʜᴏᴡ ᴏᴡɴᴇʀs", callback_data=f"owners_{character_id}_0")])
    
    return InlineKeyboardMarkup(keyboard)

async def send_media(context, chat_id, character, caption, keyboard, reply_to=None):
    media_url = character.get('img_url')
    is_video = character.get('is_video', False)
    
    if is_video:
        await context.bot.send_video(
            chat_id=chat_id,
            video=media_url,
            caption=caption,
            parse_mode='HTML',
            reply_markup=keyboard,
            reply_to_message_id=reply_to,
            read_timeout=120,
            write_timeout=120
        )
    else:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=media_url,
            caption=caption,
            parse_mode='HTML',
            reply_markup=keyboard,
            reply_to_message_id=reply_to
        )

async def check_character(update: Update, context: CallbackContext) -> None:
    try:
        if len(context.args) != 1:
            await update.message.reply_text(
                "<b>ɪɴᴄᴏʀʀᴇᴄᴛ ғᴏʀᴍᴀᴛ</b>\n\nᴜsᴀɢᴇ: <code>/check character_id</code>\nᴇxᴀᴍᴘʟᴇ: <code>/check 01</code>",
                parse_mode='HTML'
            )
            return

        character_id = context.args[0]
        character = await get_character_by_id(character_id)

        if not character:
            await update.message.reply_text(
                f"<b>❌ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ</b>\n\nɪᴅ <code>{character_id}</code> ᴅᴏᴇs ɴᴏᴛ ᴇxɪsᴛ",
                parse_mode='HTML'
            )
            return

        global_count = await get_global_count(character_id)
        caption = format_character_card(character, global_count)
        keyboard = create_pagination_keyboard(character_id, 0, 1)

        await send_media(context, update.effective_chat.id, character, caption, keyboard)

    except Exception as e:
        print(f"Error in check_character: {e}")
        await update.message.reply_text(f"<b>❌ ᴇʀʀᴏʀ</b>\n{escape(str(e))}", parse_mode='HTML')

async def find_character(update: Update, context: CallbackContext) -> None:
    try:
        if not context.args:
            await update.message.reply_text(
                "<b>ᴜsᴀɢᴇ</b> <code>/find name</code>\nᴇxᴀᴍᴘʟᴇ: <code>/find naruto</code>",
                parse_mode='HTML'
            )
            return

        char_name = ' '.join(context.args)
        characters = await collection.find({'name': {'$regex': char_name, '$options': 'i'}}).to_list(length=None)

        if not characters:
            await update.message.reply_text(
                f"<b>❌ ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ғᴏᴜɴᴅ ᴡɪᴛʜ ɴᴀᴍᴇ</b> <code>{escape(char_name)}</code>",
                parse_mode='HTML'
            )
            return

        name_counts, char_data = {}, {}
        for char in characters:
            name = char.get('name', 'Unknown')
            if name not in name_counts:
                name_counts[name] = 0
                char_data[name] = char
            name_counts[name] += 1

        response = f"""<b>╭━━━━━━━━━━━━━━━━━╮</b>
<b>┃  🔍 sᴇᴀʀᴄʜ ʀᴇsᴜʟᴛs  ┃</b>
<b>╰━━━━━━━━━━━━━━━━━╯</b>

<b>🔎 ǫᴜᴇʀʏ</b> <code>{escape(char_name)}</code>
<b>📊 ᴛᴏᴛᴀʟ ғᴏᴜɴᴅ</b> <code>{len(characters)}</code>
<b>👤 ᴜɴɪǫᴜᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs</b> <code>{len(name_counts)}</code>

<b>━━━━━━━━━━━━━━━━━</b>

"""

        for i, (name, count) in enumerate(sorted(name_counts.items()), 1):
            char = char_data[name]
            rarity_emoji, rarity_text = get_rarity_parts(char.get('rarity', '🟢 Common'))
            global_count = await get_global_count(char.get('id', '??'))

            response += f"<b>{i}. {escape(name)}</b>"
            if count > 1:
                response += f" <code>x{count}</code>"
            response += f"\n   🆔 <code>{char.get('id', '??')}</code>\n   📺 <i>{escape(char.get('anime', 'Unknown'))}</i>\n   {rarity_emoji} {rarity_text.lower()}\n   🌍 <code>{global_count}x</code> ɢʀᴀʙʙᴇᴅ\n\n"

        response += "<b>━━━━━━━━━━━━━━━━━</b>\n<i>ᴜsᴇ /check [id] ғᴏʀ ᴍᴏʀᴇ ᴅᴇᴛᴀɪʟs</i>"
        await update.message.reply_text(response, parse_mode='HTML')

    except Exception as e:
        print(f"Error in find_character: {e}")
        await update.message.reply_text(f"<b>❌ ᴇʀʀᴏʀ</b> {escape(str(e))}", parse_mode='HTML')

@bot.on_message(filters.command(["anime"]))
async def find_anime(_, message: t.Message):
    try:
        if len(message.command) < 2:
            return await message.reply_text(
                "<b>ᴜsᴀɢᴇ</b> <code>/anime anime_name</code>\nᴇxᴀᴍᴘʟᴇ: <code>/anime naruto</code>",
                quote=True
            )

        anime_name = " ".join(message.command[1:])
        cache_key = f"anime_{anime_name.lower()}"
        
        characters = anime_cache.get(cache_key) or await collection.find(
            {'anime': {'$regex': anime_name, '$options': 'i'}}
        ).to_list(length=None)
        
        if not characters:
            return await message.reply_text(
                f"<b>❌ ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ғᴏᴜɴᴅ ғʀᴏᴍ ᴀɴɪᴍᴇ</b> <code>{escape(anime_name)}</code>",
                quote=True
            )

        anime_cache[cache_key] = characters
        name_counts, char_data, rarity_counts = {}, {}, {}

        for char in characters:
            name = char.get('name', 'Unknown')
            if name not in name_counts:
                name_counts[name] = 0
                char_data[name] = char
            name_counts[name] += 1

            rarity_emoji, _ = get_rarity_parts(char.get('rarity', '🟢 Common'))
            rarity_counts[rarity_emoji] = rarity_counts.get(rarity_emoji, 0) + 1

        response = f"""<b>╭━━━━━━━━━━━━━━━━━╮</b>
<b>┃  📺 ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs  ┃</b>
<b>╰━━━━━━━━━━━━━━━━━╯</b>

<b>🎬 ᴀɴɪᴍᴇ</b> <code>{escape(anime_name)}</code>
<b>📊 ᴛᴏᴛᴀʟ ғᴏᴜɴᴅ</b> <code>{len(characters)}</code>
<b>👤 ᴜɴɪǫᴜᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs</b> <code>{len(name_counts)}</code>

"""

        if rarity_counts:
            response += "<b>🎨 ʀᴀʀɪᴛʏ ʙʀᴇᴀᴋᴅᴏᴡɴ</b>\n"
            for emoji, count in sorted(rarity_counts.items(), key=lambda x: x[1], reverse=True):
                response += f"   {emoji} <code>{count}x</code>\n"
            response += "\n"

        response += "<b>━━━━━━━━━━━━━━━━━</b>\n\n"

        for i, (name, count) in enumerate(sorted(name_counts.items()), 1):
            char = char_data[name]
            rarity_emoji, rarity_text = get_rarity_parts(char.get('rarity', '🟢 Common'))
            global_count = await get_global_count(char.get('id', '??'))

            response += f"<b>{i}. {escape(name)}</b>"
            if count > 1:
                response += f" <code>x{count}</code>"
            response += f"\n   🆔 <code>{char.get('id', '??')}</code>\n   {rarity_emoji} {rarity_text.lower()}\n   🌍 <code>{global_count}x</code> ɢʀᴀʙʙᴇᴅ\n\n"

        response += "<b>━━━━━━━━━━━━━━━━━</b>\n<i>ᴜsᴇ /check [id] ғᴏʀ ᴍᴏʀᴇ ᴅᴇᴛᴀɪʟs</i>"
        await message.reply_text(response, quote=True)

    except Exception as e:
        print(f"Error in find_anime: {e}")
        await message.reply_text(f"<b>❌ ᴇʀʀᴏʀ</b> {escape(str(e))}", quote=True)

@bot.on_message(filters.command(["pfind"]))
async def find_users_with_character(_, message: t.Message):
    try:
        if len(message.command) < 2:
            return await message.reply_text(
                "<b>ᴜsᴀɢᴇ</b> <code>/pfind character_id</code>\nᴇxᴀᴍᴘʟᴇ: <code>/pfind 01</code>",
                quote=True
            )

        character_id = message.command[1]
        character = await get_character_by_id(character_id)

        if not character:
            return await message.reply_text(
                f"<b>❌ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ</b> <code>{character_id}</code>",
                quote=True
            )

        users = await get_users_by_character(character_id)

        if not users:
            return await message.reply_text(
                f"<b>ɴᴏ ᴜsᴇʀs ғᴏᴜɴᴅ ᴡɪᴛʜ ᴄʜᴀʀᴀᴄᴛᴇʀ</b> <code>{character_id}</code>",
                quote=True
            )

        global_count = await get_global_count(character_id)
        total_pages = (len(users) + USERS_PER_PAGE - 1) // USERS_PER_PAGE
        caption = format_character_card(character, global_count, 0, users)
        keyboard = create_pagination_keyboard(character_id, 0, total_pages, show_back=True)

        media_url = character.get('img_url')
        is_video = character.get('is_video', False)

        if is_video:
            await bot.send_video(
                chat_id=message.chat.id,
                video=media_url,
                caption=caption,
                reply_to_message_id=message.id,
                reply_markup=keyboard
            )
        else:
            await bot.send_photo(
                chat_id=message.chat.id,
                photo=media_url,
                caption=caption,
                reply_to_message_id=message.id,
                reply_markup=keyboard
            )

    except Exception as e:
        print(f"Error in pfind: {e}")
        await message.reply_text(f"<b>❌ ᴇʀʀᴏʀ</b> {escape(str(e))}", quote=True)

async def handle_owners_pagination(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    try:
        data_parts = query.data.split('_')
        character_id = data_parts[1]
        page = int(data_parts[2])

        character = await get_character_by_id(character_id)
        if not character:
            return await query.answer("ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)

        users = await get_users_by_character(character_id)
        if not users:
            return await query.answer("ɴᴏ ᴏɴᴇ ᴏᴡɴs ᴛʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ", show_alert=True)

        global_count = await get_global_count(character_id)
        total_pages = (len(users) + USERS_PER_PAGE - 1) // USERS_PER_PAGE
        caption = format_character_card(character, global_count, page, users)
        keyboard = create_pagination_keyboard(character_id, page, total_pages, show_back=True)

        await query.edit_message_caption(caption=caption, parse_mode='HTML', reply_markup=keyboard)

    except Exception as e:
        print(f"Error in pagination: {e}")
        await query.answer("ᴇʀʀᴏʀ", show_alert=True)

async def handle_back_to_card(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    try:
        character_id = query.data.split('_')[1]
        character = await get_character_by_id(character_id)

        if not character:
            return await query.answer("ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)

        global_count = await get_global_count(character_id)
        caption = format_character_card(character, global_count)
        keyboard = create_pagination_keyboard(character_id, 0, 1)

        await query.edit_message_caption(caption=caption, parse_mode='HTML', reply_markup=keyboard)

    except Exception as e:
        print(f"Error going back: {e}")
        await query.answer("ᴇʀʀᴏʀ", show_alert=True)

application.add_handler(CommandHandler('check', check_character, block=False))
application.add_handler(CommandHandler('find', find_character, block=False))
application.add_handler(CallbackQueryHandler(handle_owners_pagination, pattern=r'^owners_', block=False))
application.add_handler(CallbackQueryHandler(handle_back_to_card, pattern=r'^back_', block=False))