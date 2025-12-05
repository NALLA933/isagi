""" v3 using siya method with image quality enhancement """

import io
import asyncio
import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Tuple, Dict, List, Union, Any
from pathlib import Path
from functools import wraps, lru_cache
from contextlib import asynccontextmanager
import mimetypes

import aiohttp
from aiohttp import ClientSession, TCPConnector
from pymongo import ReturnDocument
from telegram import Update, InputFile, Message
from telegram.ext import CommandHandler, ContextTypes
from telegram.error import TelegramError, NetworkError, TimedOut
from motor.motor_asyncio import AsyncIOMotorCollection
from PIL import Image, ImageEnhance, ImageFilter

from shivu import application, collection, db, CHARA_CHANNEL_ID, SUPPORT_CHAT, sudo_users


class MediaType(Enum):
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    ANIMATION = "animation"

    @classmethod
    def from_mime(cls, mime_type: str) -> 'MediaType':
        if not mime_type:
            return cls.IMAGE
        
        mime_lower = mime_type.lower()
        if mime_lower.startswith('video'):
            return cls.VIDEO
        elif mime_lower.startswith('image/gif'):
            return cls.ANIMATION
        elif mime_lower.startswith('image'):
            return cls.IMAGE
        return cls.DOCUMENT


class RarityLevel(Enum):
    COMMON = (1, "🟢 Common")
    RARE = (2, "🟣 Rare")
    LEGENDARY = (3, "🟡 Legendary")
    SPECIAL_EDITION = (4, "💮 Special Edition")
    NEON = (5, "💫 Neon")
    MANGA = (6, "✨ Manga")
    COSPLAY = (7, "🎭 Cosplay")
    CELESTIAL = (8, "🎐 Celestial")
    PREMIUM = (9, "🔮 Premium Edition")
    EROTIC = (10, "💋 Erotic")
    SUMMER = (11, "🌤 Summer")
    WINTER = (12, "☃️ Winter")
    MONSOON = (13, "☔️ Monsoon")
    VALENTINE = (14, "💝 Valentine")
    HALLOWEEN = (15, "🎃 Halloween")
    CHRISTMAS = (16, "🎄 Christmas")
    MYTHIC = (17, "🏵 Mythic")
    SPECIAL_EVENTS = (18, "🎗 Special Events")
    AMV = (19, "🎥 AMV")
    TINY = (20, "👼 Tiny")

    def __init__(self, level: int, display: str):
        self._level = level
        self._display = display

    @property
    def level(self) -> int:
        return self._level

    @property
    def display_name(self) -> str:
        return self._display

    @property
    def emoji(self) -> str:
        return self._display.split()[0]

    @classmethod
    @lru_cache(maxsize=32)
    def from_number(cls, num: int) -> Optional['RarityLevel']:
        for rarity in cls:
            if rarity.level == num:
                return rarity
        return None


@dataclass(frozen=True)
class Config:
    MAX_FILE_SIZE: int = 50 * 1024 * 1024
    DOWNLOAD_TIMEOUT: int = 300
    UPLOAD_TIMEOUT: int = 300
    CHUNK_SIZE: int = 65536
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0
    CONNECTION_LIMIT: int = 100
    CATBOX_API: str = "https://catbox.moe/user/api.php"
    ALLOWED_EXTENSIONS: tuple = ('.jpg', '.jpeg', '.png', '.gif', '.mp4', '.avi', '.mov', '.mkv', '.webm')
    
    # Image enhancement settings
    ENHANCE_IMAGES: bool = True
    ENHANCE_SHARPNESS: float = 1.3  # 1.0 = no change, >1.0 = sharper
    ENHANCE_CONTRAST: float = 1.15  # 1.0 = no change, >1.0 = more contrast
    ENHANCE_COLOR: float = 1.1  # 1.0 = no change, >1.0 = more vibrant
    ENHANCE_BRIGHTNESS: float = 1.05  # 1.0 = no change, >1.0 = brighter
    JPEG_QUALITY: int = 95  # Quality for JPEG compression (1-100)
    PNG_OPTIMIZE: bool = True  # Optimize PNG files
    MAX_IMAGE_DIMENSION: int = 4096  # Max width/height before resizing


