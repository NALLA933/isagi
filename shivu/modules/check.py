import urllib.request
from html import escape
from cachetools import TTLCache
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from pyrogram import filters
from pyrogram import types as t

from shivu import application, sudo_users, db, CHARA_CHANNEL_ID
from shivu import shivuu as bot

collection = db['anime_characters_lol']
user_collection = db['user_collection_lmaoooo']
character_cache = TTLCache(maxsize=1000, ttl=300)
anime_cache = TTLCache(maxsize=500, ttl=600)

def get_rarity_color(rarity):
    rarity_str = str(rarity).lower()
    if '🟢' in rarity_str or 'common' in rarity_str: return '🟢'
    elif '🟣' in rarity_str or 'rare' in rarity_str: return '🟣'
    elif '🟡' in rarity_str or 'legendary' in rarity_str: return '🟡'
    elif '💮' in rarity_str or 'special edition' in rarity_str: return '💮'
    elif '💫' in rarity_str or 'neon' in rarity_str: return '💫'
    elif '✨' in rarity_str or 'manga' in rarity_str: return '✨'
    elif '🎭' in rarity_str or 'cosplay' in rarity_str: return '🎭'
    elif '🎐' in rarity_str or 'celestial' in rarity_str: return '🎐'
    elif '🔮' in rarity_str or 'premium edition' in rarity_str: return '🔮'
    elif '💋' in rarity_str or 'erotic' in rarity_str: return '💋'
    elif '🌤' in rarity_str or 'summer' in rarity_str: return '🌤'
    elif '☃️' in rarity_str or 'winter' in rarity_str: return '☃️'
    elif '☔' in rarity_str or 'monsoon' in rarity_str: return '☔️'
    elif '💝' in rarity_str or 'valentine' in rarity_str: return '💝'
    elif '🎃' in rarity_str or 'halloween' in rarity_str: return '🎃'
    elif '🎄' in rarity_str or 'christmas' in rarity_str: return '🎄'
    elif '🏵' in rarity_str or 'mythic' in rarity_str: return '🏵'
    elif '🎗' in rarity_str or 'special events' in rarity_str: return '🎗'
    elif '🎥' in rarity_str or 'amv' in rarity_str: return '🎥'
    return '⚪'

async def get_character_by_id(character_id):
    if character_id in character_cache:
        return character_cache[character_id]
    try:
        character = await collection.find_one({'id': character_id})
        if character:
            character_cache[character_id] = character
        return character
    except Exception as e:
        print(f"Error getting character: {e}")
        return None

async def get_global_count(character_id):
    try:
        return await user_collection.count_documents({'characters.id': character_id})
    except:
        return 0

async def get_users_by_character(character_id):
    try:
        cursor = user_collection.find({'characters.id': character_id}, {'_id': 0, 'id': 1, 'first_name': 1, 'username': 1, 'characters': 1})
        users = await cursor.to_list(length=None)
        user_data = []
        for user in users:
            count = sum(1 for c in user.get('characters', []) if c.get('id') == character_id)
            if count > 0:
                user_data.append({'id': user.get('id'), 'first_name': user.get('first_name', 'Unknown'), 'username': user.get('username'), 'count': count})
        return user_data
    except:
        return []

