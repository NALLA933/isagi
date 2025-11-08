"""
Fully Automatic AI Upload Module v5.0
- Trace.moe anime detection (with token)
- AniList character database
- OCR.space text extraction (free)
- Face similarity matching
- Auto-assigns rarity by quality
"""

import io
import re
import asyncio
import hashlib
import base64
from typing import Optional, Tuple, Dict
from collections import defaultdict
from datetime import datetime

import aiohttp
import imagehash
from pymongo import ReturnDocument
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
from PIL import Image

from shivu import application, collection, db, CHARA_CHANNEL_ID

AUTO_UPLOAD_USER_ID = 5147822244
BATCH_SIZE = 15
BATCH_DELAY = 3

# Get your token from: https://trace.moe/token
TRACE_MOE_TOKEN = "YOUR_TRACEMOE_TOKEN"  # Replace this
TRACE_MOE_API = f"https://api.trace.moe/search?token={TRACE_MOE_TOKEN}"
ANILIST_API = "https://graphql.anilist.co"

RARITY_BY_QUALITY = {
    (90, 100): 'Neon', (80, 89): 'Legendary', (70, 79): 'Rare', (50, 69): 'Common', (0, 49): 'Common'
}

RARITY_EMOJIS = {
    'Neon': '💫', 'Legendary': '🟡', 'Rare': '🟣', 'Common': '🟢',
    'Christmas': '🎄', 'Halloween': '🎃', 'Valentine': '💝'
}

upload_queues = defaultdict(list)
processing_locks = defaultdict(asyncio.Lock)
status_messages = {}
cache = {}


async def trace_moe_search(image_bytes: bytes) -> Optional[Dict]:
    try:
        b64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                TRACE_MOE_API,
                json={"image": b64_image},
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get('result'):
                        best = data['result'][0]
                        similarity = best.get('similarity', 0) * 100
                        
                        if similarity > 65:
                            anilist = best.get('anilist', {})
                            return {
                                'anime': anilist.get('title', {}).get('romaji', ''),
                                'anime_id': anilist.get('id'),
                                'similarity': similarity
                            }
    except Exception as e:
        print(f"Trace.moe error: {e}")
    return None


async def get_anilist_characters(anime_id: int) -> list:
    try:
        query = '''
        query ($id: Int) {
          Media(id: $id, type: ANIME) {
            characters(sort: ROLE, perPage: 15) {
              edges {
                role
                node {
                  name { full }
                  image { large }
                }
              }
            }
          }
        }
        '''
        
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                ANILIST_API,
                json={'query': query, 'variables': {'id': anime_id}}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    edges = data.get('data', {}).get('Media', {}).get('characters', {}).get('edges', [])
                    
                    return [{
                        'name': e['node']['name']['full'],
                        'image': e['node']['image']['large'],
                        'role': e['role']
                    } for e in edges]
    except Exception as e:
        print(f"AniList error: {e}")
    return []


async def extract_text_ocr(image_bytes: bytes) -> list:
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            data = aiohttp.FormData()
            data.add_field("file", image_bytes, filename="image.jpg")

            async with session.post("https://api.ocr.space/parse/image", data=data) as response:
                result = await response.json()
                text = result.get("ParsedResults", [{}])[0].get("ParsedText", "")
                return [line.strip() for line in text.split("\n") if line.strip()]
    except:
        return []


def analyze_quality(image_bytes: bytes) -> int:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        res = w * h
        size = len(image_bytes)
        
        score = 0
        if res > 4000000: score += 40
        elif res > 2000000: score += 30
        elif res > 1000000: score += 20
        else: score += 10
        
        if img.format == 'PNG': score += 30
        elif img.format == 'JPEG': score += 20
        else: score += 10
        
        if size > 3000000: score += 30
        elif size > 1000000: score += 20
        else: score += 10
        
        return min(score, 100)
    except:
        return 50