class ImageEnhancer:
    """Handles image quality enhancement operations"""
    
    @staticmethod
    def enhance_image(image_bytes: bytes, filename: str) -> Tuple[bytes, bool]:
        """
        Enhance image quality with sharpening, contrast, and color adjustments
        Returns: (enhanced_bytes, was_enhanced)
        """
        try:
            # Open image
            img = Image.open(io.BytesIO(image_bytes))
            
            # Convert RGBA to RGB if necessary (for JPEG)
            if img.mode == 'RGBA':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            
            original_format = img.format or 'JPEG'
            
            # Resize if too large
            img = ImageEnhancer._resize_if_needed(img)
            
            # Apply enhancements
            img = ImageEnhancer._apply_sharpness(img)
            img = ImageEnhancer._apply_contrast(img)
            img = ImageEnhancer._apply_color(img)
            img = ImageEnhancer._apply_brightness(img)
            
            # Apply subtle unsharp mask for extra clarity
            img = ImageEnhancer._apply_unsharp_mask(img)
            
            # Save enhanced image
            output = io.BytesIO()
            save_format = 'PNG' if filename.lower().endswith('.png') else 'JPEG'
            
            if save_format == 'JPEG':
                img.save(
                    output,
                    format='JPEG',
                    quality=Config.JPEG_QUALITY,
                    optimize=True,
                    progressive=True
                )
            else:
                img.save(
                    output,
                    format='PNG',
                    optimize=Config.PNG_OPTIMIZE,
                    compress_level=6
                )
            
            enhanced_bytes = output.getvalue()
            return enhanced_bytes, True
            
        except Exception as e:
            print(f"Image enhancement failed: {type(e).__name__}: {e}")
            return image_bytes, False
    
    @staticmethod
    def _resize_if_needed(img: Image.Image) -> Image.Image:
        """Resize image if dimensions exceed maximum"""
        max_dim = Config.MAX_IMAGE_DIMENSION
        width, height = img.size
        
        if width <= max_dim and height <= max_dim:
            return img
        
        # Calculate new dimensions maintaining aspect ratio
        if width > height:
            new_width = max_dim
            new_height = int((max_dim / width) * height)
        else:
            new_height = max_dim
            new_width = int((max_dim / height) * width)
        
        return img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    @staticmethod
    def _apply_sharpness(img: Image.Image) -> Image.Image:
        """Enhance image sharpness"""
        if Config.ENHANCE_SHARPNESS != 1.0:
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(Config.ENHANCE_SHARPNESS)
        return img
    
    @staticmethod
    def _apply_contrast(img: Image.Image) -> Image.Image:
        """Enhance image contrast"""
        if Config.ENHANCE_CONTRAST != 1.0:
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(Config.ENHANCE_CONTRAST)
        return img
    
    @staticmethod
    def _apply_color(img: Image.Image) -> Image.Image:
        """Enhance color vibrancy"""
        if Config.ENHANCE_COLOR != 1.0:
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(Config.ENHANCE_COLOR)
        return img
    
    @staticmethod
    def _apply_brightness(img: Image.Image) -> Image.Image:
        """Enhance brightness"""
        if Config.ENHANCE_BRIGHTNESS != 1.0:
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(Config.ENHANCE_BRIGHTNESS)
        return img
    
    @staticmethod
    def _apply_unsharp_mask(img: Image.Image) -> Image.Image:
        """Apply unsharp mask for extra sharpness"""
        try:
            return img.filter(ImageFilter.UnsharpMask(radius=1, percent=120, threshold=3))
        except Exception:
            return img
    
    @staticmethod
    def should_enhance(media_type: MediaType, mime_type: str) -> bool:
        """Check if file should be enhanced"""
        if not Config.ENHANCE_IMAGES:
            return False
        
        if media_type != MediaType.IMAGE:
            return False
        
        # Don't enhance GIFs or animations
        if mime_type and 'gif' in mime_type.lower():
            return False
        
        return True


@dataclass
class MediaFile:
    url: str
    file_bytes: Optional[bytes] = None
    media_type: MediaType = MediaType.IMAGE
    filename: str = field(default="")
    mime_type: Optional[str] = None
    size: int = 0
    hash: str = field(default="")
    was_enhanced: bool = False

    def __post_init__(self):
        if not self.filename:
            object.__setattr__(self, 'filename', self._generate_filename())
        
        if not self.mime_type:
            object.__setattr__(self, 'mime_type', self._detect_mime_type())
        
        if self.file_bytes and not self.size:
            object.__setattr__(self, 'size', len(self.file_bytes))
        
        if self.file_bytes and not self.hash:
            object.__setattr__(self, 'hash', self._compute_hash())
        
        if self.media_type == MediaType.IMAGE and not self.mime_type:
            object.__setattr__(self, 'mime_type', 'image/jpeg')

    def _generate_filename(self) -> str:
        ext = self._extract_extension()
        hash_part = hashlib.md5(self.url.encode()).hexdigest()[:8]
        return f"character_{hash_part}{ext}"

    def _extract_extension(self) -> str:
        url_lower = self.url.lower()
        
        video_exts = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv'}
        for ext in video_exts:
            if url_lower.endswith(ext):
                object.__setattr__(self, 'media_type', MediaType.VIDEO)
                return ext
        
        if url_lower.endswith('.gif'):
            object.__setattr__(self, 'media_type', MediaType.ANIMATION)
            return '.gif'
        
        image_exts = {'.jpg', '.jpeg', '.png', '.webp'}
        for ext in image_exts:
            if url_lower.endswith(ext):
                return ext
        
        return '.jpg'

    def _detect_mime_type(self) -> str:
        mime, _ = mimetypes.guess_type(self.filename)
        return mime or 'application/octet-stream'

    def _compute_hash(self) -> str:
        return hashlib.sha256(self.file_bytes).hexdigest()

    @property
    def is_video(self) -> bool:
        return self.media_type == MediaType.VIDEO

    @property
    def is_valid_size(self) -> bool:
        return self.size <= Config.MAX_FILE_SIZE
    
    def enhance_if_applicable(self) -> None:
        """Enhance image quality if applicable"""
        if not self.file_bytes:
            return
        
        if not ImageEnhancer.should_enhance(self.media_type, self.mime_type):
            return
        
        enhanced_bytes, was_enhanced = ImageEnhancer.enhance_image(
            self.file_bytes,
            self.filename
        )
        
        if was_enhanced:
            object.__setattr__(self, 'file_bytes', enhanced_bytes)
            object.__setattr__(self, 'size', len(enhanced_bytes))
            object.__setattr__(self, 'hash', hashlib.sha256(enhanced_bytes).hexdigest())
            object.__setattr__(self, 'was_enhanced', True)


