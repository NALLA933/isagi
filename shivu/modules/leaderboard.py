import os
import asyncio
from datetime import datetime, timedelta
from html import escape
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import (
    application, OWNER_ID, user_collection, 
    top_global_groups_collection, group_user_totals_collection
)
from shivu import sudo_users as SUDO_USERS


# Animation frames
LOADING_FRAMES = ["◜", "◝", "◞", "◟"]
PROGRESS_FRAMES = ["▱▱▱▱▱▱▱▱▱▱", "▰▱▱▱▱▱▱▱▱▱", "▰▰▱▱▱▱▱▱▱▱", "▰▰▰▱▱▱▱▱▱▱", 
                   "▰▰▰▰▱▱▱▱▱▱", "▰▰▰▰▰▱▱▱▱▱", "▰▰▰▰▰▰▱▱▱▱", "▰▰▰▰▰▰▰▱▱▱",
                   "▰▰▰▰▰▰▰▰▱▱", "▰▰▰▰▰▰▰▰▰▱", "▰▰▰▰▰▰▰▰▰▰"]
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
DOTS_FRAMES = ["   ", ".  ", ".. ", "..."]
PULSE_FRAMES = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█", "▇", "▆", "▅", "▄", "▃", "▂"]


def format_number(num):
    """Format numbers with K, M suffixes"""
    if num >= 1_000_000:
        return f"{num/1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num/1_000:.1f}K"
    return f"{num:,}"


def get_rank_badge(rank):
    """Get badge based on rank"""
    if rank == 1:
        return "[★ 1ST ★]"
    elif rank == 2:
        return "[★ 2ND ★]"
    elif rank == 3:
        return "[★ 3RD ★]"
    elif rank <= 10:
        return f"[TOP {rank}]"
    else:
        return f"[#{rank}]"


async def animate_loading(message, stages):
    """Advanced loading animation with multiple stages"""
    for stage_text in stages:
        for i in range(3):
            for frame in SPINNER_FRAMES:
                try:
                    await message.edit_text(f"{frame} {stage_text}{DOTS_FRAMES[i]}", parse_mode='HTML')
                    await asyncio.sleep(0.1)
                except:
                    pass


async def animate_progress_bar(message, text):
    """Animate a progress bar"""
    for frame in PROGRESS_FRAMES:
        try:
            await message.edit_text(f"{text}\n\n{frame}", parse_mode='HTML')
            await asyncio.sleep(0.15)
        except:
            pass


