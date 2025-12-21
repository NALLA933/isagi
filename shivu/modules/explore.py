import random
from dataclasses import dataclass
from datetime import datetime
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import application, user_collection


@dataclass(frozen=True)
class ExploreConfig:
    cooldown: int = 73
    fee: int = 300
    min_reward: int = 600
    max_reward: int = 1000
    min_balance: int = 500


@dataclass
class ExploreResult:
    success: bool
    message: str
    reward: int = 0


CONFIG = ExploreConfig()
user_cooldowns = {}

EXPLORE_ACTIONS = [
    "explored a dungeon",
    "ventured into a dark forest",
    "discovered ancient ruins",
    "infiltrated an elvish village",
    "raided a goblin nest",
    "survived an orc den"
]


def check_cooldown(user_id: int) -> int | None:
    if user_id not in user_cooldowns:
        return None
    
    elapsed = (datetime.utcnow() - user_cooldowns[user_id]).total_seconds()
    return None if elapsed >= CONFIG.cooldown else int(CONFIG.cooldown - elapsed)


async def explore_cmd(update: Update, context: CallbackContext) -> None:
    if update.effective_chat.type == "private":
        await update.message.reply_text("❌ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴄᴀɴ ᴏɴʟʏ ʙᴇ ᴜsᴇᴅ ɪɴ ɢʀᴏᴜᴘs!")
        return

    if update.message.reply_to_message:
        await update.message.reply_text("❌ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴄᴀɴɴᴏᴛ ʙᴇ ᴜsᴇᴅ ᴀs ᴀ ʀᴇᴘʟʏ!")
        return

    user_id = update.effective_user.id

    if remaining := check_cooldown(user_id):
        await update.message.reply_text(
            f"⏰ ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ {remaining} sᴇᴄᴏɴᴅs ʙᴇғᴏʀᴇ ᴇxᴘʟᴏʀɪɴɢ ᴀɢᴀɪɴ!"
        )
        return

    try:
        user = await user_collection.find_one({'id': user_id})
        
        if not user:
            await update.message.reply_text("❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴀɴ ᴀᴄᴄᴏᴜɴᴛ ʏᴇᴛ!")
            return

        if user.get('balance', 0) < CONFIG.min_balance:
            await update.message.reply_text(
                f"❌ ʏᴏᴜ ɴᴇᴇᴅ ᴀᴛ ʟᴇᴀsᴛ {CONFIG.min_balance} ᴛᴏᴋᴇɴs ᴛᴏ ᴇxᴘʟᴏʀᴇ!"
            )
            return

        reward = random.randint(CONFIG.min_reward, CONFIG.max_reward)
        
        await user_collection.update_one(
            {'id': user_id},
            {'$inc': {'balance': reward - CONFIG.fee}}
        )

        user_cooldowns[user_id] = datetime.utcnow()

        action = random.choice(EXPLORE_ACTIONS)
        await update.message.reply_text(
            f"🗺️ ʏᴏᴜ {action} ᴀɴᴅ ғᴏᴜɴᴅ {reward} ᴛᴏᴋᴇɴs!\n"
            f"💰 ᴇxᴘʟᴏʀᴀᴛɪᴏɴ ғᴇᴇ: -{CONFIG.fee} ᴛᴏᴋᴇɴs"
        )

    except Exception as e:
        await update.message.reply_text(
            f"❌ ᴇʀʀᴏʀ: <code>{str(e)}</code>",
            parse_mode='HTML'
        )


application.add_handler(CommandHandler("explore", explore_cmd))