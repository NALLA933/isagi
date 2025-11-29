from pyrogram import Client, filters
from pyrogram.enums import ParseMode
import random
import string
from datetime import datetime
from shivu import user_collection, application, collection 
from shivu import shivuu as app
from shivu import shivuu as bot

generated_codes = {}

def generate_random_code():
    code = ''.join(random.choices(string.ascii_lowercase + string.ascii_uppercase + string.digits, k=10))
    return f"@siyaprobot_{code}"

def generate_random_amount():
    return random.randint(10, 5000000000)

@app.on_message(filters.command(["gen"]))
async def gen(client, message):
    sudo_user_id = ["8420981179", "5147822244"]
    if str(message.from_user.id) not in sudo_user_id:
        await message.reply_text("Only authorized users can use this command.")
        return

    try:
        amount = float(message.command[1])
        quantity = int(message.command[2])
    except (IndexError, ValueError):
        await message.reply_text("Invalid amount or quantity. Usage: `/gen 10000000 5`")
        return

    code = generate_random_code()

    generated_codes[code] = {'amount': amount, 'quantity': quantity, 'claimed_by': []}

    formatted_amount = f"{amount:,.0f}" if amount.is_integer() else f"{amount:,.2f}"

    await message.reply_text(
        f"Generated code: `{code}`\nAmount: `{formatted_amount}`\nQuantity: `{quantity}`"
    )

@app.on_message(filters.command(["redeem"]))
async def redeem(client, message):
    if len(message.command) < 2:
        await message.reply_text("Usage: `/redeem @siyaprobot_YourCode`")
        return
        
    code = " ".join(message.command[1:])
    user_id = message.from_user.id

    if not code.startswith("@siyaprobot_"):
        await message.reply_text("Invalid code format. Code must start with @siyaprobot_")
        return

    if code in generated_codes:
        code_info = generated_codes[code]

        if user_id in code_info['claimed_by']:
            await message.reply_text("You have already claimed this code.")
            return

        if len(code_info['claimed_by']) >= code_info['quantity']:
            await message.reply_text("This code has been fully claimed.")
            return

        await user_collection.update_one(
            {'id': user_id},
            {'$inc': {'balance': float(code_info['amount'])}}
        )

        code_info['claimed_by'].append(user_id)

        formatted_amount = f"{code_info['amount']:,.0f}" if code_info['amount'].is_integer() else f"{code_info['amount']:,.2f}"

        await message.reply_text(
            f"Redeemed successfully. ₩`{formatted_amount}` Cash added to your Wealth.\n\n"
            f"Powered by [Siya](https://t.me/siyaprobot)",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await message.reply_text("Invalid code.")

pending_trades = {}
pending_gifts = {}
generated_waifus = {}

sudo_user_ids = ["8420981179", "5147822244"]

def generate_waifu_code():
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    return f"@siyaprobot_{code}"

@bot.on_message(filters.command(["sgen"]))
async def waifugen(client, message):
    if str(message.from_user.id) not in sudo_user_ids:
        await message.reply_text("You are not authorized to generate waifus.")
        return

    try:
        character_id = message.command[1]
        quantity = int(message.command[2])
    except (IndexError, ValueError):
        await message.reply_text("Invalid usage. Usage: `/sgen 56 1`")
        return

    waifu = await collection.find_one({'id': character_id})
    if not waifu:
        await message.reply_text("Invalid character ID. Waifu not found.")
        return

    code = generate_waifu_code()

    generated_waifus[code] = {'waifu': waifu, 'quantity': quantity}

    response_text = (
        f"Generated code: `{code}`\n"
        f"Name: {waifu['name']}\nRarity: {waifu['rarity']}\nQuantity: {quantity}"
    )

    await message.reply_text(response_text)

@bot.on_message(filters.command(["sredeem"]))
async def claimwaifu(client, message):
    if len(message.command) < 2:
        await message.reply_text("Usage: `/sredeem @siyaprobot_YourCode`")
        return
        
    code = " ".join(message.command[1:])
    user_id = message.from_user.id
    user_mention = f"[{message.from_user.first_name}](tg://user?id={user_id})"

    if not code.startswith("@siyaprobot_"):
        await message.reply_text("Invalid code format. Code must start with @siyaprobot_")
        return

    if code in generated_waifus:
        details = generated_waifus[code]

        if details['quantity'] > 0:
            waifu = details['waifu']

            await user_collection.update_one(
                {'id': user_id},
                {'$push': {'characters': waifu}}
            )

            details['quantity'] -= 1

            if details['quantity'] == 0:
                del generated_waifus[code]

            response_text = (
                f"Congratulations {user_mention}! You have received a new Slave!\n"
                f"Name: {waifu['name']}\n"
                f"Rarity: {waifu['rarity']}\n"
                f"Anime: {waifu['anime']}\n\n"
                f"Powered by [Siya](https://t.me/siyaprobot)"
            )
            await message.reply_photo(
                photo=waifu['img_url'], 
                caption=response_text,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await message.reply_text("This code has already been claimed the maximum number of times.")
    else:
        await message.reply_text("Invalid code.")