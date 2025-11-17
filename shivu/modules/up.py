import re
import json
import aiohttp
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from shivu import application

async def get_ig_media(url: str):
    """
    Multi-method Instagram downloader with fallback options
    """
    
    # Method 1: Try direct Instagram JSON API
    try:
        async with aiohttp.ClientSession() as session:
            # Extract shortcode from URL
            shortcode_match = re.search(r'(?:p|reel|tv)/([A-Za-z0-9_-]+)', url)
            if shortcode_match:
                shortcode = shortcode_match.group(1)
                
                # Try Instagram's JSON endpoint
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                }
                
                ig_url = f'https://www.instagram.com/p/{shortcode}/?__a=1&__d=dis'
                async with session.get(ig_url, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        # Parse media from response
                        if 'items' in data and len(data['items']) > 0:
                            item = data['items'][0]
                            
                            # Handle video
                            if item.get('video_versions'):
                                video_url = item['video_versions'][0]['url']
                                return [{'type': 'video', 'url': video_url}]
                            
                            # Handle images/carousel
                            if item.get('carousel_media'):
                                media_list = []
                                for media in item['carousel_media'][:5]:
                                    if media.get('video_versions'):
                                        media_list.append({'type': 'video', 'url': media['video_versions'][0]['url']})
                                    elif media.get('image_versions2'):
                                        media_list.append({'type': 'photo', 'url': media['image_versions2']['candidates'][0]['url']})
                                return media_list
                            
                            # Single image
                            if item.get('image_versions2'):
                                img_url = item['image_versions2']['candidates'][0]['url']
                                return [{'type': 'photo', 'url': img_url}]
    except Exception as e:
        print(f"Method 1 failed: {e}")
    
    # Method 2: RapidAPI Instagram Downloader (Free tier)
    try:
        async with aiohttp.ClientSession() as session:
            api_url = "https://instagram-downloader-download-instagram-videos-stories1.p.rapidapi.com/get-info-rapidapi"
            
            headers = {
                "content-type": "application/x-www-form-urlencoded",
                "X-RapidAPI-Key": "YOUR_RAPIDAPI_KEY",  # Add your key or leave empty for testing
                "X-RapidAPI-Host": "instagram-downloader-download-instagram-videos-stories1.p.rapidapi.com"
            }
            
            payload = {"url": url}
            
            async with session.post(api_url, data=payload, headers=headers, timeout=15) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    
                    if result.get('download'):
                        media_list = []
                        for media in result['download']:
                            if 'video' in media:
                                media_list.append({'type': 'video', 'url': media['video']})
                            elif 'image' in media:
                                media_list.append({'type': 'photo', 'url': media['image']})
                        
                        if media_list:
                            return media_list
    except Exception as e:
        print(f"Method 2 failed: {e}")
    
    # Method 3: Snapinsta API
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
            }
            
            api_url = f"https://snapinsta.app/api/ajaxSearch"
            payload = {'q': url, 't': 'media', 'lang': 'en'}
            
            async with session.post(api_url, data=payload, headers=headers, timeout=15) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    
                    if result.get('data'):
                        html = result['data']
                        
                        # Extract video URL
                        video_match = re.search(r'href="([^"]+)"[^>]*download[^>]*>.*?Download.*?Video', html, re.IGNORECASE)
                        if video_match:
                            return [{'type': 'video', 'url': video_match.group(1)}]
                        
                        # Extract image URLs
                        img_matches = re.findall(r'href="([^"]+)"[^>]*download[^>]*>.*?Download.*?(?:Image|Photo)', html, re.IGNORECASE)
                        if img_matches:
                            return [{'type': 'photo', 'url': img} for img in img_matches[:5]]
    except Exception as e:
        print(f"Method 3 failed: {e}")
    
    # Method 4: Insta.savetube.me
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
            
            api_url = f"https://insta.savetube.me/downloadgram"
            params = {'url': url}
            
            async with session.get(api_url, params=params, headers=headers, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # Check various possible response structures
                    if isinstance(data, dict):
                        # Try direct url field
                        if data.get('url'):
                            return [{'type': 'video', 'url': data['url']}]
                        
                        # Try links array
                        if data.get('links'):
                            media_list = []
                            for link in data['links'][:5]:
                                url_field = link.get('url') or link.get('link')
                                if url_field:
                                    media_type = 'video' if 'video' in link.get('quality', '').lower() else 'photo'
                                    media_list.append({'type': media_type, 'url': url_field})
                            if media_list:
                                return media_list
    except Exception as e:
        print(f"Method 4 failed: {e}")
    
    # Method 5: Try saveinsta.app
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
            }
            
            api_url = "https://v3.saveinsta.app/api/ajaxSearch"
            payload = {"q": url, "t": "media", "lang": "en"}
            
            async with session.post(api_url, data=payload, headers=headers, timeout=15) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    
                    if result.get('data'):
                        html = result['data']
                        
                        # More robust regex patterns
                        video_pattern = r'href=["\']([^"\']+)["\'][^>]*class=["\'][^"\']*download[^"\']*["\']'
                        video_matches = re.findall(video_pattern, html)
                        
                        if video_matches:
                            # Filter out non-media URLs
                            valid_urls = [u for u in video_matches if 'cdninstagram' in u or 'fbcdn' in u]
                            if valid_urls:
                                return [{'type': 'video', 'url': valid_urls[0]}]
                        
                        # Try image pattern
                        img_pattern = r'src=["\']([^"\']+\.jpg[^"\']*)["\']'
                        img_matches = re.findall(img_pattern, html)
                        if img_matches:
                            return [{'type': 'photo', 'url': img} for img in img_matches[:5]]
    except Exception as e:
        print(f"Method 5 failed: {e}")
    
    return None


