import io
import base64
import re
import asyncio
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List
import aiohttp
from pymongo import ReturnDocument
from telegram import Update, InputFile
from telegram.ext import MessageHandler, filters, ContextTypes
from PIL import Image, ImageFilter, ImageStat
import numpy as np
from shivu import application, collection, db, CHARA_CHANNEL_ID

AUTHORIZED_USER = 5147822244

class RarityLevel(Enum):
    RARE = (2, "🟣 Rare")
    LEGENDARY = (3, "🟡 Legendary")
    SPECIAL = (4, "💮 Special")
    NEON = (5, "💫 Neon")
    MANGA = (6, "✨ Manga")
    CELESTIAL = (8, "🎐 Celestial")
    PREMIUM = (9, "🔮 Premium")
    MYTHIC = (17, "🏵 Mythic")

    def __init__(self, level: int, display: str):
        self._level, self._display = level, display
    
    @property
    def level(self): return self._level
    @property
    def display_name(self): return self._display
    @property
    def emoji(self): return self._display.split()[0]

@dataclass
class AIDetectionResult:
    is_authentic: bool = True
    ai_probability: float = 0.0
    warning_flags: List[str] = None
    
    def __post_init__(self):
        if self.warning_flags is None:
            self.warning_flags = []

@dataclass
class Quality:
    sharpness: float = 0.0
    contrast: float = 0.0
    resolution: float = 0.0
    overall: float = 0.5
    rarity_level: int = 2
    
    def calculate(self):
        self.overall = (self.sharpness * 0.4 + self.contrast * 0.3 + self.resolution * 0.3)
        if self.overall >= 0.90: self.rarity_level = 17
        elif self.overall >= 0.82: self.rarity_level = 9
        elif self.overall >= 0.72: self.rarity_level = 8
        elif self.overall >= 0.62: self.rarity_level = 6
        elif self.overall >= 0.52: self.rarity_level = 5
        elif self.overall >= 0.42: self.rarity_level = 4
        elif self.overall >= 0.32: self.rarity_level = 3
        else: self.rarity_level = 2
        return self

class AIDetector:
    @staticmethod
    async def detect(img_bytes: bytes) -> AIDetectionResult:
        try:
            img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
            arr = np.array(img)
            
            # Noise check
            r_noise = np.std(np.diff(arr[:,:,0].flatten()))
            ai_score = 0.85 if r_noise < 5 else 0.30
            
            # Edge check
            gray = img.convert('L')
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_count = np.sum(np.array(edges) > 30)
            if edge_count < 1000: ai_score = max(ai_score, 0.80)
            
            # Metadata check
            info = img.info
            ai_words = ['stable diffusion', 'midjourney', 'dall-e', 'novelai', 'pixai']
            for key, val in info.items():
                if isinstance(val, str) and any(w in val.lower() for w in ai_words):
                    return AIDetectionResult(False, 0.95, ["AI signature in metadata"])
            
            result = AIDetectionResult(ai_score < 0.65, ai_score)
            if ai_score > 0.75: result.warning_flags.append(f"High AI signature ({ai_score:.2f})")
            return result
        except:
            return AIDetectionResult(True, 0.0)

class QualityAnalyzer:
    @staticmethod
    def analyze(img_bytes: bytes) -> Quality:
        try:
            img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
            gray = img.convert('L')
            arr = np.array(gray)
            
            # Sharpness
            laplacian_var = np.var(np.array([[0,1,0],[1,-4,1],[0,1,0]]))
            sharpness = min(laplacian_var * 100, 1.0)
            
            # Contrast
            stat = ImageStat.Stat(gray)
            contrast = min(stat.stddev[0] / 75, 1.0)
            
            # Resolution
            w, h = img.size
            mp = (w * h) / 1_000_000
            resolution = 1.0 if mp >= 2.0 else (0.85 if mp >= 0.9 else 0.65)
            
            return Quality(sharpness, contrast, resolution).calculate()
        except:
            return Quality(0.4, 0.4, 0.5).calculate()

class AIVision:
    DEEPINFRA_KEY = None
    
    MODELS = [
        {"url": "https://api.deepinfra.com/v1/openai/chat/completions",
         "model": "meta-llama/Llama-3.2-90B-Vision-Instruct"},
        {"url": "https://api.shuttleai.app/v1/chat/completions",
         "model": "gpt-4o-mini", "auth": "Bearer shuttle-free-api-key"},
    ]
    
    @staticmethod
    async def identify(img_bytes: bytes) -> Dict:
        b64 = base64.b64encode(img_bytes).decode()
        prompt = """Identify this anime character. Return ONLY JSON:
{"character_name": "name", "anime_series": "series", "confidence": 0.95}"""
        
        for model in AIVision.MODELS:
            try:
                headers = {"Content-Type": "application/json"}
                if model.get('auth'): headers["Authorization"] = model['auth']
                elif AIVision.DEEPINFRA_KEY: headers["Authorization"] = f"Bearer {AIVision.DEEPINFRA_KEY}"
                
                payload = {
                    "model": model['model'],
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                        ]
                    }],
                    "max_tokens": 300,
                    "temperature": 0.3
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(model['url'], json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=25)) as r:
                        if r.status == 200:
                            data = await r.json()
                            content = data['choices'][0]['message']['content']
                            match = re.search(r'\{[^}]+\}', content)
                            if match:
                                result = json.loads(match.group())
                                return {
                                    'name': result.get('character_name', 'Unknown'),
                                    'anime': result.get('anime_series', 'Unknown'),
                                    'confidence': float(result.get('confidence', 0.0)),
                                    'source': 'ai-vision'
                                }
            except: continue
        
        return {'name': 'Unknown', 'anime': 'Unknown', 'confidence': 0.0, 'source': 'none'}

