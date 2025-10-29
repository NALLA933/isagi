"""
Fast Restart Command for Heroku Docker Bot
Optimized for quick restarts with minimal delay
"""

import os
import sys
import time
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from shivu import application, sudo_users, LOGGER, JOINLOGS

# Owner IDs who can restart the bot
OWNERS = [8420981179, 5147822244]


async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Fast restart the bot (Heroku/Docker compatible)
    Usage: /restart
    Only accessible by owners and sudo users
    """
    user_id = update.effective_user.id
    
    # Check permissions
    if user_id not in OWNERS and str(user_id) not in sudo_users:
        await update.message.reply_text(
            "❌ <b>Access Denied!</b>\n\n"
            "Only bot owners can use this command.",
            parse_mode='HTML'
        )
        return
    
    try:
        restart_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        chat_id = update.effective_chat.id
        
        # Send restart message (don't wait for response)
        restart_msg = await update.message.reply_text(
            "🔄 <b>Restarting...</b>",
            parse_mode='HTML'
        )
        
        LOGGER.info(f"🔄 Restart by {update.effective_user.first_name} (ID: {user_id})")
        
        # Store restart info IMMEDIATELY
        restart_data = f"{chat_id}|{restart_msg.message_id}|{user_id}"
        with open('/tmp/restart_info.txt', 'w') as f:
            f.write(restart_data)
        
        # Send log notification asynchronously (don't wait)
        asyncio.create_task(
            context.bot.send_message(
                chat_id=JOINLOGS,
                text=f"🔄 <b>Restarting...</b>\n⏰ {restart_time}\n👤 By: <code>{user_id}</code>",
                parse_mode='HTML'
            )
        )
        
        # IMMEDIATE RESTART - No delays!
        LOGGER.info("⚡ Executing immediate restart...")
        
        # Use os.execl for faster restart (replaces process immediately)
        os.execl(sys.executable, sys.executable, '-m', 'shivu')
        
    except Exception as e:
        LOGGER.error(f"❌ Restart error: {e}")
        try:
            await update.message.reply_text(f"❌ <b>Restart Failed!</b>\n<code>{str(e)}</code>", parse_mode='HTML')
        except:
            pass


async def restart_silent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Ultra-fast silent restart
    Usage: /srestart
    No messages, instant restart
    """
    user_id = update.effective_user.id
    
    # Check permissions
    if user_id not in OWNERS and str(user_id) not in sudo_users:
        return
    
    try:
        LOGGER.info(f"🔇 Silent restart by User ID: {user_id}")
        
        # INSTANT RESTART - Zero delay
        os.execl(sys.executable, sys.executable, '-m', 'shivu')
        
    except Exception as e:
        LOGGER.error(f"❌ Silent restart error: {e}")


async def ping_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Check if bot is alive and responsive
    Usage: /ping
    """
    start_time = time.time()
    
    message = await update.message.reply_text("🏓 Pinging...")
    
    end_time = time.time()
    ping_time = round((end_time - start_time) * 1000, 2)
    
    # Get uptime
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
            uptime_str = time.strftime('%H:%M:%S', time.gmtime(uptime_seconds))
    except:
        uptime_str = "N/A"
    
    await message.edit_text(
        f"🏓 <b>Pong!</b>\n\n"
        f"⚡ <b>Response:</b> <code>{ping_time}ms</code>\n"
        f"⏱ <b>Uptime:</b> <code>{uptime_str}</code>\n"
        f"✅ <b>Status:</b> Online",
        parse_mode='HTML'
    )


async def get_bot_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Get recent bot logs
    Usage: /logs [lines]
    Default: 50 lines
    """
    user_id = update.effective_user.id
    
    # Check permissions
    if user_id not in OWNERS and str(user_id) not in sudo_users:
        await update.message.reply_text("❌ You don't have permission to view logs.")
        return
    
    # Get number of lines
    num_lines = 50
    if context.args:
        try:
            num_lines = int(context.args[0])
            num_lines = max(10, min(num_lines, 500))
        except:
            pass
    
    try:
        log_file = 'log.txt'
        
        if not os.path.exists(log_file):
            await update.message.reply_text(
                "⚠️ <b>Log file not found!</b>",
                parse_mode='HTML'
            )
            return
        
        # Read last N lines efficiently using tail
        try:
            # Use tail command for faster reading
            log_content = os.popen(f'tail -n {num_lines} {log_file}').read()
        except:
            # Fallback to Python method
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                log_content = ''.join(lines[-num_lines:])
        
        if not log_content.strip():
            await update.message.reply_text("⚠️ <b>Log file is empty!</b>", parse_mode='HTML')
            return
        
        # Send as file if too long
        if len(log_content) > 4000:
            log_filename = f'/tmp/bot_logs_{int(time.time())}.txt'
            with open(log_filename, 'w', encoding='utf-8') as f:
                f.write(log_content)
            
            await update.message.reply_document(
                document=open(log_filename, 'rb'),
                filename=f'logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt',
                caption=f"📋 <b>Last {num_lines} lines</b>",
                parse_mode='HTML'
            )
            
            # Cleanup
            try:
                os.remove(log_filename)
            except:
                pass
        else:
            await update.message.reply_text(
                f"📋 <b>Last {num_lines} lines:</b>\n\n<pre>{log_content}</pre>",
                parse_mode='HTML'
            )
    
    except Exception as e:
        LOGGER.error(f"Error reading logs: {e}")
        await update.message.reply_text(
            f"❌ <b>Error:</b> <code>{str(e)}</code>",
            parse_mode='HTML'
        )