def format_character_card(character, global_count=None, show_owners=False, owners_list=None):
    char_id = character.get('id', 'Unknown')
    char_name = character.get('name', 'Unknown')
    char_anime = character.get('anime', 'Unknown')
    char_rarity = character.get('rarity', '🟢 Common')
    
    if isinstance(char_rarity, str):
        rarity_parts = char_rarity.split(' ', 1)
        rarity_emoji = rarity_parts[0] if len(rarity_parts) > 0 else '🟢'
        rarity_text = rarity_parts[1] if len(rarity_parts) > 1 else 'Common'
    else:
        rarity_emoji = '🟢'
        rarity_text = 'Common'
    
    if show_owners and owners_list:
        caption = f"""<b>╭━━━━━━━━━━━━━━━━━╮</b>
<b>┃  🎴 ᴄʜᴀʀᴀᴄᴛᴇʀ ᴏᴡɴᴇʀs  ┃</b>
<b>╰━━━━━━━━━━━━━━━━━╯</b>

<b>🆔 ɪᴅ</b> : <code>{char_id}</code>
<b>🧬 ɴᴀᴍᴇ</b> : <code>{escape(char_name)}</code>
<b>📺 ᴀɴɪᴍᴇ</b> : <code>{escape(char_anime)}</code>
<b>{rarity_emoji} ʀᴀʀɪᴛʏ</b> : <code>{rarity_text.lower()}</code>

<b>━━━━━━━━━━━━━━━━━</b>
"""
        for i, user in enumerate(owners_list[:10], 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            user_link = f"<a href='tg://user?id={user['id']}'>{escape(user['first_name'])}</a>"
            if user.get('username'):
                user_link += f" (@{escape(user['username'])})"
            caption += f"\n{medal} {user_link} <code>x{user['count']}</code>"
        
        if global_count:
            caption += f"\n\n<b>🔮 ᴛᴏᴛᴀʟ ɢʀᴀʙʙᴇᴅ</b> <code>{global_count}x</code>"
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

async def check_character(update: Update, context: CallbackContext) -> None:
    try:
        args = context.args
        if len(args) != 1:
            await update.message.reply_text(
                f"<b>ɪɴᴄᴏʀʀᴇᴄᴛ ғᴏʀᴍᴀᴛ</b>\n\nᴜsᴀɢᴇ: <code>/check character_id</code>\nᴇxᴀᴍᴘʟᴇ: <code>/check 01</code>",
                parse_mode='HTML'
            )
            return

        character_id = args[0]
        character = await get_character_by_id(character_id)

        if not character:
            await update.message.reply_text(
                f"<b>❌ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ</b>\n\nɪᴅ <code>{character_id}</code> ᴅᴏᴇs ɴᴏᴛ ᴇxɪsᴛ",
                parse_mode='HTML'
            )
            return

        global_count = await get_global_count(character_id)
        caption = format_character_card(character, global_count)

        keyboard = [
            [
                InlineKeyboardButton(f"🏆 sʜᴏᴡ ᴏᴡɴᴇʀs", callback_data=f"show_owners_{character_id}"),
                InlineKeyboardButton(f"📊 sᴛᴀᴛs", callback_data=f"char_stats_{character_id}")
            ],
            [InlineKeyboardButton(f"🔗 sʜᴀʀᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ", url=f"https://t.me/share/url?url=Check out this character: /check {character_id}")]
        ]

        is_video = character.get('is_video', False)
        media_url = character.get('img_url')

        if is_video:
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=media_url,
                caption=caption,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard),
                read_timeout=120,
                write_timeout=120
            )
        else:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=media_url,
                caption=caption,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    except Exception as e:
        print(f"Error in check_character: {e}")
        await update.message.reply_text(f"<b>❌ ᴇʀʀᴏʀ</b>\n{escape(str(e))}", parse_mode='HTML')

