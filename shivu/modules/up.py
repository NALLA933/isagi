import re
import json
import aiohttp
import urllib.parse
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from shivu import application

async def get_ig_media_v2(url: str):
    """
    Enhanced Instagram downloader with multiple working APIs (November 2024)
    """
    
    # Extract shortcode from URL for better compatibility
    shortcode_match = re.search(r'(?:p|reel|tv)/([A-Za-z0-9_-]+)', url)
    shortcode = shortcode_match.group(1) if shortcode_match else None
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Origin': 'https://www.instagram.com',
        'Referer': 'https://www.instagram.com/',
    }
    
    async with aiohttp.ClientSession() as session:
        
        # Method 1: RapidAPI - Instagram Video Downloader (Free tier available)
        try:
            rapid_url = "https://instagram-video-downloader13.p.rapidapi.com/"
            rapid_headers = {
                "X-RapidAPI-Key": "YOUR_RAPIDAPI_KEY_HERE",  # Get free key from rapidapi.com
                "X-RapidAPI-Host": "instagram-video-downloader13.p.rapidapi.com",
                "Content-Type": "application/json"
            }
            
            payload = {"url": url}
            
            async with session.post(rapid_url, json=payload, headers=rapid_headers, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if data.get('success') and data.get('media'):
                        media_list = []
                        for item in data['media']:
                            if item.get('url'):
                                media_type = 'video' if item.get('type') == 'video' else 'photo'
                                media_list.append({'type': media_type, 'url': item['url']})
                        
                        if media_list:
                            return media_list
        except Exception as e:
            print(f"RapidAPI method failed: {e}")
        
        # Method 2: FastSaverAPI - Highly reliable (used by 50+ bots)
        try:
            fastsaver_url = "https://fastsaverapi.com/api/instagram"
            fastsaver_payload = {"url": url}
            fastsaver_headers = {
                "Content-Type": "application/json",
                "User-Agent": "TelegramBot/1.0"
            }
            
            async with session.post(fastsaver_url, json=fastsaver_payload, headers=fastsaver_headers, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if data.get('result'):
                        media_list = []
                        result = data['result']
                        
                        # Handle video
                        if result.get('video'):
                            for video in result['video']:
                                if video.get('url'):
                                    media_list.append({'type': 'video', 'url': video['url']})
                        
                        # Handle images
                        if result.get('image'):
                            for image in result['image']:
                                if image.get('url'):
                                    media_list.append({'type': 'photo', 'url': image['url']})
                        
                        if media_list:
                            return media_list[:5]  # Limit to 5 items
        except Exception as e:
            print(f"FastSaverAPI method failed: {e}")
        
        # Method 3: API-Insta (Reliable paid/free service)
        try:
            api_insta_url = f"https://api.api-insta.com/integration/content/fetch"
            api_insta_headers = {
                "Content-Type": "application/json",
                "x-api-key": "YOUR_API_INSTA_KEY"  # Get from api-insta.com
            }
            
            params = {"url": url}
            
            async with session.get(api_insta_url, params=params, headers=api_insta_headers, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if data.get('data') and data['data'].get('media'):
                        media_list = []
                        for item in data['data']['media']:
                            if item.get('url'):
                                media_type = item.get('type', 'video')
                                media_list.append({'type': media_type, 'url': item['url']})
                        
                        if media_list:
                            return media_list
        except Exception as e:
            print(f"API-Insta method failed: {e}")
        
        # Method 4: SnapInsta API (No auth required - most reliable free option)
        try:
            snapinsta_url = "https://snapinsta.app/api/ajaxSearch"
            snapinsta_payload = {
                'q': url,
                't': 'media',
                'lang': 'en'
            }
            snapinsta_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Origin': 'https://snapinsta.app',
                'Referer': 'https://snapinsta.app/'
            }
            
            async with session.post(snapinsta_url, data=snapinsta_payload, headers=snapinsta_headers, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if data.get('data'):
                        html = data['data']
                        
                        # Extract video URLs
                        video_patterns = [
                            r'href="(https://[^"]+\.cdninstagram\.com/[^"]+)"[^>]*>.*?Download.*?(?:Video|HD)',
                            r'href="(https://[^"]+\.fbcdn\.net/[^"]+)"[^>]*>.*?Download',
                            r'href="([^"]+)"[^>]*download[^>]*>.*?Download.*?Video'
                        ]
                        
                        for pattern in video_patterns:
                            video_matches = re.findall(pattern, html, re.IGNORECASE | re.DOTALL)
                            if video_matches:
                                # Get the highest quality (usually first)
                                return [{'type': 'video', 'url': video_matches[0]}]
                        
                        # Extract image URLs
                        img_patterns = [
                            r'href="(https://[^"]+\.cdninstagram\.com/[^"]+\.jpg[^"]*)"',
                            r'href="(https://[^"]+\.fbcdn\.net/[^"]+\.jpg[^"]*)"'
                        ]
                        
                        for pattern in img_patterns:
                            img_matches = re.findall(pattern, html)
                            if img_matches:
                                return [{'type': 'photo', 'url': img} for img in img_matches[:5]]
        except Exception as e:
            print(f"SnapInsta method failed: {e}")
        
        # Method 5: Alternative direct Instagram embedding (works for public posts)
        if shortcode:
            try:
                embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
                
                async with session.get(embed_url, headers=headers, timeout=20) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        
                        # Find video URL in embedded player
                        video_match = re.search(r'"video_url":"([^"]+)"', html)
                        if video_match:
                            video_url = video_match.group(1).replace('\\u0026', '&')
                            return [{'type': 'video', 'url': video_url}]
                        
                        # Find image URL
                        img_match = re.search(r'"display_url":"([^"]+)"', html)
                        if img_match:
                            img_url = img_match.group(1).replace('\\u0026', '&')
                            return [{'type': 'photo', 'url': img_url}]
            except Exception as e:
                print(f"Embed method failed: {e}")
        
        # Method 6: Insta.savetube.me (Backup)
        try:
            savetube_url = "https://insta.savetube.me/downloadgram"
            params = {'url': url}
            savetube_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with session.get(savetube_url, params=params, headers=savetube_headers, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # Handle various response formats
                    media_url = None
                    if isinstance(data, dict):
                        media_url = (data.get('url') or 
                                   data.get('download_url') or 
                                   (data.get('links', [{}])[0].get('url') if data.get('links') else None))
                    
                    if media_url:
                        return [{'type': 'video', 'url': media_url}]
        except Exception as e:
            print(f"SaveTube method failed: {e}")
        
        # Method 7: Y2Mate style API
        try:
            y2mate_url = "https://v3.y2mate.com/api/ajaxSearch/instagram"
            y2mate_payload = {
                'q': url,
                'vt': 'downloader'
            }
            
            async with session.post(y2mate_url, data=y2mate_payload, headers=headers, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if data.get('links') and data['links'].get('video'):
                        for quality, link_data in data['links']['video'].items():
                            if link_data.get('url'):
                                return [{'type': 'video', 'url': link_data['url']}]
        except Exception as e:
            print(f"Y2Mate method failed: {e}")
    
    return None


async def ig_download(update: Update, context: CallbackContext):
    """
    Handle /ig and /insta commands with robust error handling
    """
    message = update.message
    
    if not context.args:
        await message.reply_text(
            "📸 *Instagram Downloader Bot*\n\n"
            "*Usage:* `/ig <instagram_url>`\n\n"
            "*Examples:*\n"
            "• `/ig https://www.instagram.com/p/ABC123/`\n"
            "• `/ig https://www.instagram.com/reel/XYZ789/`\n\n"
            "*Supported:* Posts, Reels, Videos, Images, Carousels\n"
            "*Note:* Only public accounts work",
            parse_mode='Markdown'
        )
        return
    
    url = context.args[0]
    
    # Validate Instagram URL
    if not re.search(r'instagram\.com/(p|reel|tv)/[A-Za-z0-9_-]+', url):
        await message.reply_text(
            "❌ *Invalid Instagram URL!*\n\n"
            "Please provide a valid Instagram post, reel, or video link.\n"
            "Example: `https://www.instagram.com/p/ABC123/`",
            parse_mode='Markdown'
        )
        return
    
    status_msg = await message.reply_text("⏳ *Downloading...* Please wait...", parse_mode='Markdown')
    
    try:
        media = await get_ig_media_v2(url)
        
        if not media:
            await status_msg.edit_text(
                "❌ *Download Failed*\n\n"
                "*Possible reasons:*\n"
                "• Private account (we can only download public posts)\n"
                "• Invalid or deleted post\n"
                "• Instagram temporarily blocked the request\n"
                "• Post contains restricted content\n\n"
                "*Try:*\n"
                "• Make sure the account is public\n"
                "• Verify the URL is correct\n"
                "• Try again in a few minutes",
                parse_mode='Markdown'
            )
            return
        
        await status_msg.edit_text(f"✅ Found {len(media)} file(s). Uploading...", parse_mode='Markdown')
        
        success_count = 0
        for idx, item in enumerate(media, 1):
            try:
                caption = f"📥 Downloaded {idx}/{len(media)}"
                
                if item['type'] == 'video':
                    await message.reply_video(
                        item['url'],
                        caption=caption,
                        supports_streaming=True
                    )
                else:
                    await message.reply_photo(
                        item['url'],
                        caption=caption
                    )
                
                success_count += 1
                
            except Exception as e:
                print(f"Error sending media {idx}: {e}")
                # Try sending as document if direct upload fails
                try:
                    await message.reply_document(
                        item['url'],
                        caption=f"📎 Media file {idx} ({item['type']})"
                    )
                    success_count += 1
                except Exception as doc_error:
                    print(f"Failed to send as document: {doc_error}")
        
        # Delete status message after successful upload
        try:
            await status_msg.delete()
        except:
            pass
        
        if success_count == 0:
            await message.reply_text(
                "❌ Failed to upload media files.\n"
                "The download links may have expired. Please try again."
            )
    
    except Exception as e:
        error_message = str(e)
        print(f"Instagram download error: {error_message}")
        
        await status_msg.edit_text(
            f"❌ *An error occurred*\n\n"
            f"Error: `{error_message[:100]}`\n\n"
            "Please try again later or contact support if the issue persists.",
            parse_mode='Markdown'
        )


# Register command handlers
application.add_handler(CommandHandler(["ig", "insta", "instagram"], ig_download))