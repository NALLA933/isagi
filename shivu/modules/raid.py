import asyncio
import random
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from shivu.config import Development as Config
from shivu import shivuu, db, user_collection, collection, sudo_users

raid_settings_collection = db['raid_settings']
raid_cooldown_collection = db['raid_cooldown']
active_raids_collection = db['active_raids']

OWNER_ID = [8420981179, 5147822244]
GLOBAL_SETTINGS_ID = "global_raid_settings"

RARITY_MAP = {
    1: "🟢 Common", 2: "🟣 Rare", 3: "🟡 Legendary", 4: "💮 Special Edition",
    5: "💫 Neon", 6: "✨ Manga", 7: "🎭 Cosplay", 8: "🎐 Celestial",
    9: "🔮 Premium Edition", 10: "💋 Erotic", 11: "🌤 Summer", 12: "☃️ Winter",
    13: "☔️ Monsoon", 14: "💝 Valentine", 15: "🎃 Halloween", 16: "🎄 Christmas",
    17: "🏵 Mythic", 18: "🎗 Special Events", 19: "🎥 Amv", 20: "👼 Tiny"
}

DEFAULT_SETTINGS = {
    "start_charge": 500, 
    "join_phase_duration": 30, 
    "cooldown_minutes": 5,
    "min_balance": 500, 
    "allowed_rarities": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "coin_min": 500, 
    "coin_max": 2000, 
    "coin_loss_min": 200, 
    "coin_loss_max": 500,
    "character_chance": 25, 
    "coin_chance": 35, 
    "loss_chance": 20,
    "nothing_chance": 15, 
    "critical_chance": 5
}

async def get_global_settings():
    settings = await raid_settings_collection.find_one({"chat_id": GLOBAL_SETTINGS_ID})
    if not settings:
        settings = DEFAULT_SETTINGS.copy()
        settings["chat_id"] = GLOBAL_SETTINGS_ID
        await raid_settings_collection.insert_one(settings)
    return settings

async def get_raid_settings(chat_id):
    return await get_global_settings()

async def update_global_settings(update_dict):
    await raid_settings_collection.update_one(
        {"chat_id": GLOBAL_SETTINGS_ID},
        {"$set": update_dict},
        upsert=True
    )
    await raid_settings_collection.update_many(
        {"chat_id": {"$ne": GLOBAL_SETTINGS_ID}},
        {"$set": update_dict}
    )

async def check_user_cooldown(user_id, chat_id):
    cooldown_data = await raid_cooldown_collection.find_one({"user_id": user_id, "chat_id": chat_id})
    if cooldown_data:
        cooldown_until = cooldown_data.get("cooldown_until")
        if cooldown_until and datetime.utcnow() < cooldown_until:
            remaining = (cooldown_until - datetime.utcnow()).total_seconds()
            return False, int(remaining)
    return True, 0

async def set_user_cooldown(user_id, chat_id, minutes):
    cooldown_until = datetime.utcnow() + timedelta(minutes=minutes)
    await raid_cooldown_collection.update_one(
        {"user_id": user_id, "chat_id": chat_id},
        {"$set": {"cooldown_until": cooldown_until}}, 
        upsert=True
    )

async def get_user_data(user_id):
    user = await user_collection.find_one({"id": user_id})
    if not user:
        user = {"id": user_id, "balance": 0, "characters": []}
        await user_collection.insert_one(user)
    return user

async def update_user_balance(user_id, amount):
    await user_collection.update_one(
        {"id": user_id}, 
        {"$inc": {"balance": amount}}, 
        upsert=True
    )

async def get_random_character(allowed_rarities):
    try:
        characters = await collection.find({"rarity": {"$in": allowed_rarities}}).to_list(length=None)
        if not characters:
            rarity_strings = [RARITY_MAP.get(r, f"Rarity {r}") for r in allowed_rarities]
            characters = await collection.find({"rarity": {"$in": rarity_strings}}).to_list(length=None)
        if characters:
            return random.choice(characters)
        return None
    except Exception:
        return None

