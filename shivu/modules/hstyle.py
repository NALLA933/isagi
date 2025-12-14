#v3 bc


from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from html import escape
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, List, Any
from enum import Enum
from shivu import db, application

user_collection = db['user_collection_lmaoooo']


class MediaType(Enum):
    IMAGE = "image"
    VIDEO = "video"
    NONE = "none"


@dataclass
class StyleTemplate:
    name: str
    header: str
    anime_header: str
    separator: str
    character: str
    footer: str
    
    def format_header(self, user_name: str, page: int, total_pages: int) -> str:
        return self.header.format(
            user_name=escape(user_name),
            page=page,
            total_pages=total_pages
        )
    
    def format_anime_header(self, anime: str, user_count: int, total_count: int) -> str:
        return self.anime_header.format(
            anime=escape(anime),
            user_count=user_count,
            total_count=total_count
        )
    
    def format_character(self, char_id: str, rarity: str, name: str, 
                        fav: str, count: int) -> str:
        return self.character.format(
            id=char_id,
            rarity=rarity,
            name=escape(name),
            fav=fav,
            count=count
        )


@dataclass
class DisplayOptions:
    show_url: bool = False
    preview_image: bool = True
    video_support: bool = False
    show_rarity_full: bool = False
    compact_mode: bool = False
    show_id_bottom: bool = False
    
    @classmethod
    def from_dict(cls, data: Dict[str, bool]) -> 'DisplayOptions':
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})
    
    def to_dict(self) -> Dict[str, bool]:
        return asdict(self)


@dataclass
class CharacterData:
    id: str
    name: str
    rarity: str
    anime: str
    count: int = 1
    is_fav: bool = False
    img_url: Optional[str] = None
    video_url: Optional[str] = None
    total_in_anime: int = 0


@dataclass
class CustomStyleBuilder:
    user_id: int
    header_template: Optional[str] = None
    anime_header_template: Optional[str] = None
    character_template: Optional[str] = None
    separator_template: Optional[str] = None
    footer_template: Optional[str] = None
    
    def is_complete(self) -> bool:
        return all([
            self.header_template,
            self.anime_header_template,
            self.character_template
        ])
    
    def to_style_template(self, name: str = "Custom") -> StyleTemplate:
        return StyleTemplate(
            name=name,
            header=self.header_template or "",
            anime_header=self.anime_header_template or "",
            separator=self.separator_template or "",
            character=self.character_template or "",
            footer=self.footer_template or ""
        )


