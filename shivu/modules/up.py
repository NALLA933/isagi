import re
import os
import tempfile
import asyncio
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from shivu import application

# Install: pip install instagrapi
try:
    from instagrapi import Client
    from instagrapi.exceptions import ClientError, LoginRequired
except ImportError:
    print("ERROR: Please install instagrapi: pip install instagrapi")
    Client = None

async def download_instagram_media_anonymous(url: str):
    """
    Download Instagram media anonymously using instagrapi (no login required for public posts)
    """
    if not Client:
        return None, "Instagrapi library not installed"
    
    try:
        # Extract shortcode from URL
        shortcode_match = re.search(r'(?:p|reel|tv)/([A-Za-z0-9_-]+)', url)
        if not shortcode_match:
            return None, "Invalid Instagram URL format"
        
        shortcode = shortcode_match.group(1)
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        
        def download_post():
            try:
                # Create client - no login needed for public posts
                cl = Client()
                cl.delay_range = [1, 3]
                
                # Get media info from shortcode (uses public web API - no login required)
                media_pk = cl.media_pk_from_code(shortcode)
                media_info = cl.media_info(media_pk)
                
                files = []
                
                # Handle video
                if media_info.media_type == 2 and media_info.video_url:
                    # Download video
                    video_path = cl.video_download(media_pk, folder=temp_dir)
                    files.append({'type': 'video', 'path': str(video_path)})
                
                # Handle carousel/album (multiple images/videos)
                elif media_info.media_type == 8 and media_info.resources:
                    for resource in media_info.resources[:5]:  # Limit to 5
                        if resource.video_url:
                            video_path = cl.video_download(resource.pk, folder=temp_dir)
                            files.append({'type': 'video', 'path': str(video_path)})
                        elif resource.thumbnail_url:
                            photo_path = cl.photo_download(resource.pk, folder=temp_dir)
                            files.append({'type': 'photo', 'path': str(photo_path)})
                
                # Handle single image
                elif media_info.media_type == 1:
                    photo_path = cl.photo_download(media_pk, folder=temp_dir)
                    files.append({'type': 'photo', 'path': str(photo_path)})
                
                return files, None
                
            except LoginRequired:
                # If login is required, try alternative method
                try:
                    cl = Client()
                    # Use public web endpoint without login
                    media = cl.media_info_a1(shortcode)
                    
                    files = []
                    
                    # Download based on media type
                    if media.video_url:
                        import aiohttp
                        import aiofiles
                        
                        async def download_file(url, path):
                            async with aiohttp.ClientSession() as session:
                                async with session.get(url) as resp:
                                    if resp.status == 200:
                                        async with aiofiles.open(path, 'wb') as f:
                                            await f.write(await resp.read())
                        
                        video_path = os.path.join(temp_dir, f"{shortcode}.mp4")
                        asyncio.run(download_file(media.video_url, video_path))
                        files.append({'type': 'video', 'path': video_path})
                    
                    elif media.thumbnail_url:
                        import aiohttp
                        import aiofiles
                        
                        async def download_file(url, path):
                            async with aiohttp.ClientSession() as session:
                                async with session.get(url) as resp:
                                    if resp.status == 200:
                                        async with aiofiles.open(path, 'wb') as f:
                                            await f.write(await resp.read())
                        
                        photo_path = os.path.join(temp_dir, f"{shortcode}.jpg")
                        asyncio.run(download_file(media.thumbnail_url, photo_path))
                        files.append({'type': 'photo', 'path': photo_path})
                    
                    return files, None
                    
                except Exception as e2:
                    return None, f"Private post or login required: {str(e2)}"
            
            except ClientError as e:
                if "challenge_required" in str(e).lower():
                    return None, "Instagram challenge required - try again later"
                elif "not found" in str(e).lower():
                    return None, "Post not found or deleted"
                elif "private" in str(e).lower():
                    return None, "Private account - cannot download"
                else:
                    return None, str(e)
            
            except Exception as e:
                return None, str(e)
        
        # Execute download
        files, error = await loop.run_in_executor(None, download_post)
        
        if error:
            # Cleanup
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except:
                pass
            return None, error
        
        return files, temp_dir
        
    except Exception as e:
        return None, str(e)


