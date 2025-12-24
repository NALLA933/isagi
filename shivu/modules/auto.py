import logging
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes, filters, CallbackQueryHandler, MessageHandler
from telegram.constants import ParseMode
from shivu import (
    application,
    db  # MongoDB database connection
)

LOGGER = logging.getLogger(__name__)

# MongoDB collections
message_stats = db['message_stats']  # User message statistics
group_stats = db['group_stats']      # Group-wise statistics

# Debug function to check if commands are working
async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test command to check if bot is responsive"""
    await update.message.reply_text("✅ Bot is working! Commands should be functional.")

async def track_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track every message sent in groups"""
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    
    try:
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        user_name = update.effective_user.first_name
        current_date = datetime.now()
        
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

async def groupleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show leaderboard with buttons"""
    LOGGER.info(f"groupleaderboard command called by {update.effective_user.id} in chat {update.effective_chat.id}")
    
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("❌ This command works only in groups!")
        return
    
    try:
        chat_id = update.effective_chat.id
        chat_title = update.effective_chat.title
        
        LOGGER.info(f"Creating leaderboard for chat: {chat_title} (ID: {chat_id})")
        
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
        
    except Exception as e:
        LOGGER.error(f"Error in groupleaderboard command: {e}")
        await update.message.reply_text(
            f"❌ Error displaying leaderboard: {str(e)[:100]}",
            parse_mode=ParseMode.HTML
        )

async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle leaderboard button clicks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    try:
        chat_id = int(data.split('_')[-1])
        category = data.split('_')[1]
    except:
        await query.edit_message_text("❌ Invalid button data")
        return
    
    try:
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
        
        # Get leaderboard data based on category
        leaderboard_data = []
        title = ""
        emoji = ""
        
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
                f"📭 No data available for {category} leaderboard in this group.\n"
                f"Members need to send some messages first!",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Format leaderboard message
        message = await format_leaderboard(leaderboard_data, title, emoji, chat_title)
        
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
        LOGGER.error(f"Error in leaderboard_callback: {e}", exc_info=True)
        await query.edit_message_text(
            f"❌ Error fetching {category} leaderboard. Please try again.",
            parse_mode=ParseMode.HTML
        )

async def get_overall_leaderboard(chat_id):
    """Get overall top 10 users"""
    try:
        # First, try aggregation
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
        
        # If no results with total_messages, try different approach
        if not results:
            # Get all users for this chat
            cursor = message_stats.find({"chat_id": chat_id}).sort("total_messages", -1).limit(10)
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
            # Ensure count field exists
            if 'count' not in user:
                user['count'] = user.get('total_messages', 0)
        
        return results
        
    except Exception as e:
        LOGGER.error(f"Error in get_overall_leaderboard: {e}")
        return []

async def get_weekly_leaderboard(chat_id):
    """Get weekly top 10 users"""
    try:
        year, week_num, _ = datetime.now().isocalendar()
        current_week = f"{year}-W{week_num}"
        
        # Get all users and manually filter
        cursor = message_stats.find({"chat_id": chat_id})
        all_users = await cursor.to_list(length=None)
        
        # Filter users with weekly data and calculate counts
        users_with_weekly = []
        for user in all_users:
            weekly_data = user.get('weekly', {})
            week_count = weekly_data.get(current_week, 0)
            if week_count > 0:
                user_data = {
                    'user_id': user.get('user_id'),
                    'user_name': user.get('user_name', f"User {user.get('user_id')}"),
                    'count': week_count
                }
                users_with_weekly.append(user_data)
        
        # Sort by count and take top 10
        users_with_weekly.sort(key=lambda x: x['count'], reverse=True)
        results = users_with_weekly[:10]
        
        # Add rank
        for i, user in enumerate(results, 1):
            user['rank'] = i
        
        return results
        
    except Exception as e:
        LOGGER.error(f"Error in get_weekly_leaderboard: {e}")
        return []

async def get_today_leaderboard(chat_id):
    """Get today's top 10 users"""
    try:
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        # Get all users and manually filter
        cursor = message_stats.find({"chat_id": chat_id})
        all_users = await cursor.to_list(length=None)
        
        # Filter users with today's data
        users_with_today = []
        for user in all_users:
            daily_data = user.get('daily', {})
            today_count = daily_data.get(today_str, 0)
            if today_count > 0:
                user_data = {
                    'user_id': user.get('user_id'),
                    'user_name': user.get('user_name', f"User {user.get('user_id')}"),
                    'count': today_count
                }
                users_with_today.append(user_data)
        
        # Sort by count and take top 10
        users_with_today.sort(key=lambda x: x['count'], reverse=True)
        results = users_with_today[:10]
        
        # Add rank
        for i, user in enumerate(results, 1):
            user['rank'] = i
        
        return results
        
    except Exception as e:
        LOGGER.error(f"Error in get_today_leaderboard: {e}")
        return []