async def global_leaderboard(update: Update, context: CallbackContext) -> None:
    """Top 10 groups globally with advanced animation"""
    loading_msg = await update.message.reply_text("Initializing...")
    
    # Multi-stage loading animation
    stages = [
        "Connecting to database",
        "Fetching global data",
        "Sorting rankings",
        "Preparing display"
    ]
    await animate_loading(loading_msg, stages)
    
    cursor = top_global_groups_collection.aggregate([
        {"$project": {"group_name": 1, "count": 1}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ])
    leaderboard_data = await cursor.to_list(length=10)

    if not leaderboard_data:
        await loading_msg.edit_text("║ No group data available yet ║")
        return

    # Progress bar animation
    await animate_progress_bar(loading_msg, "Rendering leaderboard")
    
    leaderboard_message = "╔════════════════════════════════╗\n"
    leaderboard_message += "║                                ║\n"
    leaderboard_message += "║     TOP GLOBAL GROUPS          ║\n"
    leaderboard_message += "║                                ║\n"
    leaderboard_message += "╚════════════════════════════════╝\n\n"

    for i, group in enumerate(leaderboard_data, start=1):
        group_name = escape(group.get('group_name', 'Unknown'))
        if len(group_name) > 25:
            group_name = group_name[:25] + '...'
        count = group['count']
        
        rank_badge = get_rank_badge(i)
        
        # Animated bars
        bar_length = min(int(count / leaderboard_data[0]['count'] * 20), 20)
        bar = "▓" * bar_length + "░" * (20 - bar_length)
        
        leaderboard_message += f'<b>{rank_badge}</b> {group_name}\n'
        leaderboard_message += f'│ Characters: <b>{count:,}</b>\n'
        leaderboard_message += f'│ {bar}\n'
        leaderboard_message += f'└─────────────────────────\n\n'

    leaderboard_message += "═══════════════════════════════════\n"
    leaderboard_message += "         Powered by @waifukunbot"

    await loading_msg.edit_text(leaderboard_message, parse_mode='HTML')


async def ctop(update: Update, context: CallbackContext) -> None:
    """Top 10 users in current chat with advanced animation"""
    chat_id = update.effective_chat.id
    
    loading_msg = await update.message.reply_text("Scanning chat...")

    stages = [
        "Analyzing members",
        "Calculating rankings",
        "Compiling results"
    ]
    await animate_loading(loading_msg, stages)

    cursor = group_user_totals_collection.aggregate([
        {"$match": {"group_id": chat_id}},
        {"$project": {"username": 1, "first_name": 1, "character_count": "$count"}},
        {"$sort": {"character_count": -1}},
        {"$limit": 10}
    ])
    leaderboard_data = await cursor.to_list(length=10)

    if not leaderboard_data:
        await loading_msg.edit_text("║ No data available for this chat ║")
        return

    await animate_progress_bar(loading_msg, "Building leaderboard")
    
    leaderboard_message = "╔════════════════════════════════╗\n"
    leaderboard_message += "║                                ║\n"
    leaderboard_message += "║      TOP CHAT COLLECTORS       ║\n"
    leaderboard_message += "║                                ║\n"
    leaderboard_message += "╚════════════════════════════════╝\n\n"

    for i, user in enumerate(leaderboard_data, start=1):
        username = user.get('username', 'Unknown')
        first_name = escape(user.get('first_name', 'Unknown'))
        
        if len(first_name) > 20:
            first_name = first_name[:20] + '...'
        character_count = user['character_count']
        
        rank_badge = get_rank_badge(i)
        
        # Progress bar
        max_count = leaderboard_data[0]['character_count']
        bar_length = min(int(character_count / max_count * 20), 20) if max_count > 0 else 0
        bar = "▓" * bar_length + "░" * (20 - bar_length)
        
        leaderboard_message += f'<b>{rank_badge}</b> <a href="https://t.me/{username}">{first_name}</a>\n'
        leaderboard_message += f'│ Count: <b>{character_count:,}</b>\n'
        leaderboard_message += f'│ {bar}\n'
        leaderboard_message += f'└─────────────────────────\n\n'

    leaderboard_message += "═══════════════════════════════════\n"
    leaderboard_message += "            Chat Rankings"

    await loading_msg.edit_text(leaderboard_message, parse_mode='HTML', disable_web_page_preview=True)


async def leaderboard(update: Update, context: CallbackContext) -> None:
    """Global top 10 users with advanced animation"""
    loading_msg = await update.message.reply_text("Loading global rankings...")
    
    stages = [
        "Querying database",
        "Processing collectors",
        "Ranking champions",
        "Finalizing results"
    ]
    await animate_loading(loading_msg, stages)
    
    cursor = user_collection.aggregate([
        {"$match": {"characters": {"$exists": True, "$type": "array"}}},
        {"$project": {"username": 1, "first_name": 1, "character_count": {"$size": "$characters"}}},
        {"$sort": {"character_count": -1}},
        {"$limit": 10}
    ])
    leaderboard_data = await cursor.to_list(length=10)

    if not leaderboard_data:
        await loading_msg.edit_text("║ No collector data available ║")
        return

    await animate_progress_bar(loading_msg, "Rendering champions list")
    
    leaderboard_message = "╔════════════════════════════════╗\n"
    leaderboard_message += "║                                ║\n"
    leaderboard_message += "║      GLOBAL CHAMPIONS          ║\n"
    leaderboard_message += "║      HALL OF FAME              ║\n"
    leaderboard_message += "║                                ║\n"
    leaderboard_message += "╚════════════════════════════════╝\n\n"

    for i, user in enumerate(leaderboard_data, start=1):
        username = user.get('username', 'Unknown')
        first_name = escape(user.get('first_name', 'Unknown'))
        
        if len(first_name) > 20:
            first_name = first_name[:20] + '...'
        character_count = user['character_count']
        
        rank_badge = get_rank_badge(i)
        
        # Dynamic progress bar
        max_count = leaderboard_data[0]['character_count']
        bar_length = min(int(character_count / max_count * 20), 20) if max_count > 0 else 0
        bar = "▓" * bar_length + "░" * (20 - bar_length)
        
        leaderboard_message += f'<b>{rank_badge}</b> <a href="https://t.me/{username}">{first_name}</a>\n'
        leaderboard_message += f'│ Collection: <b>{character_count:,}</b>\n'
        leaderboard_message += f'│ {bar}\n'
        leaderboard_message += f'└─────────────────────────\n\n'

    leaderboard_message += "═══════════════════════════════════\n"
    leaderboard_message += "         Global Rankings"

    await loading_msg.edit_text(leaderboard_message, parse_mode='HTML', disable_web_page_preview=True)


async def my_rank(update: Update, context: CallbackContext) -> None:
    """Show user's global rank with advanced animation"""
    user_id = update.effective_user.id
    
    loading_msg = await update.message.reply_text("Retrieving profile...")
    
    stages = [
        "Searching database",
        "Loading profile",
        "Computing statistics",
        "Calculating rank"
    ]
    await animate_loading(loading_msg, stages)
    
    user_data = await user_collection.find_one({'id': user_id})
    
    if not user_data or 'characters' not in user_data:
        await loading_msg.edit_text(
            "╔════════════════════════════════╗\n"
            "║ NO PROFILE FOUND               ║\n"
            "╚════════════════════════════════╝\n\n"
            "Start collecting to appear in rankings!"
        )
        return
    
    await animate_progress_bar(loading_msg, "Analyzing your position")
    
    character_count = len(user_data.get('characters', []))
    
    higher_users = await user_collection.count_documents({
        "characters": {"$exists": True, "$type": "array"},
        "$expr": {"$gt": [{"$size": "$characters"}, character_count]}
    })
    
    rank = higher_users + 1
    total_users = await user_collection.count_documents({"characters": {"$exists": True, "$type": "array"}})
    
    first_name = escape(user_data.get('first_name', 'Unknown'))
    
    percentile = ((total_users - rank) / total_users) * 100
    
    # Determine status
    if rank == 1:
        status = "CHAMPION"
        tier = "SSS+"
    elif rank <= 10:
        status = "ELITE COLLECTOR"
        tier = "S+"
    elif rank <= 50:
        status = "MASTER COLLECTOR"
        tier = "A+"
    elif rank <= 100:
        status = "EXPERT COLLECTOR"
        tier = "B+"
    elif percentile >= 90:
        status = "ADVANCED COLLECTOR"
        tier = "C+"
    else:
        status = "COLLECTOR"
        tier = "D"
    
    message = "╔════════════════════════════════╗\n"
    message += "║                                ║\n"
    message += "║        PROFILE ANALYSIS        ║\n"
    message += "║                                ║\n"
    message += "╚════════════════════════════════╝\n\n"
    message += f"┌─ USER INFORMATION\n"
    message += f"│\n"
    message += f"├─ Name: <b>{first_name}</b>\n"
    message += f"├─ User ID: <code>{user_id}</code>\n"
    message += f"├─ Tier: <b>[{tier}]</b>\n"
    message += f"└─ Status: <b>{status}</b>\n\n"
    message += f"┌─ STATISTICS\n"
    message += f"│\n"
    message += f"├─ Global Rank: <b>#{rank:,}</b> / {total_users:,}\n"
    message += f"├─ Characters: <b>{character_count:,}</b>\n"
    message += f"└─ Percentile: <b>Top {100 - percentile:.1f}%</b>\n\n"
    
    # Progress bar for percentile
    bar_length = min(int(percentile / 5), 20)
    bar = "▓" * bar_length + "░" * (20 - bar_length)
    message += f"Progress:\n{bar}\n\n"
    
    message += "═══════════════════════════════════\n"
    message += "           Keep Collecting!"
    
    await loading_msg.edit_text(message, parse_mode='HTML')


async def chat_stats(update: Update, context: CallbackContext) -> None:
    """Show current chat statistics with advanced animation"""
    chat_id = update.effective_chat.id
    chat_title = escape(update.effective_chat.title or "This Chat")
    
    loading_msg = await update.message.reply_text("Initializing analysis...")
    
    stages = [
        "Scanning chat members",
        "Collecting data",
        "Computing totals",
        "Generating report"
    ]
    await animate_loading(loading_msg, stages)
    
    user_count = await group_user_totals_collection.count_documents({"group_id": chat_id})
    
    if user_count == 0:
        await loading_msg.edit_text("║ No activity in this chat yet ║")
        return
    
    await animate_progress_bar(loading_msg, "Processing statistics")
    
    pipeline = [
        {"$match": {"group_id": chat_id}},
        {"$group": {"_id": None, "total": {"$sum": "$count"}}}
    ]
    result = await group_user_totals_collection.aggregate(pipeline).to_list(length=1)
    total_chars = result[0]['total'] if result else 0
    
    top_user = await group_user_totals_collection.find_one(
        {"group_id": chat_id},
        sort=[("count", -1)]
    )
    
    avg = total_chars / user_count if user_count > 0 else 0
    
    message = "╔════════════════════════════════╗\n"
    message += "║                                ║\n"
    message += "║       CHAT STATISTICS          ║\n"
    message += "║                                ║\n"
    message += "╚════════════════════════════════╝\n\n"
    message += f"┌─ OVERVIEW\n"
    message += f"│\n"
    message += f"├─ Chat: <b>{chat_title}</b>\n"
    message += f"├─ Active Users: <b>{user_count:,}</b>\n"
    message += f"├─ Total Characters: <b>{total_chars:,}</b>\n"
    message += f"└─ Average per User: <b>{avg:.1f}</b>\n\n"
    
    if top_user:
        top_name = escape(top_user.get('first_name', 'Unknown'))
        top_username = top_user.get('username', '')
        message += f"┌─ TOP COLLECTOR\n"
        message += f"│\n"
        if top_username:
            message += f"├─ Name: <a href='https://t.me/{top_username}'>{top_name}</a>\n"
        else:
            message += f"├─ Name: {top_name}\n"
        message += f"└─ Count: <b>{top_user['count']:,}</b>\n\n"
    
    message += "═══════════════════════════════════"
    
    await loading_msg.edit_text(message, parse_mode='HTML', disable_web_page_preview=True)


async def compare(update: Update, context: CallbackContext) -> None:
    """Compare stats with animation"""
    if not context.args:
        await update.message.reply_text(
            "╔════════════════════════════════╗\n"
            "║ USAGE: /compare <username>     ║\n"
            "╚════════════════════════════════╝\n\n"
            "Example: /compare username\n"
            "or: /compare 123456789"
        )
        return
    
    loading_msg = await update.message.reply_text("Processing comparison...")
    
    stages = [
        "Locating users",
        "Fetching data",
        "Calculating difference"
    ]
    await animate_loading(loading_msg, stages)
    
    user_id = update.effective_user.id
    target_identifier = context.args[0].replace('@', '')
    
    user_data = await user_collection.find_one({'id': user_id})
    
    if not user_data or 'characters' not in user_data:
        await loading_msg.edit_text("║ You don't have any characters yet ║")
        return
    
    if target_identifier.isdigit():
        target_data = await user_collection.find_one({'id': int(target_identifier)})
    else:
        target_data = await user_collection.find_one({'username': target_identifier})
    
    if not target_data or 'characters' not in target_data:
        await loading_msg.edit_text(f"║ User '{target_identifier}' not found ║")
        return
    
    await animate_progress_bar(loading_msg, "Rendering comparison")
    
    user_count = len(user_data.get('characters', []))
    target_count = len(target_data.get('characters', []))
    
    user_name = escape(user_data.get('first_name', 'You'))
    target_name = escape(target_data.get('first_name', 'Unknown'))
    
    difference = abs(user_count - target_count)
    
    message = "╔════════════════════════════════╗\n"
    message += "║                                ║\n"
    message += "║      HEAD-TO-HEAD COMPARISON   ║\n"
    message += "║                                ║\n"
    message += "╚════════════════════════════════╝\n\n"
    
    # Visual comparison bars
    max_count = max(user_count, target_count)
    user_bar_length = min(int(user_count / max_count * 20), 20) if max_count > 0 else 0
    target_bar_length = min(int(target_count / max_count * 20), 20) if max_count > 0 else 0
    user_bar = "▓" * user_bar_length + "░" * (20 - user_bar_length)
    target_bar = "▓" * target_bar_length + "░" * (20 - target_bar_length)
    
    message += f"┌─ PLAYER 1: <b>{user_name}</b>\n"
    message += f"│ Count: <b>{user_count:,}</b>\n"
    message += f"│ {user_bar}\n"
    message += f"└─────────────────────────\n\n"
    
    message += f"┌─ PLAYER 2: <b>{target_name}</b>\n"
    message += f"│ Count: <b>{target_count:,}</b>\n"
    message += f"│ {target_bar}\n"
    message += f"└─────────────────────────\n\n"
    
    message += f"┌─ RESULT\n"
    message += f"│\n"
    message += f"├─ Difference: <b>{difference:,}</b>\n"
    message += f"└─ Leader: <b>"
    
    if user_count > target_count:
        message += f"{user_name}</b>\n\n"
    elif target_count > user_count:
        message += f"{target_name}</b>\n\n"
    else:
        message += "TIE</b>\n\n"
    
    message += "═══════════════════════════════════"
    
    await loading_msg.edit_text(message, parse_mode='HTML')


async def recent_collectors(update: Update, context: CallbackContext) -> None:
    """Show recent activity with animation"""
    chat_id = update.effective_chat.id
    
    loading_msg = await update.message.reply_text("Scanning activity...")
    
    stages = [
        "Checking recent logs",
        "Sorting by activity"
    ]
    await animate_loading(loading_msg, stages)
    
    cursor = group_user_totals_collection.aggregate([
        {"$match": {"group_id": chat_id}},
        {"$project": {"username": 1, "first_name": 1, "character_count": "$count"}},
        {"$sort": {"character_count": -1}},
        {"$limit": 5}
    ])
    recent_data = await cursor.to_list(length=5)
    
    if not recent_data:
        await loading_msg.edit_text("║ No recent activity in this chat ║")
        return
    
    await animate_progress_bar(loading_msg, "Compiling activity report")
    
    message = "╔════════════════════════════════╗\n"
    message += "║                                ║\n"
    message += "║     ACTIVE COLLECTORS          ║\n"
    message += "║                                ║\n"
    message += "╚════════════════════════════════╝\n\n"
    
    for i, user in enumerate(recent_data, start=1):
        username = user.get('username', 'Unknown')
        first_name = escape(user.get('first_name', 'Unknown'))
        character_count = user['character_count']
        
        message += f"[{i}] <a href='https://t.me/{username}'>{first_name}</a>\n"
        message += f"├─ Count: <b>{character_count:,}</b>\n"
        message += f"└─────────────────────────\n\n"
    
    message += "═══════════════════════════════════"
    
    await loading_msg.edit_text(message, parse_mode='HTML', disable_web_page_preview=True)


async def group_rank(update: Update, context: CallbackContext) -> None:
    """Show group's global rank with animation"""
    chat_id = update.effective_chat.id
    chat_title = escape(update.effective_chat.title or "This Chat")
    
    loading_msg = await update.message.reply_text("Analyzing group...")
    
    stages = [
        "Fetching group data",
        "Computing global position",
        "Generating report"
    ]
    await animate_loading(loading_msg, stages)
    
    group_data = await top_global_groups_collection.find_one({"_id": chat_id})
    
    if not group_data:
        await loading_msg.edit_text("║ This group hasn't been ranked yet ║")
        return
    
    await animate_progress_bar(loading_msg, "Calculating rank")
    
    group_count = group_data.get('count', 0)
    
    higher_groups = await top_global_groups_collection.count_documents({"count": {"$gt": group_count}})
    rank = higher_groups + 1
    total_groups = await top_global_groups_collection.count_documents({})
    
    percentile = ((total_groups - rank) / total_groups) * 100 if total_groups > 0 else 0
    
    rank_badge = get_rank_badge(rank)
    
    message = "╔════════════════════════════════╗\n"
    message += "║                                ║\n"
    message += "║     GROUP RANKINGS             ║\n"
    message += "║                                ║\n"
    message += "╚════════════════════════════════╝\n\n"
    message += f"┌─ GROUP INFO\n"
    message += f"│\n"
    message += f"├─ Name: <b>{chat_title}</b>\n"
    message += f"├─ Badge: <b>{rank_badge}</b>\n"
    message += f"├─ Global Rank: <b>#{rank:,}</b> / {total_groups:,}\n"
    message += f"├─ Characters: <b>{group_count:,}</b>\n"
    message += f"└─ Percentile: <b>Top {100 - percentile:.1f}%</b>\n\n"
    
    # Progress visualization
    bar_length = min(int(percentile / 5), 20)
    bar = "▓" * bar_length + "░" * (20 - bar_length)
    message += f"Standing:\n{bar}\n\n"
    
    message += "═══════════════════════════════════"
    
    await loading_msg.edit_text(message, parse_mode='HTML')


async def send_users_document(update: Update, context: CallbackContext) -> None:
    """Export users with animation (Sudo only)"""
    if str(update.effective_user.id) not in SUDO_USERS:
        await update.message.reply_text('║ Unauthorized: Sudo access required ║')
        return
    
    loading_msg = await update.message.reply_text('Preparing export...')
    
    stages = [
        "Accessing database",
        "Extracting user data",
        "Formatting document",
        "Finalizing export"
    ]
    await animate_loading(loading_msg, stages)
    
    cursor = user_collection.find({})
    users = []
    async for document in cursor:
        users.append(document)
    
    await animate_progress_bar(loading_msg, "Writing to file")
    
    user_list = f"╔════════════════════════════════╗\n"
    user_list += f"║    USER DATABASE EXPORT        ║\n"
    user_list += f"╚════════════════════════════════╝\n\n"
    user_list += f"Total Users: {len(users)}\n"
    user_list += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    user_list += "="*50 + "\n\n"
    
    for user in users:
        user_id = user.get('id', 'N/A')
        first_name = user.get('first_name', 'Unknown')
        username = user.get('username', 'N/A')
        char_count = len(user.get('characters', []))
        user_list += f"[{user_id}] {first_name} | @{username} | {char_count} chars\n"
    
    with open('users.txt', 'w', encoding='utf-8') as f:
        f.write(user_list)
    
    with open('users.txt', 'rb') as f:
        await context.bot.send_document(
            chat_id=update.effective_chat.id, 
            document=f,
            caption=f"User Database Export\n[Total: {len(users):,} users]"
        )
    
    os.remove('users.txt')
    await loading_msg.delete()


async def send_groups_document(update: Update, context: CallbackContext) -> None:
    """Export groups with animation (Sudo only)"""
    if str(update.effective_user.id) not in SUDO_USERS:
        await update.message.reply_text('║ Unauthorized: Sudo access required ║')
        return
    
    loading_msg = await update.message.reply_text('Preparing export...')
    
    stages = [
        "Accessing database",
        "Extracting group data",
        "Sorting by rank",
        "Finalizing export"
    ]
    await animate_loading(loading_msg, stages)
    
    cursor = top_global_groups_collection.find({})
    groups = []
    async for document in cursor:
        groups.append(document)
    
    groups.sort(key=lambda x: x.get('count', 0), reverse=True)
    
    await animate_progress_bar(loading_msg, "Writing to file")
    
    group_list = f"╔════════════════════════════════╗\n"
    group_list += f"║   GROUP DATABASE EXPORT        ║\n"
    group_list += f"╚════════════════════════════════╝\n\n"
    group_list += f"Total Groups: {len(groups)}\n"
    group_list += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    group_list += "="*50 + "\n\n"
    
    for i, group in enumerate(groups, start=1):
        group_name = group.get('group_name', 'Unknown')
        count = group.get('count', 0)
        group_list += f"[{i}] {group_name} | {count:,} characters\n"
    
    with open('groups.txt', 'w', encoding='utf-8') as f:
        f.write(group_list)
    
    with open('groups.txt', 'rb') as f:
        await context.bot.send_document(
            chat_id=update.effective_chat.id, 
            document=f,
            caption=f"Group Database Export\n[Total: {len(groups):,} groups]"
        )
    
    os.remove('groups.txt')
    await loading_msg.delete()


async def stats(update: Update, context: CallbackContext) -> None:
    """Show bot statistics with animation (Owner only)"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("║ Unauthorized: Owner access required ║")
        return

    loading_msg = await update.message.reply_text("Initializing system scan...")
    
    stages = [
        "Querying user database",
        "Analyzing group data",
        "Computing totals",
        "Generating report"
    ]
    await animate_loading(loading_msg, stages)

    user_count = await user_collection.count_documents({})
    group_count = await group_user_totals_collection.distinct('group_id')
    
    users_with_chars = await user_collection.count_documents({"characters": {"$exists": True, "$type": "array"}})
    
    await animate_progress_bar(loading_msg, "Calculating statistics")
    
    pipeline = [
        {"$match": {"characters": {"$exists": True, "$type": "array"}}},
        {"$project": {"char_count": {"$size": "$characters"}}},
        {"$group": {"_id": None, "total": {"$sum": "$char_count"}}}
    ]
    result = await user_collection.aggregate(pipeline).to_list(length=1)
    total_chars = result[0]['total'] if result else 0

    top_collector = await user_collection.find_one(
        {"characters": {"$exists": True, "$type": "array"}},
        sort=[("characters", -1)]
    )

    message = "╔════════════════════════════════╗\n"
    message += "║                                ║\n"
    message += "║     SYSTEM STATISTICS          ║\n"
    message += "║                                ║\n"
    message += "╚════════════════════════════════╝\n\n"
    message += "┌─ DATABASE OVERVIEW\n"
    message += "│\n"
    message += f"├─ Total Users: <b>{user_count:,}</b>\n"
    message += f"├─ Active Collectors: <b>{users_with_chars:,}</b>\n"
    message += f"├─ Total Groups: <b>{len(group_count):,}</b>\n"
    message += f"└─ Total Characters: <b>{total_chars:,}</b>\n\n"
    
    if users_with_chars > 0:
        avg = total_chars / users_with_chars
        message += f"┌─ ANALYTICS\n"
        message += f"│\n"
        message += f"├─ Avg per User: <b>{avg:.1f}</b>\n"
        
        if top_collector:
            top_name = escape(top_collector.get('first_name', 'Unknown'))
            top_count = len(top_collector.get('characters', []))
            message += f"├─ Top Collector: <b>{top_name}</b>\n"
            message += f"└─ Their Count: <b>{top_count:,}</b>\n\n"
    
    message += "═══════════════════════════════════\n"
    message += "       @waifukunbot System"

    await loading_msg.edit_text(message, parse_mode='HTML')


async def top_collectors(update: Update, context: CallbackContext) -> None:
    """Show top 20 collectors with animation"""
    loading_msg = await update.message.reply_text("Loading extended rankings...")
    
    stages = [
        "Querying top collectors",
        "Processing rankings",
        "Sorting by collection",
        "Preparing display"
    ]
    await animate_loading(loading_msg, stages)
    
    limit = 20
    cursor = user_collection.aggregate([
        {"$match": {"characters": {"$exists": True, "$type": "array"}}},
        {"$project": {"username": 1, "first_name": 1, "character_count": {"$size": "$characters"}}},
        {"$sort": {"character_count": -1}},
        {"$limit": limit}
    ])
    leaderboard_data = await cursor.to_list(length=limit)

    if not leaderboard_data:
        await loading_msg.edit_text("║ No collector data available ║")
        return

    await animate_progress_bar(loading_msg, "Rendering extended list")

    leaderboard_message = "╔════════════════════════════════╗\n"
    leaderboard_message += "║                                ║\n"
    leaderboard_message += "║   TOP 20 GLOBAL COLLECTORS     ║\n"
    leaderboard_message += "║                                ║\n"
    leaderboard_message += "╚════════════════════════════════╝\n\n"

    for i, user in enumerate(leaderboard_data, start=1):
        username = user.get('username', 'Unknown')
        first_name = escape(user.get('first_name', 'Unknown'))
        
        if len(first_name) > 18:
            first_name = first_name[:18] + '...'
        character_count = user['character_count']
        
        rank_badge = get_rank_badge(i)
        
        leaderboard_message += f'<b>{rank_badge}</b> <a href="https://t.me/{username}">{first_name}</a>\n'
        leaderboard_message += f'└─ <b>{character_count:,}</b> characters\n\n'

    leaderboard_message += "═══════════════════════════════════\n"
    leaderboard_message += "       Extended Rankings"

    await loading_msg.edit_text(leaderboard_message, parse_mode='HTML', disable_web_page_preview=True)


async def search_user(update: Update, context: CallbackContext) -> None:
    """Search for user with animation"""
    if not context.args:
        await update.message.reply_text(
            "╔════════════════════════════════╗\n"
            "║ USAGE: /search <username>      ║\n"
            "╚════════════════════════════════╝\n\n"
            "Example: /search username\n"
            "or: /search 123456789"
        )
        return
    
    loading_msg = await update.message.reply_text("Searching database...")
    
    stages = [
        "Scanning records",
        "Locating user",
        "Retrieving data"
    ]
    await animate_loading(loading_msg, stages)
    
    identifier = context.args[0].replace('@', '')
    
    if identifier.isdigit():
        user_data = await user_collection.find_one({'id': int(identifier)})
    else:
        user_data = await user_collection.find_one({'username': identifier})
    
    if not user_data:
        await loading_msg.edit_text(f"║ User '{identifier}' not found ║")
        return
    
    await animate_progress_bar(loading_msg, "Compiling profile")
    
    first_name = escape(user_data.get('first_name', 'Unknown'))
    username = user_data.get('username', 'N/A')
    user_id = user_data.get('id', 'N/A')
    character_count = len(user_data.get('characters', []))
    
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
    
    rank_badge = get_rank_badge(rank) if isinstance(rank, int) else "[N/A]"
    
    message = "╔════════════════════════════════╗\n"
    message += "║                                ║\n"
    message += "║      USER PROFILE              ║\n"
    message += "║                                ║\n"
    message += "╚════════════════════════════════╝\n\n"
    message += f"┌─ IDENTITY\n"
    message += f"│\n"
    message += f"├─ Name: <b>{first_name}</b>\n"
    message += f"├─ Username: @{username}\n"
    message += f"└─ User ID: <code>{user_id}</code>\n\n"
    message += f"┌─ STATISTICS\n"
    message += f"│\n"
    message += f"├─ Characters: <b>{character_count:,}</b>\n"
    
    if isinstance(rank, int):
        message += f"├─ Badge: <b>{rank_badge}</b>\n"
        message += f"└─ Rank: <b>#{rank:,}</b> / {total_users:,}\n\n"
    else:
        message += f"└─ Rank: <b>{rank}</b>\n\n"
    
    message += "═══════════════════════════════════"
    
    await loading_msg.edit_text(message, parse_mode='HTML')


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