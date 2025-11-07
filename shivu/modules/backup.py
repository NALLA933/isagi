"""
MongoDB Backup and Restore System
Place this in shivu/modules/backup.py
"""

import os
import json
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio

LOGGER = logging.getLogger(__name__)

OWNER_ID = 5147822244

# Backup directory
BACKUP_DIR = "backups"
os.makedirs(BACKUP_DIR, exist_ok=True)

async def create_backup(context=None):
    """Create a full backup of all MongoDB collections"""
    try:
        from shivu import db
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_data = {}
        
        # Get all collections
        collections_to_backup = [
            'anime_characters_lol',
            'user_collection_lmaoooo',
            'user_totals_lmaoooo',
            'group_user_totalsssssss',
            'top_global_groups',
            'safari_users_collection',
            'safari_cooldown',
            'sudo_users_collection',
            'global_ban_users_collection',
            'total_pm_users',
            'Banned_Groups',
            'Banned_Users',
            'registered_users',
            'set_on_data',
            'set_off_data',
            'refeer_collection'
        ]
        
        LOGGER.info(f"Starting backup at {timestamp}")
        
        for collection_name in collections_to_backup:
            try:
                collection = db[collection_name]
                documents = await collection.find({}).to_list(length=None)
                
                # Convert ObjectId to string for JSON serialization
                for doc in documents:
                    if '_id' in doc:
                        doc['_id'] = str(doc['_id'])
                
                backup_data[collection_name] = documents
                LOGGER.info(f"Backed up {len(documents)} documents from {collection_name}")
            except Exception as e:
                LOGGER.error(f"Error backing up {collection_name}: {e}")
        
        # Save to file
        backup_file = os.path.join(BACKUP_DIR, f"backup_{timestamp}.json")
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)
        
        # Get file size
        file_size = os.path.getsize(backup_file) / (1024 * 1024)  # MB
        
        LOGGER.info(f"Backup completed: {backup_file} ({file_size:.2f} MB)")
        
        # Keep only last 7 backups
        cleanup_old_backups()
        
        return backup_file, file_size
    
    except Exception as e:
        LOGGER.error(f"Backup failed: {e}")
        return None, 0

def cleanup_old_backups(keep=7):
    """Keep only the most recent backups"""
    try:
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')])
        if len(backups) > keep:
            for old_backup in backups[:-keep]:
                os.remove(os.path.join(BACKUP_DIR, old_backup))
                LOGGER.info(f"Deleted old backup: {old_backup}")
    except Exception as e:
        LOGGER.error(f"Error cleaning up backups: {e}")

