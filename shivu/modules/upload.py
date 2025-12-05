""" v3 with AI-powered image enhancement """

import io
import asyncio
import hashlib
import base64
from dataclasses import dataclass, field
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
from PIL import Image, ImageEnhance, ImageFilter, ImageStat

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
    
    # AI Enhancement settings
    USE_AI_ENHANCEMENT: bool = True
    AI_ENHANCEMENT_THRESHOLD: float = 0.6  # Only enhance if quality score < 0.6
    
    # API Keys (set these in your environment or config)
    CLIPDROP_API_KEY: str = ""  # https://clipdrop.co/apis
    DEEPAI_API_KEY: str = ""    # https://deepai.org/
    
    # Fallback enhancement settings
    ENHANCE_SHARPNESS: float = 1.3
    ENHANCE_CONTRAST: float = 1.15
    ENHANCE_COLOR: float = 1.1
    ENHANCE_BRIGHTNESS: float = 1.05
    JPEG_QUALITY: int = 95
    PNG_OPTIMIZE: bool = True
    MAX_IMAGE_DIMENSION: int = 4096


@dataclass
class ImageQualityMetrics:
    """Stores image quality analysis metrics"""
    sharpness_score: float = 0.0
    contrast_score: float = 0.0
    brightness_score: float = 0.0
    color_variance: float = 0.0
    overall_quality: float = 0.0
    needs_enhancement: bool = False
    recommended_enhancements: List[str] = field(default_factory=list)
    
    def __str__(self) -> str:
        return (
            f"Quality: {self.overall_quality:.2f} | "
            f"Sharpness: {self.sharpness_score:.2f} | "
            f"Contrast: {self.contrast_score:.2f}"
        )


class ImageQualityAnalyzer:
    """Analyzes image quality to determine if enhancement is needed"""
    
    @staticmethod
    def analyze_image(image_bytes: bytes) -> ImageQualityMetrics:
        """
        Analyzes image quality and returns metrics
        """
        try:
            img = Image.open(io.BytesIO(image_bytes))
            
            # Convert to RGB if needed
            if img.mode != 'RGB':
                if img.mode == 'RGBA':
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    img = background
                else:
                    img = img.convert('RGB')
            
            metrics = ImageQualityMetrics()
            
            # Calculate sharpness (Laplacian variance)
            metrics.sharpness_score = ImageQualityAnalyzer._calculate_sharpness(img)
            
            # Calculate contrast
            metrics.contrast_score = ImageQualityAnalyzer._calculate_contrast(img)
            
            # Calculate brightness
            metrics.brightness_score = ImageQualityAnalyzer._calculate_brightness(img)
            
            # Calculate color variance
            metrics.color_variance = ImageQualityAnalyzer._calculate_color_variance(img)
            
            # Overall quality score (weighted average)
            metrics.overall_quality = (
                metrics.sharpness_score * 0.35 +
                metrics.contrast_score * 0.30 +
                metrics.brightness_score * 0.20 +
                metrics.color_variance * 0.15
            )
            
            # Determine if enhancement is needed
            metrics.needs_enhancement = metrics.overall_quality < Config.AI_ENHANCEMENT_THRESHOLD
            
            # Recommend specific enhancements
            if metrics.sharpness_score < 0.5:
                metrics.recommended_enhancements.append("sharpness")
            if metrics.contrast_score < 0.5:
                metrics.recommended_enhancements.append("contrast")
            if metrics.brightness_score < 0.4 or metrics.brightness_score > 0.8:
                metrics.recommended_enhancements.append("brightness")
            if metrics.color_variance < 0.3:
                metrics.recommended_enhancements.append("color")
            
            return metrics
            
        except Exception as e:
            print(f"Quality analysis failed: {e}")
            # Return default metrics that suggest enhancement
            return ImageQualityMetrics(
                overall_quality=0.5,
                needs_enhancement=True,
                recommended_enhancements=["general"]
            )
    
    @staticmethod
    def _calculate_sharpness(img: Image.Image) -> float:
        """Calculate image sharpness using Laplacian variance"""
        try:
            # Convert to grayscale
            gray = img.convert('L')
            # Apply Laplacian filter
            edges = gray.filter(ImageFilter.FIND_EDGES)
            # Calculate variance
            stat = ImageStat.Stat(edges)
            variance = stat.var[0]
            # Normalize to 0-1 (typical variance range: 0-10000)
            return min(variance / 10000.0, 1.0)
        except:
            return 0.5
    
    @staticmethod
    def _calculate_contrast(img: Image.Image) -> float:
        """Calculate image contrast"""
        try:
            stat = ImageStat.Stat(img.convert('L'))
            # Standard deviation indicates contrast
            stddev = stat.stddev[0]
            # Normalize (typical range: 0-128)
            return min(stddev / 128.0, 1.0)
        except:
            return 0.5
    
    @staticmethod
    def _calculate_brightness(img: Image.Image) -> float:
        """Calculate image brightness"""
        try:
            stat = ImageStat.Stat(img.convert('L'))
            # Mean brightness (0-255)
            brightness = stat.mean[0]
            # Normalize to 0-1
            return brightness / 255.0
        except:
            return 0.5
    
    @staticmethod
    def _calculate_color_variance(img: Image.Image) -> float:
        """Calculate color variance/saturation"""
        try:
            hsv = img.convert('HSV')
            stat = ImageStat.Stat(hsv)
            # Saturation channel variance
            sat_variance = stat.var[1] if len(stat.var) > 1 else 0
            # Normalize
            return min(sat_variance / 10000.0, 1.0)
        except:
            return 0.5