def get_rarity(quality: int) -> str:
    date = datetime.now().strftime('%m-%d')
    if date in ['12-24', '12-25']: return 'Christmas'
    if date == '10-31': return 'Halloween'
    if date == '02-14': return 'Valentine'
    
    for (min_q, max_q), rarity in RARITY_BY_QUALITY.items():
        if min_q <= quality <= max_q:
            return rarity
    return 'Common'


async def parse_caption(caption: str) -> Optional[Tuple[str, str, str]]:
    if not caption:
        return None
    
    lines = [l.strip() for l in caption.split('\n') if l.strip()]
    if len(lines) < 2:
        return None
    
    char = re.sub(r'^\d+[:.]\s*', '', lines[0])
    char = re.sub(r'\[.*?\]', '', char).strip()
    char = re.sub(r'[^\w\s-]', ' ', char).strip()
    char = ' '.join(char.split())
    
    anime = re.sub(r'[^\w\s-]', ' ', lines[1]).strip()
    anime = ' '.join(anime.split())
    
    rarity = 'Common'
    for line in lines:
        for emoji, name in RARITY_EMOJIS.items():
            if emoji in line or name.lower() in line.lower():
                rarity = name
                break
    
    if char and anime:
        return char, anime, rarity
    return None


async def smart_detect(image_bytes: bytes, caption: str = None) -> Tuple[str, str, str]:
    img_hash = hashlib.md5(image_bytes).hexdigest()
    if img_hash in cache:
        return cache[img_hash]
    
    char_name, anime_name, rarity = None, None, 'Common'
    
    # Try caption first
    if caption:
        parsed = await parse_caption(caption)
        if parsed:
            char_name, anime_name, rarity = parsed
            quality = analyze_quality(image_bytes)
            if rarity == 'Common':
                rarity = get_rarity(quality)
            cache[img_hash] = (char_name, anime_name, rarity)
            return char_name, anime_name, rarity
    
    # AI detection
    trace_result = await trace_moe_search(image_bytes)
    
    if trace_result and trace_result['anime']:
        anime_name = trace_result['anime']
        chars = await get_anilist_characters(trace_result['anime_id'])
        
        if chars:
            # Face similarity matching
            try:
                img1 = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                hash1 = imagehash.phash(img1)
                
                scored = []
                async with aiohttp.ClientSession() as session:
                    for c in chars[:8]:
                        try:
                            async with session.get(c['image']) as resp:
                                if resp.status == 200:
                                    img2 = Image.open(io.BytesIO(await resp.read())).convert("RGB")
                                    hash2 = imagehash.phash(img2)
                                    diff = hash1 - hash2
                                    scored.append((diff, c['name']))
                        except:
                            continue
                
                if scored:
                    scored.sort(key=lambda x: x[0])
                    char_name = scored[0][1]
                else:
                    main = [c for c in chars if c['role'] == 'MAIN']
                    char_name = main[0]['name'] if main else chars[0]['name']
            except:
                main = [c for c in chars if c['role'] == 'MAIN']
                char_name = main[0]['name'] if main else chars[0]['name']
    
    # OCR fallback
    if not char_name or not anime_name:
        texts = await extract_text_ocr(image_bytes)
        if len(texts) >= 2:
            char_name = char_name or texts[0]
            anime_name = anime_name or texts[1]
    
    quality = analyze_quality(image_bytes)
    rarity = get_rarity(quality)
    
    if char_name and anime_name:
        char_name = ' '.join(char_name.split())[:60]
        anime_name = ' '.join(anime_name.split())[:60]
        cache[img_hash] = (char_name, anime_name, rarity)
        return char_name, anime_name, rarity
    
    return None, None, rarity


async def get_next_id() -> int:
    try:
        doc = await db.sequences.find_one_and_update(
            {'_id': 'character_id'},
            {'$inc': {'sequence_value': 1}},
            return_document=ReturnDocument.AFTER,
            upsert=True
        )
        return doc.get('sequence_value', 0)
    except:
        return 0


