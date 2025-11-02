from pymongo import TEXT
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from shivu import application, collection

RARITY_MAP = {
    1: "🟢 Common",
    2: "🟣 Rare",
    3: "🟡 Legendary", 
    4: "💮 Special Edition", 
    5: "💫 Neon",
    6: "✨ Manga", 
    7: "🎭 Cosplay",
    8: "🎐 Celestial",
    9: "🔮 Premium Edition",
    10: "💋 Erotic",
    11: "🌤 Summer",
    12: "☃️ Winter",
    13: "☔️ Monsoon",
    14: "💝 Valentine",
    15: "🎃 Halloween", 
    16: "🎄 Christmas",
    17: "🏵 Mythic",
    18: "🎗 Special Events",
    19: "🎥 AMV",
    20: "👼 Tiny"
}

async def rarity_count(update: Update, context: CallbackContext) -> None:
    try:
        args = context.args
        if len(args) != 1:
            await update.message.reply_text('Incorrect format. Please use: /r <rarity_number>')
            return

        # Parse rarity number
        try:
            rarity_num = int(args[0])
        except ValueError:
            await update.message.reply_text('Please provide a valid rarity number (1-20).')
            return

        # Check if rarity exists
        if rarity_num not in RARITY_MAP:
            await update.message.reply_text('Invalid rarity number. Please use a number between 1 and 20.')
            return

        # Count characters with this rarity
        count = await collection.count_documents({'rarity': rarity_num})

        rarity_name = RARITY_MAP[rarity_num]
        
        if count > 0:
            await update.message.reply_text(
                f"<b>{rarity_name}</b>\n"
                f"Total characters: <code>{count}</code>",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(f"No characters found in {rarity_name} rarity.")

    except Exception as e:
        await update.message.reply_text(f'Error: {str(e)}')

RARITY_COUNT_HANDLER = CommandHandler('r', rarity_count, block=False)
application.add_handler(RARITY_COUNT_HANDLER)