import random
from datetime import datetime, timedelta
import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest

from shivu import application, db, user_collection

collection = db['anime_characters_lol']
giveaway_collection = db['giveaways']

sudo_users = ["8297659126", "8420981179", "5147822244"]

KOLKATA_TZ = pytz.timezone('Asia/Kolkata')

def get_kolkata_time():
    return datetime.now(KOLKATA_TZ)

def utc_to_kolkata(utc_time):
    if utc_time.tzinfo is None:
        utc_time = pytz.utc.localize(utc_time)
    return utc_time.astimezone(KOLKATA_TZ)

def kolkata_to_utc(kolkata_time):
    if kolkata_time.tzinfo is None:
        kolkata_time = KOLKATA_TZ.localize(kolkata_time)
    return kolkata_time.astimezone(pytz.utc)

async def is_sudo_user(user_id: int) -> bool:
    return str(user_id) in sudo_users

async def gstart(update: Update, context: CallbackContext):
    """Start a new giveaway"""
    user_id = update.effective_user.id

    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ sᴛᴀʀᴛ ɢɪᴠᴇᴀᴡᴀʏs")
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b> /gstart &lt;character_id&gt; &lt;hours&gt; &lt;min_characters&gt;\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b>\n"
            "/gstart CHAR001 24 10\n\n"
            "• <b>character_id:</b> ID of character to giveaway\n"
            "• <b>hours:</b> Duration in hours\n"
            "• <b>min_characters:</b> Minimum characters user must have to join",
            parse_mode="HTML"
        )
        return

    try:
        char_id = context.args[0]
        duration_hours = int(context.args[1])
        min_activity = int(context.args[2])

        if duration_hours <= 0 or min_activity < 0:
            await update.message.reply_text("⚠️ ᴅᴜʀᴀᴛɪᴏɴ ᴍᴜsᴛ ʙᴇ ᴘᴏsɪᴛɪᴠᴇ!")
            return

        character = await collection.find_one({"id": char_id})
        if not character:
            await update.message.reply_text(
                f"⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ <code>{char_id}</code> ɴᴏᴛ ғᴏᴜɴᴅ ɪɴ ᴅᴀᴛᴀʙᴀsᴇ",
                parse_mode="HTML"
            )
            return

        active = await giveaway_collection.find_one({"status": "active"})
        if active:
            await update.message.reply_text(
                "⚠️ <b>ᴀ ɢɪᴠᴇᴀᴡᴀʏ ɪs ᴀʟʀᴇᴀᴅʏ ᴀᴄᴛɪᴠᴇ!</b>\n\n"
                "ᴘʟᴇᴀsᴇ ᴇɴᴅ ɪᴛ ғɪʀsᴛ ᴜsɪɴɢ /gend",
                parse_mode="HTML"
            )
            return

        start_time_kolkata = get_kolkata_time()
        end_time_kolkata = start_time_kolkata + timedelta(hours=duration_hours)

        start_time_utc = kolkata_to_utc(start_time_kolkata).replace(tzinfo=None)
        end_time_utc = kolkata_to_utc(end_time_kolkata).replace(tzinfo=None)

        giveaway = {
            "character_id": char_id,
            "start_time": start_time_utc,
            "end_time": end_time_utc,
            "min_activity": min_activity,
            "participants": [],
            "status": "active",
            "created_by": user_id,
            "winner": None,
            "duration_hours": duration_hours
        }

        await giveaway_collection.insert_one(giveaway)

        img_url = character.get("img_url", "")
        is_video = character.get("rarity") == "🎥 AMV"

        caption = (
            f"<b>🎉 ɴᴇᴡ ɢɪᴠᴇᴀᴡᴀʏ sᴛᴀʀᴛᴇᴅ!</b>\n\n"
            f"🎁 <b>{character['name']}</b>\n"
            f"🎭 {character.get('anime', 'Unknown')}\n"
            f"💫 {character.get('rarity', 'Unknown')}\n\n"
            f"⏰ <b>sᴛᴀʀᴛs:</b> {start_time_kolkata.strftime('%d %b %Y, %I:%M %p IST')}\n"
            f"⏰ <b>ᴇɴᴅs:</b> {end_time_kolkata.strftime('%d %b %Y, %I:%M %p IST')}\n"
            f"⌛ <b>ᴅᴜʀᴀᴛɪᴏɴ:</b> {duration_hours} hours\n"
            f"📊 <b>ʀᴇǫᴜɪʀᴇᴍᴇɴᴛ:</b> {min_activity} characters minimum\n"
            f"👥 <b>ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs:</b> 0\n\n"
            f"🎫 ᴄʟɪᴄᴋ ʙᴇʟᴏᴡ ᴛᴏ ᴊᴏɪɴ!"
        )

        buttons = [
            [InlineKeyboardButton("🎫 ᴊᴏɪɴ ɢɪᴠᴇᴀᴡᴀʏ", callback_data="gj")],
            [InlineKeyboardButton("📊 ᴠɪᴇᴡ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs", callback_data="gp")],
            [InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="gr")]
        ]
        markup = InlineKeyboardMarkup(buttons)

        try:
            if is_video and img_url:
                await update.message.reply_video(
                    video=img_url,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup
                )
            elif img_url:
                await update.message.reply_photo(
                    photo=img_url,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup
                )
            else:
                await update.message.reply_text(
                    caption,
                    parse_mode="HTML",
                    reply_markup=markup
                )
        except BadRequest as e:
            await update.message.reply_text(
                caption,
                parse_mode="HTML",
                reply_markup=markup
            )

    except ValueError:
        await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ғᴏʀᴍᴀᴛ!")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ᴇʀʀᴏʀ: {str(e)}")
        print(f"Error in gstart: {e}")  # Debug log

