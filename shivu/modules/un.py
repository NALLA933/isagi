from html import escape
from typing import List, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

from shivu import application, collection, user_collection


async def get_ungrabbed_characters() -> List[dict]:
    all_chars = await collection.find({}).to_list(length=1000)
    grabbed_ids = await user_collection.distinct('characters.id')
    ungrabbed = [char for char in all_chars if char.get('id') not in grabbed_ids]
    return ungrabbed[:1000]


def format_character_card(char: dict, current: int, total: int) -> str:
    rarity = char.get('rarity', 'Common')
    rarity_parts = str(rarity).split(' ', 1)
    rarity_emoji = rarity_parts[0] if rarity_parts else ''
    rarity_text = rarity_parts[1] if len(rarity_parts) > 1 else 'Common'
    
    return (
        f"UNGRABBED CHARACTER\n\n"
        f"ID: {char.get('id', 'Unknown')}\n"
        f"Name: {escape(char.get('name', 'Unknown'))}\n"
        f"Anime: {escape(char.get('anime', 'Unknown'))}\n"
        f"Rarity: {rarity_emoji} {rarity_text}\n\n"
        f"Page {current + 1} of {total}\n\n"
        f"This character has never been grabbed"
    )


def build_navigation(page: int, total: int) -> InlineKeyboardMarkup:
    buttons = []
    
    if page > 0:
        buttons.append(InlineKeyboardButton("Previous", callback_data=f"ungrab_{page-1}"))
    
    buttons.append(InlineKeyboardButton(f"{page+1}/{total}", callback_data="noop"))
    
    if page < total - 1:
        buttons.append(InlineKeyboardButton("Next", callback_data=f"ungrab_{page+1}"))
    
    return InlineKeyboardMarkup([buttons])


async def ungrabbed_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ungrabbed = await get_ungrabbed_characters()
        
        if not ungrabbed:
            return await update.message.reply_text(
                "No ungrabbed characters found\n\nAll characters have been grabbed at least once",
                parse_mode=ParseMode.HTML
            )
        
        char = ungrabbed[0]
        total = len(ungrabbed)
        caption = format_character_card(char, 0, total)
        keyboard = build_navigation(0, total)
        
        img_url = char.get('img_url', '')
        is_video = char.get('is_video', False)
        
        try:
            if is_video:
                await update.message.reply_video(
                    video=img_url,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML
                )
            else:
                await update.message.reply_photo(
                    photo=img_url,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML
                )
        except:
            await update.message.reply_text(
                caption + f"\n\nMedia URL: {img_url}",
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
    
    except Exception as e:
        await update.message.reply_text(f"Error: {escape(str(e))}")


async def ungrabbed_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        page = int(query.data.split('_')[1])
        ungrabbed = await get_ungrabbed_characters()
        
        if page >= len(ungrabbed):
            return await query.answer("Page not found")
        
        char = ungrabbed[page]
        total = len(ungrabbed)
        caption = format_character_card(char, page, total)
        keyboard = build_navigation(page, total)
        
        try:
            await query.edit_message_caption(
                caption=caption,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
        except BadRequest:
            await query.answer("Error updating page")
    
    except Exception as e:
        await query.answer(f"Error: {str(e)[:50]}")


application.add_handler(CommandHandler("un", ungrabbed_command, block=False))
application.add_handler(CallbackQueryHandler(ungrabbed_pagination, pattern=r"^ungrab_", block=False))