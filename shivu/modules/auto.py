"""
Auto Upload Module - Automatically uploads characters from forwarded messages
Supports BULK uploads (up to 100 characters at once)
Specifically for user ID: 5147822244
"""

import io
import re
import asyncio
from typing import Optional, Tuple, List

import aiohttp
from pymongo import ReturnDocument
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from shivu import application, collection, db, CHARA_CHANNEL_ID


# Configuration
AUTO_UPLOAD_USER_ID = 5147822244  # Your Telegram user ID
MAX_BULK_UPLOAD = 100  # Maximum characters to upload at once

RARITY_MAP = {
    1: "🟢 Common",
    2: "🟣 Rare",
    3: "🟡 Legendary",
    4: "💮 Special Edition",
    5: "💫 Neon",
    6: "✨ Manga",
    7: "🎭 Cosplay",
    8: "🎐 Celestial",
    9: "🔮 Premium Edition",
    10: "💋 Erotic",
    11: "🌤 Summer",
    12: "☃️ Winter",
    13: "☔️ Monsoon",
    14: "💝 Valentine",
    15: "🎃 Halloween",
    16: "🎄 Christmas",
    17: "🏵 Mythic",
    18: "🎗 Special Events",
    19: "🎥 AMV",
    20: "👼 Tiny"
}

# Reverse mapping for easy lookup
RARITY_EMOJI_MAP = {v: v for k, v in RARITY_MAP.items()}
RARITY_EMOJI_MAP.update({
    "Common": "🟢 Common",
    "Rare": "🟣 Rare",
    "Legendary": "🟡 Legendary",
    "Special Edition": "💮 Special Edition",
    "Neon": "💫 Neon",
    "Manga": "✨ Manga",
    "Cosplay": "🎭 Cosplay",
    "Celestial": "🎐 Celestial",
    "Premium Edition": "🔮 Premium Edition",
    "Erotic": "💋 Erotic",
    "Summer": "🌤 Summer",
    "Winter": "☃️ Winter",
    "Monsoon": "☔️ Monsoon",
    "Valentine": "💝 Valentine",
    "Halloween": "🎃 Halloween",
    "Christmas": "🎄 Christmas",
    "Mythic": "🏵 Mythic",
    "Special Events": "🎗 Special Events",
    "AMV": "🎥 AMV",
    "Tiny": "👼 Tiny"
})

VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv'}

# Store for bulk uploads
bulk_upload_queue = {}


# Helper Functions
async def get_next_sequence_number(sequence_name: str) -> int:
    """Generate the next sequence number for character IDs."""
    sequence_collection = db.sequences
    sequence_document = await sequence_collection.find_one_and_update(
        {'_id': sequence_name},
        {'$inc': {'sequence_value': 1}},
        return_document=ReturnDocument.AFTER
    )

    if not sequence_document:
        await sequence_collection.insert_one({
            '_id': sequence_name,
            'sequence_value': 0
        })
        return 0

    return sequence_document['sequence_value']


async def upload_to_catbox(file_bytes: bytes, filename: str) -> Optional[str]:
    """Upload file to Catbox and return the URL."""
    try:
        timeout = aiohttp.ClientTimeout(total=300)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            data = aiohttp.FormData()
            data.add_field('reqtype', 'fileupload')
            data.add_field('fileToUpload', file_bytes, filename=filename)

            async with session.post("https://catbox.moe/user/api.php", data=data) as response:
                if response.status == 200:
                    result = (await response.text()).strip()
                    return result if result.startswith('http') else None
                return None
    except Exception as e:
        print(f"Catbox upload error: {e}")
        return None


def parse_caption(caption: str) -> Optional[Tuple[str, str, str]]:
    """
    Parse caption to extract character name, anime name, and rarity.
    
    Expected format:
    04: Megumi Fushiguro [🎄]
    Jujutsu Kaisen
    🎄 𝙍𝘼𝙍𝙄𝙏𝙔: Christmas
    """
    if not caption:
        return None
    
    lines = [line.strip() for line in caption.split('\n') if line.strip()]
    
    if len(lines) < 3:
        return None
    
    try:
        # Parse first line: "04: Megumi Fushiguro [🎄]"
        first_line = lines[0]
        # Remove ID and brackets content
        name_match = re.search(r':\s*(.+?)(?:\s*\[|$)', first_line)
        if not name_match:
            return None
        character_name = name_match.group(1).strip()
        
        # Parse second line: anime name
        anime_name = lines[1].strip()
        
        # Parse third line: rarity
        rarity_line = lines[2]
        # Extract rarity name after "𝙍𝘼𝙍𝙄𝙏𝙔:" or "RARITY:"
        rarity_match = re.search(r'(?:𝙍𝘼𝙍𝙄𝙏𝙔|RARITY|Rarity):\s*(.+?)(?:\s*Type:|$)', rarity_line, re.IGNORECASE)
        if not rarity_match:
            # Try to find rarity by emoji
            for rarity_name, rarity_full in RARITY_EMOJI_MAP.items():
                if rarity_name in rarity_line or rarity_full in rarity_line:
                    return character_name, anime_name, rarity_full
            return None
        
        rarity_text = rarity_match.group(1).strip()
        
        # Match with known rarities
        for rarity_name, rarity_full in RARITY_EMOJI_MAP.items():
            if rarity_text.lower() == rarity_name.lower() or rarity_text == rarity_full:
                return character_name, anime_name, rarity_full
        
        return None
        
    except Exception as e:
        print(f"Caption parsing error: {e}")
        return None


