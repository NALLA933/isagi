import io
import asyncio
import hashlib
import re
import base64
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List
from functools import wraps
import aiohttp
from pymongo import ReturnDocument
from telegram import Update, InputFile, Message
from telegram.ext import MessageHandler, filters, ContextTypes
from PIL import Image, ImageFilter, ImageStat
from shivu import application, collection, db, CHARA_CHANNEL_ID

AUTHORIZED_USER = 5147822244


class RarityLevel(Enum):
    COMMON = (1, "🟢 Common")
    RARE = (2, "🟣 Rare")
    LEGENDARY = (3, "🟡 Legendary")
    SPECIAL_EDITION = (4, "💮 Special Edition")
    NEON = (5, "💫 Neon")
    MANGA = (6, "✨ Manga")
    CELESTIAL = (8, "🎐 Celestial")
    PREMIUM = (9, "🔮 Premium Edition")
    MYTHIC = (17, "🏵 Mythic")

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


@dataclass
class ImageQuality:
    sharpness: float = 0.0
    contrast: float = 0.0
    brightness: float = 0.0
    color_variance: float = 0.0
    resolution_score: float = 0.0
    overall: float = 0.0
    rarity_level: int = 1

    def calculate_rarity(self):
        if self.overall >= 0.85:
            self.rarity_level = 17
        elif self.overall >= 0.75:
            self.rarity_level = 9
        elif self.overall >= 0.65:
            self.rarity_level = 8
        elif self.overall >= 0.55:
            self.rarity_level = 6
        elif self.overall >= 0.45:
            self.rarity_level = 4
        elif self.overall >= 0.35:
            self.rarity_level = 3
        else:
            self.rarity_level = 2
        return self.rarity_level


class QualityAnalyzer:
    @staticmethod
    def analyze(image_bytes: bytes) -> ImageQuality:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            if img.mode != 'RGB':
                if img.mode == 'RGBA':
                    bg = Image.new('RGB', img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[3])
                    img = bg
                else:
                    img = img.convert('RGB')

            quality = ImageQuality()
            quality.sharpness = QualityAnalyzer._calc_sharpness(img)
            quality.contrast = QualityAnalyzer._calc_contrast(img)
            quality.brightness = QualityAnalyzer._calc_brightness(img)
            quality.color_variance = QualityAnalyzer._calc_color_variance(img)
            quality.resolution_score = QualityAnalyzer._calc_resolution(img)
            
            quality.overall = (
                quality.sharpness * 0.30 + 
                quality.contrast * 0.25 +
                quality.brightness * 0.15 + 
                quality.color_variance * 0.15 +
                quality.resolution_score * 0.15
            )
            
            quality.calculate_rarity()
            return quality
        except Exception as e:
            print(f"Quality error: {e}")
            return ImageQuality(overall=0.4, rarity_level=2)

    @staticmethod
    def _calc_sharpness(img: Image.Image) -> float:
        try:
            gray = img.convert('L')
            edges = gray.filter(ImageFilter.FIND_EDGES)
            stat = ImageStat.Stat(edges)
            return min(stat.var[0] / 8000.0, 1.0)
        except:
            return 0.5

    @staticmethod
    def _calc_contrast(img: Image.Image) -> float:
        try:
            stat = ImageStat.Stat(img.convert('L'))
            return min(stat.stddev[0] / 100.0, 1.0)
        except:
            return 0.5

    @staticmethod
    def _calc_brightness(img: Image.Image) -> float:
        try:
            stat = ImageStat.Stat(img.convert('L'))
            brightness = stat.mean[0] / 255.0
            deviation = abs(brightness - 0.55)
            return max(0.0, 1.0 - (deviation / 0.55))
        except:
            return 0.5

    @staticmethod
    def _calc_color_variance(img: Image.Image) -> float:
        try:
            hsv = img.convert('HSV')
            h, s, v = hsv.split()
            s_stat = ImageStat.Stat(s)
            return min(s_stat.mean[0] / 200.0, 1.0)
        except:
            return 0.5

    @staticmethod
    def _calc_resolution(img: Image.Image) -> float:
        try:
            width, height = img.size
            total_pixels = width * height
            
            if total_pixels >= 2073600:
                return 1.0
            elif total_pixels >= 921600:
                return 0.85
            elif total_pixels >= 518400:
                return 0.70
            else:
                return 0.55
        except:
            return 0.5


