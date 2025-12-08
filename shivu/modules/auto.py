import io
import base64
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict
import aiohttp
from pymongo import ReturnDocument
from telegram import Update, InputFile
from telegram.ext import MessageHandler, filters, ContextTypes
from PIL import Image, ImageFilter, ImageStat
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
    overall: float = 0.5
    rarity_level: int = 2

    def calculate_rarity(self):
        s = self.overall
        self.rarity_level = (17 if s >= 0.85 else 9 if s >= 0.75 else 
                           8 if s >= 0.65 else 6 if s >= 0.55 else 
                           5 if s >= 0.45 else 3 if s >= 0.35 else 2)
        return self.rarity_level

class QualityAnalyzer:
    @staticmethod
    def analyze(img_bytes: bytes) -> ImageQuality:
        try:
            img = Image.open(io.BytesIO(img_bytes))
            if img.mode == 'RGBA':
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != 'RGB': img = img.convert('RGB')

            # Metrics
            sharpness = min(ImageStat.Stat(img.convert('L').filter(ImageFilter.FIND_EDGES)).var[0] / 8000, 1.0)
            contrast = min(ImageStat.Stat(img.convert('L')).stddev[0] / 100, 1.0)
            brightness = max(0, 1 - abs(ImageStat.Stat(img.convert('L')).mean[0] / 255 - 0.55) / 0.55)
            px = img.size[0] * img.size[1]
            resolution = 1.0 if px >= 2073600 else 0.85 if px >= 921600 else 0.70 if px >= 518400 else 0.55
            
            overall = sharpness * 0.35 + contrast * 0.25 + brightness * 0.20 + resolution * 0.20
            quality = ImageQuality(overall=overall)
            quality.calculate_rarity()
            return quality
        except:
            return ImageQuality(overall=0.4, rarity_level=2)