async def ig_download(update: Update, context: CallbackContext):
    """
    Handle /ig and /insta commands
    """
    message = update.message
    
    if not context.args:
        await message.reply_text(
            "📸 *Instagram Downloader*\n\n"
            "Usage: `/ig <instagram_url>`\n"
            "Example: `/ig https://www.instagram.com/p/ABC123/`\n\n"
            "Supports: Posts, Reels, Videos, and Images",
            parse_mode='Markdown'
        )
        return
    
    url = context.args[0]
    
    # Validate URL
    if 'instagram.com' not in url:
        await message.reply_text("❌ Please provide a valid Instagram URL!")
        return
    
    status_msg = await message.reply_text("⏳ Downloading... Please wait...")
    
    try:
        media = await get_ig_media(url)
        
        if not media:
            await status_msg.edit_text(
                "❌ Failed to download media.\n\n"
                "Possible reasons:\n"
                "• Private account\n"
                "• Invalid URL\n"
                "• Post deleted\n"
                "• Temporary API issue\n\n"
                "Please check the URL and try again."
            )
            return
        
        await status_msg.edit_text(f"✅ Found {len(media)} media file(s). Sending...")
        
        success_count = 0
        for item in media:
            try:
                if item['type'] == 'video':
                    await message.reply_video(
                        item['url'],
                        caption="📹 Downloaded via Instagram Downloader"
                    )
                else:
                    await message.reply_photo(
                        item['url'],
                        caption="📸 Downloaded via Instagram Downloader"
                    )
                success_count += 1
            except Exception as e:
                print(f"Error sending media: {e}")
                # Try to send as document if direct method fails
                try:
                    await message.reply_document(
                        item['url'],
                        caption=f"📎 Media file ({item['type']})"
                    )
                    success_count += 1
                except:
                    pass
        
        await status_msg.delete()
        
        if success_count == 0:
            await message.reply_text("❌ Failed to send media files. The links might be expired.")
    
    except Exception as e:
        error_msg = str(e)
        await status_msg.edit_text(
            f"❌ An error occurred:\n`{error_msg}`\n\n"
            "Please try again later.",
            parse_mode='Markdown'
        )
        print(f"Instagram download error: {e}")


# Add command handlers
application.add_handler(CommandHandler(["ig", "insta"], ig_download))