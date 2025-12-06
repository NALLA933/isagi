import io
import asyncio
import hashlib
import re
import base64
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List, Any
from functools import wraps
import aiohttp
from pymongo import ReturnDocument
from telegram import Update, InputFile, Message
from telegram.ext import MessageHandler, filters, ContextTypes
from PIL import Image, ImageFilter, ImageStat, ImageOps
import numpy as np
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
    resolution_score: float = 0.0
    blur_score: float = 0.0
    noise_score: float = 0.0
    overall: float = 0.0
    rarity_level: int = 1

    def calculate_rarity(self):
        if self.overall >= 0.88:
            self.rarity_level = 17
        elif self.overall >= 0.80:
            self.rarity_level = 9
        elif self.overall >= 0.72:
            self.rarity_level = 8
        elif self.overall >= 0.64:
            self.rarity_level = 6
        elif self.overall >= 0.56:
            self.rarity_level = 5
        elif self.overall >= 0.48:
            self.rarity_level = 4
        elif self.overall >= 0.40:
            self.rarity_level = 3
        elif self.overall >= 0.30:
            self.rarity_level = 2
        else:
            self.rarity_level = 1
        return self.rarity_level


class AdvancedQualityAnalyzer:
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
            quality.sharpness = AdvancedQualityAnalyzer._calc_sharpness(img)
            quality.contrast = AdvancedQualityAnalyzer._calc_contrast(img)
            quality.brightness = AdvancedQualityAnalyzer._calc_brightness(img)
            quality.color_variance = AdvancedQualityAnalyzer._calc_color_variance(img)
            quality.resolution_score = AdvancedQualityAnalyzer._calc_resolution(img)
            quality.blur_score = AdvancedQualityAnalyzer._calc_blur_detection(img)
            quality.noise_score = AdvancedQualityAnalyzer._calc_noise_level(img)
            
            quality.overall = (
                quality.sharpness * 0.25 + 
                quality.contrast * 0.20 +
                quality.brightness * 0.10 + 
                quality.color_variance * 0.15 +
                quality.resolution_score * 0.15 +
                quality.blur_score * 0.10 +
                quality.noise_score * 0.05
            )
            
            quality.calculate_rarity()
            return quality
        except Exception as e:
            print(f"Quality analysis error: {e}")
            return ImageQuality(overall=0.4, rarity_level=2)

    @staticmethod
    def _calc_sharpness(img: Image.Image) -> float:
        try:
            gray = img.convert('L')
            edges = gray.filter(ImageFilter.FIND_EDGES)
            stat = ImageStat.Stat(edges)
            sharpness = min(stat.var[0] / 8000.0, 1.0)
            
            laplacian = gray.filter(ImageFilter.Kernel((3, 3), [-1,-1,-1,-1,8,-1,-1,-1,-1], 1, 0))
            laplacian_var = ImageStat.Stat(laplacian).var[0]
            laplacian_score = min(laplacian_var / 5000.0, 1.0)
            
            return (sharpness * 0.6 + laplacian_score * 0.4)
        except:
            return 0.5

    @staticmethod
    def _calc_contrast(img: Image.Image) -> float:
        try:
            stat = ImageStat.Stat(img.convert('L'))
            stddev = stat.stddev[0]
            contrast_score = min(stddev / 100.0, 1.0)
            
            extrema = img.convert('L').getextrema()
            range_score = (extrema[1] - extrema[0]) / 255.0
            
            return (contrast_score * 0.7 + range_score * 0.3)
        except:
            return 0.5

    @staticmethod
    def _calc_brightness(img: Image.Image) -> float:
        try:
            stat = ImageStat.Stat(img.convert('L'))
            brightness = stat.mean[0] / 255.0
            
            optimal_brightness = 0.55
            deviation = abs(brightness - optimal_brightness)
            score = 1.0 - (deviation / 0.55)
            
            return max(0.0, min(score, 1.0))
        except:
            return 0.5

    @staticmethod
    def _calc_color_variance(img: Image.Image) -> float:
        try:
            hsv = img.convert('HSV')
            h, s, v = hsv.split()
            
            s_stat = ImageStat.Stat(s)
            saturation_score = min(s_stat.mean[0] / 200.0, 1.0)
            
            color_variance = min(s_stat.var[0] / 8000.0, 1.0)
            
            return (saturation_score * 0.6 + color_variance * 0.4)
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
            elif total_pixels >= 307200:
                return 0.55
            else:
                return 0.40
        except:
            return 0.5

    @staticmethod
    def _calc_blur_detection(img: Image.Image) -> float:
        try:
            gray = img.convert('L').resize((500, 500))
            
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_stat = ImageStat.Stat(edges)
            edge_variance = edge_stat.var[0]
            
            blur_score = min(edge_variance / 6000.0, 1.0)
            return blur_score
        except:
            return 0.5

    @staticmethod
    def _calc_noise_level(img: Image.Image) -> float:
        try:
            gray = img.convert('L')
            smoothed = gray.filter(ImageFilter.GaussianBlur(1))
            
            diff_pixels = []
            for i in range(min(gray.size[0], 100)):
                for j in range(min(gray.size[1], 100)):
                    try:
                        diff = abs(gray.getpixel((i, j)) - smoothed.getpixel((i, j)))
                        diff_pixels.append(diff)
                    except:
                        pass
            
            if diff_pixels:
                noise_level = sum(diff_pixels) / len(diff_pixels)
                noise_score = 1.0 - min(noise_level / 30.0, 1.0)
                return noise_score
            return 0.5
        except:
            return 0.5


