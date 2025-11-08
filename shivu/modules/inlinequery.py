import re
import time
from html import escape
from cachetools import TTLCache
from pymongo import ASCENDING

from telegram import (
    Update, 
    InlineQueryResultPhoto,
    InlineQueryResultVideo,
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
)
from telegram.ext import (
    InlineQueryHandler, 
    CallbackQueryHandler
)

from shivu import application, db, LOGGER

# Database collections
collection = db['anime_characters_lol']
user_collection = db['user_collection_lmaoooo']

# Create indexes
try:
    collection.create_index([('id', ASCENDING)])
    collection.create_index([('anime', ASCENDING)])
    collection.create_index([('name', ASCENDING)])
    collection.create_index([('rarity', ASCENDING)])

    user_collection.create_index([('id', ASCENDING)])
    user_collection.create_index([('characters.id', ASCENDING)])
except Exception as e:
    print(f"Index creation error: {e}")

# Caches
all_characters_cache = TTLCache(maxsize=10000, ttl=36000)
user_collection_cache = TTLCache(maxsize=10000, ttl=60)
character_count_cache = TTLCache(maxsize=10000, ttl=300)


def to_small_caps(text):
    """Convert text to small caps"""
    small_caps_map = {
        'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ғ', 'g': 'ɢ', 'h': 'ʜ', 'i': 'ɪ',
        'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ',
        's': 's', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ',
        'A': 'ᴀ', 'B': 'ʙ', 'C': 'ᴄ', 'D': 'ᴅ', 'E': 'ᴇ', 'F': 'ғ', 'G': 'ɢ', 'H': 'ʜ', 'I': 'ɪ',
        'J': 'ᴊ', 'K': 'ᴋ', 'L': 'ʟ', 'M': 'ᴍ', 'N': 'ɴ', 'O': 'ᴏ', 'P': 'ᴘ', 'Q': 'ǫ', 'R': 'ʀ',
        'S': 's', 'T': 'ᴛ', 'U': 'ᴜ', 'V': 'ᴠ', 'W': 'ᴡ', 'X': 'x', 'Y': 'ʏ', 'Z': 'ᴢ',
        '0': '0', '1': '1', '2': '2', '3': '3', '4': '4', '5': '5', '6': '6', '7': '7', '8': '8', '9': '9'
    }
    return ''.join(small_caps_map.get(c, c) for c in text)


async def get_global_count(character_id: str) -> int:
    """Get global grab count with caching"""
    cache_key = f"global_{character_id}"
    if cache_key in character_count_cache:
        return character_count_cache[cache_key]

    try:
        count = await user_collection.count_documents({'characters.id': character_id})
        character_count_cache[cache_key] = count
        return count
    except Exception as e:
        print(f"Error getting global count: {e}")
        return 0


async def get_anime_count(anime_name: str) -> int:
    """Get total characters in anime with caching"""
    cache_key = f"anime_{anime_name}"
    if cache_key in character_count_cache:
        return character_count_cache[cache_key]

    try:
        count = await collection.count_documents({'anime': anime_name})
        character_count_cache[cache_key] = count
        return count
    except Exception as e:
        print(f"Error getting anime count: {e}")
        return 0


async def get_users_by_character(character_id: str) -> list:
    """Get all users who own this character with counts"""
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
        return user_data
    except Exception as e:
        print(f"Error getting users by character: {e}")
        return []


