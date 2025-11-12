
# test 

import io
from typing import Optional, Tuple

import aiohttp
from pymongo import ReturnDocument
from telegram import Update, InputFile
from telegram.ext import CommandHandler, ContextTypes

from shivu import application, collection, db, CHARA_CHANNEL_ID, SUPPORT_CHAT, sudo_users

WRONG_FORMAT_TEXT = """Wrong ❌️ format...  
Example: `/upload Img_url muzan-kibutsuji Demon-slayer 3`

Format: img_url/video_url character-name anime-name rarity-number

**Note:** Supports both images and videos/MP4 files!

Use rarity number accordingly:
1. 🟢 Common | 2. 🟣 Rare | 3. 🟡 Legendary | 4. 💮 Special Edition
5. 💫 Neon | 6. ✨ Manga | 7. 🎭 Cosplay | 8. 🎐 Celestial
9. 🔮 Premium Edition | 10. 💋 Erotic | 11. 🌤 Summer | 12. ☃️ Winter
13. ☔️ Monsoon | 14. 💝 Valentine | 15. 🎃 Halloween | 16. 🎄 Christmas
17. 🏵 Mythic | 18. 🎗 Special Events | 19. 🎥 AMV | 20. 👼 Tiny
"""

REPLY_UPLOAD_TEXT = """Reply to a photo/video with:
`/upload character-name anime-name rarity-number`

Example: `/upload muzan-kibutsuji Demon-slayer 3`

**Supports:** Photos, Videos, MP4 files, and Documents!
"""

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

VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv'}


async def get_next_sequence_number(sequence_name: str) -> int:
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


