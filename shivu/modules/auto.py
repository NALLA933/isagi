import io
import base64
import json
import re
import aiohttp
from PIL import Image
from pymongo import ReturnDocument
from telegram import Update, InputFile
from telegram.ext import MessageHandler, filters, ContextTypes

from shivu import application, db, collection, CHARA_CHANNEL_ID

AUTHORIZED_USER = 5147822244


# ---------------------------- RARITY ----------------------------

def get_rarity(score: float):
    if score >= 0.90: return "🏵 Mythic"
    if score >= 0.80: return "🔮 Premium"
    if score >= 0.70: return "🎐 Celestial"
    if score >= 0.60: return "✨ Manga"
    if score >= 0.50: return "💫 Neon"
    if score >= 0.40: return "💮 Special"
    if score >= 0.30: return "🟡 Legendary"
    return "🟣 Rare"


# ---------------------------- CHARACTER IDENTIFY ----------------------------

async def identify_character(img_bytes: bytes):
    b64 = base64.b64encode(img_bytes).decode()

    prompt = """Identify this anime character. Return ONLY JSON like:
{"name":"Gojo Satoru", "anime":"Jujutsu Kaisen"}"""

    payload = {
        "model": "gpt-4o-mini",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]
        }],
        "max_tokens": 300
    }

    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.shuttleai.app/v1/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer shuttle-free-api-key"},
                timeout=20
            ) as r:
                data = await r.json()
                content = data["choices"][0]["message"]["content"]

                match = re.search(r"\{.*\}", content)
                return json.loads(match.group()) if match else None

    except:
        return None


# ---------------------------- QUALITY SCORE ----------------------------

def analyze_quality(img_bytes: bytes):
    try:
        img = Image.open(io.BytesIO(img_bytes)).convert("L")
        w, h = img.size

        # Resolution
        mp = (w * h) / 1_000_000
        score = min(1.0, mp / 2)

        return round(score, 2)
    except:
        return 0.4


# ---------------------------- AUTO ID GENERATOR ----------------------------

async def next_id():
    doc = await db.sequences.find_one_and_update(
        {"_id": "character_id"},
        {"$inc": {"sequence_value": 1}},
        return_document=ReturnDocument.AFTER,
        upsert=True
    )
    return str(doc["sequence_value"]).zfill(4)


# ---------------------------- MAIN HANDLER ----------------------------

async def auto_upload(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED_USER:
        return await update.message.reply_text("❌ Unauthorized")

    msg = await update.message.reply_text("⏳ Processing...")

    photo = update.message.photo[-1]
    file_bytes = bytes(await (await photo.get_file()).download_as_bytearray())

    # Identify character
    info = await identify_character(file_bytes)
    if not info:
        return await msg.edit_text("❌ Could not detect character")

    name = info.get("name", "Unknown")
    anime = info.get("anime", "Unknown")

    # Quality → rarity
    score = analyze_quality(file_bytes)
    rarity = get_rarity(score)

    # ID
    char_id = await next_id()

    # Upload to Telegram channel
    caption = (
        f"🆔 <code>{char_id}</code>\n"
        f"👤 {name}\n"
        f"📺 {anime}\n"
        f"{rarity}\n"
        f"⭐ Quality: {score}"
    )

    file_obj = io.BytesIO(file_bytes)
    file_obj.name = f"{char_id}.jpg"

    sent = await ctx.bot.send_photo(
        CHARA_CHANNEL_ID,
        photo=InputFile(file_obj),
        caption=caption,
        parse_mode="HTML"
    )

    # Save to DB
    await collection.insert_one({
        "id": char_id,
        "name": name,
        "anime": anime,
        "rarity": rarity,
        "quality": score,
        "file_id": sent.photo[-1].file_id
    })

    await msg.edit_text(f"✅ Uploaded!\nID: <code>{char_id}</code>", parse_mode="HTML")


# Register
application.add_handler(MessageHandler(filters.PHOTO & filters.User(AUTHORIZED_USER), auto_upload))
print("Auto upload active!")