import os
import json
import logging
import asyncio
import traceback
from datetime import datetime
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bson import ObjectId

LOGGER = logging.getLogger(__name__)

BACKUP_DIR = "backups"
os.makedirs(BACKUP_DIR, exist_ok=True)

OWNER_ID = 5147822244
scheduler = None


def convert_objectid(obj):
    """Convert MongoDB ObjectId to string recursively"""
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: convert_objectid(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid(item) for item in obj]
    return obj


async def create_backup():
    """Create a backup of all database collections"""
    try:
        LOGGER.info("📦 Creating backup...")
        from shivu import db

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_data = {}
        total_docs = 0

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
                doc_count = len(documents)
                total_docs += doc_count
                LOGGER.info(f"  ✓ {col_name}: {doc_count} documents")
            except Exception as e:
                LOGGER.error(f"  ✗ {col_name}: {e}")

        backup_file = os.path.join(BACKUP_DIR, f"backup_{timestamp}.json")
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False, default=str)

        file_size = os.path.getsize(backup_file) / (1024 * 1024)
        LOGGER.info(f"✅ Backup complete: {total_docs} total documents, {file_size:.2f} MB")
        
        cleanup_old_backups(24)

        return backup_file, file_size
    except Exception as e:
        LOGGER.error(f"❌ Backup failed: {e}")
        LOGGER.error(traceback.format_exc())
        return None, 0


def cleanup_old_backups(keep=24):
    """Keep only the most recent N backups"""
    try:
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')])
        if len(backups) > keep:
            for old_backup in backups[:-keep]:
                old_file = os.path.join(BACKUP_DIR, old_backup)
                os.remove(old_file)
                LOGGER.info(f"🗑️ Removed old backup: {old_backup}")
    except Exception as e:
        LOGGER.error(f"Cleanup error: {e}")


async def restore_backup(backup_file):
    """Restore database from a backup file"""
    try:
        from shivu import db

        LOGGER.info(f"📥 Restoring from: {backup_file}")
        
        with open(backup_file, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)

        restored_collections = []

        for collection_name, documents in backup_data.items():
            try:
                collection = db[collection_name]
                if documents:
                    # Remove existing _id fields to avoid conflicts
                    for doc in documents:
                        if '_id' in doc:
                            del doc['_id']
                    await collection.insert_many(documents)
                    restored_collections.append(f"{collection_name} ({len(documents)} docs)")
                    LOGGER.info(f"  ✓ Restored {collection_name}: {len(documents)} documents")
            except Exception as e:
                LOGGER.error(f"  ✗ Error restoring {collection_name}: {e}")

        LOGGER.info(f"✅ Restore complete: {len(restored_collections)} collections")
        return True, restored_collections
    except Exception as e:
        LOGGER.error(f"❌ Restore failed: {e}")
        LOGGER.error(traceback.format_exc())
        return False, []


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler for /backup"""
    from shivu import sudo_users

    user_id = update.effective_user.id
    if user_id not in sudo_users and user_id != OWNER_ID:
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return

    msg = await update.message.reply_text("📦 Creating backup...")
    backup_file, file_size = await create_backup()

    if backup_file:
        await msg.edit_text(
            f"✅ Backup Created Successfully\n\n"
            f"📄 File: {os.path.basename(backup_file)}\n"
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
            LOGGER.error(f"Failed to send backup file: {e}")
            await update.message.reply_text(f"⚠️ Backup created but couldn't send file: {e}")
    else:
        await msg.edit_text("❌ Backup failed. Check logs for details.")


async def restore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler for /restore"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only the owner can restore backups.")
        return

    if update.message.reply_to_message and update.message.reply_to_message.document:
        msg = await update.message.reply_text("📥 Downloading backup file...")
        try:
            file = await update.message.reply_to_message.document.get_file()
            backup_file = os.path.join(BACKUP_DIR, update.message.reply_to_message.document.file_name)
            await file.download_to_drive(backup_file)

            await msg.edit_text("⚙️ Restoring database...")
            success, restored = await restore_backup(backup_file)

            if success:
                restored_text = "\n".join(restored)
                await msg.edit_text(
                    f"✅ Restore Completed\n\n"
                    f"📊 Restored Collections:\n{restored_text}"
                )
            else:
                await msg.edit_text("❌ Restore failed. Check logs for details.")
        except Exception as e:
            LOGGER.error(f"Restore command error: {e}")
            await msg.edit_text(f"❌ Error: {e}")
    else:
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')], reverse=True)
        if backups:
            backup_list = "\n".join(f"• {b}" for b in backups[:10])
            await update.message.reply_text(
                f"📋 Available Backups:\n\n{backup_list}\n\n"
                f"💡 Reply to a backup file with /restore to restore it."
            )
        else:
            await update.message.reply_text("❌ No backups found.")


async def list_backups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler for /listbackups"""
    from shivu import sudo_users

    if update.effective_user.id not in sudo_users and update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return

    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')], reverse=True)
    if backups:
        backup_info = []
        total_size = 0
        for backup in backups[:20]:
            size = os.path.getsize(os.path.join(BACKUP_DIR, backup)) / (1024 * 1024)
            total_size += size
            backup_info.append(f"• {backup} ({size:.2f} MB)")

        await update.message.reply_text(
            f"📋 Backup List\n\n"
            f"📊 Total Backups: {len(backups)}\n"
            f"💾 Total Size: {total_size:.2f} MB\n\n"
            f"Recent Backups:\n" + "\n".join(backup_info)
        )
    else:
        await update.message.reply_text("❌ No backups found.")


