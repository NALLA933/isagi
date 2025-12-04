from html import escape
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from cachetools import TTLCache

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from shivu import shivuu as app
from shivu import db

collection = db['anime_characters_lol']
user_collection = db['user_collection_lmaoooo']

character_cache = TTLCache(maxsize=2000, ttl=600)
anime_cache = TTLCache(maxsize=1000, ttl=900)
user_cache = TTLCache(maxsize=500, ttl=300)

USERS_PER_PAGE = 10
MAX_RESULTS_DISPLAY = 20

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
    async def format_owners_card(
        char: CharacterData,
        owners: List[UserOwnership],
        page: int,
        global_count: int,
        client: Client
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
            
            try:
                user = await client.get_users(owner.id)
                user_mention = user.mention
            except:
                user_mention = f"<a href='tg://user?id={owner.id}'>{escape(owner.first_name)}</a>"
            
            caption += f"\n{medal} {user_mention} <code>x{owner.count}</code>"
        
        caption += (
            f"\n\n<b>📄 ᴘᴀɢᴇ</b> <code>{page + 1}/{total_pages}</code>\n"
            f"<b>🔮 ᴛᴏᴛᴀʟ ɢʀᴀʙʙᴇᴅ</b> <code>{global_count}x</code>"
        )
        
        return caption
    
    @staticmethod
    def format_search_results(query: str, result: SearchResult) -> str:
        response = (
            f"<b>╭━━━━━━━━━━━━━━━━━╮</b>\n"
            f"<b>┃  🔍 sᴇᴀʀᴄʜ ʀᴇsᴜʟᴛs  ┃</b>\n"
            f"<b>╰━━━━━━━━━━━━━━━━━╯</b>\n\n"
            f"<b>🔎 ǫᴜᴇʀʏ</b> <code>{escape(query)}</code>\n"
            f"<b>📊 ᴛᴏᴛᴀʟ ғᴏᴜɴᴅ</b> <code>{result.total_count}</code>\n"
            f"<b>👤 ᴜɴɪǫᴜᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs</b> <code>{result.unique_count}</code>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━</b>\n\n"
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

class MediaSender:
    @staticmethod
    async def send(
        message: Message,
        character: CharacterData,
        caption: str,
        keyboard: InlineKeyboardMarkup
    ) -> None:
        if character.is_video:
            await message.reply_video(
                video=character.img_url,
                caption=caption,
                reply_markup=keyboard
            )
        else:
            await message.reply_photo(
                photo=character.img_url,
                caption=caption,
                reply_markup=keyboard
            )

@app.on_message(filters.command(["check"]))
async def check_character(client: Client, message: Message):
    try:
        if len(message.command) < 2:
            return await message.reply_text(
                "<b>ɪɴᴄᴏʀʀᴇᴄᴛ ғᴏʀᴍᴀᴛ</b>\n\n"
                "ᴜsᴀɢᴇ: <code>/check character_id</code>\n"
                "ᴇxᴀᴍᴘʟᴇ: <code>/check 01</code>"
            )

        character_id = message.command[1]
        character = await CharacterRepository.get_by_id(character_id)

        if not character:
            return await message.reply_text(
                f"<b>❌ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ</b>\n\n"
                f"ɪᴅ <code>{character_id}</code> ᴅᴏᴇs ɴᴏᴛ ᴇxɪsᴛ"
            )

        global_count = await CharacterRepository.get_global_count(character_id)
        caption = CardFormatter.format_basic_card(character, global_count)
        keyboard = KeyboardBuilder.build_pagination(character_id, 0, 1)

        await MediaSender.send(message, character, caption, keyboard)

    except Exception as e:
        print(f"Error in check_character: {e}")
        await message.reply_text(f"<b>❌ ᴇʀʀᴏʀ</b>\n{escape(str(e))}")

@app.on_message(filters.command(["find"]))
async def find_character(client: Client, message: Message):
    try:
        if len(message.command) < 2:
            return await message.reply_text(
                "<b>ᴜsᴀɢᴇ</b> <code>/find name</code>\n"
                "ᴇxᴀᴍᴘʟᴇ: <code>/find naruto</code>"
            )

        char_name = ' '.join(message.command[1:])
        characters = await CharacterRepository.find_by_name(char_name)

        if not characters:
            return await message.reply_text(
                f"<b>❌ ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ғᴏᴜɴᴅ ᴡɪᴛʜ ɴᴀᴍᴇ</b> <code>{escape(char_name)}</code>"
            )

        result = SearchProcessor.process_search_results(characters)
        response = CardFormatter.format_search_results(char_name, result)
        response = await CardFormatter.append_character_list(response, result)

        await message.reply_text(response)

    except Exception as e:
        print(f"Error in find_character: {e}")
        await message.reply_text(f"<b>❌ ᴇʀʀᴏʀ</b> {escape(str(e))}")

@app.on_message(filters.command(["anime"]))
async def find_anime(client: Client, message: Message):
    try:
        if len(message.command) < 2:
            return await message.reply_text(
                "<b>ᴜsᴀɢᴇ</b> <code>/anime anime_name</code>\n"
                "ᴇxᴀᴍᴘʟᴇ: <code>/anime naruto</code>"
            )

        anime_name = " ".join(message.command[1:])
        characters = await CharacterRepository.find_by_anime(anime_name)
        
        if not characters:
            return await message.reply_text(
                f"<b>❌ ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ғᴏᴜɴᴅ ғʀᴏᴍ ᴀɴɪᴍᴇ</b> <code>{escape(anime_name)}</code>"
            )

        result = SearchProcessor.process_search_results(characters)
        response = CardFormatter.format_anime_results(anime_name, result)
        response = await CardFormatter.append_character_list(response, result)

        await message.reply_text(response)

    except Exception as e:
        print(f"Error in find_anime: {e}")
        await message.reply_text(f"<b>❌ ᴇʀʀᴏʀ</b> {escape(str(e))}")

@app.on_message(filters.command(["pfind"]))
async def find_users_with_character(client: Client, message: Message):
    try:
        if len(message.command) < 2:
            return await message.reply_text(
                "<b>ᴜsᴀɢᴇ</b> <code>/pfind character_id</code>\n"
                "ᴇxᴀᴍᴘʟᴇ: <code>/pfind 01</code>"
            )

        character_id = message.command[1]
        character = await CharacterRepository.get_by_id(character_id)

        if not character:
            return await message.reply_text(
                f"<b>❌ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ</b> <code>{character_id}</code>"
            )

        owners = await UserRepository.get_owners(character_id)

        if not owners:
            return await message.reply_text(
                f"<b>ɴᴏ ᴜsᴇʀs ғᴏᴜɴᴅ ᴡɪᴛʜ ᴄʜᴀʀᴀᴄᴛᴇʀ</b> <code>{character_id}</code>"
            )

        global_count = await CharacterRepository.get_global_count(character_id)
        total_pages = (len(owners) + USERS_PER_PAGE - 1) // USERS_PER_PAGE
        
        caption = await CardFormatter.format_owners_card(character, owners, 0, global_count, client)
        keyboard = KeyboardBuilder.build_pagination(character_id, 0, total_pages, show_back=True)

        await MediaSender.send(message, character, caption, keyboard)

    except Exception as e:
        print(f"Error in pfind: {e}")
        await message.reply_text(f"<b>❌ ᴇʀʀᴏʀ</b> {escape(str(e))}")

@app.on_callback_query(filters.regex(r"^owners_"))
async def handle_owners_pagination(client: Client, query: CallbackQuery):
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
        
        caption = await CardFormatter.format_owners_card(character, owners, page, global_count, client)
        keyboard = KeyboardBuilder.build_pagination(character_id, page, total_pages, show_back=True)

        await query.edit_message_caption(caption=caption, reply_markup=keyboard)

    except Exception as e:
        print(f"Error in pagination: {e}")
        await query.answer("ᴇʀʀᴏʀ", show_alert=True)

@app.on_callback_query(filters.regex(r"^back_"))
async def handle_back_to_card(client: Client, query: CallbackQuery):
    await query.answer()

    try:
        character_id = query.data.split('_')[1]
        character = await CharacterRepository.get_by_id(character_id)

        if not character:
            return await query.answer("ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)

        global_count = await CharacterRepository.get_global_count(character_id)
        caption = CardFormatter.format_basic_card(character, global_count)
        keyboard = KeyboardBuilder.build_pagination(character_id, 0, 1)

        await query.edit_message_caption(caption=caption, reply_markup=keyboard)

    except Exception as e:
        print(f"Error going back: {e}")
        await query.answer("ᴇʀʀᴏʀ", show_alert=True)