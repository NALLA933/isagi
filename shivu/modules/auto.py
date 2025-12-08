import io
import base64
import re
import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List, Tuple
import aiohttp
from pymongo import ReturnDocument
from telegram import Update, InputFile
from telegram.ext import MessageHandler, filters, ContextTypes
from PIL import Image, ImageFilter, ImageStat, ImageEnhance
from shivu import application, collection, db, CHARA_CHANNEL_ID

AUTHORIZED_USER = 5147822244

class RarityLevel(Enum):
    RARE = (2, "🟣 Rare")
    LEGENDARY = (3, "🟡 Legendary")
    SPECIAL = (4, "💮 Special Edition")
    NEON = (5, "💫 Neon")
    MANGA = (6, "✨ Manga")
    CELESTIAL = (8, "🎐 Celestial")
    PREMIUM = (9, "🔮 Premium")
    MYTHIC = (17, "🏵 Mythic")

    def __init__(self, level: int, display: str):
        self._level, self._display = level, display

    @property
    def level(self) -> int: return self._level
    
    @property
    def display_name(self) -> str: return self._display
    
    @property
    def emoji(self) -> str: return self._display.split()[0]

@dataclass
class ImageQuality:
    sharpness: float = 0.0
    contrast: float = 0.0
    brightness: float = 0.0
    resolution: float = 0.0
    color_richness: float = 0.0
    noise_level: float = 0.0
    overall: float = 0.5
    rarity_level: int = 2
    
    def calculate_overall(self):
        """Calculate weighted overall score"""
        self.overall = (
            self.sharpness * 0.25 +
            self.contrast * 0.20 +
            self.brightness * 0.15 +
            self.resolution * 0.20 +
            self.color_richness * 0.12 +
            (1 - self.noise_level) * 0.08
        )
        return self.overall

    def calculate_rarity(self):
        """Map quality score to rarity level with refined thresholds"""
        s = self.overall
        if s >= 0.88:
            self.rarity_level = 17  # Mythic
        elif s >= 0.78:
            self.rarity_level = 9   # Premium
        elif s >= 0.68:
            self.rarity_level = 8   # Celestial
        elif s >= 0.58:
            self.rarity_level = 6   # Manga
        elif s >= 0.48:
            self.rarity_level = 5   # Neon
        elif s >= 0.38:
            self.rarity_level = 4   # Special
        elif s >= 0.28:
            self.rarity_level = 3   # Legendary
        else:
            self.rarity_level = 2   # Rare
        return self.rarity_level

class QualityAnalyzer:
    """Enhanced image quality analysis with multiple metrics"""
    
    @staticmethod
    def analyze(img_bytes: bytes) -> ImageQuality:
        try:
            img = Image.open(io.BytesIO(img_bytes))
            
            # Convert to RGB
            if img.mode == 'RGBA':
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            quality = ImageQuality()
            
            # 1. Sharpness (edge detection)
            gray = img.convert('L')
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_stat = ImageStat.Stat(edges)
            quality.sharpness = min(edge_stat.var[0] / 10000, 1.0)
            
            # 2. Contrast
            gray_stat = ImageStat.Stat(gray)
            quality.contrast = min(gray_stat.stddev[0] / 80, 1.0)
            
            # 3. Brightness (optimal around 128)
            mean_brightness = gray_stat.mean[0]
            quality.brightness = 1.0 - abs(mean_brightness - 128) / 128
            
            # 4. Resolution score
            width, height = img.size
            pixels = width * height
            if pixels >= 2073600:  # 1920x1080
                quality.resolution = 1.0
            elif pixels >= 1228800:  # 1280x960
                quality.resolution = 0.9
            elif pixels >= 921600:  # 1280x720
                quality.resolution = 0.8
            elif pixels >= 518400:  # 720x720
                quality.resolution = 0.7
            elif pixels >= 307200:  # 640x480
                quality.resolution = 0.6
            else:
                quality.resolution = 0.5
            
            # 5. Color richness
            stat = ImageStat.Stat(img)
            color_variance = sum(stat.stddev) / 3
            quality.color_richness = min(color_variance / 100, 1.0)
            
            # 6. Noise level (smoothness)
            blurred = img.filter(ImageFilter.GaussianBlur(1))
            diff = ImageStat.Stat(
                Image.blend(img, blurred, 0.5)
            )
            quality.noise_level = min(diff.stddev[0] / 50, 1.0)
            
            # Calculate final scores
            quality.calculate_overall()
            quality.calculate_rarity()
            
            return quality
            
        except Exception as e:
            print(f"Quality analysis error: {e}")
            return ImageQuality(overall=0.4, rarity_level=2)