@dataclass
class Character:
    character_id: str
    name: str
    anime: str
    rarity: RarityLevel
    media_file: MediaFile
    uploader_id: str
    uploader_name: str
    message_id: Optional[int] = None
    file_id: Optional[str] = None
    file_unique_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.character_id,
            'name': self.name,
            'anime': self.anime,
            'rarity': self.rarity.display_name,
            'img_url': self.media_file.url,
            'is_video': self.media_file.is_video,
            'message_id': self.message_id,
            'file_id': self.file_id,
            'file_unique_id': self.file_unique_id,
            'media_type': self.media_file.media_type.value,
            'file_hash': self.media_file.hash,
            'was_enhanced': self.media_file.was_enhanced,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def get_caption(self, is_update: bool = False) -> str:
        media_type = {
            MediaType.VIDEO: "🎥 Video",
            MediaType.IMAGE: "🖼 Image",
            MediaType.ANIMATION: "🎬 Animation",
            MediaType.DOCUMENT: "📄 Document"
        }.get(self.media_file.media_type, "🖼 Image")
        
        action = "𝑼𝒑𝒅𝒂𝒕𝒆𝒅" if is_update else "𝑴𝒂𝒅𝒆"
        
        quality_badge = " ✨ Enhanced" if self.media_file.was_enhanced else ""
        
        return (
            f'<b>{self.character_id}:</b> {self.name}\n'
            f'<b>{self.anime}</b>\n'
            f'<b>{self.rarity.emoji} 𝙍𝘼𝙍𝙄𝙏𝙔:</b> {self.rarity.display_name[2:]}\n'
            f'<b>Type:</b> {media_type}{quality_badge}\n\n'
            f'{action} 𝑩𝒚 ➥ <a href="tg://user?id={self.uploader_id}">{self.uploader_name}</a>'
        )


@dataclass
class UploadResult:
    success: bool
    message: str
    character_id: Optional[str] = None
    character: Optional[Character] = None
    error: Optional[Exception] = None
    retry_count: int = 0


class SessionManager:
    _session: Optional[ClientSession] = None
    _lock = asyncio.Lock()

    @classmethod
    @asynccontextmanager
    async def get_session(cls):
        async with cls._lock:
            if cls._session is None or cls._session.closed:
                connector = TCPConnector(
                    limit=Config.CONNECTION_LIMIT,
                    limit_per_host=30,
                    ttl_dns_cache=300,
                    enable_cleanup_closed=True
                )
                timeout = aiohttp.ClientTimeout(
                    total=Config.DOWNLOAD_TIMEOUT,
                    connect=60,
                    sock_read=60
                )
                cls._session = ClientSession(
                    connector=connector,
                    timeout=timeout,
                    raise_for_status=False
                )
        
        try:
            yield cls._session
        finally:
            pass

    @classmethod
    async def close(cls):
        async with cls._lock:
            if cls._session and not cls._session.closed:
                await cls._session.close()
                cls._session = None


def retry_on_failure(max_attempts: int = 3, delay: float = 1.0):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(delay * (attempt + 1))
                    continue
            raise last_exception
        return wrapper
    return decorator


class SequenceGenerator:
    _cache: Dict[str, int] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def get_next_id(cls, sequence_name: str) -> str:
        async with cls._lock:
            sequence_collection = db.sequences
            sequence_document = await sequence_collection.find_one_and_update(
                {'_id': sequence_name},
                {'$inc': {'sequence_value': 1}},
                return_document=ReturnDocument.AFTER,
                upsert=True
            )
            
            value = sequence_document.get('sequence_value', 0)
            cls._cache[sequence_name] = value
            return str(value).zfill(2)


class FileDownloader:
    @staticmethod
    def _get_headers(url: str) -> Dict[str, str]:
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': url,
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }

    @staticmethod
    @retry_on_failure(max_attempts=Config.MAX_RETRIES, delay=Config.RETRY_DELAY)
    async def download(url: str) -> Optional[bytes]:
        async with SessionManager.get_session() as session:
            async with session.get(
                url,
                headers=FileDownloader._get_headers(url),
                allow_redirects=True,
                max_redirects=10
            ) as response:
                if response.status != 200:
                    return None
                
                chunks = []
                total_size = 0
                
                async for chunk in response.content.iter_chunked(Config.CHUNK_SIZE):
                    if not chunk:
                        break
                    
                    total_size += len(chunk)
                    if total_size > Config.MAX_FILE_SIZE:
                        raise ValueError(f"File size exceeds {Config.MAX_FILE_SIZE} bytes")
                    
                    chunks.append(chunk)
                
                return b"".join(chunks) if chunks else None

    @staticmethod
    async def download_with_progress(url: str, callback=None) -> Optional[bytes]:
        async with SessionManager.get_session() as session:
            async with session.get(
                url,
                headers=FileDownloader._get_headers(url),
                allow_redirects=True,
                max_redirects=10
            ) as response:
                if response.status != 200:
                    return None
                
                total_size = int(response.headers.get('content-length', 0))
                if total_size > Config.MAX_FILE_SIZE:
                    raise ValueError(f"File size exceeds limit")
                
                chunks = []
                downloaded = 0
                
                async for chunk in response.content.iter_chunked(Config.CHUNK_SIZE):
                    if not chunk:
                        break
                    
                    chunks.append(chunk)
                    downloaded += len(chunk)
                    
                    if callback:
                        await callback(downloaded, total_size)
                
                return b"".join(chunks) if chunks else None


