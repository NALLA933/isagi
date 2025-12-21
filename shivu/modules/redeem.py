import random
import string
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from shivu import user_collection, collection, db, shivuu as app

# --- CONFIGURATION ---
LOG_CHANNEL_ID = -1003110990230  
SUDO_USER_IDS = [8420981179, 5147822244]

# Database collections
codes_db = db.redeem_codes  
waifu_codes_db = db.waifu_codes 

# --- HELPER ---
def generate_random_code():
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    return f"@siyaprobot_{code}"

# --- ACTIVE CODES COMMAND (/activecodes) ---
@app.on_message(filters.command(["activecodes"]))
async def active_codes(client, message):
    if message.from_user.id not in SUDO_USER_IDS:
        return

    # 1. Fetch Cash Codes
    cash_cursor = codes_db.find({})
    cash_codes = await cash_cursor.to_list(length=100)
    
    # 2. Fetch Waifu Codes
    waifu_cursor = waifu_codes_db.find({})
    waifu_codes = await waifu_cursor.to_list(length=100)

    response = "📜 **ᴀʟʟ ᴀᴄᴛɪᴠᴇ ʀᴇᴅᴇᴇᴍ ᴄᴏᴅᴇs**\n\n"

    # Cash Section
    response += "💰 **ᴄᴀsʜ ᴄᴏᴅᴇs:**\n"
    cash_found = False
    for c in cash_codes:
        left = c['quantity'] - len(c['claimed_by'])
        if left > 0:
            response += f"• `{c['code']}` | ₩{c['amount']:,.0f} | ({left} ʟᴇғᴛ)\n"
            cash_found = True
    if not cash_found: response += "• _No active cash codes_\n"

    response += "\n🌸 **ᴡᴀɪғᴜ ᴄᴏᴅᴇs:**\n"
    waifu_found = False
    for w in waifu_codes:
        left = w.get('qty', 0) - len(w.get('claimed', []))
        if left > 0:
            # Waifu ka naam nikaalne ke liye
            char = await collection.find_one({'id': w['char_id']})
            name = char['name'] if char else "Unknown"
            response += f"• `{w['code']}` | {name} | ({left} ʟᴇғᴛ)\n"
            waifu_found = True
    if not waifu_found: response += "• _No active waifu codes_\n"

    await message.reply_text(response)

# --- DELETE CODE COMMAND (/delcode) ---
@app.on_message(filters.command(["delcode"]))
async def delete_code(client, message):
    if message.from_user.id not in SUDO_USER_IDS:
        return

    if len(message.command) < 2:
        await message.reply_text("⚠️ Usage: `/delcode @siyaprobot_XXXX`")
        return

    target_code = message.command[1].strip()
    
    # Dono DBs se delete karne ki koshish karein
    res1 = await codes_db.delete_one({'code': target_code})
    res2 = await waifu_codes_db.delete_one({'code': target_code})

    if res1.deleted_count > 0 or res2.deleted_count > 0:
        await message.reply_text(f"✅ Code `{target_code}` successfully delete kar diya gaya hai.")
        await client.send_message(LOG_CHANNEL_ID, f"🗑️ #DELETE_CODE\n**Admin:** {message.from_user.mention}\n**Code:** `{target_code}`")
    else:
        await message.reply_text("❌ Yeh code database mein nahi mila.")

# --- Baki Commands (Gen/Redeem) wahi rahengi jo pehle thin ---