async def ig_download(update: Update, context: CallbackContext):
    """
    Handle /ig and /insta commands
    """
    message = update.message
    
    if not Client:
        await message.reply_text(
            "❌ *Service Unavailable*\n\n"
            "Instagram downloader is not configured.\n"
            "Contact administrator.",
            parse_mode='Markdown'
        )
        return
    
    if not context.args:
        await message.reply_text(
            "📸 *Instagram Downloader Bot*\n\n"
            "*Usage:* `/ig <instagram_url>`\n\n"
            "*Examples:*\n"
            "• `/ig https://www.instagram.com/p/ABC123/`\n"
            "• `/ig https://www.instagram.com/reel/XYZ789/`\n\n"
            "*Supported Content:*\n"
            "✅ Posts & Photos\n"
            "✅ Videos & Reels\n"
            "✅ Carousels (multiple images)\n"
            "✅ Public accounts only\n\n"
            "*Note:* Private posts cannot be downloaded",
            parse_mode='Markdown'
        )
        return
    
    url = context.args[0]
    
    # Validate URL
    if not re.search(r'instagram\.com/(p|reel|tv)/[A-Za-z0-9_-]+', url):
        await message.reply_text(
            "❌ *Invalid URL*\n\n"
            "Please provide a valid Instagram link.\n\n"
            "*Format:* `https://www.instagram.com/p/CODE/`",
            parse_mode='Markdown'
        )
        return
    
    status_msg = await message.reply_text(
        "⏳ *Downloading...*\n\nPlease wait...",
        parse_mode='Markdown'
    )
    
    try:
        # Download media
        files, temp_dir_or_error = await download_instagram_media_anonymous(url)
        
        if files is None:
            error_msg = temp_dir_or_error
            
            # Provide specific error messages
            if "private" in error_msg.lower():
                await status_msg.edit_text(
                    "❌ *Private Account*\n\n"
                    "This post is from a private account.\n"
                    "Only public posts can be downloaded.",
                    parse_mode='Markdown'
                )
            elif "not found" in error_msg.lower():
                await status_msg.edit_text(
                    "❌ *Post Not Found*\n\n"
                    "The post may have been deleted or URL is incorrect.",
                    parse_mode='Markdown'
                )
            elif "challenge" in error_msg.lower() or "rate" in error_msg.lower():
                await status_msg.edit_text(
                    "❌ *Temporarily Blocked*\n\n"
                    "Instagram has temporarily restricted access.\n"
                    "Please try again in 5-10 minutes.",
                    parse_mode='Markdown'
                )
            elif "login required" in error_msg.lower():
                await status_msg.edit_text(
                    "❌ *Login Required*\n\n"
                    "This content requires authentication.\n"
                    "The post may be from a private account.",
                    parse_mode='Markdown'
                )
            else:
                await status_msg.edit_text(
                    f"❌ *Download Failed*\n\n"
                    f"Error: `{error_msg[:100]}`",
                    parse_mode='Markdown'
                )
            return
        
        if not files:
            await status_msg.edit_text(
                "❌ *No Media Found*\n\n"
                "No downloadable content in this post.",
                parse_mode='Markdown'
            )
            # Cleanup
            try:
                import shutil
                shutil.rmtree(temp_dir_or_error)
            except:
                pass
            return
        
        await status_msg.edit_text(
            f"✅ Found {len(files)} file(s)\n📤 Uploading...",
            parse_mode='Markdown'
        )
        
        # Send files
        success_count = 0
        for idx, item in enumerate(files, 1):
            try:
                caption = f"📥 {idx}/{len(files)}"
                
                if item['type'] == 'video':
                    with open(item['path'], 'rb') as video_file:
                        await message.reply_video(
                            video=video_file,
                            caption=caption,
                            supports_streaming=True
                        )
                else:
                    with open(item['path'], 'rb') as photo_file:
                        await message.reply_photo(
                            photo=photo_file,
                            caption=caption
                        )
                
                success_count += 1
                
            except Exception as e:
                print(f"Error sending file {idx}: {e}")
                # Try as document
                try:
                    with open(item['path'], 'rb') as doc_file:
                        await message.reply_document(
                            document=doc_file,
                            caption=f"📎 Media {idx}"
                        )
                    success_count += 1
                except:
                    pass
        
        # Cleanup
        try:
            await status_msg.delete()
        except:
            pass
        
        try:
            import shutil
            shutil.rmtree(temp_dir_or_error)
        except:
            pass
        
        if success_count == 0:
            await message.reply_text(
                "❌ *Upload Failed*\n\n"
                "Could not send files to Telegram.",
                parse_mode='Markdown'
            )
    
    except Exception as e:
        error_message = str(e)
        print(f"Instagram download error: {error_message}")
        
        try:
            await status_msg.edit_text(
                f"❌ *Error Occurred*\n\n"
                f"```\n{error_message[:150]}\n```",
                parse_mode='Markdown'
            )
        except:
            pass


# Register handlers
application.add_handler(CommandHandler(["ig", "insta", "instagram"], ig_download))