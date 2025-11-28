from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
import requests
import os
import tempfile
from shivu import application

CATBOX_API = "https://catbox.moe/user/api.php"
LITTERBOX_API = "https://litterbox.catbox.moe/resources/internals/api.php"

async def telegraph_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message

    if not message.reply_to_message:
        await message.reply_text("Reply to a message with /telegraph to upload it")
        return

    reply_msg = message.reply_to_message
    status_message = await message.reply_text("Processing...")

    file_id = None
    file_ext = "bin"
    
    if reply_msg.photo:
        file_id = reply_msg.photo[-1].file_id
        file_ext = "jpg"
    elif reply_msg.video:
        file_id = reply_msg.video.file_id
        file_ext = "mp4"
    elif reply_msg.animation:
        file_id = reply_msg.animation.file_id
        file_ext = "gif"
    elif reply_msg.document:
        file_id = reply_msg.document.file_id
        file_name = reply_msg.document.file_name
        file_ext = file_name.split('.')[-1] if '.' in file_name else "bin"
    elif reply_msg.sticker:
        file_id = reply_msg.sticker.file_id
        file_ext = "webp"
    elif reply_msg.audio:
        file_id = reply_msg.audio.file_id
        file_ext = "mp3"
    else:
        await status_message.edit_text("Unsupported media type")
        return

    temp_path = None
    try:
        file = await context.bot.get_file(file_id)
        temp_path = tempfile.mktemp(suffix=f".{file_ext}")
        await file.download_to_drive(temp_path)

        with open(temp_path, "rb") as f:
            files = {"fileToUpload": f}
            data = {"reqtype": "fileupload"}
            response = requests.post(CATBOX_API, data=data, files=files, timeout=60)

        if response.ok:
            url = response.text.strip()
            if url.startswith("http"):
                file_size = os.path.getsize(temp_path)
                size_mb = file_size / (1024 * 1024)
                await status_message.edit_text(
                    f"Successfully uploaded\n\n"
                    f"Size: {size_mb:.2f} MB\n"
                    f"Link: {url}"
                )
            else:
                await status_message.edit_text(f"Upload failed: {url}")
        else:
            await status_message.edit_text(f"Upload failed with status {response.status_code}")

    except requests.Timeout:
        await status_message.edit_text("Upload timeout, file too large")
    except Exception as e:
        await status_message.edit_text(f"Error: {str(e)}")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

application.add_handler(CommandHandler("tgm", telegraph_command))