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

# Kolkata timezone
KOLKATA_TZ = pytz.timezone('Asia/Kolkata')

def get_kolkata_time():
    """Get current time in Kolkata timezone"""
    return datetime.now(KOLKATA_TZ)

def utc_to_kolkata(utc_time):
    """Convert UTC datetime to Kolkata timezone"""
    if utc_time.tzinfo is None:
        utc_time = pytz.utc.localize(utc_time)
    return utc_time.astimezone(KOLKATA_TZ)

def kolkata_to_utc(kolkata_time):
    """Convert Kolkata datetime to UTC"""
    if kolkata_time.tzinfo is None:
        kolkata_time = KOLKATA_TZ.localize(kolkata_time)
    return kolkata_time.astimezone(pytz.utc)

async def is_sudo_user(user_id: int) -> bool:
    return str(user_id) in sudo_users

async def gstart(update: Update, context: CallbackContext):
    """Start a giveaway
    Usage: /gstart <character_id> <hours> <min_characters_required>
    Example: /gstart CHAR001 24 10
    """
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

        # Check if character exists
        character = await collection.find_one({"id": char_id})
        if not character:
            await update.message.reply_text(
                f"⚠️ ᴄʜᴀʀᴀᴄᴛᴇʀ <code>{char_id}</code> ɴᴏᴛ ғᴏᴜɴᴅ ɪɴ ᴅᴀᴛᴀʙᴀsᴇ",
                parse_mode="HTML"
            )
            return

        # Check if there's already an active giveaway
        active = await giveaway_collection.find_one({"status": "active"})
        if active:
            await update.message.reply_text(
                "⚠️ <b>ᴀ ɢɪᴠᴇᴀᴡᴀʏ ɪs ᴀʟʀᴇᴀᴅʏ ᴀᴄᴛɪᴠᴇ!</b>\n\n"
                "ᴘʟᴇᴀsᴇ ᴇɴᴅ ɪᴛ ғɪʀsᴛ ᴜsɪɴɢ /gend",
                parse_mode="HTML"
            )
            return

        # Calculate end time in Kolkata timezone
        start_time_kolkata = get_kolkata_time()
        end_time_kolkata = start_time_kolkata + timedelta(hours=duration_hours)
        
        # Store in UTC for consistency
        start_time_utc = kolkata_to_utc(start_time_kolkata).replace(tzinfo=None)
        end_time_utc = kolkata_to_utc(end_time_kolkata).replace(tzinfo=None)

        # Create giveaway document
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

        # Prepare giveaway announcement
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
            await query.edit_message_caption(
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        except BadRequest:
            pass

        await query.answer("🔄 ʀᴇғʀᴇsʜᴇᴅ!", show_alert=False)

async def glist(update: Update, context: CallbackContext):
    """List recent giveaways (last 5)"""
    giveaways = await giveaway_collection.find().sort("start_time", -1).limit(5).to_list(5)
    
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
    """Cancel active giveaway without selecting winner"""
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

# Register all handlers
application.add_handler(CommandHandler("gstart", gstart, block=False))
application.add_handler(CommandHandler("gend", gend, block=False))
application.add_handler(CommandHandler("gstatus", gstatus, block=False))
application.add_handler(CommandHandler("glist", glist, block=False))
application.add_handler(CommandHandler("gcancel", gcancel, block=False))
application.add_handler(CallbackQueryHandler(giveaway_callback, pattern=r"^g", block=False)) ʀᴇғʀᴇsʜ", callback_data="gr")