async def inlinequery(update: Update, context) -> None:
    """Handle inline queries for character search with VIDEO SUPPORT and FAVORITE VALIDATION"""
    query = update.inline_query.query
    offset = int(update.inline_query.offset) if update.inline_query.offset else 0

    all_characters = []
    user = None
    user_id = None

    try:
        if query.startswith('collection.'):
            # User collection search
            parts = query.split(' ', 1)
            user_id = parts[0].split('.')[1]
            search_terms = parts[1] if len(parts) > 1 else ''

            if user_id.isdigit():
                user_id_int = int(user_id)

                # Get user from cache or database
                if user_id in user_collection_cache:
                    user = user_collection_cache[user_id]
                else:
                    user = await user_collection.find_one({'id': user_id_int})
                    if user:
                        user_collection_cache[user_id] = user

                if user:
                    # Get unique characters from user's collection
                    characters_dict = {}
                    for c in user.get('characters', []):
                        if isinstance(c, dict) and c.get('id'):
                            characters_dict[c.get('id')] = c
                    all_characters = list(characters_dict.values())

                    # Validate favorite exists in collection
                    favorite_char_data = user.get('favorites')
                    favorite_char = None

                    if favorite_char_data:
                        if isinstance(favorite_char_data, dict):
                            fav_id = favorite_char_data.get('id')
                            if any(c.get('id') == fav_id for c in all_characters):
                                favorite_char = favorite_char_data
                            else:
                                await user_collection.update_one(
                                    {'id': user_id_int},
                                    {'$unset': {'favorites': ""}}
                                )
                        elif isinstance(favorite_char_data, str):
                            favorite_char = next(
                                (c for c in all_characters if c.get('id') == favorite_char_data),
                                None
                            )
                            if not favorite_char:
                                await user_collection.update_one(
                                    {'id': user_id_int},
                                    {'$unset': {'favorites': ""}}
                                )

                    # If no search terms and user has valid favorite, show favorite FIRST
                    if not search_terms and favorite_char:
                        all_characters = [c for c in all_characters if c.get('id') != favorite_char.get('id')]
                        all_characters.insert(0, favorite_char)

                    # Apply search filter
                    if search_terms:
                        regex = re.compile(search_terms, re.IGNORECASE)
                        all_characters = [
                            c for c in all_characters 
                            if regex.search(c.get('name', '')) 
                            or regex.search(c.get('rarity', '')) 
                            or regex.search(c.get('id', '')) 
                            or regex.search(c.get('anime', ''))
                        ]
        else:
            # Global character search
            if query:
                regex = re.compile(re.escape(query), re.IGNORECASE)
                all_characters = await collection.find({
                    "$or": [
                        {"name": regex}, 
                        {"rarity": regex}, 
                        {"id": regex}, 
                        {"anime": regex}
                    ]
                }).to_list(length=200)
            else:
                if 'all_characters' in all_characters_cache:
                    all_characters = all_characters_cache['all_characters']
                else:
                    all_characters = await collection.find({}).limit(200).to_list(length=200)
                    all_characters_cache['all_characters'] = all_characters

        # Pagination
        characters = all_characters[offset:offset+50]
        has_more = len(all_characters) > offset + 50
        next_offset = str(offset + 50) if has_more else ""

        results = []
        for character in characters:
            char_id = character.get('id')
            if not char_id:
                continue

            char_name = character.get('name', 'Unknown')
            char_anime = character.get('anime', 'Unknown')
            char_rarity = character.get('rarity', '🟢 Common')
            char_img = character.get('img_url', '')

            is_video = character.get('is_video', False)

            # Extract rarity emoji and text
            if isinstance(char_rarity, str):
                rarity_parts = char_rarity.split(' ', 1)
                rarity_emoji = rarity_parts[0] if len(rarity_parts) > 0 else '🟢'
                rarity_text = rarity_parts[1] if len(rarity_parts) > 1 else 'Common'
            else:
                rarity_emoji = '🟢'
                rarity_text = 'Common'

            # Check if this is user's favorite
            is_favorite = False
            if user and user.get('favorites'):
                fav = user.get('favorites')
                if isinstance(fav, dict) and fav.get('id') == char_id:
                    is_favorite = True
                elif isinstance(fav, str) and fav == char_id:
                    is_favorite = True

            # Build caption
            if query.startswith('collection.') and user:
                user_character_count = sum(1 for c in user.get('characters', []) if c.get('id') == char_id)
                user_anime_count = sum(1 for c in user.get('characters', []) if c.get('anime') == char_anime)
                anime_total = await get_anime_count(char_anime)

                user_first_name = user.get('first_name', 'User')
                user_id_int = user.get('id')

                fav_indicator = "💖 " if is_favorite else ""
                media_type = "🎥" if is_video else "🖼"

                caption = (
                    f"<b>{fav_indicator}🔮 {to_small_caps('look at')} <a href='tg://user?id={user_id_int}'>{escape(user_first_name)}</a>{to_small_caps('s waifu')}</b>\n\n"
                    f"<b>🆔 {to_small_caps('id')}</b> <code>{char_id}</code>\n"
                    f"<b>🧬 {to_small_caps('name')}</b> <code>{escape(char_name)}</code> x{user_character_count}\n"
                    f"<b>📺 {to_small_caps('anime')}</b> <code>{escape(char_anime)}</code> {user_anime_count}/{anime_total}\n"
                    f"<b>{rarity_emoji} {to_small_caps('rarity')}</b> <code>{to_small_caps(rarity_text)}</code>\n"
                    f"<b>{media_type} {to_small_caps('type')}</b> <code>{to_small_caps('video' if is_video else 'image')}</code>"
                )

                if is_favorite:
                    caption += f"\n\n💖 <b>{to_small_caps('favorite character')}</b>"
            else:
                global_count = await get_global_count(char_id)
                media_type = "🎥" if is_video else "🖼"

                caption = (
                    f"<b>🔮 {to_small_caps('look at this waifu')}</b>\n\n"
                    f"<b>🆔 {to_small_caps('id')}</b> : <code>{char_id}</code>\n"
                    f"<b>🧬 {to_small_caps('name')}</b> : <code>{escape(char_name)}</code>\n"
                    f"<b>📺 {to_small_caps('anime')}</b> : <code>{escape(char_anime)}</code>\n"
                    f"<b>{rarity_emoji} {to_small_caps('rarity')}</b> : <code>{to_small_caps(rarity_text)}</code>\n"
                    f"<b>{media_type} {to_small_caps('type')}</b> : <code>{to_small_caps('video' if is_video else 'image')}</code>\n\n"
                    f"<b>🌍 {to_small_caps('globally grabbed')} {global_count} {to_small_caps('times')}</b>"
                )

            # MATCHING YOUR WORKING PATTERN: show_owners_{character_id}
            button = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    f"🏆 {to_small_caps('show owners')}", 
                    callback_data=f"show_owners_{char_id}"
                )]
            ])

            # Use video or photo result
            if is_video:
                results.append(
                    InlineQueryResultVideo(
                        id=f"{char_id}_{offset}_{time.time()}",
                        video_url=char_img,
                        mime_type="video/mp4",
                        thumbnail_url=char_img,
                        title=f"{char_name} ({char_anime})",
                        caption=caption,
                        parse_mode='HTML',
                        reply_markup=button
                    )
                )
            else:
                results.append(
                    InlineQueryResultPhoto(
                        id=f"{char_id}_{offset}_{time.time()}",
                        photo_url=char_img,
                        thumbnail_url=char_img,
                        caption=caption,
                        parse_mode='HTML',
                        reply_markup=button
                    )
                )

        await update.inline_query.answer(results, next_offset=next_offset, cache_time=5)

    except Exception as e:
        print(f"Error in inline query: {e}")
        import traceback
        traceback.print_exc()
        await update.inline_query.answer([], next_offset="", cache_time=5)


