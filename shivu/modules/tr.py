import re
import asyncio
import aiohttp
from pathlib import Path
from telegram import Update
from telegram.ext import MessageHandler, ContextTypes, filters
from shivu import application

class TeraDL:
    REGEX = re.compile(r'(?:terabox\.com|teraboxapp\.com|1024terabox\.com)/(?:s/|sharing/link\?surl=)([A-Za-z0-9_-]+)')
    API = "https://terabox-dl.qtcloud.workers.dev/api/get-info"
    
    @staticmethod
    async def fetch(url: str) -> dict | None:
        async with aiohttp.ClientSession() as s:
            try:
                async with s.post(TeraDL.API, json={"url": url}, timeout=30) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data.get("ok"):
                            return data.get("response", [{}])[0]
            except:
                pass
        return None
    
    @staticmethod
    async def dl(url: str, path: str):
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=300) as r:
                if r.status == 200:
                    with open(path, 'wb') as f:
                        async for chunk in r.content.iter_chunked(8192):
                            f.write(chunk)

async def tera_hdl(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not u.message or not u.message.text or not TeraDL.REGEX.search(u.message.text):
        return
    
    m = await u.message.reply_text("⏳")
    info = await TeraDL.fetch(u.message.text)
    
    if info and info.get("downloadLink"):
        fname = info.get("fileName", "file")
        fsize = info.get("fileSize", 0)
        
        if fsize > 50 * 1024 * 1024:
            await m.edit_text(f"❌ File too large ({fsize / (1024*1024):.1f}MB)")
            return
        
        fpath = f"/tmp/{fname}"
        try:
            await TeraDL.dl(info["downloadLink"], fpath)
            if Path(fpath).exists():
                with open(fpath, 'rb') as f:
                    await u.message.reply_document(f, caption=f"✅ {fname}", read_timeout=120, write_timeout=120)
                Path(fpath).unlink(missing_ok=True)
                await m.delete()
            else:
                await m.edit_text("❌")
        except:
            Path(fpath).unlink(missing_ok=True)
            await m.edit_text("❌")
    else:
        await m.edit_text("❌")

application.add_handler(MessageHandler(filters.TEXT & filters.Regex(TeraDL.REGEX), tera_hdl))