async def add_character_to_user(user_id, character):
    try:
        char_rarity = character.get("rarity")
        if isinstance(char_rarity, int):
            char_rarity = RARITY_MAP.get(char_rarity, "🟢 Common")
        char_data = {
            "id": character.get("id"), 
            "name": character.get("name"),
            "anime": character.get("anime"), 
            "rarity": char_rarity,
            "img_url": character.get("img_url", "")
        }
        await user_collection.update_one(
            {"id": user_id}, 
            {"$push": {"characters": char_data}}, 
            upsert=True
        )
    except Exception:
        pass

async def cleanup_raid(raid_id, chat_id):
    try:
        await active_raids_collection.delete_one({"raid_id": raid_id})
        await active_raids_collection.delete_many({
            "chat_id": chat_id,
            "started_at": {"$lt": datetime.utcnow() - timedelta(minutes=10)}
        })
    except Exception:
        pass

@shivuu.on_message(filters.command(["raid"]) & filters.group)
async def start_raid(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    active_raid = await active_raids_collection.find_one({"chat_id": chat_id})
    if active_raid:
        time_since_start = (datetime.utcnow() - active_raid.get("started_at", datetime.utcnow())).total_seconds()
        if time_since_start > 300:
            await cleanup_raid(active_raid.get("raid_id"), chat_id)
        else:
            await message.reply_text("⚠️ ᴀ ʀᴀɪᴅ ɪs ᴀʟʀᴇᴀᴅʏ ᴀᴄᴛɪᴠᴇ ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ!")
            return

    settings = await get_raid_settings(chat_id)

    can_raid, remaining = await check_user_cooldown(user_id, chat_id)
    if not can_raid:
        mins, secs = remaining // 60, remaining % 60
        await message.reply_text(f"⏳ ʏᴏᴜ'ʀᴇ ᴏɴ ᴄᴏᴏʟᴅᴏᴡɴ!\nᴛɪᴍᴇ ʟᴇғᴛ: `{mins}m {secs}s`")
        return

    user_data = await get_user_data(user_id)
    if user_data.get("balance", 0) < settings["start_charge"]:
        await message.reply_text(
            f"💰 ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ!\n"
            f"ʏᴏᴜ ɴᴇᴇᴅ `{settings['start_charge']}` ᴄᴏɪɴs ᴛᴏ sᴛᴀʀᴛ ᴀ ʀᴀɪᴅ."
        )
        return

    await update_user_balance(user_id, -settings["start_charge"])

    raid_id = f"{chat_id}_{int(datetime.utcnow().timestamp() * 1000)}"
    raid_data = {
        "raid_id": raid_id, 
        "chat_id": chat_id, 
        "starter_id": user_id,
        "participants": [user_id], 
        "started_at": datetime.utcnow(), 
        "settings": settings,
        "status": "active"
    }
    await active_raids_collection.insert_one(raid_data)
    await set_user_cooldown(user_id, chat_id, settings["cooldown_minutes"])

    join_button = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ ᴊᴏɪɴ ʀᴀɪᴅ ⚔️", callback_data=f"join_raid:{raid_id}")]
    ])

    announcement = (
        f"<blockquote>⚔️ <b>sʜᴀᴅᴏᴡ ʀᴀɪᴅ ʜᴀs ʙᴇɢᴜɴ!</b> ⚔️</blockquote>\n\n"
        f"<code>ᴊᴏɪɴ ɴᴏᴡ ᴀɴᴅ ʜᴇʟᴘ ᴜɴᴄᴏᴠᴇʀ ᴀɴᴄɪᴇɴᴛ ᴛʀᴇᴀsᴜʀᴇs!</code>\n"
        f"<code>ʙᴇғᴏʀᴇ ᴛʜᴇ sʜᴀᴅᴏᴡs ᴄʟᴏsᴇ ɪɴ...</code>\n\n"
        f"⏱ <b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> <code>{settings['join_phase_duration']}s</code>\n"
        f"💰 <b>ᴇɴᴛʀʏ ғᴇᴇ:</b> <code>{settings['start_charge']} ᴄᴏɪɴs</code>\n"
        f"👥 <b>ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs:</b> <code>1</code>\n\n"
        f"━━━━━━━━━━━━━━━\n<i>sᴛᴀʀᴛᴇᴅ ʙʏ</i> {message.from_user.mention}"
    )

    raid_msg = await message.reply_text(announcement, reply_markup=join_button)
    
    await asyncio.sleep(settings["join_phase_duration"])
    
    raid_check = await active_raids_collection.find_one({"raid_id": raid_id})
    if raid_check and raid_check.get("status") == "active":
        await execute_raid(client, raid_msg, raid_id)