async def upload_catbox(file_bytes: bytes, filename: str) -> str:
    try:
        timeout = aiohttp.ClientTimeout(total=300)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            data = aiohttp.FormData()
            data.add_field('reqtype', 'fileupload')
            data.add_field('fileToUpload', file_bytes, filename=filename)
            
            async with session.post("https://catbox.moe/user/api.php", data=data) as resp:
                if resp.status == 200:
                    url = (await resp.text()).strip()
                    if url.startswith('http'):
                        return url
    except Exception as e:
        print(f"Upload error: {e}")
    return None


async def check_duplicate(char: str, anime: str) -> bool:
    try:
        exists = await collection.find_one({
            'name': {'$regex': f'^{re.escape(char)}$', '$options': 'i'},
            'anime': {'$regex': f'^{re.escape(anime)}$', '$options': 'i'}
        })
        return exists is not None
    except:
        return False


async def process_upload(item: dict, user_id: int, user_name: str, ctx: ContextTypes.DEFAULT_TYPE) -> dict:
    try:
        char, anime, rarity = await smart_detect(item['file_data'], item.get('caption'))
        
        if not char or not anime:
            return {'success': False, 'msg': 'AI failed - add caption: Name\\nAnime', 'manual': True}
        
        if await check_duplicate(char, anime):
            return {'success': False, 'msg': f'{char}: Duplicate', 'dup': True}
        
        url = await upload_catbox(item['file_data'], item['filename'])
        if not url:
            return {'success': False, 'msg': f'{char}: Upload failed'}
        
        char_id = str(await get_next_id()).zfill(2)
        
        character = {
            'img_url': url, 'id': char_id, 'name': char, 'anime': anime,
            'rarity': f"{RARITY_EMOJIS[rarity]} {rarity}", 'is_video': item['is_video'],
            'uploaded_at': datetime.utcnow(), 'uploaded_by': user_id, 'ai_detected': True
        }
        
        media_type = "Video" if item['is_video'] else "Image"
        caption = (
            f'<b>{char_id}:</b> {char}\n'
            f'<b>{anime}</b>\n'
            f'<b>{RARITY_EMOJIS[rarity]} RARITY:</b> {rarity}\n'
            f'<b>Type:</b> {media_type}\n'
            f'<b>AI Detected</b>\n\n'
            f'Made By <a href="tg://user?id={user_id}">{user_name}</a>'
        )
        
        if item['is_video']:
            msg = await ctx.bot.send_video(
                chat_id=CHARA_CHANNEL_ID, video=url, caption=caption,
                parse_mode='HTML', supports_streaming=True, read_timeout=300, write_timeout=300
            )
            character['file_id'] = msg.video.file_id
            character['file_unique_id'] = msg.video.file_unique_id
        else:
            msg = await ctx.bot.send_photo(
                chat_id=CHARA_CHANNEL_ID, photo=url, caption=caption,
                parse_mode='HTML', read_timeout=180, write_timeout=180
            )
            character['file_id'] = msg.photo[-1].file_id
            character['file_unique_id'] = msg.photo[-1].file_unique_id
        
        character['message_id'] = msg.message_id
        await collection.insert_one(character)
        
        return {'success': True, 'msg': f'{char_id}: {char} ({anime})', 'id': char_id}
    
    except Exception as e:
        return {'success': False, 'msg': f'Error: {str(e)[:30]}'}


