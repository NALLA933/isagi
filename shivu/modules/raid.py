import asyncio
import random
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from shivu.config import Development as Config
from shivu import shivuu, db, user_collection, collection

raid_settings = db['raid_settings']
raid_cooldown = db['raid_cooldown']
active_raids = db['active_raids']

OWNER_ID = [8420981179, 5147822244]
GLOBAL_ID = "global_raid"

RARITY = {
    1: "🟢 Common", 2: "🟣 Rare", 3: "🟡 Legendary", 4: "💮 Special Edition",
    5: "💫 Neon", 6: "✨ Manga", 7: "🎭 Cosplay", 8: "🎐 Celestial",
    9: "🔮 Premium", 10: "💋 Erotic", 11: "🌤 Summer", 12: "☃️ Winter",
    13: "☔️ Monsoon", 14: "💝 Valentine", 15: "🎃 Halloween", 16: "🎄 Christmas",
    17: "🏵 Mythic", 18: "🎗 Events", 19: "🎥 Amv", 20: "👼 Tiny"
}

DEFAULT = {
    "charge": 500, "duration": 30, "cooldown": 5, "rarities": [1,2,3,4,5,6,7,8,9,10],
    "coin_min": 500, "coin_max": 2000, "loss_min": 200, "loss_max": 500,
    "char_chance": 25, "coin_chance": 35, "loss_chance": 20, 
    "nothing_chance": 15, "crit_chance": 5
}


async def get_settings():
    s = await raid_settings.find_one({"_id": GLOBAL_ID})
    if not s:
        s = DEFAULT.copy()
        s["_id"] = GLOBAL_ID
        await raid_settings.insert_one(s)
    return s


async def update_settings(data):
    await raid_settings.update_one({"_id": GLOBAL_ID}, {"$set": data}, upsert=True)


async def check_cooldown(user_id, chat_id):
    cd = await raid_cooldown.find_one({"user": user_id, "chat": chat_id})
    if cd and cd.get("until") and datetime.utcnow() < cd["until"]:
        return False, int((cd["until"] - datetime.utcnow()).total_seconds())
    return True, 0


async def set_cooldown(user_id, chat_id, minutes):
    until = datetime.utcnow() + timedelta(minutes=minutes)
    await raid_cooldown.update_one(
        {"user": user_id, "chat": chat_id},
        {"$set": {"until": until}},
        upsert=True
    )


async def get_user(user_id):
    u = await user_collection.find_one({"id": user_id})
    if not u:
        u = {"id": user_id, "balance": 0, "characters": []}
        await user_collection.insert_one(u)
    return u


async def update_balance(user_id, amount):
    await user_collection.update_one(
        {"id": user_id}, 
        {"$inc": {"balance": amount}}, 
        upsert=True
    )


async def get_character(rarities):
    try:
        chars = await collection.find({"rarity": {"$in": rarities}}).to_list(None)
        if not chars:
            r_str = [RARITY.get(r, f"Rarity {r}") for r in rarities]
            chars = await collection.find({"rarity": {"$in": r_str}}).to_list(None)
        return random.choice(chars) if chars else None
    except:
        return None


async def add_character(user_id, char):
    try:
        r = char.get("rarity")
        if isinstance(r, int):
            r = RARITY.get(r, "🟢 Common")
        data = {
            "id": char.get("id"), "name": char.get("name"),
            "anime": char.get("anime"), "rarity": r,
            "img_url": char.get("img_url", "")
        }
        await user_collection.update_one(
            {"id": user_id}, 
            {"$push": {"characters": data}}, 
            upsert=True
        )
    except:
        pass


async def cleanup(raid_id, chat_id):
    try:
        await active_raids.delete_one({"_id": raid_id})
        await active_raids.delete_many({
            "chat": chat_id,
            "time": {"$lt": datetime.utcnow() - timedelta(minutes=10)}
        })
    except:
        pass