@shivuu.on_callback_query(filters.regex(r"^join_raid:"))
async def join_raid_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    raid_id = callback_query.data.split(":")[1]

    raid = await active_raids_collection.find_one({"raid_id": raid_id})
    if not raid or raid.get("status") != "active":
        await callback_query.answer("⚠️ ᴛʜɪs ʀᴀɪᴅ ʜᴀs ᴇɴᴅᴇᴅ!", show_alert=True)
        return

    if user_id in raid["participants"]:
        await callback_query.answer("✅ ʏᴏᴜ'ᴠᴇ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ!", show_alert=False)
        return

    settings = raid["settings"]

    can_raid, remaining = await check_user_cooldown(user_id, raid["chat_id"])
    if not can_raid:
        mins, secs = remaining // 60, remaining % 60
        await callback_query.answer(f"⏳ ʏᴏᴜ'ʀᴇ ᴏɴ ᴄᴏᴏʟᴅᴏᴡɴ! {mins}m {secs}s ʟᴇғᴛ", show_alert=True)
        return

    user_data = await get_user_data(user_id)
    if user_data.get("balance", 0) < settings["start_charge"]:
        await callback_query.answer(
            f"💰 ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ! ɴᴇᴇᴅ {settings['start_charge']} ᴄᴏɪɴs", 
            show_alert=True
        )
        return

    await update_user_balance(user_id, -settings["start_charge"])
    await active_raids_collection.update_one(
        {"raid_id": raid_id}, 
        {"$push": {"participants": user_id}}
    )
    await set_user_cooldown(user_id, raid["chat_id"], settings["cooldown_minutes"])
    await callback_query.answer("⚔️ ʏᴏᴜ'ᴠᴇ ᴊᴏɪɴᴇᴅ ᴛʜᴇ ʀᴀɪᴅ!", show_alert=False)

    try:
        updated_raid = await active_raids_collection.find_one({"raid_id": raid_id})
        if not updated_raid:
            return
            
        participant_count = len(updated_raid["participants"])
        elapsed = (datetime.utcnow() - raid["started_at"]).total_seconds()
        remaining_time = max(0, int(settings["join_phase_duration"] - elapsed))

        try:
            starter = await client.get_users(raid["starter_id"])
            starter_mention = starter.mention
        except Exception:
            starter_mention = "Unknown"

        updated_text = (
            f"<blockquote>⚔️ <b>sʜᴀᴅᴏᴡ ʀᴀɪᴅ ʜᴀs ʙᴇɢᴜɴ!</b> ⚔️</blockquote>\n\n"
            f"<code>ᴊᴏɪɴ ɴᴏᴡ ᴀɴᴅ ʜᴇʟᴘ ᴜɴᴄᴏᴠᴇʀ ᴀɴᴄɪᴇɴᴛ ᴛʀᴇᴀsᴜʀᴇs!</code>\n"
            f"<code>ʙᴇғᴏʀᴇ ᴛʜᴇ sʜᴀᴅᴏᴡs ᴄʟᴏsᴇ ɪɴ...</code>\n\n"
            f"⏱ <b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> <code>{remaining_time}s</code>\n"
            f"💰 <b>ᴇɴᴛʀʏ ғᴇᴇ:</b> <code>{settings['start_charge']} ᴄᴏɪɴs</code>\n"
            f"👥 <b>ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs:</b> <code>{participant_count}</code>\n\n"
            f"━━━━━━━━━━━━━━━\n<i>sᴛᴀʀᴛᴇᴅ ʙʏ</i> {starter_mention}"
        )

        join_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚔️ ᴊᴏɪɴ ʀᴀɪᴅ ⚔️", callback_data=f"join_raid:{raid_id}")]
        ])
        await callback_query.message.edit_text(updated_text, reply_markup=join_button)
    except Exception:
        pass