class AIImageEnhancer:
    """Uses AI APIs to enhance images intelligently"""
    
    @staticmethod
    async def enhance_with_clipdrop(image_bytes: bytes) -> Optional[bytes]:
        """
        Enhance image using Clipdrop Image Upscaler API
        https://clipdrop.co/apis/docs/image-upscaling
        """
        if not Config.CLIPDROP_API_KEY:
            return None
        
        try:
            async with SessionManager.get_session() as session:
                form = aiohttp.FormData()
                form.add_field('image_file', image_bytes, 
                             filename='image.jpg',
                             content_type='image/jpeg')
                form.add_field('target_width', '2048')
                form.add_field('target_height', '2048')
                
                headers = {'x-api-key': Config.CLIPDROP_API_KEY}
                
                async with session.post(
                    'https://clipdrop-api.co/image-upscaling/v1/upscale',
                    data=form,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        return await response.read()
                    else:
                        print(f"Clipdrop API error: {response.status}")
                        return None
        except Exception as e:
            print(f"Clipdrop enhancement failed: {e}")
            return None
    
    @staticmethod
    async def enhance_with_deepai(image_bytes: bytes) -> Optional[bytes]:
        """
        Enhance image using DeepAI Image Super Resolution
        https://deepai.org/machine-learning-model/torch-srgan
        """
        if not Config.DEEPAI_API_KEY:
            return None
        
        try:
            async with SessionManager.get_session() as session:
                form = aiohttp.FormData()
                form.add_field('image', image_bytes,
                             filename='image.jpg',
                             content_type='image/jpeg')
                
                headers = {'api-key': Config.DEEPAI_API_KEY}
                
                async with session.post(
                    'https://api.deepai.org/api/torch-srgan',
                    data=form,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        output_url = result.get('output_url')
                        
                        if output_url:
                            # Download enhanced image
                            async with session.get(output_url) as img_response:
                                if img_response.status == 200:
                                    return await img_response.read()
                    return None
        except Exception as e:
            print(f"DeepAI enhancement failed: {e}")
            return None
    
    @staticmethod
    async def enhance_with_replicate(image_bytes: bytes) -> Optional[bytes]:
        """
        Enhance using Replicate Real-ESRGAN
        Free alternative using public API
        """
        try:
            # Convert to base64
            b64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            async with SessionManager.get_session() as session:
                payload = {
                    "version": "42fed1c4974146d4d2414e2be2c5277c7fcf05fcc3a73abf41610695738c1d7b",
                    "input": {
                        "image": f"data:image/jpeg;base64,{b64_image}",
                        "scale": 2,
                        "face_enhance": False
                    }
                }
                
                # This is a simplified example - you'd need proper Replicate API integration
                # For now, we'll skip this as it requires API token
                return None
        except Exception as e:
            print(f"Replicate enhancement failed: {e}")
            return None


class ImageEnhancer:
    """Handles intelligent image enhancement with AI and fallback methods"""
    
    @staticmethod
    async def enhance_image_smart(
        image_bytes: bytes, 
        filename: str,
        progress_callback=None
    ) -> Tuple[bytes, bool, str]:
        """
        Intelligently enhance image based on quality analysis
        Returns: (enhanced_bytes, was_enhanced, enhancement_method)
        """
        try:
            # Step 1: Analyze image quality
            if progress_callback:
                await progress_callback("🔍 Analyzing image quality...")
            
            metrics = ImageQualityAnalyzer.analyze_image(image_bytes)
            print(f"Image Quality Metrics: {metrics}")
            
            # Step 2: If image is already high quality, skip enhancement
            if not metrics.needs_enhancement and not Config.USE_AI_ENHANCEMENT:
                return image_bytes, False, "none"
            
            # Step 3: Try AI enhancement if quality is low
            if Config.USE_AI_ENHANCEMENT and metrics.needs_enhancement:
                # Try Clipdrop first (best quality)
                if Config.CLIPDROP_API_KEY:
                    if progress_callback:
                        await progress_callback("🤖 AI Enhancement (Clipdrop)...")
                    
                    enhanced = await AIImageEnhancer.enhance_with_clipdrop(image_bytes)
                    if enhanced:
                        return enhanced, True, "ai-clipdrop"
                
                # Try DeepAI as fallback
                if Config.DEEPAI_API_KEY:
                    if progress_callback:
                        await progress_callback("🤖 AI Enhancement (DeepAI)...")
                    
                    enhanced = await AIImageEnhancer.enhance_with_deepai(image_bytes)
                    if enhanced:
                        return enhanced, True, "ai-deepai"
            
            # Step 4: Fallback to PIL-based enhancement
            if progress_callback:
                await progress_callback("✨ Applying standard enhancement...")
            
            enhanced = ImageEnhancer._enhance_with_pil(
                image_bytes, 
                filename, 
                metrics
            )
            return enhanced, True, "pil-enhanced"
            
        except Exception as e:
            print(f"Image enhancement failed: {e}")
            return image_bytes, False, "failed"
    
    @staticmethod
    def _enhance_with_pil(
        image_bytes: bytes, 
        filename: str,
        metrics: ImageQualityMetrics
    ) -> bytes:
        """
        Traditional PIL-based enhancement with adaptive parameters
        based on quality metrics
        """
        img = Image.open(io.BytesIO(image_bytes))
        
        # Convert RGBA to RGB
        if img.mode == 'RGBA':
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        elif img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        
        # Resize if needed
        img = ImageEnhancer._resize_if_needed(img)
        
        # Adaptive enhancements based on metrics
        if "sharpness" in metrics.recommended_enhancements:
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.4)  # More aggressive
        elif metrics.sharpness_score < 0.7:
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(Config.ENHANCE_SHARPNESS)
        
        if "contrast" in metrics.recommended_enhancements:
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.25)
        elif metrics.contrast_score < 0.7:
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(Config.ENHANCE_CONTRAST)
        
        if "color" in metrics.recommended_enhancements:
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(1.2)
        
        if "brightness" in metrics.recommended_enhancements:
            if metrics.brightness_score < 0.4:
                enhancer = ImageEnhance.Brightness(img)
                img = enhancer.enhance(1.15)
            elif metrics.brightness_score > 0.8:
                enhancer = ImageEnhance.Brightness(img)
                img = enhancer.enhance(0.95)
        
        # Apply unsharp mask for final touch
        img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=120, threshold=3))
        
        # Save with optimal settings
        output = io.BytesIO()
        save_format = 'PNG' if filename.lower().endswith('.png') else 'JPEG'
        
        if save_format == 'JPEG':
            img.save(output, format='JPEG', quality=Config.JPEG_QUALITY, 
                    optimize=True, progressive=True)
        else:
            img.save(output, format='PNG', optimize=Config.PNG_OPTIMIZE, 
                    compress_level=6)
        
        return output.getvalue()
    
    @staticmethod
    def _resize_if_needed(img: Image.Image) -> Image.Image:
        """Resize image if dimensions exceed maximum"""
        max_dim = Config.MAX_IMAGE_DIMENSION
        width, height = img.size
        
        if width <= max_dim and height <= max_dim:
            return img
        
        if width > height:
            new_width = max_dim
            new_height = int((max_dim / width) * height)
        else:
            new_height = max_dim
            new_width = int((max_dim / height) * width)
        
        return img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    @staticmethod
    def should_enhance(media_type: MediaType, mime_type: str) -> bool:
        """Check if file should be enhanced"""
        if media_type != MediaType.IMAGE:
            return False
        
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
    enhancement_method: str = "none"
    quality_metrics: Optional[ImageQualityMetrics] = None

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
    
    async def enhance_if_applicable(self, progress_callback=None) -> None:
        """Enhance image quality if applicable using AI"""
        if not self.file_bytes:
            return
        
        if not ImageEnhancer.should_enhance(self.media_type, self.mime_type):
            return
        
        enhanced_bytes, was_enhanced, method = await ImageEnhancer.enhance_image_smart(
            self.file_bytes,
            self.filename,
            progress_callback
        )
        
        if was_enhanced:
            object.__setattr__(self, 'file_bytes', enhanced_bytes)
            object.__setattr__(self, 'size', len(enhanced_bytes))
            object.__setattr__(self, 'hash', hashlib.sha256(enhanced_bytes).hexdigest())
            object.__setattr__(self, 'was_enhanced', True)
            object.__setattr__(self, 'enhancement_method', method)


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
            'enhancement_method': self.media_file.enhancement_method,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def get_caption(self, is_update: bool = False) -> str:
        media_type_icons = {
            MediaType.VIDEO: "🎥 Video",
            MediaType.IMAGE: "🖼 Image",
            MediaType.ANIMATION: "🎬 Animation",
            MediaType.DOCUMENT: "📄 Document"
        }
        media_display = media_type_icons.get(self.media_file.media_type, "🖼 Image")
        
        # Enhanced badge based on method
        quality_badge = ""
        if self.media_file.was_enhanced:
            if "ai-" in self.media_file.enhancement_method:
                quality_badge = " 🤖 AI Enhanced"
            else:
                quality_badge = " ✨ Enhanced"
        
        action = "𝑼𝒑𝒅𝒂𝒕𝒆𝒅" if is_update else "𝑴𝒂𝒅𝒆"
        
        return (
            f'<b>{self.character_id}:</b> {self.name}\n'
            f'<b>{self.anime}</b>\n'
            f'<b>{self.rarity.emoji} 𝙍𝘼𝙍𝙄𝙏𝙔:</b> {self.rarity.display_name[2:]}\n'
            f'<b>Type:</b> {media_display}{quality_badge}\n\n'
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': url,
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
                        raise ValueError(f"File size exceeds limit")
                    
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
        
        enhancement_note = ""
        if character.media_file.was_enhanced:
            if "ai-" in character.media_file.enhancement_method:
                enhancement_note = " (🤖 AI Enhanced)"
            else:
                enhancement_note = " (✨ Enhanced)"
        
        return UploadResult(
            success=True,
            message=(
                f'✅ Character added successfully!{enhancement_note}\n'
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
    
    async def update_text(self, text: str):
        """Update with custom text"""
        try:
            await self.message.edit_text(text)
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
        
        # Enhance image quality with AI if applicable
        if ImageEnhancer.should_enhance(media_file.media_type, media_file.mime_type):
            progress = ProgressTracker(processing_msg)
            await media_file.enhance_if_applicable(progress.update_text)
        
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
        
        # Enhance image quality with AI if applicable
        if ImageEnhancer.should_enhance(media_file.media_type, media_file.mime_type):
            progress = ProgressTracker(processing_msg)
            await media_file.enhance_if_applicable(progress.update_text)
        
        await processing_msg.edit_text('⏳ Uploading to Catbox...')
        
        catbox_url = await CatboxUploader.upload_with_progress(
            media_file.file_bytes,
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
        
        if character.get('message_id'):
            try:
                await context.bot.delete_message(
                    chat_id=CHARA_CHANNEL_ID,
                    message_id=character['message_id']
                )
            except Exception as e:
                print(f"Channel message deletion failed: {type(e).__name__}")
        
        await processing_msg.edit_text(
            f'✅ Character deleted successfully!\n'
            f'🆔 ID: {char_id}\n'
            f'📝 Name: {character.get("name", "Unknown")}'
        )


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
            
            # Enhance image quality with AI if applicable
            if ImageEnhancer.should_enhance(media_file.media_type, media_file.mime_type):
                progress = ProgressTracker(processing_msg)
                await media_file.enhance_if_applicable(progress.update_text)
            
            await processing_msg.edit_text('⏳ Uploading to Catbox...')
            
            catbox_url = await CatboxUploader.upload_with_progress(
                media_file.file_bytes,
                media_file.filename,
                progress.update
            )
            
            if not catbox_url:
                await processing_msg.edit_text('❌ Catbox upload failed.')
                return None
            
            enhancement_note = ""
            if media_file.was_enhanced:
                if "ai-" in media_file.enhancement_method:
                    enhancement_note = " (🤖 AI Enhanced)"
                else:
                    enhancement_note = " (✨ Enhanced)"
            await processing_msg.edit_text(f'✅ Re-uploaded to Catbox!{enhancement_note}')
            
            return {
                'img_url': catbox_url,
                'is_video': media_file.is_video,
                'media_type': media_file.media_type.value,
                'file_hash': media_file.hash,
                'was_enhanced': media_file.was_enhanced,
                'enhancement_method': media_file.enhancement_method
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
        
        media_type = character_data.get('media_type', 'image')
        was_enhanced = character_data.get('was_enhanced', False)
        enhancement_method = character_data.get('enhancement_method', 'none')
        
        media_type_display = {
            'video': '🎥 Video',
            'image': '🖼 Image',
            'animation': '🎬 Animation',
            'document': '📄 Document'
        }.get(media_type, '🖼 Image')
        
        quality_badge = ""
        if was_enhanced:
            if "ai-" in enhancement_method:
                quality_badge = " 🤖 AI Enhanced"
            else:
                quality_badge = " ✨ Enhanced"
        
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
                # Delete old message and send new one
                try:
                    await context.bot.delete_message(
                        chat_id=CHARA_CHANNEL_ID,
                        message_id=character_data['message_id']
                    )
                except Exception:
                    pass
                
                new_url = character_data['img_url']
                media_type_enum = MediaType(media_type)
                
                message = await TelegramUploader._send_media_url(
                    new_url,
                    media_type_enum,
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
    """
    Upload character with AI-powered image enhancement
    
    Usage:
    - Reply to image: /upload character-name anime-name rarity
    - From URL: /upload URL character-name anime-name rarity
    """
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
    """Delete a character by ID"""
    try:
        await CharacterDeletionHandler.delete_character(update, context)
    except Exception as e:
        await update.message.reply_text(
            f'❌ Deletion failed: {type(e).__name__}\n{str(e)}'
        )


@require_sudo
async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Update character fields with AI enhancement for images"""
    try:
        await CharacterUpdateHandler.update_character(update, context)
    except Exception as e:
        await update.message.reply_text(
            f'❌ Update failed: {type(e).__name__}\n{str(e)}'
        )


# Register command handlers
application.add_handler(CommandHandler('upload', upload_command, block=False))
application.add_handler(CommandHandler('delete', delete_command, block=False))
application.add_handler(CommandHandler('update', update_command, block=False))