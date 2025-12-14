from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from html import escape
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
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
    
    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass
class DisplayOption:
    name: str
    description: str
    key: str
    default: bool = False


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


class StyleTemplates:
    CLASSIC = StyleTemplate(
        name="🎨 Classic",
        header="<b>{user_name}'s ʜᴀʀᴇᴍ - ᴘᴀɢᴇ {page}/{total_pages}</b>\n\n",
        anime_header="<b>𖤍 {anime} ｛{user_count}/{total_count}｝</b>\n",
        separator="⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋\n",
        character="<b>𒄬 {id}</b> [ {rarity} ] <b>{name}</b>{fav} ×{count}\n",
        footer="⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋⚋\n\n"
    )
    
    MINIMAL = StyleTemplate(
        name="⚡ Minimal",
        header="<b>📚 {user_name}'s Collection [{page}/{total_pages}]</b>\n\n",
        anime_header="<b>• {anime} ({user_count}/{total_count})</b>\n",
        separator="━━━━━━━━━━━━━━━\n",
        character="  {rarity} {id} • {name}{fav} ×{count}\n",
        footer="\n"
    )
    
    ELEGANT = StyleTemplate(
        name="✨ Elegant",
        header="╭─────────────────╮\n│ <b>{user_name}'s Collection</b> │\n│   Page {page} of {total_pages}   │\n╰─────────────────╯\n\n",
        anime_header="╔═ <b>{anime}</b> ═╗\n├─ {user_count}/{total_count} Characters\n",
        separator="├─────────────────\n",
        character="│ {rarity} <code>{id}</code> ► {name}{fav} ×{count}\n",
        footer="╚═════════════════\n\n"
    )
    
    CUTE = StyleTemplate(
        name="🌸 Cute",
        header="✧･ﾟ: *✧･ﾟ:* {user_name}'s Harem *:･ﾟ✧*:･ﾟ✧\n━━━ Page {page}/{total_pages} ━━━\n\n",
        anime_header="🌺 <b>{anime}</b> 🌺\n♡ {user_count}/{total_count} Characters ♡\n",
        separator="･ﾟ✧･ﾟ✧･ﾟ✧･ﾟ✧･ﾟ✧\n",
        character="  ღ {id} {rarity} {name}{fav} ×{count}\n",
        footer="･ﾟ✧･ﾟ✧･ﾟ✧･ﾟ✧･ﾟ✧\n\n"
    )
    
    MODERN = StyleTemplate(
        name="🎯 Modern",
        header="▰▰▰ {user_name}'s COLLECTION ▰▰▰\n⟨ {page}/{total_pages} ⟩\n\n",
        anime_header="▸ <b>{anime}</b>\n▹ Progress: {user_count}/{total_count}\n",
        separator="▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n",
        character="  ◆ {id} | {rarity} | {name}{fav} ×{count}\n",
        footer="▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
    )
    
    ROYAL = StyleTemplate(
        name="👑 Royal",
        header="╔══════════════════╗\n║ {user_name}'s Royal Harem ║\n║    【{page}/{total_pages}】    ║\n╚══════════════════╝\n\n",
        anime_header="┏━━ <b>{anime}</b> ━━┓\n┃ 👥 {user_count}/{total_count} Characters\n",
        separator="┣━━━━━━━━━━━━━━━\n",
        character="┃ 💎 {id} ◈ {rarity} ◈ {name}{fav} ×{count}\n",
        footer="┗━━━━━━━━━━━━━━━\n\n"
    )
    
    @classmethod
    def get_all(cls) -> Dict[str, StyleTemplate]:
        return {
            'classic': cls.CLASSIC,
            'minimal': cls.MINIMAL,
            'elegant': cls.ELEGANT,
            'cute': cls.CUTE,
            'modern': cls.MODERN,
            'royal': cls.ROYAL
        }
    
    @classmethod
    def get(cls, key: str) -> StyleTemplate:
        return cls.get_all().get(key, cls.CLASSIC)