async def clear_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Clear bot logs
    Usage: /clearlogs
    """
    user_id = update.effective_user.id
    
    # Only owners
    if user_id not in OWNERS:
        await update.message.reply_text(
            "❌ <b>Access Denied!</b>\n\nOnly owners can clear logs.",
            parse_mode='HTML'
        )
        return
    
    try:
        log_file = 'log.txt'
        
        if os.path.exists(log_file):
            file_size = os.path.getsize(log_file) / 1024  # KB
            
            # Clear the log file
            with open(log_file, 'w') as f:
                f.write(f"# Logs cleared by User {user_id} at {datetime.now()}\n")
            
            await update.message.reply_text(
                f"✅ <b>Logs Cleared!</b>\n\n"
                f"📊 <b>Previous Size:</b> <code>{file_size:.2f} KB</code>",
                parse_mode='HTML'
            )
            
            # Notify log channel
            try:
                await context.bot.send_message(
                    chat_id=JOINLOGS,
                    text=f"🗑 <b>Logs Cleared</b>\n👤 By: <code>{user_id}</code>\n📊 Size: <code>{file_size:.2f} KB</code>",
                    parse_mode='HTML'
                )
            except:
                pass
        else:
            await update.message.reply_text("⚠️ <b>No log file found!</b>", parse_mode='HTML')
    
    except Exception as e:
        await update.message.reply_text(f"❌ <b>Error:</b> <code>{str(e)}</code>", parse_mode='HTML')


async def shutdown_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Gracefully shutdown the bot
    Usage: /shutdown
    Only for owners
    """
    user_id = update.effective_user.id
    
    # Only owners
    if user_id not in OWNERS:
        await update.message.reply_text(
            "❌ <b>Access Denied!</b>\n\nOnly owners can shutdown.",
            parse_mode='HTML'
        )
        return
    
    try:
        await update.message.reply_text(
            "🛑 <b>Shutting down...</b>",
            parse_mode='HTML'
        )
        
        # Notify log channel
        try:
            await context.bot.send_message(
                chat_id=JOINLOGS,
                text=f"🛑 <b>Bot Shutdown</b>\n👤 By: <code>{user_id}</code>\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode='HTML'
            )
        except:
            pass
        
        LOGGER.info(f"🛑 Shutdown by User ID: {user_id}")
        
        # Stop application
        await context.application.stop()
        await context.application.shutdown()
        
        # Exit
        sys.exit(0)
        
    except Exception as e:
        LOGGER.error(f"Shutdown error: {e}")
        await update.message.reply_text(f"❌ <b>Error:</b> <code>{str(e)}</code>", parse_mode='HTML')


async def get_system_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Get system information
    Usage: /sysinfo
    """
    user_id = update.effective_user.id
    
    # Check permissions
    if user_id not in OWNERS and str(user_id) not in sudo_users:
        return
    
    try:
        import psutil
        
        # CPU and Memory
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Uptime
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.readline().split()[0])
                uptime_str = time.strftime('%H:%M:%S', time.gmtime(uptime_seconds))
        except:
            uptime_str = "N/A"
        
        info_text = (
            f"🖥 <b>System Information</b>\n\n"
            f"💻 <b>CPU:</b> <code>{cpu_percent}%</code>\n"
            f"🧠 <b>RAM:</b> <code>{memory.percent}%</code> (<code>{memory.used / (1024**3):.2f}GB</code> / <code>{memory.total / (1024**3):.2f}GB</code>)\n"
            f"💾 <b>Disk:</b> <code>{disk.percent}%</code> (<code>{disk.used / (1024**3):.2f}GB</code> / <code>{disk.total / (1024**3):.2f}GB</code>)\n"
            f"⏱ <b>Uptime:</b> <code>{uptime_str}</code>\n"
            f"🐍 <b>Python:</b> <code>{sys.version.split()[0]}</code>"
        )
        
        await update.message.reply_text(info_text, parse_mode='HTML')
        
    except ImportError:
        await update.message.reply_text(
            "⚠️ <b>psutil not installed</b>\n\nInstall with: <code>pip install psutil</code>",
            parse_mode='HTML'
        )
    except Exception as e:
        await update.message.reply_text(f"❌ <b>Error:</b> <code>{str(e)}</code>", parse_mode='HTML')


# Register handlers
application.add_handler(CommandHandler("restart", restart_bot, block=False))
application.add_handler(CommandHandler("srestart", restart_silent, block=False))
application.add_handler(CommandHandler("ping", ping_bot, block=False))
application.add_handler(CommandHandler("logs", get_bot_logs, block=False))
application.add_handler(CommandHandler("clearlogs", clear_logs, block=False))
application.add_handler(CommandHandler("shutdown", shutdown_bot, block=False))
application.add_handler(CommandHandler("sysinfo", get_system_info, block=False))