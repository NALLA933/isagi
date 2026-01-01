from html import escape
from typing import List

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

from shivu import application, collection, user_collection

CHARS_PER_PAGE = 10


async def get_ungrabbed_characters() -> List[dict]:
    all_chars = await collection.find({}).to_list(length=1000)
    grabbed_ids = await user_collection.distinct('characters.id')
    ungrabbed = [char for char in all_chars if char.get('id') not in grabbed_ids]
    return ungrabbed[:1000]


def format_caption(chars: List[dict], page: int, total_pages: int, total_chars: int) -> str:
    caption = f"UNGRABBED CHARACTERS\n\n"
    caption += f"Page {page + 1} of {total_pages}\n"
    caption += f"Total ungrabbed: {total_chars}\n\n"
    
    for i, char in enumerate(chars, 1):
        rarity = char.get('rarity', 'Common')
        rarity_parts = str(rarity).split(' ', 1)
        rarity_emoji = rarity_parts[0] if rarity_parts else ''
        rarity_text = rarity_parts[1] if len(rarity_parts) > 1 else 'Common'
        
        caption += (
            f"{i}. ID: {char.get('id')}\n"
            f"   Name: {escape(char.get('name', 'Unknown'))}\n"
            f"   Anime: {escape(char.get('anime', 'Unknown'))}\n"
            f"   Rarity: {rarity_emoji} {rarity_text}\n\n"
        )
    
    return caption


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
                "No ungrabbed characters found\n\nAll characters have been grabbed at least once"
            )
        
        total_chars = len(ungrabbed)
        total_pages = (total_chars + CHARS_PER_PAGE - 1) // CHARS_PER_PAGE
        
        page_chars = ungrabbed[:CHARS_PER_PAGE]
        caption = format_caption(page_chars, 0, total_pages, total_chars)
        keyboard = build_navigation(0, total_pages)
        
        media_group = []
        for i, char in enumerate(page_chars):
            img_url = char.get('img_url', '')
            is_video = char.get('is_video', False)
            
            try:
                if is_video:
                    media_group.append(InputMediaVideo(media=img_url))
                else:
                    media_group.append(InputMediaPhoto(media=img_url))
            except:
                continue
        
        if media_group:
            media_group[0].caption = caption
            media_group[0].parse_mode = ParseMode.HTML
            
            await update.message.reply_media_group(media_group)
            await update.message.reply_text(
                f"Page 1 of {total_pages}",
                reply_markup=keyboard
            )
        else:
            await update.message.reply_text(caption, reply_markup=keyboard)
    
    except Exception as e:
        await update.message.reply_text(f"Error: {escape(str(e))}")


async def ungrabbed_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        page = int(query.data.split('_')[1])
        ungrabbed = await get_ungrabbed_characters()
        
        total_chars = len(ungrabbed)
        total_pages = (total_chars + CHARS_PER_PAGE - 1) // CHARS_PER_PAGE
        
        if page >= total_pages:
            return await query.answer("Page not found")
        
        start_idx = page * CHARS_PER_PAGE
        end_idx = start_idx + CHARS_PER_PAGE
        page_chars = ungrabbed[start_idx:end_idx]
        
        caption = format_caption(page_chars, page, total_pages, total_chars)
        keyboard = build_navigation(page, total_pages)
        
        media_group = []
        for char in page_chars:
            img_url = char.get('img_url', '')
            is_video = char.get('is_video', False)
            
            try:
                if is_video:
                    media_group.append(InputMediaVideo(media=img_url))
                else:
                    media_group.append(InputMediaPhoto(media=img_url))
            except:
                continue
        
        if media_group:
            media_group[0].caption = caption
            media_group[0].parse_mode = ParseMode.HTML
            
            await query.message.reply_media_group(media_group)
            await query.edit_message_text(
                f"Page {page + 1} of {total_pages}",
                reply_markup=keyboard
            )
        else:
            await query.edit_message_text(caption, reply_markup=keyboard)
    
    except Exception as e:
        await query.answer(f"Error: {str(e)[:50]}")


application.add_handler(CommandHandler("ungrabbed", ungrabbed_command, block=False))
application.add_handler(CallbackQueryHandler(ungrabbed_pagination, pattern=r"^ungrab_", block=False))