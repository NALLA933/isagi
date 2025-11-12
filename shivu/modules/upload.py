import io
import logging
import asyncio
from typing import Optional, Tuple
from urllib.parse import urlparse
from collections import defaultdict
import time

import aiohttp
from pymongo import ReturnDocument
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from shivu import application, collection, db, CHARA_CHANNEL_ID, SUPPORT_CHAT, sudo_users

logger = logging.getLogger(__name__)

RARITY_MAP = {
    1: "🟢 Common", 2: "🟣 Rare", 3: "🟡 Legendary", 4: "💮 Special Edition",
    5: "💫 Neon", 6: "✨ Manga", 7: "🎭 Cosplay", 8: "🎐 Celestial",
    9: "🔮 Premium Edition", 10: "💋 Erotic", 11: "🌤 Summer", 12: "☃️ Winter",
    13: "☔️ Monsoon", 14: "💝 Valentine", 15: "🎃 Halloween", 16: "🎄 Christmas",
    17: "🏵 Mythic", 18: "🎗 Special Events", 19: "🎥 AMV", 20: "👼 Tiny"
}

VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv'}
MAX_FILE_SIZE = 50 * 1024 * 1024
UPLOAD_TIMEOUT = 300

class RateLimiter:
    def __init__(self, max_requests: int, time_window: int):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = defaultdict(list)
    
    def is_allowed(self, user_id: str) -> bool:
        now = time.time()
        user_requests = self.requests[user_id]
        user_requests = [req_time for req_time in user_requests if now - req_time < self.time_window]
        self.requests[user_id] = user_requests
        
        if len(user_requests) >= self.max_requests:
            return False
            
        user_requests.append(now)
        return True

upload_limiter = RateLimiter(max_requests=5, time_window=300)

