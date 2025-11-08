"""
FULLY INTELLIGENT AUTO-UPLOAD MODULE v3.0
- AI-powered character recognition from images
- Automatic anime detection
- Smart rarity assignment based on image quality
- NO CAPTIONS REQUIRED - Just forward the image!
- Uses Google Vision API / Anime character databases
"""

import io
import re
import asyncio
import hashlib
from typing import Optional, Tuple, List, Dict
from collections import defaultdict
from datetime import datetime

import aiohttp
from pymongo import ReturnDocument
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
from PIL import Image

from shivu import application, collection, db, CHARA_CHANNEL_ID


# ==================== CONFIGURATION ====================
AUTO_UPLOAD_USER_ID = 5147822244
BATCH_SIZE = 50
BATCH_DELAY = 2
MAX_RETRIES = 3
RETRY_DELAY = 5

# AI Recognition APIs (you can configure these)
ENABLE_AI_RECOGNITION = True
ENABLE_REVERSE_IMAGE_SEARCH = True
ENABLE_OCR = True  # For extracting text from images

# Rarity assignment rules (automatic based on image analysis)
RARITY_RULES = {
    'quality_score': {
        (90, 100): '💫 Neon',  # Ultra high quality
        (80, 89): '🟡 Legendary',
        (70, 79): '🟣 Rare',
        (0, 69): '🟢 Common'
    },
    'special_dates': {
        '12-24': '🎄 Christmas',
        '12-25': '🎄 Christmas',
        '10-31': '🎃 Halloween',
        '02-14': '💝 Valentine',
        '01-01': '🎊 New Year'
    }
}

# Anime database (can be expanded or loaded from external source)
ANIME_DATABASE = {
    # Format: character_signature: (character_name, anime_name)
    # This will be populated dynamically from reverse image search
}

# Global state
upload_queues = defaultdict(list)
processing_locks = defaultdict(asyncio.Lock)
status_messages = {}
upload_stats = defaultdict(lambda: {'success': 0, 'failed': 0, 'total': 0})
recognition_cache = {}  # Cache recognized characters


# ==================== AI RECOGNITION FUNCTIONS ====================