class AIIdentifier:
    """Multi-source AI character identification with fallback chain"""
    
    SAUCENAO_API_KEY = None  # Optional: Get from https://saucenao.com/user.php
    TIMEOUT = aiohttp.ClientTimeout(total=25)
    
    @staticmethod
    async def identify(img_bytes: bytes) -> Dict[str, str]:
        """Try multiple identification methods in parallel for best results"""
        
        # Run multiple methods concurrently
        tasks = [
            AIIdentifier._trace_moe(img_bytes),
            AIIdentifier._ascii2d(img_bytes),
            AIIdentifier._iqdb(img_bytes),
        ]
        
        if AIIdentifier.SAUCENAO_API_KEY:
            tasks.append(AIIdentifier._saucenao(img_bytes))
        
        # Wait for all results
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter valid results
        valid_results = []
        for result in results:
            if isinstance(result, dict) and result.get('name') != "Unknown Character":
                valid_results.append(result)
        
        # Return best result (prioritize higher confidence)
        if valid_results:
            # Sort by confidence if available, otherwise return first
            return sorted(
                valid_results, 
                key=lambda x: x.get('confidence', 0.5), 
                reverse=True
            )[0]
        
        return {"name": "Unknown Character", "anime": "Unknown Series", "confidence": 0.0}

    @staticmethod
    async def _trace_moe(img_bytes: bytes) -> Dict[str, str]:
        """Trace.moe - Best for anime screenshots"""
        try:
            b64 = base64.b64encode(img_bytes).decode()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.trace.moe/search",
                    json={"image": b64},
                    timeout=AIIdentifier.TIMEOUT
                ) as response:
                    if response.status != 200:
                        return {"name": "Unknown Character", "anime": "Unknown Series"}
                    
                    data = await response.json()
                    
                    if not data.get('result'):
                        return {"name": "Unknown Character", "anime": "Unknown Series"}
                    
                    # Get best match
                    top = data['result'][0]
                    similarity = top.get('similarity', 0)
                    
                    # Require at least 65% similarity
                    if similarity < 0.65:
                        return {"name": "Unknown Character", "anime": "Unknown Series"}
                    
                    # Extract anime info
                    anilist = top.get('anilist', {})
                    title = anilist.get('title', {})
                    
                    anime = (
                        title.get('english') or 
                        title.get('romaji') or 
                        title.get('native') or 
                        'Unknown Series'
                    )
                    
                    # Extract character from filename
                    filename = top.get('filename', '')
                    char_name = AIIdentifier._extract_character_name(filename)
                    
                    return {
                        "name": char_name,
                        "anime": anime,
                        "confidence": similarity,
                        "source": "trace.moe"
                    }
                    
        except Exception as e:
            print(f"Trace.moe error: {e}")
            return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    async def _saucenao(img_bytes: bytes) -> Dict[str, str]:
        """SauceNAO - Good for artwork"""
        if not AIIdentifier.SAUCENAO_API_KEY:
            return {"name": "Unknown Character", "anime": "Unknown Series"}
        
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('file', img_bytes, filename='image.jpg')
                
                async with session.post(
                    "https://saucenao.com/search.php",
                    data=data,
                    params={
                        'output_type': 2,
                        'api_key': AIIdentifier.SAUCENAO_API_KEY,
                        'db': 999,
                        'numres': 3
                    },
                    timeout=AIIdentifier.TIMEOUT
                ) as response:
                    if response.status != 200:
                        return {"name": "Unknown Character", "anime": "Unknown Series"}
                    
                    result = await response.json()
                    
                    if not result.get('results'):
                        return {"name": "Unknown Character", "anime": "Unknown Series"}
                    
                    # Find best anime/character match
                    for res in result['results']:
                        similarity = float(res.get('header', {}).get('similarity', 0))
                        
                        if similarity < 60:
                            continue
                        
                        data = res.get('data', {})
                        
                        # Extract character
                        characters = data.get('characters')
                        char_name = "Unknown Character"
                        
                        if characters:
                            if isinstance(characters, list):
                                char_name = characters[0]
                            else:
                                char_name = characters
                        elif data.get('title'):
                            char_name = data.get('title')
                        
                        # Extract anime
                        anime = (
                            data.get('source') or 
                            data.get('material') or 
                            data.get('eng_name') or 
                            data.get('jp_name') or 
                            'Unknown Series'
                        )
                        
                        if char_name != "Unknown Character":
                            return {
                                "name": char_name,
                                "anime": anime,
                                "confidence": similarity / 100,
                                "source": "saucenao"
                            }
                    
        except Exception as e:
            print(f"SauceNAO error: {e}")
        
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    async def _ascii2d(img_bytes: bytes) -> Dict[str, str]:
        """ASCII2D - Good for general artwork"""
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('file', img_bytes, filename='image.jpg')
                
                async with session.post(
                    "https://ascii2d.net/search/file",
                    data=data,
                    timeout=AIIdentifier.TIMEOUT
                ) as response:
                    if response.status != 200:
                        return {"name": "Unknown Character", "anime": "Unknown Series"}
                    
                    html = await response.text()
                    
                    # Parse results (color search)
                    pattern = r'<div class="detail-box"[^>]*>.*?<h6[^>]*>(.*?)</h6>.*?<h6[^>]*>(.*?)</h6>'
                    matches = re.findall(pattern, html, re.DOTALL)
                    
                    for match in matches[:3]:  # Check first 3 results
                        char_raw = match[0].strip()
                        anime_raw = match[1].strip()
                        
                        # Clean HTML tags
                        char_name = re.sub(r'<[^>]+>', '', char_raw).strip()
                        anime_name = re.sub(r'<[^>]+>', '', anime_raw).strip()
                        
                        if char_name and anime_name and len(char_name) > 2:
                            return {
                                "name": char_name,
                                "anime": anime_name,
                                "confidence": 0.7,
                                "source": "ascii2d"
                            }
                    
        except Exception as e:
            print(f"ASCII2D error: {e}")
        
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    async def _iqdb(img_bytes: bytes) -> Dict[str, str]:
        """IQDB - Basic but reliable"""
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('file', img_bytes, filename='image.jpg')
                
                async with session.post(
                    "https://iqdb.org/",
                    data=data,
                    timeout=AIIdentifier.TIMEOUT
                ) as response:
                    if response.status != 200:
                        return {"name": "Unknown Character", "anime": "Unknown Series"}
                    
                    html = await response.text()
                    
                    # Look for match with good similarity
                    if 'No relevant matches' in html:
                        return {"name": "Unknown Character", "anime": "Unknown Series"}
                    
                    # Parse table results
                    pattern = r'<td[^>]*class=["\']image["\'][^>]*>.*?alt=["\']([^"\']+)["\']'
                    match = re.search(pattern, html, re.DOTALL)
                    
                    if match:
                        text = match.group(1).strip()
                        
                        # Try to split character/anime
                        if '/' in text or '-' in text:
                            separator = '/' if '/' in text else '-'
                            parts = [p.strip() for p in text.split(separator)]
                            
                            if len(parts) >= 2:
                                return {
                                    "name": parts[1] if len(parts[1]) > len(parts[0]) else parts[0],
                                    "anime": parts[0] if len(parts[1]) > len(parts[0]) else parts[1],
                                    "confidence": 0.65,
                                    "source": "iqdb"
                                }
                    
        except Exception as e:
            print(f"IQDB error: {e}")
        
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    def _extract_character_name(filename: str) -> str:
        """Extract and clean character name from filename"""
        if not filename:
            return "Unknown Character"
        
        # Remove extension
        name = re.sub(r'\.[^.]+$', '', filename)
        
        # Remove common patterns
        name = re.sub(r'\[.*?\]', '', name)  # Remove [brackets]
        name = re.sub(r'\(.*?\)', '', name)  # Remove (parentheses)
        name = re.sub(r'[\-_]', ' ', name)   # Replace - and _ with space
        name = re.sub(r'\d+', '', name)      # Remove numbers
        name = re.sub(r'\s+', ' ', name)     # Normalize spaces
        
        # Split and capitalize
        parts = [p.strip().title() for p in name.split() if len(p) > 1]
        
        # Take first 3 meaningful words
        result = ' '.join(parts[:3]) if parts else "Unknown Character"
        
        return result if len(result) > 3 else "Unknown Character"