class CatboxUploader:
    @staticmethod
    @retry_on_failure(max_attempts=Config.MAX_RETRIES, delay=Config.RETRY_DELAY)
    async def upload(file_bytes: bytes, filename: str) -> Optional[str]:
        async with SessionManager.get_session() as session:
            data = aiohttp.FormData()
            data.add_field('reqtype', 'fileupload')
            data.add_field(
                'fileToUpload',
                file_bytes,
                filename=filename,
                content_type='application/octet-stream'
            )
            
            async with session.post(Config.CATBOX_API, data=data) as response:
                if response.status == 200:
                    result = (await response.text()).strip()
                    if result.startswith('http'):
                        return result
                return None

    @staticmethod
    async def upload_with_progress(file_bytes: bytes, filename: str, callback=None) -> Optional[str]:
        total_size = len(file_bytes)
        if callback:
            await callback(0, total_size)
        
        result = await CatboxUploader.upload(file_bytes, filename)
        
        if callback:
            await callback(total_size, total_size)
        
        return result


class TelegramUploader:
    @staticmethod
    async def upload_character(
        character: Character,
        context: ContextTypes.DEFAULT_TYPE,
        is_update: bool = False
    ) -> UploadResult:
        caption = character.get_caption(is_update)
        
        for attempt in range(Config.MAX_RETRIES):
            try:
                if character.media_file.file_bytes:
                    result = await TelegramUploader._upload_with_bytes(
                        character, caption, context
                    )
                else:
                    result = await TelegramUploader._upload_with_url(
                        character, caption, context
                    )
                
                if result.success:
                    return result
                
            except (NetworkError, TimedOut) as e:
                if attempt < Config.MAX_RETRIES - 1:
                    await asyncio.sleep(Config.RETRY_DELAY * (attempt + 1))
                    continue
                return UploadResult(
                    success=False,
                    message=f"❌ Network error after {attempt + 1} attempts: {str(e)}",
                    error=e,
                    retry_count=attempt + 1
                )
            except Exception as e:
                try:
                    await collection.insert_one(character.to_dict())
                    return UploadResult(
                        success=False,
                        message=(
                            f"⚠️ Character saved to database but channel upload failed.\n\n"
                            f"🆔 ID: {character.character_id}\n"
                            f"❌ Error: {type(e).__name__}\n\n"
                            f"💡 Try: `/update {character.character_id} img_url <new_url>`"
                        ),
                        character_id=character.character_id,
                        error=e
                    )
                except Exception as db_error:
                    return UploadResult(
                        success=False,
                        message=f"❌ Critical failure: {type(db_error).__name__}",
                        error=db_error
                    )
        
        return UploadResult(
            success=False,
            message="❌ Upload failed after maximum retries",
            retry_count=Config.MAX_RETRIES
        )

    @staticmethod
    async def _upload_with_bytes(
        character: Character,
        caption: str,
        context: ContextTypes.DEFAULT_TYPE
    ) -> UploadResult:
        fp = io.BytesIO(character.media_file.file_bytes)
        fp.name = character.media_file.filename
        
        message = await TelegramUploader._send_media_bytes(
            fp, character.media_file.media_type, caption, context
        )
        
        TelegramUploader._update_character_from_message(character, message)
        await collection.insert_one(character.to_dict())
        
        enhanced_note = " (✨ Quality Enhanced)" if character.media_file.was_enhanced else ""
        
        return UploadResult(
            success=True,
            message=(
                f'✅ Character added successfully!{enhanced_note}\n'
                f'🆔 ID: {character.character_id}\n'
                f'📁 Type: {character.media_file.media_type.value.title()}\n'
                f'💾 Size: {character.media_file.size / 1024:.2f} KB'
            ),
            character_id=character.character_id,
            character=character
        )

    @staticmethod
    async def _upload_with_url(
        character: Character,
        caption: str,
        context: ContextTypes.DEFAULT_TYPE
    ) -> UploadResult:
        message = await TelegramUploader._send_media_url(
            character.media_file.url,
            character.media_file.media_type,
            caption,
            context
        )
        
        TelegramUploader._update_character_from_message(character, message)
        await collection.insert_one(character.to_dict())
        
        return UploadResult(
            success=True,
            message=(
                f'✅ Character added successfully!\n'
                f'🆔 ID: {character.character_id}\n'
                f'📁 Type: {character.media_file.media_type.value.title()}'
            ),
            character_id=character.character_id,
            character=character
        )

    @staticmethod
    def _update_character_from_message(character: Character, message: Message):
        character.message_id = message.message_id
        
        if message.video:
            character.file_id = message.video.file_id
            character.file_unique_id = message.video.file_unique_id
        elif message.photo:
            character.file_id = message.photo[-1].file_id
            character.file_unique_id = message.photo[-1].file_unique_id
        elif message.document:
            character.file_id = message.document.file_id
            character.file_unique_id = message.document.file_unique_id
        elif message.animation:
            character.file_id = message.animation.file_id
            character.file_unique_id = message.animation.file_unique_id

    @staticmethod
    async def _send_media_bytes(
        fp: io.BytesIO,
        media_type: MediaType,
        caption: str,
        context: ContextTypes.DEFAULT_TYPE
    ) -> Message:
        send_kwargs = {
            'chat_id': CHARA_CHANNEL_ID,
            'caption': caption,
            'parse_mode': 'HTML',
            'read_timeout': Config.UPLOAD_TIMEOUT,
            'write_timeout': Config.UPLOAD_TIMEOUT
        }
        
        try:
            if media_type == MediaType.VIDEO:
                return await context.bot.send_video(
                    video=InputFile(fp),
                    supports_streaming=True,
                    **send_kwargs
                )
            elif media_type == MediaType.ANIMATION:
                return await context.bot.send_animation(
                    animation=InputFile(fp),
                    **send_kwargs
                )
            else:
                return await context.bot.send_photo(
                    photo=InputFile(fp),
                    **send_kwargs
                )
        except TelegramError:
            return await context.bot.send_document(
                document=InputFile(fp),
                **send_kwargs
            )

    @staticmethod
    async def _send_media_url(
        url: str,
        media_type: MediaType,
        caption: str,
        context: ContextTypes.DEFAULT_TYPE
    ) -> Message:
        send_kwargs = {
            'chat_id': CHARA_CHANNEL_ID,
            'caption': caption,
            'parse_mode': 'HTML',
            'read_timeout': Config.UPLOAD_TIMEOUT,
            'write_timeout': Config.UPLOAD_TIMEOUT,
            'connect_timeout': 60,
            'pool_timeout': 60
        }
        
        try:
            if media_type == MediaType.VIDEO:
                return await context.bot.send_video(
                    video=url,
                    supports_streaming=True,
                    **send_kwargs
                )
            elif media_type == MediaType.ANIMATION:
                return await context.bot.send_animation(
                    animation=url,
                    **send_kwargs
                )
            else:
                return await context.bot.send_photo(
                    photo=url,
                    **send_kwargs
                )
        except TelegramError:
            return await context.bot.send_document(
                document=url,
                **send_kwargs
            )