class StyleManager:
    STYLES: Dict[str, StyleTemplate] = {
        "classic": StyleTemplate(
            name="🎨 Classic",
            header="<b>{user_name}'s ʜᴀʀᴇᴍ - ᴘᴀɢᴇ {page}/{total_pages}</b>\n\n",
            anime_header="<b>𖤍 {anime} ｛{user_count}/{total_count}｝</b>\n",
            separator="⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋\n",
            character="<b>𒄬 {id}</b> [ {rarity} ] <b>{name}</b>{fav} ×{count}\n",
            footer="⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋\n\n"
        ),
        "minimal": StyleTemplate(
            name="⚡ Minimal",
            header="<b>📚 {user_name}'s Collection [{page}/{total_pages}]</b>\n\n",
            anime_header="<b>• {anime} ({user_count}/{total_count})</b>\n",
            separator="━━━━━━━━━━━━━━━\n",
            character="  {rarity} {id} • {name}{fav} ×{count}\n",
            footer="\n"
        ),
        "elegant": StyleTemplate(
            name="✨ Elegant",
            header="<b>{user_name}'s Collection</b>\nPage {page} of {total_pages}\n\n",
            anime_header="═ <b>{anime}</b> ═\n{user_count}/{total_count} Characters\n",
            separator="─────────────────\n",
            character="{rarity} <code>{id}</code> ► {name}{fav} ×{count}\n",
            footer="═════════════════\n\n"
        ),
        "cute": StyleTemplate(
            name="🌸 Cute",
            header="✧･ﾟ: *✧･ﾟ:* {user_name}'s Harem *:･ﾟ✧*:･ﾟ✧\nPage {page}/{total_pages}\n\n",
            anime_header="🌺 <b>{anime}</b> 🌺\n♡ {user_count}/{total_count} Characters ♡\n",
            separator="･ﾟ✧･ﾟ✧･ﾟ✧･ﾟ✧･ﾟ✧\n",
            character="  ღ {id} {rarity} {name}{fav} ×{count}\n",
            footer="･ﾟ✧･ﾟ✧･ﾟ✧･ﾟ✧･ﾟ✧\n\n"
        ),
        "modern": StyleTemplate(
            name="🎯 Modern",
            header="▰▰▰ {user_name}'s COLLECTION ▰▰▰\n⟨ {page}/{total_pages} ⟩\n\n",
            anime_header="▸ <b>{anime}</b>\n▹ Progress: {user_count}/{total_count}\n",
            separator="▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n",
            character="  ◆ {id} | {rarity} | {name}{fav} ×{count}\n",
            footer="▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        ),
        "royal": StyleTemplate(
            name="👑 Royal",
            header="<b>{user_name}'s Royal Harem</b>\n【{page}/{total_pages}】\n\n",
            anime_header="━━ <b>{anime}</b> ━━\n👥 {user_count}/{total_count} Characters\n",
            separator="━━━━━━━━━━━━━━━\n",
            character="💎 {id} ◈ {rarity} ◈ {name}{fav} ×{count}\n",
            footer="━━━━━━━━━━━━━━━\n\n"
        )
    }
    
    OPTION_INFO: Dict[str, Dict[str, str]] = {
        "show_url": {
            "name": "🔗 Show URLs",
            "description": "Display image URLs below character info"
        },
        "preview_image": {
            "name": "🖼️ Preview Image",
            "description": "Show character image as preview"
        },
        "video_support": {
            "name": "🎥 Video Support",
            "description": "Enable AMV/video preview"
        },
        "show_rarity_full": {
            "name": "💫 Full Rarity",
            "description": "Show full rarity name"
        },
        "compact_mode": {
            "name": "📦 Compact Mode",
            "description": "Reduce spacing and separators"
        },
        "show_id_bottom": {
            "name": "🔢 ID at Bottom",
            "description": "Move character IDs to bottom"
        }
    }
    
    @classmethod
    def get_style(cls, style_key: str) -> StyleTemplate:
        return cls.STYLES.get(style_key, cls.STYLES["classic"])
    
    @classmethod
    async def get_user_style(cls, user_id: int) -> StyleTemplate:
        user = await user_collection.find_one({'id': user_id})
        if user and 'custom_style' in user:
            custom_data = user['custom_style']
            return StyleTemplate(**custom_data)
        style_key = user.get('harem_style', 'classic') if user else 'classic'
        return cls.get_style(style_key)
    
    @classmethod
    async def get_user_options(cls, user_id: int) -> DisplayOptions:
        user = await user_collection.find_one({'id': user_id})
        if user and 'harem_display_options' in user:
            return DisplayOptions.from_dict(user['harem_display_options'])
        return DisplayOptions()
    
    @classmethod
    async def set_user_style(cls, user_id: int, style_key: str) -> bool:
        if style_key not in cls.STYLES:
            return False
        await user_collection.update_one(
            {'id': user_id},
            {'$set': {'harem_style': style_key}, '$unset': {'custom_style': ''}},
            upsert=True
        )
        return True
    
    @classmethod
    async def set_custom_style(cls, user_id: int, style: StyleTemplate) -> None:
        await user_collection.update_one(
            {'id': user_id},
            {'$set': {'custom_style': asdict(style)}, '$unset': {'harem_style': ''}},
            upsert=True
        )
    
    @classmethod
    async def toggle_option(cls, user_id: int, option_key: str) -> bool:
        options = await cls.get_user_options(user_id)
        current_value = getattr(options, option_key, False)
        new_value = not current_value
        setattr(options, option_key, new_value)
        
        await user_collection.update_one(
            {'id': user_id},
            {'$set': {'harem_display_options': options.to_dict()}},
            upsert=True
        )
        return new_value
    
    @classmethod
    async def reset_user_settings(cls, user_id: int) -> None:
        await user_collection.update_one(
            {'id': user_id},
            {'$set': {
                'harem_style': 'classic',
                'harem_display_options': {}
            }, '$unset': {'custom_style': ''}},
            upsert=True
        )


class MediaFormatter:
    @staticmethod
    def add_media_preview(text: str, img_url: Optional[str], 
                         video_url: Optional[str], 
                         options: DisplayOptions) -> str:
        result = text
        
        if options.preview_image and img_url:
            result += f'<a href="{escape(img_url)}">&#8203;</a>'
        
        if options.video_support and video_url:
            result += f'<a href="{escape(video_url)}">&#8203;</a>'
        
        if options.show_url:
            if img_url:
                result += f"\n  🔗 {escape(img_url)}"
            if video_url:
                result += f"\n  🎥 {escape(video_url)}"
        
        return result


class HaremFormatter:
    @staticmethod
    async def format_page(user_id: int, user_name: str, 
                         characters: List[CharacterData], 
                         page: int, total_pages: int) -> str:
        style = await StyleManager.get_user_style(user_id)
        options = await StyleManager.get_user_options(user_id)
        
        text = style.format_header(user_name, page, total_pages)
        
        anime_groups: Dict[str, List[CharacterData]] = {}
        for char in characters:
            if char.anime not in anime_groups:
                anime_groups[char.anime] = []
            anime_groups[char.anime].append(char)
        
        for anime, chars in anime_groups.items():
            text += style.format_anime_header(
                anime, 
                len(chars), 
                chars[0].total_in_anime if chars else len(chars)
            )
            
            if not options.compact_mode:
                text += style.separator
            
            for char in chars:
                fav_marker = " [🍁]" if char.is_fav else ""
                
                char_text = style.format_character(
                    char.id, char.rarity, char.name, fav_marker, char.count
                )
                
                char_text = MediaFormatter.add_media_preview(
                    char_text, char.img_url, char.video_url, options
                )
                
                text += char_text
            
            if not options.compact_mode:
                text += style.footer
            else:
                text += "\n"
        
        return text


async def hstyle(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    
    user = await user_collection.find_one({'id': user_id})
    current_style = user.get('harem_style', 'classic') if user else 'classic'
    style_name = StyleManager.STYLES.get(current_style, StyleManager.STYLES['classic']).name
    
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
    
    text = (
        "<b>ʜᴀʀᴇᴍ sᴛʏʟᴇ sᴇᴛᴛɪɴɢs</b>\n\n"
        f"<b>📌 Current Style:</b> {style_name}\n\n"
        "<b>🎨 Choose Style</b>\n"
        "Select from preset templates\n\n"
        "<b>⚙️ Display Options</b>\n"
        "Customize display features\n\n"
        "<b>✏️ Custom Style</b>\n"
        "Create your own template\n\n"
        "<b>🔄 Reset Default</b>\n"
        "Return to classic style"
    )
    
    await update.message.reply_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


async def hstyle_select(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    keyboard = []
    row = []
    for style_key, style_data in StyleManager.STYLES.items():
        row.append(InlineKeyboardButton(
            style_data.name, 
            callback_data=f"hstyle_apply_{style_key}"
        ))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="hstyle_back")])
    
    text = (
        "<b>sᴇʟᴇᴄᴛ ʜᴀʀᴇᴍ sᴛʏʟᴇ</b>\n\n"
        "<b>Available Templates:</b>\n\n"
        "🎨 <b>Classic</b> - Traditional style\n"
        "⚡ <b>Minimal</b> - Clean & simple\n"
        "✨ <b>Elegant</b> - Sophisticated look\n"
        "🌸 <b>Cute</b> - Kawaii aesthetic\n"
        "🎯 <b>Modern</b> - Contemporary design\n"
        "👑 <b>Royal</b> - Majestic theme\n\n"
        "Select a style to preview"
    )
    
    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