class AIIdentifier:
    """
    Free APIs for anime character identification:
    1. trace.moe - Best for anime scenes (100% free, no key needed)
    2. ascii2d - Good for artwork (100% free, no key needed)  
    3. IQDB - Basic but reliable (100% free, no key needed)
    4. SauceNAO - Requires free API key from saucenao.com/user.php
    """
    
    SAUCENAO_API_KEY = None  # Get free key: https://saucenao.com/user.php (150 searches/day)
    
    @staticmethod
    async def identify(img_bytes: bytes) -> Dict[str, str]:
        methods = [
            AIIdentifier._trace_moe,
            AIIdentifier._ascii2d,
            AIIdentifier._iqdb,
        ]
        
        # Add SauceNAO if API key is configured
        if AIIdentifier.SAUCENAO_API_KEY:
            methods.insert(1, AIIdentifier._saucenao)
        
        for method in methods:
            try:
                result = await method(img_bytes)
                if result['name'] != "Unknown Character":
                    return result
            except Exception as e:
                print(f"{method.__name__}: {e}")
        
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    async def _trace_moe(img_bytes: bytes) -> Dict[str, str]:
        """100% Free - No API key needed"""
        try:
            b64 = base64.b64encode(img_bytes).decode()
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://api.trace.moe/search",
                    json={"image": b64},
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data.get('result'):
                            top = data['result'][0]
                            if top.get('similarity', 0) < 0.70:
                                return {"name": "Unknown Character", "anime": "Unknown Series"}
                            
                            anilist = top.get('anilist', {})
                            title = anilist.get('title', {})
                            anime = (title.get('english') or title.get('romaji') or 
                                   title.get('native') or 'Unknown')
                            
                            char = AIIdentifier._clean(top.get('filename', ''))
                            return {"name": char, "anime": anime}
        except: pass
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    async def _ascii2d(img_bytes: bytes) -> Dict[str, str]:
        """100% Free - No API key needed"""
        try:
            async with aiohttp.ClientSession() as s:
                data = aiohttp.FormData()
                data.add_field('file', img_bytes, filename='img.jpg')
                
                async with s.post(
                    "https://ascii2d.net/search/file",
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    if r.status == 200:
                        html = await r.text()
                        
                        # Parse color search results
                        char_match = re.search(r'<div class="detail-box"[^>]*>.*?<h6>(.*?)</h6>.*?<h6>(.*?)</h6>', html, re.DOTALL)
                        if char_match:
                            char_name = char_match.group(1).strip()
                            anime_name = char_match.group(2).strip()
                            
                            if char_name and anime_name:
                                return {"name": char_name, "anime": anime_name}
        except: pass
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    async def _saucenao(img_bytes: bytes) -> Dict[str, str]:
        """Free tier: 150 searches/day with API key"""
        if not AIIdentifier.SAUCENAO_API_KEY:
            return {"name": "Unknown Character", "anime": "Unknown Series"}
        
        try:
            async with aiohttp.ClientSession() as s:
                data = aiohttp.FormData()
                data.add_field('file', img_bytes, filename='img.jpg')
                
                async with s.post(
                    "https://saucenao.com/search.php",
                    data=data,
                    params={
                        'output_type': 2,
                        'api_key': AIIdentifier.SAUCENAO_API_KEY,
                        'db': 999  # All databases
                    },
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as r:
                    if r.status == 200:
                        result = await r.json()
                        if result.get('results'):
                            for res in result['results'][:3]:
                                similarity = float(res.get('header', {}).get('similarity', 0))
                                if similarity >= 65:
                                    info = res.get('data', {})
                                    
                                    # Try to extract character and anime
                                    chars = info.get('characters', [])
                                    char_name = chars[0] if chars else info.get('title', 'Unknown Character')
                                    
                                    anime = info.get('source') or info.get('material') or 'Unknown Series'
                                    
                                    return {"name": char_name, "anime": anime}
        except: pass
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    async def _iqdb(img_bytes: bytes) -> Dict[str, str]:
        """100% Free - No API key needed"""
        try:
            async with aiohttp.ClientSession() as s:
                data = aiohttp.FormData()
                data.add_field('file', img_bytes, filename='img.jpg')
                
                async with s.post(
                    "https://iqdb.org/",
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    if r.status == 200:
                        html = await r.text()
                        
                        # Parse results
                        match = re.search(r'<td[^>]*class=["\']image["\'][^>]*>.*?alt=["\']([^"\']+)["\']', html, re.DOTALL)
                        if match:
                            text = match.group(1)
                            if '/' in text:
                                parts = text.split('/')
                                return {"name": parts[1].strip(), "anime": parts[0].strip()}
                            
                        # Fallback: try to find any relevant text
                        title_match = re.search(r'<td>([^<]+)</td>', html)
                        if title_match:
                            text = title_match.group(1).strip()
                            if len(text) > 5 and len(text) < 100:
                                return {"name": text, "anime": "Unknown Series"}
        except: pass
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    def _clean(filename: str) -> str:
        if not filename: return "Unknown Character"
        name = re.sub(r'\.[^.]+$', '', filename)
        name = re.sub(r'[\[\]()_\-\d]', ' ', name)
        parts = [p.strip().title() for p in name.split() if len(p) > 1]
        return ' '.join(parts[:3]) if parts else "Unknown Character"

class SequenceGen:
    @staticmethod
    async def get_next_id() -> str:
        doc = await db.sequences.find_one_and_update(
            {'_id': 'character_id'},
            {'$inc': {'sequence_value': 1}},
            return_document=ReturnDocument.AFTER,
            upsert=True
        )
        return str(doc.get('sequence_value', 0)).zfill(2)

class Uploader:
    @staticmethod
    async def upload_to_catbox(file_bytes: bytes, filename: str) -> Optional[str]:
        try:
            async with aiohttp.ClientSession() as s:
                data = aiohttp.FormData()
                data.add_field('reqtype', 'fileupload')
                data.add_field('fileToUpload', file_bytes, filename=filename)
                
                async with s.post(
                    "https://catbox.moe/user/api.php",
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as r:
                    if r.status == 200:
                        result = (await r.text()).strip()
                        if result.startswith('http'):
                            return result
        except Exception as e:
            print(f"Catbox: {e}")
        return None

    @staticmethod
    async def send_to_channel(char_data: Dict, file_bytes: bytes, context):
        try:
            caption = (
                f'<b>{char_data["id"]}:</b> {char_data["name"]}\n'
                f'<b>{char_data["anime"]}</b>\n'
                f'<b>{char_data["rarity_emoji"]} 𝙍𝘼𝙍𝙄𝙏𝙔:</b> {char_data["rarity_name"]}\n'
                f'<b>Quality:</b> {char_data["quality_score"]}/1.0\n\n'
                f'𝑨𝒖𝒕𝒐 𝑼𝒑𝒍𝒐𝒂𝒅𝒆𝒅 ➥ <a href="tg://user?id={char_data["uploader_id"]}">{char_data["uploader_name"]}</a>'
            )

            fp = io.BytesIO(file_bytes)
            fp.name = f"{char_data['id']}.jpg"
            
            return await context.bot.send_photo(
                chat_id=CHARA_CHANNEL_ID,
                photo=InputFile(fp),
                caption=caption,
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"Channel: {e}")
            return None

async def auto_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != AUTHORIZED_USER or not update.message.photo:
            return

        msg = update.message
        status = await msg.reply_text('🔍 Processing...')

        # Download
        photo = msg.photo[-1]
        file = await photo.get_file()
        file_bytes = bytes(await file.download_as_bytearray())

        # Quality
        await status.edit_text('📊 Analyzing...')
        quality = QualityAnalyzer.analyze(file_bytes)

        # Identify
        await status.edit_text('🤖 Identifying...')
        char_info = await AIIdentifier.identify(file_bytes)

        # Upload
        await status.edit_text('⏳ Uploading...')
        catbox_url = await Uploader.upload_to_catbox(file_bytes, f"c_{photo.file_unique_id}.jpg")
        
        if not catbox_url:
            await status.edit_text('❌ Upload failed')
            return

        # Save
        await status.edit_text('💾 Saving...')
        char_id = await SequenceGen.get_next_id()
        rarity = next((r for r in RarityLevel if r.level == quality.rarity_level), RarityLevel.RARE)
        
        char_data = {
            'id': char_id,
            'name': char_info['name'],
            'anime': char_info['anime'],
            'rarity': rarity.display_name,
            'rarity_emoji': rarity.emoji,
            'rarity_name': rarity.display_name[2:],
            'img_url': catbox_url,
            'uploader_id': str(update.effective_user.id),
            'uploader_name': update.effective_user.first_name,
            'quality_score': round(quality.overall, 2),
            'auto_uploaded': True
        }

        # Channel
        channel_msg = await Uploader.send_to_channel(char_data, file_bytes, context)
        
        if channel_msg and channel_msg.photo:
            char_data['message_id'] = channel_msg.message_id
            char_data['file_id'] = channel_msg.photo[-1].file_id

        await collection.insert_one(char_data)

        await status.edit_text(
            f'✅ Success!\n\n'
            f'🆔 {char_id}\n'
            f'👤 {char_info["name"]}\n'
            f'📺 {char_info["anime"]}\n'
            f'{rarity.emoji} {rarity.display_name[2:]}\n'
            f'⭐ {quality.overall:.2f}'
        )

    except Exception as e:
        print(f"Error: {e}")
        try:
            await update.message.reply_text(f'❌ Error: {str(e)}')
        except: pass

# Register
application.add_handler(
    MessageHandler(
        filters.PHOTO & filters.User(user_id=AUTHORIZED_USER),
        auto_upload_handler
    )
)