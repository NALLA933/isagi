import io
import asyncio
import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List, Any
from functools import wraps
import aiohttp
from pymongo import ReturnDocument
from telegram import Update, InputFile, Message
from telegram.ext import MessageHandler, filters, ContextTypes
from PIL import Image, ImageFilter, ImageStat
from shivu import application, collection, db, CHARA_CHANNEL_ID

AUTHORIZED_USER = "5147822244"


class MediaType(Enum):
    IMAGE = "image"
    VIDEO = "video"


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
            quality.overall = (quality.sharpness * 0.35 + quality.contrast * 0.30 +
                               quality.brightness * 0.20 + quality.color_variance * 0.15)
            quality.calculate_rarity()
            return quality
        except:
            return ImageQuality(overall=0.5, rarity_level=2)

    @staticmethod
    def _calc_sharpness(img: Image.Image) -> float:
        try:
            gray = img.convert('L')
            edges = gray.filter(ImageFilter.FIND_EDGES)
            stat = ImageStat.Stat(edges)
            return min(stat.var[0] / 10000.0, 1.0)
        except:
            return 0.5

    @staticmethod
    def _calc_contrast(img: Image.Image) -> float:
        try:
            stat = ImageStat.Stat(img.convert('L'))
            return min(stat.stddev[0] / 128.0, 1.0)
        except:
            return 0.5

    @staticmethod
    def _calc_brightness(img: Image.Image) -> float:
        try:
            stat = ImageStat.Stat(img.convert('L'))
            return stat.mean[0] / 255.0
        except:
            return 0.5

    @staticmethod
    def _calc_color_variance(img: Image.Image) -> float:
        try:
            hsv = img.convert('HSV')
            stat = ImageStat.Stat(hsv)
            return min(stat.var[1] / 10000.0, 1.0) if len(stat.var) > 1 else 0.5
        except:
            return 0.5


class FreeAIIdentifier:
    @staticmethod
    async def identify_character(image_bytes: bytes) -> Dict[str, str]:
        methods = [
            FreeAIIdentifier._try_trace_moe,
            FreeAIIdentifier._try_saucenao,
            FreeAIIdentifier._try_google_lens,
        ]
        
        for method in methods:
            try:
                result = await method(image_bytes)
                if result and result['name'] != "Unknown Character":
                    return result
            except Exception as e:
                print(f"Method {method.__name__} failed: {e}")
                continue
        
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    async def _try_trace_moe(image_bytes: bytes) -> Dict[str, str]:
        try:
            import base64
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
                            anime_title = result.get('anilist', {}).get('title', {})
                            anime_name = (anime_title.get('english') or 
                                        anime_title.get('romaji') or 
                                        anime_title.get('native', 'Unknown'))
                            
                            character = "Unknown Character"
                            filename = result.get('filename', '')
                            if filename:
                                character = filename.split('.')[0].replace('_', ' ').title()
                            
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
                    params={'output_type': 2, 'api_key': '', 'db': 999},
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get('results') and len(result['results']) > 0:
                            top_result = result['results'][0]
                            data_info = top_result.get('data', {})
                            
                            char_name = data_info.get('characters', ['Unknown'])[0] if data_info.get('characters') else 'Unknown Character'
                            anime_name = data_info.get('source', 'Unknown Series')
                            
                            if char_name != 'Unknown' or anime_name != 'Unknown Series':
                                return {"name": char_name, "anime": anime_name}
        except Exception as e:
            print(f"SauceNAO error: {e}")
        
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    async def _try_google_lens(image_bytes: bytes) -> Dict[str, str]:
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('encoded_image', image_bytes, filename='image.jpg')
                
                async with session.post(
                    "https://lens.google.com/v3/upload",
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        
                        anime_pattern = r'(One Piece|Naruto|Dragon Ball|Attack on Titan|Demon Slayer|My Hero Academia|Bleach|Death Note|Sword Art Online|Tokyo Ghoul|Fullmetal Alchemist|Hunter x Hunter|Jujutsu Kaisen|Chainsaw Man)'
                        anime_match = re.search(anime_pattern, text, re.IGNORECASE)
                        
                        name_pattern = r'([A-Z][a-z]+ [A-Z][a-z]+)'
                        name_match = re.search(name_pattern, text)
                        
                        if anime_match or name_match:
                            return {
                                "name": name_match.group(1) if name_match else "Unknown Character",
                                "anime": anime_match.group(1) if anime_match else "Unknown Series"
                            }
        except Exception as e:
            print(f"Google Lens error: {e}")
        
        return {"name": "Unknown Character", "anime": "Unknown Series"}


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
                
                async with session.post("https://catbox.moe/user/api.php", data=data) as resp:
                    if resp.status == 200:
                        result = (await resp.text()).strip()
                        if result.startswith('http'):
                            return result
        except Exception as e:
            print(f"Catbox upload failed: {e}")
        return None

    @staticmethod
    async def send_to_channel(char_data: Dict, file_bytes: bytes, context: ContextTypes.DEFAULT_TYPE) -> Optional[Message]:
        try:
            caption = (
                f'<b>{char_data["id"]}:</b> {char_data["name"]}\n'
                f'<b>{char_data["anime"]}</b>\n'
                f'<b>{char_data["rarity_emoji"]} 𝙍𝘼𝙍𝙄𝙏𝙔:</b> {char_data["rarity_name"]}\n'
                f'<b>Type:</b> 🖼 Image (🤖 AI Auto)\n\n'
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
            print(f"Channel upload failed: {e}")
            return None


def auth_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != AUTHORIZED_USER:
            await update.message.reply_text('❌ Unauthorized')
            return
        return await func(update, context)
    return wrapper


@auth_required
async def auto_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.photo:
        return

    status = await msg.reply_text('🔍 Analyzing image...')

    try:
        photo = msg.photo[-1]
        file = await photo.get_file()
        file_bytes = bytes(await file.download_as_bytearray())

        await status.edit_text('🔍 Analyzing quality...')
        quality = QualityAnalyzer.analyze(file_bytes)

        await status.edit_text('🤖 Identifying character (Free AI)...')
        char_info = await FreeAIIdentifier.identify_character(file_bytes)

        await status.edit_text('⏳ Uploading to Catbox...')
        catbox_url = await Uploader.upload_to_catbox(file_bytes, f"char_{photo.file_unique_id}.jpg")
        
        if not catbox_url:
            await status.edit_text('❌ Catbox upload failed')
            return

        await status.edit_text('💾 Saving to database...')
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

        await status.edit_text('📤 Posting to channel...')
        channel_msg = await Uploader.send_to_channel(char_data, file_bytes, context)
        
        if channel_msg:
            char_data['message_id'] = channel_msg.message_id
            if channel_msg.photo:
                char_data['file_id'] = channel_msg.photo[-1].file_id
                char_data['file_unique_id'] = channel_msg.photo[-1].file_unique_id

        await collection.insert_one(char_data)

        await status.edit_text(
            f'✅ Auto-uploaded successfully!\n\n'
            f'🆔 ID: {char_id}\n'
            f'👤 Name: {char_info["name"]}\n'
            f'📺 Anime: {char_info["anime"]}\n'
            f'{rarity_obj.emoji} Rarity: {rarity_obj.display_name[2:]}\n'
            f'⭐ Quality: {quality.overall:.2f}/1.0\n'
            f'🤖 Free AI Detection'
        )

    except Exception as e:
        await status.edit_text(f'❌ Error: {type(e).__name__}\n{str(e)}')


application.add_handler(MessageHandler(filters.PHOTO & filters.User(user_id=int(AUTHORIZED_USER)), auto_upload_handler, block=False))