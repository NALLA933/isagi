from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from html import escape
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
import random
import math
from shivu import db, application
from hstyle import get_user_style_template, get_user_display_options


class RarityType(Enum):
    COMMON = ("common", "🟢 Common")
    RARE = ("rare", "🟣 Rare")
    LEGENDARY = ("legendary", "🟡 Legendary")
    SPECIAL = ("special", "💮 Special Edition")
    NEON = ("neon", "💫 Neon")
    MANGA = ("manga", "✨ Manga")
    COSPLAY = ("cosplay", "🎭 Cosplay")
    CELESTIAL = ("celestial", "🎐 Celestial")
    PREMIUM = ("premium", "🔮 Premium Edition")
    EROTIC = ("erotic", "💋 Erotic")
    SUMMER = ("summer", "🌤 Summer")
    WINTER = ("winter", "☃️ Winter")
    MONSOON = ("monsoon", "☔️ Monsoon")
    VALENTINE = ("valentine", "💝 Valentine")
    HALLOWEEN = ("halloween", "🎃 Halloween")
    CHRISTMAS = ("christmas", "🎄 Christmas")
    MYTHIC = ("mythic", "🏵 Mythic")
    EVENTS = ("events", "🎗 Special Events")
    AMV = ("amv", "🎥 AMV")
    TINY = ("tiny", "👼 Tiny")
    DEFAULT = ("default", None)

    @classmethod
    def get_display(cls, key: str) -> Optional[str]:
        for rarity in cls:
            if rarity.value[0] == key:
                return rarity.value[1]
        return None

    @classmethod
    def get_emoji(cls, display: str) -> str:
        if not display or not isinstance(display, str):
            return "🟢"
        return display.split(' ')[0]

    @classmethod
    def get_name(cls, display: str) -> str:
        if not display or not isinstance(display, str):
            return "common"
        return ' '.join(display.split(' ')[1:])


@dataclass
class Character:
    id: str
    name: str
    anime: str
    rarity: str
    img_url: Optional[str] = None
    is_video: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional['Character']:
        if not isinstance(data, dict):
            return None
        return cls(
            id=data.get('id', ''),
            name=data.get('name', 'Unknown'),
            anime=data.get('anime', 'Unknown'),
            rarity=data.get('rarity', '🟢 Common'),
            img_url=data.get('img_url'),
            is_video=data.get('is_video', False)
        )


@dataclass
class DisplayOptions:
    show_url: bool = False
    video_support: bool = True
    preview_image: bool = True
    show_rarity_full: bool = False
    compact_mode: bool = False
    show_id_bottom: bool = False


@dataclass
class UserCollection:
    user_id: int
    characters: List[Character] = field(default_factory=list)
    favorite: Optional[Character] = None
    filter_mode: str = "default"

    def get_filtered_characters(self) -> List[Character]:
        if self.filter_mode == "default":
            return self.characters
        
        rarity_value = RarityType.get_display(self.filter_mode)
        if not rarity_value:
            return self.characters
        
        return [char for char in self.characters if char.rarity == rarity_value]

    def count_by_id(self, characters: List[Character]) -> Dict[str, int]:
        counts = {}
        for char in characters:
            counts[char.id] = counts.get(char.id, 0) + 1
        return counts

    def group_by_anime(self, characters: List[Character]) -> Dict[str, List[Character]]:
        grouped = {}
        for char in characters:
            if char.anime not in grouped:
                grouped[char.anime] = []
            grouped[char.anime].append(char)
        return grouped


