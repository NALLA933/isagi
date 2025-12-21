import random
import string
import logging
from pyrogram import Client, filters
from pyrogram.enums import ParseMode

# Isagi repo ke structure ke hisab se sahi imports
from Grabber import shivuu as app
from Grabber import user_collection, collection, db

# --- LOGGING SETUP ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Config
LOG_CHANNEL_ID = -1003110990230  # Aapka channel ID
AUTHORIZED_USERS = [8420981179, 5147822244] 

# Database collections
codes_db = db.generated_codes 

def generate_random_code():
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    return f"@siyaprobot_{code}"

# --- 1. CASH GENERATE (/gen) ---
@app.on_message(filters.command(["gen"]))
async def gen(client, message):
    if message.from_user.id not in AUTHORIZED_USERS:
        return

    try:
        amount = float(message.command[1])
        quantity = int(message.command[2])
    except (IndexError, ValueError):
        await message.reply_text("⚠️ Usage: `/gen 50000 10` (Amount Qty)")
        return

    code = generate_random_code()

    await codes_db.insert_one({
        'code': code,
        'amount': amount,
        'quantity': quantity,
        'claimed_by': [],
        'type': 'cash'
    })

    amt_str = f"{amount:,.0f}"
    await message.reply_text(f"✅ **Cash Code:** `{code}`\n💰 **Amt:** ₩{amt_str}\n👥 **Qty:** {quantity}")

    # Channel Log
    await client.send_message(LOG_CHANNEL_ID, f"🎁 #GEN_CASH\n**Admin:** {message.from_user.mention}\n**Code:** `{code}`\n**Amt:** ₩{amt_str}")

# --- 2. WAIFU GENERATE (/sgen) ---
@app.on_message(filters.command(["sgen"]))
async def waifugen(client, message):
    if message.from_user.id not in AUTHORIZED_USERS:
        return

    try:
        char_id = message.command[1]
        quantity = int(message.command[2])
    except (IndexError, ValueError):
        await message.reply_text("⚠️ Usage: `/sgen [ID] [Qty]`")
        return

    waifu = await collection.find_one({'id': char_id})
    if not waifu:
        await message.reply_text("❌ Character not found.")
        return

    code = generate_random_code()
    await codes_db.insert_one({
        'code': code, 'char_id': char_id, 'quantity': quantity,
        'claimed_by': [], 'type': 'waifu'
    })

    await message.reply_text(f"✅ **Waifu Code:** `{code}`\n👤 **Name:** {waifu['name']}")
    
    # Channel Log
    await client.send_message(LOG_CHANNEL_ID, f"🌸 #GEN_WAIFU\n**Admin:** {message.from_user.mention}\n**Char:** {waifu['name']}\n**Code:** `{code}`")

# --- 3. REDEEM CASH (/redeem) ---
@app.on_message(filters.command(["redeem"]))
async def redeem(client, message):
    if len(message.command) < 2:
        await message.reply_text("⚠️ Usage: `/redeem @siyaprobot_code`")
        return
        
    code = message.command[1].strip()
    user_id = message.from_user.id

    code_info = await codes_db.find_one({'code': code, 'type': 'cash'})
    
    if not code_info:
        await message.reply_text("❌ Invalid code.")
        return

    if user_id in code_info['claimed_by'] or len(code_info['claimed_by']) >= code_info['quantity']:
        await message.reply_text("❌ Expired ya pehle hi claim ho chuka hai.")
        return

    # Update balance in user_collection (Isagi repo schema)
    await user_collection.update_one({'id': user_id}, {'$inc': {'balance': code_info['amount']}})
    await codes_db.update_one({'code': code}, {'$push': {'claimed_by': user_id}})

    await message.reply_text(f"🎉 Success! `₩{code_info['amount']:,.0f}` added.")
    await client.send_message(LOG_CHANNEL_ID, f"💰 #CLAIM_CASH\n**User:** {message.from_user.mention}\n**Amt:** ₩{code_info['amount']:,.0f}\n**Code:** `{code}`")

# --- 4. REDEEM WAIFU (/sredeem) ---
@app.on_message(filters.command(["sredeem"]))
async def sredeem(client, message):
    if len(message.command) < 2: return
    
    code = message.command[1].strip()
    user_id = message.from_user.id

    data = await codes_db.find_one({'code': code, 'type': 'waifu'})
    if not data or user_id in data['claimed_by'] or len(data['claimed_by']) >= data['quantity']:
        await message.reply_text("❌ Invalid/Expired.")
        return

    waifu = await collection.find_one({'id': data['char_id']})
    # Isagi repo harem structure: '$push': {'characters': waifu}
    await user_collection.update_one({'id': user_id}, {'$push': {'characters': waifu}})
    await codes_db.update_one({'code': code}, {'$push': {'claimed_by': user_id}})

    await message.reply_photo(waifu['img_url'], caption=f"🎉 **{waifu['name']}** successfully claimed!")
    await client.send_message(LOG_CHANNEL_ID, f"🌸 #CLAIM_WAIFU\n**User:** {message.from_user.mention}\n**Char:** {waifu['name']}\n**Code:** `{code}`")

# --- 5. ACTIVE CODES (/activecodes) ---
@app.on_message(filters.command(["activecodes"]))
async def activecodes(client, message):
    if message.from_user.id not in AUTHORIZED_USERS: return
    
    res = "📜 **Active Codes:**\n\n"
    cursor = codes_db.find({})
    async for c in cursor:
        left = c['quantity'] - len(c['claimed_by'])
        if left > 0:
            res += f"• `{c['code']}` | ({left} Left)\n"
    
    await message.reply_text(res)
