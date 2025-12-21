import random
import string
from pyrogram import filters
from pyrogram.enums import ParseMode
from Grabber import shivuu as app
from Grabber import user_collection, collection, db

# --- LOGGING CHANNEL ---
LOG_CHANNEL_ID = -1003110990230  
SUDO_USER_IDS = [8420981179, 5147822244]

def generate_random_code():
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    return f"SIYA_{code}"

# --- 1. HTML STYLE GENERATE (/gen) ---
@app.on_message(filters.command(["gen"]))
async def gen(client, message):
    if message.from_user.id not in SUDO_USER_IDS:
        return

    try:
        amount = float(message.command[1])
        quantity = int(message.command[2])
    except:
        return await message.reply_text("<b>Usage:</b> <code>/gen 50000 10</code>", parse_mode=ParseMode.HTML)

    code = generate_random_code()
    await db.generated_codes.insert_one({
        'code': code, 'amount': amount, 'quantity': quantity, 'claimed_by': [], 'type': 'cash'
    })

    # HTML formatted Response
    response = (
        f"<b>✅ CASH CODE GENERATED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"<b>🎫 CODE:</b> <code>{code}</code>\n"
        f"<b>💰 AMOUNT:</b> <code>₩{amount:,.0f}</code>\n"
        f"<b>👥 LIMIT:</b> <code>{quantity} Users</code>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Tap on code to copy!</i>"
    )
    await message.reply_text(response, parse_mode=ParseMode.HTML)

# --- 2. HTML STYLE REDEEM (/redeem) ---
@app.on_message(filters.command(["redeem"]))
async def redeem(client, message):
    if len(message.command) < 2:
        return

    code = message.command[1].strip()
    user = message.from_user
    data = await db.generated_codes.find_one({'code': code})

    if not data or len(data['claimed_by']) >= data['quantity']:
        return await message.reply_text("<b>❌ Invalid or Expired Code!</b>", parse_mode=ParseMode.HTML)

    if user.id in data['claimed_by']:
        return await message.reply_text("<b>❌ Already Claimed!</b>", parse_mode=ParseMode.HTML)

    await user_collection.update_one({'id': user.id}, {'$inc': {'balance': data['amount']}})
    await db.generated_codes.update_one({'code': code}, {'$push': {'claimed_by': user.id}})

    await message.reply_text(
        f"<b>🎉 REDEEMED SUCCESSFULLY!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"<b>👤 USER:</b> {user.mention}\n"
        f"<b>💰 ADDED:</b> <code>₩{data['amount']:,.0f}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━",
        parse_mode=ParseMode.HTML
    )