async def restore_backup(backup_file):
    """Restore database from backup file"""
    try:
        from shivu import db
        
        LOGGER.info(f"Starting restore from {backup_file}")
        
        with open(backup_file, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
        
        restored_collections = []
        
        for collection_name, documents in backup_data.items():
            try:
                collection = db[collection_name]
                
                # Clear existing data (optional - remove if you want to merge)
                # await collection.delete_many({})
                
                if documents:
                    # Remove _id field to let MongoDB generate new ones
                    for doc in documents:
                        if '_id' in doc:
                            del doc['_id']
                    
                    await collection.insert_many(documents)
                    restored_collections.append(f"{collection_name} ({len(documents)} docs)")
                    LOGGER.info(f"Restored {len(documents)} documents to {collection_name}")
            
            except Exception as e:
                LOGGER.error(f"Error restoring {collection_name}: {e}")
        
        LOGGER.info("Restore completed successfully")
        return True, restored_collections
    
    except Exception as e:
        LOGGER.error(f"Restore failed: {e}")
        return False, []

# Command Handlers

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual backup command - /backup"""
    from shivu import sudo_users
    
    user_id = update.effective_user.id
    
    # Check if user is authorized
    if user_id not in sudo_users and user_id != OWNER_ID:
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    msg = await update.message.reply_text("🔄 Creating backup... Please wait.")
    
    backup_file, file_size = await create_backup()
    
    if backup_file:
        await msg.edit_text(
            f"✅ **Backup Created Successfully!**\n\n"
            f"📁 File: `{os.path.basename(backup_file)}`\n"
            f"📊 Size: {file_size:.2f} MB\n"
            f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        # Send the backup file
        try:
            with open(backup_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=os.path.basename(backup_file),
                    caption="📦 Database Backup"
                )
        except Exception as e:
            await update.message.reply_text(f"⚠️ Backup created but couldn't send file: {e}")
    else:
        await msg.edit_text("❌ Backup failed. Check logs for details.")

async def restore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restore from backup - /restore [filename]"""
    from shivu import OWNER_ID
    
    user_id = update.effective_user.id
    
    # Only owner can restore
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Only the owner can restore backups.")
        return
    
    # Check if file is attached
    if update.message.reply_to_message and update.message.reply_to_message.document:
        msg = await update.message.reply_text("🔄 Downloading backup file...")
        
        try:
            file = await update.message.reply_to_message.document.get_file()
            backup_file = os.path.join(BACKUP_DIR, update.message.reply_to_message.document.file_name)
            await file.download_to_drive(backup_file)
            
            await msg.edit_text("🔄 Restoring database... This may take a while.")
            
            success, restored = await restore_backup(backup_file)
            
            if success:
                await msg.edit_text(
                    f"✅ **Restore Completed!**\n\n"
                    f"📦 Restored Collections:\n" +
                    "\n".join(f"• {col}" for col in restored)
                )
            else:
                await msg.edit_text("❌ Restore failed. Check logs for details.")
        
        except Exception as e:
            await msg.edit_text(f"❌ Error: {e}")
    
    else:
        # List available backups
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')], reverse=True)
        
        if backups:
            backup_list = "\n".join(f"• `{b}`" for b in backups[:10])
            await update.message.reply_text(
                f"📦 **Available Backups:**\n\n{backup_list}\n\n"
                f"**To restore:** Reply to a backup file with `/restore`"
            )
        else:
            await update.message.reply_text("❌ No backups found.")

async def list_backups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all available backups - /listbackups"""
    from shivu import sudo_users, OWNER_ID
    
    user_id = update.effective_user.id
    
    if user_id not in sudo_users and user_id != OWNER_ID:
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')], reverse=True)
    
    if backups:
        backup_info = []
        for backup in backups[:15]:
            filepath = os.path.join(BACKUP_DIR, backup)
            size = os.path.getsize(filepath) / (1024 * 1024)
            backup_info.append(f"• `{backup}` ({size:.2f} MB)")
        
        await update.message.reply_text(
            f"📦 **Available Backups:** ({len(backups)} total)\n\n" +
            "\n".join(backup_info)
        )
    else:
        await update.message.reply_text("❌ No backups found.")

async def auto_backup_job(context):
    """Automatic backup job"""
    LOGGER.info("Running automatic backup...")
    backup_file, file_size = await create_backup(context)
    
    if backup_file:
        # Send to specified user (5147822244)
        BACKUP_USER_ID = 5147822244
        try:
            with open(backup_file, 'rb') as f:
                await context.bot.send_document(
                    chat_id=BACKUP_USER_ID,
                    document=f,
                    filename=os.path.basename(backup_file),
                    caption=f"🤖 **Automatic Backup**\n\n📊 Size: {file_size:.2f} MB\n🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            LOGGER.info(f"Backup sent to user {BACKUP_USER_ID}")
        except Exception as e:
            LOGGER.error(f"Failed to send backup to user {BACKUP_USER_ID}: {e}")

def setup_backup_handlers(application):
    """Setup backup command handlers and scheduler"""
    application.add_handler(CommandHandler("backup", backup_command))
    application.add_handler(CommandHandler("restore", restore_command))
    application.add_handler(CommandHandler("listbackups", list_backups_command))
    
    # Setup automatic backup (daily at 3 AM)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(auto_backup_job, 'cron', hour=3, minute=0, args=[application])
    scheduler.start()
    
    LOGGER.info("Backup system initialized - Automatic backups at 3 AM daily")

# Call this in your main bot file
# from shivu.modules.backup import setup_backup_handlers
# setup_backup_handlers(application)