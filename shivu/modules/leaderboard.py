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


# Utility function for formatting numbers
def format_number(num):
    """Format numbers with K, M suffixes"""
    if num >= 1_000_000:
        return f"{num/1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num/1_000:.1f}K"
    return f"{num:,}"


async def global_leaderboard(update: Update, context: CallbackContext) -> None:
    """Top 10 groups globally"""
    cursor = top_global_groups_collection.aggregate([
        {"$project": {"group_name": 1, "count": 1}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ])
    leaderboard_data = await cursor.to_list(length=10)

    if not leaderboard_data:
        await update.message.reply_text("No group data available yet!")
        return

    leaderboard_message = "<b>Top 10 Global Groups</b>\n"
    leaderboard_message += "-------------------\n\n"

    for i, group in enumerate(leaderboard_data, start=1):
        group_name = escape(group.get('group_name', 'Unknown'))
        if len(group_name) > 25:
            group_name = group_name[:25] + '...'
        count = group['count']
        
        leaderboard_message += f'{i}. {group_name}\n'
        leaderboard_message += f'   Characters: {count:,}\n\n'

    leaderboard_message += "-------------------\n"
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
        
        leaderboard_message += f'{i}. <a href="https://t.me/{username}">{first_name}</a>\n'
        leaderboard_message += f'   Characters: {character_count:,}\n\n'

    leaderboard_message += "-------------------\n"
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

    if not leaderboard_data:
        await update.message.reply_text("No collector data available yet!")
        return

    leaderboard_message = "<b>Top 10 Global Collectors</b>\n"
    leaderboard_message += "-------------------\n\n"

    for i, user in enumerate(leaderboard_data, start=1):
        username = user.get('username', 'Unknown')
        first_name = escape(user.get('first_name', 'Unknown'))
        
        if len(first_name) > 20:
            first_name = first_name[:20] + '...'
        character_count = user['character_count']
        
        leaderboard_message += f'{i}. <a href="https://t.me/{username}">{first_name}</a>\n'
        leaderboard_message += f'   Characters: {character_count:,}\n\n'

    leaderboard_message += "-------------------\n"
    leaderboard_message += "Global Rankings via @waifukunbot"

    await update.message.reply_text(leaderboard_message, parse_mode='HTML', disable_web_page_preview=True)


async def my_rank(update: Update, context: CallbackContext) -> None:
    """Show user's global rank and stats"""
    user_id = update.effective_user.id
    
    user_data = await user_collection.find_one({'id': user_id})
    
    if not user_data or 'characters' not in user_data:
        await update.message.reply_text("You don't have any characters yet!\nStart collecting to appear in rankings.")
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
    
    # Calculate percentile
    percentile = ((total_users - rank) / total_users) * 100
    
    message = f"<b>Your Statistics</b>\n"
    message += f"-------------------\n\n"
    message += f"<b>Name:</b> {first_name}\n"
    message += f"<b>User ID:</b> {user_id}\n"
    message += f"<b>Global Rank:</b> #{rank:,} of {total_users:,}\n"
    message += f"<b>Characters:</b> {character_count:,}\n"
    message += f"<b>Percentile:</b> Top {100 - percentile:.1f}%\n\n"
    
    # Rank category
    if rank == 1:
        message += "<b>Status:</b> CHAMPION\n"
    elif rank <= 10:
        message += "<b>Status:</b> Elite Collector\n"
    elif rank <= 50:
        message += "<b>Status:</b> Master Collector\n"
    elif rank <= 100:
        message += "<b>Status:</b> Expert Collector\n"
    elif percentile >= 90:
        message += "<b>Status:</b> Advanced Collector\n"
    else:
        message += "<b>Status:</b> Collector\n"
    
    message += f"-------------------"
    
    await update.message.reply_text(message, parse_mode='HTML')


async def chat_stats(update: Update, context: CallbackContext) -> None:
    """Show current chat statistics"""
    chat_id = update.effective_chat.id
    chat_title = escape(update.effective_chat.title or "This Chat")
    
    # Count users in this chat
    user_count = await group_user_totals_collection.count_documents({"group_id": chat_id})
    
    if user_count == 0:
        await update.message.reply_text("No activity in this chat yet!")
        return
    
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
    
    # Calculate average
    avg = total_chars / user_count if user_count > 0 else 0
    
    message = f"<b>Chat Statistics</b>\n"
    message += f"-------------------\n\n"
    message += f"<b>Chat:</b> {chat_title}\n"
    message += f"<b>Active Users:</b> {user_count:,}\n"
    message += f"<b>Total Characters:</b> {total_chars:,}\n"
    message += f"<b>Average per User:</b> {avg:.1f}\n\n"
    
    if top_user:
        top_name = escape(top_user.get('first_name', 'Unknown'))
        top_username = top_user.get('username', '')
        if top_username:
            message += f"<b>Top Collector:</b> <a href='https://t.me/{top_username}'>{top_name}</a>\n"
        else:
            message += f"<b>Top Collector:</b> {top_name}\n"
        message += f"<b>Their Count:</b> {top_user['count']:,}\n"
    
    message += f"\n-------------------"
    
    await update.message.reply_text(message, parse_mode='HTML', disable_web_page_preview=True)


async def compare(update: Update, context: CallbackContext) -> None:
    """Compare your stats with another user"""
    if not context.args:
        await update.message.reply_text(
            "Usage: /compare <username or user_id>\n"
            "Example: /compare username or /compare 123456789"
        )
        return
    
    user_id = update.effective_user.id
    target_identifier = context.args[0].replace('@', '')
    
    # Get current user data
    user_data = await user_collection.find_one({'id': user_id})
    
    if not user_data or 'characters' not in user_data:
        await update.message.reply_text("You don't have any characters yet!")
        return
    
    # Try to find target user by username or ID
    if target_identifier.isdigit():
        target_data = await user_collection.find_one({'id': int(target_identifier)})
    else:
        target_data = await user_collection.find_one({'username': target_identifier})
    
    if not target_data or 'characters' not in target_data:
        await update.message.reply_text(f"User '{target_identifier}' not found or has no characters!")
        return
    
    user_count = len(user_data.get('characters', []))
    target_count = len(target_data.get('characters', []))
    
    user_name = escape(user_data.get('first_name', 'You'))
    target_name = escape(target_data.get('first_name', 'Unknown'))
    
    difference = abs(user_count - target_count)
    
    message = f"<b>Comparison</b>\n"
    message += f"-------------------\n\n"
    message += f"<b>{user_name}:</b> {user_count:,} characters\n"
    message += f"<b>{target_name}:</b> {target_count:,} characters\n\n"
    message += f"<b>Difference:</b> {difference:,} characters\n\n"
    
    if user_count > target_count:
        message += f"{user_name} is ahead by {difference:,}!"
    elif target_count > user_count:
        message += f"{target_name} is ahead by {difference:,}!"
    else:
        message += "You're tied!"
    
    message += f"\n-------------------"
    
    await update.message.reply_text(message, parse_mode='HTML')


async def recent_collectors(update: Update, context: CallbackContext) -> None:
    """Show users who recently gained characters"""
    # This shows top collectors from the last 24 hours based on activity
    chat_id = update.effective_chat.id
    
    cursor = group_user_totals_collection.aggregate([
        {"$match": {"group_id": chat_id}},
        {"$project": {"username": 1, "first_name": 1, "character_count": "$count"}},
        {"$sort": {"character_count": -1}},
        {"$limit": 5}
    ])
    recent_data = await cursor.to_list(length=5)
    
    if not recent_data:
        await update.message.reply_text("No recent activity in this chat!")
        return
    
    message = "<b>Top 5 Active Collectors</b>\n"
    message += "-------------------\n\n"
    
    for i, user in enumerate(recent_data, start=1):
        username = user.get('username', 'Unknown')
        first_name = escape(user.get('first_name', 'Unknown'))
        character_count = user['character_count']
        
        message += f"{i}. <a href='https://t.me/{username}'>{first_name}</a>\n"
        message += f"   Characters: {character_count:,}\n\n"
    
    message += "-------------------"
    
    await update.message.reply_text(message, parse_mode='HTML', disable_web_page_preview=True)


async def group_rank(update: Update, context: CallbackContext) -> None:
    """Show current group's global rank"""
    chat_id = update.effective_chat.id
    chat_title = escape(update.effective_chat.title or "This Chat")
    
    # Get this group's data
    group_data = await top_global_groups_collection.find_one({"_id": chat_id})
    
    if not group_data:
        await update.message.reply_text("This group hasn't been ranked yet!")
        return
    
    group_count = group_data.get('count', 0)
    
    # Calculate rank
    higher_groups = await top_global_groups_collection.count_documents({"count": {"$gt": group_count}})
    rank = higher_groups + 1
    total_groups = await top_global_groups_collection.count_documents({})
    
    message = f"<b>Group Rankings</b>\n"
    message += f"-------------------\n\n"
    message += f"<b>Group:</b> {chat_title}\n"
    message += f"<b>Global Rank:</b> #{rank:,} of {total_groups:,}\n"
    message += f"<b>Characters:</b> {group_count:,}\n\n"
    
    percentile = ((total_groups - rank) / total_groups) * 100 if total_groups > 0 else 0
    message += f"<b>Percentile:</b> Top {100 - percentile:.1f}%\n"
    
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
    
    # Sort by count
    groups.sort(key=lambda x: x.get('count', 0), reverse=True)
    
    group_list = f"Total Groups: {len(groups)}\n"
    group_list += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    group_list += "="*50 + "\n\n"
    
    for i, group in enumerate(groups, start=1):
        group_name = group.get('group_name', 'Unknown')
        count = group.get('count', 0)
        group_list += f"{i}. {group_name} | {count:,} characters\n"
    
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

    # Get top collector
    top_collector = await user_collection.find_one(
        {"characters": {"$exists": True, "$type": "array"}},
        sort=[("characters", -1)]
    )

    message = "<b>Bot Statistics</b>\n"
    message += "-------------------\n\n"
    message += f"<b>Total Users:</b> {user_count:,}\n"
    message += f"<b>Active Collectors:</b> {users_with_chars:,}\n"
    message += f"<b>Total Groups:</b> {len(group_count):,}\n"
    message += f"<b>Total Characters:</b> {total_chars:,}\n\n"
    
    if users_with_chars > 0:
        avg = total_chars / users_with_chars
        message += f"<b>Avg per User:</b> {avg:.1f}\n"
    
    if top_collector:
        top_name = escape(top_collector.get('first_name', 'Unknown'))
        top_count = len(top_collector.get('characters', []))
        message += f"<b>Top Collector:</b> {top_name} ({top_count:,})\n"
    
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

    if not leaderboard_data:
        await update.message.reply_text("No collector data available yet!")
        return

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


async def search_user(update: Update, context: CallbackContext) -> None:
    """Search for a user's stats by username or ID"""
    if not context.args:
        await update.message.reply_text(
            "Usage: /search <username or user_id>\n"
            "Example: /search username or /search 123456789"
        )
        return
    
    identifier = context.args[0].replace('@', '')
    
    # Try to find user by username or ID
    if identifier.isdigit():
        user_data = await user_collection.find_one({'id': int(identifier)})
    else:
        user_data = await user_collection.find_one({'username': identifier})
    
    if not user_data:
        await update.message.reply_text(f"User '{identifier}' not found!")
        return
    
    first_name = escape(user_data.get('first_name', 'Unknown'))
    username = user_data.get('username', 'N/A')
    user_id = user_data.get('id', 'N/A')
    character_count = len(user_data.get('characters', []))
    
    # Get user's rank
    if character_count > 0:
        higher_users = await user_collection.count_documents({
            "characters": {"$exists": True, "$type": "array"},
            "$expr": {"$gt": [{"$size": "$characters"}, character_count]}
        })
        rank = higher_users + 1
        total_users = await user_collection.count_documents({"characters": {"$exists": True, "$type": "array"}})
    else:
        rank = "Unranked"
        total_users = 0
    
    message = f"<b>User Information</b>\n"
    message += f"-------------------\n\n"
    message += f"<b>Name:</b> {first_name}\n"
    message += f"<b>Username:</b> @{username}\n"
    message += f"<b>User ID:</b> {user_id}\n"
    message += f"<b>Characters:</b> {character_count:,}\n"
    
    if isinstance(rank, int):
        message += f"<b>Global Rank:</b> #{rank:,} of {total_users:,}\n"
    else:
        message += f"<b>Global Rank:</b> {rank}\n"
    
    message += f"\n-------------------"
    
    await update.message.reply_text(message, parse_mode='HTML')


async def help_command(update: Update, context: CallbackContext) -> None:
    """Show all available commands"""
    message = "<b>Available Commands</b>\n"
    message += "-------------------\n\n"
    message += "<b>Leaderboards:</b>\n"
    message += "/topgroups - Top 10 global groups\n"
    message += "/topchat - Top 10 users in this chat\n"
    message += "/gstop or /top - Top 10 global collectors\n"
    message += "/top20 - Top 20 global collectors\n\n"
    message += "<b>Personal Stats:</b>\n"
    message += "/myrank or /rank - Your global rank\n"
    message += "/compare <user> - Compare with another user\n"
    message += "/search <user> - Search user stats\n\n"
    message += "<b>Group Stats:</b>\n"
    message += "/chatstats - Current chat statistics\n"
    message += "/grouprank - This group's global rank\n"
    message += "/recent - Recently active collectors\n\n"
    message += "<b>Admin Commands:</b>\n"
    message += "/stats - Bot statistics (Owner)\n"
    message += "/list - Export users list (Sudo)\n"
    message += "/groups - Export groups list (Sudo)\n\n"
    message += "-------------------\n"
    message += "Bot by @waifukunbot"
    
    await update.message.reply_text(message, parse_mode='HTML')


# Register all handlers
application.add_handler(CommandHandler('topgroups', global_leaderboard, block=False))
application.add_handler(CommandHandler('topchat', ctop, block=False))
application.add_handler(CommandHandler('gstop', leaderboard, block=False))
application.add_handler(CommandHandler('top', leaderboard, block=False))
application.add_handler(CommandHandler('myrank', my_rank, block=False))
application.add_handler(CommandHandler('rank', my_rank, block=False))
application.add_handler(CommandHandler('chatstats', chat_stats, block=False))
application.add_handler(CommandHandler('top20', top_collectors, block=False))
application.add_handler(CommandHandler('compare', compare, block=False))
application.add_handler(CommandHandler('recent', recent_collectors, block=False))
application.add_handler(CommandHandler('grouprank', group_rank, block=False))
application.add_handler(CommandHandler('search', search_user, block=False))
application.add_handler(CommandHandler('stats', stats, block=False))
application.add_handler(CommandHandler('list', send_users_document, block=False))
application.add_handler(CommandHandler('groups', send_groups_document, block=False))
application.add_handler(CommandHandler('hel', help_command, block=False))
application.add_handler(CommandHandler('leaderhelp', help_command, block=False))