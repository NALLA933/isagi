from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters
from html import escape
import random
import re
from shivu import db, application, collection, user_collection, sudo_users

# Owner IDs (in addition to sudo_users)
OWNERS = [8420981179, 5147822244]

# Rarity mapping - MUST MATCH the format stored in database
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

RARITY_LIST = list(RARITY_MAP.values())


async def add_characters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add random characters to a user. Usage: /add <quantity> <rarity_number> or /add <quantity> (random rarity)"""

    user_id = update.effective_user.id

    # Check if user is owner or sudo user
    if user_id not in OWNERS and str(user_id) not in sudo_users:
        await update.message.reply_text("❌ You don't have permission to use this command!")
        return

    # Check if it's a reply to another user
    target_user = None
    target_user_id = None
    target_username = None
    target_first_name = None

    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_user_id = target_user.id
        target_username = target_user.username
        target_first_name = target_user.first_name

    # Parse command arguments
    args = context.args

    quantity = None
    rarity_choice = None

    # Handle /add <quantity> format (random rarity)
    if len(args) == 1:
        try:
            quantity = int(args[0])
            rarity_choice = None  # Will select random rarity
        except ValueError:
            await update.message.reply_text("❌ Quantity must be a number!")
            return
    # Handle /add <quantity> <rarity> format
    elif len(args) >= 2:
        try:
            quantity = int(args[0])
            rarity_choice = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ Quantity and rarity must be numbers!")
            return
    else:
        rarity_list_text = "\n".join([f"{num}. {rarity}" 
                                      for num, rarity in RARITY_MAP.items()])
        await update.message.reply_text(
            "❌ <b>Invalid format!</b>\n\n"
            "<b>Usage:</b>\n"
            "• <code>/add &lt;quantity&gt;</code> - Random rarity characters\n"
            "• <code>/add &lt;quantity&gt; &lt;rarity&gt;</code> - Specific rarity\n\n"
            "<b>Rarity Options:</b>\n" + rarity_list_text,
            parse_mode='HTML'
        )
        return

    # Check for username in args (optional, for direct targeting)
    if args and len(args) >= 3 and not target_user_id:
        username_or_id = args[2]
        # Check if it's a user ID
        if username_or_id.isdigit():
            target_user_id = int(username_or_id)
        else:
            # Remove @ if present
            target_username = username_or_id.lstrip('@')

    # Validate target user
    if not target_user_id and not target_username:
        await update.message.reply_text(
            "❌ <b>Please specify a user!</b>\n\n"
            "You can:\n"
            "• Reply to a user's message\n"
            "• Use: <code>/add &lt;quantity&gt; &lt;user_id&gt;</code>\n"
            "• Use: <code>/add &lt;quantity&gt; @username</code>\n"
            "• Use: <code>/add &lt;quantity&gt; &lt;rarity&gt; &lt;user_id&gt;</code>",
            parse_mode='HTML'
        )
        return

    # Validate quantity
    if quantity < 1 or quantity > 100:
        await update.message.reply_text("❌ Quantity must be between 1 and 100!")
        return

    # Validate rarity choice (if provided)
    if rarity_choice is not None and rarity_choice not in RARITY_MAP:
        rarity_list_text = "\n".join([f"{num}. {rarity}" 
                                      for num, rarity in RARITY_MAP.items()])
        await update.message.reply_text(
            f"❌ <b>Invalid rarity!</b> Choose between 1 and {len(RARITY_MAP)}\n\n"
            "<b>Rarity Options:</b>\n" + rarity_list_text,
            parse_mode='HTML'
        )
        return

    # Determine rarity mode
    if rarity_choice is None:
        rarity_mode = "🎲 Random Rarity"
        selected_rarity = None
    else:
        selected_rarity = RARITY_MAP[rarity_choice]
        rarity_mode = selected_rarity

    # Show processing message
    processing_msg = await update.message.reply_text(
        f"⏳ <b>Searching for {rarity_mode} characters...</b>",
        parse_mode='HTML'
    )

    # Get random characters from database
    try:
        if selected_rarity:
            # Specific rarity
            count = await collection.count_documents({"rarity": selected_rarity})

            if count == 0:
                await processing_msg.edit_text(
                    f"❌ No characters found with rarity: <b>{selected_rarity}</b>\n\n"
                    f"<i>💡 Tip: Check available rarities in the database.</i>",
                    parse_mode='HTML'
                )
                return

            # Fetch random characters
            characters = await collection.aggregate([
                {"$match": {"rarity": selected_rarity}},
                {"$sample": {"size": min(quantity, count)}}
            ]).to_list(length=quantity)
        else:
            # Random rarity - get random characters from all rarities
            total_count = await collection.count_documents({})

            if total_count == 0:
                await processing_msg.edit_text(
                    "❌ No characters found in database!",
                    parse_mode='HTML'
                )
                return

            # Fetch random characters (any rarity)
            characters = await collection.aggregate([
                {"$sample": {"size": min(quantity, total_count)}}
            ]).to_list(length=quantity)

    except Exception as e:
        print(f"Error fetching characters: {e}")
        import traceback
        traceback.print_exc()
        await processing_msg.edit_text(
            f"❌ <b>Error fetching characters from database!</b>\n\n"
            f"<code>{str(e)}</code>",
            parse_mode='HTML'
        )
        return

    if not characters:
        await processing_msg.edit_text(
            f"❌ No characters found!",
            parse_mode='HTML'
        )
        return

    await processing_msg.edit_text(
        f"⏳ <b>Adding {len(characters)} characters to user...</b>",
        parse_mode='HTML'
    )

    # Add characters to user's collection
    added_characters = []
    failed_count = 0

    for char in characters:
        character_data = {
            'id': char.get('id'),
            'name': char.get('name'),
            'anime': char.get('anime'),
            'img_url': char.get('img_url'),
            'rarity': char.get('rarity'),
        }

        # Add optional fields if they exist
        if 'is_video' in char:
            character_data['is_video'] = char['is_video']

        # Add to user collection
        try:
            if target_user_id:
                await user_collection.update_one(
                    {'id': target_user_id},
                    {
                        '$push': {'characters': character_data},
                        '$setOnInsert': {
                            'id': target_user_id,
                            'username': target_username,
                            'first_name': target_first_name
                        }
                    },
                    upsert=True
                )
            elif target_username:
                await user_collection.update_one(
                    {'username': target_username},
                    {
                        '$push': {'characters': character_data},
                        '$setOnInsert': {
                            'username': target_username
                        }
                    },
                    upsert=True
                )
        except Exception as e:
            print(f"Error adding character {char.get('id')} to collection: {e}")
            failed_count += 1
            continue

        added_characters.append(
            f"• <b>{escape(char.get('name', 'Unknown'))}</b> (<i>{escape(char.get('anime', 'Unknown'))}</i>) - {char.get('rarity', 'Unknown')}"
        )

    # Send success message
    if target_username:
        target_display = f"@{target_username}"
    elif target_first_name:
        target_display = escape(target_first_name)
    else:
        target_display = f"User ID: {target_user_id}"

    success_msg = (
        f"✅ <b>Characters Added Successfully!</b>\n\n"
        f"👤 <b>Target:</b> {target_display}\n"
        f"📊 <b>Quantity:</b> {len(added_characters)}/{quantity}\n"
        f"🎭 <b>Mode:</b> {rarity_mode}\n\n"
        f"<b>Added Characters:</b>\n" + "\n".join(added_characters[:10])
    )

    if len(added_characters) > 10:
        success_msg += f"\n<i>... and {len(added_characters) - 10} more!</i>"

    if failed_count > 0:
        success_msg += f"\n\n⚠️ <b>Failed to add:</b> {failed_count} characters"

    # Get random character image for display
    random_char = random.choice(characters)
    char_img = random_char.get('img_url')
    is_video = random_char.get('is_video', False)

    try:
        if char_img and is_video:
            await processing_msg.delete()
            await update.message.reply_video(
                video=char_img,
                caption=success_msg,
                parse_mode='HTML',
                read_timeout=60,
                write_timeout=60
            )
        elif char_img:
            await processing_msg.delete()
            await update.message.reply_photo(
                photo=char_img,
                caption=success_msg,
                parse_mode='HTML'
            )
        else:
            await processing_msg.edit_text(success_msg, parse_mode='HTML')
    except Exception as e:
        print(f"Error sending media: {e}")
        await processing_msg.edit_text(success_msg, parse_mode='HTML')


# Register handlers
application.add_handler(CommandHandler("add", add_characters, block=False))