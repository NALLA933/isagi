from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from shivu import application, db

collection = db['anime_characters_lol']

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
        
        if not args:
            response = "<blockquote><b>Rarity List</b></blockquote>\n\n"
            for num, name in RARITY_MAP.items():
                response += f"<code>{num}</code> → {name}\n"
            response += f"\n<b>Usage:</b> <code>/r number</code>\n<b>Example:</b> <code>/r 1</code>"
            await update.message.reply_text(response, parse_mode='HTML')
            return

        try:
            rarity_num = int(args[0])
        except ValueError:
            await update.message.reply_text(
                "<blockquote>Please provide a valid rarity number (1-20)</blockquote>",
                parse_mode='HTML'
            )
            return

        if rarity_num not in RARITY_MAP:
            await update.message.reply_text(
                "<blockquote>Invalid rarity. Use number between 1-20</blockquote>",
                parse_mode='HTML'
            )
            return

        rarity_name = RARITY_MAP[rarity_num]
        
        # Count with multiple formats
        count_string = await collection.count_documents({'rarity': rarity_name})
        count_number = await collection.count_documents({'rarity': rarity_num})
        emoji = rarity_name.split()[0]
        count_emoji = await collection.count_documents({'rarity': {'$regex': f'^{emoji}'}})
        
        total = max(count_string, count_number, count_emoji)
        
        response = f"<blockquote><b>{rarity_name}</b></blockquote>\n\n"
        response += f"<b>Total Characters:</b> <code>{total}</code>"
        
        await update.message.reply_text(response, parse_mode='HTML')

    except Exception as e:
        await update.message.reply_text(f"<blockquote>Error: {str(e)}</blockquote>", parse_mode='HTML')

# Register command handler only
application.add_handler(CommandHandler('r', rarity_count, block=False))