async def execute_raid(client, message, raid_id):
    raid = await active_raids_collection.find_one({"raid_id": raid_id})
    if not raid or raid.get("status") != "active":
        return

    await active_raids_collection.update_one(
        {"raid_id": raid_id},
        {"$set": {"status": "completed"}}
    )

    participants = raid["participants"]
    settings = raid["settings"]

    if len(participants) == 0:
        await message.edit_text("❌ ɴᴏ ᴏɴᴇ ᴊᴏɪɴᴇᴅ ᴛʜᴇ ʀᴀɪᴅ!")
        await cleanup_raid(raid_id, raid["chat_id"])
        return

    results = []
    total_coins_gained = 0
    total_characters = 0
    total_critical = 0
    character_images = []

    for user_id in participants:
        rand = random.randint(1, 100)
        critical_threshold = settings.get("critical_chance", 5)
        char_threshold = critical_threshold + settings["character_chance"]
        coin_threshold = char_threshold + settings["coin_chance"]
        loss_threshold = coin_threshold + settings["loss_chance"]

        if rand <= critical_threshold:
            character = await get_random_character(settings["allowed_rarities"])
            coins = random.randint(settings["coin_min"], settings["coin_max"])

            if character:
                await add_character_to_user(user_id, character)
                await update_user_balance(user_id, coins)
                char_rarity = character.get("rarity")
                if isinstance(char_rarity, int):
                    rarity_text = RARITY_MAP.get(char_rarity, "🟢 Common")
                else:
                    rarity_text = char_rarity

                results.append({
                    "user_id": user_id, 
                    "type": "critical", 
                    "character": character, 
                    "rarity": rarity_text, 
                    "coins": coins
                })
                if character.get("img_url"):
                    character_images.append(character.get("img_url"))
                total_characters += 1
                total_coins_gained += coins
                total_critical += 1
            else:
                coins = coins * 2
                await update_user_balance(user_id, coins)
                results.append({
                    "user_id": user_id, 
                    "type": "coins", 
                    "amount": coins, 
                    "doubled": True
                })
                total_coins_gained += coins

        elif rand <= char_threshold:
            character = await get_random_character(settings["allowed_rarities"])
            if character:
                await add_character_to_user(user_id, character)
                char_rarity = character.get("rarity")
                if isinstance(char_rarity, int):
                    rarity_text = RARITY_MAP.get(char_rarity, "🟢 Common")
                else:
                    rarity_text = char_rarity
                results.append({
                    "user_id": user_id, 
                    "type": "character", 
                    "character": character, 
                    "rarity": rarity_text
                })
                if character.get("img_url"):
                    character_images.append(character.get("img_url"))
                total_characters += 1
            else:
                coins = random.randint(settings["coin_min"], settings["coin_max"])
                await update_user_balance(user_id, coins)
                results.append({"user_id": user_id, "type": "coins", "amount": coins})
                total_coins_gained += coins

        elif rand <= coin_threshold:
            coins = random.randint(settings["coin_min"], settings["coin_max"])
            await update_user_balance(user_id, coins)
            results.append({"user_id": user_id, "type": "coins", "amount": coins})
            total_coins_gained += coins

        elif rand <= loss_threshold:
            loss = random.randint(settings["coin_loss_min"], settings["coin_loss_max"])
            await update_user_balance(user_id, -loss)
            results.append({"user_id": user_id, "type": "loss", "amount": loss})

        else:
            results.append({"user_id": user_id, "type": "nothing"})

    result_text = (
        f"<blockquote>⚔️ <b>ʀᴀɪᴅ ᴄᴏᴍᴘʟᴇᴛᴇ</b> ⚔️</blockquote>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👥 <b>ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs:</b> <code>{len(participants)}</code>\n\n"
        f"<b>🏆 ʟᴏᴏᴛ ʀᴇᴘᴏʀᴛ:</b>\n"
    )

    for result in results:
        try:
            user = await client.get_users(result["user_id"])
            username = f"@{user.username}" if user.username else user.first_name
        except Exception:
            username = "Unknown"

        if result["type"] == "critical":
            char_id = result["character"].get("id", "???")
            char_name = result["character"].get("name", "Unknown")
            result_text += (
                f"• {username} — <b>💥 ᴄʀɪᴛɪᴄᴀʟ ʜɪᴛ!</b>\n"
                f"  └ 🎴 {result['rarity']} • <code>{char_id}</code> • {char_name}\n"
                f"  └ 💰 <code>{result['coins']} ᴄᴏɪɴs</code>\n"
            )
        elif result["type"] == "character":
            char_id = result["character"].get("id", "???")
            char_name = result["character"].get("name", "Unknown")
            result_text += (
                f"• {username} — <code>ᴄᴀᴘᴛᴜʀᴇᴅ</code> 🎴\n"
                f"  └ {result['rarity']} • <code>{char_id}</code> • {char_name}\n"
            )
        elif result["type"] == "coins":
            doubled_text = " (ᴅᴏᴜʙʟᴇᴅ!)" if result.get("doubled") else ""
            result_text += f"• {username} — <code>ғᴏᴜɴᴅ {result['amount']} ᴄᴏɪɴs</code> 💰{doubled_text}\n"
        elif result["type"] == "loss":
            result_text += f"• {username} — <code>ʟᴏsᴛ {result['amount']} ᴄᴏɪɴs</code> 💀\n"
        else:
            result_text += f"• {username} — <code>ғᴏᴜɴᴅ ɴᴏᴛʜɪɴɢ...</code> ❌\n"

    result_text += (
        f"\n━━━━━━━━━━━━━━━\n"
        f"💰 <b>ᴛᴏᴛᴀʟ ʟᴏᴏᴛ ᴠᴀʟᴜᴇ:</b> <code>{total_coins_gained:,} ᴄᴏɪɴs</code>\n"
        f"🎴 <b>ɴᴇᴡ ʀᴇʟɪᴄs ғᴏᴜɴᴅ:</b> <code>{total_characters}</code>\n"
        f"💥 <b>ᴄʀɪᴛɪᴄᴀʟ ʜɪᴛs:</b> <code>{total_critical}</code>\n\n"
        f"<i>ᴍᴇssᴀɢᴇ ᴘʀᴏᴠɪᴅᴇᴅ ʙʏ</i> <a href='https://t.me/siyaprobot'>sɪʏᴀ</a>"
    )

    try:
        if character_images:
            await message.delete()
            await client.send_photo(
                chat_id=raid["chat_id"], 
                photo=character_images[0], 
                caption=result_text
            )
        else:
            await message.edit_text(result_text)
    except Exception:
        try:
            await message.edit_text(result_text)
        except Exception:
            pass

    await cleanup_raid(raid_id, raid["chat_id"])