async def inline_show_owners(update: Update, context) -> None:
    """
    Handle show_owners callback for INLINE results
    EXACT COPY of your working handle_show_owners function
    """
    query = update.callback_query
    await query.answer()

    try:
        # Parse character_id from callback_data
        character_id = query.data.split('_')[2]
        
        LOGGER.info(f"[INLINE_OWNERS] Loading owners for character: {character_id}")
        
        # Get character
        character = await collection.find_one({'id': character_id})
        if not character:
            await query.answer("ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return

        # Get users who own this character
        users = await get_users_by_character(character_id)

        if not users:
            await query.answer("ɴᴏ ᴏɴᴇ ᴏᴡɴs ᴛʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ ʏᴇᴛ", show_alert=True)
            return

        # Sort by count
        users.sort(key=lambda x: x['count'], reverse=True)
        
        # Get global count
        global_count = await get_global_count(character_id)
        
        # Build owners caption
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

        caption = f"""<b>╭━━━━━━━━━━━━━━━━━╮</b>
<b>┃  🎴 {to_small_caps('character owners')}  ┃</b>
<b>╰━━━━━━━━━━━━━━━━━╯</b>

<b>🆔 {to_small_caps('id')}</b> : <code>{character_id}</code>
<b>🧬 {to_small_caps('name')}</b> : <code>{escape(char_name)}</code>
<b>📺 {to_small_caps('anime')}</b> : <code>{escape(char_anime)}</code>
<b>{rarity_emoji} {to_small_caps('rarity')}</b> : <code>{to_small_caps(rarity_text)}</code>

<b>━━━━━━━━━━━━━━━━━</b>
"""

        # Add top 10 owners
        for i, user in enumerate(users[:10], 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            user_link = f"<a href='tg://user?id={user['id']}'>{escape(user['first_name'])}</a>"
            if user.get('username'):
                user_link += f" (@{escape(user['username'])})"
            caption += f"\n{medal} {user_link} <code>x{user['count']}</code>"

        caption += f"\n\n<b>🔮 {to_small_caps('total grabbed')}</b> <code>{global_count}x</code>"

        # Only back button
        keyboard = [[
            InlineKeyboardButton(f"⬅️ {to_small_caps('back')}", callback_data=f"back_to_card_{character_id}")
        ]]

        # Edit the caption
        await query.edit_message_caption(
            caption=caption, 
            parse_mode='HTML', 
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        LOGGER.info(f"[INLINE_OWNERS] Successfully displayed owners for {character_id}")

    except Exception as e:
        LOGGER.error(f"[INLINE_OWNERS] Error: {e}")
        import traceback
        traceback.print_exc()
        await query.answer("ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ ᴏᴡɴᴇʀs", show_alert=True)


async def inline_back_to_card(update: Update, context) -> None:
    """
    Handle back_to_card callback for INLINE results
    """
    query = update.callback_query
    await query.answer()

    try:
        # Parse character_id
        character_id = query.data.split('_')[3]
        
        LOGGER.info(f"[INLINE_BACK] Going back to card for: {character_id}")
        
        # Get character
        character = await collection.find_one({'id': character_id})
        if not character:
            await query.answer("ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return

        # Rebuild original caption
        char_name = character.get('name', 'Unknown')
        char_anime = character.get('anime', 'Unknown')
        char_rarity = character.get('rarity', '🟢 Common')
        is_video = character.get('is_video', False)

        if isinstance(char_rarity, str):
            rarity_parts = char_rarity.split(' ', 1)
            rarity_emoji = rarity_parts[0] if len(rarity_parts) > 0 else '🟢'
            rarity_text = rarity_parts[1] if len(rarity_parts) > 1 else 'Common'
        else:
            rarity_emoji = '🟢'
            rarity_text = 'Common'

        global_count = await get_global_count(character_id)
        media_type = "🎥" if is_video else "🖼"

        caption = (
            f"<b>🔮 {to_small_caps('look at this waifu')}</b>\n\n"
            f"<b>🆔 {to_small_caps('id')}</b> : <code>{character_id}</code>\n"
            f"<b>🧬 {to_small_caps('name')}</b> : <code>{escape(char_name)}</code>\n"
            f"<b>📺 {to_small_caps('anime')}</b> : <code>{escape(char_anime)}</code>\n"
            f"<b>{rarity_emoji} {to_small_caps('rarity')}</b> : <code>{to_small_caps(rarity_text)}</code>\n"
            f"<b>{media_type} {to_small_caps('type')}</b> : <code>{to_small_caps('video' if is_video else 'image')}</code>\n\n"
            f"<b>🌍 {to_small_caps('globally grabbed')} {global_count} {to_small_caps('times')}</b>"
        )

        # Only show owners button
        keyboard = [[
            InlineKeyboardButton(f"🏆 {to_small_caps('show owners')}", callback_data=f"show_owners_{character_id}")
        ]]

        await query.edit_message_caption(
            caption=caption, 
            parse_mode='HTML', 
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        LOGGER.info(f"[INLINE_BACK] Successfully returned to card for {character_id}")

    except Exception as e:
        LOGGER.error(f"[INLINE_BACK] Error: {e}")
        import traceback
        traceback.print_exc()
        await query.answer("ᴇʀʀᴏʀ", show_alert=True)


# Register handlers with EXACT SAME patterns as your working code
application.add_handler(InlineQueryHandler(inlinequery, block=False))
application.add_handler(CallbackQueryHandler(inline_show_owners, pattern=r'^show_owners_', block=False))
application.add_handler(CallbackQueryHandler(inline_back_to_card, pattern=r'^back_to_card_', block=False))

LOGGER.info("[INLINE] ✅ Handlers registered with WORKING PATTERN from check.py! 🎯")