class ImageSearch:
    @staticmethod
    async def search(img_bytes: bytes) -> Dict:
        # Trace.moe
        try:
            img = Image.open(io.BytesIO(img_bytes))
            if max(img.size) > 1000:
                img.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=90)
                img_bytes = buf.getvalue()
            
            b64 = base64.b64encode(img_bytes).decode()
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.trace.moe/search", json={"image": b64}, timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data.get('result'):
                            top = data['result'][0]
                            if top.get('similarity', 0) >= 0.60:
                                anilist = top.get('anilist', {})
                                title = anilist.get('title', {})
                                anime = title.get('english') or title.get('romaji') or 'Unknown'
                                filename = top.get('filename', '')
                                name = re.sub(r'\.[^.]+$|[_\-\.]|\d{3,}', ' ', filename).strip().title() or 'Unknown'
                                return {'name': name, 'anime': anime, 'confidence': top['similarity'], 'source': 'trace.moe'}
        except: pass
        
        return {'name': 'Unknown', 'anime': 'Unknown', 'confidence': 0.0, 'source': 'none'}

class AnimeDB:
    @staticmethod
    async def verify(char_name: str, anime_name: str) -> Dict:
        # Jikan (MAL)
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://api.jikan.moe/v4/characters", params={'q': char_name, 'limit': 5}, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 200:
                        data = await r.json()
                        for char in data.get('data', []):
                            name = char.get('name', '')
                            if AnimeDB._similar(char_name, name) > 0.6:
                                return {'verified': True, 'confidence': 0.95, 'sources': 1, 'character_name': name, 'anime_name': anime_name}
        except: pass
        
        return {'verified': False, 'confidence': 0.0, 'sources': 0, 'character_name': char_name, 'anime_name': anime_name}
    
    @staticmethod
    def _similar(a: str, b: str) -> float:
        a, b = a.lower(), b.lower()
        if a == b: return 1.0
        if a in b or b in a: return 0.85
        wa, wb = set(a.split()), set(b.split())
        return len(wa & wb) / len(wa | wb) if wa | wb else 0.0

class Uploader:
    @staticmethod
    async def to_catbox(file_bytes: bytes, filename: str) -> Optional[str]:
        try:
            async with aiohttp.ClientSession() as s:
                data = aiohttp.FormData()
                data.add_field('reqtype', 'fileupload')
                data.add_field('fileToUpload', file_bytes, filename=filename)
                async with s.post("https://catbox.moe/user/api.php", data=data, timeout=aiohttp.ClientTimeout(total=60)) as r:
                    if r.status == 200:
                        url = (await r.text()).strip()
                        return url if url.startswith('http') else None
        except: pass
        return None
    
    @staticmethod
    async def to_channel(data: Dict, img_bytes: bytes, ctx):
        try:
            cap = (
                f'╔════════════════╗\n'
                f'  🆔 <code>{data["id"]}</code>\n'
                f'╚════════════════╝\n\n'
                f'👤 {data["name"]}\n'
                f'📺 {data["anime"]}\n'
                f'{data["rarity_emoji"]} {data["rarity_name"]}\n\n'
                f'⭐ Quality: {data["quality_score"]:.2f}\n'
                f'🔐 Auth: {data["authenticity_score"]:.0f}%\n'
                f'✅ Verified: {data["verified_sources"]} DB\n\n'
                f'<i>By</i> <a href="tg://user?id={data["uploader_id"]}">{data["uploader_name"]}</a>'
            )
            
            file_obj = io.BytesIO(img_bytes)
            file_obj.name = f"{data['id']}.jpg"
            
            return await ctx.bot.send_photo(CHARA_CHANNEL_ID, photo=InputFile(file_obj), caption=cap, parse_mode='HTML')
        except: return None

async def get_next_id() -> str:
    doc = await db.sequences.find_one_and_update(
        {'_id': 'character_id'},
        {'$inc': {'sequence_value': 1}},
        return_document=ReturnDocument.AFTER,
        upsert=True
    )
    return str(doc.get('sequence_value', 0)).zfill(4)

