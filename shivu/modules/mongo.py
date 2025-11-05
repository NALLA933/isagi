from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from shivu import db, collection


OWNER_ID = 5147822244

async def db_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check MongoDB storage and statistics"""
    user_id = update.effective_user.id
    
    # Only allow owner/sudo users to check stats
    if user_id not in sudo_users and user_id != OWNER_ID:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    try:
        # Get database stats
        stats = await db.command("dbStats")
        
        # Format the data
        storage_size = stats.get('storageSize', 0) / (1024 * 1024)  # Convert to MB
        data_size = stats.get('dataSize', 0) / (1024 * 1024)
        index_size = stats.get('indexSize', 0) / (1024 * 1024)
        
        # Count documents in collections
        users_count = await user_collection.count_documents({})
        characters_count = await collection.count_documents({})
        banned_users_count = await BANNED_USERS.count_documents({})
        
        message = f"""
📊 **Database Statistics**

💾 **Storage Info:**
• Storage Size: {storage_size:.2f} MB
• Data Size: {data_size:.2f} MB
• Index Size: {index_size:.2f} MB
• Collections: {stats.get('collections', 0)}

📈 **Document Counts:**
• Users: {users_count}
• Characters: {characters_count}
• Banned Users: {banned_users_count}
        """
        
        await update.message.reply_text(message)
        
    except Exception as e:
        LOGGER.error(f"Error getting DB stats: {e}")
        await update.message.reply_text(f"Error: {str(e)}")

# Add this handler to your application
application.add_handler(CommandHandler("dbstats", db_stats))