class DisplayOptionRegistry:
    OPTIONS = [
        DisplayOption("🔗 Show URLs", "Display image URLs below character info", "show_url"),
        DisplayOption("🖼️ Preview Image", "Show character image as preview", "preview_image", True),
        DisplayOption("🎥 Video Support", "Enable AMV/video preview for characters", "video_support"),
        DisplayOption("💫 Full Rarity", "Show full rarity name instead of emoji only", "show_rarity_full"),
        DisplayOption("📦 Compact Mode", "Reduce spacing and separators", "compact_mode"),
        DisplayOption("🔢 ID at Bottom", "Move character IDs to bottom of each entry", "show_id_bottom")
    ]
    
    @classmethod
    def get_all(cls) -> Dict[str, DisplayOption]:
        return {opt.key: opt for opt in cls.OPTIONS}


class MediaFormatter:
    VIDEO_EXTENSIONS = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.gif']
    VIDEO_PATTERNS = ['/video/', '/videos/', '/amv/', '/clips/']
    
    @staticmethod
    def is_video_url(url: Optional[str]) -> bool:
        if not url:
            return False
        url_lower = url.lower()
        return (any(url_lower.endswith(ext) for ext in MediaFormatter.VIDEO_EXTENSIONS) or
                any(pattern in url_lower for pattern in MediaFormatter.VIDEO_PATTERNS))
    
    @staticmethod
    def detect_media_type(url: Optional[str]) -> MediaType:
        if not url:
            return MediaType.NONE
        return MediaType.VIDEO if MediaFormatter.is_video_url(url) else MediaType.IMAGE
    
    @staticmethod
    def create_invisible_link(url: str) -> str:
        return f'<a href="{escape(url)}">&#8203;</a>'
    
    @staticmethod
    def format_media_preview(
        character_text: str,
        char_data: CharacterData,
        options: DisplayOptions
    ) -> str:
        result = character_text
        
        if options.preview_image and char_data.img_url:
            media_type = MediaFormatter.detect_media_type(char_data.img_url)
            
            if media_type == MediaType.VIDEO and options.video_support:
                result += MediaFormatter.create_invisible_link(char_data.img_url)
            elif media_type == MediaType.IMAGE:
                result += MediaFormatter.create_invisible_link(char_data.img_url)
        
        if options.video_support and char_data.video_url:
            result += MediaFormatter.create_invisible_link(char_data.video_url)
        
        if options.show_url:
            if char_data.img_url:
                media_icon = "🎥" if MediaFormatter.is_video_url(char_data.img_url) else "🔗"
                result += f"\n  {media_icon} {escape(char_data.img_url)}"
            if char_data.video_url:
                result += f"\n  🎥 {escape(char_data.video_url)}"
        
        return result


class UserStyleManager:
    @staticmethod
    async def get_style_template(user_id: int) -> StyleTemplate:
        user = await user_collection.find_one({'id': user_id})
        if user:
            style_key = user.get('harem_style', 'classic')
            return StyleTemplates.get(style_key)
        return StyleTemplates.CLASSIC
    
    @staticmethod
    async def get_display_options(user_id: int) -> DisplayOptions:
        user = await user_collection.find_one({'id': user_id})
        if user:
            options_dict = user.get('harem_display_options', {})
            return DisplayOptions.from_dict(options_dict)
        return DisplayOptions()
    
    @staticmethod
    async def set_style(user_id: int, style_key: str) -> bool:
        if style_key not in StyleTemplates.get_all():
            return False
        await user_collection.update_one(
            {'id': user_id},
            {'$set': {'harem_style': style_key}},
            upsert=True
        )
        return True
    
    @staticmethod
    async def toggle_option(user_id: int, option_key: str) -> bool:
        user = await user_collection.find_one({'id': user_id})
        options = user.get('harem_display_options', {}) if user else {}
        options[option_key] = not options.get(option_key, False)
        await user_collection.update_one(
            {'id': user_id},
            {'$set': {'harem_display_options': options}},
            upsert=True
        )
        return options[option_key]
    
    @staticmethod
    async def reset_style(user_id: int) -> None:
        await user_collection.update_one(
            {'id': user_id},
            {'$set': {'harem_style': 'classic', 'harem_display_options': {}}},
            upsert=True
        )


