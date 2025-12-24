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
    application
)

LOGGER = logging.getLogger(__name__)

async def gstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Access control
    if user_id not in sudo_users and user_id != OWNER_ID and user_id != 8420981179:
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return
    
    processing_msg = None
    try:
        # Show processing message
        processing_msg = await update.message.reply_text("📊 Fetching statistics...")
        start_time = time.time()
        
        # Basic counts - original logic
        total_users = await user_collection.count_documents({})
        total_chats = await top_global_groups_collection.count_documents({})
        banned_users_count = await BANNED_USERS.count_documents({})
        banned_groups_count = await banned_groups_collection.count_documents({})
        pm_users_count = await pm_users.count_documents({})
        
        # Try to get additional stats with fallbacks
        try:
            # Try to get active users (last 7 days)
            week_ago_timestamp = time.time() - (7 * 24 * 60 * 60)
            active_users_cursor = user_collection.find({
                "last_active": {"$exists": True, "$gte": week_ago_timestamp}
            })
            active_users = len(await active_users_cursor.to_list(length=None))
        except:
            active_users = "N/A"
        
        try:
            # Try to get new users in last 30 days
            month_ago_timestamp = time.time() - (30 * 24 * 60 * 60)
            new_users_cursor = user_collection.find({
                "joined_date": {"$exists": True, "$gte": month_ago_timestamp}
            })
            new_users_month = len(await new_users_cursor.to_list(length=None))
        except:
            new_users_month = "N/A"
        
        # Calculate percentages with safe division
        active_percentage = "N/A"
        if isinstance(active_users, int) and total_users > 0:
            active_percentage = f"{(active_users/total_users*100):.1f}%"
        
        banned_percentage = "0%"
        if total_users > 0:
            banned_percentage = f"{(banned_users_count/total_users*100):.1f}%"
        
        # Get top groups (safe method)
        top_groups_text = []
        try:
            # First check if collection has any groups with member count
            sample_group = await top_global_groups_collection.find_one({"members": {"$exists": True}})
            if sample_group:
                pipeline = [
                    {"$match": {"members": {"$exists": True}}},
                    {"$sort": {"members": -1}},
                    {"$limit": 5},
                    {"$project": {
                        "title": {"$ifNull": ["$title", "Unnamed Group"]},
                        "members": {"$ifNull": ["$members", 0]},
                        "_id": 0
                    }}
                ]
                top_groups = await top_global_groups_collection.aggregate(pipeline).to_list(length=5)
                
                for i, group in enumerate(top_groups, 1):
                    group_name = group.get('title', 'Unnamed Group')[:30]
                    members = group.get('members', 0)
                    top_groups_text.append(f"  {i}. {group_name}: {members:,} members")
            else:
                top_groups_text = ["  No member data available"]
        except Exception as e:
            LOGGER.error(f"Error fetching top groups: {e}")
            top_groups_text = ["  Error fetching group data"]
        
        processing_time = time.time() - start_time
        
        # Create formatted message with better emoji and structure
        stats_text = (
            "✨ <b>BOT STATISTICS REPORT</b> ✨\n"
            "╔════════════════════════════╗\n\n"
            
            "👤 <b>USER STATISTICS</b>\n"
            "├ Total Users: " + f"<code>{total_users:,}</code>\n" +
            (f"├ New Users (30d): <code>{new_users_month:,}</code>\n" if new_users_month != "N/A" else "") +
            (f"├ Active Users (7d): <code>{active_users:,}</code> ({active_percentage})\n" if active_users != "N/A" else "") +
            f"├ PM Users: <code>{pm_users_count:,}</code>\n"
            f"├ Banned Users: <code>{banned_users_count:,}</code> ({banned_percentage})\n\n"
            
            "👥 <b>GROUP STATISTICS</b>\n"
            f"├ Total Chats: <code>{total_chats:,}</code>\n"
            f"├ Banned Groups: <code>{banned_groups_count:,}</code>\n\n"
            
            "🏆 <b>TOP GROUPS</b>\n" + "\n".join(top_groups_text) + "\n\n"
            
            "📊 <b>SYSTEM INFO</b>\n"
            f"├ Query Time: <code>{processing_time:.3f}s</code>\n"
            f"├ Generated: <code>{datetime.now().strftime('%d %b %Y, %I:%M %p')}</code>\n"
            "╚════════════════════════════╝"
        )
        
        if processing_msg:
            await processing_msg.delete()
        
        await update.message.reply_text(
            stats_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        LOGGER.error(f"Error in gstats: {str(e)}", exc_info=True)
        
        # Try to delete processing message
        if processing_msg:
            try:
                await processing_msg.delete()
            except:
                pass
        
        # Fallback to basic stats if detailed stats fail
        try:
            basic_stats = (
                "📊 <b>Basic Statistics</b>\n"
                "════════════════════\n"
                f"👥 Total Users: {await user_collection.count_documents({})}\n"
                f"👥 Total Chats: {await top_global_groups_collection.count_documents({})}\n"
                f"⚠️ Banned Users: {await BANNED_USERS.count_documents({})}\n"
                f"⚠️ Banned Groups: {await banned_groups_collection.count_documents({})}"
            )
            await update.message.reply_text(basic_stats, parse_mode=ParseMode.HTML)
        except:
            await update.message.reply_text(
                "❌ Could not fetch statistics. Please check if database is connected.",
                parse_mode=ParseMode.HTML
            )

# Simple public stats command
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Public stats command for all users"""
    try:
        total_users = await user_collection.count_documents({})
        total_chats = await top_global_groups_collection.count_documents({})
        
        stats_text = (
            "📊 <b>Bot Statistics</b>\n"
            "════════════════════\n\n"
            f"👥 Total Users: <b>{total_users:,}</b>\n"
            f"👥 Total Groups: <b>{total_chats:,}</b>\n\n"
            f"⏰ Last Updated: {datetime.now().strftime('%d %b %Y')}"
        )
        
        await update.message.reply_text(
            stats_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        LOGGER.error(f"Error in public stats: {e}")
        await update.message.reply_text("⚠️ Could not fetch statistics at the moment.")

# Register handlers
application.add_handler(CommandHandler("gstats", gstats, filters=filters.ALL))
application.add_handler(CommandHandler("stats", stats, filters=filters.ALL))

# Optional: Add debug command to check collections
async def check_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check database connectivity and collections"""
    user_id = update.effective_user.id
    if user_id not in sudo_users and user_id != OWNER_ID:
        return
    
    try:
        collections_info = []
        
        # Check each collection
        collections = [
            ("Users", user_collection),
            ("Groups", top_global_groups_collection),
            ("Banned Users", BANNED_USERS),
            ("Banned Groups", banned_groups_collection),
            ("PM Users", pm_users)
        ]
        
        for name, collection in collections:
            try:
                count = await collection.count_documents({})
                collections_info.append(f"✅ {name}: {count} documents")
            except Exception as e:
                collections_info.append(f"❌ {name}: Error - {str(e)[:50]}")
        
        response = "🔍 <b>Database Check</b>\n════════════════════\n\n" + "\n".join(collections_info)
        await update.message.reply_text(response, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Database check failed: {str(e)}")

application.add_handler(CommandHandler("checkdb", check_db, filters=filters.ALL))