class TextFormatter:
    @staticmethod
    @lru_cache(maxsize=256)
    def format_name(name: str) -> str:
        return name.replace('-', ' ').replace('_', ' ').title().strip()


class CharacterFactory:
    @staticmethod
    async def create_from_args(
        args: List[str],
        media_file: MediaFile,
        user_id: str,
        user_name: str
    ) -> Optional[Character]:
        if len(args) < 3:
            return None
        
        character_name = TextFormatter.format_name(args[0])
        anime = TextFormatter.format_name(args[1])
        
        try:
            rarity_num = int(args[2])
            rarity = RarityLevel.from_number(rarity_num)
            if not rarity:
                return None
        except ValueError:
            return None
        
        char_id = await SequenceGenerator.get_next_id('character_id')
        
        from datetime import datetime
        timestamp = datetime.utcnow().isoformat()
        
        return Character(
            character_id=char_id,
            name=character_name,
            anime=anime,
            rarity=rarity,
            media_file=media_file,
            uploader_id=user_id,
            uploader_name=user_name,
            created_at=timestamp,
            updated_at=timestamp
        )


class ProgressTracker:
    def __init__(self, message: Message):
        self.message = message
        self.last_update = 0
        self.update_interval = 2
        
    async def update(self, current: int, total: int):
        import time
        now = time.time()
        
        if now - self.last_update < self.update_interval and current < total:
            return
        
        self.last_update = now
        percent = (current / total * 100) if total > 0 else 0
        
        progress_bar = self._create_progress_bar(percent)
        size_mb = current / (1024 * 1024)
        total_mb = total / (1024 * 1024)
        
        try:
            await self.message.edit_text(
                f'⏳ Progress: {progress_bar} {percent:.1f}%\n'
                f'📊 {size_mb:.2f} MB / {total_mb:.2f} MB'
            )
        except Exception:
            pass
    
    @staticmethod
    def _create_progress_bar(percent: float, length: int = 10) -> str:
        filled = int(length * percent / 100)
        return '█' * filled + '░' * (length - filled)


