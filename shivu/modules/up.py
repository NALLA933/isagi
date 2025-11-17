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
            except:
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
    if not context.args:
        return
    
    url = context.args[0]
    media = await get_ig_media(url)
    
    if not media:
        return
    
    for item in media:
        try:
            if item['type'] == 'video':
                await update.message.reply_video(item['url'])
            else:
                await update.message.reply_photo(item['url'])
        except:
            pass

# Add handlers
application.add_handler(CommandHandler(["ig", "insta"], ig_download))