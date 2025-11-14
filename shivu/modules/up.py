import httpx
import os
import re
import json
from pyrogram import filters
from pyrogram.types import Message
from shivu import shivuu as app

def extract_instagram_url(text: str) -> str:
    """Extract Instagram URL from text"""
    patterns = [
        r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)',
        r'https?://(?:www\.)?instagram\.com/stories/([A-Za-z0-9._]+)/([0-9]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None

async def download_with_fastdl(url: str) -> dict:
    """Using FastDL API - Most Reliable"""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            api_url = "https://v3.fastdl.app/api/convert"
            
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            payload = {"url": url}
            
            response = await client.post(api_url, headers=headers, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                # Check for video URL in various response formats
                video_url = (data.get("url") or 
                           data.get("video_url") or 
                           data.get("download_url") or
                           (data.get("media", [{}])[0].get("url") if data.get("media") else None))
                
                if video_url:
                    return {"video_url": video_url, "source": "FastDL"}
    except Exception as e:
        print(f"FastDL error: {e}")
    return {"error": "FastDL failed"}

async def download_with_saveinsta(url: str) -> dict:
    """Using SaveInsta API"""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            api_url = "https://saveinsta.app/core/ajax.php"
            
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-Requested-With": "XMLHttpRequest"
            }
            
            data = {
                "url": url,
                "action": "post"
            }
            
            response = await client.post(api_url, headers=headers, data=data)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("data"):
                    html = result.get("data")
                    # Extract video URL from response
                    video_match = re.search(r'href="([^"]+)"[^>]*download[^>]*>.*?MP4', html, re.IGNORECASE)
                    if video_match:
                        video_url = video_match.group(1).replace("&amp;", "&")
                        return {"video_url": video_url, "source": "SaveInsta"}
    except Exception as e:
        print(f"SaveInsta error: {e}")
    return {"error": "SaveInsta failed"}

async def download_with_indown(url: str) -> dict:
    """Using Indown.io API"""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            api_url = "https://indown.io/download"
            
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            data = {"url": url}
            
            response = await client.post(api_url, headers=headers, data=data)
            
            if response.status_code == 200:
                html = response.text
                # Extract video URL from response
                video_match = re.search(r'href="([^"]+)"[^>]*class="download-btn', html)
                if video_match:
                    video_url = video_match.group(1)
                    return {"video_url": video_url, "source": "Indown"}
    except Exception as e:
        print(f"Indown error: {e}")
    return {"error": "Indown failed"}

async def download_with_downloadgram(url: str) -> dict:
    """Using DownloadGram API"""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            api_url = "https://downloadgram.org/"
            
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            data = {
                "url": url,
                "submit": ""
            }
            
            response = await client.post(api_url, headers=headers, data=data)
            
            if response.status_code == 200:
                html = response.text
                # Extract video download URL
                video_match = re.search(r'href="([^"]+)"[^>]*download[^>]*video', html, re.IGNORECASE)
                if video_match:
                    video_url = video_match.group(1)
                    return {"video_url": video_url, "source": "DownloadGram"}
    except Exception as e:
        print(f"DownloadGram error: {e}")
    return {"error": "DownloadGram failed"}

async def download_with_savefrom(url: str) -> dict:
    """Using SaveFrom.net API"""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Extract shortcode
            shortcode_match = re.search(r'/(?:p|reel|tv)/([A-Za-z0-9_-]+)', url)
            if not shortcode_match:
                return {"error": "Invalid URL"}
            
            shortcode = shortcode_match.group(1)
            api_url = f"https://www.savefrom.net/download?url=https://www.instagram.com/p/{shortcode}/"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            response = await client.get(api_url, headers=headers)
            
            if response.status_code == 200:
                html = response.text
                # Extract video URL
                video_match = re.search(r'href="([^"]+)"[^>]*class="[^"]*download', html)
                if video_match:
                    video_url = video_match.group(1)
                    return {"video_url": video_url, "source": "SaveFrom"}
    except Exception as e:
        print(f"SaveFrom error: {e}")
    return {"error": "SaveFrom failed"}

async def download_with_igdownloader(url: str) -> dict:
    """Using IGDownloader API"""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            api_url = "https://igdownloader.app/api/ajaxSearch"
            
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            data = {
                "q": url,
                "t": "media",
                "lang": "en"
            }
            
            response = await client.post(api_url, headers=headers, data=data)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("data"):
                    html = result.get("data")
                    # Extract video URL
                    video_match = re.search(r'href="([^"]+)"[^>]*>[\s]*Download[\s]*Video', html, re.IGNORECASE)
                    if video_match:
                        video_url = video_match.group(1).replace("&amp;", "&")
                        return {"video_url": video_url, "source": "IGDownloader"}
    except Exception as e:
        print(f"IGDownloader error: {e}")
    return {"error": "IGDownloader failed"}