async def hstyle_options(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    options = await StyleManager.get_user_options(user_id)
    
    keyboard = []
    for opt_key, opt_info in StyleManager.OPTION_INFO.items():
        is_enabled = getattr(options, opt_key, False)
        status = "✅" if is_enabled else "❌"
        keyboard.append([InlineKeyboardButton(
            f"{status} {opt_info['name']}", 
            callback_data=f"hstyle_toggle_{opt_key}"
        )])
    
    keyboard.append([InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="hstyle_back")])
    
    text = "<b>ᴅɪsᴘʟᴀʏ ᴏᴘᴛɪᴏɴs</b>\n\n<b>Customize your harem display:</b>\n\n"
    
    for opt_key, opt_info in StyleManager.OPTION_INFO.items():
        is_enabled = getattr(options, opt_key, False)
        status = "✅ Enabled" if is_enabled else "❌ Disabled"
        text += f"<b>{opt_info['name']}</b>\n"
        text += f"{opt_info['description']}\n"
        text += f"Status: {status}\n\n"
    
    text += "Tap to toggle options"
    
    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


async def hstyle_custom(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📝 Set Header", callback_data="hstyle_custom_header")],
        [InlineKeyboardButton("🎨 Set Character Format", callback_data="hstyle_custom_char")],
        [InlineKeyboardButton("📊 Set Anime Header", callback_data="hstyle_custom_anime")],
        [InlineKeyboardButton("🔧 Set Separator", callback_data="hstyle_custom_sep")],
        [InlineKeyboardButton("💾 Save Custom Style", callback_data="hstyle_custom_save")],
        [InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="hstyle_back")]
    ]
    
    text = (
        "<b>ᴄᴜsᴛᴏᴍ sᴛʏʟᴇ ᴄʀᴇᴀᴛᴏʀ</b>\n\n"
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
        "⚠️ <i>Reply to bot messages to set templates</i>\n"
        "<i>Use /cancel to stop editing</i>"
    )
    
    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