async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = None
    try:
        if update.effective_user.id != AUTHORIZED_USER:
            await update.message.reply_text("❌ Unauthorized")
            return
        
        if not update.message.photo:
            await update.message.reply_text("❌ Send a photo")
            return
        
        status = await update.message.reply_text('🔄 <b>Analyzing...</b>', parse_mode='HTML')
        
        # Download
        await status.edit_text('📥 <b>1/5:</b> Downloading...', parse_mode='HTML')
        photo = update.message.photo[-1]
        file_bytes = bytes(await (await photo.get_file()).download_as_bytearray())
        
        # AI Detection
        await status.edit_text('🤖 <b>2/5:</b> AI Detection...', parse_mode='HTML')
        ai_check = await AIDetector.detect(file_bytes)
        if not ai_check.is_authentic:
            await status.edit_text(
                f'⚠️ <b>AI-Generated Detected!</b>\n\n'
                f'AI Probability: {ai_check.ai_probability:.0%}\n\n'
                f'❌ <b>Upload Rejected</b>\n'
                f'<i>Only authentic anime artwork allowed.</i>',
                parse_mode='HTML'
            )
            return
        
        # Quality
        await status.edit_text('📊 <b>3/5:</b> Quality Analysis...', parse_mode='HTML')
        quality = QualityAnalyzer.analyze(file_bytes)
        
        # Character ID
        await status.edit_text('🔍 <b>4/5:</b> Identifying Character...', parse_mode='HTML')
        
        # Try AI Vision first
        char = await AIVision.identify(file_bytes)
        if char['confidence'] < 0.50:
            # Fallback to image search
            char = await ImageSearch.search(file_bytes)
        
        if char['confidence'] < 0.50:
            await status.edit_text(
                f'❌ <b>Character Not Found</b>\n\n'
                f'Confidence: {char["confidence"]:.0%}\n\n'
                f'<i>Could not identify character.</i>',
                parse_mode='HTML'
            )
            return
        
        # Database Verify
        verify = await AnimeDB.verify(char['name'], char['anime'])
        if not verify['verified'] and char['confidence'] < 0.75:
            await status.edit_text(
                f'❌ <b>Not Verified</b>\n\n'
                f'Character: {char["name"]}\n'
                f'Anime: {char["anime"]}\n'
                f'Confidence: {char["confidence"]:.0%}\n\n'
                f'<i>Character not found in anime databases.</i>',
                parse_mode='HTML'
            )
            return
        
        if verify['verified']:
            char['name'] = verify['character_name']
            char['anime'] = verify['anime_name']
        
        # Upload
        await status.edit_text('⬆️ <b>5/5:</b> Uploading...', parse_mode='HTML')
        url = await Uploader.to_catbox(file_bytes, f"char_{photo.file_unique_id}.jpg")
        if not url:
            await status.edit_text('❌ <b>Upload Failed</b>', parse_mode='HTML')
            return
        
        # Save
        char_id = await get_next_id()
        rarity = next((r for r in RarityLevel if r.level == quality.rarity_level), RarityLevel.RARE)
        
        auth_score = ((1.0 - ai_check.ai_probability) * 0.5 + char['confidence'] * 0.3 + (verify['confidence'] if verify['verified'] else 0.5) * 0.2) * 100
        
        char_data = {
            'id': char_id,
            'name': char['name'],
            'anime': char['anime'],
            'rarity': rarity.display_name,
            'rarity_emoji': rarity.emoji,
            'rarity_name': rarity.display_name[2:],
            'img_url': url,
            'uploader_id': str(update.effective_user.id),
            'uploader_name': update.effective_user.first_name,
            'quality_score': round(quality.overall, 2),
            'ai_confidence': round(char['confidence'], 2),
            'authenticity_score': round(auth_score, 1),
            'verified': verify['verified'],
            'verified_sources': verify['sources'],
            'auto_uploaded': True
        }
        
        msg = await Uploader.to_channel(char_data, file_bytes, context)
        if msg and msg.photo:
            char_data['message_id'] = msg.message_id
            char_data['file_id'] = msg.photo[-1].file_id
        
        await collection.insert_one(char_data)
        
        # Success
        await status.edit_text(
            f'✅ <b>Upload Complete!</b>\n\n'
            f'🆔 <code>{char_id}</code>\n\n'
            f'👤 {char["name"]}\n'
            f'📺 {char["anime"]}\n'
            f'{rarity.emoji} {rarity.display_name[2:]}\n\n'
            f'⭐ Quality: {quality.overall:.2f}\n'
            f'🔐 Auth: {auth_score:.0f}%\n'
            f'✅ Verified: {verify["sources"]} DB',
            parse_mode='HTML'
        )
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        
        if status:
            await status.edit_text(
                f'❌ <b>Error!</b>\n\n'
                f'<code>{str(e)[:150]}</code>',
                parse_mode='HTML'
            )

# Register
application.add_handler(MessageHandler(filters.PHOTO & filters.User(user_id=AUTHORIZED_USER), auto_upload))
print(f"✅ Handler registered for user {AUTHORIZED_USER}")