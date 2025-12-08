import io
import aiohttp
from PIL import Image
from telegram import Update, InputFile
from telegram.ext import MessageHandler, filters, ContextTypes
from pymongo import ReturnDocument

from shivu import application, db, collection, CHARA_CHANNEL_ID

AUTHORIZED = 5147822244  # your ID


# ---------------- RARITY ----------------
def get_rarity(score: float):
    if score >= 0.90: return "🏵 Mythic"
    if score >= 0.80: return "🔮 Premium"
    if score >= 0.70: return "🎐 Celestial"
    if score >= 0.60: return "✨ Manga"
    if score >= 0.50: return "💫 Neon"
    if score >= 0.40: return "💮 Special"
    if score >= 0.30: return "🟡 Legendary"
    return "🟣 Rare"


# ------------ QUALITY SCORE ------------
def img_quality(img_bytes):
    img = Image.open(io.BytesIO(img_bytes)).convert("L")
    w, h = img.size
    mp = (w * h) / 1_000_000
    return min(1.0, round(mp / 2, 2))


# --------- FREE ANIME CHARACTER DETECTION ---------
async def detect_character(img_bytes: bytes):
    url = "https://api-inference.huggingface.co/models/kadirnar/Anime-Character-Recognition"

    async with aiohttp.ClientSession() as s:
        async with s.post(
            url,
            data=img_bytes,
            timeout=20
        ) as r:
            res = await r.json()

            # Result looks like:
            # [{"label": "Satoru Gojo", "score": 0.99}]
            if isinstance(res, list) and len(res) > 0:
                name = res[0].get("label")
                conf = res[0].get("score", 0)
                return name, conf

    return None, 0.0


# ------------ CHARACTER ID GENERATOR ------------
async def next_id():
    doc = await db.sequences.find_one_and_update(
        {"_id": "character_id"},
        {"$inc": {"sequence_value": 1}},
        return_document=ReturnDocument.AFTER,
        upsert=True
    )
    return str(doc["sequence_value"]).zfill(4)


# ------------------ MAIN AUTO UPLOADER ------------------
async def auto_char_upload(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED:
        return

    msg = await update.message.reply_text("⏳ Processing image...")

    photo = update.message.photo[-1]
    file = await photo.get_file()
    img_bytes = await file.download_as_bytearray()

    # Detect character name
    name, conf = await detect_character(img_bytes)

    if not name:
        return await msg.edit_text("❌ Could not detect character name.\nTry clearer image.")

    # Anime is unknown (HuggingFace does only character)
    anime = "Unknown"

    # Rarity
    quality_score = img_quality(img_bytes)
    rarity = get_rarity(quality_score)

    # ID
    char_id = await next_id()

    # Caption
    caption = (
        f"🆔 <code>{char_id}</code>\n"
        f"👤 {name}\n"
        f"📺 {anime}\n"
        f"{rarity}\n"
        f"⭐ Quality: {quality_score}"
    )

    # Upload to channel
    file_obj = io.BytesIO(img_bytes)
    file_obj.name = f"{char_id}.jpg"

    sent = await ctx.bot.send_photo(
        CHARA_CHANNEL_ID,
        photo=InputFile(file_obj),
        caption=caption,
        parse_mode="HTML"
    )

    # Save DB
    await collection.insert_one({
        "id": char_id,
        "name": name,
        "anime": anime,
        "rarity": rarity,
        "quality": quality_score,
        "file_id": sent.photo[-1].file_id
    })

    await msg.edit_text(
        f"✅ **Character Uploaded!**\nID: <code>{char_id}</code>",
        parse_mode="HTML"
    )


# Handler
application.add_handler(
    MessageHandler(filters.PHOTO & filters.User(AUTHORIZED), auto_char_upload)
)