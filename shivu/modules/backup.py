"""
MongoDB Backup and Restore System - Fixed Version
Place this in shivu/modules/backup.py
"""

import os
import json
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from bson import ObjectId
import pytz

LOGGER = logging.getLogger(__name__)

BACKUP_DIR = "backups"
os.makedirs(BACKUP_DIR, exist_ok=True)

OWNER_ID = 5147822244

# Global scheduler instance
scheduler = None

def convert_objectid(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: convert_objectid(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid(item) for item in obj]
    return obj

async def create_backup():
    try:
        from shivu import db

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_data = {}

        collections = [
            'anime_characters_lol', 'user_collection_lmaoooo', 'user_totals_lmaoooo',
            'group_user_totalsssssss', 'top_global_groups', 'safari_users_collection',
            'safari_cooldown', 'sudo_users_collection', 'global_ban_users_collection',
            'total_pm_users', 'Banned_Groups', 'Banned_Users', 'registered_users',
            'set_on_data', 'set_off_data', 'refeer_collection'
        ]

        for col_name in collections:
            try:
                collection = db[col_name]
                documents = await collection.find({}).to_list(length=None)
                backup_data[col_name] = [convert_objectid(doc) for doc in documents]
                LOGGER.info(f"Backed up {len(documents)} documents from {col_name}")
            except Exception as e:
                LOGGER.error(f"Error backing up {col_name}: {e}")

        backup_file = os.path.join(BACKUP_DIR, f"backup_{timestamp}.json")
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False, default=str)

        file_size = os.path.getsize(backup_file) / (1024 * 1024)
        cleanup_old_backups(24)

        return backup_file, file_size
    except Exception as e:
        LOGGER.error(f"Backup failed: {e}")
        return None, 0

def cleanup_old_backups(keep=24):
    try:
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')])
        if len(backups) > keep:
            for old_backup in backups[:-keep]:
                os.remove(os.path.join(BACKUP_DIR, old_backup))
                LOGGER.info(f"Deleted old backup: {old_backup}")
    except Exception as e:
        LOGGER.error(f"Cleanup error: {e}")

async def restore_backup(backup_file):
    try:
        from shivu import db

        with open(backup_file, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)

        restored_collections = []

        for collection_name, documents in backup_data.items():
            try:
                collection = db[collection_name]
                if documents:
                    for doc in documents:
                        if '_id' in doc:
                            del doc['_id']
                    await collection.insert_many(documents)
                    restored_collections.append(f"{collection_name} ({len(documents)} docs)")
            except Exception as e:
                LOGGER.error(f"Error restoring {collection_name}: {e}")

        return True, restored_collections
    except Exception as e:
        LOGGER.error(f"Restore failed: {e}")
        return False, []

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from shivu import sudo_users

    user_id = update.effective_user.id
    if user_id not in sudo_users and user_id != OWNER_ID:
        await update.message.reply_text("You don't have permission.")
        return

    msg = await update.message.reply_text("🔄 Creating backup...")
    backup_file, file_size = await create_backup()

    if backup_file:
        await msg.edit_text(
            f"✅ Backup Created\n\n"
            f"📁 File: {os.path.basename(backup_file)}\n"
            f"💾 Size: {file_size:.2f} MB\n"
            f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
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
        await msg.edit_text("❌ Backup failed. Check logs.")

async def restore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can restore.")
        return

    if update.message.reply_to_message and update.message.reply_to_message.document:
        msg = await update.message.reply_text("⬇️ Downloading backup file...")
        try:
            file = await update.message.reply_to_message.document.get_file()
            backup_file = os.path.join(BACKUP_DIR, update.message.reply_to_message.document.file_name)
            await file.download_to_drive(backup_file)

            await msg.edit_text("🔄 Restoring database...")
            success, restored = await restore_backup(backup_file)

            if success:
                await msg.edit_text("✅ Restore Completed\n\n" + "\n".join(restored))
            else:
                await msg.edit_text("❌ Restore failed.")
        except Exception as e:
            await msg.edit_text(f"❌ Error: {e}")
            LOGGER.error(f"Restore command error: {e}", exc_info=True)
    else:
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')], reverse=True)
        if backups:
            backup_list = "\n".join(backups[:10])
            await update.message.reply_text(
                f"📋 Available Backups:\n\n{backup_list}\n\n"
                f"Reply to a backup file with /restore to restore it."
            )
        else:
            await update.message.reply_text("❌ No backups found.")

async def list_backups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from shivu import sudo_users

    if update.effective_user.id not in sudo_users and update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ You don't have permission.")
        return

    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')], reverse=True)
    if backups:
        backup_info = []
        total_size = 0
        for backup in backups[:20]:
            size = os.path.getsize(os.path.join(BACKUP_DIR, backup)) / (1024 * 1024)
            total_size += size
            backup_info.append(f"📄 {backup} ({size:.2f} MB)")

        await update.message.reply_text(
            f"📦 Backups: {len(backups)} total\n"
            f"💾 Total Size: {total_size:.2f} MB\n\n" + "\n".join(backup_info)
        )
    else:
        await update.message.reply_text("❌ No backups found.")

async def test_backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test command to trigger backup immediately"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner only.")
        return
    
    await update.message.reply_text("🧪 Testing automatic backup...")
    await hourly_backup_job(context.application)
    await update.message.reply_text("✅ Test backup completed! Check your DMs.")

