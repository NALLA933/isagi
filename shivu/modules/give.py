from dataclasses import dataclass
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import collection, user_collection, application
from shivu.modules.database.sudo import is_user_sudo


@dataclass
class CharacterGiftResult:
    img_url: str
    caption: str


async def give_character(receiver_id: int, character_id: str) -> CharacterGiftResult:
    if not (character := await collection.find_one({'id': character_id})):
        raise ValueError("Character not found")
    
    await user_collection.update_one(
        {'id': receiver_id},
        {'$push': {'characters': character}}
    )
    
    caption = (
        f"🍀 Slave Added {receiver_id}\n\n"
        f"🍥 Name: {character['name']}\n"
        f"🏵️ Rarity: {character['rarity']}\n"
        f"🆔 ID: {character['id']}"
    )
    
    return CharacterGiftResult(character['img_url'], caption)


async def give_cmd(update: Update, context: CallbackContext):
    msg = update.message
    
    if not await is_user_sudo(msg.from_user.id):
        await msg.reply_text("⛔ You are not authorized to use this command")
        return
    
    if not msg.reply_to_message:
        await msg.reply_text("❌ Reply to a user's message to give a character")
        return
    
    try:
        character_id = msg.text.split()[1]
        receiver_id = msg.reply_to_message.from_user.id
        
        result = await give_character(receiver_id, character_id)
        await msg.reply_photo(photo=result.img_url, caption=result.caption)
    
    except IndexError:
        await msg.reply_text("❌ Please provide a character ID\n<i>Usage: /give [character_id]</i>", parse_mode='HTML')
    except ValueError as e:
        await msg.reply_text(f"❌ {str(e)}")
    except Exception as e:
        await msg.reply_text(f"❌ Error: <code>{str(e)}</code>", parse_mode='HTML')


application.add_handler(CommandHandler("give", give_cmd, block=False))