async def try_all_apis(url: str) -> dict:
    """Try all APIs in sequence until one works"""
    apis = [
        download_with_fastdl,
        download_with_saveinsta,
        download_with_igdownloader,
        download_with_indown,
        download_with_downloadgram,
        download_with_savefrom,
    ]
    
    for api_func in apis:
        result = await api_func(url)
        if "video_url" in result:
            return result
    
    return {"error": "All APIs failed to extract video"}

@app.on_message(filters.command(["insta", "instagram", "igdl", "ig"]))
async def instagram_downloader(client, message: Message):
    """Main Instagram downloader command handler"""
    
    # Check if URL is provided
    if len(message.command) < 2 and not message.reply_to_message:
        await message.reply_text(
            "📥 **Instagram Video Downloader**\n\n"
            "**Usage:**\n"
            "`/insta <instagram_url>`\n\n"
            "**Example:**\n"
            "`/insta https://www.instagram.com/reel/xxxxx/`\n\n"
            "**Supported:** Posts, Reels, IGTV"
        )
        return
    
    # Get URL from command or replied message
    if len(message.command) >= 2:
        url = " ".join(message.command[1:])
    elif message.reply_to_message:
        url = message.reply_to_message.text or message.reply_to_message.caption or ""
    else:
        await message.reply_text("❌ Please provide an Instagram URL")
        return
    
    # Extract Instagram URL
    instagram_url = extract_instagram_url(url)
    
    if not instagram_url:
        await message.reply_text(
            "❌ **Invalid Instagram URL**\n\n"
            "Please provide a valid Instagram post, reel, or IGTV link."
        )
        return
    
    # Send processing message
    status_msg = await message.reply_text("🔄 **Processing...**\nFetching video from Instagram...")
    
    try:
        # Try all APIs to get video URL
        result = await try_all_apis(instagram_url)
        
        if "error" in result:
            await status_msg.edit_text(
                f"❌ **Download Failed**\n\n"
                f"Error: {result['error']}\n\n"
                "This could be due to:\n"
                "• Private account\n"
                "• Invalid/deleted post\n"
                "• Instagram restrictions"
            )
            return
        
        video_url = result.get("video_url")
        source = result.get("source", "Unknown")
        
        if not video_url:
            await status_msg.edit_text("❌ Could not extract video URL")
            return
        
        await status_msg.edit_text(f"⬇️ **Downloading video...**\nSource: {source}")
        
        # Download video
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            video_response = await client.get(video_url)
            
            if video_response.status_code == 200:
                # Save temporary file
                temp_file = f"temp_insta_{message.from_user.id}_{message.id}.mp4"
                
                with open(temp_file, "wb") as f:
                    f.write(video_response.content)
                
                file_size = os.path.getsize(temp_file)
                file_size_mb = file_size / (1024 * 1024)
                
                await status_msg.edit_text(f"⬆️ **Uploading video...**\nSize: {file_size_mb:.2f} MB")
                
                # Upload video
                await message.reply_video(
                    video=temp_file,
                    caption=f"📥 **Downloaded from Instagram**\n\n🔗 [Source]({instagram_url})\n💾 Size: {file_size_mb:.2f} MB",
                    supports_streaming=True
                )
                
                # Clean up
                await status_msg.delete()
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            else:
                await status_msg.edit_text(
                    f"❌ **Download Failed**\n\n"
                    f"HTTP Status: {video_response.status_code}\n"
                    "Please try again later."
                )
    
    except httpx.TimeoutException:
        await status_msg.edit_text("❌ **Timeout Error**\n\nThe request took too long. Please try again.")
    except httpx.HTTPError as e:
        await status_msg.edit_text(f"❌ **Network Error**\n\n{str(e)}")
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error**\n\n{str(e)}")
        # Clean up temp file if exists
        temp_file = f"temp_insta_{message.from_user.id}_{message.id}.mp4"
        if os.path.exists(temp_file):
            os.remove(temp_file)

# Additional command for help
@app.on_message(filters.command(["instahelp", "ighelp"]))
async def instagram_help(client, message: Message):
    """Help command for Instagram downloader"""
    help_text = """
📥 **Instagram Video Downloader Help**

**Commands:**
• `/insta <url>` - Download Instagram video
• `/instagram <url>` - Download Instagram video
• `/igdl <url>` - Download Instagram video
• `/ig <url>` - Download Instagram video

**Supported Content:**
✅ Instagram Posts (with videos)
✅ Instagram Reels
✅ IGTV Videos

**How to use:**
1. Copy the Instagram post/reel link
2. Send `/insta <paste_link>`
3. Wait for the video to download
4. Video will be sent to you

**Example:**
`/insta https://www.instagram.com/reel/ABC123/`

**Note:**
• Private account videos cannot be downloaded
• Some videos may be restricted by Instagram
• Video quality depends on source
"""
    await message.reply_text(help_text)