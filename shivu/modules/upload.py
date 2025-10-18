import urllib.request
import io
import aiohttp
from pymongo import ReturnDocument
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from shivu.modules.database.sudo import is_user_sudo
from shivu import application, collection, db, CHARA_CHANNEL_ID, SUPPORT_CHAT, sudo_users


WRONG_FORMAT_TEXT = """Wrong ❌️ format...  
Example: `/upload Img_url muzan-kibutsuji Demon-slayer 3`

Format:  
img_url/video_url character-name anime-name rarity-number  

**Note:** Supports both images and videos/MP4 files!

Use rarity number accordingly:  
1. 🟢 Common 
2. 🟣 Rare
3. 🟡 Legendary 
4. 💮 Special Edition 
5. 💫 Neon 
6. ✨ Manga 
7. 🎭 Cosplay 
8. 🎐 Celestial 
9. 🔮 Premium Edition 
10. 💋 Erotic 
11. 🌤 Summer 
12. ☃️ Winter 
13. ☔️ Monsoon 
14. 💝 Valentine 
15. 🎃 Halloween 
16. 🎄 Christmas 
17. 🏵 Mythic
18. 🎗 Special Events
19. 🎥 AMV
20. 👼 Tiny
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


async def get_next_sequence_number(sequence_name):
    """Generate next sequential ID for characters"""
    sequence_collection = db.sequences
    sequence_document = await sequence_collection.find_one_and_update(
        {'_id': sequence_name},
        {'$inc': {'sequence_value': 1}},
        return_document=ReturnDocument.AFTER
    )
    if not sequence_document:
        await sequence_collection.insert_one({'_id': sequence_name, 'sequence_value': 0})
        return 0
    return sequence_document['sequence_value']


async def upload_to_catbox(file_bytes, filename):
    """Upload file to Catbox and return the URL"""
    url = "https://catbox.moe/user/api.php"

    try:
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field('reqtype', 'fileupload')
            data.add_field('fileToUpload', file_bytes, filename=filename)

            async with session.post(url, data=data) as response:
                if response.status == 200:
                    return (await response.text()).strip()
                return None
    except Exception as e:
        print(f"Catbox upload error: {e}")
        return None


def is_video_url(url):
    """Check if URL points to a video file"""
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv']
    return any(url.lower().endswith(ext) for ext in video_extensions)


async def create_character_entry(media_url, character_name, anime, rarity, user_id, user_name, context, is_new=True, is_video=False):
    """Create character entry in database and post to channel"""
    char_id = str(await get_next_sequence_number('character_id')).zfill(2)

    character = {
        'img_url': media_url,  # Store as img_url for backward compatibility
        'id': char_id,
        'name': character_name,
        'anime': anime,
        'rarity': rarity,
        'is_video': is_video  # Flag to identify video content
    }

    action_text = "𝑴𝒂𝒅𝒆" if is_new else "𝑼𝒑𝒅𝒂𝒕𝒆𝒅"
    media_type = "🎥 Video" if is_video else "🖼 Image"

    caption = (
        f'<b>{char_id}:</b> {character_name}\n'
        f'<b>{anime}</b>\n'
        f'<b>{rarity[0]} 𝙍𝘼𝙍𝙄𝙏𝙔:</b> {rarity[2:]}\n'
        f'<b>Type:</b> {media_type}\n\n'
        f'{action_text} 𝑩𝒚 ➥ <a href="tg://user?id={user_id}">{user_name}</a>'
    )

    try:
        # Send video or photo based on type
        if is_video:
            message = await context.bot.send_video(
                chat_id=CHARA_CHANNEL_ID,
                video=media_url,
                caption=caption,
                parse_mode='HTML'
            )
        else:
            message = await context.bot.send_photo(
                chat_id=CHARA_CHANNEL_ID,
                photo=media_url,
                caption=caption,
                parse_mode='HTML'
            )
        
        character['message_id'] = message.message_id
        await collection.insert_one(character)
        return True, f'✅ Character added successfully!\n🆔 ID: {char_id}\n📁 Type: {media_type}'
    except Exception as e:
        await collection.insert_one(character)
        return False, f"Character added to database but channel upload failed.\nError: {str(e)}"


def validate_url(url):
    """Validate if URL is accessible"""
    try:
        urllib.request.urlopen(url)
        return True
    except Exception:
        return False


def parse_rarity(rarity_str):
    """Parse and validate rarity number"""
    try:
        rarity_num = int(rarity_str)
        if rarity_num in RARITY_MAP:
            return RARITY_MAP[rarity_num]
        return None
    except (KeyError, ValueError):
        return None


async def upload(update: Update, context: CallbackContext) -> None:
    """Handle character uploads via URL or by replying to media"""
    if str(update.effective_user.id) not in sudo_users:
        await update.message.reply_text('❌ You need sudo access to use this command.')
        return

    try:
        # Handle reply to photo/video/document
        if update.message.reply_to_message:
            reply_msg = update.message.reply_to_message

            if not (reply_msg.photo or reply_msg.video or reply_msg.document):
                await update.message.reply_text('❌ Please reply to a photo, video, or document!')
                return

            args = context.args
            if len(args) != 3:
                await update.message.reply_text(REPLY_UPLOAD_TEXT)
                return

            processing_msg = await update.message.reply_text('⏳ Uploading to Catbox...')

            try:
                # Get file and determine type
                is_video = False
                
                if reply_msg.photo:
                    file = await reply_msg.photo[-1].get_file()
                    filename = f"char_{update.effective_user.id}.jpg"
                elif reply_msg.video:
                    file = await reply_msg.video.get_file()
                    filename = f"char_{update.effective_user.id}.mp4"
                    is_video = True
                else:  # Document
                    file = await reply_msg.document.get_file()
                    filename = reply_msg.document.file_name or f"char_{update.effective_user.id}"
                    # Check if document is a video
                    if reply_msg.document.mime_type and 'video' in reply_msg.document.mime_type:
                        is_video = True

                # Download and upload to Catbox
                file_bytes = await file.download_as_bytearray()
                media_url = await upload_to_catbox(io.BytesIO(file_bytes), filename)

                if not media_url:
                    await processing_msg.edit_text('❌ Failed to upload to Catbox. Please try again.')
                    return

                media_type = "video" if is_video else "image"
                await processing_msg.edit_text(f'✅ {media_type.title()} uploaded!\n🔗 {media_url}\n\n⏳ Adding to database...')

                character_name = args[0].replace('-', ' ').title()
                anime = args[1].replace('-', ' ').title()
                rarity = parse_rarity(args[2])

                if not rarity:
                    await processing_msg.edit_text('❌ Invalid rarity number. Check format guide.')
                    return

                success, message = await create_character_entry(
                    media_url, character_name, anime, rarity,
                    update.effective_user.id, update.effective_user.first_name,
                    context, is_video=is_video
                )

                await processing_msg.edit_text(message)

            except Exception as e:
                await processing_msg.edit_text(f'❌ Error: {str(e)}')
                return

        # Handle URL-based upload (supports both image and video URLs)
        else:
            args = context.args
            if len(args) != 4:
                await update.message.reply_text(WRONG_FORMAT_TEXT)
                return

            media_url = args[0]
            if not validate_url(media_url):
                await update.message.reply_text('❌ Invalid or inaccessible URL.')
                return

            # Detect if URL is for a video
            is_video = is_video_url(media_url)

            character_name = args[1].replace('-', ' ').title()
            anime = args[2].replace('-', ' ').title()
            rarity = parse_rarity(args[3])

            if not rarity:
                await update.message.reply_text('❌ Invalid rarity number. Check format guide.')
                return

            success, message = await create_character_entry(
                media_url, character_name, anime, rarity,
                update.effective_user.id, update.effective_user.first_name,
                context, is_video=is_video
            )

            await update.message.reply_text(message)

    except Exception as e:
        await update.message.reply_text(
            f'❌ Character upload failed.\n\n'
            f'Error: {str(e)}\n\n'
            f'Contact: {SUPPORT_CHAT}'
        )


async def delete(update: Update, context: CallbackContext) -> None:
    """Delete a character by ID"""
    if str(update.effective_user.id) not in sudo_users:
        await update.message.reply_text('❌ You need sudo access to use this command.')
        return

    try:
        args = context.args
        if len(args) != 1:
            await update.message.reply_text('❌ Incorrect format.\n\nUse: `/delete ID`')
            return

        character = await collection.find_one_and_delete({'id': args[0]})

        if not character:
            await update.message.reply_text('❌ Character not found in database.')
            return

        # Try to delete from channel
        try:
            await context.bot.delete_message(
                chat_id=CHARA_CHANNEL_ID, 
                message_id=character['message_id']
            )
        except Exception:
            pass  # Message might already be deleted

        await update.message.reply_text('✅ Character deleted successfully.')

    except Exception as e:
        await update.message.reply_text(f'❌ Error: {str(e)}')


async def update_character(update: Update, context: CallbackContext) -> None:
    """Update character fields"""
    if str(update.effective_user.id) not in sudo_users:
        await update.message.reply_text('❌ You need sudo access to use this command.')
        return

    try:
        args = context.args
        if len(args) != 3:
            await update.message.reply_text(
                '❌ Incorrect format.\n\n'
                'Use: `/update id field new_value`\n\n'
                'Valid fields: img_url, name, anime, rarity'
            )
            return

        char_id, field, new_value = args
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

        # Process field values
        if field in ['name', 'anime']:
            new_value = new_value.replace('-', ' ').title()
        elif field == 'rarity':
            new_value = parse_rarity(new_value)
            if not new_value:
                await update.message.reply_text('❌ Invalid rarity number.')
                return
        elif field == 'img_url':
            if not validate_url(new_value):
                await update.message.reply_text('❌ Invalid or inaccessible URL.')
                return

        # Update database
        update_data = {field: new_value}
        
        # If updating img_url, also update is_video flag
        if field == 'img_url':
            update_data['is_video'] = is_video_url(new_value)
        
        await collection.find_one_and_update({'id': char_id}, {'$set': update_data})
        character = await collection.find_one({'id': char_id})

        # Determine if current entry is video
        is_video = character.get('is_video', False)
        media_type = "🎥 Video" if is_video else "🖼 Image"

        # Update channel message
        caption = (
            f'<b>{character["id"]}:</b> {character["name"]}\n'
            f'<b>{character["anime"]}</b>\n'
            f'<b>{character["rarity"][0]} 𝙍𝘼𝙍𝙄𝙏𝙔:</b> {character["rarity"][2:]}\n'
            f'<b>Type:</b> {media_type}\n\n'
            f'𝑼𝒑𝒅𝒂𝒕𝒆𝒅 𝑩𝒚 ➥ <a href="tg://user?id={update.effective_user.id}">'
            f'{update.effective_user.first_name}</a>'
        )

        try:
            if field == 'img_url':
                # Delete old message and send new one
                await context.bot.delete_message(
                    chat_id=CHARA_CHANNEL_ID, 
                    message_id=character['message_id']
                )
                
                # Send video or photo based on new URL
                if is_video:
                    message = await context.bot.send_video(
                        chat_id=CHARA_CHANNEL_ID,
                        video=new_value,
                        caption=caption,
                        parse_mode='HTML'
                    )
                else:
                    message = await context.bot.send_photo(
                        chat_id=CHARA_CHANNEL_ID,
                        photo=new_value,
                        caption=caption,
                        parse_mode='HTML'
                    )
                
                await collection.find_one_and_update(
                    {'id': char_id}, 
                    {'$set': {'message_id': message.message_id}}
                )
            else:
                # Just update caption
                await context.bot.edit_message_caption(
                    chat_id=CHARA_CHANNEL_ID,
                    message_id=character['message_id'],
                    caption=caption,
                    parse_mode='HTML'
                )
        except Exception as e:
            await update.message.reply_text(
                f'⚠️ Database updated but channel message update failed.\n\nError: {str(e)}'
            )
            return

        await update.message.reply_text('✅ Character updated successfully.')

    except Exception as e:
        await update.message.reply_text(f'❌ Error: {str(e)}')


# Register handlers
application.add_handler(CommandHandler('upload', upload, block=False))
application.add_handler(CommandHandler('delete', delete, block=False))
application.add_handler(CommandHandler('update', update_character, block=False))