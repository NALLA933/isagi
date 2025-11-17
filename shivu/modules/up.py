import re
import os
import tempfile
import asyncio
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from shivu import application

# Install instaloader if not already: pip install instaloader
try:
    import instaloader
except ImportError:
    print("ERROR: Please install instaloader: pip install instaloader")
    instaloader = None

async def download_instagram_media(url: str):
    """
    Download Instagram media using Instaloader library
    Returns list of file paths
    """
    if not instaloader:
        return None, "Instaloader library not installed"
    
    try:
        # Extract shortcode from URL
        shortcode_match = re.search(r'(?:p|reel|tv)/([A-Za-z0-9_-]+)', url)
        if not shortcode_match:
            return None, "Invalid Instagram URL format"
        
        shortcode = shortcode_match.group(1)
        
        # Create Instaloader instance
        L = instaloader.Instaloader(
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            post_metadata_txt_pattern='',
        )
        
        # Create temporary directory for downloads
        temp_dir = tempfile.mkdtemp()
        
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        
        def download_post():
            try:
                # Get post from shortcode
                post = instaloader.Post.from_shortcode(L.context, shortcode)
                
                # Download post
                L.download_post(post, target=temp_dir)
                
                # Collect downloaded files
                files = []
                for filename in os.listdir(temp_dir):
                    if filename.endswith(('.jpg', '.png', '.mp4', '.webp')):
                        full_path = os.path.join(temp_dir, filename)
                        
                        # Determine file type
                        if filename.endswith('.mp4'):
                            file_type = 'video'
                        else:
                            file_type = 'photo'
                        
                        files.append({
                            'type': file_type,
                            'path': full_path
                        })
                
                return files, None
            except instaloader.exceptions.InstaloaderException as e:
                return None, str(e)
            except Exception as e:
                return None, str(e)
        
        # Execute download in thread pool
        files, error = await loop.run_in_executor(None, download_post)
        
        if error:
            # Cleanup temp directory
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
    
    if not instaloader:
        await message.reply_text(
            "❌ *Service Unavailable*\n\n"
            "Instagram downloader is not properly configured.\n"
            "Please contact the bot administrator.",
            parse_mode='Markdown'
        )
        return
    
    if not context.args:
        await message.reply_text(
            "📸 *Instagram Downloader*\n\n"
            "*Usage:* `/ig <instagram_url>`\n\n"
            "*Examples:*\n"
            "• `/ig https://www.instagram.com/p/ABC123/`\n"
            "• `/ig https://www.instagram.com/reel/XYZ789/`\n\n"
            "*Supported:*\n"
            "✅ Posts (single/multiple images)\n"
            "✅ Videos & Reels\n"
            "✅ Public accounts only\n\n"
            "*Note:* Private accounts are not supported",
            parse_mode='Markdown'
        )
        return
    
    url = context.args[0]
    
    # Validate Instagram URL
    if not re.search(r'instagram\.com/(p|reel|tv)/[A-Za-z0-9_-]+', url):
        await message.reply_text(
            "❌ *Invalid URL*\n\n"
            "Please provide a valid Instagram post, reel, or video link.\n\n"
            "*Example:* `https://www.instagram.com/p/ABC123/`",
            parse_mode='Markdown'
        )
        return
    
    status_msg = await message.reply_text(
        "⏳ *Downloading...*\n\nThis may take a few seconds...",
        parse_mode='Markdown'
    )
    
    try:
        # Download media
        files, temp_dir_or_error = await download_instagram_media(url)
        
        if files is None:
            error_msg = temp_dir_or_error
            
            # Provide helpful error messages
            if "not found" in error_msg.lower() or "404" in error_msg:
                await status_msg.edit_text(
                    "❌ *Post Not Found*\n\n"
                    "The post may have been deleted or the URL is incorrect.\n"
                    "Please check the link and try again.",
                    parse_mode='Markdown'
                )
            elif "private" in error_msg.lower() or "login" in error_msg.lower():
                await status_msg.edit_text(
                    "❌ *Private Account*\n\n"
                    "This post is from a private account.\n"
                    "Only public posts can be downloaded.",
                    parse_mode='Markdown'
                )
            elif "rate" in error_msg.lower() or "limit" in error_msg.lower():
                await status_msg.edit_text(
                    "❌ *Rate Limited*\n\n"
                    "Instagram has temporarily blocked our requests.\n"
                    "Please try again in a few minutes.",
                    parse_mode='Markdown'
                )
            else:
                await status_msg.edit_text(
                    f"❌ *Download Failed*\n\n"
                    f"Error: `{error_msg[:100]}`\n\n"
                    "Please try again later.",
                    parse_mode='Markdown'
                )
            return
        
        if not files:
            await status_msg.edit_text(
                "❌ *No Media Found*\n\n"
                "No downloadable media was found in this post.",
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
                # Try sending as document
                try:
                    with open(item['path'], 'rb') as doc_file:
                        await message.reply_document(
                            document=doc_file,
                            caption=f"📎 Media {idx} ({item['type']})"
                        )
                    success_count += 1
                except Exception as doc_error:
                    print(f"Failed to send file as document: {doc_error}")
        
        # Delete status message
        try:
            await status_msg.delete()
        except:
            pass
        
        # Cleanup temporary files
        try:
            import shutil
            shutil.rmtree(temp_dir_or_error)
        except Exception as cleanup_error:
            print(f"Cleanup error: {cleanup_error}")
        
        if success_count == 0:
            await message.reply_text(
                "❌ *Upload Failed*\n\n"
                "Could not send the downloaded files.\n"
                "They may be too large or in an unsupported format.",
                parse_mode='Markdown'
            )
    
    except Exception as e:
        error_message = str(e)
        print(f"Instagram download error: {error_message}")
        
        try:
            await status_msg.edit_text(
                f"❌ *An Error Occurred*\n\n"
                f"```\n{error_message[:150]}\n```\n\n"
                "Please try again later.",
                parse_mode='Markdown'
            )
        except:
            pass


# Register command handlers
application.add_handler(CommandHandler(["ig", "insta", "instagram"], ig_download))