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

async def check_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check database connectivity and collections - Debug command"""
    user_id = update.effective_user.id
    
    # Debug: Log who is trying to access
    LOGGER.info(f"User {user_id} trying to access checkdb command")
    LOGGER.info(f"sudo_users: {sudo_users}")
    LOGGER.info(f"OWNER_ID: {OWNER_ID}")
    
    # First check authorization - with less restrictive check for debugging
    if user_id != OWNER_ID and user_id != 8420981179:
        # Check if user is in sudo_users list
        if hasattr(sudo_users, '__contains__'):
            if user_id not in sudo_users:
                await update.message.reply_text("❌ You are not authorized to use this command.")
                return
        else:
            await update.message.reply_text("❌ sudo_users variable issue. Contact owner.")
            return
    
    try:
        message_parts = []
        message_parts.append("🔍 <b>DATABASE DIAGNOSTICS</b>")
        message_parts.append("════════════════════════════")
        message_parts.append("")
        
        # Test 1: Check each collection one by one
        collections_to_check = [
            ("Users Collection", user_collection),
            ("Groups Collection", top_global_groups_collection),
            ("Banned Users", BANNED_USERS),
            ("Banned Groups", banned_groups_collection),
            ("PM Users", pm_users)
        ]
        
        for collection_name, collection in collections_to_check:
            try:
                # Try to get collection info
                count = await collection.count_documents({})
                
                # Try to get one sample document to check structure
                sample = await collection.find_one({})
                
                if sample:
                    sample_info = f" - Sample ID: {str(sample.get('_id', 'N/A'))[:20]}..."
                else:
                    sample_info = " - Empty collection"
                    
                message_parts.append(f"✅ <b>{collection_name}:</b>")
                message_parts.append(f"   📊 Documents: {count}")
                message_parts.append(f"   {sample_info}")
                
            except Exception as e:
                message_parts.append(f"❌ <b>{collection_name}:</b>")
                message_parts.append(f"   Error: {str(e)[:100]}")
            
            message_parts.append("")
        
        # Test 2: Check specific fields in user collection
        message_parts.append("<b>USER COLLECTION FIELDS CHECK:</b>")
        try:
            user_sample = await user_collection.find_one({})
            if user_sample:
                available_fields = list(user_sample.keys())
                message_parts.append(f"   Available fields: {', '.join(available_fields[:10])}")
                if len(available_fields) > 10:
                    message_parts.append(f"   ... and {len(available_fields) - 10} more")
            else:
                message_parts.append("   No users found in collection")
        except Exception as e:
            message_parts.append(f"   Error checking fields: {str(e)[:100]}")
        
        message_parts.append("")
        
        # Test 3: Check application info
        message_parts.append("<b>BOT INFORMATION:</b>")
        message_parts.append(f"   Bot Username: @{context.bot.username}" if context.bot.username else "   Bot username not available")
        message_parts.append(f"   Your User ID: {user_id}")
        message_parts.append(f"   Owner ID: {OWNER_ID}")
        message_parts.append(f"   Sudo Users Count: {len(sudo_users) if hasattr(sudo_users, '__len__') else 'N/A'}")
        message_parts.append(f"   Command Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Send the diagnostic message
        full_message = "\n".join(message_parts)
        
        # Split message if too long (Telegram has 4096 character limit)
        if len(full_message) > 4000:
            part1 = full_message[:2000]
            part2 = full_message[2000:4000]
            await update.message.reply_text(part1, parse_mode=ParseMode.HTML)
            await update.message.reply_text(part2, parse_mode=ParseMode.HTML)
            if len(full_message) > 4000:
                part3 = full_message[4000:]
                await update.message.reply_text(part3, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(full_message, parse_mode=ParseMode.HTML)
            
    except Exception as e:
        LOGGER.error(f"Error in check_db: {str(e)}", exc_info=True)
        error_msg = (
            f"❌ <b>Critical Error in check_db:</b>\n"
            f"Error: {str(e)[:200]}\n\n"
            f"Please check logs for details."
        )
        await update.message.reply_text(error_msg, parse_mode=ParseMode.HTML)

# Simple test command without any restrictions
async def test_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test command for everyone - no restrictions"""
    try:
        # Just try to count users
        count = await user_collection.count_documents({})
        
        response = (
            f"✅ <b>Database Test Successful!</b>\n\n"
            f"📊 Total Users: {count}\n"
            f"🕒 Time: {datetime.now().strftime('%H:%M:%S')}\n"
            f"👤 Your ID: {update.effective_user.id}"
        )
        
        await update.message.reply_text(response, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        error_msg = (
            f"❌ <b>Database Test Failed!</b>\n\n"
            f"Error: {str(e)[:200]}\n"
            f"This means the database connection is not working."
        )
        await update.message.reply_text(error_msg, parse_mode=ParseMode.HTML)

# Fix the original gstats command with better debugging
async def gstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global statistics command"""
    user_id = update.effective_user.id
    
    # Debug authorization
    LOGGER.info(f"gstats accessed by user {user_id}")
    
    # Check authorization - same logic as before
    authorized = False
    if user_id == OWNER_ID or user_id == 8420981179:
        authorized = True
    elif hasattr(sudo_users, '__contains__') and user_id in sudo_users:
        authorized = True
    
    if not authorized:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    
    try:
        # Try to get basic stats
        total_users = await user_collection.count_documents({})
        total_chats = await top_global_groups_collection.count_documents({})
        banned_users_count = await BANNED_USERS.count_documents({})
        banned_groups_count = await banned_groups_collection.count_documents({})
        pm_users_count = await pm_users.count_documents({})
        
        stats_text = (
            f"📊 <b>Global Statistics</b>\n"
            f"════════════════════\n\n"
            f"👥 <b>Total Users:</b> {total_users:,}\n"
            f"👥 <b>Total Chats:</b> {total_chats:,}\n"
            f"📩 <b>PM Users:</b> {pm_users_count:,}\n"
            f"⛔ <b>Banned Users:</b> {banned_users_count:,}\n"
            f"⛔ <b>Banned Groups:</b> {banned_groups_count:,}\n\n"
            f"🕒 <i>Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</i>"
        )
        
        await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        LOGGER.error(f"Error in gstats: {e}")
        await update.message.reply_text(
            f"❌ Error fetching statistics.\nError: {str(e)[:100]}",
            parse_mode=ParseMode.HTML
        )

# Add all handlers
application.add_handler(CommandHandler("gstats", gstats, filters=filters.ALL))
application.add_handler(CommandHandler("checkdb", check_db, filters=filters.ALL))
application.add_handler(CommandHandler("testdb", test_db, filters=filters.ALL))
application.add_handler(CommandHandler("dbinfo", check_db, filters=filters.ALL))  # Alias

# Also add a simple ping command to check if bot is alive
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check if bot is responsive"""
    start_time = time.time()
    message = await update.message.reply_text("🏓 Pong!")
    end_time = time.time()
    latency = (end_time - start_time) * 1000  # Convert to milliseconds
    
    await message.edit_text(
        f"🏓 <b>Pong!</b>\n"
        f"📶 Latency: {latency:.0f} ms\n"
        f"🕒 Time: {datetime.now().strftime('%H:%M:%S')}",
        parse_mode=ParseMode.HTML
    )

application.add_handler(CommandHandler("ping", ping, filters=filters.ALL))