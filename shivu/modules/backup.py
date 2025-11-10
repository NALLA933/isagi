import os
import json
import logging
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
    
    msg = await update.message.reply_text("Creating backup...")
    backup_file, file_size = await create_backup()
    
    if backup_file:
        await msg.edit_text(
            f"Backup Created\n\n"
            f"File: {os.path.basename(backup_file)}\n"
            f"Size: {file_size:.2f} MB\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        try:
            with open(backup_file, 'rb') as f:
                await update.message.reply_document(document=f, filename=os.path.basename(backup_file))
        except Exception as e:
            await update.message.reply_text(f"Backup created but couldn't send file: {e}")
    else:
        await msg.edit_text("Backup failed. Check logs.")

async def restore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Only owner can restore.")
        return
    
    if update.message.reply_to_message and update.message.reply_to_message.document:
        msg = await update.message.reply_text("Downloading backup file...")
        try:
            file = await update.message.reply_to_message.document.get_file()
            backup_file = os.path.join(BACKUP_DIR, update.message.reply_to_message.document.file_name)
            await file.download_to_drive(backup_file)
            
            await msg.edit_text("Restoring database...")
            success, restored = await restore_backup(backup_file)
            
            if success:
                await msg.edit_text("Restore Completed\n\n" + "\n".join(restored))
            else:
                await msg.edit_text("Restore failed.")
        except Exception as e:
            await msg.edit_text(f"Error: {e}")
    else:
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')], reverse=True)
        if backups:
            backup_list = "\n".join(backups[:10])
            await update.message.reply_text(f"Available Backups:\n\n{backup_list}\n\nReply to a file with /restore")
        else:
            await update.message.reply_text("No backups found.")

async def list_backups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from shivu import sudo_users
    
    if update.effective_user.id not in sudo_users and update.effective_user.id != OWNER_ID:
        await update.message.reply_text("You don't have permission.")
        return
    
    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')], reverse=True)
    if backups:
        backup_info = []
        total_size = 0
        for backup in backups[:20]:
            size = os.path.getsize(os.path.join(BACKUP_DIR, backup)) / (1024 * 1024)
            total_size += size
            backup_info.append(f"{backup} ({size:.2f} MB)")
        
        await update.message.reply_text(
            f"Backups: {len(backups)} total\n"
            f"Total Size: {total_size:.2f} MB\n\n" + "\n".join(backup_info)
        )
    else:
        await update.message.reply_text("No backups found.")

async def test_backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Owner only.")
        return
    
    await update.message.reply_text("Testing backup...")
    await hourly_backup_job(context.application)
    await update.message.reply_text("Test completed.")

async def hourly_backup_job(application):
    try:
        backup_file, file_size = await create_backup()
        
        if backup_file:
            try:
                with open(backup_file, 'rb') as f:
                    await application.bot.send_document(
                        chat_id=OWNER_ID,
                        document=f,
                        filename=os.path.basename(backup_file),
                        caption=(
                            f"Hourly Backup\n\n"
                            f"Size: {file_size:.2f} MB\n"
                            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                    )
            except Exception as e:
                LOGGER.error(f"Failed to send backup: {e}")
                await application.bot.send_message(
                    chat_id=OWNER_ID,
                    text=f"Backup created but send failed: {e}"
                )
        else:
            await application.bot.send_message(
                chat_id=OWNER_ID,
                text=f"Backup failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
    except Exception as e:
        LOGGER.error(f"Backup job error: {e}")

def setup_backup_handlers(application):
    global scheduler
    
    application.add_handler(CommandHandler("backup", backup_command, block=False))
    application.add_handler(CommandHandler("restore", restore_command, block=False))
    application.add_handler(CommandHandler("listbackups", list_backups_command, block=False))
    application.add_handler(CommandHandler("testbackup", test_backup_command, block=False))
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        hourly_backup_job,
        'interval',
        hours=1,
        args=[application],
        id='hourly_backup'
    )
    scheduler.start()
    
    LOGGER.info("Backup system initialized")

# In main bot file:
# from shivu.modules.backup import setup_backup_handlers
# setup_backup_handlers(application)