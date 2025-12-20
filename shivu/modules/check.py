from html import escape
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from cachetools import TTLCache

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

from shivu import application, collection, user_collection

character_cache = TTLCache(maxsize=2000, ttl=600)
anime_cache = TTLCache(maxsize=1000, ttl=900)
user_cache = TTLCache(maxsize=500, ttl=300)

USERS_PER_PAGE = 10
CHARACTERS_PER_PAGE = 15
MAX_RESULTS_DISPLAY = 1000


@dataclass
class CharacterData:
    id: str
    name: str
    anime: str
    rarity: str
    img_url: str
    is_video: bool = False
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'CharacterData':
        return cls(
            id=data.get('id', 'Unknown'),
            name=data.get('name', 'Unknown'),
            anime=data.get('anime', 'Unknown'),
            rarity=data.get('rarity', '🟢 Common'),
            img_url=data.get('img_url', ''),
            is_video=data.get('is_video', False)
        )


@dataclass
class UserOwnership:
    id: int
    first_name: str
    username: Optional[str]
    count: int
    
    @classmethod
    def from_dict(cls, data: Dict, char_id: str) -> 'UserOwnership':
        count = sum(1 for c in data.get('characters', []) if c.get('id') == char_id)
        return cls(
            id=data.get('id'),
            first_name=data.get('first_name', 'Unknown'),
            username=data.get('username'),
            count=count
        )


@dataclass
class RarityInfo:
    emoji: str
    text: str
    
    @staticmethod
    def parse(rarity: str | int) -> 'RarityInfo':
        if isinstance(rarity, str):
            parts = rarity.split(' ', 1)
            return RarityInfo(
                emoji=parts[0] if parts else '🟢',
                text=parts[1] if len(parts) > 1 else 'Common'
            )
        return RarityInfo(emoji='🟢', text='Common')


@dataclass
class SearchResult:
    characters: List[Dict]
    unique_count: int
    total_count: int
    name_counts: Dict[str, int]
    char_data: Dict[str, Dict]
    rarity_breakdown: Dict[str, int] = field(default_factory=dict)


class CharacterRepository:
    @staticmethod
    async def get_by_id(character_id: str) -> Optional[CharacterData]:
        cache_key = f"char_{character_id}"
        if cache_key in character_cache:
            return character_cache[cache_key]
        
        data = await collection.find_one({'id': character_id})
        if data:
            char = CharacterData.from_dict(data)
            character_cache[cache_key] = char
            return char
        return None
    
    @staticmethod
    async def find_by_name(name: str) -> List[Dict]:
        cache_key = f"name_{name.lower()}"
        if cache_key in character_cache:
            return character_cache[cache_key]
        
        results = await collection.find({
            'name': {'$regex': name, '$options': 'i'}
        }).to_list(length=None)
        
        if results:
            character_cache[cache_key] = results
        return results
    
    @staticmethod
    async def find_by_anime(anime: str) -> List[Dict]:
        cache_key = f"anime_{anime.lower()}"
        if cache_key in anime_cache:
            return anime_cache[cache_key]
        
        results = await collection.find({
            'anime': {'$regex': anime, '$options': 'i'}
        }).to_list(length=None)
        
        if results:
            anime_cache[cache_key] = results
        return results
    
    @staticmethod
    async def get_global_count(character_id: str) -> int:
        cache_key = f"count_{character_id}"
        if cache_key in user_cache:
            return user_cache[cache_key]
        
        try:
            count = await user_collection.count_documents({
                'characters.id': character_id
            })
            user_cache[cache_key] = count
            return count
        except:
            return 0


class UserRepository:
    @staticmethod
    async def get_owners(character_id: str) -> List[UserOwnership]:
        cache_key = f"owners_{character_id}"
        if cache_key in user_cache:
            return user_cache[cache_key]
        
        try:
            cursor = user_collection.find(
                {'characters.id': character_id},
                {'_id': 0, 'id': 1, 'first_name': 1, 'username': 1, 'characters': 1}
            )
            users = await cursor.to_list(length=None)
            
            owners = []
            for user_data in users:
                owner = UserOwnership.from_dict(user_data, character_id)
                if owner.count > 0:
                    owners.append(owner)
            
            owners.sort(key=lambda x: x.count, reverse=True)
            user_cache[cache_key] = owners
            return owners
        except:
            return []


