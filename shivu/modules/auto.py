import logging
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes, filters, CallbackQueryHandler
from telegram.constants import ParseMode
from shivu import (
    application,
    db  # MongoDB database connection
)

LOGGER = logging.getLogger(__name__)

# MongoDB collections
message_stats = db['message_stats']  # User message statistics
group_stats = db['group_stats']      # Group-wise statistics

async def track_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track every message sent in groups"""
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name
    current_date = datetime.now()
    
    try:
        # Get today's date and week number
        today_str = current_date.strftime('%Y-%m-%d')
        year, week_num, _ = current_date.isocalendar()
        week_str = f"{year}-W{week_num}"
        
        # Update overall stats
        await message_stats.update_one(
            {"user_id": user_id, "chat_id": chat_id},
            {
                "$inc": {
                    "total_messages": 1,
                    f"weekly.{week_str}": 1,
                    f"daily.{today_str}": 1
                },
                "$set": {
                    "user_name": user_name,
                    "last_active": current_date,
                    "chat_title": update.effective_chat.title
                },
                "$setOnInsert": {
                    "first_seen": current_date
                }
            },
            upsert=True
        )
        
        # Update group stats
        await group_stats.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "chat_title": update.effective_chat.title,
                    "last_updated": current_date
                },
                "$inc": {"total_messages": 1}
            },
            upsert=True
        )
        
    except Exception as e:
        LOGGER.error(f"Error tracking message: {e}")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show leaderboard with buttons"""
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("❌ This command works only in groups!")
        return
    
    chat_id = update.effective_chat.id
    chat_title = update.effective_chat.title
    
    keyboard = [
        [
            InlineKeyboardButton("📊 Overall", callback_data=f"leaderboard_overall_{chat_id}"),
            InlineKeyboardButton("📅 Weekly", callback_data=f"leaderboard_weekly_{chat_id}")
        ],
        [
            InlineKeyboardButton("🕐 Today", callback_data=f"leaderboard_today_{chat_id}"),
            InlineKeyboardButton("🔄 Refresh", callback_data=f"leaderboard_refresh_{chat_id}")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🏆 <b>{chat_title} Leaderboard</b>\n\n"
        "Select a category to view top 10 active members:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle leaderboard button clicks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = int(data.split('_')[-1])
    category = data.split('_')[1]
    
    # Get chat title
    chat = await query.bot.get_chat(chat_id)
    chat_title = chat.title
    
    if category == 'refresh':
        # Refresh the leaderboard menu
        keyboard = [
            [
                InlineKeyboardButton("📊 Overall", callback_data=f"leaderboard_overall_{chat_id}"),
                InlineKeyboardButton("📅 Weekly", callback_data=f"leaderboard_weekly_{chat_id}")
            ],
            [
                InlineKeyboardButton("🕐 Today", callback_data=f"leaderboard_today_{chat_id}"),
                InlineKeyboardButton("🔄 Refresh", callback_data=f"leaderboard_refresh_{chat_id}")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🏆 <b>{chat_title} Leaderboard</b>\n\n"
            "Select a category to view top 10 active members:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        return
    
    # Show processing
    await query.edit_message_text(
        f"📊 Fetching {category} leaderboard...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        if category == 'overall':
            leaderboard_data = await get_overall_leaderboard(chat_id)
            title = "📊 Overall Leaderboard"
            emoji = "🏆"
            
        elif category == 'weekly':
            leaderboard_data = await get_weekly_leaderboard(chat_id)
            title = "📅 Weekly Leaderboard"
            emoji = "🗓️"
            
        elif category == 'today':
            leaderboard_data = await get_today_leaderboard(chat_id)
            title = "🕐 Today's Leaderboard"
            emoji = "☀️"
        
        if not leaderboard_data:
            await query.edit_message_text(
                f"📭 No data available for {category} leaderboard in this group.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Format leaderboard message
        message = format_leaderboard(leaderboard_data, title, emoji, chat_title)
        
        # Add navigation buttons
        keyboard = [
            [
                InlineKeyboardButton("📊 Overall", callback_data=f"leaderboard_overall_{chat_id}"),
                InlineKeyboardButton("📅 Weekly", callback_data=f"leaderboard_weekly_{chat_id}")
            ],
            [
                InlineKeyboardButton("🕐 Today", callback_data=f"leaderboard_today_{chat_id}"),
                InlineKeyboardButton("🏠 Main Menu", callback_data=f"leaderboard_refresh_{chat_id}")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        LOGGER.error(f"Error in leaderboard_callback: {e}")
        await query.edit_message_text(
            f"❌ Error fetching {category} leaderboard.",
            parse_mode=ParseMode.HTML
        )

async def get_overall_leaderboard(chat_id):
    """Get overall top 10 users"""
    pipeline = [
        {"$match": {"chat_id": chat_id}},
        {"$sort": {"total_messages": -1}},
        {"$limit": 10},
        {"$project": {
            "user_id": 1,
            "user_name": 1,
            "count": "$total_messages",
            "first_seen": 1,
            "_id": 0
        }}
    ]
    
    cursor = message_stats.aggregate(pipeline)
    results = await cursor.to_list(length=10)
    
    # Add rank and format
    for i, user in enumerate(results, 1):
        user['rank'] = i
        # Calculate days since first seen
        if 'first_seen' in user:
            days = (datetime.now() - user['first_seen']).days
            user['days_active'] = max(1, days)
        else:
            user['days_active'] = 1
    
    return results

async def get_weekly_leaderboard(chat_id):
    """Get weekly top 10 users"""
    year, week_num, _ = datetime.now().isocalendar()
    current_week = f"{year}-W{week_num}"
    
    pipeline = [
        {"$match": {
            "chat_id": chat_id,
            f"weekly.{current_week}": {"$exists": True}
        }},
        {"$addFields": {
            "weekly_count": {"$ifNull": [f"${current_week}", 0]}
        }},
        {"$sort": {"weekly_count": -1}},
        {"$limit": 10},
        {"$project": {
            "user_id": 1,
            "user_name": 1,
            "count": "$weekly_count",
            "_id": 0
        }}
    ]
    
    cursor = message_stats.aggregate(pipeline)
    results = await cursor.to_list(length=10)
    
    # Add rank
    for i, user in enumerate(results, 1):
        user['rank'] = i
    
    return results

async def get_today_leaderboard(chat_id):
    """Get today's top 10 users"""
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    pipeline = [
        {"$match": {
            "chat_id": chat_id,
            f"daily.{today_str}": {"$exists": True}
        }},
        {"$addFields": {
            "daily_count": {"$ifNull": [f"${today_str}", 0]}
        }},
        {"$sort": {"daily_count": -1}},
        {"$limit": 10},
        {"$project": {
            "user_id": 1,
            "user_name": 1,
            "count": "$daily_count",
            "_id": 0
        }}
    ]
    
    cursor = message_stats.aggregate(pipeline)
    results = await cursor.to_list(length=10)
    
    # Add rank
    for i, user in enumerate(results, 1):
        user['rank'] = i
    
    return results

def format_leaderboard(data, title, emoji, chat_title):
    """Format leaderboard data into a readable message"""
    if not data:
        return f"{emoji} <b>{title}</b>\n\nNo data available yet."
    
    message_parts = []
    message_parts.append(f"{emoji} <b>{title}</b>")
    message_parts.append(f"👥 Group: {chat_title}")
    message_parts.append("════════════════════")
    message_parts.append("")
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for user in data:
        rank = user['rank']
        name = user.get('user_name', f"User {user['user_id']}")
        count = user['count']
        
        # Truncate long names
        if len(name) > 20:
            name = name[:17] + "..."
        
        # Add additional info for overall leaderboard
        if 'days_active' in user:
            avg_per_day = count / user['days_active']
            message_parts.append(
                f"{medals[rank-1] if rank <= 10 else f'{rank}.'} "
                f"<b>{name}</b>\n"
                f"   📨 Messages: <code>{count:,}</code>\n"
                f"   📅 Active: {user['days_active']} days\n"
                f"   ⚡ Daily Avg: <code>{avg_per_day:.1f}</code>"
            )
        else:
            message_parts.append(
                f"{medals[rank-1] if rank <= 10 else f'{rank}.'} "
                f"<b>{name}</b>\n"
                f"   📨 Messages: <code>{count:,}</code>"
            )
        
        message_parts.append("")
    
    # Add footer with stats
    total_users = len(data)
    total_messages = sum(user['count'] for user in data)
    message_parts.append("════════════════════")
    message_parts.append(f"📊 Total in Top {total_users}: <code>{total_messages:,}</code> messages")
    message_parts.append(f"🕒 Updated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    
    return "\n".join(message_parts)

async def myrank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check user's rank in the group"""
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("❌ This command works only in groups!")
        return
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name
    
    try:
        # Get user's overall rank
        user_data = await message_stats.find_one(
            {"user_id": user_id, "chat_id": chat_id}
        )
        
        if not user_data:
            await update.message.reply_text(
                f"📭 No data found for you in this group.\n"
                f"Start sending messages to appear on the leaderboard!",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Get overall ranking
        total_messages = user_data.get('total_messages', 0)
        
        # Count users with more messages
        higher_users = await message_stats.count_documents({
            "chat_id": chat_id,
            "total_messages": {"$gt": total_messages}
        })
        
        rank = higher_users + 1
        
        # Get total users in group
        total_group_users = await message_stats.count_documents({
            "chat_id": chat_id
        })
        
        # Get weekly and today stats
        year, week_num, _ = datetime.now().isocalendar()
        current_week = f"{year}-W{week_num}"
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        weekly_messages = user_data.get('weekly', {}).get(current_week, 0)
        today_messages = user_data.get('daily', {}).get(today_str, 0)
        
        # Calculate days active
        first_seen = user_data.get('first_seen', datetime.now())
        days_active = (datetime.now() - first_seen).days
        days_active = max(1, days_active)
        
        avg_per_day = total_messages / days_active
        
        # Format response
        response = (
            f"👤 <b>Your Stats in {update.effective_chat.title}</b>\n"
            "════════════════════\n\n"
            f"🏆 <b>Overall Rank:</b> {rank}/{total_group_users}\n"
            f"📨 <b>Total Messages:</b> {total_messages:,}\n"
            f"📅 <b>Active Days:</b> {days_active}\n"
            f"⚡ <b>Daily Average:</b> {avg_per_day:.1f}\n\n"
            
            f"🗓️ <b>This Week:</b> {weekly_messages:,} messages\n"
            f"☀️ <b>Today:</b> {today_messages:,} messages\n\n"
            
            f"⏰ <i>First seen: {first_seen.strftime('%d %b %Y')}</i>\n"
            f"🔄 <i>Updated: {datetime.now().strftime('%I:%M %p')}</i>"
        )
        
        await update.message.reply_text(
            response,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        LOGGER.error(f"Error in myrank: {e}")
        await update.message.reply_text(
            "❌ Error fetching your rank. Try again later.",
            parse_mode=ParseMode.HTML
        )

async def reset_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset stats (admin only)"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Check if user is admin
    try:
        member = await update.effective_chat.get_member(user_id)
        if member.status not in ['administrator', 'creator']:
            await update.message.reply_text("❌ Only admins can reset stats!")
            return
    except:
        await update.message.reply_text("❌ Could not verify admin status!")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes, Reset", callback_data=f"reset_confirm_{chat_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"reset_cancel_{chat_id}")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚠️ <b>Reset Statistics</b>\n\n"
        "Are you sure you want to reset ALL message statistics for this group?\n"
        "This action cannot be undone!",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reset confirmation"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = int(data.split('_')[-1])
    action = data.split('_')[1]
    
    if action == 'cancel':
        await query.edit_message_text("✅ Reset cancelled.")
        return
    
    elif action == 'confirm':
        await query.edit_message_text("🔄 Resetting statistics...")
        
        try:
            # Delete all stats for this group
            result = await message_stats.delete_many({"chat_id": chat_id})
            await group_stats.delete_one({"chat_id": chat_id})
            
            await query.edit_message_text(
                f"✅ Statistics reset successfully!\n"
                f"🗑️ Removed {result.deleted_count} user records.",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            LOGGER.error(f"Error resetting stats: {e}")
            await query.edit_message_text(
                "❌ Error resetting statistics!",
                parse_mode=ParseMode.HTML
            )

# Cleanup old data (run periodically)
async def cleanup_old_data():
    """Cleanup old weekly and daily data"""
    try:
        current_date = datetime.now()
        
        # Cleanup daily data older than 30 days
        thirty_days_ago = current_date - timedelta(days=30)
        date_to_clean = thirty_days_ago.strftime('%Y-%m-%d')
        
        # This is complex in MongoDB, we'll handle it differently
        # For now, we'll just log
        LOGGER.info("Cleanup job running...")
        
    except Exception as e:
        LOGGER.error(f"Error in cleanup: {e}")

# Register all handlers
# Message tracker (for all group messages)
from telegram.ext import MessageHandler
application.add_handler(MessageHandler(
    filters.ChatType.GROUPS & ~filters.COMMAND, 
    track_message
))

# Leaderboard commands
application.add_handler(CommandHandler("leaderboard", leaderboard, filters=filters.ALL))
application.add_handler(CommandHandler("top", leaderboard, filters=filters.ALL))  # Alias
application.add_handler(CommandHandler("rank", myrank, filters=filters.ALL))
application.add_handler(CommandHandler("myrank", myrank, filters=filters.ALL))
application.add_handler(CommandHandler("resetstats", reset_stats, filters=filters.ALL))

# Callback handlers
application.add_handler(CallbackQueryHandler(leaderboard_callback, pattern="^leaderboard_"))
application.add_handler(CallbackQueryHandler(reset_callback, pattern="^reset_"))

# Add cleanup job (optional - runs daily)
from telegram.ext import JobQueue
if hasattr(application, 'job_queue'):
    job_queue = application.job_queue
    job_queue.run_repeating(cleanup_old_data, interval=86400, first=10)  # Run daily