async def find_character(update: Update, context: CallbackContext) -> None:
    try:
        if not context.args:
            await update.message.reply_text(
                f"<b>ᴜsᴀɢᴇ</b> <code>/find name</code>\nᴇxᴀᴍᴘʟᴇ: <code>/find naruto</code>",
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
        
        name_counts = {}
        char_data = {}
        for char in characters:
            name = char.get('name', 'Unknown')
            if name not in name_counts:
                name_counts[name] = 0
                char_data[name] = char
            name_counts[name] += 1
        
        total_chars = len(characters)
        unique_names = len(name_counts)
        
        response = f"""<b>╭━━━━━━━━━━━━━━━━━╮</b>
<b>┃  🔍 sᴇᴀʀᴄʜ ʀᴇsᴜʟᴛs  ┃</b>
<b>╰━━━━━━━━━━━━━━━━━╯</b>

<b>🔎 ǫᴜᴇʀʏ</b> <code>{escape(char_name)}</code>
<b>📊 ᴛᴏᴛᴀʟ ғᴏᴜɴᴅ</b> <code>{total_chars}</code>
<b>👤 ᴜɴɪǫᴜᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs</b> <code>{unique_names}</code>

<b>━━━━━━━━━━━━━━━━━</b>

"""
        
        for i, (name, count) in enumerate(sorted(name_counts.items()), 1):
            char = char_data[name]
            char_id = char.get('id', '??')
            char_anime = char.get('anime', 'Unknown')
            char_rarity = char.get('rarity', '🟢 Common')
            
            if isinstance(char_rarity, str):
                rarity_parts = char_rarity.split(' ', 1)
                rarity_emoji = rarity_parts[0] if len(rarity_parts) > 0 else '🟢'
                rarity_text = rarity_parts[1] if len(rarity_parts) > 1 else 'Common'
            else:
                rarity_emoji = '🟢'
                rarity_text = 'Common'
            
            global_count = await get_global_count(char_id)
            
            response += f"<b>{i}. {escape(name)}</b>"
            if count > 1:
                response += f" <code>x{count}</code>"
            response += f"\n   🆔 <code>{char_id}</code>\n   📺 <i>{escape(char_anime)}</i>\n   {rarity_emoji} {rarity_text.lower()}\n   🌍 <code>{global_count}x</code> ɢʀᴀʙʙᴇᴅ\n\n"
        
        response += f"<b>━━━━━━━━━━━━━━━━━</b>\n<i>ᴜsᴇ /check [id] ғᴏʀ ᴍᴏʀᴇ ᴅᴇᴛᴀɪʟs</i>"
        
        await update.message.reply_text(response, parse_mode='HTML')
        
    except Exception as e:
        print(f"Error in find_character: {e}")
        await update.message.reply_text(f"<b>❌ ᴇʀʀᴏʀ</b> {escape(str(e))}", parse_mode='HTML')

@bot.on_message(filters.command(["anime"]))
async def find_anime(_, message: t.Message):
    try:
        if len(message.command) < 2:
            return await message.reply_text(
                f"<b>ᴜsᴀɢᴇ</b> <code>/anime anime_name</code>\nᴇxᴀᴍᴘʟᴇ: <code>/anime naruto</code>",
                quote=True
            )

        anime_name = " ".join(message.command[1:])
        
        cache_key = f"anime_{anime_name.lower()}"
        if cache_key in anime_cache:
            characters = anime_cache[cache_key]
        else:
            characters = await collection.find({'anime': {'$regex': anime_name, '$options': 'i'}}).to_list(length=None)
            anime_cache[cache_key] = characters

        if not characters:
            return await message.reply_text(
                f"<b>❌ ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ғᴏᴜɴᴅ ғʀᴏᴍ ᴀɴɪᴍᴇ</b> <code>{escape(anime_name)}</code>",
                quote=True
            )

        name_counts = {}
        char_data = {}
        rarity_counts = {}
        
        for char in characters:
            name = char.get('name', 'Unknown')
            if name not in name_counts:
                name_counts[name] = 0
                char_data[name] = char
            name_counts[name] += 1
            
            rarity = char.get('rarity', '🟢 Common')
            if isinstance(rarity, str):
                rarity_emoji = rarity.split(' ')[0] if ' ' in rarity else rarity
                rarity_counts[rarity_emoji] = rarity_counts.get(rarity_emoji, 0) + 1

        total_chars = len(characters)
        unique_names = len(name_counts)
        
        response = f"""<b>╭━━━━━━━━━━━━━━━━━╮</b>
<b>┃  📺 ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs  ┃</b>
<b>╰━━━━━━━━━━━━━━━━━╯</b>

<b>🎬 ᴀɴɪᴍᴇ</b> <code>{escape(anime_name)}</code>
<b>📊 ᴛᴏᴛᴀʟ ғᴏᴜɴᴅ</b> <code>{total_chars}</code>
<b>👤 ᴜɴɪǫᴜᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs</b> <code>{unique_names}</code>

"""
        
        if rarity_counts:
            response += f"<b>🎨 ʀᴀʀɪᴛʏ ʙʀᴇᴀᴋᴅᴏᴡɴ</b>\n"
            for rarity_emoji, count in sorted(rarity_counts.items(), key=lambda x: x[1], reverse=True):
                response += f"   {rarity_emoji} <code>{count}x</code>\n"
            response += "\n"
        
        response += f"<b>━━━━━━━━━━━━━━━━━</b>\n\n"

        for i, (name, count) in enumerate(sorted(name_counts.items()), 1):
            char = char_data[name]
            char_id = char.get('id', '??')
            char_rarity = char.get('rarity', '🟢 Common')
            
            if isinstance(char_rarity, str):
                rarity_parts = char_rarity.split(' ', 1)
                rarity_emoji = rarity_parts[0] if len(rarity_parts) > 0 else '🟢'
                rarity_text = rarity_parts[1] if len(rarity_parts) > 1 else 'Common'
            else:
                rarity_emoji = '🟢'
                rarity_text = 'Common'
            
            global_count = await get_global_count(char_id)
            
            response += f"<b>{i}. {escape(name)}</b>"
            if count > 1:
                response += f" <code>x{count}</code>"
            response += f"\n   🆔 <code>{char_id}</code>\n   {rarity_emoji} {rarity_text.lower()}\n   🌍 <code>{global_count}x</code> ɢʀᴀʙʙᴇᴅ\n\n"

        response += f"<b>━━━━━━━━━━━━━━━━━</b>\n<i>ᴜsᴇ /check [id] ғᴏʀ ᴍᴏʀᴇ ᴅᴇᴛᴀɪʟs</i>"

        await message.reply_text(response, quote=True)
        
    except Exception as e:
        print(f"Error in find_anime: {e}")
        await message.reply_text(f"<b>❌ ᴇʀʀᴏʀ</b> {escape(str(e))}", quote=True)

@bot.on_message(filters.command(["pfind"]))
async def find_users_with_character(_, message: t.Message):
    try:
        if len(message.command) < 2:
            await message.reply_text(
                f"<b>ᴜsᴀɢᴇ</b> <code>/pfind character_id</code>\nᴇxᴀᴍᴘʟᴇ: <code>/pfind 01</code>",
                quote=True
            )
            return

        character_id = message.command[1]
        character = await get_character_by_id(character_id)
        
        if not character:
            await message.reply_text(f"<b>❌ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ</b> <code>{character_id}</code>", quote=True)
            return

        users = await get_users_by_character(character_id)

        if not users:
            await message.reply_text(f"<b>ɴᴏ ᴜsᴇʀs ғᴏᴜɴᴅ ᴡɪᴛʜ ᴄʜᴀʀᴀᴄᴛᴇʀ</b> <code>{character_id}</code>", quote=True)
            return

        users.sort(key=lambda x: x['count'], reverse=True)
        global_count = await get_global_count(character_id)
        caption = format_character_card(character, global_count, show_owners=True, owners_list=users)

        is_video = character.get('is_video', False)
        media_url = character.get('img_url')

        if is_video:
            await bot.send_video(chat_id=message.chat.id, video=media_url, caption=caption, reply_to_message_id=message.id)
        else:
            await bot.send_photo(chat_id=message.chat.id, photo=media_url, caption=caption, reply_to_message_id=message.id)

    except Exception as e:
        print(f"Error in find_users_with_character: {e}")
        await message.reply_text(f"<b>❌ ᴇʀʀᴏʀ</b> {escape(str(e))}", quote=True)

async def handle_show_owners(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    try:
        character_id = query.data.split('_')[2]
        character = await get_character_by_id(character_id)
        
        if not character:
            await query.answer("ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        users = await get_users_by_character(character_id)
        
        if not users:
            await query.answer("ɴᴏ ᴏɴᴇ ᴏᴡɴs ᴛʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ ʏᴇᴛ", show_alert=True)
            return
        
        users.sort(key=lambda x: x['count'], reverse=True)
        global_count = await get_global_count(character_id)
        caption = format_character_card(character, global_count, show_owners=True, owners_list=users)
        
        keyboard = [
            [
                InlineKeyboardButton(f"⬅️ ʙᴀᴄᴋ", callback_data=f"back_to_card_{character_id}"),
                InlineKeyboardButton(f"📊 sᴛᴀᴛs", callback_data=f"char_stats_{character_id}")
            ]
        ]
        
        await query.edit_message_caption(caption=caption, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        print(f"Error showing owners: {e}")
        await query.answer("ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ ᴏᴡɴᴇʀs", show_alert=True)

async def handle_back_to_card(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    try:
        character_id = query.data.split('_')[3]
        character = await get_character_by_id(character_id)
        
        if not character:
            await query.answer("ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        global_count = await get_global_count(character_id)
        caption = format_character_card(character, global_count)
        
        keyboard = [
            [
                InlineKeyboardButton(f"🏆 sʜᴏᴡ ᴏᴡɴᴇʀs", callback_data=f"show_owners_{character_id}"),
                InlineKeyboardButton(f"📊 sᴛᴀᴛs", callback_data=f"char_stats_{character_id}")
            ],
            [InlineKeyboardButton(f"🔗 sʜᴀʀᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ", url=f"https://t.me/share/url?url=Check out this character: /check {character_id}")]
        ]
        
        await query.edit_message_caption(caption=caption, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        print(f"Error going back: {e}")
        await query.answer("ᴇʀʀᴏʀ", show_alert=True)

async def handle_char_stats(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    try:
        character_id = query.data.split('_')[2]
        character = await get_character_by_id(character_id)
        
        if not character:
            await query.answer("ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        global_count = await get_global_count(character_id)
        users = await get_users_by_character(character_id)
        unique_owners = len(users)
        
        stats = f"📊 sᴛᴀᴛɪsᴛɪᴄs\n\n🌍 ᴛᴏᴛᴀʟ ɢʀᴀʙʙᴇᴅ: {global_count}\n👥 ᴜɴɪǫᴜᴇ ᴏᴡɴᴇʀs: {unique_owners}\n📈 ᴀᴠɢ ᴘᴇʀ ᴜsᴇʀ: {global_count/unique_owners if unique_owners > 0 else 0:.1f}"
        
        await query.answer(stats, show_alert=True)
        
    except Exception as e:
        print(f"Error showing stats: {e}")
        await query.answer("ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ sᴛᴀᴛs", show_alert=True)

application.add_handler(CommandHandler('check', check_character, block=False))
application.add_handler(CommandHandler('find', find_character, block=False))
application.add_handler(CallbackQueryHandler(handle_show_owners, pattern=r'^show_owners_', block=False))
application.add_handler(CallbackQueryHandler(handle_back_to_card, pattern=r'^back_to_card_', block=False))
application.add_handler(CallbackQueryHandler(handle_char_stats, pattern=r'^char_stats_', block=False))