async def hourly_backup_job(application):
    """Scheduled backup job that runs every hour"""
    LOGGER.info("=" * 50)
    LOGGER.info("Starting hourly backup job...")
    LOGGER.info(f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # Create backup
        backup_file, file_size = await create_backup()

        if backup_file:
            LOGGER.info(f"Backup created: {backup_file} ({file_size:.2f} MB)")
            
            try:
                # Send backup file to owner
                with open(backup_file, 'rb') as f:
                    await application.bot.send_document(
                        chat_id=OWNER_ID,
                        document=f,
                        filename=os.path.basename(backup_file),
                        caption=(
                            f"⏰ Hourly Automated Backup\n\n"
                            f"💾 Size: {file_size:.2f} MB\n"
                            f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"📊 Status: ✅ Success"
                        )
                    )
                LOGGER.info(f"✅ Backup successfully sent to owner {OWNER_ID}")
                
            except Exception as e:
                LOGGER.error(f"❌ Failed to send backup to owner: {e}", exc_info=True)
                try:
                    # Send error notification
                    await application.bot.send_message(
                        chat_id=OWNER_ID,
                        text=(
                            f"⚠️ Backup Created But Send Failed\n\n"
                            f"📁 File: {os.path.basename(backup_file)}\n"
                            f"💾 Size: {file_size:.2f} MB\n"
                            f"❌ Error: {str(e)[:100]}"
                        )
                    )
                except Exception as notify_error:
                    LOGGER.error(f"Failed to send error notification: {notify_error}")
        else:
            LOGGER.error("❌ Backup creation failed")
            try:
                # Notify owner of failure
                await application.bot.send_message(
                    chat_id=OWNER_ID,
                    text=(
                        f"❌ Automated Backup Failed\n\n"
                        f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"Check bot logs for details."
                    )
                )
            except Exception as e:
                LOGGER.error(f"Failed to send failure notification: {e}")
                
    except Exception as e:
        LOGGER.error(f"💥 Critical error in backup job: {e}", exc_info=True)
        try:
            await application.bot.send_message(
                chat_id=OWNER_ID,
                text=f"💥 Critical Backup Error\n\n{str(e)[:200]}"
            )
        except:
            pass
    
    LOGGER.info("Hourly backup job completed")
    LOGGER.info("=" * 50)

def setup_backup_handlers(application):
    """Initialize backup system with handlers and scheduler"""
    global scheduler
    
    # Add command handlers
    application.add_handler(CommandHandler("backup", backup_command, block=False))
    application.add_handler(CommandHandler("restore", restore_command, block=False))
    application.add_handler(CommandHandler("listbackups", list_backups_command, block=False))
    application.add_handler(CommandHandler("testbackup", test_backup_command, block=False))

    # Create scheduler with timezone
    scheduler = AsyncIOScheduler(timezone=pytz.UTC)
    
    # Schedule hourly backup at minute 0 of every hour
    scheduler.add_job(
        hourly_backup_job,
        trigger=CronTrigger(minute=0, timezone=pytz.UTC),
        args=[application],
        id='hourly_backup',
        replace_existing=True,
        misfire_grace_time=300  # Allow 5 minutes grace time if job is delayed
    )
    
    # Start the scheduler
    scheduler.start()
    
    LOGGER.info("=" * 50)
    LOGGER.info("📦 Backup System Initialized")
    LOGGER.info(f"👤 Owner ID: {OWNER_ID}")
    LOGGER.info(f"⏰ Scheduled: Every hour at minute 0 (UTC)")
    LOGGER.info(f"📁 Backup Directory: {BACKUP_DIR}")
    LOGGER.info(f"🕐 Current Time: {datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    LOGGER.info(f"⏭️  Next Backup: {scheduler.get_job('hourly_backup').next_run_time}")
    LOGGER.info("=" * 50)

# Call in main bot file:
# from shivu.modules.backup import setup_backup_handlers
# setup_backup_handlers(application)