"""
MongoDB Backup and Restore System - HOURLY AUTO-BACKUP VERSION
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
from bson import ObjectId

LOGGER = logging.getLogger(__name__)

# Backup directory
BACKUP_DIR = "backups"
os.makedirs(BACKUP_DIR, exist_ok=True)

# Owner ID
OWNER_ID = 5147822244

def convert_objectid(obj):
    """Recursively convert ObjectId to string in nested structures"""
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: convert_objectid(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid(item) for item in obj]
    else:
        return obj

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

                # Convert ALL ObjectIds to strings recursively
                documents = [convert_objectid(doc) for doc in documents]

                backup_data[collection_name] = documents
                LOGGER.info(f"Backed up {len(documents)} documents from {collection_name}")
            except Exception as e:
                LOGGER.error(f"Error backing up {collection_name}: {e}")

        # Save to file with proper encoding
        backup_file = os.path.join(BACKUP_DIR, f"backup_{timestamp}.json")
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False, default=str)

        # Get file size
        file_size = os.path.getsize(backup_file) / (1024 * 1024)  # MB

        LOGGER.info(f"Backup completed: {backup_file} ({file_size:.2f} MB)")

        # Keep only last 24 backups (1 day worth of hourly backups)
        cleanup_old_backups(keep=24)

        return backup_file, file_size

    except Exception as e:
        LOGGER.error(f"Backup failed: {e}")
        import traceback
        LOGGER.error(traceback.format_exc())
        return None, 0

def cleanup_old_backups(keep=24):
    """Keep only the most recent backups (default: last 24 hours)"""
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
        import traceback
        LOGGER.error(traceback.format_exc())
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
    from shivu import sudo_users

    user_id = update.effective_user.id

    if user_id not in sudo_users and user_id != OWNER_ID:
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return

    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')], reverse=True)

    if backups:
        backup_info = []
        total_size = 0
        for backup in backups[:20]:
            filepath = os.path.join(BACKUP_DIR, backup)
            size = os.path.getsize(filepath) / (1024 * 1024)
            total_size += size
            backup_info.append(f"• `{backup}` ({size:.2f} MB)")

        await update.message.reply_text(
            f"📦 **Available Backups:** ({len(backups)} total)\n"
            f"💾 **Total Size:** {total_size:.2f} MB\n\n" +
            "\n".join(backup_info)
        )
    else:
        await update.message.reply_text("❌ No backups found.")

async def hourly_backup_job(context):
    """Hourly automatic backup job"""
    LOGGER.info("Running hourly automatic backup...")
    backup_file, file_size = await create_backup(context)

    if backup_file:
        # Send to owner via PM
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Send backup file to owner
            with open(backup_file, 'rb') as f:
                await context.bot.send_document(
                    chat_id=OWNER_ID,
                    document=f,
                    filename=os.path.basename(backup_file),
                    caption=(
                        f"🤖 **Hourly Automatic Backup**\n\n"
                        f"📊 Size: {file_size:.2f} MB\n"
                        f"🕐 Time: {current_time}\n"
                        f"⏰ Next backup in 1 hour"
                    )
                )
            LOGGER.info(f"Hourly backup sent to owner {OWNER_ID}")
        except Exception as e:
            LOGGER.error(f"Failed to send hourly backup to owner {OWNER_ID}: {e}")
            # Try to send error notification
            try:
                await context.bot.send_message(
                    chat_id=OWNER_ID,
                    text=f"⚠️ **Backup Error**\n\nFailed to send backup file: {e}"
                )
            except:
                pass
    else:
        # Notify owner of backup failure
        try:
            await context.bot.send_message(
                chat_id=OWNER_ID,
                text=f"❌ **Hourly Backup Failed**\n\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\nCheck bot logs for details."
            )
        except Exception as e:
            LOGGER.error(f"Failed to send backup failure notification: {e}")

def setup_backup_handlers(application):
    """Setup backup command handlers and scheduler"""
    application.add_handler(CommandHandler("backup", backup_command, block=False))
    application.add_handler(CommandHandler("restore", restore_command, block=False))
    application.add_handler(CommandHandler("listbackups", list_backups_command, block=False))

    # Setup automatic hourly backup
    scheduler = AsyncIOScheduler()
    
    # Run backup every hour at the start of the hour (XX:00:00)
    scheduler.add_job(
        hourly_backup_job, 
        'cron', 
        minute=0,  # At minute 0 of every hour
        args=[application]
    )
    
    scheduler.start()

    LOGGER.info(f"✅ Backup system initialized - Hourly automatic backups to owner {OWNER_ID}")
    LOGGER.info(f"📅 Keeping last 24 backups (1 day retention)")
    LOGGER.info(f"⏰ Backups run every hour at XX:00:00")

# Call this in your main bot file:
# from shivu.modules.backup import setup_backup_handlers
# setup_backup_handlers(application)