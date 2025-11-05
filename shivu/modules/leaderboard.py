import os
import asyncio
from datetime import datetime
from html import escape
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import (
    application, OWNER_ID, user_collection, 
    top_global_groups_collection, group_user_totals_collection
)
from shivu import sudo_users as SUDO_USERS

SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

def get_badge(rank):
    """Get rank badge"""
    if rank == 1: return "[★ 1ST ★]"
    elif rank == 2: return "[★ 2ND ★]"
    elif rank == 3: return "[★ 3RD ★]"
    elif rank <= 10: return f"[TOP {rank}]"
    return f"[#{rank}]"

async def animate(msg, text):
    """Simple loading animation"""
    for i in range(10):
        try:
            await msg.edit_text(f"{SPINNER[i % len(SPINNER)]} {text}", parse_mode='HTML')
            await asyncio.sleep(0.15)
        except: pass

async def global_leaderboard(update: Update, context: CallbackContext) -> None:
    """Top 10 groups globally"""
    msg = await update.message.reply_text("Loading...")
    await animate(msg, "Fetching global groups")
    
    cursor = top_global_groups_collection.aggregate([
        {"$project": {"group_name": 1, "count": 1}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ])
    data = await cursor.to_list(length=10)
    
    if not data:
        await msg.edit_text("║ No group data available ║")
        return
    
    text = "╔══════════════════════════╗\n║   TOP GLOBAL GROUPS      ║\n╚══════════════════════════╝\n\n"
    for i, g in enumerate(data, 1):
        name = escape(g.get('group_name', 'Unknown'))[:25]
        text += f'<b>{get_badge(i)}</b> {name}\n│ <b>{g["count"]:,}</b>\n└─────────────\n\n'
    text += "═══════════════════════════\n    @waifukunbot"
    await msg.edit_text(text, parse_mode='HTML')

async def ctop(update: Update, context: CallbackContext) -> None:
    """Top 10 users in chat"""
    msg = await update.message.reply_text("Loading...")
    await animate(msg, "Analyzing chat")
    
    cursor = group_user_totals_collection.aggregate([
        {"$match": {"group_id": update.effective_chat.id}},
        {"$project": {"username": 1, "first_name": 1, "character_count": "$count"}},
        {"$sort": {"character_count": -1}},
        {"$limit": 10}
    ])
    data = await cursor.to_list(length=10)
    
    if not data:
        await msg.edit_text("║ No data available ║")
        return
    
    text = "╔══════════════════════════╗\n║  TOP CHAT COLLECTORS     ║\n╚══════════════════════════╝\n\n"
    for i, u in enumerate(data, 1):
        name = escape(u.get('first_name', 'Unknown'))[:20]
        username = u.get('username', 'Unknown')
        text += f'<b>{get_badge(i)}</b> <a href="https://t.me/{username}">{name}</a>\n│ <b>{u["character_count"]:,}</b>\n└─────────────\n\n'
    await msg.edit_text(text, parse_mode='HTML', disable_web_page_preview=True)

async def leaderboard(update: Update, context: CallbackContext) -> None:
    """Global top 10 users"""
    msg = await update.message.reply_text("Loading...")
    await animate(msg, "Fetching rankings")
    
    cursor = user_collection.aggregate([
        {"$match": {"characters": {"$exists": True, "$type": "array"}}},
        {"$project": {"username": 1, "first_name": 1, "character_count": {"$size": "$characters"}}},
        {"$sort": {"character_count": -1}},
        {"$limit": 10}
    ])
    data = await cursor.to_list(length=10)
    
    if not data:
        await msg.edit_text("║ No data available ║")
        return
    
    text = "╔══════════════════════════╗\n║   GLOBAL CHAMPIONS       ║\n╚══════════════════════════╝\n\n"
    for i, u in enumerate(data, 1):
        name = escape(u.get('first_name', 'Unknown'))[:20]
        username = u.get('username', 'Unknown')
        text += f'<b>{get_badge(i)}</b> <a href="https://t.me/{username}">{name}</a>\n│ <b>{u["character_count"]:,}</b>\n└─────────────\n\n'
    await msg.edit_text(text, parse_mode='HTML', disable_web_page_preview=True)

async def my_rank(update: Update, context: CallbackContext) -> None:
    """Show user's rank"""
    msg = await update.message.reply_text("Loading...")
    await animate(msg, "Calculating rank")
    
    user_data = await user_collection.find_one({'id': update.effective_user.id})
    if not user_data or 'characters' not in user_data:
        await msg.edit_text("║ No profile found ║")
        return
    
    char_count = len(user_data.get('characters', []))
    higher = await user_collection.count_documents({
        "characters": {"$exists": True, "$type": "array"},
        "$expr": {"$gt": [{"$size": "$characters"}, char_count]}
    })
    rank = higher + 1
    total = await user_collection.count_documents({"characters": {"$exists": True, "$type": "array"}})
    
    name = escape(user_data.get('first_name', 'Unknown'))
    text = f"╔══════════════════════════╗\n║   YOUR PROFILE           ║\n╚══════════════════════════╝\n\n"
    text += f"Name: <b>{name}</b>\n"
    text += f"Rank: <b>#{rank:,}</b> / {total:,}\n"
    text += f"Characters: <b>{char_count:,}</b>\n"
    text += f"Badge: <b>{get_badge(rank)}</b>"
    await msg.edit_text(text, parse_mode='HTML')

async def chat_stats(update: Update, context: CallbackContext) -> None:
    """Chat statistics"""
    msg = await update.message.reply_text("Loading...")
    await animate(msg, "Computing stats")
    
    chat_id = update.effective_chat.id
    title = escape(update.effective_chat.title or "This Chat")
    
    user_count = await group_user_totals_collection.count_documents({"group_id": chat_id})
    if user_count == 0:
        await msg.edit_text("║ No activity yet ║")
        return
    
    result = await group_user_totals_collection.aggregate([
        {"$match": {"group_id": chat_id}},
        {"$group": {"_id": None, "total": {"$sum": "$count"}}}
    ]).to_list(length=1)
    total = result[0]['total'] if result else 0
    
    text = f"╔══════════════════════════╗\n║   CHAT STATISTICS        ║\n╚══════════════════════════╝\n\n"
    text += f"Chat: <b>{title}</b>\n"
    text += f"Users: <b>{user_count:,}</b>\n"
    text += f"Total: <b>{total:,}</b>\n"
    text += f"Average: <b>{total/user_count:.1f}</b>"
    await msg.edit_text(text, parse_mode='HTML')

async def stats(update: Update, context: CallbackContext) -> None:
    """Bot statistics (Owner only)"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("║ Unauthorized ║")
        return
    
    msg = await update.message.reply_text("Loading...")
    await animate(msg, "Computing stats")
    
    users = await user_collection.count_documents({})
    groups = len(await group_user_totals_collection.distinct('group_id'))
    collectors = await user_collection.count_documents({"characters": {"$exists": True, "$type": "array"}})
    
    result = await user_collection.aggregate([
        {"$match": {"characters": {"$exists": True, "$type": "array"}}},
        {"$project": {"char_count": {"$size": "$characters"}}},
        {"$group": {"_id": None, "total": {"$sum": "$char_count"}}}
    ]).to_list(length=1)
    total_chars = result[0]['total'] if result else 0
    
    text = "╔══════════════════════════╗\n║  SYSTEM STATISTICS       ║\n╚══════════════════════════╝\n\n"
    text += f"Users: <b>{users:,}</b>\n"
    text += f"Collectors: <b>{collectors:,}</b>\n"
    text += f"Groups: <b>{groups:,}</b>\n"
    text += f"Characters: <b>{total_chars:,}</b>"
    await msg.edit_text(text, parse_mode='HTML')

async def send_users_document(update: Update, context: CallbackContext) -> None:
    """Export users (Sudo only)"""
    if str(update.effective_user.id) not in SUDO_USERS:
        await update.message.reply_text('║ Unauthorized ║')
        return
    
    msg = await update.message.reply_text('Exporting...')
    await animate(msg, "Generating file")
    
    users = await user_collection.find({}).to_list(length=None)
    content = f"User Export - {datetime.now()}\n{'='*50}\n\n"
    for u in users:
        content += f"[{u.get('id')}] {u.get('first_name')} | @{u.get('username')} | {len(u.get('characters', []))} chars\n"
    
    with open('users.txt', 'w', encoding='utf-8') as f:
        f.write(content)
    
    with open('users.txt', 'rb') as f:
        await context.bot.send_document(update.effective_chat.id, f, caption=f"Users: {len(users):,}")
    
    os.remove('users.txt')
    await msg.delete()

async def send_groups_document(update: Update, context: CallbackContext) -> None:
    """Export groups (Sudo only)"""
    if str(update.effective_user.id) not in SUDO_USERS:
        await update.message.reply_text('║ Unauthorized ║')
        return
    
    msg = await update.message.reply_text('Exporting...')
    await animate(msg, "Generating file")
    
    groups = await top_global_groups_collection.find({}).to_list(length=None)
    groups.sort(key=lambda x: x.get('count', 0), reverse=True)
    
    content = f"Group Export - {datetime.now()}\n{'='*50}\n\n"
    for i, g in enumerate(groups, 1):
        content += f"[{i}] {g.get('group_name')} | {g.get('count', 0):,}\n"
    
    with open('groups.txt', 'w', encoding='utf-8') as f:
        f.write(content)
    
    with open('groups.txt', 'rb') as f:
        await context.bot.send_document(update.effective_chat.id, f, caption=f"Groups: {len(groups):,}")
    
    os.remove('groups.txt')
    await msg.delete()

# Register handlers
application.add_handler(CommandHandler('topgroups', global_leaderboard, block=False))
application.add_handler(CommandHandler('topchat', ctop, block=False))
application.add_handler(CommandHandler(['gstop', 'top'], leaderboard, block=False))
application.add_handler(CommandHandler(['myrank', 'rank'], my_rank, block=False))
application.add_handler(CommandHandler('chatstats', chat_stats, block=False))
application.add_handler(CommandHandler('stats', stats, block=False))
application.add_handler(CommandHandler('list', send_users_document, block=False))
application.add_handler(CommandHandler('groups', send_groups_document, block=False))