@shivuu.on_message(filters.command("raid") & filters.group)
async def start_raid(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    existing = await active_raids.find_one({"chat": chat_id, "active": True})
    if existing:
        elapsed = (datetime.utcnow() - existing.get("time", datetime.utcnow())).total_seconds()
        if elapsed > 300:
            await cleanup(existing.get("_id"), chat_id)
        else:
            return await message.reply_text("⚠️ ᴀ ʀᴀɪᴅ ɪs ᴀʟʀᴇᴀᴅʏ ᴀᴄᴛɪᴠᴇ!")
    
    cfg = await get_settings()
    
    can, rem = await check_cooldown(user_id, chat_id)
    if not can:
        m, s = rem // 60, rem % 60
        return await message.reply_text(f"⏳ ᴄᴏᴏʟᴅᴏᴡɴ: `{m}m {s}s`")
    
    user = await get_user(user_id)
    if user.get("balance", 0) < cfg["charge"]:
        return await message.reply_text(
            f"💰 ɴᴇᴇᴅ `{cfg['charge']}` ᴄᴏɪɴs ᴛᴏ sᴛᴀʀᴛ ʀᴀɪᴅ"
        )
    
    await update_balance(user_id, -cfg["charge"])
    
    raid_id = f"{chat_id}_{int(datetime.utcnow().timestamp() * 1000)}"
    await active_raids.insert_one({
        "_id": raid_id, "chat": chat_id, "starter": user_id,
        "users": [user_id], "time": datetime.utcnow(), "active": True
    })
    await set_cooldown(user_id, chat_id, cfg["cooldown"])
    
    text = (
        f"<blockquote>⚔️ <b>sʜᴀᴅᴏᴡ ʀᴀɪᴅ ʙᴇɢɪɴs!</b> ⚔️</blockquote>\n\n"
        f"<code>ᴊᴏɪɴ ɴᴏᴡ ᴀɴᴅ ᴄᴏʟʟᴇᴄᴛ ᴛʀᴇᴀsᴜʀᴇs!</code>\n\n"
        f"⏱ <b>ᴛɪᴍᴇ:</b> <code>{cfg['duration']}s</code>\n"
        f"💰 <b>ғᴇᴇ:</b> <code>{cfg['charge']} ᴄᴏɪɴs</code>\n"
        f"👥 <b>ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs:</b> <code>1</code>\n\n"
        f"━━━━━━━━━━━━━━━\n<i>ʙʏ</i> {message.from_user.mention}"
    )
    
    btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚔️ ᴊᴏɪɴ ʀᴀɪᴅ", callback_data=f"jr:{raid_id}")
    ]])
    
    msg = await message.reply_text(text, reply_markup=btn)
    await asyncio.sleep(cfg["duration"])
    
    check = await active_raids.find_one({"_id": raid_id, "active": True})
    if check:
        await execute_raid(client, msg, raid_id)


@shivuu.on_callback_query(filters.regex(r"^jr:"))
async def join_raid(client, query: CallbackQuery):
    user_id = query.from_user.id
    raid_id = query.data.split(":")[1]
    
    raid = await active_raids.find_one({"_id": raid_id, "active": True})
    if not raid:
        return await query.answer("⚠️ ʀᴀɪᴅ ᴇɴᴅᴇᴅ!", show_alert=True)
    
    if user_id in raid["users"]:
        return await query.answer("✅ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ!")
    
    cfg = await get_settings()
    
    can, rem = await check_cooldown(user_id, raid["chat"])
    if not can:
        m, s = rem // 60, rem % 60
        return await query.answer(f"⏳ ᴄᴏᴏʟᴅᴏᴡɴ: {m}m {s}s", show_alert=True)
    
    user = await get_user(user_id)
    if user.get("balance", 0) < cfg["charge"]:
        return await query.answer(f"💰 ɴᴇᴇᴅ {cfg['charge']} ᴄᴏɪɴs", show_alert=True)
    
    await update_balance(user_id, -cfg["charge"])
    await active_raids.update_one({"_id": raid_id}, {"$push": {"users": user_id}})
    await set_cooldown(user_id, raid["chat"], cfg["cooldown"])
    await query.answer("⚔️ ᴊᴏɪɴᴇᴅ ʀᴀɪᴅ!")
    
    try:
        updated = await active_raids.find_one({"_id": raid_id})
        if not updated:
            return
        
        count = len(updated["users"])
        elapsed = (datetime.utcnow() - raid["time"]).total_seconds()
        left = max(0, int(cfg["duration"] - elapsed))
        
        try:
            starter = await client.get_users(raid["starter"])
            mention = starter.mention
        except:
            mention = "Unknown"
        
        text = (
            f"<blockquote>⚔️ <b>sʜᴀᴅᴏᴡ ʀᴀɪᴅ ʙᴇɢɪɴs!</b> ⚔️</blockquote>\n\n"
            f"<code>ᴊᴏɪɴ ɴᴏᴡ ᴀɴᴅ ᴄᴏʟʟᴇᴄᴛ ᴛʀᴇᴀsᴜʀᴇs!</code>\n\n"
            f"⏱ <b>ᴛɪᴍᴇ:</b> <code>{left}s</code>\n"
            f"💰 <b>ғᴇᴇ:</b> <code>{cfg['charge']} ᴄᴏɪɴs</code>\n"
            f"👥 <b>ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs:</b> <code>{count}</code>\n\n"
            f"━━━━━━━━━━━━━━━\n<i>ʙʏ</i> {mention}"
        )
        
        btn = InlineKeyboardMarkup([[
            InlineKeyboardButton("⚔️ ᴊᴏɪɴ ʀᴀɪᴅ", callback_data=f"jr:{raid_id}")
        ]])
        await query.message.edit_text(text, reply_markup=btn)
    except:
        pass


