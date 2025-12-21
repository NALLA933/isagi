from dataclasses import dataclass
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
import html

from shivu import collection, user_collection, application
from shivu.modules.database.sudo import is_user_sudo

# --- CONFIGURATION ---
LOG_GROUP_ID = -1003110990230 
OWNER_ID = 8420981179  # <--- Sirf ye ID command use kar payegi
# ---------------------

@dataclass
class CharacterGiftResult:
    img_url: str
    caption: str
    char_name: str
    char_id: str

async def give_character(receiver_id: int, character_id: str) -> CharacterGiftResult:
    character = await collection.find_one({'id': character_id})
    if not character:
        raise ValueError("Character ID database mein nahi mila.")
    
    await user_collection.update_one(
        {'id': receiver_id},
        {'$push': {'characters': character}}
    )
    
    caption = (
        f"🎁 <b>Character Added!</b>\n\n"
        f"👤 <b>Receiver ID:</b> <code>{receiver_id}</code>\n"
        f"🍥 <b>Name:</b> {html.escape(character['name'])}\n"
        f"🏵️ <b>Rarity:</b> {character['rarity']}\n"
        f"🆔 <b>ID:</b> <code>{character['id']}</code>"
    )
    
    return CharacterGiftResult(character['img_url'], caption, character['name'], character['id'])

async def give_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = msg.from_user.id
    
    # --- OWNER & SUDO CHECK ---
    # Agar user Owner nahi hai AND Sudo bhi nahi hai, toh access deny kar do
    if user_id != OWNER_ID and not await is_user_sudo(user_id):
        await msg.reply_text("⛔ <b>Access Denied:</b> Only the Owner or Sudo users can use this.")
        return
    
    if not msg.reply_to_message:
        await msg.reply_text("❌ Reply to a user to give a character.")
        return
    
    try:
        if not context.args:
            await msg.reply_text("❌ ID missing! Usage: <code>/give [id]</code>", parse_mode='HTML')
            return

        character_id = context.args[0]
        receiver_id = msg.reply_to_message.from_user.id
        
        result = await give_character(receiver_id, character_id)
        
        await msg.reply_photo(
            photo=result.img_url, 
            caption=result.caption, 
            parse_mode='HTML'
        )
        
        # --- LOG TO GROUP ---
        executor_name = html.escape(msg.from_user.first_name)
        receiver_name = html.escape(msg.reply_to_message.from_user.first_name)
        
        log_text = (
            f"📢 <b>#GIVE_LOG</b>\n\n"
            f"<b>Authorized By:</b> {executor_name} (<code>{user_id}</code>)\n"
            f"<b>Gave To:</b> {receiver_name} (<code>{receiver_id}</code>)\n"
            f"<b>Character:</b> {html.escape(result.char_name)} (<code>{result.char_id}</code>)\n"
            f"<b>Status:</b> Success ✅"
        )
        
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text=log_text, parse_mode='HTML')

    except ValueError as e:
        await msg.reply_text(f"❌ {str(e)}")
    except Exception as e:
        await msg.reply_text(f"❌ <b>Error:</b> <code>{html.escape(str(e))}</code>", parse_mode='HTML')

# Registration
application.add_handler(CommandHandler("give", give_cmd, block=False))