@shivuu.on_message(filters.command(["setraidcharge"]) & filters.user(OWNER_ID))
async def set_raid_charge(c, m):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /setraidcharge amount")
    try:
        amt = int(m.command[1])
        await update_global_settings({"start_charge": amt})
        await m.reply_text(f"✅ Raid charge set to {amt} coins globally for all groups!")
    except Exception:
        await m.reply_text("Invalid amount")

@shivuu.on_message(filters.command(["setraidcooldown"]) & filters.user(OWNER_ID))
async def set_raid_cooldown(c, m):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /setraidcooldown minutes")
    try:
        mins = int(m.command[1])
        await update_global_settings({"cooldown_minutes": mins})
        await m.reply_text(f"✅ Cooldown set to {mins} minutes globally for all groups!")
    except Exception:
        await m.reply_text("Invalid value")

@shivuu.on_message(filters.command(["setraidrarities"]) & filters.user(OWNER_ID))
async def set_raid_rarities(c, m):
    if len(m.command) < 2:
        return await m.reply_text("Usage: /setraidrarities 1,2,3,4,5")
    try:
        rarities = [int(r.strip()) for r in m.command[1].split(",")]
        await update_global_settings({"allowed_rarities": rarities})
        rarity_names = [RARITY_MAP.get(r, f"Rarity {r}") for r in rarities]
        await m.reply_text(f"✅ Allowed rarities set globally for all groups:\n" + "\n".join(rarity_names))
    except Exception:
        await m.reply_text("Invalid format")