class SequenceGen:
    """Generate sequential IDs for characters"""
    
    @staticmethod
    async def get_next_id() -> str:
        doc = await db.sequences.find_one_and_update(
            {'_id': 'character_id'},
            {'$inc': {'sequence_value': 1}},
            return_document=ReturnDocument.AFTER,
            upsert=True
        )
        seq = doc.get('sequence_value', 0)
        return str(seq).zfill(4)  # 4-digit padding

class Uploader:
    """Handle file uploads and channel posting"""
    
    @staticmethod
    async def upload_to_catbox(file_bytes: bytes, filename: str) -> Optional[str]:
        """Upload to Catbox.moe"""
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('reqtype', 'fileupload')
                data.add_field('fileToUpload', file_bytes, filename=filename)
                
                async with session.post(
                    "https://catbox.moe/user/api.php",
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        url = (await response.text()).strip()
                        if url.startswith('http'):
                            return url
        except Exception as e:
            print(f"Catbox upload error: {e}")
        return None

    @staticmethod
    async def send_to_channel(char_data: Dict, file_bytes: bytes, context):
        """Send character to Telegram channel"""
        try:
            caption = (
                f'<b>🆔 ID:</b> {char_data["id"]}\n'
                f'<b>👤 Name:</b> {char_data["name"]}\n'
                f'<b>📺 Anime:</b> {char_data["anime"]}\n'
                f'<b>{char_data["rarity_emoji"]} Rarity:</b> {char_data["rarity_name"]}\n'
                f'<b>⭐ Quality:</b> {char_data["quality_score"]:.2f}/1.00\n\n'
                f'<i>Auto-uploaded by</i> <a href="tg://user?id={char_data["uploader_id"]}">{char_data["uploader_name"]}</a>'
            )

            file_obj = io.BytesIO(file_bytes)
            file_obj.name = f"{char_data['id']}.jpg"
            
            msg = await context.bot.send_photo(
                chat_id=CHARA_CHANNEL_ID,
                photo=InputFile(file_obj),
                caption=caption,
                parse_mode='HTML'
            )
            
            return msg
            
        except Exception as e:
            print(f"Channel send error: {e}")
            return None

async def auto_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main handler for auto-uploading characters"""
    try:
        # Security check
        if update.effective_user.id != AUTHORIZED_USER:
            return
        
        if not update.message or not update.message.photo:
            return

        msg = update.message
        status_msg = await msg.reply_text('🔄 <b>Processing image...</b>', parse_mode='HTML')

        # Step 1: Download image
        await status_msg.edit_text('📥 <b>Downloading image...</b>', parse_mode='HTML')
        photo = msg.photo[-1]
        file = await photo.get_file()
        file_bytes = bytes(await file.download_as_bytearray())

        # Step 2: Analyze quality
        await status_msg.edit_text('📊 <b>Analyzing quality...</b>', parse_mode='HTML')
        quality = QualityAnalyzer.analyze(file_bytes)

        # Step 3: Identify character (parallel AI search)
        await status_msg.edit_text('🤖 <b>Identifying character...</b>\n<i>Searching multiple sources...</i>', parse_mode='HTML')
        char_info = await AIIdentifier.identify(file_bytes)

        # Step 4: Upload to Catbox
        await status_msg.edit_text('⬆️ <b>Uploading to storage...</b>', parse_mode='HTML')
        catbox_url = await Uploader.upload_to_catbox(
            file_bytes, 
            f"char_{photo.file_unique_id}.jpg"
        )
        
        if not catbox_url:
            await status_msg.edit_text('❌ <b>Upload failed!</b>\nCould not upload to Catbox.', parse_mode='HTML')
            return

        # Step 5: Generate ID and prepare data
        await status_msg.edit_text('💾 <b>Saving to database...</b>', parse_mode='HTML')
        char_id = await SequenceGen.get_next_id()
        rarity = next(
            (r for r in RarityLevel if r.level == quality.rarity_level), 
            RarityLevel.RARE
        )
        
        char_data = {
            'id': char_id,
            'name': char_info['name'],
            'anime': char_info['anime'],
            'rarity': rarity.display_name,
            'rarity_emoji': rarity.emoji,
            'rarity_name': rarity.display_name[2:],  # Remove emoji
            'img_url': catbox_url,
            'uploader_id': str(update.effective_user.id),
            'uploader_name': update.effective_user.first_name,
            'quality_score': round(quality.overall, 2),
            'quality_metrics': {
                'sharpness': round(quality.sharpness, 2),
                'contrast': round(quality.contrast, 2),
                'brightness': round(quality.brightness, 2),
                'resolution': round(quality.resolution, 2),
                'color_richness': round(quality.color_richness, 2),
            },
            'ai_confidence': char_info.get('confidence', 0.0),
            'ai_source': char_info.get('source', 'unknown'),
            'auto_uploaded': True
        }

        # Step 6: Send to channel
        await status_msg.edit_text('📢 <b>Publishing to channel...</b>', parse_mode='HTML')
        channel_msg = await Uploader.send_to_channel(char_data, file_bytes, context)
        
        if channel_msg and channel_msg.photo:
            char_data['message_id'] = channel_msg.message_id
            char_data['file_id'] = channel_msg.photo[-1].file_id

        # Step 7: Save to database
        await collection.insert_one(char_data)

        # Success message
        confidence_emoji = "🟢" if char_info.get('confidence', 0) > 0.7 else "🟡" if char_info.get('confidence', 0) > 0.5 else "🔴"
        
        success_text = (
            f'✅ <b>Upload Successful!</b>\n\n'
            f'🆔 <b>ID:</b> <code>{char_id}</code>\n'
            f'👤 <b>Name:</b> {char_info["name"]}\n'
            f'📺 <b>Anime:</b> {char_info["anime"]}\n'
            f'{rarity.emoji} <b>Rarity:</b> {rarity.display_name[2:]}\n'
            f'⭐ <b>Quality:</b> {quality.overall:.2f}/1.00\n'
            f'{confidence_emoji} <b>AI Confidence:</b> {char_info.get("confidence", 0):.0%}\n'
            f'🔍 <b>Source:</b> {char_info.get("source", "unknown")}'
        )
        
        await status_msg.edit_text(success_text, parse_mode='HTML')

    except Exception as e:
        error_msg = f'❌ <b>Error occurred:</b>\n<code>{str(e)}</code>'
        print(f"Auto-upload error: {e}")
        
        try:
            if 'status_msg' in locals():
                await status_msg.edit_text(error_msg, parse_mode='HTML')
            else:
                await update.message.reply_text(error_msg, parse_mode='HTML')
        except:
            pass

# Register handler
application.add_handler(
    MessageHandler(
        filters.PHOTO & filters.User(user_id=AUTHORIZED_USER),
        auto_upload_handler
    )
)