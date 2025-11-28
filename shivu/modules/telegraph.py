from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
import requests
import os
import tempfile
import asyncio
from concurrent.futures import ThreadPoolExecutor
from shivu import application
import time

CATBOX_API = "https://catbox.moe/user/api.php"
GOFILE_API = "https://store1.gofile.io/uploadFile"
executor = ThreadPoolExecutor(max_workers=10)
upload_stats = {}

def get_best_server():
    try:
        response = requests.get("https://api.gofile.io/getServer", timeout=5)
        if response.ok:
            data = response.json()
            if data.get("status") == "ok":
                return f"https://{data['data']['server']}.gofile.io/uploadFile"
    except:
        pass
    return GOFILE_API

def upload_to_catbox(file_path):
    with open(file_path, "rb") as f:
        files = {"fileToUpload": f}
        data = {"reqtype": "fileupload"}
        response = requests.post(CATBOX_API, data=data, files=files, timeout=120)
    return response

def upload_to_gofile(file_path):
    server = get_best_server()
    with open(file_path, "rb") as f:
        files = {"file": f}
        response = requests.post(server, files=files, timeout=120)
    return response

async def telegraph_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user_id = message.from_user.id

    if not message.reply_to_message:
        await message.reply_text("Reply to a message with /telegraph to upload it")
        return

    reply_msg = message.reply_to_message
    status_message = await message.reply_text("Uploading...")

    file_id = None
    file_ext = "bin"
    file_type = "file"
    
    if reply_msg.photo:
        file_id = reply_msg.photo[-1].file_id
        file_ext = "jpg"
        file_type = "photo"
    elif reply_msg.video:
        file_id = reply_msg.video.file_id
        file_ext = "mp4"
        file_type = "video"
    elif reply_msg.animation:
        file_id = reply_msg.animation.file_id
        file_ext = "gif"
        file_type = "gif"
    elif reply_msg.document:
        file_id = reply_msg.document.file_id
        file_name = reply_msg.document.file_name
        file_ext = file_name.split('.')[-1] if '.' in file_name else "bin"
        file_type = "document"
    elif reply_msg.sticker:
        file_id = reply_msg.sticker.file_id
        file_ext = "webp"
        file_type = "sticker"
    elif reply_msg.audio:
        file_id = reply_msg.audio.file_id
        file_ext = "mp3"
        file_type = "audio"
    else:
        await status_message.edit_text("Unsupported media type")
        return

    temp_path = None
    start_time = time.time()
    
    try:
        file = await context.bot.get_file(file_id)
        temp_path = tempfile.mktemp(suffix=f".{file_ext}")
        
        await file.download_to_drive(temp_path)
        
        file_size = os.path.getsize(temp_path)
        size_mb = file_size / (1024 * 1024)
        
        if size_mb > 50:
            await status_message.edit_text("File too large. Maximum size is 50 MB")
            return
        
        await status_message.edit_text(f"Uploading {size_mb:.2f} MB...")
        
        loop = asyncio.get_event_loop()
        
        if size_mb > 20:
            response = await loop.run_in_executor(executor, upload_to_gofile, temp_path)
            
            if response.ok:
                result = response.json()
                if result.get("status") == "ok":
                    url = result["data"]["downloadPage"]
                    direct_link = result["data"]["fileId"]
                    upload_time = time.time() - start_time
                    
                    if user_id not in upload_stats:
                        upload_stats[user_id] = {"count": 0, "total_size": 0}
                    upload_stats[user_id]["count"] += 1
                    upload_stats[user_id]["total_size"] += size_mb
                    
                    keyboard = [
                        [InlineKeyboardButton("Open Link", url=url)],
                        [InlineKeyboardButton("Stats", callback_data=f"stats_{user_id}")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await status_message.edit_text(
                        f"Successfully uploaded via GoFile\n\n"
                        f"Type: {file_type.upper()}\n"
                        f"Size: {size_mb:.2f} MB\n"
                        f"Time: {upload_time:.1f}s\n\n"
                        f"`{url}`",
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                    return
        
        response = await loop.run_in_executor(executor, upload_to_catbox, temp_path)

        if response.ok:
            url = response.text.strip()
            if url.startswith("http"):
                upload_time = time.time() - start_time
                
                if user_id not in upload_stats:
                    upload_stats[user_id] = {"count": 0, "total_size": 0}
                upload_stats[user_id]["count"] += 1
                upload_stats[user_id]["total_size"] += size_mb
                
                keyboard = [
                    [InlineKeyboardButton("Open Link", url=url)],
                    [InlineKeyboardButton("Stats", callback_data=f"stats_{user_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await status_message.edit_text(
                    f"Successfully uploaded\n\n"
                    f"Type: {file_type.upper()}\n"
                    f"Size: {size_mb:.2f} MB\n"
                    f"Time: {upload_time:.1f}s\n\n"
                    f"`{url}`",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            else:
                await status_message.edit_text(f"Upload failed: {url}")
        else:
            await status_message.edit_text(f"Upload failed with status {response.status_code}")

    except asyncio.TimeoutError:
        await status_message.edit_text("Upload timeout, file too large")
    except Exception as e:
        await status_message.edit_text(f"Error: {str(e)}")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("stats_"):
        user_id = int(query.data.split("_")[1])
        if user_id in upload_stats:
            stats = upload_stats[user_id]
            await query.answer(
                f"Total uploads: {stats['count']}\n"
                f"Total size: {stats['total_size']:.2f} MB",
                show_alert=True
            )
        else:
            await query.answer("No stats available", show_alert=True)

application.add_handler(CommandHandler("t", telegraph_command))
application.add_handler(CallbackQueryHandler(button_callback))