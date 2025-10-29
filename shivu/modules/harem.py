from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from html import escape 
import random
import math
from shivu import db, application

# Database collections
collection = db['anime_characters_lol']
user_collection = db['user_collection_lmaoooo']

# Rarity mapping for harem modes
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
    "amv": "🎥 Amv",
    "tiny": "👼 Tiny",
    "default": None
}


async def harem(update: Update, context: CallbackContext, page=0, edit=False) -> None:
    """Display user's character collection (harem) with VIDEO SUPPORT"""
    user_id = update.effective_user.id

    try:
        user = await user_collection.find_one({'id': user_id})
        if not user:
            message = update.message or update.callback_query.message
            await message.reply_text("You need to grab a character first using /grab command!")
            return

        characters = user.get('characters', [])
        if not characters:
            message = update.message or update.callback_query.message
            await message.reply_text("You don't have any characters yet! Use /grab to catch some.")
            return

        # Get favorite character
        fav_character = user.get('favorites', None)

        # Validate favorite character
        if fav_character and not isinstance(fav_character, dict):
            fav_character = None

        # Get harem mode
        hmode = user.get('smode', 'default')

        # Filter characters based on mode
        if hmode == "default" or hmode is None:
            filtered_chars = [char for char in characters if isinstance(char, dict)]
            rarity_filter = "All"
        else:
            rarity_value = HAREM_MODE_MAPPING.get(hmode, None)
            if rarity_value:
                filtered_chars = [
                    char for char in characters 
                    if isinstance(char, dict) and char.get('rarity') == rarity_value
                ]
                rarity_filter = rarity_value
            else:
                filtered_chars = [char for char in characters if isinstance(char, dict)]
                rarity_filter = "All"

        if not filtered_chars:
            message = update.message or update.callback_query.message
            await message.reply_text(
                f"You don't have any characters with rarity: {rarity_filter}\n"
                f"Change mode using /smode"
            )
            return

        # Sort characters
        filtered_chars = sorted(filtered_chars, key=lambda x: (x.get('anime', ''), x.get('id', '')))

        # Count characters
        character_counts = {}
        for char in filtered_chars:
            char_id = char.get('id')
            if char_id:
                character_counts[char_id] = character_counts.get(char_id, 0) + 1

        # Pagination
        total_pages = math.ceil(len(filtered_chars) / 10)
        if page < 0 or page >= total_pages:
            page = 0

        # Build message
        user_name = escape(update.effective_user.first_name)
        harem_message = f"<b>🎴 {user_name}'s Collection ({rarity_filter})</b>\n"

        # Add favorite indicator if exists
        if fav_character:
            harem_message += f"<b>💖 Favorite: {escape(fav_character.get('name', 'Unknown'))}</b>\n"

        harem_message += f"<b>Page {page + 1}/{total_pages}</b>\n\n"

        # Get current page characters
        start_idx = page * 10
        end_idx = start_idx + 10
        current_chars = filtered_chars[start_idx:end_idx]

        # Group by anime
        grouped = {}
        for char in current_chars:
            anime = char.get('anime', 'Unknown')
            if anime not in grouped:
                grouped[anime] = []
            grouped[anime].append(char)

        # Track included characters to avoid duplicates
        included = set()

        for anime, chars in grouped.items():
            # Count user's characters from this anime
            user_anime_count = len([
                c for c in user['characters'] 
                if isinstance(c, dict) and c.get('anime') == anime
            ])

            # Count total characters in this anime
            total_anime_count = await collection.count_documents({"anime": anime})

            harem_message += f'<b>➥ {anime} [{user_anime_count}/{total_anime_count}]</b>\n'

            for char in chars:
                char_id = char.get('id')
                if char_id and char_id not in included:
                    count = character_counts.get(char_id, 1)
                    name = char.get('name', 'Unknown')
                    rarity = char.get('rarity', '🟢 Common')

                    # Get rarity emoji
                    if isinstance(rarity, str):
                        rarity_emoji = rarity.split(' ')[0]
                    else:
                        rarity_emoji = '🟢'

                    # Add heart emoji if this is the favorite
                    fav_marker = ""
                    if fav_character and char_id == fav_character.get('id'):
                        fav_marker = " 💖"

                    harem_message += f'  {rarity_emoji} <code>{char_id}</code> • <b>{escape(name)}</b> ×{count}{fav_marker}\n'
                    included.add(char_id)

            harem_message += '\n'

        # Calculate total character count
        total_char_count = len(filtered_chars)
        unique_char_count = len(character_counts)

        # Create keyboard with character count
        keyboard = [
            [
                InlineKeyboardButton(
                    "🎭 View All", 
                    switch_inline_query_current_chat=f"collection.{user_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    f"📊 Total: {total_char_count} | Unique: {unique_char_count}", 
                    callback_data="harem_char_count"
                )
            ]
        ]

        # Add navigation buttons
        if total_pages > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append(
                    InlineKeyboardButton("⬅️ Prev", callback_data=f"harem_page:{page - 1}:{user_id}")
                )
            if page < total_pages - 1:
                nav_buttons.append(
                    InlineKeyboardButton("Next ➡️", callback_data=f"harem_page:{page + 1}:{user_id}")
                )
            if nav_buttons:
                keyboard.append(nav_buttons)

        reply_markup = InlineKeyboardMarkup(keyboard)
        message = update.message or update.callback_query.message

        # ===== KEY CHANGE: Determine which media to show and detect video =====
        display_media = None
        is_video_display = False

        # Priority 1: Show favorite if it exists
        if fav_character and fav_character.get('img_url'):
            display_media = fav_character['img_url']
            is_video_display = fav_character.get('is_video', False)
        # Priority 2: Show random character from filtered list
        elif filtered_chars:
            random_char = random.choice(filtered_chars)
            display_media = random_char.get('img_url')
            is_video_display = random_char.get('is_video', False)

        # Send or edit message with VIDEO SUPPORT
        if display_media:
            if edit:
                # Editing existing message - just update caption
                await message.edit_caption(
                    caption=harem_message, 
                    reply_markup=reply_markup, 
                    parse_mode='HTML'
                )
            else:
                # New message - send photo or video
                if is_video_display:
                    # Send as VIDEO
                    await message.reply_video(
                        video=display_media,
                        caption=harem_message,
                        reply_markup=reply_markup,
                        parse_mode='HTML',
                        supports_streaming=True,  # ← PREVENTS GIF CONVERSION!
                        read_timeout=120,
                        write_timeout=120
                    )
                else:
                    # Send as PHOTO
                    await message.reply_photo(
                        photo=display_media,
                        caption=harem_message,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
        else:
            # Fallback to text-only
            if edit:
                await message.edit_text(
                    text=harem_message,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            else:
                await message.reply_text(
                    text=harem_message,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )

    except Exception as e:
        print(f"Error in harem command: {e}")
        import traceback
        traceback.print_exc()
        message = update.message or update.callback_query.message
        await message.reply_text("An error occurred while loading your collection.")


async def harem_callback(update: Update, context: CallbackContext) -> None:
    """Handle harem pagination callbacks"""
    query = update.callback_query

    try:
        data = query.data
        _, page, user_id = data.split(':')
        page = int(page)
        user_id = int(user_id)

        # Verify user
        if query.from_user.id != user_id:
            await query.answer("⚠️ This is not your collection!", show_alert=True)
            return

        await query.answer()
        await harem(update, context, page, edit=True)

    except Exception as e:
        print(f"Error in harem callback: {e}")
        await query.answer("Error loading page", show_alert=True)


async def unfav(update: Update, context: CallbackContext) -> None:
    """Remove favorite character"""
    user_id = update.effective_user.id

    try:
        user = await user_collection.find_one({'id': user_id})
        if not user:
            await update.message.reply_text('𝙔𝙤𝙪 𝙝𝙖𝙫𝙚 𝙣𝙤𝙩 𝙂𝙤𝙩 𝘼𝙣𝙮 𝙒𝘼𝙄𝙁𝙐 𝙮𝙚𝙩...')
            return

        fav_character = user.get('favorites', None)

        if not fav_character or not isinstance(fav_character, dict):
            await update.message.reply_text('💔 𝙔𝙤𝙪 𝙙𝙤𝙣\'𝙩 𝙝𝙖𝙫𝙚 𝙖 𝙛𝙖𝙫𝙤𝙧𝙞𝙩𝙚 𝙘𝙝𝙖𝙧𝙖𝙘𝙩𝙚𝙧 𝙨𝙚𝙩!')
            return

        # Create confirmation buttons
        buttons = [
            [
                InlineKeyboardButton("✅ ʏᴇs", callback_data=f"harem_unfav_yes:{user_id}"),
                InlineKeyboardButton("❌ ɴᴏ", callback_data=f"harem_unfav_no:{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        # ===== KEY CHANGE: Check if favorite is video =====
        is_video_fav = fav_character.get('is_video', False)
        media_url = fav_character.get("img_url", "")

        caption = (
            f"<b>💔 ᴅᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ʀᴇᴍᴏᴠᴇ ᴛʜɪs ғᴀᴠᴏʀɪᴛᴇ?</b>\n\n"
            f"✨ <b>ɴᴀᴍᴇ:</b> <code>{fav_character.get('name', 'Unknown')}</code>\n"
            f"📺 <b>ᴀɴɪᴍᴇ:</b> <code>{fav_character.get('anime', 'Unknown')}</code>\n"
            f"🆔 <b>ɪᴅ:</b> <code>{fav_character.get('id', 'Unknown')}</code>"
        )

        if is_video_fav:
            await update.message.reply_video(
                video=media_url,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode='HTML',
                supports_streaming=True
            )
        else:
            await update.message.reply_photo(
                photo=media_url,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

    except Exception as e:
        print(f"Error in unfav command: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text('ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ᴘʀᴏᴄᴇssɪɴɢ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ.')


async def handle_unfav_callback(update: Update, context: CallbackContext) -> None:
    """Handle unfavorite button callbacks"""
    query = update.callback_query

    try:
        data = query.data
        await query.answer()

        # Parse callback data
        if ':' not in data:
            await query.answer("❌ ɪɴᴠᴀʟɪᴅ ᴄᴀʟʟʙᴀᴄᴋ ᴅᴀᴛᴀ!", show_alert=True)
            return

        action, user_id_str = data.split(':', 1)
        user_id = int(user_id_str)

        # Verify user
        if query.from_user.id != user_id:
            await query.answer("⚠️ ᴛʜɪs ɪs ɴᴏᴛ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ!", show_alert=True)
            return

        if action == 'harem_unfav_yes':  # Confirm unfavorite
            user = await user_collection.find_one({'id': user_id})
            if not user:
                await query.answer("❌ ᴜsᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ!", show_alert=True)
                return

            fav_character = user.get('favorites', None)

            # Remove favorite
            result = await user_collection.update_one(
                {'id': user_id},
                {'$unset': {'favorites': ""}}
            )

            if result.matched_count == 0:
                await query.answer("❌ ғᴀɪʟᴇᴅ ᴛᴏ ᴜᴘᴅᴀᴛᴇ!", show_alert=True)
                return

            await query.edit_message_caption(
                caption=(
                    f"<b>💔 ғᴀᴠᴏʀɪᴛᴇ ʀᴇᴍᴏᴠᴇᴅ!</b>\n\n"
                    f"✨ <b>ɴᴀᴍᴇ:</b> <code>{fav_character.get('name', 'Unknown')}</code>\n"
                    f"📺 <b>ᴀɴɪᴍᴇ:</b> <code>{fav_character.get('anime', 'Unknown')}</code>\n\n"
                    f"<i>💖 ʏᴏᴜ ᴄᴀɴ sᴇᴛ ᴀ ɴᴇᴡ ғᴀᴠᴏʀɪᴛᴇ ᴜsɪɴɢ /fav</i>"
                ),
                parse_mode='HTML'
            )

        elif action == 'harem_unfav_no':  # Cancel
            await query.edit_message_caption(
                caption="❌ ᴀᴄᴛɪᴏɴ ᴄᴀɴᴄᴇʟᴇᴅ. ғᴀᴠᴏʀɪᴛᴇ ᴋᴇᴘᴛ.",
                parse_mode='HTML'
            )

    except Exception as e:
        print(f"Error in unfav callback: {e}")
        import traceback
        traceback.print_exc()
        try:
            await query.answer(f"❌ ᴇʀʀᴏʀ: {str(e)[:100]}", show_alert=True)
        except:
            pass


async def set_hmode(update: Update, context: CallbackContext) -> None:
    """Set harem display mode"""
    keyboard = [
        [
            InlineKeyboardButton("🧩 Default", callback_data="harem_mode_default"),
            InlineKeyboardButton("🔮 By Rarity", callback_data="harem_mode_rarity"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_photo(
        photo="https://te.legra.ph/file/e714526fdc85b8800e1de.jpg",
        caption="<b>⚙️ Collection Display Mode</b>\n\nChoose how to display your collection:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def hmode_rarity(update: Update, context: CallbackContext) -> None:
    """Show rarity selection menu"""
    keyboard = [
        [
            InlineKeyboardButton("🟢 Common", callback_data="harem_mode_common"),
            InlineKeyboardButton("🟣 Rare", callback_data="harem_mode_rare"),
            InlineKeyboardButton("🟡 Legendary", callback_data="harem_mode_legendary"),
        ],
        [
            InlineKeyboardButton("💮 Special", callback_data="harem_mode_special"),
            InlineKeyboardButton("💫 Neon", callback_data="harem_mode_neon"),
            InlineKeyboardButton("✨ Manga", callback_data="harem_mode_manga"),
        ],
        [
            InlineKeyboardButton("🎭 Cosplay", callback_data="harem_mode_cosplay"),
            InlineKeyboardButton("🎐 Celestial", callback_data="harem_mode_celestial"),
            InlineKeyboardButton("🔮 Premium", callback_data="harem_mode_premium"),
        ],
        [
            InlineKeyboardButton("💋 Erotic", callback_data="harem_mode_erotic"),
            InlineKeyboardButton("🌤 Summer", callback_data="harem_mode_summer"),
            InlineKeyboardButton("☃️ Winter", callback_data="harem_mode_winter"),
        ],
        [
            InlineKeyboardButton("☔️ Monsoon", callback_data="harem_mode_monsoon"),
            InlineKeyboardButton("💝 Valentine", callback_data="harem_mode_valentine"),
            InlineKeyboardButton("🎃 Halloween", callback_data="harem_mode_halloween"),
        ],
        [
            InlineKeyboardButton("🎄 Christmas", callback_data="harem_mode_christmas"),
            InlineKeyboardButton("🏵 Mythic", callback_data="harem_mode_mythic"),
            InlineKeyboardButton("🎗 Events", callback_data="harem_mode_events"),
        ],
        [
            InlineKeyboardButton("🎥 Amv", callback_data="harem_mode_amv"),
            InlineKeyboardButton("👼 Tiny", callback_data="harem_mode_tiny"),
        ],
        [
            InlineKeyboardButton("⬅️ Back", callback_data="harem_mode_back"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    query = update.callback_query
    await query.edit_message_caption(
        caption="<b>🔮 Filter by Rarity</b>\n\nSelect a rarity to display:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    await query.answer()


async def mode_button(update: Update, context: CallbackContext) -> None:
    """Handle mode selection buttons"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    try:
        if data == "harem_mode_default":
            await user_collection.update_one(
                {'id': user_id}, 
                {'$set': {'smode': 'default'}}
            )
            await query.answer("✅ Mode set to Default")
            await query.edit_message_caption(
                caption="<b>✅ Display Mode Updated</b>\n\nShowing: <b>All Characters</b>",
                parse_mode='HTML'
            )

        elif data == "harem_mode_rarity":
            await hmode_rarity(update, context)

        elif data == "harem_mode_back":
            keyboard = [
                [
                    InlineKeyboardButton("🧩 Default", callback_data="harem_mode_default"),
                    InlineKeyboardButton("🔮 By Rarity", callback_data="harem_mode_rarity"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_caption(
                caption="<b>⚙️ Collection Display Mode</b>\n\nChoose how to display your collection:",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            await query.answer()

        elif data.startswith("harem_mode_"):
            # Extract mode name
            mode_name = data.replace("harem_mode_", "")
            rarity_display = HAREM_MODE_MAPPING.get(mode_name, "Unknown")

            await user_collection.update_one(
                {'id': user_id}, 
                {'$set': {'smode': mode_name}}
            )
            await query.answer(f"✅ Mode set to {rarity_display}")
            await query.edit_message_caption(
                caption=f"<b>✅ Display Mode Updated</b>\n\nShowing: <b>{rarity_display}</b>",
                parse_mode='HTML'
            )

    except Exception as e:
        print(f"Error in mode button: {e}")
        import traceback
        traceback.print_exc()
        await query.answer("Error updating mode", show_alert=True)


async def handle_char_count_info(update: Update, context: CallbackContext) -> None:
    """Handle character count info button"""
    query = update.callback_query
    await query.answer(
        "📊 Total: All characters you own\n"
        "🎯 Unique: Different characters (no duplicates)",
        show_alert=True
    )


# Register handlers - ORDER MATTERS! More specific patterns first
application.add_handler(CommandHandler(["harem"], harem, block=False))
application.add_handler(CommandHandler("smode", set_hmode, block=False))
application.add_handler(CommandHandler("unfav", unfav, block=False))

# Callback handlers with specific prefixes to avoid conflicts
application.add_handler(CallbackQueryHandler(harem_callback, pattern='^harem_page:', block=False))
application.add_handler(CallbackQueryHandler(mode_button, pattern='^harem_mode_', block=False))
application.add_handler(CallbackQueryHandler(handle_unfav_callback, pattern="^harem_unfav_", block=False))
application.add_handler(CallbackQueryHandler(handle_char_count_info, pattern="^harem_char_count$", block=False))