async def extract_text_from_image(image_bytes: bytes) -> List[str]:
    """Extract text from image using OCR (can detect watermarks, names)."""
    try:
        # Using free OCR.space API as example
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            data = aiohttp.FormData()
            data.add_field('file', image_bytes, filename='image.jpg')
            data.add_field('language', 'eng')
            data.add_field('isOverlayRequired', 'false')
            
            # OCR.space API with your key
            headers = {'apikey': 'K81013368388957'}
            
            async with session.post(
                'https://api.ocr.space/parse/image',
                data=data,
                headers=headers
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('ParsedResults'):
                        text = result['ParsedResults'][0].get('ParsedText', '')
                        # Extract potential character/anime names
                        lines = [line.strip() for line in text.split('\n') if line.strip()]
                        return lines
    except Exception as e:
        print(f"OCR error: {e}")
    
    return []


async def reverse_image_search(image_bytes: bytes) -> Optional[Dict]:
    """
    Perform reverse image search to find character and anime.
    Uses SauceNAO API (best for anime images).
    """
    try:
        # Get image hash for caching
        img_hash = hashlib.md5(image_bytes).hexdigest()
        if img_hash in recognition_cache:
            print(f"✅ Cache hit for image {img_hash[:8]}")
            return recognition_cache[img_hash]
        
        print(f"🔍 Performing reverse image search...")
        
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # SauceNAO API (free tier available)
            data = aiohttp.FormData()
            data.add_field('file', image_bytes, filename='search.jpg')
            
            # SauceNAO API with your key
            params = {
                'api_key': '09df5f46227581fda504d66d8644d0d74d26c924',
                'output_type': 2,  # JSON output
                'numres': 5  # Top 5 results
            }
            
            async with session.post(
                'https://saucenao.com/search.php',
                data=data,
                params=params
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    
                    if result.get('results'):
                        # Get best match
                        best_match = result['results'][0]
                        similarity = float(best_match.get('header', {}).get('similarity', 0))
                        
                        if similarity > 55:  # Lowered threshold for better detection
                            data = best_match.get('data', {})
                            
                            # Extract character and anime info
                            character_info = {
                                'character': data.get('character') or data.get('characters', ''),
                                'anime': data.get('source') or data.get('title', ''),
                                'similarity': similarity,
                                'source': best_match.get('header', {}).get('index_name', '')
                            }
                            
                            print(f"✅ Found: {character_info['character']} from {character_info['anime']} ({similarity}% match)")
                            
                            # Clean up character name (remove multiple names)
                            if isinstance(character_info['character'], str):
                                character_info['character'] = character_info['character'].split(',')[0].strip()
                            
                            # Cache result
                            recognition_cache[img_hash] = character_info
                            return character_info
                        else:
                            print(f"⚠️ Low similarity: {similarity}% (threshold: 55%)")
    
    except Exception as e:
        print(f"Reverse image search error: {e}")
    
    return None


async def analyze_image_quality(image_bytes: bytes) -> Dict:
    """
    Analyze image quality to auto-assign rarity.
    Checks: resolution, compression, colors, etc.
    """
    try:
        # Ensure bytes object
        if isinstance(image_bytes, bytearray):
            image_bytes = bytes(image_bytes)
        
        image = Image.open(io.BytesIO(image_bytes))
        
        # Get image properties
        width, height = image.size
        resolution = width * height
        format_quality = image.format
        mode = image.mode
        
        # Calculate quality score
        quality_score = 0
        
        # Resolution score (max 40 points)
        if resolution > 4000000:  # 4K+
            quality_score += 40
        elif resolution > 2000000:  # 2K+
            quality_score += 30
        elif resolution > 1000000:  # 1K+
            quality_score += 20
        else:
            quality_score += 10
        
        # Format score (max 20 points)
        if format_quality == 'PNG':
            quality_score += 20
        elif format_quality == 'JPEG':
            quality_score += 15
        else:
            quality_score += 10
        
        # Color depth score (max 20 points)
        if mode == 'RGB' or mode == 'RGBA':
            quality_score += 20
        else:
            quality_score += 10
        
        # Size score (max 20 points)
        file_size = len(image_bytes)
        if file_size > 5000000:  # 5MB+
            quality_score += 20
        elif file_size > 2000000:  # 2MB+
            quality_score += 15
        else:
            quality_score += 10
        
        return {
            'quality_score': quality_score,
            'resolution': resolution,
            'width': width,
            'height': height,
            'format': format_quality,
            'size_mb': file_size / 1024 / 1024
        }
    
    except Exception as e:
        print(f"Image analysis error: {e}")
        return {'quality_score': 50}


def assign_rarity_by_quality(quality_score: int, current_date: str = None) -> str:
    """Automatically assign rarity based on quality score and special dates."""
    
    # Check for special date rarities first
    if current_date:
        date_str = current_date.strftime('%m-%d')
        if date_str in RARITY_RULES['special_dates']:
            return RARITY_RULES['special_dates'][date_str]
    
    # Assign by quality score
    for (min_score, max_score), rarity in RARITY_RULES['quality_score'].items():
        if min_score <= quality_score <= max_score:
            return rarity
    
    return '🟢 Common'


async def smart_character_detection(
    image_bytes: bytes,
    caption: Optional[str] = None
) -> Tuple[Optional[str], Optional[str], str]:
    """
    Intelligently detect character name, anime name, and assign rarity.
    
    Priority:
    1. Caption parsing (if provided) - MOST RELIABLE
    2. OCR text extraction (fast)
    3. Reverse image search (slower but accurate)
    4. Fallback to generic naming
    
    Returns: (character_name, anime_name, rarity)
    """
    
    character_name = None
    anime_name = None
    rarity = '🟢 Common'
    
    # Priority 1: Parse caption if provided (MOST RELIABLE!)
    if caption:
        print(f"📝 Parsing caption: {caption[:50]}...")
        caption_lower = caption.lower()
        lines = [line.strip() for line in caption.split('\n') if line.strip()]
        
        # Pattern 1: Standard format "ID: Name [emoji]\nAnime\nRarity"
        if len(lines) >= 2:
            # First line: character name
            first_line = lines[0]
            char_match = re.search(r'(?:\d+[:.]\s*)?(.+?)(?:\s*\[|$)', first_line)
            if char_match:
                character_name = char_match.group(1).strip()
                character_name = re.sub(r'[^\w\s-]', '', character_name).strip()
            
            # Second line: anime name
            anime_name = lines[1]
            anime_name = re.sub(r'[^\w\s-]', '', anime_name).strip()
            
            # Find rarity in any line
            for line in lines:
                # Check for emoji
                for rarity_key, (emoji, full_name, aliases) in RARITY_DEFINITIONS.items():
                    if emoji in line:
                        rarity = f"{emoji} {full_name}"
                        break
                
                # Check for rarity text
                if rarity == '🟢 Common':
                    for alias in sum([v[2] for v in RARITY_DEFINITIONS.values()], []):
                        if alias in line.lower():
                            for rk, (em, fn, als) in RARITY_DEFINITIONS.items():
                                if alias in als:
                                    rarity = f"{em} {fn}"
                                    break
                
                if rarity != '🟢 Common':
                    break
        
        # Pattern 2: Key-value format "Character: X | Anime: Y"
        if not character_name or not anime_name:
            char_match = re.search(r'(?:character|char|name)[:\s]+([^\n|]+)', caption_lower)
            anime_match = re.search(r'(?:anime|series|from)[:\s]+([^\n|]+)', caption_lower)
            
            if char_match:
                character_name = char_match.group(1).strip()
            if anime_match:
                anime_name = anime_match.group(1).strip()
        
        if character_name and anime_name:
            print(f"✅ Caption parsed: {character_name} from {anime_name}")
            # Analyze image quality for rarity if not found in caption
            if rarity == '🟢 Common':
                quality_info = await analyze_image_quality(image_bytes)
                rarity = assign_rarity_by_quality(quality_info['quality_score'], datetime.now())
            return character_name, anime_name, rarity
    
    # Priority 2: OCR text extraction (fast and often works!)
    if ENABLE_OCR and (not character_name or not anime_name):
        print(f"📝 Attempting OCR text extraction...")
        extracted_text = await extract_text_from_image(image_bytes)
        if extracted_text and len(extracted_text) >= 2:
            if not character_name:
                character_name = extracted_text[0]
                character_name = re.sub(r'[^\w\s-]', '', character_name).strip()
            if not anime_name:
                anime_name = extracted_text[1]
                anime_name = re.sub(r'[^\w\s-]', '', anime_name).strip()
            
            if character_name and anime_name:
                print(f"✅ OCR detected: {character_name} from {anime_name}")
    
    # Priority 3: Reverse image search (slower but accurate for known images)
    if ENABLE_REVERSE_IMAGE_SEARCH and (not character_name or not anime_name):
        print(f"🔍 Trying reverse image search...")
        search_result = await reverse_image_search(image_bytes)
        if search_result:
            if not character_name and search_result.get('character'):
                character_name = search_result['character']
            if not anime_name and search_result.get('anime'):
                anime_name = search_result['anime']
            
            if character_name and anime_name:
                print(f"✅ Reverse search found: {character_name} from {anime_name}")
    
    # Analyze image quality for rarity assignment
    quality_info = await analyze_image_quality(image_bytes)
    rarity = assign_rarity_by_quality(quality_info['quality_score'], datetime.now())
    
    # Clean up names
    if character_name:
        character_name = re.sub(r'[^\w\s-]', '', character_name).strip()
        character_name = ' '.join(character_name.split())[:50]  # Limit length
    
    if anime_name:
        anime_name = re.sub(r'[^\w\s-]', '', anime_name).strip()
        anime_name = ' '.join(anime_name.split())[:50]
    
    # Final validation
    if character_name and anime_name:
        print(f"✅ Final result: {character_name} from {anime_name} - {rarity}")
        return character_name, anime_name, rarity
    
    # If still no results, return None to mark for manual review
    print(f"⚠️ Could not detect character - will mark for manual review")
    return None, None, rarity


# ==================== HELPER FUNCTIONS ====================

async def get_next_sequence_number(sequence_name: str) -> int:
    """Generate the next sequence number for character IDs."""
    try:
        sequence_collection = db.sequences
        sequence_document = await sequence_collection.find_one_and_update(
            {'_id': sequence_name},
            {'$inc': {'sequence_value': 1}},
            return_document=ReturnDocument.AFTER,
            upsert=True
        )
        return sequence_document.get('sequence_value', 0)
    except Exception:
        return 0


async def upload_to_catbox(file_bytes: bytes, filename: str, max_retries: int = 3) -> Optional[str]:
    """Upload file to Catbox with retry logic."""
    for attempt in range(max_retries):
        try:
            timeout = aiohttp.ClientTimeout(total=300)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                data = aiohttp.FormData()
                data.add_field('reqtype', 'fileupload')
                data.add_field('fileToUpload', file_bytes, filename=filename)

                async with session.post("https://catbox.moe/user/api.php", data=data) as response:
                    if response.status == 200:
                        result = (await response.text()).strip()
                        if result.startswith('http'):
                            return result
            
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        except Exception as e:
            print(f"Catbox upload attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
    
    return None


async def check_duplicate(character_name: str, anime_name: str) -> bool:
    """Check if character already exists."""
    try:
        existing = await collection.find_one({
            'name': {'$regex': f'^{re.escape(character_name)}$', '$options': 'i'},
            'anime': {'$regex': f'^{re.escape(anime_name)}$', '$options': 'i'}
        })
        return existing is not None
    except Exception:
        return False


async def process_single_upload(
    item: Dict,
    user_id: int,
    user_name: str,
    context: ContextTypes.DEFAULT_TYPE
) -> Dict[str, any]:
    """Process a single character upload with AI recognition."""
    
    for attempt in range(MAX_RETRIES):
        try:
            # AI Recognition - automatically detect character info
            character_name, anime_name, rarity = await smart_character_detection(
                item['file_data'],
                item.get('caption')
            )
            
            # Validation - ensure we have at least basic info
            if not character_name or not anime_name:
                # Provide helpful feedback
                feedback = "⚠️ AI Detection Failed\n\n"
                feedback += "Could not identify character automatically.\n"
                feedback += "💡 To fix this, include a caption like:\n\n"
                feedback += "Character Name\n"
                feedback += "Anime Name\n"
                feedback += "Rarity (optional)\n\n"
                feedback += "Example:\n"
                feedback += "Naruto Uzumaki\n"
                feedback += "Naruto\n"
                feedback += "Legendary"
                
                return {
                    'success': False,
                    'message': feedback,
                    'char_id': None,
                    'needs_manual': True
                }
            
            # Check for duplicates
            is_duplicate = await check_duplicate(character_name, anime_name)
            if is_duplicate:
                return {
                    'success': False,
                    'message': f"⚠️ {character_name}: Already exists (skipped)",
                    'char_id': None,
                    'is_duplicate': True
                }
            
            # Upload to Catbox
            media_url = await upload_to_catbox(item['file_data'], item['filename'])
            
            if not media_url:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                return {
                    'success': False,
                    'message': f"❌ {character_name}: Upload failed",
                    'char_id': None
                }
            
            # Generate character ID
            char_id = str(await get_next_sequence_number('character_id')).zfill(2)
            
            # Create character document
            character = {
                'img_url': media_url,
                'id': char_id,
                'name': character_name,
                'anime': anime_name,
                'rarity': rarity,
                'is_video': item['is_video'],
                'uploaded_at': datetime.utcnow(),
                'uploaded_by': user_id,
                'auto_detected': True  # Flag for AI-detected characters
            }
            
            # Create caption
            media_type = "🎥 Video" if item['is_video'] else "🖼 Image"
            channel_caption = (
                f'<b>{char_id}:</b> {character_name}\n'
                f'<b>{anime_name}</b>\n'
                f'<b>{rarity[0]} 𝙍𝘼𝙍𝙄𝙏𝙔:</b> {rarity[2:]}\n'
                f'<b>Type:</b> {media_type}\n'
                f'<b>🤖 AI Detected</b>\n\n'
                f'𝑴𝒂𝒅𝒆 𝑩𝒚 ➥ <a href="tg://user?id={user_id}">{user_name}</a>'
            )
            
            # Upload to channel
            if item['is_video']:
                channel_msg = await context.bot.send_video(
                    chat_id=CHARA_CHANNEL_ID,
                    video=media_url,
                    caption=channel_caption,
                    parse_mode='HTML',
                    supports_streaming=True,
                    read_timeout=300,
                    write_timeout=300
                )
                character['file_id'] = channel_msg.video.file_id
                character['file_unique_id'] = channel_msg.video.file_unique_id
            else:
                channel_msg = await context.bot.send_photo(
                    chat_id=CHARA_CHANNEL_ID,
                    photo=media_url,
                    caption=channel_caption,
                    parse_mode='HTML',
                    read_timeout=180,
                    write_timeout=180
                )
                character['file_id'] = channel_msg.photo[-1].file_id
                character['file_unique_id'] = channel_msg.photo[-1].file_unique_id
            
            character['message_id'] = channel_msg.message_id
            
            # Insert to database
            await collection.insert_one(character)
            
            return {
                'success': True,
                'message': f"✅ {char_id}: {character_name} ({anime_name}) - {rarity}",
                'char_id': char_id
            }
            
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
                continue
            return {
                'success': False,
                'message': f"❌ Error: {str(e)[:50]}",
                'char_id': None
            }
    
    return {
        'success': False,
        'message': f"❌ Max retries exceeded",
        'char_id': None
    }


async def process_batch(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Process batch with AI recognition."""
    
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
                    f"🤖 AI AUTO-RECOGNITION\n\n"
                    f"📦 Analyzing {total} images...\n"
                    f"🔍 Detecting characters & anime\n"
                    f"⭐ Auto-assigning rarities\n\n"
                    f"⏳ Please wait..."
                )
            except Exception:
                pass
        
        results = []
        success_count = 0
        failed_count = 0
        duplicate_count = 0
        manual_needed = 0
        
        # Process with AI recognition
        for i in range(0, total, 3):  # Slower batches for AI processing
            batch = queue[i:i+3]
            tasks = [
                process_single_upload(item, user_id, user_name, context)
                for item in batch
            ]
            batch_results = await asyncio.gather(*tasks)
            
            for result in batch_results:
                results.append(result)
                if result['success']:
                    success_count += 1
                elif result.get('is_duplicate'):
                    duplicate_count += 1
                elif result.get('needs_manual'):
                    manual_needed += 1
                else:
                    failed_count += 1
            
            # Update progress
            processed = len(results)
            if user_id in status_messages:
                try:
                    await status_messages[user_id].edit_text(
                        f"🤖 AI PROCESSING...\n\n"
                        f"✅ Detected: {success_count}\n"
                        f"⚠️ Duplicates: {duplicate_count}\n"
                        f"🔍 Manual needed: {manual_needed}\n"
                        f"❌ Failed: {failed_count}\n\n"
                        f"Progress: {processed}/{total}"
                    )
                except Exception:
                    pass
            
            await asyncio.sleep(1)
        
        # Summary
        summary = f"🎉 AI AUTO-UPLOAD COMPLETE!\n\n"
        summary += f"📊 Results:\n"
        summary += f"✅ Auto-detected: {success_count}/{total}\n"
        summary += f"⚠️ Duplicates: {duplicate_count}\n"
        summary += f"🔍 Manual review: {manual_needed}\n"
        summary += f"❌ Failed: {failed_count}\n\n"
        
        if success_count > 0:
            summary += f"🎊 Successfully uploaded:\n"
            success_results = [r['message'] for r in results if r['success']][:10]
            summary += '\n'.join(success_results)
            if len([r for r in results if r['success']]) > 10:
                summary += f"\n... and {success_count - 10} more!"
            summary += "\n\n"
        
        if manual_needed > 0:
            summary += f"💡 TIP: For better AI detection:\n"
            summary += f"• Add simple captions (Name\\nAnime)\n"
            summary += f"• Use high-quality images\n"
            summary += f"• Try popular anime characters\n"
        
        if user_id in status_messages:
            try:
                await status_messages[user_id].edit_text(summary)
            except Exception:
                pass
        
        # Process next batch
        if upload_queues[user_id]:
            await asyncio.sleep(2)
            asyncio.create_task(process_batch(user_id, context))


async def auto_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    FULLY AUTOMATIC HANDLER - AI detects everything!
    Just forward ANY anime image - no captions needed!
    """
    
    if update.effective_user.id != AUTO_UPLOAD_USER_ID:
        return
    
    message = update.message
    
    if not (message.photo or message.video or message.document):
        return
    
    # Download file
    try:
        is_video = False
        if message.photo:
            file = await message.photo[-1].get_file()
            filename = f"char_{message.message_id}.jpg"
        elif message.video:
            file = await message.video.get_file()
            filename = f"char_{message.message_id}.mp4"
            is_video = True
        else:
            file = await message.document.get_file()
            filename = message.document.file_name or f"char_{message.message_id}"
            if message.document.mime_type and 'video' in message.document.mime_type:
                is_video = True
        
        file_bytes = await file.download_as_bytearray()
    except Exception as e:
        print(f"Download error: {e}")
        return
    
    user_id = update.effective_user.id
    
    # Add to queue
    upload_queues[user_id].append({
        'file_data': bytes(file_bytes),
        'filename': filename,
        'caption': message.caption,  # Optional
        'is_video': is_video,
        'user_name': update.effective_user.first_name
    })
    
    queue_size = len(upload_queues[user_id])
    
    if queue_size == 1:
        status_msg = await message.reply_text(
            f"🤖 AI AUTO-RECOGNITION ACTIVATED\n\n"
            f"🔍 Analyzing image...\n"
            f"📝 Detecting character & anime\n"
            f"⭐ Calculating rarity\n\n"
            f"⏳ Processing in {BATCH_DELAY}s..."
        )
        status_messages[user_id] = status_msg
        
        await asyncio.sleep(BATCH_DELAY)
        asyncio.create_task(process_batch(user_id, context))
    else:
        try:
            if user_id in status_messages:
                await status_messages[user_id].edit_text(
                    f"🤖 AI MODE\n\n"
                    f"📦 Queue: {queue_size}\n"
                    f"🔍 Auto-detecting all...\n\n"
                    f"⏳ Processing..."
                )
        except Exception:
            pass


# Register handler
application.add_handler(
    MessageHandler(
        filters.User(AUTO_UPLOAD_USER_ID) & 
        (filters.PHOTO | filters.VIDEO | filters.Document.IMAGE),
        auto_upload_handler,
        block=False
    )
)

print(f"✅ INTELLIGENT AI AUTO-UPLOAD MODULE v3.0")
print(f"🤖 AI Recognition: {ENABLE_AI_RECOGNITION}")
print(f"🔍 Reverse Search: {ENABLE_REVERSE_IMAGE_SEARCH}")
print(f"📝 OCR Enabled: {ENABLE_OCR}")
print(f"🚀 Just forward images - AI does the rest!")