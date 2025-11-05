import os
from datetime import datetime, timedelta
from html import escape
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import (
    application, OWNER_ID, user_collection, 
    top_global_groups_collection, group_user_totals_collection
)
from shivu import sudo_users as SUDO_USERS


async def global_leaderboard(update: Update, context: CallbackContext) -> None:
    """Top 10 groups globally"""
    cursor = top_global_groups_collection.aggregate([
        {"$project": {"group_name": 1, "count": 1}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ])
    leaderboard_data = await cursor.to_list(length=10)

    leaderboard_message = "<b>Top 10 Global Groups</b>\n"
    leaderboard_message += "-------------------\n\n"

    for i, group in enumerate(leaderboard_data, start=1):
        group_name = escape(group.get('group_name', 'Unknown'))
        if len(group_name) > 20:
            group_name = group_name[:20] + '...'
        count = group['count']
        
        leaderboard_message += f'{i}. <b>{group_name}</b> - {count:,}\n'

    leaderboard_message += "\n-------------------\n"
    leaderboard_message += "Powered by @waifukunbot"

    await update.message.reply_text(leaderboard_message, parse_mode='HTML')


async def ctop(update: Update, context: CallbackContext) -> None:
    """Top 10 users in current chat"""
    chat_id = update.effective_chat.id

    cursor = group_user_totals_collection.aggregate([
        {"$match": {"group_id": chat_id}},
        {"$project": {"username": 1, "first_name": 1, "character_count": "$count"}},
        {"$sort": {"character_count": -1}},
        {"$limit": 10}
    ])
    leaderboard_data = await cursor.to_list(length=10)

    if not leaderboard_data:
        await update.message.reply_text("No data available for this chat yet!")
        return

    leaderboard_message = "<b>Top 10 Users In This Chat</b>\n"
    leaderboard_message += "-------------------\n\n"

    for i, user in enumerate(leaderboard_data, start=1):
        username = user.get('username', 'Unknown')
        first_name = escape(user.get('first_name', 'Unknown'))
        
        if len(first_name) > 20:
            first_name = first_name[:20] + '...'
        character_count = user['character_count']
        
        leaderboard_message += f'{i}. <a href="https://t.me/{username}"><b>{first_name}</b></a> - {character_count:,}\n'

    leaderboard_message += "\n-------------------\n"
    leaderboard_message += "Chat Rankings via @waifukunbot"

    await update.message.reply_text(leaderboard_message, parse_mode='HTML', disable_web_page_preview=True)


async def leaderboard(update: Update, context: CallbackContext) -> None:
    """Global top 10 users by character count"""
    cursor = user_collection.aggregate([
        {"$match": {"characters": {"$exists": True, "$type": "array"}}},
        {"$project": {"username": 1, "first_name": 1, "character_count": {"$size": "$characters"}}},
        {"$sort": {"character_count": -1}},
        {"$limit": 10}
    ])
    leaderboard_data = await cursor.to_list(length=10)

    leaderboard_message = "<b>Top 10 Global Collectors</b>\n"
    leaderboard_message += "-------------------\n\n"

    for i, user in enumerate(leaderboard_data, start=1):
        username = user.get('username', 'Unknown')
        first_name = escape(user.get('first_name', 'Unknown'))
        
        if len(first_name) > 20:
            first_name = first_name[:20] + '...'
        character_count = user['character_count']
        
        leaderboard_message += f'{i}. <a href="https://t.me/{username}"><b>{first_name}</b></a> - {character_count:,}\n'

    leaderboard_message += "\n-------------------\n"
    leaderboard_message += "Global Rankings via @waifukunbot"

    await update.message.reply_text(leaderboard_message, parse_mode='HTML', disable_web_page_preview=True)


async def my_rank(update: Update, context: CallbackContext) -> None:
    """Show user's global rank and stats"""
    user_id = update.effective_user.id
    
    user_data = await user_collection.find_one({'id': user_id})
    
    if not user_data or 'characters' not in user_data:
        await update.message.reply_text("You don't have any characters yet!")
        return
    
    character_count = len(user_data.get('characters', []))
    
    # Get user's rank
    higher_users = await user_collection.count_documents({
        "characters": {"$exists": True, "$type": "array"},
        "$expr": {"$gt": [{"$size": "$characters"}, character_count]}
    })
    
    rank = higher_users + 1
    total_users = await user_collection.count_documents({"characters": {"$exists": True, "$type": "array"}})
    
    first_name = escape(user_data.get('first_name', 'Unknown'))
    
    message = f"<b>Your Statistics</b>\n"
    message += f"-------------------\n\n"
    message += f"Name: {first_name}\n"
    message += f"Global Rank: #{rank:,} / {total_users:,}\n"
    message += f"Characters: {character_count:,}\n\n"
    
    # Percentile
    percentile = ((total_users - rank) / total_users) * 100
    message += f"Top {100 - percentile:.1f}% of collectors\n"
    message += f"-------------------"
    
    await update.message.reply_text(message, parse_mode='HTML')


async def chat_stats(update: Update, context: CallbackContext) -> None:
    """Show current chat statistics"""
    chat_id = update.effective_chat.id
    
    # Count users in this chat
    user_count = await group_user_totals_collection.count_documents({"group_id": chat_id})
    
    # Get total character count for this chat
    pipeline = [
        {"$match": {"group_id": chat_id}},
        {"$group": {"_id": None, "total": {"$sum": "$count"}}}
    ]
    result = await group_user_totals_collection.aggregate(pipeline).to_list(length=1)
    total_chars = result[0]['total'] if result else 0
    
    # Get top user
    top_user = await group_user_totals_collection.find_one(
        {"group_id": chat_id},
        sort=[("count", -1)]
    )
    
    message = f"<b>Chat Statistics</b>\n"
    message += f"-------------------\n\n"
    message += f"Active Users: {user_count:,}\n"
    message += f"Total Characters: {total_chars:,}\n"
    
    if top_user:
        top_name = escape(top_user.get('first_name', 'Unknown'))
        message += f"Top Collector: {top_name} ({top_user['count']:,})\n"
    
    if user_count > 0:
        avg = total_chars / user_count
        message += f"Average per User: {avg:.1f}\n"
    
    message += f"\n-------------------"
    
    await update.message.reply_text(message, parse_mode='HTML')


async def send_users_document(update: Update, context: CallbackContext) -> None:
    """Export all users to a text file (Sudo only)"""
    if str(update.effective_user.id) not in SUDO_USERS:
        await update.message.reply_text('This command is only for sudo users.')
        return
    
    await update.message.reply_text('Generating users list...')
    
    cursor = user_collection.find({})
    users = []
    async for document in cursor:
        users.append(document)
    
    user_list = f"Total Users: {len(users)}\n"
    user_list += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    user_list += "="*50 + "\n\n"
    
    for user in users:
        user_id = user.get('id', 'N/A')
        first_name = user.get('first_name', 'Unknown')
        username = user.get('username', 'N/A')
        char_count = len(user.get('characters', []))
        user_list += f"ID: {user_id} | {first_name} | @{username} | {char_count} chars\n"
    
    with open('users.txt', 'w', encoding='utf-8') as f:
        f.write(user_list)
    
    with open('users.txt', 'rb') as f:
        await context.bot.send_document(
            chat_id=update.effective_chat.id, 
            document=f,
            caption=f"User Database Export\nTotal: {len(users):,} users"
        )
    
    os.remove('users.txt')


async def send_groups_document(update: Update, context: CallbackContext) -> None:
    """Export all groups to a text file (Sudo only)"""
    if str(update.effective_user.id) not in SUDO_USERS:
        await update.message.reply_text('This command is only for sudo users.')
        return
    
    await update.message.reply_text('Generating groups list...')
    
    cursor = top_global_groups_collection.find({})
    groups = []
    async for document in cursor:
        groups.append(document)
    
    group_list = f"Total Groups: {len(groups)}\n"
    group_list += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    group_list += "="*50 + "\n\n"
    
    for group in groups:
        group_name = group.get('group_name', 'Unknown')
        count = group.get('count', 0)
        group_list += f"{group_name} | {count} characters\n"
    
    with open('groups.txt', 'w', encoding='utf-8') as f:
        f.write(group_list)
    
    with open('groups.txt', 'rb') as f:
        await context.bot.send_document(
            chat_id=update.effective_chat.id, 
            document=f,
            caption=f"Group Database Export\nTotal: {len(groups):,} groups"
        )
    
    os.remove('groups.txt')


async def stats(update: Update, context: CallbackContext) -> None:
    """Show bot statistics (Owner only)"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    user_count = await user_collection.count_documents({})
    group_count = await group_user_totals_collection.distinct('group_id')
    
    # Count users with characters
    users_with_chars = await user_collection.count_documents({"characters": {"$exists": True, "$type": "array"}})
    
    # Total characters across all users
    pipeline = [
        {"$match": {"characters": {"$exists": True, "$type": "array"}}},
        {"$project": {"char_count": {"$size": "$characters"}}},
        {"$group": {"_id": None, "total": {"$sum": "$char_count"}}}
    ]
    result = await user_collection.aggregate(pipeline).to_list(length=1)
    total_chars = result[0]['total'] if result else 0

    message = "<b>Bot Statistics</b>\n"
    message += "-------------------\n\n"
    message += f"Total Users: {user_count:,}\n"
    message += f"Active Collectors: {users_with_chars:,}\n"
    message += f"Total Groups: {len(group_count):,}\n"
    message += f"Total Characters: {total_chars:,}\n\n"
    
    if users_with_chars > 0:
        avg = total_chars / users_with_chars
        message += f"Avg per Active User: {avg:.1f}\n"
    
    message += f"\n-------------------\n"
    message += f"@waifukunbot"

    await update.message.reply_text(message, parse_mode='HTML')


async def top_collectors(update: Update, context: CallbackContext) -> None:
    """Show top 20 collectors"""
    limit = 20
    cursor = user_collection.aggregate([
        {"$match": {"characters": {"$exists": True, "$type": "array"}}},
        {"$project": {"username": 1, "first_name": 1, "character_count": {"$size": "$characters"}}},
        {"$sort": {"character_count": -1}},
        {"$limit": limit}
    ])
    leaderboard_data = await cursor.to_list(length=limit)

    leaderboard_message = "<b>Top 20 Global Collectors</b>\n"
    leaderboard_message += "-------------------\n\n"

    for i, user in enumerate(leaderboard_data, start=1):
        username = user.get('username', 'Unknown')
        first_name = escape(user.get('first_name', 'Unknown'))
        
        if len(first_name) > 18:
            first_name = first_name[:18] + '...'
        character_count = user['character_count']
        
        leaderboard_message += f'{i}. <a href="https://t.me/{username}">{first_name}</a> - {character_count:,}\n'

    leaderboard_message += "\n-------------------\n"
    leaderboard_message += "Extended Rankings via @waifukunbot"

    await update.message.reply_text(leaderboard_message, parse_mode='HTML', disable_web_page_preview=True)


# Register handlers
application.add_handler(CommandHandler('topgroups', global_leaderboard, block=False))
application.add_handler(CommandHandler('topchat', ctop, block=False))
application.add_handler(CommandHandler('gstop', leaderboard, block=False))
application.add_handler(CommandHandler('top', leaderboard, block=False))  # Alias
application.add_handler(CommandHandler('myrank', my_rank, block=False))
application.add_handler(CommandHandler('rank', my_rank, block=False))  # Alias
application.add_handler(CommandHandler('chatstats', chat_stats, block=False))
application.add_handler(CommandHandler('top20', top_collectors, block=False))
application.add_handler(CommandHandler('stats', stats, block=False))
application.add_handler(CommandHandler('list', send_users_document, block=False))
application.add_handler(CommandHandler('groups', send_groups_document, block=False))