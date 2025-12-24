import logging
import time
from datetime import datetime
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, filters
from telegram.constants import ParseMode
from shivu import (
    sudo_users, 
    OWNER_ID,
    user_collection,
    top_global_groups_collection,
    BANNED_USERS,
    banned_groups_collection,
    pm_users,
    application,
    db  # Assuming you have a database connection
)

LOGGER = logging.getLogger(__name__)

async def gstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Enhanced access control with logging
    if user_id not in sudo_users and user_id != OWNER_ID and user_id != 8420981179:
        LOGGER.warning(f"Unauthorized access attempt by user {user_id}")
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return
    
    # Show processing message
    processing_msg = await update.message.reply_text("📊 Fetching statistics...")
    
    try:
        start_time = time.time()
        
        # Basic counts (parallel execution would be better but async MongoDB works sequentially)
        total_users = await user_collection.count_documents({})
        total_chats = await top_global_groups_collection.count_documents({})
        banned_users_count = await BANNED_USERS.count_documents({})
        banned_groups_count = await banned_groups_collection.count_documents({})
        pm_users_count = await pm_users.count_documents({})
        
        # Get active users (users who messaged in last 7 days)
        week_ago = datetime.now().timestamp() - (7 * 24 * 60 * 60)
        active_users = await user_collection.count_documents({
            "last_active": {"$gte": week_ago}
        }) if await user_collection.find_one({"last_active": {"$exists": True}}) else "N/A"
        
        # Get database stats if available
        db_stats = {}
        try:
            if hasattr(db, 'command'):
                db_stats = await db.command("dbstats")
        except:
            pass
        
        # Get user growth (last 30 days)
        month_ago = datetime.now().timestamp() - (30 * 24 * 60 * 60)
        new_users_month = await user_collection.count_documents({
            "joined_date": {"$gte": month_ago}
        }) if await user_collection.find_one({"joined_date": {"$exists": True}}) else "N/A"
        
        # Calculate percentages
        active_percentage = f"{(active_users/total_users*100):.1f}%" if isinstance(active_users, int) and total_users > 0 else "N/A"
        banned_percentage = f"{(banned_users_count/total_users*100):.1f}%" if total_users > 0 else "0%"
        
        # Get top 5 groups by member count (if field exists)
        top_groups = []
        try:
            cursor = top_global_groups_collection.find({}).sort("members", -1).limit(5)
            async for group in cursor:
                if "title" in group:
                    top_groups.append(f"  • {group['title']}: {group.get('members', 'N/A')} members")
        except:
            top_groups = ["  • No group data available"]
        
        processing_time = time.time() - start_time
        
        # Create formatted message
        stats_text = (
            "📈 <b>Global Statistics</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            
            "👥 <b>User Statistics:</b>\n"
            f"  • Total Users: <code>{total_users:,}</code>\n"
            f"  • New Users (30d): <code>{new_users_month:,}</code>\n"
            f"  • Active Users (7d): <code>{active_users:,}</code> ({active_percentage})\n"
            f"  • PM Users: <code>{pm_users_count:,}</code>\n"
            f"  • Banned Users: <code>{banned_users_count:,}</code> ({banned_percentage})\n\n"
            
            "👥 <b>Group Statistics:</b>\n"
            f"  • Total Chats: <code>{total_chats:,}</code>\n"
            f"  • Banned Groups: <code>{banned_groups_count:,}</code>\n\n"
            
            "🏆 <b>Top 5 Groups:</b>\n" + "\n".join(top_groups) + "\n\n"
            
            "💾 <b>Database Info:</b>\n"
            f"  • Data Size: <code>{db_stats.get('dataSize', 0)/1024/1024:.2f} MB</code>\n"
            f"  • Storage Size: <code>{db_stats.get('storageSize', 0)/1024/1024:.2f} MB</code>\n"
            f"  • Index Size: <code>{db_stats.get('indexSize', 0)/1024/1024:.2f} MB</code>\n\n"
            
            "⏱ <b>Performance:</b>\n"
            f"  • Query Time: <code>{processing_time:.3f}s</code>\n"
            f"  • Last Updated: <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>"
        )
        
        await processing_msg.delete()
        await update.message.reply_text(
            stats_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        LOGGER.error(f"Error in gstats: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        await update.message.reply_text(
            "❌ Error fetching statistics. Please check logs for details.",
            parse_mode=ParseMode.HTML
        )

# Add command with better filters
application.add_handler(CommandHandler("gstats", gstats, filters=filters.ALL))

# Optional: Add a /stats command for regular users with limited info
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Public stats command for regular users"""
    try:
        total_users = await user_collection.count_documents({})
        total_chats = await top_global_groups_collection.count_documents({})
        
        stats_text = (
            "📊 <b>Bot Statistics</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 Total Users: <code>{total_users:,}</code>\n"
            f"👥 Total Groups: <code>{total_chats:,}</code>\n\n"
            f"📅 Last Updated: {datetime.now().strftime('%Y-%m-%d')}"
        )
        
        await update.message.reply_text(
            stats_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        LOGGER.error(f"Error in stats: {e}")
        await update.message.reply_text("⚠️ Could not fetch statistics.")

# Add public stats command
application.add_handler(CommandHandler("stats", stats, filters=filters.ALL))