class MediaHelper:
    VIDEO_EXTENSIONS = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v']
    VIDEO_PATTERNS = ['/video/', '/videos/', 'video=', 'v=', '.mp4?', '/stream/']

    @staticmethod
    def is_video_url(url: str) -> bool:
        if not url:
            return False
        url_lower = url.lower()
        return (any(url_lower.endswith(ext) for ext in MediaHelper.VIDEO_EXTENSIONS) or
                any(pattern in url_lower for pattern in MediaHelper.VIDEO_PATTERNS))

    @staticmethod
    async def send_media_message(message, media_url: str, caption: str, 
                                 reply_markup, is_video: bool = False, 
                                 display_options: Optional[DisplayOptions] = None):
        if display_options is None:
            display_options = DisplayOptions()

        if display_options.show_url and media_url:
            caption += f"\n\n🔗 <code>{media_url}</code>"

        if not display_options.video_support:
            is_video = False
        elif not is_video:
            is_video = MediaHelper.is_video_url(media_url)

        if not display_options.preview_image:
            return await message.reply_text(
                text=caption,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

        try:
            if is_video:
                try:
                    return await message.reply_video(
                        video=media_url,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode='HTML',
                        supports_streaming=True,
                        read_timeout=120,
                        write_timeout=120
                    )
                except:
                    return await message.reply_photo(
                        photo=media_url,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
            else:
                return await message.reply_photo(
                    photo=media_url,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
        except:
            return await message.reply_text(
                text=caption,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )


class HaremMessageBuilder:
    def __init__(self, user_collection: UserCollection, page: int, total_pages: int,
                 style_template: Dict, display_options: DisplayOptions, user_name: str):
        self.collection = user_collection
        self.page = page
        self.total_pages = total_pages
        self.style = style_template
        self.options = display_options
        self.user_name = user_name

    def build_message(self, characters: List[Character], anime_counts: Dict[str, int]) -> str:
        message = self.style['header'].format(
            user_name=escape(self.user_name),
            page=self.page + 1,
            total_pages=self.total_pages
        )

        grouped = self.collection.group_by_anime(characters)
        character_counts = self.collection.count_by_id(self.collection.characters)
        included = set()

        for anime, chars in grouped.items():
            user_anime_count = len([c for c in self.collection.characters if c.anime == anime])
            total_anime_count = anime_counts.get(anime, 0)

            message += self.style['anime_header'].format(
                anime=escape(anime),
                user_count=user_anime_count,
                total_count=total_anime_count
            )

            if not self.options.compact_mode:
                message += self.style['separator']

            for char in chars:
                if char.id not in included:
                    message += self._format_character(char, character_counts.get(char.id, 1))
                    included.add(char.id)

            if not self.options.compact_mode:
                message += self.style['footer']
            else:
                message += '\n'

        return message

    def _format_character(self, char: Character, count: int) -> str:
        rarity_display = (char.rarity if self.options.show_rarity_full 
                         else RarityType.get_emoji(char.rarity))
        
        fav_marker = ""
        if self.collection.favorite and char.id == self.collection.favorite.id:
            fav_marker = " [🍁]"

        if self.options.show_id_bottom:
            char_line = self.style['character'].replace('{id}', '').format(
                id='',
                rarity=rarity_display,
                name=escape(char.name),
                fav=fav_marker,
                count=count
            )
            char_line += f"    └─ ID: <code>{char.id}</code>\n"
        else:
            char_line = self.style['character'].format(
                id=char.id,
                rarity=rarity_display,
                name=escape(char.name),
                fav=fav_marker,
                count=count
            )
        return char_line


class HaremHandler:
    CHARACTERS_PER_PAGE = 10

    def __init__(self):
        self.collection_db = db['anime_characters_lol']
        self.user_db = db['user_collection_lmaoooo']

    async def load_user_collection(self, user_id: int) -> Optional[UserCollection]:
        user = await self.user_db.find_one({'id': user_id})
        if not user:
            return None

        characters = [Character.from_dict(c) for c in user.get('characters', [])
                     if Character.from_dict(c)]
        
        favorite_data = user.get('favorites')
        favorite = Character.from_dict(favorite_data) if favorite_data else None

        if favorite:
            still_owns = any(c.id == favorite.id for c in characters)
            if not still_owns:
                await self.user_db.update_one(
                    {'id': user_id},
                    {'$unset': {'favorites': ""}}
                )
                favorite = None

        return UserCollection(
            user_id=user_id,
            characters=characters,
            favorite=favorite,
            filter_mode=user.get('smode', 'default')
        )

    async def get_anime_counts(self, anime_list: List[str]) -> Dict[str, int]:
        counts = {}
        for anime in anime_list:
            counts[anime] = await self.collection_db.count_documents({"anime": anime})
        return counts

    async def show_harem(self, update: Update, context: CallbackContext, 
                        page: int = 0, edit: bool = False):
        user_id = update.effective_user.id
        message = update.message or update.callback_query.message

        collection = await self.load_user_collection(user_id)
        if not collection:
            await message.reply_text("⚠️ You need to grab a character first using /grab command!")
            return

        if not collection.characters:
            await message.reply_text("📭 You don't have any characters yet! Use /grab to catch some.")
            return

        filtered_chars = collection.get_filtered_characters()
        if not filtered_chars:
            rarity_name = RarityType.get_display(collection.filter_mode) or "Unknown"
            await message.reply_text(
                f"❌ You don't have any characters with rarity: {rarity_name}\n"
                f"💡 Change mode using /smode"
            )
            return

        filtered_chars.sort(key=lambda x: (x.anime, x.id))
        total_pages = math.ceil(len(filtered_chars) / self.CHARACTERS_PER_PAGE)
        
        if page < 0 or page >= total_pages:
            page = 0

        start_idx = page * self.CHARACTERS_PER_PAGE
        end_idx = start_idx + self.CHARACTERS_PER_PAGE
        current_chars = filtered_chars[start_idx:end_idx]

        style_template = await get_user_style_template(user_id)
        display_options_dict = await get_user_display_options(user_id)
        display_options = DisplayOptions(**display_options_dict) if display_options_dict else DisplayOptions()

        anime_list = list(set(char.anime for char in current_chars))
        anime_counts = await self.get_anime_counts(anime_list)

        builder = HaremMessageBuilder(
            collection, page, total_pages, style_template,
            display_options, update.effective_user.first_name
        )
        harem_message = builder.build_message(current_chars, anime_counts)

        keyboard = [
            [InlineKeyboardButton(
                f"🎭 View All ({len(filtered_chars)})",
                switch_inline_query_current_chat=f"collection.{user_id}"
            )]
        ]

        if total_pages > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(
                    "⬅️ Prev", callback_data=f"harem_page:{page - 1}:{user_id}"
                ))
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(
                    "Next ➡️", callback_data=f"harem_page:{page + 1}:{user_id}"
                ))
            if nav_buttons:
                keyboard.append(nav_buttons)

        reply_markup = InlineKeyboardMarkup(keyboard)

        display_media = None
        is_video_display = False

        if collection.favorite and collection.favorite.img_url:
            display_media = collection.favorite.img_url
            is_video_display = collection.favorite.is_video or MediaHelper.is_video_url(display_media)
        elif filtered_chars:
            random_char = random.choice(filtered_chars)
            display_media = random_char.img_url
            is_video_display = random_char.is_video or MediaHelper.is_video_url(display_media)

        if display_media:
            if edit:
                try:
                    await message.edit_caption(
                        caption=harem_message,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                except:
                    await MediaHelper.send_media_message(
                        message, display_media, harem_message, reply_markup,
                        is_video_display, display_options
                    )
            else:
                await MediaHelper.send_media_message(
                    message, display_media, harem_message, reply_markup,
                    is_video_display, display_options
                )
        else:
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


class ModeHandler:
    def __init__(self):
        self.user_db = db['user_collection_lmaoooo']

    async def show_mode_menu(self, update: Update):
        keyboard = [
            [
                InlineKeyboardButton("ᴅᴇғᴀᴜʟᴛ", callback_data="harem_mode_default"),
                InlineKeyboardButton("ʀᴀʀɪᴛʏ ғɪʟᴛᴇʀ", callback_data="harem_mode_rarity"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message_text = (
            "╭─────────────────╮\n"
            "│  <b>ᴄᴏʟʟᴇᴄᴛɪᴏɴ ᴍᴏᴅᴇ</b>  │\n"
            "╰─────────────────╯\n\n"
            "◆ <b>ᴅᴇғᴀᴜʟᴛ</b>\n"
            "  sʜᴏᴡ ᴀʟʟ ᴄʜᴀʀᴀᴄᴛᴇʀs\n\n"
            "◆ <b>ʀᴀʀɪᴛʏ ғɪʟᴛᴇʀ</b>\n"
            "  ғɪʟᴛᴇʀ ʙʏ sᴘᴇᴄɪғɪᴄ ᴛɪᴇʀ\n\n"
            "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
            "💡 <i>Use /hstyle to change visual style</i>"
        )

        await update.message.reply_text(
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    async def show_rarity_menu(self, query):
        keyboard = [
            [
                InlineKeyboardButton("🟢", callback_data="harem_mode_common"),
                InlineKeyboardButton("🟣", callback_data="harem_mode_rare"),
                InlineKeyboardButton("🟡", callback_data="harem_mode_legendary"),
            ],
            [
                InlineKeyboardButton("💮", callback_data="harem_mode_special"),
                InlineKeyboardButton("💫", callback_data="harem_mode_neon"),
                InlineKeyboardButton("✨", callback_data="harem_mode_manga"),
            ],
            [
                InlineKeyboardButton("🎭", callback_data="harem_mode_cosplay"),
                InlineKeyboardButton("🎐", callback_data="harem_mode_celestial"),
                InlineKeyboardButton("🔮", callback_data="harem_mode_premium"),
            ],
            [
                InlineKeyboardButton("💋", callback_data="harem_mode_erotic"),
                InlineKeyboardButton("🌤", callback_data="harem_mode_summer"),
                InlineKeyboardButton("☃️", callback_data="harem_mode_winter"),
            ],
            [
                InlineKeyboardButton("☔️", callback_data="harem_mode_monsoon"),
                InlineKeyboardButton("💝", callback_data="harem_mode_valentine"),
                InlineKeyboardButton("🎃", callback_data="harem_mode_halloween"),
            ],
            [
                InlineKeyboardButton("🎄", callback_data="harem_mode_christmas"),
                InlineKeyboardButton("🏵", callback_data="harem_mode_mythic"),
                InlineKeyboardButton("🎗", callback_data="harem_mode_events"),
            ],
            [
                InlineKeyboardButton("🎥", callback_data="harem_mode_amv"),
                InlineKeyboardButton("👼", callback_data="harem_mode_tiny"),
            ],
            [
                InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data="harem_mode_back"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message_text = (
            "╭─────────────────╮\n"
            "│ <b>ʀᴀʀɪᴛʏ ғɪʟᴛᴇʀ</b>  │\n"
            "╰─────────────────╯\n\n"
            "     ◇ sᴇʟᴇᴄᴛ ᴛɪᴇʀ ◇\n\n"
            "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
            "ᴄʜᴏᴏsᴇ ᴀ ʀᴀʀɪᴛʏ ᴇᴍᴏᴊɪ\n"
            "ᴛᴏ ғɪʟᴛᴇʀ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ"
        )

        await query.edit_message_text(
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    async def set_mode(self, user_id: int, mode: str):
        await self.user_db.update_one(
            {'id': user_id},
            {'$set': {'smode': mode}},
            upsert=True
        )

    async def handle_mode_callback(self, update: Update, context: CallbackContext):
        query = update.callback_query
        user_id = query.from_user.id
        data = query.data

        if data == "harem_mode_default":
            await self.set_mode(user_id, 'default')
            await query.answer("✓ ᴍᴏᴅᴇ sᴇᴛ ᴛᴏ ᴅᴇғᴀᴜʟᴛ", show_alert=False)

            success_text = (
                "╭─────────────────╮\n"
                "│   <b>ᴍᴏᴅᴇ ᴜᴘᴅᴀᴛᴇᴅ</b>   │\n"
                "╰─────────────────╯\n\n"
                "◆ <b>ᴄᴜʀʀᴇɴᴛ ғɪʟᴛᴇʀ</b>\n"
                "  ᴀʟʟ ᴄʜᴀʀᴀᴄᴛᴇʀs\n\n"
                "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
                "   ✦ ᴀᴄᴛɪᴠᴀᴛᴇᴅ ✦\n\n"
                "sʜᴏᴡɪɴɢ ʏᴏᴜʀ ᴄᴏᴍᴘʟᴇᴛᴇ\n"
                "ᴄʜᴀʀᴀᴄᴛᴇʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ"
            )
            await query.edit_message_text(text=success_text, parse_mode='HTML')

        elif data == "harem_mode_rarity":
            await self.show_rarity_menu(query)
            await query.answer()

        elif data == "harem_mode_back":
            await self.show_mode_menu(update)
            await query.answer()

        elif data.startswith("harem_mode_"):
            mode_name = data.replace("harem_mode_", "")
            rarity_display = RarityType.get_display(mode_name)

            if not rarity_display:
                await query.answer("❌ ɪɴᴠᴀʟɪᴅ ʀᴀʀɪᴛʏ", show_alert=True)
                return

            rarity_emoji = RarityType.get_emoji(rarity_display)
            rarity_name = RarityType.get_name(rarity_display)

            await self.set_mode(user_id, mode_name)
            await query.answer(f"✓ {rarity_name} ғɪʟᴛᴇʀ ᴀᴄᴛɪᴠᴀᴛᴇᴅ", show_alert=False)

            success_text = (
                "╭─────────────────╮\n"
                "│  <b>ғɪʟᴛᴇʀ ᴀᴘᴘʟɪᴇᴅ</b>  │\n"
                "╰─────────────────╯\n\n"
                f"      {rarity_emoji}\n\n"
                f"◆ <b>{rarity_name}</b>\n\n"
                "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
                "   ✦ ᴀᴄᴛɪᴠᴀᴛᴇᴅ ✦\n\n"
                f"ᴅɪsᴘʟᴀʏɪɴɢ ᴏɴʟʏ\n"
                f"{rarity_name.lower()} ᴄʜᴀʀᴀᴄᴛᴇʀs"
            )
            await query.edit_message_text(text=success_text, parse_mode='HTML')


class UnfavHandler:
    def __init__(self):
        self.user_db = db['user_collection_lmaoooo']

    async def show_unfav_prompt(self, update: Update):
        user_id = update.effective_user.id
        user = await self.user_db.find_one({'id': user_id})

        if not user:
            await update.message.reply_text('⚠️ 𝙔𝙤𝙪 𝙝𝙖𝙫𝙚 𝙣𝙤𝙩 𝙂𝙤𝙩 𝘼𝙣𝙮 𝙒𝘼𝙄𝙁𝙐 𝙮𝙚𝙩...')
            return

        fav_data = user.get('favorites')
        if not fav_data or not isinstance(fav_data, dict):
            await update.message.reply_text('💔 𝙔𝙤𝙪 𝙙𝙤𝙣\'𝙩 𝙝𝙖𝙫𝙚 𝙖 𝙛𝙖𝙫𝙤𝙧𝙞𝙩𝙚 𝙘𝙝𝙖𝙧𝙖𝙘𝙩𝙚𝙧 𝙨𝙚𝙩!')
            return

        fav_character = Character.from_dict(fav_data)
        buttons = [
            [
                InlineKeyboardButton("✅ ʏᴇs", callback_data=f"harem_unfav_yes:{user_id}"),
                InlineKeyboardButton("❌ ɴᴏ", callback_data=f"harem_unfav_no:{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        display_options_dict = await get_user_display_options(user_id)
        display_options = DisplayOptions(**display_options_dict) if display_options_dict else DisplayOptions()

        caption = (
            f"<b>💔 ᴅᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ʀᴇᴍᴏᴠᴇ ᴛʜɪs ғᴀᴠᴏʀɪᴛᴇ?</b>\n\n"
            f"✨ <b>ɴᴀᴍᴇ:</b> <code>{escape(fav_character.name)}</code>\n"
            f"📺 <b>ᴀɴɪᴍᴇ:</b> <code>{escape(fav_character.anime)}</code>\n"
            f"🆔 <b>ɪᴅ:</b> <code>{fav_character.id}</code>"
        )

        is_video = fav_character.is_video or MediaHelper.is_video_url(fav_character.img_url)
        await MediaHelper.send_media_message(
            update.message, fav_character.img_url, caption,
            reply_markup, is_video, display_options
        )

    async def handle_unfav_callback(self, update: Update):
        query = update.callback_query
        data = query.data

        if ':' not in data:
            await query.answer("❌ ɪɴᴠᴀʟɪᴅ ᴄᴀʟʟʙᴀᴄᴋ ᴅᴀᴛᴀ!", show_alert=True)
            return

        parts = data.split(':', 1)
        if len(parts) != 2:
            await query.answer("❌ ɪɴᴠᴀʟɪᴅ ᴄᴀʟʟʙᴀᴄᴋ ᴅᴀᴛᴀ!", show_alert=True)
            return

        action, user_id_str = parts

        try:
            user_id = int(user_id_str)
        except ValueError:
            await query.answer("❌ ɪɴᴠᴀʟɪᴅ ᴜsᴇʀ ɪᴅ!", show_alert=True)
            return

        if query.from_user.id != user_id:
            await query.answer("⚠️ ᴛʜɪs ɪs ɴᴏᴛ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ!", show_alert=True)
            return

        await query.answer()

        if action == 'harem_unfav_yes':
            user = await self.user_db.find_one({'id': user_id})
            if not user:
                await query.answer("❌ ᴜsᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ!", show_alert=True)
                return

            fav_data = user.get('favorites')
            if not fav_data:
                await query.answer("❌ ɴᴏ ғᴀᴠᴏʀɪᴛᴇ ғᴏᴜɴᴅ!", show_alert=True)
                return

            fav_character = Character.from_dict(fav_data)
            result = await self.user_db.update_one(
                {'id': user_id},
                {'$unset': {'favorites': ""}}
            )

            if result.matched_count == 0:
                await query.answer("❌ ғᴀɪʟᴇᴅ ᴛᴏ ᴜᴘᴅᴀᴛᴇ!", show_alert=True)
                return

            await query.edit_message_caption(
                caption=(
                    f"<b>💔 ғᴀᴠᴏʀɪᴛᴇ ʀᴇᴍᴏᴠᴇᴅ!</b>\n\n"
                    f"✨ <b>ɴᴀᴍᴇ:</b> <code>{escape(fav_character.name)}</code>\n"
                    f"📺 <b>ᴀɴɪᴍᴇ:</b> <code>{escape(fav_character.anime)}</code>\n\n"
                    f"<i>💖 ʏᴏᴜ ᴄᴀɴ sᴇᴛ ᴀ ɴᴇᴡ ғᴀᴠᴏʀɪᴛᴇ ᴜsɪɴɢ /fav</i>"
                ),
                parse_mode='HTML'
            )

        elif action == 'harem_unfav_no':
            await query.edit_message_caption(
                caption="❌ ᴀᴄᴛɪᴏɴ ᴄᴀɴᴄᴇʟᴇᴅ. ғᴀᴠᴏʀɪᴛᴇ ᴋᴇᴘᴛ.",
                parse_mode='HTML'
            )


harem_handler = HaremHandler()
mode_handler = ModeHandler()
unfav_handler = UnfavHandler()


async def harem_command(update: Update, context: CallbackContext):
    await harem_handler.show_harem(update, context)


async def harem_page_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    parts = data.split(':')

    if len(parts) != 3:
        await query.answer("❌ Invalid callback data!", show_alert=True)
        return

    try:
        _, page_str, user_id_str = parts
        page = int(page_str)
        user_id = int(user_id_str)
    except ValueError:
        await query.answer("❌ Invalid page or user ID!", show_alert=True)
        return

    if query.from_user.id != user_id:
        await query.answer("⚠️ This is not your collection!", show_alert=True)
        return

    await query.answer()
    await harem_handler.show_harem(update, context, page, edit=True)


async def smode_command(update: Update, context: CallbackContext):
    await mode_handler.show_mode_menu(update)


async def mode_callback(update: Update, context: CallbackContext):
    await mode_handler.handle_mode_callback(update, context)


async def unfav_command(update: Update, context: CallbackContext):
    await unfav_handler.show_unfav_prompt(update)


async def unfav_callback(update: Update, context: CallbackContext):
    await unfav_handler.handle_unfav_callback(update)


application.add_handler(CommandHandler(["harem", "collection"], harem_command, block=False))
application.add_handler(CommandHandler("smode", smode_command, block=False))
application.add_handler(CommandHandler("unfav", unfav_command, block=False))
application.add_handler(CallbackQueryHandler(harem_page_callback, pattern='^harem_page:', block=False))
application.add_handler(CallbackQueryHandler(mode_callback, pattern='^harem_mode_', block=False))
application.add_handler(CallbackQueryHandler(unfav_callback, pattern="^harem_unfav_", block=False))