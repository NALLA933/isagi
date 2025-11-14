import base64
import httpx
import os
import re
from pyrogram import filters
from pyrogram.types import Message
from shivu import shivuu as app

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "YOUR_RAPIDAPI_KEY_HERE")
RAPIDAPI_HOST = "instagram-downloader-download-instagram-videos-stories.p.rapidapi.com"

def extract_instagram_url(text: str) -> str:
    patterns = [
        r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)',
        r'https?://(?:www\.)?instagram\.com/stories/([A-Za-z0-9._]+)/([0-9]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None

async def download_instagram_video(url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "X-RapidAPI-Key": RAPIDAPI_KEY,
                "X-RapidAPI-Host": RAPIDAPI_HOST
            }
            params = {"url": url}
            response = await client.get(
                f"https://{RAPIDAPI_HOST}/instagram",
                headers=headers,
                params=params
            )
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"API returned status code {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

@app.on_message(filters.command(["insta", "instagram", "igdl"]))
async def instagram_downloader(client, message: Message):
    if len(message.command) < 2 and not message.reply_to_message:
        await message.reply_text(
            "Usage: /insta <instagram_url>\n"
            "Example: /insta https://www.instagram.com/reel/xxxxx/"
        )
        return
    
    if len(message.command) >= 2:
        url = " ".join(message.command[1:])
    elif message.reply_to_message:
        url = message.reply_to_message.text or message.reply_to_message.caption or ""
    else:
        await message.reply_text("Please provide an Instagram URL")
        return
    
    instagram_url = extract_instagram_url(url)
    
    if not instagram_url:
        await message.reply_text("Invalid Instagram URL")
        return
    
    status_msg = await message.reply_text("Downloading video...")
    
    try:
        result = await download_instagram_video(instagram_url)
        
        if "error" in result:
            await status_msg.edit_text(f"Error: {result['error']}")
            return
        
        video_url = None
        caption_text = "Downloaded from Instagram"
        
        if isinstance(result, dict):
            if "url" in result:
                video_url = result["url"]
            elif "video_url" in result:
                video_url = result["video_url"]
            elif "download_url" in result:
                video_url = result["download_url"]
            elif "result" in result and isinstance(result["result"], str):
                video_url = result["result"]
            elif "data" in result:
                if isinstance(result["data"], dict):
                    video_url = result["data"].get("url") or result["data"].get("video_url")
                elif isinstance(result["data"], list) and len(result["data"]) > 0:
                    video_url = result["data"][0].get("url")
            
            if "title" in result:
                caption_text = result['title']
            elif "caption" in result:
                caption_text = result['caption'][:100]
        
        if not video_url:
            await status_msg.edit_text("Could not extract video URL")
            return
        
        await status_msg.edit_text("Uploading video...")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            video_response = await client.get(video_url)
            
            if video_response.status_code == 200:
                temp_file = f"temp_insta_{message.from_user.id}.mp4"
                
                with open(temp_file, "wb") as f:
                    f.write(video_response.content)
                
                await message.reply_video(
                    video=temp_file,
                    caption=caption_text,
                    supports_streaming=True
                )
                
                await status_msg.delete()
                os.remove(temp_file)
            else:
                await status_msg.edit_text(f"Failed to download video. Status: {video_response.status_code}")
    
    except Exception as e:
        await status_msg.edit_text(f"Error: {str(e)}")