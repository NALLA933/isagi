import random
import string
import logging
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from Grabber import user_collection, collection, db

# --- LOGGING SETUP ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Authorized IDs (Yahan aap manually IDs add kar sakte hain)
AUTHORIZED_USERS = [8420981179, 5147822244, 123456789] 

codes_db = db.generated_codes 

def generate_random_code():
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    return f"@siyaprobot_{code}"

# --- 1. CASH GENERATE (/gen) ---
@app.on_message(filters.command(["gen"]))
async def gen(client, message):
    user_id = message.from_user.id
    
    # Manual ID Check
    if user_id not in AUTHORIZED_USERS:
        await message.reply_text("❌ Unauthorized! Aapke paas access nahi hai.")
        return

    try:
        amount = float(message.command[1])
        quantity = int(message.command[2])
    except (IndexError, ValueError):
        await message.reply_text("⚠️ Usage: `/gen 50000 10` (Amount Qty)")
        return

    code = generate_random_code()

    # Save to Database
    await codes_db.insert_one({
        'code': code,
        'amount': amount,
        'quantity': quantity,
        'claimed_by': [],
        'type': 'cash'
    })

    # LOG PRINT (Terminal mein dikhega)
    print(f">>> [GENLOG] Admin: {message.from_user.first_name} ({user_id}) generated code {code} for ₩{amount}")
    logger.info(f"GEN: {user_id} generated {code}")

    await message.reply_text(
        f"✅ **Cash Code Generated!**\n\n"
        f"🎫 **Code:** `{code}`\n"
        f"💰 **Amount:** `₩{amount:,.0f}`\n"
        f"👥 **Quantity:** `{quantity}`"
    )

# --- 2. WAIFU GENERATE (/sgen) ---
@app.on_message(filters.command(["sgen"]))
async def waifugen(client, message):
    user_id = message.from_user.id
    
    if user_id not in AUTHORIZED_USERS:
        return

    try:
        char_id = message.command[1]
        quantity = int(message.command[2])
    except (IndexError, ValueError):
        await message.reply_text("⚠️ Usage: `/sgen [CharID] [Qty]`")
        return

    waifu = await collection.find_one({'id': char_id})
    if not waifu:
        await message.reply_text("❌ Character ID invalid hai.")
        return

    code = generate_random_code()
    
    await codes_db.insert_one({
        'code': code,
        'char_id': char_id,
        'quantity': quantity,
        'claimed_by': [],
        'type': 'waifu'
    })

    # LOG PRINT
    print(f">>> [SGENLOG] Admin: {user_id} generated Waifu Code {code} for {waifu['name']}")

    await message.reply_text(
        f"✅ **Waifu Code Generated!**\n\n"
        f"🎫 **Code:** `{code}`\n"
        f"👤 **Name:** {waifu['name']}\n"
        f"👥 **Quantity:** {quantity}"
    )

# --- 3. REDEEM LOGIC (With Logging) ---
@app.on_message(filters.command(["redeem"]))
async def redeem(client, message):
    user_id = message.from_user.id
    code = message.command[1] if len(message.command) > 1 else ""

    code_info = await codes_db.find_one({'code': code, 'type': 'cash'})
    if not code_info:
        await message.reply_text("❌ Invalid code.")
        return

    if user_id in code_info['claimed_by']:
        await message.reply_text("❌ Aap pehle hi claim kar chuke hain.")
        return

    if len(code_info['claimed_by']) >= code_info['quantity']:
        await message.reply_text("❌ Code limit khatam ho gayi hai.")
        return

    # Update Balance and DB
    await user_collection.update_one({'id': user_id}, {'$inc': {'balance': code_info['amount']}})
    await codes_db.update_one({'code': code}, {'$push': {'claimed_by': user_id}})

    # LOG PRINT
    print(f">>> [CLAIM] User: {message.from_user.first_name} ({user_id}) redeemed {code} for ₩{code_info['amount']}")

    await message.reply_text(f"🎉 Success! `₩{code_info['amount']}` aapke wealth mein add kar diye gaye hain.")
