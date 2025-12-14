from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from html import escape
import random
from shivu import db, application

user_collection = db['user_collection_lmaoooo']

# Default Harem Style Templates
DEFAULT_STYLES = {
    "classic": {
        "name": "🎨 Classic",
        "header": "<b>{user_name}'s ʜᴀʀᴇᴍ - ᴘᴀɢᴇ {page}/{total_pages}</b>\n\n",
        "anime_header": "<b>𖤍 {anime} ｛{user_count}/{total_count}｝</b>\n",
        "separator": "⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋\n",
        "character": "<b>𒄬 {id}</b> [ {rarity} ] <b>{name}</b>{fav} ×{count}\n",
        "footer": "⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋\n\n"
    },
    "minimal": {
        "name": "⚡ Minimal",
        "header": "<b>📚 {user_name}'s Collection [{page}/{total_pages}]</b>\n\n",
        "anime_header": "<b>• {anime} ({user_count}/{total_count})</b>\n",
        "separator": "━━━━━━━━━━━━━━━\n",
        "character": "  {rarity} {id} • {name}{fav} ×{count}\n",
        "footer": "\n"
    },
    "elegant": {
        "name": "✨ Elegant",
        "header": "╭─────────────────╮\n│ <b>{user_name}'s Collection</b> │\n│   Page {page} of {total_pages}   │\n╰─────────────────╯\n\n",
        "anime_header": "╔═ <b>{anime}</b> ═╗\n├─ {user_count}/{total_count} Characters\n",
        "separator": "├─────────────────\n",
        "character": "│ {rarity} <code>{id}</code> ► {name}{fav} ×{count}\n",
        "footer": "╚═════════════════\n\n"
    },
    "cute": {
        "name": "🌸 Cute",
        "header": "✧･ﾟ: *✧･ﾟ:* {user_name}'s Harem *:･ﾟ✧*:･ﾟ✧\n━━━ Page {page}/{total_pages} ━━━\n\n",
        "anime_header": "🌺 <b>{anime}</b> 🌺\n♡ {user_count}/{total_count} Characters ♡\n",
        "separator": "･ﾟ✧･ﾟ✧･ﾟ✧･ﾟ✧･ﾟ✧\n",
        "character": "  ღ {id} {rarity} {name}{fav} ×{count}\n",
        "footer": "･ﾟ✧･ﾟ✧･ﾟ✧･ﾟ✧･ﾟ✧\n\n"
    },
    "modern": {
        "name": "🎯 Modern",
        "header": "▰▰▰ {user_name}'s COLLECTION ▰▰▰\n⟨ {page}/{total_pages} ⟩\n\n",
        "anime_header": "▸ <b>{anime}</b>\n▹ Progress: {user_count}/{total_count}\n",
        "separator": "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n",
        "character": "  ◆ {id} | {rarity} | {name}{fav} ×{count}\n",
        "footer": "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
    },
    "royal": {
        "name": "👑 Royal",
        "header": "╔══════════════════╗\n║ {user_name}'s Royal Harem ║\n║    【{page}/{total_pages}】    ║\n╚══════════════════╝\n\n",
        "anime_header": "┏━━ <b>{anime}</b> ━━┓\n┃ 👥 {user_count}/{total_count} Characters\n",
        "separator": "┣━━━━━━━━━━━━━━━\n",
        "character": "┃ 💎 {id} ◈ {rarity} ◈ {name}{fav} ×{count}\n",
        "footer": "┗━━━━━━━━━━━━━━━\n\n"
    }
}

# Display Options
DISPLAY_OPTIONS = {
    "show_url": {
        "name": "🔗 Show URLs",
        "description": "Display image URLs below character info"
    },
    "preview_image": {
        "name": "🖼️ Preview Image",
        "description": "Show character image as preview (default)"
    },
    "video_support": {
        "name": "🎥 Video Support",
        "description": "Enable AMV/video preview for characters"
    },
    "show_rarity_full": {
        "name": "💫 Full Rarity",
        "description": "Show full rarity name instead of emoji only"
    },
    "compact_mode": {
        "name": "📦 Compact Mode",
        "description": "Reduce spacing and separators"
    },
    "show_id_bottom": {
        "name": "🔢 ID at Bottom",
        "description": "Move character IDs to bottom of each entry"
    }
}