async def get_next_sequence_number(sequence_name: str) -> int:
    sequence_collection = db.sequences
    try:
        sequence_document = await sequence_collection.find_one_and_update(
            {'_id': sequence_name},
            {'$inc': {'sequence_value': 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        return sequence_document['sequence_value']
    except Exception as e:
        logger.error(f"Sequence error: {e}")
        sequence_document = await sequence_collection.find_one({'_id': sequence_name})
        if sequence_document:
            return sequence_document['sequence_value']
        await sequence_collection.insert_one({'_id': sequence_name, 'sequence_value': 0})
        return 0

async def download_file(url: str) -> Optional[bytes]:
    try:
        timeout = aiohttp.ClientTimeout(total=UPLOAD_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.head(url) as response:
                content_length = int(response.headers.get('content-length', 0))
                if content_length > MAX_FILE_SIZE:
                    return None
            
            async with session.get(url) as response:
                if response.status == 200:
                    chunk_size = 8192
                    total_bytes = 0
                    chunks = []
                    
                    async for chunk in response.content.iter_chunked(chunk_size):
                        total_bytes += len(chunk)
                        if total_bytes > MAX_FILE_SIZE:
                            return None
                        chunks.append(chunk)
                    
                    return b''.join(chunks)
                return None
    except Exception as e:
        logger.error(f"Download error for {url}: {e}")
        return None

async def upload_to_catbox(file_bytes: bytes, filename: str) -> Optional[str]:
    try:
        timeout = aiohttp.ClientTimeout(total=UPLOAD_TIMEOUT)
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
        logger.error(f"Catbox upload error: {e}")
        return None

def is_video_file(url_or_filename: str) -> bool:
    if not url_or_filename:
        return False
    parsed = urlparse(url_or_filename)
    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in VIDEO_EXTENSIONS)

def validate_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False

def parse_rarity(rarity_str: str) -> Optional[str]:
    try:
        rarity_num = int(rarity_str)
        return RARITY_MAP.get(rarity_num)
    except (ValueError, TypeError):
        return None

def format_name(name: str) -> str:
    return name.replace('-', ' ').title()

def validate_character_input(character_name: str, anime: str, rarity: str) -> bool:
    if not character_name or len(character_name) > 100:
        return False
    if not anime or len(anime) > 100:
        return False
    if not parse_rarity(rarity):
        return False
    return True

async def create_character_entry(
    media_url: str,
    character_name: str,
    anime: str,
    rarity: str,
    user_id: str,
    user_name: str,
    context: ContextTypes.DEFAULT_TYPE,
    is_video_file: bool = False
) -> Tuple[bool, str]:
    char_id = str(await get_next_sequence_number('character_id')).zfill(2)

    character = {
        'img_url': media_url,
        'id': char_id,
        'name': character_name,
        'anime': anime,
        'rarity': rarity,
        'is_video': is_video_file
    }

    media_type = "🎥 Video" if is_video_file else "🖼 Image"
    caption = (
        f'<b>{char_id}:</b> {character_name}\n'
        f'<b>{anime}</b>\n'
        f'<b>{rarity[0]} 𝙍𝘼𝙍𝙄𝙏𝙔:</b> {rarity[2:]}\n'
        f'<b>Type:</b> {media_type}\n\n'
        f'𝑴𝒂𝒅𝒆 𝑩𝒚 ➥ <a href="tg://user?id={user_id}">{user_name}</a>'
    )

    try:
        if is_video_file:
            message = await context.bot.send_video(
                chat_id=CHARA_CHANNEL_ID,
                video=media_url,
                caption=caption,
                parse_mode='HTML',
                supports_streaming=True,
                read_timeout=UPLOAD_TIMEOUT,
                write_timeout=UPLOAD_TIMEOUT,
                connect_timeout=60,
                pool_timeout=60
            )
            character['file_id'] = message.video.file_id
            character['file_unique_id'] = message.video.file_unique_id
        else:
            message = await context.bot.send_photo(
                chat_id=CHARA_CHANNEL_ID,
                photo=media_url,
                caption=caption,
                parse_mode='HTML',
                read_timeout=180,
                write_timeout=180
            )
            character['file_id'] = message.photo[-1].file_id
            character['file_unique_id'] = message.photo[-1].file_unique_id

        character['message_id'] = message.message_id
        await collection.insert_one(character)

        return True, f'✅ Character added successfully!\n🆔 ID: {char_id}\n📁 Type: {media_type}'
        
    except Exception as e:
        logger.error(f"Failed to create character in channel: {e}")
        try:
            await collection.insert_one(character)
            return False, f"⚠️ Added to DB but channel upload failed.\n🆔 ID: {char_id}\n❌ Error: {str(e)}"
        except Exception as db_error:
            logger.error(f"Database insert failed: {db_error}")
            return False, f"❌ Complete failure: {str(db_error)}"

async def handle_reply_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_msg = update.message.reply_to_message

    if not (reply_msg.photo or reply_msg.video or reply_msg.document):
        await update.message.reply_text('❌ Reply to a photo, video, or document!')
        return

    if len(context.args) != 3:
        await update.message.reply_text('Reply with: `/upload character-name anime-name rarity-number`')
        return

    user_id = str(update.effective_user.id)
    if not upload_limiter.is_allowed(user_id):
        await update.message.reply_text('❌ Rate limit exceeded. Try again later.')
        return

    processing_msg = await update.message.reply_text('⏳ Downloading file...')

    try:
        if reply_msg.photo:
            file = await reply_msg.photo[-1].get_file()
            filename = f"char_{user_id}.jpg"
            is_video_file = False
        elif reply_msg.video:
            file = await reply_msg.video.get_file()
            filename = f"char_{user_id}.mp4"
            is_video_file = True
        else:
            file = await reply_msg.document.get_file()
            filename = reply_msg.document.file_name or f"char_{user_id}"
            is_video_file = bool(reply_msg.document.mime_type and 'video' in reply_msg.document.mime_type)

        file_bytes = await file.download_as_bytearray()
        if len(file_bytes) > MAX_FILE_SIZE:
            await processing_msg.edit_text('❌ File too large. Max 50MB.')
            return

        await processing_msg.edit_text('⏳ Uploading to Catbox...')
        media_url = await upload_to_catbox(io.BytesIO(file_bytes), filename)

        if not media_url:
            await processing_msg.edit_text('❌ Catbox upload failed.')
            return

        await processing_msg.edit_text('✅ Uploaded! Adding to database...')

        character_name = format_name(context.args[0])
        anime = format_name(context.args[1])
        rarity = parse_rarity(context.args[2])

        if not validate_character_input(character_name, anime, context.args[2]):
            await processing_msg.edit_text('❌ Invalid input. Check name length and rarity.')
            return

        success, message = await create_character_entry(
            media_url, character_name, anime, rarity, 
            user_id, update.effective_user.first_name, context, is_video_file
        )
        await processing_msg.edit_text(message)

    except Exception as e:
        logger.error(f"Reply upload error: {e}")
        await processing_msg.edit_text(f'❌ Upload failed: {str(e)}')

async def handle_url_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 4:
        await update.message.reply_text('Format: img_url character-name anime-name rarity-number')
        return

    user_id = str(update.effective_user.id)
    if not upload_limiter.is_allowed(user_id):
        await update.message.reply_text('❌ Rate limit exceeded. Try again later.')
        return

    media_url = context.args[0]
    if not validate_url(media_url):
        await update.message.reply_text('❌ Invalid URL.')
        return

    processing_msg = await update.message.reply_text('⏳ Downloading from URL...')

    try:
        file_bytes = await download_file(media_url)
        if not file_bytes:
            await processing_msg.edit_text('❌ Download failed.')
            return

        is_video_file = is_video_file(media_url)
        filename = media_url.split('/')[-1] or ('video.mp4' if is_video_file else 'image.jpg')

        await processing_msg.edit_text('⏳ Uploading to Catbox...')
        new_url = await upload_to_catbox(io.BytesIO(file_bytes), filename)

        if not new_url:
            await processing_msg.edit_text('❌ Catbox upload failed.')
            return

        await processing_msg.edit_text('✅ Uploaded! Adding to database...')

        character_name = format_name(context.args[1])
        anime = format_name(context.args[2])
        rarity = parse_rarity(context.args[3])

        if not validate_character_input(character_name, anime, context.args[3]):
            await processing_msg.edit_text('❌ Invalid input.')
            return

        success, message = await create_character_entry(
            new_url, character_name, anime, rarity,
            user_id, update.effective_user.first_name, context, is_video_file
        )
        await processing_msg.edit_text(message)

    except Exception as e:
        logger.error(f"URL upload error: {e}")
        await processing_msg.edit_text(f'❌ Upload failed: {str(e)}')

async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    
    if user_id not in sudo_users:
        await update.message.reply_text('❌ Sudo access required.')
        return

    try:
        if update.message.reply_to_message:
            await handle_reply_upload(update, context)
        else:
            await handle_url_upload(update, context)
    except Exception as e:
        logger.error(f"Upload command error: {e}")
        await update.message.reply_text(f'❌ Command failed: {str(e)}')

async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    
    if user_id not in sudo_users:
        await update.message.reply_text('❌ Sudo access required.')
        return

    if len(context.args) != 1:
        await update.message.reply_text('Use: `/delete ID`')
        return

    try:
        character = await collection.find_one_and_delete({'id': context.args[0]})
        if not character:
            await update.message.reply_text('❌ Character not found.')
            return

        try:
            await context.bot.delete_message(
                chat_id=CHARA_CHANNEL_ID,
                message_id=character['message_id']
            )
        except Exception:
            pass

        await update.message.reply_text('✅ Character deleted.')
        
    except Exception as e:
        logger.error(f"Delete error: {e}")
        await update.message.reply_text(f'❌ Delete failed: {str(e)}')

async def update_character(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    
    if user_id not in sudo_users:
        await update.message.reply_text('❌ Sudo access required.')
        return

    if len(context.args) != 3:
        await update.message.reply_text('Use: `/update id field new_value`')
        return

    char_id, field, new_value = context.args
    valid_fields = ['img_url', 'name', 'anime', 'rarity']
    
    if field not in valid_fields:
        await update.message.reply_text(f'❌ Invalid field. Use: {", ".join(valid_fields)}')
        return

    try:
        character = await collection.find_one({'id': char_id})
        if not character:
            await update.message.reply_text('❌ Character not found.')
            return

        processing_msg = None

        if field in ['name', 'anime']:
            new_value = format_name(new_value)
        elif field == 'rarity':
            parsed_rarity = parse_rarity(new_value)
            if not parsed_rarity:
                await update.message.reply_text('❌ Invalid rarity.')
                return
            new_value = parsed_rarity
        elif field == 'img_url':
            if not validate_url(new_value):
                await update.message.reply_text('❌ Invalid URL.')
                return

            processing_msg = await update.message.reply_text('⏳ Processing new media...')
            file_bytes = await download_file(new_value)
            if not file_bytes:
                await processing_msg.edit_text('❌ Download failed.')
                return

            is_video_file = is_video_file(new_value)
            filename = new_value.split('/')[-1] or ('video.mp4' if is_video_file else 'image.jpg')

            await processing_msg.edit_text('⏳ Uploading to Catbox...')
            new_url = await upload_to_catbox(io.BytesIO(file_bytes), filename)

            if not new_url:
                await processing_msg.edit_text('❌ Catbox upload failed.')
                return

            new_value = new_url
            await processing_msg.edit_text('✅ Re-uploaded!')

        update_data = {field: new_value}
        if field == 'img_url':
            update_data['is_video'] = is_video_file(new_value)

        await collection.find_one_and_update(
            {'id': char_id},
            {'$set': update_data}
        )

        character = await collection.find_one({'id': char_id})
        is_video_file_flag = character.get('is_video', False)
        media_type = "🎥 Video" if is_video_file_flag else "🖼 Image"

        caption = (
            f'<b>{character["id"]}:</b> {character["name"]}\n'
            f'<b>{character["anime"]}</b>\n'
            f'<b>{character["rarity"][0]} 𝙍𝘼𝙍𝙄𝙏𝙔:</b> {character["rarity"][2:]}\n'
            f'<b>Type:</b> {media_type}\n\n'
            f'𝑼𝒑𝒅𝒂𝒕𝒆𝒅 𝑩𝒚 ➥ <a href="tg://user?id={user_id}">{update.effective_user.first_name}</a>'
        )

        try:
            if field == 'img_url':
                await context.bot.delete_message(
                    chat_id=CHARA_CHANNEL_ID,
                    message_id=character['message_id']
                )

                if is_video_file_flag:
                    message = await context.bot.send_video(
                        chat_id=CHARA_CHANNEL_ID,
                        video=new_value,
                        caption=caption,
                        parse_mode='HTML',
                        supports_streaming=True,
                        read_timeout=UPLOAD_TIMEOUT,
                        write_timeout=UPLOAD_TIMEOUT
                    )
                    await collection.find_one_and_update(
                        {'id': char_id},
                        {'$set': {
                            'message_id': message.message_id,
                            'file_id': message.video.file_id,
                            'file_unique_id': message.video.file_unique_id
                        }}
                    )
                else:
                    message = await context.bot.send_photo(
                        chat_id=CHARA_CHANNEL_ID,
                        photo=new_value,
                        caption=caption,
                        parse_mode='HTML',
                        read_timeout=180,
                        write_timeout=180
                    )
                    await collection.find_one_and_update(
                        {'id': char_id},
                        {'$set': {
                            'message_id': message.message_id,
                            'file_id': message.photo[-1].file_id,
                            'file_unique_id': message.photo[-1].file_unique_id
                        }}
                    )
            else:
                await context.bot.edit_message_caption(
                    chat_id=CHARA_CHANNEL_ID,
                    message_id=character['message_id'],
                    caption=caption,
                    parse_mode='HTML'
                )

            success_msg = '✅ Character updated.'
            if processing_msg:
                await processing_msg.edit_text(success_msg)
            else:
                await update.message.reply_text(success_msg)
                
        except Exception as e:
            error_msg = f'⚠️ DB updated but channel failed: {str(e)}'
            if processing_msg:
                await processing_msg.edit_text(error_msg)
            else:
                await update.message.reply_text(error_msg)

    except Exception as e:
        logger.error(f"Update error: {e}")
        await update.message.reply_text(f'❌ Update failed: {str(e)}')

application.add_handler(CommandHandler('upload', upload, block=False))
application.add_handler(CommandHandler('delete', delete, block=False))
application.add_handler(CommandHandler('update', update_character, block=False))