class SearchProcessor:
    @staticmethod
    def process_search_results(characters: List[Dict]) -> SearchResult:
        name_counts = {}
        char_data = {}
        rarity_breakdown = {}
        
        for char in characters:
            name = char.get('name', 'Unknown')
            if name not in name_counts:
                name_counts[name] = 0
                char_data[name] = char
            name_counts[name] += 1
            
            rarity = RarityInfo.parse(char.get('rarity', '🟢 Common'))
            rarity_breakdown[rarity.emoji] = rarity_breakdown.get(rarity.emoji, 0) + 1
        
        return SearchResult(
            characters=characters,
            unique_count=len(name_counts),
            total_count=len(characters),
            name_counts=name_counts,
            char_data=char_data,
            rarity_breakdown=rarity_breakdown
        )


class CardFormatter:
    @staticmethod
    def format_basic_card(char: CharacterData, global_count: Optional[int] = None) -> str:
        rarity = RarityInfo.parse(char.rarity)
        
        caption = (
            f"<b>╭━━━━━━━━━━━━━━━━━╮</b>\n"
            f"<b>┃  🎴 ᴄʜᴀʀᴀᴄᴛᴇʀ ᴄᴀʀᴅ  ┃</b>\n"
            f"<b>╰━━━━━━━━━━━━━━━━━╯</b>\n\n"
            f"<b>🆔 ɪᴅ</b> : <code>{char.id}</code>\n"
            f"<b>🧬 ɴᴀᴍᴇ</b> : <code>{escape(char.name)}</code>\n"
            f"<b>📺 ᴀɴɪᴍᴇ</b> : <code>{escape(char.anime)}</code>\n"
            f"<b>{rarity.emoji} ʀᴀʀɪᴛʏ</b> : <code>{rarity.text.lower()}</code>"
        )
        
        if global_count is not None:
            caption += f"\n\n<b>🌍 ɢʟᴏʙᴀʟʟʏ ɢʀᴀʙʙᴇᴅ</b> <code>{global_count}x</code>"
        
        caption += (
            f"\n\n<b>━━━━━━━━━━━━━━━━━</b>\n"
            f"<i>ᴀ ᴘʀᴇᴄɪᴏᴜs ᴄʜᴀʀᴀᴄᴛᴇʀ ᴡᴀɪᴛɪɴɢ ᴛᴏ ᴊᴏɪɴ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ</i>"
        )
        
        return caption
    
    @staticmethod
    def format_owners_card(
        char: CharacterData,
        owners: List[UserOwnership],
        page: int,
        global_count: int
    ) -> str:
        rarity = RarityInfo.parse(char.rarity)
        
        start_idx = page * USERS_PER_PAGE
        end_idx = start_idx + USERS_PER_PAGE
        page_owners = owners[start_idx:end_idx]
        total_pages = (len(owners) + USERS_PER_PAGE - 1) // USERS_PER_PAGE
        
        caption = (
            f"<b>╭━━━━━━━━━━━━━━━━━╮</b>\n"
            f"<b>┃  🎴 ᴄʜᴀʀᴀᴄᴛᴇʀ ᴏᴡɴᴇʀs  ┃</b>\n"
            f"<b>╰━━━━━━━━━━━━━━━━━╯</b>\n\n"
            f"<b>🆔 ɪᴅ</b> : <code>{char.id}</code>\n"
            f"<b>🧬 ɴᴀᴍᴇ</b> : <code>{escape(char.name)}</code>\n"
            f"<b>📺 ᴀɴɪᴍᴇ</b> : <code>{escape(char.anime)}</code>\n"
            f"<b>{rarity.emoji} ʀᴀʀɪᴛʏ</b> : <code>{rarity.text.lower()}</code>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━</b>\n"
        )
        
        for i, owner in enumerate(page_owners, start=start_idx + 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            user_link = f"<a href='tg://user?id={owner.id}'>{escape(owner.first_name)}</a>"
            if owner.username:
                user_link += f" (@{escape(owner.username)})"
            caption += f"\n{medal} {user_link} <code>x{owner.count}</code>"
        
        caption += (
            f"\n\n<b>📄 ᴘᴀɢᴇ</b> <code>{page + 1}/{total_pages}</code>\n"
            f"<b>🔮 ᴛᴏᴛᴀʟ ɢʀᴀʙʙᴇᴅ</b> <code>{global_count}x</code>"
        )
        
        return caption
    
    @staticmethod
    def format_find_results_paginated(
        query: str,
        result: SearchResult,
        page: int = 0,
        show_all: bool = False
    ) -> Tuple[str, int]:
        """Format paginated find results"""
        total_chars = result.unique_count
        total_pages = (total_chars + CHARACTERS_PER_PAGE - 1) // CHARACTERS_PER_PAGE if not show_all else 1
        
        # Header
        response = (
            f"<b>╭━━━━━━━━━━━━━━━━━╮</b>\n"
            f"<b>┃ 🔍 ᴅᴇᴛᴀɪʟᴇᴅ sᴇᴀʀᴄʜ ┃</b>\n"
            f"<b>╰━━━━━━━━━━━━━━━━━╯</b>\n"
            f"<b>🔎 ǫᴜᴇʀʏ:</b> <code>{escape(query)}</code>\n"
            f"<b>📊 ᴛᴏᴛᴀʟ:</b> <code>{result.total_count}</code> ᴠᴀʀɪᴀɴᴛs\n"
            f"<b>👤 ᴜɴɪǫᴜᴇ:</b> <code>{result.unique_count}</code> ᴄʜᴀʀᴀᴄᴛᴇʀs\n"
        )
        
        if result.rarity_breakdown:
            response += "<b>✨ ʀᴀʀɪᴛʏ sᴘʟɪᴛ:</b>\n"
            for emoji, count in sorted(result.rarity_breakdown.items(), key=lambda x: x[1], reverse=True):
                response += f"   {emoji} <code>{count}</code> ᴄᴀʀᴅs\n"
        
        response += "<b>━━━━━━━━━━━━━━━━━</b>\n"
        
        # Character list with pagination
        sorted_chars = sorted(result.name_counts.items())
        
        if show_all:
            start_idx = 0
            end_idx = len(sorted_chars)
        else:
            start_idx = page * CHARACTERS_PER_PAGE
            end_idx = min(start_idx + CHARACTERS_PER_PAGE, len(sorted_chars))
        
        for i, (name, count) in enumerate(sorted_chars[start_idx:end_idx], start=start_idx + 1):
            char = result.char_data[name]
            char_id = char.get('id', '??')
            rarity = RarityInfo.parse(char.get('rarity', '🟢 Common'))
            
            response += f"<b>{i}. {escape(name)}</b> <code>[{char_id}]</code>\n"
            response += f"📺 {escape(char.get('anime', 'Unknown'))}\n"
            response += f"{rarity.emoji} {rarity.text.lower()}"
            
            if count > 1:
                response += f" • <code>{count}</code> ᴠᴀʀɪᴀɴᴛs"
            
            response += f"\n💫 /check {char_id}\n"
        
        response += "<b>━━━━━━━━━━━━━━━━━</b>\n"
        
        if not show_all and total_pages > 1:
            response += f"<b>📄 ᴘᴀɢᴇ:</b> <code>{page + 1}/{total_pages}</code>\n"
        
        response += "<i>💡 ᴛᴀᴘ /check ᴄᴏᴍᴍᴀɴᴅs ᴛᴏ ᴠɪᴇᴡ ᴄᴀʀᴅs</i>"
        
        return response, total_pages
    
    @staticmethod
    def format_id_list(characters: List[Dict], query: str) -> str:
        """Format a compact ID list view"""
        char_ids = sorted(set(char.get('id', '??') for char in characters))
        
        response = (
            f"<b>╭━━━━━━━━━━━━━━━━━╮</b>\n"
            f"<b>┃  🆔 ɪᴅ ʟɪsᴛ ᴠɪᴇᴡ  ┃</b>\n"
            f"<b>╰━━━━━━━━━━━━━━━━━╯</b>\n"
            f"<b>🔎 ǫᴜᴇʀʏ:</b> <code>{escape(query)}</code>\n"
            f"<b>📊 ᴛᴏᴛᴀʟ:</b> <code>{len(char_ids)}</code> ᴄʜᴀʀᴀᴄᴛᴇʀs\n"
            f"<b>━━━━━━━━━━━━━━━━━</b>\n"
        )
        
        # Group IDs in rows of 6 for compact display
        ids_per_row = 6
        for i in range(0, len(char_ids), ids_per_row):
            row_ids = char_ids[i:i+ids_per_row]
            response += " ".join(f"<code>{cid}</code>" for cid in row_ids) + "\n"
        
        response += (
            f"<b>━━━━━━━━━━━━━━━━━</b>\n"
            f"<i>💡 ᴜsᴇ /check [ɪᴅ] ᴛᴏ ᴠɪᴇᴡ ᴀɴʏ ᴄᴀʀᴅ</i>"
        )
        
        return response
    
    @staticmethod
    def format_anime_results(anime: str, result: SearchResult) -> str:
        response = (
            f"<b>╭━━━━━━━━━━━━━━━━━╮</b>\n"
            f"<b>┃  📺 ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs  ┃</b>\n"
            f"<b>╰━━━━━━━━━━━━━━━━━╯</b>\n\n"
            f"<b>🎬 ᴀɴɪᴍᴇ</b> <code>{escape(anime)}</code>\n"
            f"<b>📊 ᴛᴏᴛᴀʟ ғᴏᴜɴᴅ</b> <code>{result.total_count}</code>\n"
            f"<b>👤 ᴜɴɪǫᴜᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs</b> <code>{result.unique_count}</code>\n\n"
        )
        
        if result.rarity_breakdown:
            response += "<b>🎨 ʀᴀʀɪᴛʏ ʙʀᴇᴀᴋᴅᴏᴡɴ</b>\n"
            for emoji, count in sorted(result.rarity_breakdown.items(), key=lambda x: x[1], reverse=True):
                response += f"   {emoji} <code>{count}x</code>\n"
            response += "\n"
        
        response += "<b>━━━━━━━━━━━━━━━━━</b>\n\n"
        return response
    
    @staticmethod
    async def append_character_list(
        response: str,
        result: SearchResult,
        limit: int = MAX_RESULTS_DISPLAY
    ) -> str:
        for i, (name, count) in enumerate(sorted(result.name_counts.items()), 1):
            if i > limit:
                remaining = result.unique_count - limit
                response += f"\n<i>... ᴀɴᴅ {remaining} ᴍᴏʀᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs</i>\n"
                break
            
            char = result.char_data[name]
            rarity = RarityInfo.parse(char.get('rarity', '🟢 Common'))
            global_count = await CharacterRepository.get_global_count(char.get('id', '??'))

            response += f"<b>{i}. {escape(name)}</b>"
            if count > 1:
                response += f" <code>x{count}</code>"
            response += (
                f"\n   🆔 <code>{char.get('id', '??')}</code>\n"
                f"   📺 <i>{escape(char.get('anime', 'Unknown'))}</i>\n"
                f"   {rarity.emoji} {rarity.text.lower()}\n"
                f"   🌍 <code>{global_count}x</code> ɢʀᴀʙʙᴇᴅ\n\n"
            )
        
        response += "<b>━━━━━━━━━━━━━━━━━</b>\n<i>ᴜsᴇ /check [id] ғᴏʀ ᴍᴏʀᴇ ᴅᴇᴛᴀɪʟs</i>"
        return response


class KeyboardBuilder:
    @staticmethod
    def build_pagination(
        character_id: str,
        page: int,
        total_pages: int,
        show_back: bool = False
    ) -> InlineKeyboardMarkup:
        keyboard = []
        
        if total_pages > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append(
                    InlineKeyboardButton("⬅️ ᴘʀᴇᴠ", callback_data=f"owners_{character_id}_{page-1}")
                )
            if page < total_pages - 1:
                nav_buttons.append(
                    InlineKeyboardButton("ɴᴇxᴛ ➡️", callback_data=f"owners_{character_id}_{page+1}")
                )
            if nav_buttons:
                keyboard.append(nav_buttons)
        
        if show_back:
            keyboard.append([
                InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data=f"back_{character_id}")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("🏆 sʜᴏᴡ ᴏᴡɴᴇʀs", callback_data=f"owners_{character_id}_0")
            ])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def build_find_pagination(
        query: str,
        page: int,
        total_pages: int,
        rarity_filter: Optional[str] = None
    ) -> InlineKeyboardMarkup:
        keyboard = []
        
        if total_pages > 1:
            nav_buttons = []
            
            callback_prefix = f"find_{query}"
            if rarity_filter:
                callback_prefix += f"_r{rarity_filter}"
            
            if page > 0:
                nav_buttons.append(
                    InlineKeyboardButton("⬅️ ᴘʀᴇᴠ", callback_data=f"{callback_prefix}_{page-1}")
                )
            
            nav_buttons.append(
                InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="noop")
            )
            
            if page < total_pages - 1:
                nav_buttons.append(
                    InlineKeyboardButton("ɴᴇxᴛ ➡️", callback_data=f"{callback_prefix}_{page+1}")
                )
            
            if nav_buttons:
                keyboard.append(nav_buttons)
        
        return InlineKeyboardMarkup(keyboard) if keyboard else None