async def gend(update: Update, context: CallbackContext):
    """End the active giveaway"""
    user_id = update.effective_user.id

    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴇɴᴅ ɢɪᴠᴇᴀᴡᴀʏs")
        return

    giveaway = await giveaway_collection.find_one({"status": "active"})

    if not giveaway:
        await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢɪᴠᴇᴀᴡᴀʏ ғᴏᴜɴᴅ")
        return

    participants = giveaway.get("participants", [])

    if not participants:
        await giveaway_collection.update_one(
            {"_id": giveaway["_id"]},
            {"$set": {"status": "ended", "ended_at": datetime.utcnow()}}
        )
        await update.message.reply_text(
            "😢 <b>ɢɪᴠᴇᴀᴡᴀʏ ᴇɴᴅᴇᴅ</b>\n\n"
            "ɴᴏ ᴏɴᴇ ᴊᴏɪɴᴇᴅ ᴛʜᴇ ɢɪᴠᴇᴀᴡᴀʏ",
            parse_mode="HTML"
        )
        return

    winner_id = random.choice(participants)

    character = await collection.find_one({"id": giveaway["character_id"]})

    await user_collection.update_one(
        {"id": winner_id},
        {"$push": {"characters": character}},
        upsert=True
    )

    end_time_kolkata = utc_to_kolkata(datetime.utcnow())
    await giveaway_collection.update_one(
        {"_id": giveaway["_id"]},
        {
            "$set": {
                "status": "ended",
                "winner": winner_id,
                "ended_at": datetime.utcnow()
            }
        }
    )

    try:
        winner_user = await context.bot.get_chat(winner_id)
        winner_name = winner_user.first_name
        winner_mention = f"<a href='tg://user?id={winner_id}'>{winner_name}</a>"
    except:
        winner_name = f"User {winner_id}"
        winner_mention = winner_name

    img_url = character.get("img_url", "")
    is_video = character.get("rarity") == "🎥 AMV"

    caption = (
        f"<b>🎊 ɢɪᴠᴇᴀᴡᴀʏ ᴇɴᴅᴇᴅ!</b>\n\n"
        f"🎁 <b>{character['name']}</b>\n"
        f"🎭 {character.get('anime', 'Unknown')}\n"
        f"💫 {character.get('rarity', 'Unknown')}\n\n"
        f"🏆 <b>ᴡɪɴɴᴇʀ:</b> {winner_mention}\n"
        f"👥 <b>ᴛᴏᴛᴀʟ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs:</b> {len(participants)}\n"
        f"⏰ <b>ᴇɴᴅᴇᴅ ᴀᴛ:</b> {end_time_kolkata.strftime('%d %b %Y, %I:%M %p IST')}\n\n"
        f"🎉 ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs!"
    )

    try:
        if is_video and img_url:
            await update.message.reply_video(
                video=img_url,
                caption=caption,
                parse_mode="HTML"
            )
        elif img_url:
            await update.message.reply_photo(
                photo=img_url,
                caption=caption,
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(caption, parse_mode="HTML")
    except BadRequest:
        await update.message.reply_text(caption, parse_mode="HTML")

    try:
        await context.bot.send_message(
            chat_id=winner_id,
            text=(
                f"🎉 <b>ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs!</b>\n\n"
                f"ʏᴏᴜ ᴡᴏɴ <b>{character['name']}</b> ғʀᴏᴍ ᴛʜᴇ ɢɪᴠᴇᴀᴡᴀʏ!\n"
                f"ᴛʜᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs ʙᴇᴇɴ ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ!"
            ),
            parse_mode="HTML"
        )
    except:
        pass

async def gstatus(update: Update, context: CallbackContext):
    """Check giveaway status"""
    giveaway = await giveaway_collection.find_one({"status": "active"})

    if not giveaway:
        await update.message.reply_text(
            "ℹ️ <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ɢɪᴠᴇᴀᴡᴀʏ</b>\n\n"
            "ᴛʜᴇʀᴇ ɪs ᴄᴜʀʀᴇɴᴛʟʏ ɴᴏ ɢɪᴠᴇᴀᴡᴀʏ ʀᴜɴɴɪɴɢ",
            parse_mode="HTML"
        )
        return

    character = await collection.find_one({"id": giveaway["character_id"]})
    participants = giveaway.get("participants", [])

    end_time_utc = giveaway["end_time"]
    current_time_utc = datetime.utcnow()
    time_left = end_time_utc - current_time_utc

    hours_left = int(time_left.total_seconds() / 3600)
    minutes_left = int((time_left.total_seconds() % 3600) / 60)

    start_time_kolkata = utc_to_kolkata(giveaway["start_time"])
    end_time_kolkata = utc_to_kolkata(end_time_utc)

    status_text = (
        f"<b>🎁 ᴀᴄᴛɪᴠᴇ ɢɪᴠᴇᴀᴡᴀʏ sᴛᴀᴛᴜs</b>\n\n"
        f"✨ <b>{character['name']}</b>\n"
        f"🎭 {character.get('anime', 'Unknown')}\n"
        f"💫 {character.get('rarity', 'Unknown')}\n\n"
        f"⏰ <b>sᴛᴀʀᴛᴇᴅ:</b> {start_time_kolkata.strftime('%d %b %Y, %I:%M %p IST')}\n"
        f"⏰ <b>ᴇɴᴅs:</b> {end_time_kolkata.strftime('%d %b %Y, %I:%M %p IST')}\n"
        f"⌛ <b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {hours_left}h {minutes_left}m\n"
        f"📊 <b>ʀᴇǫᴜɪʀᴇᴍᴇɴᴛ:</b> {giveaway['min_activity']} characters\n"
        f"👥 <b>ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs:</b> {len(participants)}\n\n"
        f"ᴜsᴇ /gend ᴛᴏ ᴇɴᴅ ᴛʜᴇ ɢɪᴠᴇᴀᴡᴀʏ"
    )

    buttons = [
        [InlineKeyboardButton("🎫 ᴊᴏɪɴ ɢɪᴠᴇᴀᴡᴀʏ", callback_data="gj")],
        [InlineKeyboardButton("📊 ᴠɪᴇᴡ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs", callback_data="gp")]
    ]
    markup = InlineKeyboardMarkup(buttons)

    await update.message.reply_text(
        status_text,
        parse_mode="HTML",
        reply_markup=markup
    )

async def glist(update: Update, context: CallbackContext):
    """List recent giveaways"""
    # Fixed: Use proper async iteration
    cursor = giveaway_collection.find().sort("start_time", -1).limit(5)
    giveaways = await cursor.to_list(length=5)

    if not giveaways:
        await update.message.reply_text(
            "ℹ️ <b>ɴᴏ ɢɪᴠᴇᴀᴡᴀʏs ғᴏᴜɴᴅ</b>\n\n"
            "ᴛʜᴇʀᴇ ʜᴀᴠᴇɴ'ᴛ ʙᴇᴇɴ ᴀɴʏ ɢɪᴠᴇᴀᴡᴀʏs ʏᴇᴛ",
            parse_mode="HTML"
        )
        return

    text = "<b>📜 ʀᴇᴄᴇɴᴛ ɢɪᴠᴇᴀᴡᴀʏs</b>\n\n"

    for i, g in enumerate(giveaways, 1):
        character = await collection.find_one({"id": g["character_id"]})
        char_name = character.get("name", "Unknown") if character else "Unknown"

        status = g.get("status", "unknown")
        status_emoji = "✅" if status == "ended" else "🟢" if status == "active" else "❌"

        start_time_kolkata = utc_to_kolkata(g["start_time"])

        text += f"{i}. {status_emoji} <b>{char_name}</b>\n"
        text += f"   📅 {start_time_kolkata.strftime('%d %b %Y, %I:%M %p IST')}\n"
        text += f"   👥 {len(g.get('participants', []))} participants\n"

        if status == "ended" and g.get("winner"):
            winner_id = g.get("winner")
            try:
                winner_user = await context.bot.get_chat(winner_id)
                winner_name = winner_user.first_name
            except:
                winner_name = f"User {winner_id}"
            text += f"   🏆 Winner: {winner_name}\n"

        text += "\n"

    await update.message.reply_text(text, parse_mode="HTML")

async def gcancel(update: Update, context: CallbackContext):
    """Cancel active giveaway"""
    user_id = update.effective_user.id

    if not await is_sudo_user(user_id):
        await update.message.reply_text("⛔️ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ ᴄᴀɴᴄᴇʟ ɢɪᴠᴇᴀᴡᴀʏs")
        return

    giveaway = await giveaway_collection.find_one({"status": "active"})

    if not giveaway:
        await update.message.reply_text("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢɪᴠᴇᴀᴡᴀʏ ғᴏᴜɴᴅ")
        return

    character = await collection.find_one({"id": giveaway["character_id"]})

    await giveaway_collection.update_one(
        {"_id": giveaway["_id"]},
        {"$set": {"status": "cancelled"}}
    )

    await update.message.reply_text(
        f"❌ <b>ɢɪᴠᴇᴀᴡᴀʏ ᴄᴀɴᴄᴇʟʟᴇᴅ</b>\n\n"
        f"🎁 {character['name']}\n"
        f"👥 {len(giveaway.get('participants', []))} participants\n\n"
        f"ᴛʜᴇ ɢɪᴠᴇᴀᴡᴀʏ ʜᴀs ʙᴇᴇɴ ᴄᴀɴᴄᴇʟʟᴇᴅ",
        parse_mode="HTML"
    )

async def giveaway_callback(update: Update, context: CallbackContext):
    """Handle giveaway button callbacks"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "gj":
        giveaway = await giveaway_collection.find_one({"status": "active"})

        if not giveaway:
            await query.answer("⚠️ ɢɪᴠᴇᴀᴡᴀʏ ʜᴀs ᴇɴᴅᴇᴅ", show_alert=True)
            return

        user_data = await user_collection.find_one({"id": user_id})
        if not user_data:
            await query.answer(
                "⚠️ ʏᴏᴜ ɴᴇᴇᴅ ᴛᴏ sᴛᴀʀᴛ ᴘʟᴀʏɪɴɢ ғɪʀsᴛ!",
                show_alert=True
            )
            return

        user_chars = user_data.get("characters", [])
        min_required = giveaway.get("min_activity", 0)

        if len(user_chars) < min_required:
            await query.answer(
                f"⚠️ ʏᴏᴜ ɴᴇᴇᴅ {min_required} ᴄʜᴀʀᴀᴄᴛᴇʀs ᴛᴏ ᴊᴏɪɴ!\n"
                f"ʏᴏᴜ ᴄᴜʀʀᴇɴᴛʟʏ ʜᴀᴠᴇ {len(user_chars)}",
                show_alert=True
            )
            return

        participants = giveaway.get("participants", [])
        if user_id in participants:
            await query.answer("⚠️ ʏᴏᴜ'ᴠᴇ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ!", show_alert=True)
            return

        await giveaway_collection.update_one(
            {"_id": giveaway["_id"]},
            {"$push": {"participants": user_id}}
        )

        participants_count = len(participants) + 1

        character = await collection.find_one({"id": giveaway["character_id"]})
        end_time_kolkata = utc_to_kolkata(giveaway["end_time"])
        start_time_kolkata = utc_to_kolkata(giveaway["start_time"])

        caption = (
            f"<b>🎉 ɴᴇᴡ ɢɪᴠᴇᴀᴡᴀʏ sᴛᴀʀᴛᴇᴅ!</b>\n\n"
            f"🎁 <b>{character['name']}</b>\n"
            f"🎭 {character.get('anime', 'Unknown')}\n"
            f"💫 {character.get('rarity', 'Unknown')}\n\n"
            f"⏰ <b>sᴛᴀʀᴛs:</b> {start_time_kolkata.strftime('%d %b %Y, %I:%M %p IST')}\n"
            f"⏰ <b>ᴇɴᴅs:</b> {end_time_kolkata.strftime('%d %b %Y, %I:%M %p IST')}\n"
            f"⌛ <b>ᴅᴜʀᴀᴛɪᴏɴ:</b> {giveaway['duration_hours']} hours\n"
            f"📊 <b>ʀᴇǫᴜɪʀᴇᴍᴇɴᴛ:</b> {min_required} characters minimum\n"
            f"👥 <b>ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs:</b> {participants_count}\n\n"
            f"🎫 ᴄʟɪᴄᴋ ʙᴇʟᴏᴡ ᴛᴏ ᴊᴏɪɴ!"
        )

        buttons = [
            [InlineKeyboardButton("🎫 ᴊᴏɪɴ ɢɪᴠᴇᴀᴡᴀʏ", callback_data="gj")],
            [InlineKeyboardButton("📊 ᴠɪᴇᴡ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs", callback_data="gp")],
            [InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="gr")]
        ]
        markup = InlineKeyboardMarkup(buttons)

        try:
            await query.edit_message_caption(
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        except BadRequest:
            pass

        await query.answer("✅ ʏᴏᴜ'ᴠᴇ ᴊᴏɪɴᴇᴅ ᴛʜᴇ ɢɪᴠᴇᴀᴡᴀʏ!", show_alert=False)

    elif data == "gp":
        giveaway = await giveaway_collection.find_one({"status": "active"})

        if not giveaway:
            await query.answer("⚠️ ɢɪᴠᴇᴀᴡᴀʏ ʜᴀs ᴇɴᴅᴇᴅ", show_alert=True)
            return

        participants = giveaway.get("participants", [])

        if not participants:
            await query.answer(
                "📊 ɴᴏ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs ʏᴇᴛ!\n\nʙᴇ ᴛʜᴇ ғɪʀsᴛ ᴛᴏ ᴊᴏɪɴ!",
                show_alert=True
            )
            return

        await query.answer(
            f"👥 ᴛᴏᴛᴀʟ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs: {len(participants)}\n\n"
            f"ɢᴏᴏᴅ ʟᴜᴄᴋ ᴛᴏ ᴀʟʟ!",
            show_alert=True
        )

    elif data == "gr":
        giveaway = await giveaway_collection.find_one({"status": "active"})

        if not giveaway:
            await query.answer("⚠️ ɢɪᴠᴇᴀᴡᴀʏ ʜᴀs ᴇɴᴅᴇᴅ", show_alert=True)
            return

        character = await collection.find_one({"id": giveaway["character_id"]})
        participants = giveaway.get("participants", [])

        end_time_kolkata = utc_to_kolkata(giveaway["end_time"])
        start_time_kolkata = utc_to_kolkata(giveaway["start_time"])

        caption = (
            f"<b>🎉 ɴᴇᴡ ɢɪᴠᴇᴀᴡᴀʏ sᴛᴀʀᴛᴇᴅ!</b>\n\n"
            f"🎁 <b>{character['name']}</b>\n"
            f"🎭 {character.get('anime', 'Unknown')}\n"
            f"💫 {character.get('rarity', 'Unknown')}\n\n"
            f"⏰ <b>sᴛᴀʀᴛs:</b> {start_time_kolkata.strftime('%d %b %Y, %I:%M %p IST')}\n"
            f"⏰ <b>ᴇɴᴅs:</b> {end_time_kolkata.strftime('%d %b %Y, %I:%M %p IST')}\n"
            f"⌛ <b>ᴅᴜʀᴀᴛɪᴏɴ:</b> {giveaway['duration_hours']} hours\n"
            f"📊 <b>ʀᴇǫᴜɪʀᴇᴍᴇɴᴛ:</b> {giveaway['min_activity']} characters minimum\n"
            f"👥 <b>ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs:</b> {len(participants)}\n\n"
            f"🎫 ᴄʟɪᴄᴋ ʙᴇʟᴏᴡ ᴛᴏ ᴊᴏɪɴ!"
        )

        buttons = [
            [InlineKeyboardButton("🎫 ᴊᴏɪɴ ɢɪᴠᴇᴀᴡᴀʏ", callback_data="gj")],
            [InlineKeyboardButton("📊 ᴠɪᴇᴡ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs", callback_data="gp")],
            [InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="gr")]
        ]
        markup = InlineKeyboardMarkup(buttons)

        try:
            await query.edit_message_caption(
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        except BadRequest:
            pass

        await query.answer("🔄 ʀᴇғʀᴇsʜᴇᴅ!", show_alert=False)


# Register handlers
def register_handlers():
    """Register all giveaway handlers"""
    application.add_handler(CommandHandler("gstart", gstart, block=False))
    application.add_handler(CommandHandler("gend", gend, block=False))
    application.add_handler(CommandHandler("gstatus", gstatus, block=False))
    application.add_handler(CommandHandler("glist", glist, block=False))
    application.add_handler(CommandHandler("gcancel", gcancel, block=False))
    application.add_handler(CallbackQueryHandler(giveaway_callback, pattern=r"^g[jpr]$", block=False))


# Call this function when your bot starts
register_handlers()