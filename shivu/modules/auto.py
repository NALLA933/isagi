"""
Auto Upload Module - Automatically uploads characters from forwarded messages
Specifically for user ID: 5147822244
"""

import io
import re
from typing import Optional, Tuple

import aiohttp
from pymongo import ReturnDocument
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from shivu import application, collection, db, CHARA_CHANNEL_ID


# Configuration
AUTO_UPLOAD_USER_ID = 5147822244  # Your Telegram user ID

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


async def auto_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Automatically upload characters from forwarded messages.
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
    
    # Send processing message
    processing_msg = await message.reply_text(
        f"🔄 Auto-uploading...\n\n"
        f"📝 Character: {character_name}\n"
        f"📺 Anime: {anime_name}\n"
        f"⭐ Rarity: {rarity}"
    )
    
    try:
        # Determine file type and download
        is_video_file = False
        if message.photo:
            file = await message.photo[-1].get_file()
            filename = f"char_auto_{update.effective_user.id}.jpg"
        elif message.video:
            file = await message.video.get_file()
            filename = f"char_auto_{update.effective_user.id}.mp4"
            is_video_file = True
        else:  # document
            file = await message.document.get_file()
            filename = message.document.file_name or f"char_auto_{update.effective_user.id}"
            if message.document.mime_type and 'video' in message.document.mime_type:
                is_video_file = True
        
        await processing_msg.edit_text(
            f"🔄 Auto-uploading...\n\n"
            f"📝 Character: {character_name}\n"
            f"📺 Anime: {anime_name}\n"
            f"⭐ Rarity: {rarity}\n\n"
            f"⏳ Downloading file..."
        )
        
        # Download file
        file_bytes = await file.download_as_bytearray()
        
        await processing_msg.edit_text(
            f"🔄 Auto-uploading...\n\n"
            f"📝 Character: {character_name}\n"
            f"📺 Anime: {anime_name}\n"
            f"⭐ Rarity: {rarity}\n\n"
            f"⏳ Uploading to Catbox... (This may take a while)"
        )
        
        # Upload to Catbox
        media_url = await upload_to_catbox(io.BytesIO(file_bytes), filename)
        
        if not media_url:
            await processing_msg.edit_text(
                f"❌ Auto-upload failed!\n\n"
                f"Failed to upload to Catbox. Please try again."
            )
            return
        
        await processing_msg.edit_text(
            f"🔄 Auto-uploading...\n\n"
            f"📝 Character: {character_name}\n"
            f"📺 Anime: {anime_name}\n"
            f"⭐ Rarity: {rarity}\n\n"
            f"✅ Uploaded to Catbox!\n"
            f"⏳ Adding to database..."
        )
        
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
            f'𝑴𝒂𝒅𝒆 𝑩𝒚 ➥ <a href="tg://user?id={update.effective_user.id}">{update.effective_user.first_name}</a>'
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
        
        await processing_msg.edit_text(
            f"✅ AUTO-UPLOAD SUCCESSFUL!\n\n"
            f"🆔 ID: {char_id}\n"
            f"📝 Character: {character_name}\n"
            f"📺 Anime: {anime_name}\n"
            f"⭐ Rarity: {rarity}\n"
            f"📁 Type: {media_type}\n\n"
            f"🔗 URL: {media_url}"
        )
        
    except Exception as e:
        await processing_msg.edit_text(
            f"❌ AUTO-UPLOAD FAILED!\n\n"
            f"Error: {str(e)}\n\n"
            f"Please try manual upload with /upload command."
        )


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

print(f"✅ Auto-upload module loaded for user ID: {AUTO_UPLOAD_USER_ID}")