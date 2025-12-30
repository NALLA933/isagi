import re
import asyncio
import aiohttp
from pathlib import Path
from telegram import Update
from telegram.ext import MessageHandler, ContextTypes, filters
from shivu import application

class TeraDL:
    REGEX = re.compile(r'(?:terabox\.com|teraboxapp\.com|1024terabox\.com)/(?:s/|sharing/link\?surl=)([A-Za-z0-9_-]+)')
    
    # Multiple API endpoints as fallbacks
    APIS = [
        {
            "name": "API 1 (terabox-dl)",
            "url": "https://terabox-dl.qtcloud.workers.dev/api/get-info",
            "type": "post_json"
        },
        {
            "name": "API 2 (teraboxvideodownloader)",
            "url": "https://teraboxvideodownloader.nepcoderdevs.workers.dev/",
            "type": "post_json"
        },
        {
            "name": "API 3 (teradl-api)",
            "url": "https://teradl-api.deno.dev/download",
            "type": "get_params"
        }
    ]

    @staticmethod
    async def fetch_api1(session: aiohttp.ClientSession, url: str) -> dict | None:
        """API 1: terabox-dl format"""
        try:
            async with session.post(
                TeraDL.APIS[0]["url"],
                json={"url": url},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    if data.get("ok"):
                        response = data.get("response", [{}])[0]
                        return {
                            "fileName": response.get("fileName"),
                            "fileSize": response.get("fileSize"),
                            "downloadLink": response.get("downloadLink")
                        }
        except Exception as e:
            print(f"API 1 failed: {e}")
        return None

    @staticmethod
    async def fetch_api2(session: aiohttp.ClientSession, url: str) -> dict | None:
        """API 2: alternative format"""
        try:
            async with session.post(
                TeraDL.APIS[1]["url"],
                json={"url": url},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    if data.get("response"):
                        files = data["response"]
                        if files and len(files) > 0:
                            file = files[0]
                            return {
                                "fileName": file.get("resolutions", {}).get("Fast Download", {}).get("file_name") or file.get("file_name"),
                                "fileSize": file.get("size", 0),
                                "downloadLink": file.get("resolutions", {}).get("Fast Download", {}).get("url")
                            }
        except Exception as e:
            print(f"API 2 failed: {e}")
        return None

    @staticmethod
    async def fetch_api3(session: aiohttp.ClientSession, url: str) -> dict | None:
        """API 3: GET params format"""
        try:
            async with session.get(
                TeraDL.APIS[2]["url"],
                params={"url": url},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    if data.get("download_link"):
                        return {
                            "fileName": data.get("file_name", "file"),
                            "fileSize": data.get("file_size", 0),
                            "downloadLink": data.get("download_link")
                        }
        except Exception as e:
            print(f"API 3 failed: {e}")
        return None

    @staticmethod
    async def fetch(url: str) -> dict | None:
        """Try all APIs in sequence until one works"""
        async with aiohttp.ClientSession() as session:
            # Try API 1
            result = await TeraDL.fetch_api1(session, url)
            if result and result.get("downloadLink"):
                return result
            
            # Try API 2
            result = await TeraDL.fetch_api2(session, url)
            if result and result.get("downloadLink"):
                return result
            
            # Try API 3
            result = await TeraDL.fetch_api3(session, url)
            if result and result.get("downloadLink"):
                return result
        
        return None

    @staticmethod
    async def dl(url: str, path: str):
        """Download file from URL"""
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as r:
                if r.status == 200:
                    with open(path, 'wb') as f:
                        async for chunk in r.content.iter_chunked(8192):
                            f.write(chunk)

async def tera_hdl(u: Update, c: ContextTypes.DEFAULT_TYPE):
    """Handle Terabox link messages"""
    if not u.message or not u.message.text or not TeraDL.REGEX.search(u.message.text):
        return

    m = await u.message.reply_text("⏳ Processing...")
    
    try:
        info = await TeraDL.fetch(u.message.text)

        if info and info.get("downloadLink"):
            fname = info.get("fileName", "file")
            fsize = info.get("fileSize", 0)

            # Convert file size to MB if it's in bytes
            if isinstance(fsize, int):
                fsize_mb = fsize / (1024 * 1024)
            else:
                # Try to parse if it's a string like "125.50 MB"
                try:
                    fsize_str = str(fsize).replace("MB", "").replace("GB", "").strip()
                    fsize_mb = float(fsize_str)
                    if "GB" in str(fsize):
                        fsize_mb *= 1024
                except:
                    fsize_mb = 0

            # File size limit check (50MB)
            if fsize_mb > 50:
                await m.edit_text(f"❌ File too large ({fsize_mb:.1f}MB)\nMax: 50MB")
                return

            await m.edit_text(f"📥 Downloading: {fname}\nSize: {fsize_mb:.1f}MB")
            
            fpath = f"/tmp/{fname}"
            try:
                await TeraDL.dl(info["downloadLink"], fpath)
                
                if Path(fpath).exists():
                    await m.edit_text(f"📤 Uploading...")
                    with open(fpath, 'rb') as f:
                        await u.message.reply_document(
                            f,
                            caption=f"✅ {fname}",
                            read_timeout=120,
                            write_timeout=120
                        )
                    Path(fpath).unlink(missing_ok=True)
                    await m.delete()
                else:
                    await m.edit_text("❌ Download failed")
            except Exception as e:
                Path(fpath).unlink(missing_ok=True)
                await m.edit_text(f"❌ Error: {str(e)[:100]}")
        else:
            await m.edit_text("❌ Could not fetch download link\nAll APIs failed")
    except Exception as e:
        await m.edit_text(f"❌ Error: {str(e)[:100]}")

# Register handler
application.add_handler(MessageHandler(filters.TEXT & filters.Regex(TeraDL.REGEX), tera_hdl))