@shivuu.on_message(filters.command(["setraidchances"]) & filters.user(OWNER_ID))
async def set_raid_chances(c, m):
    if len(m.command) < 6:
        return await m.reply_text(
            "Usage: /setraidchances char coin loss nothing critical\n"
            "Example: /setraidchances 25 35 20 15 5"
        )
    try:
        char_c, coin_c, loss_c, nothing_c, crit_c = [int(m.command[i]) for i in range(1, 6)]
        total = char_c + coin_c + loss_c + nothing_c + crit_c
        if total != 100:
            return await m.reply_text(f"Total must equal 100. Current: {total}")
        await update_global_settings({
            "character_chance": char_c, 
            "coin_chance": coin_c, 
            "loss_chance": loss_c, 
            "nothing_chance": nothing_c, 
            "critical_chance": crit_c
        })
        await m.reply_text(
            f"✅ Chances updated globally for all groups:\n"
            f"Char: {char_c}% | Coin: {coin_c}% | Loss: {loss_c}% | "
            f"Nothing: {nothing_c}% | Critical: {crit_c}%"
        )
    except Exception:
        await m.reply_text("Invalid values")

@shivuu.on_message(filters.command(["setraidcoins"]) & filters.user(OWNER_ID))
async def set_raid_coins(c, m):
    if len(m.command) < 3:
        return await m.reply_text("Usage: /setraidcoins min max")
    try:
        coin_min, coin_max = int(m.command[1]), int(m.command[2])
        if coin_min >= coin_max:
            return await m.reply_text("Min must be less than max")
        await update_global_settings({"coin_min": coin_min, "coin_max": coin_max})
        await m.reply_text(f"✅ Coin range set to {coin_min}-{coin_max} globally for all groups!")
    except Exception:
        await m.reply_text("Invalid values")

@shivuu.on_message(filters.command(["setraidloss"]) & filters.user(OWNER_ID))
async def set_raid_loss(c, m):
    if len(m.command) < 3:
        return await m.reply_text("Usage: /setraidloss min max")
    try:
        loss_min, loss_max = int(m.command[1]), int(m.command[2])
        if loss_min >= loss_max:
            return await m.reply_text("Min must be less than max")
        await update_global_settings({"coin_loss_min": loss_min, "coin_loss_max": loss_max})
        await m.reply_text(f"✅ Loss range set to {loss_min}-{loss_max} globally for all groups!")
    except Exception:
        await m.reply_text("Invalid values")

@shivuu.on_message(filters.command(["raidsettings"]) & filters.user(OWNER_ID))
async def show_raid_settings(c, m):
    s = await get_global_settings()
    rn = [RARITY_MAP.get(r, f"Rarity {r}") for r in s["allowed_rarities"]]
    await m.reply_text(
        f"<b>🌐 Global Raid Settings (All Groups)</b>\n\n"
        f"Charge: {s['start_charge']} coins\n"
        f"Join Phase: {s['join_phase_duration']}s\n"
        f"Cooldown: {s['cooldown_minutes']}m\n"
        f"Min Balance: {s['min_balance']}\n\n"
        f"<b>Rewards:</b>\n"
        f"Coins: {s['coin_min']}-{s['coin_max']}\n"
        f"Loss: {s['coin_loss_min']}-{s['coin_loss_max']}\n\n"
        f"<b>Chances:</b>\n"
        f"Char: {s['character_chance']}% | Coin: {s['coin_chance']}%\n"
        f"Loss: {s['loss_chance']}% | Nothing: {s['nothing_chance']}%\n"
        f"Critical: {s.get('critical_chance', 5)}%\n\n"
        f"<b>Rarities:</b> {len(rn)}\n" + 
        ", ".join(rn[:5]) + ("..." if len(rn) > 5 else "") +
        f"\n\n<b>Global Commands (applies to ALL groups):</b>\n"
        f"/setraidcharge amount\n"
        f"/setraidcooldown minutes\n"
        f"/setraidchances c co l n cr\n"
        f"/setraidcoins min max\n"
        f"/setraidloss min max\n"
        f"/setraidrarities 1,2,3...\n\n"
        f"✨ All settings apply globally to every group!"
    )