async def process_batch(user_id: int, ctx: ContextTypes.DEFAULT_TYPE):
    async with processing_locks[user_id]:
        if not upload_queues[user_id]:
            return
        
        queue = upload_queues[user_id][:BATCH_SIZE]
        upload_queues[user_id] = upload_queues[user_id][BATCH_SIZE:]
        
        total = len(queue)
        user_name = queue[0]['user_name']
        
        if user_id in status_messages:
            try:
                await status_messages[user_id].edit_text(
                    f"AI AUTO-UPLOAD\n\nProcessing {total} images\n"
                    f"Trace.moe + AniList + Face matching\n\nPlease wait..."
                )
            except:
                pass
        
        results = {'ok': 0, 'fail': 0, 'dup': 0, 'manual': 0}
        msgs = []
        
        for idx, item in enumerate(queue, 1):
            res = await process_upload(item, user_id, user_name, ctx)
            
            if res['success']:
                results['ok'] += 1
                msgs.append(res['msg'])
            elif res.get('dup'):
                results['dup'] += 1
            elif res.get('manual'):
                results['manual'] += 1
            else:
                results['fail'] += 1
            
            if idx % 3 == 0 and user_id in status_messages:
                try:
                    await status_messages[user_id].edit_text(
                        f"AI PROCESSING\n\n"
                        f"Uploaded: {results['ok']}\n"
                        f"Duplicates: {results['dup']}\n"
                        f"Manual: {results['manual']}\n"
                        f"Failed: {results['fail']}\n\n"
                        f"Progress: {idx}/{total}"
                    )
                except:
                    pass
            
            await asyncio.sleep(2)
        
        summary = f"COMPLETE!\n\n"
        summary += f"Uploaded: {results['ok']}/{total}\n"
        summary += f"Duplicates: {results['dup']}\n"
        summary += f"Need captions: {results['manual']}\n"
        summary += f"Failed: {results['fail']}\n\n"
        
        if msgs:
            summary += "Uploaded:\n" + '\n'.join(msgs[:8])
            if len(msgs) > 8:
                summary += f"\n...+{len(msgs)-8} more"
        
        if results['manual'] > 0:
            summary += "\n\nTip: Add captions - Name\\nAnime"
        
        if user_id in status_messages:
            try:
                await status_messages[user_id].edit_text(summary)
            except:
                pass
        
        if upload_queues[user_id]:
            await asyncio.sleep(2)
            asyncio.create_task(process_batch(user_id, ctx))


async def auto_upload_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTO_UPLOAD_USER_ID:
        return
    
    msg = update.message
    if not (msg.photo or msg.video or msg.document):
        return
    
    try:
        is_video = False
        if msg.photo:
            file = await msg.photo[-1].get_file()
            filename = f"char_{msg.message_id}.jpg"
        elif msg.video:
            file = await msg.video.get_file()
            filename = f"char_{msg.message_id}.mp4"
            is_video = True
        else:
            file = await msg.document.get_file()
            filename = msg.document.file_name or f"char_{msg.message_id}"
            if msg.document.mime_type and 'video' in msg.document.mime_type:
                is_video = True
        
        file_bytes = await file.download_as_bytearray()
    except Exception as e:
        print(f"Download error: {e}")
        return
    
    user_id = update.effective_user.id
    
    upload_queues[user_id].append({
        'file_data': bytes(file_bytes),
        'filename': filename,
        'caption': msg.caption,
        'is_video': is_video,
        'user_name': update.effective_user.first_name
    })
    
    queue_size = len(upload_queues[user_id])
    
    if queue_size == 1:
        status_msg = await msg.reply_text(
            f"AI AUTO-UPLOAD\n\nTrace.moe anime detection\n"
            f"AniList character lookup\nFace similarity matching\n\n"
            f"Starting in {BATCH_DELAY}s..."
        )
        status_messages[user_id] = status_msg
        
        await asyncio.sleep(BATCH_DELAY)
        asyncio.create_task(process_batch(user_id, ctx))
    else:
        try:
            if user_id in status_messages:
                await status_messages[user_id].edit_text(
                    f"AI MODE\n\nQueue: {queue_size}\nAuto-detecting...\n\nProcessing..."
                )
        except:
            pass


application.add_handler(
    MessageHandler(
        filters.User(AUTO_UPLOAD_USER_ID) & 
        (filters.PHOTO | filters.VIDEO | filters.Document.IMAGE),
        auto_upload_handler,
        block=False
    )
)

print(f"AI AUTO-UPLOAD v5.0 LOADED")
print(f"User: {AUTO_UPLOAD_USER_ID}")
print(f"Trace.moe + AniList + Face matching")
print(f"REMEMBER: Add your Trace.moe token!")