class HaremFormatter:
    @staticmethod
    def format_character(
        char: CharacterData,
        style: StyleTemplate,
        options: DisplayOptions
    ) -> str:
        fav_marker = " [🍁]" if char.is_fav else ""
        
        char_text = style.character.format(
            id=char.id,
            rarity=char.rarity,
            name=escape(char.name),
            fav=fav_marker,
            count=char.count
        )
        
        return MediaFormatter.format_media_preview(char_text, char, options)
    
    @staticmethod
    async def format_page(
        user_id: int,
        user_name: str,
        characters: List[CharacterData],
        page: int,
        total_pages: int
    ) -> str:
        style = await UserStyleManager.get_style_template(user_id)
        options = await UserStyleManager.get_display_options(user_id)
        
        text = style.header.format(
            user_name=escape(user_name),
            page=page,
            total_pages=total_pages
        )
        
        anime_groups = {}
        for char in characters:
            if char.anime not in anime_groups:
                anime_groups[char.anime] = []
            anime_groups[char.anime].append(char)
        
        for anime, chars in anime_groups.items():
            text += style.anime_header.format(
                anime=escape(anime),
                user_count=len(chars),
                total_count=chars[0].total_in_anime if chars else len(chars)
            )
            
            if not options.compact_mode:
                text += style.separator
            
            for char in chars:
                text += HaremFormatter.format_character(char, style, options)
            
            text += style.footer
        
        return text


class KeyboardBuilder:
    @staticmethod
    def main_menu(current_style: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎨 Choose Style", callback_data="hstyle_select"),
                InlineKeyboardButton("⚙️ Display Options", callback_data="hstyle_options")
            ],
            [
                InlineKeyboardButton("✏️ Custom Style", callback_data="hstyle_custom"),
                InlineKeyboardButton("🔄 Reset Default", callback_data="hstyle_reset")
            ],
            [InlineKeyboardButton("👁️ Preview Current", callback_data="hstyle_preview")]
        ])
    
    @staticmethod
    def style_selection() -> InlineKeyboardMarkup:
        keyboard = []
        row = []
        for style_key, style_data in StyleTemplates.get_all().items():
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
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def display_options(enabled_options: Dict[str, bool]) -> InlineKeyboardMarkup:
        keyboard = []
        for opt_key, opt_data in DisplayOptionRegistry.get_all().items():
            is_enabled = enabled_options.get(opt_key, opt_data.default)
            status = "✅" if is_enabled else "❌"
            keyboard.append([InlineKeyboardButton(
                f"{status} {opt_data.name}",
                callback_data=f"hstyle_toggle_{opt_key}"
            )])
        keyboard.append([InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="hstyle_back")])
        return InlineKeyboardMarkup(keyboard)


class MessageBuilder:
    @staticmethod
    def main_menu(style_name: str) -> str:
        return (
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
    
    @staticmethod
    def style_selection() -> str:
        return (
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
    
    @staticmethod
    def display_options(options: Dict[str, bool]) -> str:
        text = (
            "╭─────────────────────╮\n"
            "│ <b>ᴅɪsᴘʟᴀʏ ᴏᴘᴛɪᴏɴs</b> │\n"
            "╰─────────────────────╯\n\n"
            "<b>Customize your harem display:</b>\n\n"
        )
        
        for opt_key, opt_data in DisplayOptionRegistry.get_all().items():
            is_enabled = options.get(opt_key, opt_data.default)
            status = "✅ Enabled" if is_enabled else "❌ Disabled"
            text += f"<b>{opt_data.name}</b>\n"
            text += f"  {opt_data.description}\n"
            text += f"  Status: {status}\n\n"
        
        text += "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\nTap to toggle options"
        return text


async def hstyle_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    style = await UserStyleManager.get_style_template(user_id)
    
    await update.message.reply_text(
        text=MessageBuilder.main_menu(style.name),
        reply_markup=KeyboardBuilder.main_menu(style.name),
        parse_mode='HTML'
    )


async def hstyle_callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    handlers = {
        "hstyle_select": handle_select,
        "hstyle_options": handle_options,
        "hstyle_custom": handle_custom,
        "hstyle_preview": handle_preview,
        "hstyle_reset": handle_reset,
        "hstyle_back": handle_back
    }
    
    if data.startswith("hstyle_apply_"):
        await handle_apply(query, user_id, data)
    elif data.startswith("hstyle_toggle_"):
        await handle_toggle(query, user_id, data)
    else:
        handler = handlers.get(data)
        if handler:
            await handler(query, user_id)


async def handle_select(query, user_id):
    await query.answer()
    await query.edit_message_text(
        text=MessageBuilder.style_selection(),
        reply_markup=KeyboardBuilder.style_selection(),
        parse_mode='HTML'
    )


async def handle_options(query, user_id):
    await query.answer()
    options = await UserStyleManager.get_display_options(user_id)
    await query.edit_message_text(
        text=MessageBuilder.display_options(options.to_dict()),
        reply_markup=KeyboardBuilder.display_options(options.to_dict()),
        parse_mode='HTML'
    )


async def handle_custom(query, user_id):
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📝 Set Custom Header", callback_data="hstyle_custom_header")],
        [InlineKeyboardButton("🎨 Set Character Format", callback_data="hstyle_custom_char")],
        [InlineKeyboardButton("📊 Set Anime Header", callback_data="hstyle_custom_anime")],
        [InlineKeyboardButton("💾 Save Custom Style", callback_data="hstyle_custom_save")],
        [InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="hstyle_back")]
    ]
    
    await query.edit_message_text(
        text=(
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
            "⚠️ <i>Custom styles coming soon!</i>\n"
            "<i>For now, use preset templates</i>"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


async def handle_preview(query, user_id):
    await query.answer()
    style = await UserStyleManager.get_style_template(user_id)
    options = await UserStyleManager.get_display_options(user_id)
    
    sample_chars = [
        CharacterData("001", "Sample Character", "🟡", "Sample Anime", 2, True, 
                     "https://graph.org/file/sample-image.jpg", None, 10),
        CharacterData("002", "Another Character", "🟣", "Sample Anime", 1, False,
                     None, "https://telegra.ph/file/sample-video.mp4", 10)
    ]
    
    preview = await HaremFormatter.format_page(
        user_id,
        query.from_user.first_name,
        sample_chars,
        1,
        3
    )
    
    await query.edit_message_text(
        text=f"<b>📺 PREVIEW: {style.name}</b>\n\n{preview}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="hstyle_back")
        ]]),
        parse_mode='HTML',
        disable_web_page_preview=False
    )