async def execute_raid(client, message, raid_id):
    raid = await active_raids.find_one({"_id": raid_id, "active": True})
    if not raid:
        return
    
    await active_raids.update_one({"_id": raid_id}, {"$set": {"active": False}})
    
    users = raid["users"]
    cfg = await get_settings()
    
    if not users:
        await message.edit_text("❌ ɴᴏ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs!")
        await cleanup(raid_id, raid["chat"])
        return
    
    results = []
    total_coins = 0
    total_chars = 0
    total_crits = 0
    images = []
    
    for uid in users:
        roll = random.randint(1, 100)
        crit = cfg["crit_chance"]
        char = crit + cfg["char_chance"]
        coin = char + cfg["coin_chance"]
        loss = coin + cfg["loss_chance"]
        
        if roll <= crit:
            character = await get_character(cfg["rarities"])
            coins = random.randint(cfg["coin_min"], cfg["coin_max"])
            
            if character:
                await add_character(uid, character)
                await update_balance(uid, coins)
                r = character.get("rarity")
                if isinstance(r, int):
                    r = RARITY.get(r, "🟢 Common")
                
                results.append({
                    "user": uid, "type": "crit", "char": character, 
                    "rarity": r, "coins": coins
                })
                if character.get("img_url"):
                    images.append(character["img_url"])
                total_chars += 1
                total_coins += coins
                total_crits += 1
            else:
                coins *= 2
                await update_balance(uid, coins)
                results.append({"user": uid, "type": "coins", "amount": coins, "2x": True})
                total_coins += coins
        
        elif roll <= char:
            character = await get_character(cfg["rarities"])
            if character:
                await add_character(uid, character)
                r = character.get("rarity")
                if isinstance(r, int):
                    r = RARITY.get(r, "🟢 Common")
                results.append({"user": uid, "type": "char", "char": character, "rarity": r})
                if character.get("img_url"):
                    images.append(character["img_url"])
                total_chars += 1
            else:
                coins = random.randint(cfg["coin_min"], cfg["coin_max"])
                await update_balance(uid, coins)
                results.append({"user": uid, "type": "coins", "amount": coins})
                total_coins += coins
        
        elif roll <= coin:
            coins = random.randint(cfg["coin_min"], cfg["coin_max"])
            await update_balance(uid, coins)
            results.append({"user": uid, "type": "coins", "amount": coins})
            total_coins += coins
        
        elif roll <= loss:
            l = random.randint(cfg["loss_min"], cfg["loss_max"])
            await update_balance(uid, -l)
            results.append({"user": uid, "type": "loss", "amount": l})
        
        else:
            results.append({"user": uid, "type": "nothing"})
    
    text = (
        f"<blockquote>⚔️ <b>ʀᴀɪᴅ ᴄᴏᴍᴘʟᴇᴛᴇ</b> ⚔️</blockquote>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👥 <b>ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs:</b> <code>{len(users)}</code>\n\n"
        f"<b>🏆 ʟᴏᴏᴛ:</b>\n"
    )
    
    for r in results:
        try:
            u = await client.get_users(r["user"])
            name = f"@{u.username}" if u.username else u.first_name
        except:
            name = "Unknown"
        
        if r["type"] == "crit":
            cid = r["char"].get("id", "???")
            cname = r["char"].get("name", "Unknown")
            text += (
                f"• {name} — <b>💥 ᴄʀɪᴛɪᴄᴀʟ!</b>\n"
                f"  └ 🎴 {r['rarity']} • <code>{cid}</code> • {cname}\n"
                f"  └ 💰 <code>{r['coins']} ᴄᴏɪɴs</code>\n"
            )
        elif r["type"] == "char":
            cid = r["char"].get("id", "???")
            cname = r["char"].get("name", "Unknown")
            text += f"• {name} — 🎴\n  └ {r['rarity']} • <code>{cid}</code> • {cname}\n"
        elif r["type"] == "coins":
            x2 = " (2x!)" if r.get("2x") else ""
            text += f"• {name} — 💰 <code>{r['amount']}{x2}</code>\n"
        elif r["type"] == "loss":
            text += f"• {name} — 💀 <code>-{r['amount']}</code>\n"
        else:
            text += f"• {name} — ❌\n"
    
    text += (
        f"\n━━━━━━━━━━━━━━━\n"
        f"💰 <b>ᴛᴏᴛᴀʟ:</b> <code>{total_coins:,}</code>\n"
        f"🎴 <b>ᴄʜᴀʀs:</b> <code>{total_chars}</code>\n"
        f"💥 <b>ᴄʀɪᴛs:</b> <code>{total_crits}</code>\n\n"
        f"<i>ʙʏ</i> <a href='https://t.me/siyaprobot'>sɪʏᴀ</a>"
    )
    
    try:
        if images:
            await message.delete()
            await client.send_photo(raid["chat"], images[0], caption=text)
        else:
            await message.edit_text(text)
    except:
        try:
            await message.edit_text(text)
        except:
            pass
    
    await cleanup(raid_id, raid["chat"])