class EnhancedAIIdentifier:
    @staticmethod
    async def identify_character(image_bytes: bytes) -> Dict[str, str]:
        detection_methods = [
            EnhancedAIIdentifier._try_whatanime,
            EnhancedAIIdentifier._try_trace_moe,
            EnhancedAIIdentifier._try_animesearch,
            EnhancedAIIdentifier._try_iqdb,
            EnhancedAIIdentifier._try_saucenao,
            EnhancedAIIdentifier._try_ascii2d,
        ]
        
        results = []
        for method in detection_methods:
            try:
                result = await method(image_bytes)
                if result and result['name'] != "Unknown Character":
                    results.append(result)
                    if len(results) >= 2:
                        break
            except Exception as e:
                print(f"Method {method.__name__} failed: {e}")
                continue
        
        if results:
            return EnhancedAIIdentifier._merge_results(results)
        
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    def _merge_results(results: List[Dict[str, str]]) -> Dict[str, str]:
        names = [r['name'] for r in results if r['name'] != "Unknown Character"]
        animes = [r['anime'] for r in results if r['anime'] != "Unknown Series"]
        
        final_name = names[0] if names else "Unknown Character"
        final_anime = animes[0] if animes else "Unknown Series"
        
        return {"name": final_name, "anime": final_anime}

    @staticmethod
    async def _try_whatanime(image_bytes: bytes) -> Dict[str, str]:
        try:
            b64_img = base64.b64encode(image_bytes).decode('utf-8')
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.trace.moe/search",
                    json={"image": b64_img},
                    timeout=aiohttp.ClientTimeout(total=25),
                    headers={'Content-Type': 'application/json'}
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
                                        anime_title.get('native', 'Unknown'))
                            
                            filename = result.get('filename', '')
                            character = EnhancedAIIdentifier._extract_character_from_filename(filename)
                            
                            return {"name": character, "anime": anime_name}
        except Exception as e:
            print(f"WhatAnime error: {e}")
        
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    async def _try_trace_moe(image_bytes: bytes) -> Dict[str, str]:
        try:
            b64_img = base64.b64encode(image_bytes).decode('utf-8')
            
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field('image', b64_img)
                
                async with session.post(
                    "https://api.trace.moe/search",
                    data=form,
                    timeout=aiohttp.ClientTimeout(total=25)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('result'):
                            best = max(data['result'], key=lambda x: x.get('similarity', 0))
                            
                            if best.get('similarity', 0) >= 0.85:
                                anime = best.get('anilist', {}).get('title', {}).get('romaji', 'Unknown')
                                return {"name": "Unknown Character", "anime": anime}
        except Exception as e:
            print(f"TraceMoe error: {e}")
        
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    async def _try_animesearch(image_bytes: bytes) -> Dict[str, str]:
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('file', image_bytes, filename='image.jpg', content_type='image/jpeg')
                
                async with session.post(
                    "https://anime-search.p.rapidapi.com/",
                    data=data,
                    headers={
                        'X-RapidAPI-Host': 'anime-search.p.rapidapi.com'
                    },
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get('docs'):
                            doc = result['docs'][0]
                            anime = doc.get('anime', 'Unknown')
                            return {"name": "Unknown Character", "anime": anime}
        except:
            pass
        
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
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        
                        anime_match = re.search(r'<td class=\'image\'>.*?alt="(.*?)"', html, re.DOTALL)
                        if anime_match:
                            full_text = anime_match.group(1)
                            parts = full_text.split('/')
                            if len(parts) >= 2:
                                return {"name": parts[1].strip(), "anime": parts[0].strip()}
        except Exception as e:
            print(f"IQDB error: {e}")
        
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
                    params={'output_type': 2, 'db': 999, 'numres': 3},
                    timeout=aiohttp.ClientTimeout(total=25)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get('results') and len(result['results']) > 0:
                            for res in result['results'][:3]:
                                similarity = float(res.get('header', {}).get('similarity', 0))
                                if similarity >= 70:
                                    data_info = res.get('data', {})
                                    
                                    characters = data_info.get('characters')
                                    char_name = characters[0] if characters and len(characters) > 0 else None
                                    
                                    source = data_info.get('source') or data_info.get('title', '')
                                    anime_name = EnhancedAIIdentifier._clean_anime_name(source)
                                    
                                    member = data_info.get('member_name', '')
                                    material = data_info.get('material', '')
                                    
                                    if not char_name and member:
                                        char_name = member
                                    
                                    if not anime_name and material:
                                        anime_name = material
                                    
                                    if char_name or anime_name:
                                        return {
                                            "name": char_name or "Unknown Character",
                                            "anime": anime_name or "Unknown Series"
                                        }
        except Exception as e:
            print(f"SauceNAO error: {e}")
        
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    async def _try_ascii2d(image_bytes: bytes) -> Dict[str, str]:
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('file', image_bytes, filename='image.jpg')
                
                async with session.post(
                    "https://ascii2d.net/search/file",
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        
                        title_match = re.search(r'<h6><a[^>]*>(.*?)</a></h6>', html)
                        if title_match:
                            title = title_match.group(1).strip()
                            if '/' in title:
                                parts = title.split('/')
                                return {"name": parts[0].strip(), "anime": parts[1].strip() if len(parts) > 1 else "Unknown"}
                            return {"name": title, "anime": "Unknown Series"}
        except Exception as e:
            print(f"Ascii2D error: {e}")
        
        return {"name": "Unknown Character", "anime": "Unknown Series"}

    @staticmethod
    def _extract_character_from_filename(filename: str) -> str:
        if not filename:
            return "Unknown Character"
        
        name = filename.split('.')[0]
        name = re.sub(r'[\[\]()]', '', name)
        name = name.replace('_', ' ').replace('-', ' ')
        
        parts = name.split()
        filtered = [p for p in parts if not p.isdigit() and len(p) > 1]
        
        return ' '.join(filtered[:4]).title() if filtered else "Unknown Character"

    @staticmethod
    def _clean_anime_name(source: str) -> str:
        if not source or source == "Unknown":
            return "Unknown Series"
        
        source = re.sub(r'\[.*?\]', '', source)
        source = re.sub(r'\(.*?\)', '', source)
        source = source.strip()
        
        return source if source else "Unknown Series"


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
            print(f"Catbox upload failed: {e}")
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

    status = await msg.reply_text('🔍 Analyzing image quality...')

    try:
        photo = msg.photo[-1]
        file = await photo.get_file()
        file_bytes = bytes(await file.download_as_bytearray())

        quality = AdvancedQualityAnalyzer.analyze(file_bytes)
        
        quality_details = (
            f"📊 Quality Analysis:\n"
            f"Sharpness: {quality.sharpness:.2f}\n"
            f"Contrast: {quality.contrast:.2f}\n"
            f"Resolution: {quality.resolution_score:.2f}\n"
            f"Blur: {quality.blur_score:.2f}\n"
            f"Overall: {quality.overall:.2f}"
        )

        await status.edit_text(f'🤖 Identifying character...\n\n{quality_details}')
        char_info = await EnhancedAIIdentifier.identify_character(file_bytes)

        await status.edit_text(
            f'⏳ Uploading...\n\n'
            f'👤 {char_info["name"]}\n'
            f'📺 {char_info["anime"]}\n'
            f'⭐ Quality: {quality.overall:.2f}'
        )
        
        catbox_url = await Uploader.upload_to_catbox(file_bytes, f"char_{photo.file_unique_id}.jpg")
        
        if not catbox_url:
            await status.edit_text('❌ Catbox upload failed')
            return

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
            f'👤 Name: {char_info["name"]}\n'
            f'📺 Anime: {char_info["anime"]}\n'
            f'{rarity_obj.emoji} Rarity: {rarity_obj.display_name[2:]}\n'
            f'⭐ Quality: {quality.overall:.2f}/1.0\n'
            f'🎯 Sharpness: {quality.sharpness:.2f}\n'
            f'🎨 Contrast: {quality.contrast:.2f}\n'
            f'📐 Resolution: {quality.resolution_score:.2f}'
        )

    except Exception as e:
        await status.edit_text(f'❌ Error: {type(e).__name__}\n{str(e)}')


application.add_handler(MessageHandler(filters.PHOTO & filters.User(user_id=int(AUTHORIZED_USER)), auto_upload_handler, block=False))