async def download_file(url: str) -> Optional[bytes]:
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept': '*/*',
            'Referer': url
        }
        timeout = aiohttp.ClientTimeout(total=300)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, timeout=timeout, allow_redirects=True) as response:
                if response.status == 200:
                    chunks = []
                    async for chunk in response.content.iter_chunked(1024 * 32):
                        if not chunk:
                            break
                        chunks.append(chunk)
                    return b"".join(chunks)
                return None
    except Exception as e:
        print(f"Download error for {url}: {e}")
        return None


async def upload_to_catbox(file_bytes: bytes, filename: str) -> Optional[str]:
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


def is_video(url_or_filename: str) -> bool:
    if not url_or_filename:
        return False
    return any(url_or_filename.lower().endswith(ext) for ext in VIDEO_EXTENSIONS)


def parse_rarity(rarity_str: str) -> Optional[str]:
    try:
        rarity_num = int(rarity_str)
        return RARITY_MAP.get(rarity_num)
    except (KeyError, ValueError):
        return None


def format_name(name: str) -> str:
    return name.replace('-', ' ').title()


async def create_character_entry(
    media_url: str,
    character_name: str,
    anime: str,
    rarity: str,
    user_id: str,
    user_name: str,
    context: ContextTypes.DEFAULT_TYPE,
    is_video_file: bool = False,
    file_bytes: Optional[bytes] = None
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
        if file_bytes:
            fp = io.BytesIO(file_bytes)
            if is_video_file:
                fp.name = "upload.mp4"
                message = await context.bot.send_video(
                    chat_id=CHARA_CHANNEL_ID,
                    video=InputFile(fp),
                    caption=caption,
                    parse_mode='HTML',
                    supports_streaming=True,
                    read_timeout=300,
                    write_timeout=300
                )
                character['file_id'] = message.video.file_id
                character['file_unique_id'] = message.video.file_unique_id
            else:
                fp.name = "upload.jpg"
                message = await context.bot.send_photo(
                    chat_id=CHARA_CHANNEL_ID,
                    photo=InputFile(fp),
                    caption=caption,
                    parse_mode='HTML',
                    read_timeout=180,
                    write_timeout=180
                )
                character['file_id'] = message.photo[-1].file_id
                character['file_unique_id'] = message.photo[-1].file_unique_id
        else:
            if is_video_file:
                try:
                    message = await context.bot.send_video(
                        chat_id=CHARA_CHANNEL_ID,
                        video=media_url,
                        caption=caption,
                        parse_mode='HTML',
                        supports_streaming=True,
                        read_timeout=300,
                        write_timeout=300,
                        connect_timeout=60,
                        pool_timeout=60
                    )
                    character['file_id'] = message.video.file_id
                    character['file_unique_id'] = message.video.file_unique_id
                except Exception:
                    message = await context.bot.send_document(
                        chat_id=CHARA_CHANNEL_ID,
                        document=media_url,
                        caption=caption,
                        parse_mode='HTML'
                    )
                    character['file_id'] = message.document.file_id
                    character['file_unique_id'] = message.document.file_unique_id
            else:
                try:
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
                except Exception:
                    message = await context.bot.send_document(
                        chat_id=CHARA_CHANNEL_ID,
                        document=media_url,
                        caption=caption,
                        parse_mode='HTML'
                    )
                    character['file_id'] = message.document.file_id
                    character['file_unique_id'] = message.document.file_unique_id
        character['message_id'] = message.message_id
        await collection.insert_one(character)
        return True, (
            f'✅ Character added successfully!\n'
            f'🆔 ID: {char_id}\n'
            f'📁 Type: {media_type}'
        )
    except Exception as e:
        await collection.insert_one(character)
        return False, (
            f"⚠️ Character added to database but channel upload failed.\n\n"
            f"🆔 ID: {char_id}\n"
            f"❌ Error: {str(e)}\n\n"
            f"💡 Try updating: `/update {char_id} img_url <new_url>`"
        )


async def handle_reply_upload(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    reply_msg = update.message.reply_to_message
    if not (reply_msg.photo or reply_msg.video or reply_msg.document):
        await update.message.reply_text('❌ Please reply to a photo, video, or document!')
        return
    if len(context.args) != 3:
        await update.message.reply_text(REPLY_UPLOAD_TEXT)
        return
    processing_msg = await update.message.reply_text('⏳ Downloading file...')
    is_video_file = False
    if reply_msg.photo:
        file = await reply_msg.photo[-1].get_file()
        filename = f"char_{update.effective_user.id}.jpg"
    elif reply_msg.video:
        file = await reply_msg.video.get_file()
        filename = f"char_{update.effective_user.id}.mp4"
        is_video_file = True
    else:
        file = await reply_msg.document.get_file()
        filename = reply_msg.document.file_name or f"char_{update.effective_user.id}"
        if reply_msg.document.mime_type and 'video' in reply_msg.document.mime_type:
            is_video_file = True
    file_bytes = await file.download_as_bytearray()
    await processing_msg.edit_text('⏳ Uploading to Catbox... (This may take a while for videos)')
    media_url = await upload_to_catbox(bytes(file_bytes), filename)
    if not media_url:
        await processing_msg.edit_text('❌ Failed to upload to Catbox. Please try again.')
        return
    await processing_msg.edit_text(
        f'✅ Uploaded to Catbox!\n🔗 {media_url}\n\n⏳ Adding to database...'
    )
    character_name = format_name(context.args[0])
    anime = format_name(context.args[1])
    rarity = parse_rarity(context.args[2])
    if not rarity:
        await processing_msg.edit_text('❌ Invalid rarity number. Check format guide.')
        return
    success, message = await create_character_entry(
        media_url,
        character_name,
        anime,
        rarity,
        str(update.effective_user.id),
        update.effective_user.first_name,
        context,
        is_video_file,
        file_bytes=bytes(file_bytes)
    )
    await processing_msg.edit_text(message)


async def handle_url_upload(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    if len(context.args) != 4:
        await update.message.reply_text(WRONG_FORMAT_TEXT)
        return
    media_url = context.args[0]
    processing_msg = await update.message.reply_text('⏳ Downloading from URL... (This may take a while)')
    file_bytes = await download_file(media_url)
    if not file_bytes:
        await processing_msg.edit_text('❌ Failed to download file from URL. Check if URL is accessible.')
        return
    is_video_file = is_video(media_url)
    filename = media_url.split('/')[-1] or ('video.mp4' if is_video_file else 'image.jpg')
    await processing_msg.edit_text('⏳ Uploading to Catbox... (This may take a while for large files)')
    new_url = await upload_to_catbox(file_bytes, filename)
    if not new_url:
        await processing_msg.edit_text('❌ Failed to upload to Catbox. File might be too large or invalid.')
        return
    await processing_msg.edit_text('✅ Uploaded to Catbox!\n⏳ Adding to database and channel...')
    character_name = format_name(context.args[1])
    anime = format_name(context.args[2])
    rarity = parse_rarity(context.args[3])
    if not rarity:
        await processing_msg.edit_text('❌ Invalid rarity number. Check format guide.')
        return
    success, message = await create_character_entry(
        new_url,
        character_name,
        anime,
        rarity,
        str(update.effective_user.id),
        update.effective_user.first_name,
        context,
        is_video_file,
        file_bytes=file_bytes
    )
    await processing_msg.edit_text(message)


async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    if user_id not in sudo_users:
        await update.message.reply_text('❌ You need sudo access to use this command.')
        return
    try:
        if update.message.reply_to_message:
            await handle_reply_upload(update, context)
        else:
            await handle_url_upload(update, context)
    except Exception as e:
        error_msg = (
            f'❌ Character upload failed.\n\n'
            f'Error: {str(e)}\n\n'
            f'Contact: {SUPPORT_CHAT}'
        )
        await update.message.reply_text(error_msg)


async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    if user_id not in sudo_users:
        await update.message.reply_text('❌ You need sudo access to use this command.')
        return
    if len(context.args) != 1:
        await update.message.reply_text('❌ Incorrect format.\n\nUse: `/delete ID`')
        return
    character = await collection.find_one_and_delete({'id': context.args[0]})
    if not character:
        await update.message.reply_text('❌ Character not found in database.')
        return
    try:
        await context.bot.delete_message(
            chat_id=CHARA_CHANNEL_ID,
            message_id=character['message_id']
        )
    except Exception:
        pass
    await update.message.reply_text('✅ Character deleted successfully.')


async def update_character(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    if user_id not in sudo_users:
        await update.message.reply_text('❌ You need sudo access to use this command.')
        return
    if len(context.args) != 3:
        await update.message.reply_text(
            '❌ Incorrect format.\n\n'
            'Use: `/update id field new_value`\n\n'
            'Valid fields: img_url, name, anime, rarity'
        )
        return
    char_id, field, new_value = context.args
    character = await collection.find_one({'id': char_id})
    if not character:
        await update.message.reply_text('❌ Character not found.')
        return
    valid_fields = ['img_url', 'name', 'anime', 'rarity']
    if field not in valid_fields:
        await update.message.reply_text(
            f'❌ Invalid field.\n\nChoose from: {", ".join(valid_fields)}'
        )
        return
    processing_msg = None
    if field in ['name', 'anime']:
        new_value = format_name(new_value)
    elif field == 'rarity':
        new_value = parse_rarity(new_value)
        if not new_value:
            await update.message.reply_text('❌ Invalid rarity number.')
            return
    elif field == 'img_url':
        processing_msg = await update.message.reply_text('⏳ Processing new media...')
        file_bytes = await download_file(new_value)
        if not file_bytes:
            await processing_msg.edit_text('❌ Failed to download file from URL.')
            return
        is_video_file = is_video(new_value)
        filename = new_value.split('/')[-1] or ('video.mp4' if is_video_file else 'image.jpg')
        await processing_msg.edit_text('⏳ Uploading to Catbox...')
        new_url = await upload_to_catbox(file_bytes, filename)
        if not new_url:
            await processing_msg.edit_text('❌ Failed to upload to Catbox.')
            return
        new_value = new_url
        await processing_msg.edit_text('✅ Re-uploaded to Catbox!')
    update_data = {field: new_value}
    if field == 'img_url':
        update_data['is_video'] = is_video(new_value)
    await collection.find_one_and_update(
        {'id': char_id},
        {'$set': update_data}
    )
    character = await collection.find_one({'id': char_id})
    is_video_file = character.get('is_video', False)
    media_type = "🎥 Video" if is_video_file else "🖼 Image"
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
            if is_video_file:
                message = await context.bot.send_video(
                    chat_id=CHARA_CHANNEL_ID,
                    video=new_value,
                    caption=caption,
                    parse_mode='HTML',
                    supports_streaming=True,
                    read_timeout=300,
                    write_timeout=300
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
        success_msg = '✅ Character updated successfully.'
        if processing_msg:
            await processing_msg.edit_text(success_msg)
        else:
            await update.message.reply_text(success_msg)
    except Exception as e:
        error_msg = f'⚠️ Database updated but channel update failed.\n\nError: {str(e)}'
        if processing_msg:
            await processing_msg.edit_text(error_msg)
        else:
            await update.message.reply_text(error_msg)


application.add_handler(CommandHandler('upload', upload, block=False))
application.add_handler(CommandHandler('delete', delete, block=False))
application.add_handler(CommandHandler('update', update_character, block=False))
