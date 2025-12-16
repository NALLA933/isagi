import re
import aiohttp
from telegram import Update
from telegram.ext import MessageHandler, ContextTypes, filters
from shivu import application

class IGDownloader:
    REGEX = re.compile(r'instagram\.com/(?:p|reel|reels)/([A-Za-z0-9_-]+)')
    
    @staticmethod
    async def fetch(url: str) -> str | None:
        async with aiohttp.ClientSession() as s:
            try:
                async with s.post("https://v3.saveig.app/api/ajaxSearch", 
                                   data={"q": url, "t": "media", "lang": "en"}, 
                                   timeout=30) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data.get("status") == "ok":
                            html = data.get("data", "")
                            match = re.search(r'href="([^"]+download[^"]+)"', html)
                            return match.group(1) if match else None
            except:
                pass
        return None

async def ig_handler(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not u.message or not u.message.text or not IGDownloader.REGEX.search(u.message.text):
        return
    
    m = await u.message.reply_text("⏳")
    v = await IGDownloader.fetch(u.message.text)
    
    if v:
        try:
            await u.message.reply_video(v, caption="✅", read_timeout=60, write_timeout=60)
            await m.delete()
        except:
            await m.edit_text("❌")
    else:
        await m.edit_text("❌")

application.add_handler(MessageHandler(filters.TEXT & filters.Regex(IGDownloader.REGEX) & filters.ChatType.PRIVATE, ig_handler))