class CharacterUploadHandler:
    @staticmethod
    async def handle_reply_upload(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        reply_msg = update.message.reply_to_message
        
        if not (reply_msg.photo or reply_msg.video or reply_msg.document or reply_msg.animation):
            await update.message.reply_text(
                '❌ Please reply to a photo, video, animation, or document!'
            )
            return
        
        if len(context.args) != 3:
            await update.message.reply_text(
                '❌ Format: `/upload character-name anime-name rarity-number`\n'
                'Example: `/upload muzan-kibutsuji Demon-slayer 3`'
            )
            return
        
        processing_msg = await update.message.reply_text('⏳ Extracting file...')
        
        media_file = await CharacterUploadHandler._extract_media_from_reply(
            reply_msg, update
        )
        
        if not media_file:
            await processing_msg.edit_text('❌ Failed to extract media file.')
            return
        
        if not media_file.is_valid_size:
            await processing_msg.edit_text(
                f'❌ File too large! Maximum size: {Config.MAX_FILE_SIZE / (1024 * 1024):.1f} MB'
            )
            return
        
        # Enhance image quality if applicable
        if ImageEnhancer.should_enhance(media_file.media_type, media_file.mime_type):
            await processing_msg.edit_text('✨ Enhancing image quality...')
            media_file.enhance_if_applicable()
        
        progress = ProgressTracker(processing_msg)
        await processing_msg.edit_text('⏳ Uploading to Catbox...')
        
        catbox_url = await CatboxUploader.upload_with_progress(
            media_file.file_bytes,
            media_file.filename,
            progress.update
        )
        
        if not catbox_url:
            await processing_msg.edit_text('❌ Catbox upload failed. Please retry.')
            return
        
        object.__setattr__(media_file, 'url', catbox_url)
        await processing_msg.edit_text('✅ Catbox uploaded!\n⏳ Creating character...')
        
        character = await CharacterFactory.create_from_args(
            context.args,
            media_file,
            str(update.effective_user.id),
            update.effective_user.first_name
        )
        
        if not character:
            await processing_msg.edit_text('❌ Invalid rarity number (1-20).')
            return
        
        result = await TelegramUploader.upload_character(character, context)
        await processing_msg.edit_text(result.message)

    @staticmethod
    async def _extract_media_from_reply(
        reply_msg,
        update: Update
    ) -> Optional[MediaFile]:
        try:
            if reply_msg.photo:
                file = await reply_msg.photo[-1].get_file()
                filename = f"char_{update.effective_user.id}_{reply_msg.photo[-1].file_unique_id}.jpg"
                media_type = MediaType.IMAGE
                mime_type = 'image/jpeg'
            elif reply_msg.video:
                file = await reply_msg.video.get_file()
                filename = f"char_{update.effective_user.id}_{reply_msg.video.file_unique_id}.mp4"
                media_type = MediaType.VIDEO
                mime_type = reply_msg.video.mime_type
            elif reply_msg.animation:
                file = await reply_msg.animation.get_file()
                filename = f"char_{update.effective_user.id}_{reply_msg.animation.file_unique_id}.gif"
                media_type = MediaType.ANIMATION
                mime_type = reply_msg.animation.mime_type
            else:
                file = await reply_msg.document.get_file()
                filename = reply_msg.document.file_name or f"char_{update.effective_user.id}_{reply_msg.document.file_unique_id}"
                mime_type = reply_msg.document.mime_type
                media_type = MediaType.from_mime(mime_type)
            
            file_bytes = bytes(await file.download_as_bytearray())
            
            return MediaFile(
                url="",
                file_bytes=file_bytes,
                media_type=media_type,
                filename=filename,
                mime_type=mime_type,
                size=len(file_bytes)
            )
        except Exception as e:
            print(f"Media extraction error: {type(e).__name__}: {e}")
            return None

    @staticmethod
    async def handle_url_upload(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if len(context.args) != 4:
            await update.message.reply_text(
                '❌ Format: `/upload URL character-name anime-name rarity-number`\n'
                'Example: `/upload https://example.com/img.jpg muzan Demon-slayer 3`'
            )
            return
        
        media_url = context.args[0]
        processing_msg = await update.message.reply_text('⏳ Downloading from URL...')
        
        try:
            progress = ProgressTracker(processing_msg)
            file_bytes = await FileDownloader.download_with_progress(
                media_url,
                progress.update
            )
        except ValueError as e:
            await processing_msg.edit_text(f'❌ {str(e)}')
            return
        except Exception as e:
            await processing_msg.edit_text(
                f'❌ Download failed: {type(e).__name__}\n\n'
                '💡 Possible issues:\n'
                '• URL is not a direct media link\n'
                '• Server blocking requests\n'
                '• File requires authentication\n\n'
                'Try downloading and replying to the file instead.'
            )
            return
        
        if not file_bytes:
            await processing_msg.edit_text('❌ Failed to download. Check URL validity.')
            return
        
        media_file = MediaFile(url=media_url, file_bytes=file_bytes)
        
        if not media_file.is_valid_size:
            await processing_msg.edit_text(
                f'❌ File exceeds {Config.MAX_FILE_SIZE / (1024 * 1024):.1f} MB limit!'
            )
            return
        
        # Enhance image quality if applicable
        if ImageEnhancer.should_enhance(media_file.media_type, media_file.mime_type):
            await processing_msg.edit_text('✨ Enhancing image quality...')
            media_file.enhance_if_applicable()
        
        await processing_msg.edit_text('⏳ Uploading to Catbox...')
        
        catbox_url = await CatboxUploader.upload_with_progress(
            file_bytes,
            media_file.filename,
            progress.update
        )
        
        if not catbox_url:
            await processing_msg.edit_text('❌ Catbox upload failed.')
            return
        
        object.__setattr__(media_file, 'url', catbox_url)
        await processing_msg.edit_text('✅ Uploaded!\n⏳ Saving character...')
        
        character = await CharacterFactory.create_from_args(
            context.args[1:],
            media_file,
            str(update.effective_user.id),
            update.effective_user.first_name
        )
        
        if not character:
            await processing_msg.edit_text('❌ Invalid rarity number (1-20).')
            return
        
        result = await TelegramUploader.upload_character(character, context)
        await processing_msg.edit_text(result.message)


class CharacterDeletionHandler:
    @staticmethod
    async def delete_character(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if len(context.args) != 1:
            await update.message.reply_text(
                '❌ Format: `/delete ID`\n'
                'Example: `/delete 01`'
            )
            return
        
        char_id = context.args[0]
        processing_msg = await update.message.reply_text(f'⏳ Deleting character {char_id}...')
        
        character = await collection.find_one_and_delete({'id': char_id})
        
        if not character:
            await processing_msg.edit_text(f'❌ Character {char_id} not found.')
            return
        
        deletion_tasks = []
        
        if character.get('message_id'):
            deletion_tasks.append(
                CharacterDeletionHandler._delete_channel_message(
                    context,
                    character['message_id']
                )
            )
        
        await asyncio.gather(*deletion_tasks, return_exceptions=True)
        
        await processing_msg.edit_text(
            f'✅ Character deleted successfully!\n'
            f'🆔 ID: {char_id}\n'
            f'📝 Name: {character.get("name", "Unknown")}'
        )

    @staticmethod
    async def _delete_channel_message(
        context: ContextTypes.DEFAULT_TYPE,
        message_id: int
    ) -> None:
        try:
            await context.bot.delete_message(
                chat_id=CHARA_CHANNEL_ID,
                message_id=message_id
            )
        except Exception as e:
            print(f"Channel message deletion failed: {type(e).__name__}")


class CharacterUpdateHandler:
    VALID_FIELDS = {'img_url', 'name', 'anime', 'rarity'}
    
    @staticmethod
    async def update_character(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if len(context.args) != 3:
            await update.message.reply_text(
                '❌ Format: `/update ID field new_value`\n\n'
                'Valid fields: img_url, name, anime, rarity\n\n'
                'Examples:\n'
                '• `/update 01 name New-Name`\n'
                '• `/update 01 rarity 5`\n'
                '• `/update 01 img_url https://example.com/new.jpg`'
            )
            return
        
        char_id, field, new_value = context.args
        
        if field not in CharacterUpdateHandler.VALID_FIELDS:
            await update.message.reply_text(
                f'❌ Invalid field: {field}\n'
                f'Valid fields: {", ".join(CharacterUpdateHandler.VALID_FIELDS)}'
            )
            return
        
        character_data = await collection.find_one({'id': char_id})
        
        if not character_data:
            await update.message.reply_text(f'❌ Character {char_id} not found.')
            return
        
        processing_msg = await update.message.reply_text(f'⏳ Updating {field}...')
        
        try:
            update_data = await CharacterUpdateHandler._process_field_update(
                field,
                new_value,
                processing_msg,
                update
            )
            
            if update_data is None:
                return
            
            from datetime import datetime
            update_data['updated_at'] = datetime.utcnow().isoformat()
            
            await collection.find_one_and_update(
                {'id': char_id},
                {'$set': update_data}
            )
            
            await CharacterUpdateHandler._update_channel_message(
                char_id,
                field,
                context,
                update.effective_user,
                processing_msg
            )
            
        except Exception as e:
            await processing_msg.edit_text(
                f'❌ Update failed: {type(e).__name__}\n{str(e)}'
            )

    @staticmethod
    async def _process_field_update(
        field: str,
        new_value: str,
        processing_msg: Message,
        update: Update
    ) -> Optional[Dict[str, Any]]:
        if field in ['name', 'anime']:
            return {field: TextFormatter.format_name(new_value)}
        
        elif field == 'rarity':
            try:
                rarity_num = int(new_value)
                rarity = RarityLevel.from_number(rarity_num)
                if not rarity:
                    await processing_msg.edit_text('❌ Invalid rarity (1-20).')
                    return None
                return {field: rarity.display_name}
            except ValueError:
                await processing_msg.edit_text('❌ Rarity must be a number.')
                return None
        
        elif field == 'img_url':
            await processing_msg.edit_text('⏳ Downloading new media...')
            
            try:
                progress = ProgressTracker(processing_msg)
                file_bytes = await FileDownloader.download_with_progress(
                    new_value,
                    progress.update
                )
            except Exception as e:
                await processing_msg.edit_text(f'❌ Download failed: {type(e).__name__}')
                return None
            
            if not file_bytes:
                await processing_msg.edit_text('❌ Failed to download media.')
                return None
            
            media_file = MediaFile(url=new_value, file_bytes=file_bytes)
            
            if not media_file.is_valid_size:
                await processing_msg.edit_text('❌ File size exceeds limit.')
                return None
            
            # Enhance image quality if applicable
            was_enhanced = False
            if ImageEnhancer.should_enhance(media_file.media_type, media_file.mime_type):
                await processing_msg.edit_text('✨ Enhancing image quality...')
                media_file.enhance_if_applicable()
                was_enhanced = media_file.was_enhanced
            
            await processing_msg.edit_text('⏳ Uploading to Catbox...')
            
            catbox_url = await CatboxUploader.upload_with_progress(
                media_file.file_bytes,
                media_file.filename,
                progress.update
            )
            
            if not catbox_url:
                await processing_msg.edit_text('❌ Catbox upload failed.')
                return None
            
            enhanced_note = " (✨ Enhanced)" if was_enhanced else ""
            await processing_msg.edit_text(f'✅ Re-uploaded to Catbox!{enhanced_note}')
            
            return {
                'img_url': catbox_url,
                'is_video': media_file.is_video,
                'media_type': media_file.media_type.value,
                'file_hash': media_file.hash,
                'was_enhanced': was_enhanced
            }
        
        return None

    @staticmethod
    async def _update_channel_message(
        char_id: str,
        field: str,
        context: ContextTypes.DEFAULT_TYPE,
        user,
        processing_msg: Message
    ) -> None:
        character_data = await collection.find_one({'id': char_id})
        
        if not character_data:
            return
        
        is_video_file = character_data.get('is_video', False)
        media_type = character_data.get('media_type', 'image')
        was_enhanced = character_data.get('was_enhanced', False)
        
        media_type_display = {
            'video': '🎥 Video',
            'image': '🖼 Image',
            'animation': '🎬 Animation',
            'document': '📄 Document'
        }.get(media_type, '🖼 Image')
        
        quality_badge = " ✨ Enhanced" if was_enhanced else ""
        
        rarity_text = character_data['rarity']
        emoji = rarity_text.split()[0]
        
        caption = (
            f'<b>{character_data["id"]}:</b> {character_data["name"]}\n'
            f'<b>{character_data["anime"]}</b>\n'
            f'<b>{emoji} 𝙍𝘼𝙍𝙄𝙏𝙔:</b> {rarity_text[2:]}\n'
            f'<b>Type:</b> {media_type_display}{quality_badge}\n\n'
            f'𝑼𝒑𝒅𝒂𝒕𝒆𝒅 𝑩𝒚 ➥ <a href="tg://user?id={user.id}">{user.first_name}</a>'
        )
        
        try:
            if field == 'img_url':
                await CharacterUpdateHandler._replace_channel_media(
                    character_data,
                    caption,
                    context,
                    char_id
                )
            else:
                await context.bot.edit_message_caption(
                    chat_id=CHARA_CHANNEL_ID,
                    message_id=character_data['message_id'],
                    caption=caption,
                    parse_mode='HTML'
                )
            
            await processing_msg.edit_text(
                f'✅ Character updated successfully!\n'
                f'🆔 ID: {char_id}\n'
                f'📝 Field: {field}'
            )
            
        except Exception as e:
            await processing_msg.edit_text(
                f'⚠️ Database updated but channel sync failed.\n'
                f'Error: {type(e).__name__}'
            )

    @staticmethod
    async def _replace_channel_media(
        character_data: Dict,
        caption: str,
        context: ContextTypes.DEFAULT_TYPE,
        char_id: str
    ) -> None:
        try:
            await context.bot.delete_message(
                chat_id=CHARA_CHANNEL_ID,
                message_id=character_data['message_id']
            )
        except Exception:
            pass
        
        new_url = character_data['img_url']
        media_type = MediaType(character_data.get('media_type', 'image'))
        
        message = await TelegramUploader._send_media_url(
            new_url,
            media_type,
            caption,
            context
        )
        
        update_fields = {'message_id': message.message_id}
        
        if message.video:
            update_fields['file_id'] = message.video.file_id
            update_fields['file_unique_id'] = message.video.file_unique_id
        elif message.photo:
            update_fields['file_id'] = message.photo[-1].file_id
            update_fields['file_unique_id'] = message.photo[-1].file_unique_id
        elif message.animation:
            update_fields['file_id'] = message.animation.file_id
            update_fields['file_unique_id'] = message.animation.file_unique_id
        elif message.document:
            update_fields['file_id'] = message.document.file_id
            update_fields['file_unique_id'] = message.document.file_unique_id
        
        await collection.find_one_and_update(
            {'id': char_id},
            {'$set': update_fields}
        )


def require_sudo(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        if user_id not in sudo_users:
            await update.message.reply_text(
                '❌ Access Denied\n\n'
                'This command requires sudo privileges.\n'
                f'Contact: {SUPPORT_CHAT}'
            )
            return
        return await func(update, context)
    return wrapper


@require_sudo
async def upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if update.message.reply_to_message:
            await CharacterUploadHandler.handle_reply_upload(update, context)
        else:
            await CharacterUploadHandler.handle_url_upload(update, context)
    except Exception as e:
        error_msg = (
            f'❌ Upload Failed\n\n'
            f'Error: {type(e).__name__}\n'
            f'Details: {str(e)}\n\n'
            f'Support: {SUPPORT_CHAT}'
        )
        await update.message.reply_text(error_msg)


@require_sudo
async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await CharacterDeletionHandler.delete_character(update, context)
    except Exception as e:
        await update.message.reply_text(
            f'❌ Deletion failed: {type(e).__name__}\n{str(e)}'
        )


@require_sudo
async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await CharacterUpdateHandler.update_character(update, context)
    except Exception as e:
        await update.message.reply_text(
            f'❌ Update failed: {type(e).__name__}\n{str(e)}'
        )


application.add_handler(CommandHandler('upload', upload_command, block=False))
application.add_handler(CommandHandler('delete', delete_command, block=False))
application.add_handler(CommandHandler('update', update_command, block=False))