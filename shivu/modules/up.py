import re
import aiohttp
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from shivu import application

async def get_ig_media(url: str):
    apis = [
        ("https://v3.saveinsta.app/api/ajaxSearch", {"q": url, "t": "media", "lang": "en"}),
        ("https://downloadgram.org/reel-downloader.php", {"url": url, "submit": ""}),
    ]
    
    async with aiohttp.ClientSession() as session:
        for api_url, data in apis:
            try:
                async with session.post(api_url, data=data, timeout=15) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        
                        if result.get('data'):
                            html = result['data']
                            video_match = re.search(r'href="([^"]+)".*?download', html)
                            if video_match:
                                return [{'type': 'video', 'url': video_match.group(1)}]
                            
                            img_match = re.findall(r'href="([^"]+\.jpg[^"]*)"', html)
                            if img_match:
                                return [{'type': 'photo', 'url': img} for img in img_match[:5]]
            except Exception as e:
                continue
        
        try:
            async with session.get(f"https://insta.savetube.me/downloadgram?url={url}", timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('url'):
                        return [{'type': 'video', 'url': data['url']}]
        except:
            pass
    
    return None

async def ig_download(update: Update, context: CallbackContext):
    message = update.message
    
    if not context.args:
        await message.reply_text("Please provide an Instagram URL.\nUsage: /ig <instagram_url>")
        return
    
    url = context.args[0]
    
    status_msg = await message.reply_text("Downloading...")
    
    try:
        media = await get_ig_media(url)
        
        if not media:
            await status_msg.edit_text("Failed to download. Please check the URL and try again.")
            return
        
        await status_msg.delete()
        
        for item in media:
            try:
                if item['type'] == 'video':
                    await message.reply_video(item['url'])
                else:
                    await message.reply_photo(item['url'])
            except Exception as e:
                await message.reply_text(f"Error sending media: {str(e)}")
    
    except Exception as e:
        await status_msg.edit_text(f"An error occurred: {str(e)}")

# Add handler
application.add_handler(CommandHandler(["ig", "insta"], ig_download))