async def process_single_character(
    file_data: bytes,
    filename: str,
    character_name: str,
    anime_name: str,
    rarity: str,
    is_video_file: bool,
    user_id: int,
    user_name: str,
    context: ContextTypes.DEFAULT_TYPE
) -> Tuple[bool, str, Optional[str]]:
    """
    Process and upload a single character.
    Returns: (success, message, char_id)
    """
    try:
        # Upload to Catbox
        media_url = await upload_to_catbox(io.BytesIO(file_data), filename)
        
        if not media_url:
            return False, f"❌ Failed to upload to Catbox", None
        
        # Generate character ID
        char_id = str(await get_next_sequence_number('character_id')).zfill(2)
        
        # Create character entry
        character = {
            'img_url': media_url,
            'id': char_id,
            'name': character_name,
            'anime': anime_name,
            'rarity': rarity,
            'is_video': is_video_file
        }
        
        # Create caption for channel
        media_type = "🎥 Video" if is_video_file else "🖼 Image"
        channel_caption = (
            f'<b>{char_id}:</b> {character_name}\n'
            f'<b>{anime_name}</b>\n'
            f'<b>{rarity[0]} 𝙍𝘼𝙍𝙄𝙏𝙔:</b> {rarity[2:]}\n'
            f'<b>Type:</b> {media_type}\n\n'
            f'𝑴𝒂𝒅𝒆 𝑩𝒚 ➥ <a href="tg://user?id={user_id}">{user_name}</a>'
        )
        
        # Upload to channel
        if is_video_file:
            channel_msg = await context.bot.send_video(
                chat_id=CHARA_CHANNEL_ID,
                video=media_url,
                caption=channel_caption,
                parse_mode='HTML',
                supports_streaming=True,
                read_timeout=300,
                write_timeout=300,
                connect_timeout=60,
                pool_timeout=60
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
        
        return True, f"✅ {char_id}: {character_name}", char_id
        
    except Exception as e:
        return False, f"❌ {character_name}: {str(e)}", None


async def bulk_upload_processor(
    user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    status_message
):
    """
    Process bulk upload queue after collection is complete.
    """
    await asyncio.sleep(5)  # Wait 5 seconds for more uploads
    
    if user_id not in bulk_upload_queue or not bulk_upload_queue[user_id]:
        return
    
    queue = bulk_upload_queue[user_id]
    total = len(queue)
    
    if total > MAX_BULK_UPLOAD:
        await status_message.edit_text(
            f"⚠️ Too many characters!\n\n"
            f"You sent {total} characters.\n"
            f"Maximum allowed: {MAX_BULK_UPLOAD}\n\n"
            f"Please send in smaller batches."
        )
        bulk_upload_queue[user_id] = []
        return
    
    await status_message.edit_text(
        f"🚀 BULK AUTO-UPLOAD STARTED!\n\n"
        f"📦 Total characters: {total}\n"
        f"⏳ Processing... This may take a while.\n\n"
        f"Progress: 0/{total}"
    )
    
    results = {
        'success': [],
        'failed': []
    }
    
    # Process each character
    for idx, item in enumerate(queue, 1):
        try:
            success, message, char_id = await process_single_character(
                item['file_data'],
                item['filename'],
                item['character_name'],
                item['anime_name'],
                item['rarity'],
                item['is_video'],
                user_id,
                item['user_name'],
                context
            )
            
            if success:
                results['success'].append(message)
            else:
                results['failed'].append(message)
            
            # Update progress every 5 uploads
            if idx % 5 == 0 or idx == total:
                await status_message.edit_text(
                    f"🚀 BULK AUTO-UPLOAD IN PROGRESS...\n\n"
                    f"📦 Total: {total}\n"
                    f"✅ Success: {len(results['success'])}\n"
                    f"❌ Failed: {len(results['failed'])}\n\n"
                    f"Progress: {idx}/{total}"
                )
            
            # Small delay to avoid rate limits
            await asyncio.sleep(1)
            
        except Exception as e:
            results['failed'].append(f"❌ Error: {str(e)}")
    
    # Send final summary
    summary = f"🎉 BULK AUTO-UPLOAD COMPLETE!\n\n"
    summary += f"📊 SUMMARY:\n"
    summary += f"✅ Successful: {len(results['success'])}/{total}\n"
    summary += f"❌ Failed: {len(results['failed'])}/{total}\n\n"
    
    if results['success']:
        summary += f"✅ UPLOADED:\n"
        # Show first 20 successes
        for msg in results['success'][:20]:
            summary += f"{msg}\n"
        if len(results['success']) > 20:
            summary += f"... and {len(results['success']) - 20} more!\n"
        summary += "\n"
    
    if results['failed']:
        summary += f"❌ FAILED:\n"
        for msg in results['failed'][:10]:
            summary += f"{msg}\n"
        if len(results['failed']) > 10:
            summary += f"... and {len(results['failed']) - 10} more!\n"
    
    await status_message.edit_text(summary)
    
    # Clear queue
    bulk_upload_queue[user_id] = []


async def auto_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Automatically upload characters from forwarded messages.
    Supports bulk uploads (up to 100 at once).
    Only works for the specified user ID.
    """
    # Check if message is from authorized user
    if update.effective_user.id != AUTO_UPLOAD_USER_ID:
        return
    
    message = update.message
    
    # Check if message has photo or video
    if not (message.photo or message.video or message.document):
        return
    
    # Check if message has caption
    if not message.caption:
        return
    
    # Parse caption
    parsed = parse_caption(message.caption)
    if not parsed:
        await message.reply_text(
            "❌ Could not parse caption.\n\n"
            "Expected format:\n"
            "04: Character Name [emoji]\n"
            "Anime Name\n"
            "🎄 𝙍𝘼𝙍𝙄𝙏𝙔: Christmas"
        )
        return
    
    character_name, anime_name, rarity = parsed
    
    # Determine file type and download
    is_video_file = False
    if message.photo:
        file = await message.photo[-1].get_file()
        filename = f"char_{update.effective_user.id}_{message.message_id}.jpg"
    elif message.video:
        file = await message.video.get_file()
        filename = f"char_{update.effective_user.id}_{message.message_id}.mp4"
        is_video_file = True
    else:  # document
        file = await message.document.get_file()
        filename = message.document.file_name or f"char_{update.effective_user.id}_{message.message_id}"
        if message.document.mime_type and 'video' in message.document.mime_type:
            is_video_file = True
    
    # Download file
    try:
        file_bytes = await file.download_as_bytearray()
    except Exception as e:
        await message.reply_text(f"❌ Failed to download file: {str(e)}")
        return
    
    # Initialize queue if not exists
    user_id = update.effective_user.id
    if user_id not in bulk_upload_queue:
        bulk_upload_queue[user_id] = []
    
    # Add to queue
    bulk_upload_queue[user_id].append({
        'file_data': bytes(file_bytes),
        'filename': filename,
        'character_name': character_name,
        'anime_name': anime_name,
        'rarity': rarity,
        'is_video': is_video_file,
        'user_name': update.effective_user.first_name
    })
    
    queue_size = len(bulk_upload_queue[user_id])
    
    # Send status message
    if queue_size == 1:
        status_msg = await message.reply_text(
            f"📥 BULK UPLOAD MODE ACTIVATED!\n\n"
            f"📦 Characters in queue: {queue_size}\n"
            f"⏳ Send more characters or wait 5 seconds to start upload...\n\n"
            f"✅ Last added: {character_name}\n"
            f"📺 Anime: {anime_name}\n"
            f"⭐ Rarity: {rarity}\n\n"
            f"💡 You can upload up to {MAX_BULK_UPLOAD} characters at once!"
        )
        
        # Start processor
        asyncio.create_task(bulk_upload_processor(user_id, context, status_msg))
    else:
        # Update existing status
        try:
            # Find the last status message (stored in context)
            if hasattr(context, 'bot_data') and f'bulk_status_{user_id}' in context.bot_data:
                status_msg = context.bot_data[f'bulk_status_{user_id}']
                await status_msg.edit_text(
                    f"📥 BULK UPLOAD MODE\n\n"
                    f"📦 Characters in queue: {queue_size}/{MAX_BULK_UPLOAD}\n"
                    f"⏳ Collecting more... (5 sec wait)\n\n"
                    f"✅ Last added: {character_name}\n"
                    f"📺 Anime: {anime_name}\n"
                    f"⭐ Rarity: {rarity}"
                )
            else:
                await message.reply_text(
                    f"✅ Added to queue! ({queue_size}/{MAX_BULK_UPLOAD})\n"
                    f"{character_name} - {anime_name}"
                )
        except Exception:
            pass


# Register handler
# This handler will trigger on ALL photo/video messages from the specified user
application.add_handler(
    MessageHandler(
        filters.User(AUTO_UPLOAD_USER_ID) & 
        (filters.PHOTO | filters.VIDEO | filters.Document.ALL) &
        filters.CaptionRegex(r'.+'),  # Must have caption
        auto_upload_handler,
        block=False
    )
)

print(f"✅ Auto-upload module (BULK MODE) loaded for user ID: {AUTO_UPLOAD_USER_ID}")
print(f"📦 Maximum bulk upload: {MAX_BULK_UPLOAD} characters")