class MediaSender:
    @staticmethod
    async def send(
        update: Update,
        character: CharacterData,
        caption: str,
        keyboard: InlineKeyboardMarkup
    ) -> None:
        if character.is_video:
            await update.message.reply_video(
                video=character.img_url,
                caption=caption,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_photo(
                photo=character.img_url,
                caption=caption,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )


async def check_character(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if len(context.args) < 1:
            return await update.message.reply_text(
                "<b>ɪɴᴄᴏʀʀᴇᴄᴛ ғᴏʀᴍᴀᴛ</b>\n\n"
                "ᴜsᴀɢᴇ: <code>/check character_id</code>\n"
                "ᴇxᴀᴍᴘʟᴇ: <code>/check 01</code>",
                parse_mode=ParseMode.HTML
            )

        character_id = context.args[0]
        character = await CharacterRepository.get_by_id(character_id)

        if not character:
            return await update.message.reply_text(
                f"<b>❌ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ</b>\n\n"
                f"ɪᴅ <code>{character_id}</code> ᴅᴏᴇs ɴᴏᴛ ᴇxɪsᴛ",
                parse_mode=ParseMode.HTML
            )

        global_count = await CharacterRepository.get_global_count(character_id)
        caption = CardFormatter.format_basic_card(character, global_count)
        keyboard = KeyboardBuilder.build_pagination(character_id, 0, 1)

        await MediaSender.send(update, character, caption, keyboard)

    except Exception as e:
        print(f"Error in check_character: {e}")
        await update.message.reply_text(
            f"<b>❌ ᴇʀʀᴏʀ</b>\n{escape(str(e))}",
            parse_mode=ParseMode.HTML
        )


async def find_character(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if len(context.args) < 1:
            return await update.message.reply_text(
                "<b>╭━━━━━━━━━━━━━━━━━╮</b>\n"
                "<b>┃  🔍 ғɪɴᴅ ᴄᴏᴍᴍᴀɴᴅ  ┃</b>\n"
                "<b>╰━━━━━━━━━━━━━━━━━╯</b>\n\n"
                "<b>📖 ᴜsᴀɢᴇ</b>\n"
                "<code>/find [name]</code> - Basic search\n"
                "<code>/find [name] --all</code> - Show all results\n"
                "<code>/find [name] --ids</code> - ID list only\n"
                "<code>/find [name] --rarity [emoji]</code> - Filter by rarity\n\n"
                "<b>📌 ᴇxᴀᴍᴘʟᴇs</b>\n"
                "• <code>/find naruto</code>\n"
                "• <code>/find goku --all</code>\n"
                "• <code>/find luffy --ids</code>\n"
                "• <code>/find sasuke --rarity 🔴</code>\n\n"
                "<b>✨ ʀᴀʀɪᴛʏ ғɪʟᴛᴇʀs</b>\n"
                "🟢 Common | 🔵 Medium | 🟣 Rare\n"
                "🟡 Legendary | 🔴 Limited | ⚪️ Special\n\n"
                "<i>💡 ғɪɴᴅ ᴀɴʏ ᴄʜᴀʀᴀᴄᴛᴇʀ ʙʏ ɴᴀᴍᴇ!</i>",
                parse_mode=ParseMode.HTML
            )

        # Parse arguments
        args = context.args.copy()
        show_all = False
        ids_only = False
        rarity_filter = None
        
        # Check for flags
        if '--all' in args:
            show_all = True
            args.remove('--all')
        
        if '--ids' in args:
            ids_only = True
            args.remove('--ids')
        
        if '--rarity' in args:
            idx = args.index('--rarity')
            if idx + 1 < len(args):
                rarity_filter = args[idx + 1]
                args.pop(idx)
                args.pop(idx)
        
        if not args:
            return await update.message.reply_text(
                "<b>❌ ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴀᴍᴇ</b>\n\n"
                "ᴇxᴀᴍᴘʟᴇ: <code>/find naruto</code>",
                parse_mode=ParseMode.HTML
            )

        char_name = ' '.join(args)
        characters = await CharacterRepository.find_by_name(char_name)

        if not characters:
            return await update.message.reply_text(
                f"<b>❌ ɴᴏ ʀᴇsᴜʟᴛs</b>\n\n"
                f"ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ғᴏᴜɴᴅ ᴍᴀᴛᴄʜɪɴɢ:\n"
                f"<code>{escape(char_name)}</code>\n\n"
                f"<i>💡 ᴛʀʏ ᴀ ᴅɪғғᴇʀᴇɴᴛ sᴘᴇʟʟɪɴɢ ᴏʀ ɴᴀᴍᴇ</i>",
                parse_mode=ParseMode.HTML
            )

        # Apply rarity filter if specified
        if rarity_filter:
            characters = [
                char for char in characters 
                if rarity_filter in str(char.get('rarity', ''))
            ]
            if not characters:
                return await update.message.reply_text(
                    f"<b>❌ ɴᴏ ʀᴇsᴜʟᴛs</b>\n\n"
                    f"ɴᴏ <code>{escape(char_name)}</code> ᴄʜᴀʀᴀᴄᴛᴇʀs ғᴏᴜɴᴅ ᴡɪᴛʜ ʀᴀʀɪᴛʏ {rarity_filter}",
                    parse_mode=ParseMode.HTML
                )

        # Show ID list view if requested
        if ids_only:
            response = CardFormatter.format_id_list(characters, char_name)
            return await update.message.reply_text(response, parse_mode=ParseMode.HTML)

        # Show detailed results with pagination
        result = SearchProcessor.process_search_results(characters)
        response, total_pages = CardFormatter.format_find_results_paginated(char_name, result, 0, show_all)
        
        # Build keyboard if pagination needed
        keyboard = None
        if not show_all and total_pages > 1:
            keyboard = KeyboardBuilder.build_find_pagination(char_name, 0, total_pages, rarity_filter)

        await update.message.reply_text(response, parse_mode=ParseMode.HTML, reply_markup=keyboard)

    except Exception as e:
        print(f"Error in find_character: {e}")
        await update.message.reply_text(
            f"<b>❌ ᴇʀʀᴏʀ</b>\n\n{escape(str(e))}",
            parse_mode=ParseMode.HTML
        )


async def find_anime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if len(context.args) < 1:
            return await update.message.reply_text(
                "<b>ᴜsᴀɢᴇ</b> <code>/anime anime_name</code>\n"
                "ᴇxᴀᴍᴘʟᴇ: <code>/anime naruto</code>",
                parse_mode=ParseMode.HTML
            )

        anime_name = " ".join(context.args)
        characters = await CharacterRepository.find_by_anime(anime_name)
        
        if not characters:
            return await update.message.reply_text(
                f"<b>❌ ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ғᴏᴜɴᴅ ғʀᴏᴍ ᴀɴɪᴍᴇ</b> <code>{escape(anime_name)}</code>",
                parse_mode=ParseMode.HTML
            )

        result = SearchProcessor.process_search_results(characters)
        response = CardFormatter.format_anime_results(anime_name, result)
        response = await CardFormatter.append_character_list(response, result)

        await update.message.reply_text(response, parse_mode=ParseMode.HTML)

    except Exception as e:
        print(f"Error in find_anime: {e}")
        await update.message.reply_text(
            f"<b>❌ ᴇʀʀᴏʀ</b> {escape(str(e))}",
            parse_mode=ParseMode.HTML
        )


async def find_users_with_character(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if len(context.args) < 1:
            return await update.message.reply_text(
                "<b>ᴜsᴀɢᴇ</b> <code>/pfind character_id</code>\n"
                "ᴇxᴀᴍᴘʟᴇ: <code>/pfind 01</code>",
                parse_mode=ParseMode.HTML
            )

        character_id = context.args[0]
        character = await CharacterRepository.get_by_id(character_id)

        if not character:
            return await update.message.reply_text(
                f"<b>❌ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ</b> <code>{character_id}</code>",
                parse_mode=ParseMode.HTML
            )

        owners = await UserRepository.get_owners(character_id)

        if not owners:
            return await update.message.reply_text(
                f"<b>ɴᴏ ᴜsᴇʀs ғᴏᴜɴᴅ ᴡɪᴛʜ ᴄʜᴀʀᴀᴄᴛᴇʀ</b> <code>{character_id}</code>",
                parse_mode=ParseMode.HTML
            )

        global_count = await CharacterRepository.get_global_count(character_id)
        total_pages = (len(owners) + USERS_PER_PAGE - 1) // USERS_PER_PAGE
        
        caption = CardFormatter.format_owners_card(character, owners, 0, global_count)
        keyboard = KeyboardBuilder.build_pagination(character_id, 0, total_pages, show_back=True)

        await MediaSender.send(update, character, caption, keyboard)

    except Exception as e:
        print(f"Error in pfind: {e}")
        await update.message.reply_text(
            f"<b>❌ ᴇʀʀᴏʀ</b> {escape(str(e))}",
            parse_mode=ParseMode.HTML
        )


async def handle_owners_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    try:
        data_parts = query.data.split('_')
        character_id = data_parts[1]
        page = int(data_parts[2])

        character = await CharacterRepository.get_by_id(character_id)
        if not character:
            return await query.answer("ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)

        owners = await UserRepository.get_owners(character_id)
        if not owners:
            return await query.answer("ɴᴏ ᴏɴᴇ ᴏᴡɴs ᴛʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ", show_alert=True)

        global_count = await CharacterRepository.get_global_count(character_id)
        total_pages = (len(owners) + USERS_PER_PAGE - 1) // USERS_PER_PAGE
        
        caption = CardFormatter.format_owners_card(character, owners, page, global_count)
        keyboard = KeyboardBuilder.build_pagination(character_id, page, total_pages, show_back=True)

        await query.edit_message_caption(
            caption=caption,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        print(f"Error in pagination: {e}")
        await query.answer("ᴇʀʀᴏʀ", show_alert=True)


async def handle_back_to_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    try:
        character_id = query.data.split('_')[1]
        character = await CharacterRepository.get_by_id(character_id)

        if not character:
            return await query.answer("ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)

        global_count = await CharacterRepository.get_global_count(character_id)
        caption = CardFormatter.format_basic_card(character, global_count)
        keyboard = KeyboardBuilder.build_pagination(character_id, 0, 1)

        await query.edit_message_caption(
            caption=caption,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        print(f"Error going back: {e}")
        await query.answer("ᴇʀʀᴏʀ", show_alert=True)


async def handle_find_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    try:
        # Parse callback data: find_query_rRARITY_page or find_query_page
        data = query.data.replace('find_', '', 1)
        parts = data.rsplit('_', 1)
        
        if len(parts) != 2:
            return await query.answer("ɪɴᴠᴀʟɪᴅ ᴅᴀᴛᴀ", show_alert=True)
        
        query_part = parts[0]
        page = int(parts[1])
        
        # Check for rarity filter
        rarity_filter = None
        char_name = query_part
        if '_r' in query_part:
            name_parts = query_part.rsplit('_r', 1)
            char_name = name_parts[0]
            rarity_filter = name_parts[1]
        
        # Fetch characters
        characters = await CharacterRepository.find_by_name(char_name)
        
        if not characters:
            return await query.answer("ɴᴏ ʀᴇsᴜʟᴛs ғᴏᴜɴᴅ", show_alert=True)
        
        # Apply rarity filter if present
        if rarity_filter:
            characters = [
                char for char in characters 
                if rarity_filter in str(char.get('rarity', ''))
            ]
        
        if not characters:
            return await query.answer("ɴᴏ ʀᴇsᴜʟᴛs ғᴏʀ ᴛʜɪs ғɪʟᴛᴇʀ", show_alert=True)
        
        # Process and format results
        result = SearchProcessor.process_search_results(characters)
        response, total_pages = CardFormatter.format_find_results_paginated(char_name, result, page, False)
        
        # Build keyboard
        keyboard = KeyboardBuilder.build_find_pagination(char_name, page, total_pages, rarity_filter)
        
        await query.edit_message_text(
            text=response,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        print(f"Error in find pagination: {e}")
        await query.answer("ᴇʀʀᴏʀ", show_alert=True)


# Register handlers
application.add_handler(CommandHandler("check", check_character, block=False))
application.add_handler(CommandHandler("find", find_character, block=False))
application.add_handler(CommandHandler("anime", find_anime, block=False))
application.add_handler(CommandHandler("pfind", find_users_with_character, block=False))
application.add_handler(CallbackQueryHandler(handle_owners_pagination, pattern=r"^owners_", block=False))
application.add_handler(CallbackQueryHandler(handle_back_to_card, pattern=r"^back_", block=False))
application.add_handler(CallbackQueryHandler(handle_find_pagination, pattern=r"^find_", block=False))