async def handle_reset(query, user_id):
    await UserStyleManager.reset_style(user_id)
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


async def handle_back(query, user_id):
    style = await UserStyleManager.get_style_template(user_id)
    await query.edit_message_text(
        text=MessageBuilder.main_menu(style.name),
        reply_markup=KeyboardBuilder.main_menu(style.name),
        parse_mode='HTML'
    )


async def handle_apply(query, user_id, data):
    style_key = data.replace("hstyle_apply_", "")
    success = await UserStyleManager.set_style(user_id, style_key)
    
    if success:
        style = StyleTemplates.get(style_key)
        await query.answer(f"✅ {style.name} applied!", show_alert=False)
        await query.edit_message_text(
            text=(
                "╭─────────────────────╮\n"
                "│  <b>sᴛʏʟᴇ ᴀᴘᴘʟɪᴇᴅ</b>  │\n"
                "╰─────────────────────╯\n\n"
                f"✨ <b>{style.name}</b>\n\n"
                "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
                "   ✦ ᴀᴄᴛɪᴠᴀᴛᴇᴅ ✦\n\n"
                "Your harem now uses\n"
                f"the {style.name.lower()} template\n\n"
                "Use /harem to see changes"
            ),
            parse_mode='HTML'
        )
    else:
        await query.answer("❌ Style not found", show_alert=True)


async def handle_toggle(query, user_id, data):
    option_key = data.replace("hstyle_toggle_", "")
    new_state = await UserStyleManager.toggle_option(user_id, option_key)
    
    opt_data = DisplayOptionRegistry.get_all().get(option_key)
    if opt_data:
        status = "enabled" if new_state else "disabled"
        await query.answer(f"✅ {opt_data.name} {status}", show_alert=False)
        await handle_options(query, user_id)


async def get_user_style_template(user_id: int) -> StyleTemplate:
    return await UserStyleManager.get_style_template(user_id)


async def get_user_display_options(user_id: int) -> Dict[str, bool]:
    options = await UserStyleManager.get_display_options(user_id)
    return options.to_dict()


async def format_harem_page(
    user_id: int,
    user_name: str,
    characters_data: List[Dict[str, Any]],
    page: int,
    total_pages: int
) -> str:
    characters = [CharacterData(**char) for char in characters_data]
    return await HaremFormatter.format_page(user_id, user_name, characters, page, total_pages)


application.add_handler(CommandHandler("hstyle", hstyle_command, block=False))
application.add_handler(CallbackQueryHandler(hstyle_callback_handler, pattern='^hstyle_', block=False))