async def test_backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler for /testbackup - triggers immediate backup"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner only.")
        return

    msg = await update.message.reply_text("🧪 Testing backup system...")
    await hourly_backup_job(context.application)
    await msg.edit_text("✅ Test backup completed. Check your PM for the backup file.")


async def hourly_backup_job(application):
    """Job that runs every hour to create and send backup"""
    try:
        LOGGER.info("⏰ Starting hourly backup job...")
        backup_file, file_size = await create_backup()

        if backup_file:
            try:
                with open(backup_file, 'rb') as f:
                    await application.bot.send_document(
                        chat_id=OWNER_ID,
                        document=f,
                        filename=os.path.basename(backup_file),
                        caption=(
                            f"✅ Hourly Backup Complete\n\n"
                            f"💾 Size: {file_size:.2f} MB\n"
                            f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"📊 Status: All collections backed up successfully"
                        )
                    )
                LOGGER.info(f"✅ Backup sent successfully: {file_size:.2f} MB")
            except Exception as e:
                LOGGER.error(f"Failed to send backup: {e}")
                await application.bot.send_message(
                    chat_id=OWNER_ID,
                    text=f"⚠️ Backup created but send failed:\n{str(e)}\n\nFile: {os.path.basename(backup_file)}"
                )
        else:
            error_msg = f"❌ Backup failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            LOGGER.error(error_msg)
            await application.bot.send_message(
                chat_id=OWNER_ID,
                text=error_msg
            )
    except Exception as e:
        LOGGER.error(f"Backup job error: {e}")
        LOGGER.error(traceback.format_exc())
        try:
            await application.bot.send_message(
                chat_id=OWNER_ID,
                text=f"❌ Critical backup error:\n{str(e)}"
            )
        except:
            pass


async def start_scheduler(context):
    """Start the backup scheduler - called by job queue after bot starts"""
    global scheduler
    
    try:
        LOGGER.info("🔧 Starting backup scheduler...")
        
        # Create scheduler
        scheduler = AsyncIOScheduler()
        
        # Schedule hourly backup
        scheduler.add_job(
            hourly_backup_job,
            'interval',
            hours=1,
            args=[context.application],
            id='hourly_backup',
            replace_existing=True,
            max_instances=1
        )
        
        # Start scheduler
        scheduler.start()
        LOGGER.info("✅ Backup scheduler started - hourly backups enabled")
        
    except Exception as e:
        LOGGER.error(f"Failed to start scheduler: {e}")
        LOGGER.error(traceback.format_exc())


def setup_backup_handlers(application):
    """Setup backup command handlers and schedule scheduler start"""
    LOGGER.info("🔧 Setting up backup handlers...")
    
    # Add command handlers
    application.add_handler(CommandHandler("backup", backup_command, block=False))
    application.add_handler(CommandHandler("restore", restore_command, block=False))
    application.add_handler(CommandHandler("listbackups", list_backups_command, block=False))
    application.add_handler(CommandHandler("testbackup", test_backup_command, block=False))
    
    # Use job queue to start scheduler after 5 seconds (when event loop is running)
    application.job_queue.run_once(start_scheduler, when=5)
    
    LOGGER.info("✅ Backup handlers registered")
    LOGGER.info("📋 Commands available: /backup, /restore, /listbackups, /testbackup")


# Export functions for use in main bot
__all__ = [
    'setup_backup_handlers',
    'create_backup',
    'restore_backup',
    'hourly_backup_job',
    'start_scheduler'
]