async def format_leaderboard(data, title, emoji, chat_title):
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
        rank = user.get('rank', 1)
        name = user.get('user_name', f"User {user.get('user_id', 'Unknown')}")
        count = user.get('count', 0)
        
        # Truncate long names
        if len(name) > 20:
            name = name[:17] + "..."
        
        # Add additional info for overall leaderboard
        if 'days_active' in user and user['days_active'] > 0:
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
    total_messages = sum(user.get('count', 0) for user in data)
    message_parts.append("════════════════════")
    message_parts.append(f"📊 Total in Top {total_users}: <code>{total_messages:,}</code> messages")
    message_parts.append(f"🕒 Updated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    
    return "\n".join(message_parts)

async def grank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check user's rank in the group"""
    LOGGER.info(f"grank command called by {update.effective_user.id}")
    
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("❌ This command works only in groups!")
        return
    
    try:
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        user_name = update.effective_user.first_name
        
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
        
        avg_per_day = total_messages / days_active if days_active > 0 else total_messages
        
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
        LOGGER.error(f"Error in grank: {e}")
        await update.message.reply_text(
            f"❌ Error fetching your rank: {str(e)[:100]}",
            parse_mode=ParseMode.HTML
        )

async def resetstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    try:
        chat_id = int(data.split('_')[-1])
        action = data.split('_')[1]
    except:
        await query.edit_message_text("❌ Invalid button data")
        return
    
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
async def cleanup_old_data(context: ContextTypes.DEFAULT_TYPE):
    """Cleanup old weekly and daily data"""
    try:
        current_date = datetime.now()
        
        # Cleanup daily data older than 30 days
        thirty_days_ago = current_date - timedelta(days=30)
        date_to_clean = thirty_days_ago.strftime('%Y-%m-%d')
        
        LOGGER.info("Cleanup job running...")
        
    except Exception as e:
        LOGGER.error(f"Error in cleanup: {e}")

# Register all handlers with proper order
async def register_handlers():
    """Register all handlers to avoid conflicts"""
    
    # Test command first (for debugging)
    application.add_handler(CommandHandler("testcmd", test_command, filters=filters.ALL))
    
    # Group leaderboard commands
    application.add_handler(CommandHandler("groupleaderboard", groupleaderboard, filters=filters.ALL))
    application.add_handler(CommandHandler("gtop", groupleaderboard, filters=filters.ALL))
    application.add_handler(CommandHandler("gleaderboard", groupleaderboard, filters=filters.ALL))
    application.add_handler(CommandHandler("grank", grank, filters=filters.ALL))
    application.add_handler(CommandHandler("gstats", grank, filters=filters.ALL))
    application.add_handler(CommandHandler("resetstats", resetstats, filters=filters.ALL))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(leaderboard_callback, pattern="^leaderboard_"))
    application.add_handler(CallbackQueryHandler(reset_callback, pattern="^reset_"))
    
    # Message tracker (for all group messages) - Should be last
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & ~filters.COMMAND, 
        track_message
    ))
    
    # Help command
    application.add_handler(CommandHandler("grouphelp", grouphelp, filters=filters.ALL))
    application.add_handler(CommandHandler("ghelp", grouphelp, filters=filters.ALL))
    
    LOGGER.info("All handlers registered successfully!")

async def grouphelp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help for group leaderboard commands"""
    help_text = (
        "📊 <b>Group Leaderboard Commands</b>\n"
        "════════════════════════════\n\n"
        
        "🏆 <code>/groupleaderboard</code>\n"
        "   or <code>/gtop</code>\n"
        "   or <code>/gleaderboard</code>\n"
        "   - Show group leaderboard with Overall, Weekly & Today stats\n\n"
        
        "👤 <code>/grank</code>\n"
        "   or <code>/gstats</code>\n"
        "   - Check your personal rank and statistics\n\n"
        
        "🔄 <code>/resetstats</code> (Admin only)\n"
        "   - Reset all message statistics for the group\n\n"
        
        "🔧 <code>/testcmd</code>\n"
        "   - Test if bot commands are working\n\n"
        
        "📈 <b>How it works:</b>\n"
        "• Every message in group is automatically counted\n"
        "• Data updates in real-time\n"
        "• Leaderboards show top 10 members\n"
        "• Stats are group-specific\n\n"
        
        "🕒 Updated automatically"
    )
    
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

# Initialize handlers when module loads
import asyncio
try:
    asyncio.run(register_handlers())
    LOGGER.info("Group leaderboard module initialized successfully!")
except Exception as e:
    LOGGER.error(f"Error initializing group leaderboard module: {e}")

# Manual fallback registration if async fails
try:
    # Test command
    application.add_handler(CommandHandler("testcmd", test_command, filters=filters.ALL))
    
    # Group leaderboard commands
    application.add_handler(CommandHandler("groupleaderboard", groupleaderboard, filters=filters.ALL))
    application.add_handler(CommandHandler("gtop", groupleaderboard, filters=filters.ALL))
    application.add_handler(CommandHandler("gleaderboard", groupleaderboard, filters=filters.ALL))
    application.add_handler(CommandHandler("grank", grank, filters=filters.ALL))
    application.add_handler(CommandHandler("gstats", grank, filters=filters.ALL))
    application.add_handler(CommandHandler("resetstats", resetstats, filters=filters.ALL))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(leaderboard_callback, pattern="^leaderboard_"))
    application.add_handler(CallbackQueryHandler(reset_callback, pattern="^reset_"))
    
    # Message tracker
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & ~filters.COMMAND, 
        track_message
    ))
    
    # Help command
    application.add_handler(CommandHandler("grouphelp", grouphelp, filters=filters.ALL))
    application.add_handler(CommandHandler("ghelp", grouphelp, filters=filters.ALL))
    
    LOGGER.info("Manual handler registration completed!")
except Exception as e:
    LOGGER.error(f"Error in manual handler registration: {e}")

# Add cleanup job (optional - runs daily)
try:
    from telegram.ext import JobQueue
    if hasattr(application, 'job_queue'):
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_old_data, interval=86400, first=10)
        LOGGER.info("Cleanup job scheduled successfully!")
except Exception as e:
    LOGGER.error(f"Error scheduling cleanup job: {e}")