@shivuu.on_message(filters.command("setraidcharge") & filters.user(OWNER_ID))
async def set_charge(_, m):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /setraidcharge <amount>")
    try:
        amt = int(m.command[1])
        await update_settings({"charge": amt})
        await m.reply_text(f"✅ Charge: {amt} coins")
    except:
        await m.reply_text("❌ Invalid")


@shivuu.on_message(filters.command("setraidcooldown") & filters.user(OWNER_ID))
async def set_cd(_, m):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /setraidcooldown <minutes>")
    try:
        mins = int(m.command[1])
        await update_settings({"cooldown": mins})
        await m.reply_text(f"✅ Cooldown: {mins}m")
    except:
        await m.reply_text("❌ Invalid")


@shivuu.on_message(filters.command("setraidrarities") & filters.user(OWNER_ID))
async def set_rarities(_, m):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /setraidrarities <1,2,3...>")
    try:
        rarities = [int(r.strip()) for r in m.command[1].split(",")]
        await update_settings({"rarities": rarities})
        names = [RARITY.get(r, f"R{r}") for r in rarities]
        await m.reply_text(f"✅ Rarities:\n" + "\n".join(names))
    except:
        await m.reply_text("❌ Invalid")


@shivuu.on_message(filters.command("setraidchances") & filters.user(OWNER_ID))
async def set_chances(_, m):
    if len(m.command) < 6:
        return await m.reply_text("Usage: /setraidchances <char> <coin> <loss> <nothing> <crit>")
    try:
        cc, co, l, n, cr = [int(m.command[i]) for i in range(1, 6)]
        if cc + co + l + n + cr != 100:
            return await m.reply_text(f"❌ Total: {cc+co+l+n+cr} (must be 100)")
        await update_settings({
            "char_chance": cc, "coin_chance": co, "loss_chance": l,
            "nothing_chance": n, "crit_chance": cr
        })
        await m.reply_text(f"✅ Char:{cc}% Coin:{co}% Loss:{l}% Nothing:{n}% Crit:{cr}%")
    except:
        await m.reply_text("❌ Invalid")


@shivuu.on_message(filters.command("setraidcoins") & filters.user(OWNER_ID))
async def set_coins(_, m):
    if len(m.command) < 3:
        return await m.reply_text("Usage: /setraidcoins <min> <max>")
    try:
        cmin, cmax = int(m.command[1]), int(m.command[2])
        if cmin >= cmax:
            return await m.reply_text("❌ Min >= Max")
        await update_settings({"coin_min": cmin, "coin_max": cmax})
        await m.reply_text(f"✅ Coins: {cmin}-{cmax}")
    except:
        await m.reply_text("❌ Invalid")


@shivuu.on_message(filters.command("setraidloss") & filters.user(OWNER_ID))
async def set_loss(_, m):
    if len(m.command) < 3:
        return await m.reply_text("Usage: /setraidloss <min> <max>")
    try:
        lmin, lmax = int(m.command[1]), int(m.command[2])
        if lmin >= lmax:
            return await m.reply_text("❌ Min >= Max")
        await update_settings({"loss_min": lmin, "loss_max": lmax})
        await m.reply_text(f"✅ Loss: {lmin}-{lmax}")
    except:
        await m.reply_text("❌ Invalid")


@shivuu.on_message(filters.command("raidsettings") & filters.user(OWNER_ID))
async def show_settings(_, m):
    s = await get_settings()
    r = [RARITY.get(i, f"R{i}") for i in s["rarities"]]
    await m.reply_text(
        f"<b>🌐 Global Raid Settings</b>\n\n"
        f"💰 Charge: {s['charge']}\n"
        f"⏱ Duration: {s['duration']}s\n"
        f"⏳ Cooldown: {s['cooldown']}m\n\n"
        f"<b>Rewards:</b>\n"
        f"Coins: {s['coin_min']}-{s['coin_max']}\n"
        f"Loss: {s['loss_min']}-{s['loss_max']}\n\n"
        f"<b>Chances:</b>\n"
        f"Char: {s['char_chance']}% | Coin: {s['coin_chance']}%\n"
        f"Loss: {s['loss_chance']}% | Nothing: {s['nothing_chance']}%\n"
        f"Crit: {s['crit_chance']}%\n\n"
        f"<b>Rarities:</b> {len(r)}\n" + ", ".join(r[:5]) + 
        ("..." if len(r) > 5 else "")
    )