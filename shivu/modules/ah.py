import re
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import instaloader
from telegram import Update, InputFile
from telegram.ext import MessageHandler, ContextTypes, filters
from shivu import application

class IGDl:
    REGEX = re.compile(r'instagram\.com/(?:p|reel|reels)/([A-Za-z0-9_-]+)')
    
    @staticmethod
    async def get_video(url: str) -> str | None:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, IGDl._download, url)
    
    @staticmethod
    def _download(url: str) -> str | None:
        match = IGDl.REGEX.search(url)
        if not match:
            return None
        
        shortcode = match.group(1)
        loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False
        )
        
        try:
            with TemporaryDirectory() as tmpdir:
                post = instaloader.Post.from_shortcode(loader.context, shortcode)
                if post.is_video:
                    loader.download_post(post, target=tmpdir)
                    video_file = next(Path(tmpdir).glob("*.mp4"), None)
                    if video_file:
                        return str(video_file)
        except:
            pass
        return None

async def ig_hdl(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not u.message or not u.message.text or not IGDl.REGEX.search(u.message.text):
        return
    
    m = await u.message.reply_text("⏳")
    v = await IGDl.get_video(u.message.text)
    
    if v:
        try:
            with open(v, 'rb') as vf:
                await u.message.reply_video(vf, caption="✅", read_timeout=60, write_timeout=60)
            await m.delete()
        except:
            await m.edit_text("❌")
    else:
        await m.edit_text("❌")

application.add_handler(MessageHandler(filters.TEXT & filters.Regex(IGDl.REGEX) & filters.ChatType.PRIVATE, ig_hdl))