async def hstyle(update: Update, context: CallbackContext) -> None:
    """Main /hstyle command - shows style selection menu"""
    user_id = update.effective_user.id
    
    try:
        user = await user_collection.find_one({'id': user_id})
        current_style = user.get('harem_style', 'classic') if user else 'classic'
        
        keyboard = [
            [
                InlineKeyboardButton("🎨 Choose Style", callback_data="hstyle_select"),
                InlineKeyboardButton("⚙️ Display Options", callback_data="hstyle_options")
            ],
            [
                InlineKeyboardButton("✏️ Custom Style", callback_data="hstyle_custom"),
                InlineKeyboardButton("🔄 Reset Default", callback_data="hstyle_reset")
            ],
            [
                InlineKeyboardButton("👁️ Preview Current", callback_data="hstyle_preview")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        style_name = DEFAULT_STYLES.get(current_style, {}).get('name', current_style)
        
        message_text = (
            "╭─────────────────────╮\n"
            "│ <b>ʜᴀʀᴇᴍ sᴛʏʟᴇ sᴇᴛᴛɪɴɢs</b> │\n"
            "╰─────────────────────╯\n\n"
            f"<b>📌 Current Style:</b> {style_name}\n\n"
            "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
            "<b>🎨 Choose Style</b>\n"
            "  Select from preset templates\n\n"
            "<b>⚙️ Display Options</b>\n"
            "  Customize display features\n\n"
            "<b>✏️ Custom Style</b>\n"
            "  Create your own template\n\n"
            "<b>🔄 Reset Default</b>\n"
            "  Return to classic style\n\n"
            "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈"
        )
        
        await update.message.reply_text(
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        print(f"Error in hstyle command: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text("⚠️ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ")


async def hstyle_select(update: Update, context: CallbackContext) -> None:
    """Show available style templates"""
    query = update.callback_query
    await query.answer()
    
    keyboard = []
    row = []
    for style_key, style_data in DEFAULT_STYLES.items():
        row.append(InlineKeyboardButton(
            style_data['name'], 
            callback_data=f"hstyle_apply_{style_key}"
        ))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="hstyle_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = (
        "╭─────────────────────╮\n"
        "│  <b>sᴇʟᴇᴄᴛ ʜᴀʀᴇᴍ sᴛʏʟᴇ</b>  │\n"
        "╰─────────────────────╯\n\n"
        "<b>Available Templates:</b>\n\n"
        "🎨 <b>Classic</b> - Traditional style\n"
        "⚡ <b>Minimal</b> - Clean & simple\n"
        "✨ <b>Elegant</b> - Sophisticated look\n"
        "🌸 <b>Cute</b> - Kawaii aesthetic\n"
        "🎯 <b>Modern</b> - Contemporary design\n"
        "👑 <b>Royal</b> - Majestic theme\n\n"
        "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        "Select a style to preview"
    )
    
    await query.edit_message_text(
        text=message_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def hstyle_options(update: Update, context: CallbackContext) -> None:
    """Show display options"""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    try:
        user = await user_collection.find_one({'id': user_id})
        options = user.get('harem_display_options', {}) if user else {}
        
        keyboard = []
        for opt_key, opt_data in DISPLAY_OPTIONS.items():
            is_enabled = options.get(opt_key, False)
            status = "✅" if is_enabled else "❌"
            keyboard.append([InlineKeyboardButton(
                f"{status} {opt_data['name']}", 
                callback_data=f"hstyle_toggle_{opt_key}"
            )])
        
        keyboard.append([InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="hstyle_back")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            "╭─────────────────────╮\n"
            "│ <b>ᴅɪsᴘʟᴀʏ ᴏᴘᴛɪᴏɴs</b> │\n"
            "╰─────────────────────╯\n\n"
            "<b>Customize your harem display:</b>\n\n"
        )
        
        for opt_key, opt_data in DISPLAY_OPTIONS.items():
            is_enabled = options.get(opt_key, False)
            status = "✅ Enabled" if is_enabled else "❌ Disabled"
            message_text += f"<b>{opt_data['name']}</b>\n"
            message_text += f"  {opt_data['description']}\n"
            message_text += f"  Status: {status}\n\n"
        
        message_text += "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        message_text += "Tap to toggle options"
        
        await query.edit_message_text(
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        print(f"Error showing options: {e}")
        await query.answer("❌ Error loading options", show_alert=True)


async def hstyle_custom(update: Update, context: CallbackContext) -> None:
    """Show custom style creation instructions"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📝 Set Custom Header", callback_data="hstyle_custom_header")],
        [InlineKeyboardButton("🎨 Set Character Format", callback_data="hstyle_custom_char")],
        [InlineKeyboardButton("📊 Set Anime Header", callback_data="hstyle_custom_anime")],
        [InlineKeyboardButton("💾 Save Custom Style", callback_data="hstyle_custom_save")],
        [InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="hstyle_back")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = (
        "╭─────────────────────╮\n"
        "│ <b>ᴄᴜsᴛᴏᴍ sᴛʏʟᴇ ᴄʀᴇᴀᴛᴏʀ</b> │\n"
        "╰─────────────────────╯\n\n"
        "<b>Create your own harem style!</b>\n\n"
        "🎯 <b>Available Variables:</b>\n\n"
        "<code>{user_name}</code> - Your name\n"
        "<code>{page}</code> - Current page\n"
        "<code>{total_pages}</code> - Total pages\n"
        "<code>{anime}</code> - Anime name\n"
        "<code>{user_count}</code> - Your characters\n"
        "<code>{total_count}</code> - Total characters\n"
        "<code>{id}</code> - Character ID\n"
        "<code>{name}</code> - Character name\n"
        "<code>{rarity}</code> - Rarity emoji\n"
        "<code>{fav}</code> - Favorite marker\n"
        "<code>{count}</code> - Character count\n\n"
        "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
        "⚠️ <i>Custom styles coming soon!\i>\n"
        "<i>For now, use preset templates</i>"
    )
    
    await query.edit_message_text(
        text=message_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def hstyle_preview(update: Update, context: CallbackContext) -> None:
    """Preview current style with sample data"""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    try:
        user = await user_collection.find_one({'id': user_id})
        current_style = user.get('harem_style', 'classic') if user else 'classic'
        style_template = DEFAULT_STYLES.get(current_style, DEFAULT_STYLES['classic'])
        
        # Create sample preview
        user_name = escape(query.from_user.first_name)
        preview = style_template['header'].format(
            user_name=user_name,
            page=1,
            total_pages=3
        )
        
        preview += style_template['anime_header'].format(
            anime="Sample Anime",
            user_count=5,
            total_count=10
        )
        
        preview += style_template['separator']
        
        preview += style_template['character'].format(
            id="001",
            rarity="🟡",
            name="Sample Character",
            fav=" [🍁]",
            count=2
        )
        
        preview += style_template['character'].format(
            id="002",
            rarity="🟣",
            name="Another Character",
            fav="",
            count=1
        )
        
        preview += style_template['footer']
        
        keyboard = [[InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="hstyle_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=f"<b>📺 PREVIEW: {style_template['name']}</b>\n\n{preview}",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        print(f"Error in preview: {e}")
        await query.answer("❌ Preview error", show_alert=True)


async def hstyle_callback(update: Update, context: CallbackContext) -> None:
    """Handle all hstyle callbacks"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    try:
        if data == "hstyle_select":
            await hstyle_select(update, context)
            
        elif data == "hstyle_options":
            await hstyle_options(update, context)
            
        elif data == "hstyle_custom":
            await hstyle_custom(update, context)
            
        elif data == "hstyle_preview":
            await hstyle_preview(update, context)
            
        elif data == "hstyle_reset":
            await user_collection.update_one(
                {'id': user_id},
                {'$set': {'harem_style': 'classic', 'harem_display_options': {}}}
            )
            await query.answer("✅ Reset to default style", show_alert=True)
            await query.edit_message_text(
                text=(
                    "╭─────────────────────╮\n"
                    "│   <b>sᴛʏʟᴇ ʀᴇsᴇᴛ</b>   │\n"
                    "╰─────────────────────╯\n\n"
                    "✨ Style reset to <b>Classic</b>\n\n"
                    "All display options cleared\n\n"
                    "Use /harem to see changes"
                ),
                parse_mode='HTML'
            )
            
        elif data.startswith("hstyle_apply_"):
            style_key = data.replace("hstyle_apply_", "")
            style_data = DEFAULT_STYLES.get(style_key)
            
            if style_data:
                await user_collection.update_one(
                    {'id': user_id},
                    {'$set': {'harem_style': style_key}}
                )
                await query.answer(f"✅ {style_data['name']} applied!", show_alert=False)
                await query.edit_message_text(
                    text=(
                        "╭─────────────────────╮\n"
                        "│  <b>sᴛʏʟᴇ ᴀᴘᴘʟɪᴇᴅ</b>  │\n"
                        "╰─────────────────────╯\n\n"
                        f"✨ <b>{style_data['name']}</b>\n\n"
                        "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
                        "   ✦ ᴀᴄᴛɪᴠᴀᴛᴇᴅ ✦\n\n"
                        "Your harem now uses\n"
                        f"the {style_data['name'].lower()} template\n\n"
                        "Use /harem to see changes"
                    ),
                    parse_mode='HTML'
                )
            else:
                await query.answer("❌ Style not found", show_alert=True)
                
        elif data.startswith("hstyle_toggle_"):
            option_key = data.replace("hstyle_toggle_", "")
            
            user = await user_collection.find_one({'id': user_id})
            options = user.get('harem_display_options', {}) if user else {}
            
            # Toggle the option
            options[option_key] = not options.get(option_key, False)
            
            await user_collection.update_one(
                {'id': user_id},
                {'$set': {'harem_display_options': options}}
            )
            
            status = "enabled" if options[option_key] else "disabled"
            opt_name = DISPLAY_OPTIONS[option_key]['name']
            await query.answer(f"✅ {opt_name} {status}", show_alert=False)
            
            # Refresh the options menu
            await hstyle_options(update, context)
            
        elif data == "hstyle_back":
            # Return to main menu
            await hstyle(update, context)
            
    except Exception as e:
        print(f"Error in hstyle callback: {e}")
        import traceback
        traceback.print_exc()
        await query.answer("❌ An error occurred", show_alert=True)


# Export function to get user's style template
async def get_user_style_template(user_id):
    """Get the style template for a user"""
    try:
        user = await user_collection.find_one({'id': user_id})
        if user:
            style_key = user.get('harem_style', 'classic')
            return DEFAULT_STYLES.get(style_key, DEFAULT_STYLES['classic'])
        return DEFAULT_STYLES['classic']
    except:
        return DEFAULT_STYLES['classic']


# Export function to get user's display options
async def get_user_display_options(user_id):
    """Get the display options for a user"""
    try:
        user = await user_collection.find_one({'id': user_id})
        if user:
            return user.get('harem_display_options', {})
        return {}
    except:
        return {}


# Register handlers
application.add_handler(CommandHandler("hstyle", hstyle, block=False))
application.add_handler(CallbackQueryHandler(hstyle_callback, pattern='^hstyle_', block=False))