class AIIdentifier:
    @staticmethod
    async def identify_character(image_bytes: bytes) -> Dict[str, str]:
        methods = [
            AIIdentifier._try_trace_moe,
            AIIdentifier._try_saucenao,
            AIIdentifier._try_iqdb,
        ]
        
        for method in methods:
            try:
                result = await method(image_bytes)
                if result and result['name'] != "Unknown Character":
                    return result
            except Exception as e:
                print(f"{method.__name__} failed: {e}")
                continue
        
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    async def _try_trace_moe(image_bytes: bytes) -> Dict[str, str]:
        try:
            b64_img = base64.b64encode(image_bytes).decode('utf-8')
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.trace.moe/search",
                    json={"image": b64_img},
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('result') and len(data['result']) > 0:
                            result = data['result'][0]
                            
                            if result.get('similarity', 0) < 0.80:
                                return {"name": "Unknown Character", "anime": "Unknown Series"}
                            
                            anilist = result.get('anilist', {})
                            anime_title = anilist.get('title', {})
                            anime_name = (anime_title.get('english') or 
                                        anime_title.get('romaji') or 
                                        'Unknown')
                            
                            filename = result.get('filename', '')
                            character = AIIdentifier._clean_name(filename)
                            
                            return {"name": character, "anime": anime_name}
        except Exception as e:
            print(f"TraceMoe error: {e}")
        
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    async def _try_saucenao(image_bytes: bytes) -> Dict[str, str]:
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('file', image_bytes, filename='image.jpg')
                
                async with session.post(
                    "https://saucenao.com/search.php",
                    data=data,
                    params={'output_type': 2, 'db': 999},
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get('results'):
                            for res in result['results'][:2]:
                                similarity = float(res.get('header', {}).get('similarity', 0))
                                if similarity >= 70:
                                    data_info = res.get('data', {})
                                    
                                    characters = data_info.get('characters', [])
                                    char_name = characters[0] if characters else "Unknown Character"
                                    
                                    source = data_info.get('source', 'Unknown Series')
                                    
                                    return {"name": char_name, "anime": source}
        except Exception as e:
            print(f"SauceNAO error: {e}")
        
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    async def _try_iqdb(image_bytes: bytes) -> Dict[str, str]:
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('file', image_bytes, filename='image.jpg')
                
                async with session.post(
                    "https://iqdb.org/",
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        
                        match = re.search(r'alt="(.*?)"', html)
                        if match:
                            text = match.group(1)
                            if '/' in text:
                                parts = text.split('/')
                                return {"name": parts[1].strip(), "anime": parts[0].strip()}
        except Exception as e:
            print(f"IQDB error: {e}")
        
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    def _clean_name(filename: str) -> str:
        if not filename:
            return "Unknown Character"
        
        name = filename.split('.')[0]
        name = re.sub(r'[\[\]()_-]', ' ', name)
        parts = [p for p in name.split() if not p.isdigit() and len(p) > 1]
        
        return ' '.join(parts[:3]).title() if parts else "Unknown Character"


class SequenceGen:
    @staticmethod
    async def get_next_id() -> str:
        seq_coll = db.sequences
        doc = await seq_coll.find_one_and_update(
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
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('reqtype', 'fileupload')
                data.add_field('fileToUpload', file_bytes, filename=filename)
                
                async with session.post(
                    "https://catbox.moe/user/api.php", 
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status == 200:
                        result = (await resp.text()).strip()
                        if result.startswith('http'):
                            return result
        except Exception as e:
            print(f"Catbox error: {e}")
        return None

    @staticmethod
    async def send_to_channel(char_data: Dict, file_bytes: bytes, context: ContextTypes.DEFAULT_TYPE) -> Optional[Message]:
        try:
            caption = (
                f'<b>{char_data["id"]}:</b> {char_data["name"]}\n'
                f'<b>{char_data["anime"]}</b>\n'
                f'<b>{char_data["rarity_emoji"]} 𝙍𝘼𝙍𝙄𝙏𝙔:</b> {char_data["rarity_name"]}\n'
                f'<b>Type:</b> 🖼 Image (🤖 AI Auto)\n'
                f'<b>Quality:</b> {char_data["quality_score"]}/1.0\n\n'
                f'𝑨𝒖𝒕𝒐 𝑼𝒑𝒍𝒐𝒂𝒅𝒆𝒅 ➥ <a href="tg://user?id={char_data["uploader_id"]}">{char_data["uploader_name"]}</a>'
            )

            fp = io.BytesIO(file_bytes)
            fp.name = f"{char_data['id']}.jpg"
            
            msg = await context.bot.send_photo(
                chat_id=CHARA_CHANNEL_ID,
                photo=InputFile(fp),
                caption=caption,
                parse_mode='HTML'
            )
            return msg
        except Exception as e:
            print(f"Channel error: {e}")
            return None


async def auto_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != AUTHORIZED_USER:
            return
        
        if not update.message or not update.message.photo:
            return

        msg = update.message
        status = await msg.reply_text('🔍 Processing...')

        photo = msg.photo[-1]
        file = await photo.get_file()
        file_bytes = bytes(await file.download_as_bytearray())

        await status.edit_text('📊 Analyzing quality...')
        quality = QualityAnalyzer.analyze(file_bytes)

        await status.edit_text('🤖 Identifying character...')
        char_info = await AIIdentifier.identify_character(file_bytes)

        await status.edit_text('⏳ Uploading to Catbox...')
        catbox_url = await Uploader.upload_to_catbox(file_bytes, f"char_{photo.file_unique_id}.jpg")
        
        if not catbox_url:
            await status.edit_text('❌ Upload failed')
            return

        await status.edit_text('💾 Saving...')
        char_id = await SequenceGen.get_next_id()

        rarity_obj = next((r for r in RarityLevel if r.level == quality.rarity_level), RarityLevel.RARE)
        
        char_data = {
            'id': char_id,
            'name': char_info['name'],
            'anime': char_info['anime'],
            'rarity': rarity_obj.display_name,
            'rarity_emoji': rarity_obj.emoji,
            'rarity_name': rarity_obj.display_name[2:],
            'img_url': catbox_url,
            'is_video': False,
            'media_type': 'image',
            'uploader_id': str(update.effective_user.id),
            'uploader_name': update.effective_user.first_name,
            'quality_score': round(quality.overall, 2),
            'auto_uploaded': True
        }

        channel_msg = await Uploader.send_to_channel(char_data, file_bytes, context)
        
        if channel_msg:
            char_data['message_id'] = channel_msg.message_id
            if channel_msg.photo:
                char_data['file_id'] = channel_msg.photo[-1].file_id
                char_data['file_unique_id'] = channel_msg.photo[-1].file_unique_id

        await collection.insert_one(char_data)

        await status.edit_text(
            f'✅ Success!\n\n'
            f'🆔 ID: {char_id}\n'
            f'👤 {char_info["name"]}\n'
            f'📺 {char_info["anime"]}\n'
            f'{rarity_obj.emoji} {rarity_obj.display_name[2:]}\n'
            f'⭐ Quality: {quality.overall:.2f}'
        )

    except Exception as e:
        print(f"Handler error: {e}")
        try:
            await update.message.reply_text(f'❌ Error: {str(e)}')
        except:
            pass


application.add_handler(
    MessageHandler(
        filters.PHOTO & filters.User(user_id=AUTHORIZED_USER),
        auto_upload_handler
    )
)