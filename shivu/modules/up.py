import httpx
import os
import re
import json
from pyrogram import filters
from pyrogram.types import Message
from shivu import shivuu as app

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

async def get_instagram_video(url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            response = await client.get(url, headers=headers)
            
            if response.status_code != 200:
                return {"error": f"Failed to fetch URL: {response.status_code}"}
            
            html = response.text
            
            patterns = [
                r'"video_url":"([^"]+)"',
                r'"video_versions":\[{"url":"([^"]+)"',
                r'<meta property="og:video" content="([^"]+)"',
                r'"playback_url":"([^"]+)"',
            ]
            
            video_url = None
            for pattern in patterns:
                match = re.search(pattern, html)
                if match:
                    video_url = match.group(1).replace('\\u0026', '&').replace('\/', '/')
                    break
            
            if video_url:
                return {"video_url": video_url}
            else:
                return {"error": "Could not extract video URL from page"}
                
    except Exception as e:
        return {"error": str(e)}

async def download_with_api(url: str) -> dict:
    apis = [
        {
            "url": "https://v3.saveig.app/api/ajaxSearch",
            "method": "POST",
            "data": {"q": url, "t": "media", "lang": "en"},
            "extract": lambda r: re.search(r'href="([^"]+)"[^>]*>Download', r).group(1) if re.search(r'href="([^"]+)"[^>]*>Download', r) else None
        },
        {
            "url": "https://api.downloadgram.org/media",
            "method": "GET",
            "params": lambda u: {"url": u},
            "extract": lambda r: json.loads(r).get("video") or json.loads(r).get("url")
        }
    ]
    
    for api in apis:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if api["method"] == "POST":
                    response = await client.post(api["url"], data=api["data"])
                else:
                    params = api["params"](url)
                    response = await client.get(api["url"], params=params)
                
                if response.status_code == 200:
                    video_url = api["extract"](response.text)
                    if video_url:
                        return {"video_url": video_url}
        except:
            continue
    
    return {"error": "All APIs failed"}

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
        result = await download_with_api(instagram_url)
        
        if "error" in result:
            result = await get_instagram_video(instagram_url)
        
        if "error" in result:
            await status_msg.edit_text(f"Error: {result['error']}")
            return
        
        video_url = result.get("video_url")
        
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
                    caption="Downloaded from Instagram",
                    supports_streaming=True
                )
                
                await status_msg.delete()
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            else:
                await status_msg.edit_text(f"Failed to download video. Status: {video_response.status_code}")
    
    except Exception as e:
        await status_msg.edit_text(f"Error: {str(e)}")