async def hstyle_preview(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    style = await StyleManager.get_user_style(user_id)
    options = await StyleManager.get_user_options(user_id)
    
    user_name = escape(query.from_user.first_name)
    preview = style.format_header(user_name, 1, 3)
    preview += style.format_anime_header("Sample Anime", 5, 10)
    
    if not options.compact_mode:
        preview += style.separator
    
    preview += style.format_character("001", "🟡", "Sample Character", " [🍁]", 2)
    
    if options.preview_image:
        preview += '<a href="https://graph.org/file/sample.jpg">&#8203;</a>'
    
    if options.show_url:
        preview += "\n  🔗 https://graph.org/file/sample.jpg"
    
    preview += style.format_character("002", "🟣", "Another Character", "", 1)
    
    if not options.compact_mode:
        preview += style.footer
    
    keyboard = [[InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="hstyle_back")]]
    
    await query.edit_message_text(
        text=f"<b>📺 PREVIEW: {style.name}</b>\n\n{preview}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML',
        disable_web_page_preview=False
    )


async def hstyle_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    if data == "hstyle_select":
        await hstyle_select(update, context)
        
    elif data == "hstyle_options":
        await hstyle_options(update, context)
        
    elif data == "hstyle_custom":
        await hstyle_custom(update, context)
        
    elif data == "hstyle_preview":
        await hstyle_preview(update, context)
        
    elif data == "hstyle_reset":
        await StyleManager.reset_user_settings(user_id)
        await query.answer("✅ Reset to default style", show_alert=True)
        await query.edit_message_text(
            text=(
                "<b>sᴛʏʟᴇ ʀᴇsᴇᴛ</b>\n\n"
                "✨ Style reset to <b>Classic</b>\n\n"
                "All display options cleared\n\n"
                "Use /harem to see changes"
            ),
            parse_mode='HTML'
        )
        
    elif data.startswith("hstyle_apply_"):
        style_key = data.replace("hstyle_apply_", "")
        success = await StyleManager.set_user_style(user_id, style_key)
        
        if success:
            style = StyleManager.get_style(style_key)
            await query.answer(f"✅ {style.name} applied!", show_alert=False)
            await query.edit_message_text(
                text=(
                    "<b>sᴛʏʟᴇ ᴀᴘᴘʟɪᴇᴅ</b>\n\n"
                    f"✨ <b>{style.name}</b>\n\n"
                    "✦ ᴀᴄᴛɪᴠᴀᴛᴇᴅ ✦\n\n"
                    "Your harem now uses\n"
                    f"the {style.name.lower()} template\n\n"
                    "Use /harem to see changes"
                ),
                parse_mode='HTML'
            )
        else:
            await query.answer("❌ Style not found", show_alert=True)
            
    elif data.startswith("hstyle_toggle_"):
        option_key = data.replace("hstyle_toggle_", "")
        new_value = await StyleManager.toggle_option(user_id, option_key)
        
        status = "enabled" if new_value else "disabled"
        opt_name = StyleManager.OPTION_INFO[option_key]['name']
        await query.answer(f"✅ {opt_name} {status}", show_alert=False)
        
        await hstyle_options(update, context)
        
    elif data == "hstyle_back":
        user = await user_collection.find_one({'id': user_id})
        current_style = user.get('harem_style', 'classic') if user else 'classic'
        style_name = StyleManager.STYLES.get(current_style, StyleManager.STYLES['classic']).name
        
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
        
        text = (
            "<b>ʜᴀʀᴇᴍ sᴛʏʟᴇ sᴇᴛᴛɪɴɢs</b>\n\n"
            f"<b>📌 Current Style:</b> {style_name}\n\n"
            "<b>🎨 Choose Style</b>\n"
            "Select from preset templates\n\n"
            "<b>⚙️ Display Options</b>\n"
            "Customize display features\n\n"
            "<b>✏️ Custom Style</b>\n"
            "Create your own template\n\n"
            "<b>🔄 Reset Default</b>\n"
            "Return to classic style"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )


application.add_handler(CommandHandler("hstyle", hstyle, block=False))
application.add_handler(CallbackQueryHandler(hstyle_callback, pattern='^hstyle_', block=False))