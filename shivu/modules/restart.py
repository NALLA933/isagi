"""
Restart Command for Heroku Docker Bot
Handles bot restart with proper logging and notification system
"""

import os
import sys
import time
import subprocess
from datetime import datetime
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from shivu import application, sudo_users, LOGGER, JOINLOGS

# Owner IDs who can restart the bot
OWNERS = [8420981179, 5147822244]


async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Restart the bot (Heroku/Docker compatible)
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
        # Get restart info
        restart_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        chat_id = update.effective_chat.id
        message_id = update.message.message_id
        
        # Send restart notification
        restart_msg = await update.message.reply_text(
            "🔄 <b>Restarting Bot...</b>\n\n"
            f"⏰ <b>Time:</b> <code>{restart_time}</code>\n"
            f"👤 <b>By:</b> {update.effective_user.mention_html()}\n\n"
            "⏳ Please wait, this may take a few seconds.",
            parse_mode='HTML'
        )
        
        LOGGER.info(f"🔄 Bot restart initiated by {update.effective_user.first_name} (ID: {user_id})")
        
        # Notify log channel
        try:
            await context.bot.send_message(
                chat_id=JOINLOGS,
                text=(
                    "🔄 <b>Bot Restarting...</b>\n\n"
                    f"⏰ <b>Time:</b> <code>{restart_time}</code>\n"
                    f"👤 <b>Initiated By:</b> {update.effective_user.mention_html()}\n"
                    f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
                    f"💬 <b>Chat:</b> {update.effective_chat.title or 'Private'}\n\n"
                    "⚡ Restart in progress..."
                ),
                parse_mode='HTML'
            )
        except Exception as e:
            LOGGER.error(f"Failed to send restart notification to log channel: {e}")
        
        # Store restart info for post-restart message
        restart_data = f"{chat_id}|{restart_msg.message_id}|{user_id}"
        
        # Write restart data to file
        with open('/tmp/restart_info.txt', 'w') as f:
            f.write(restart_data)
        
        LOGGER.info("⚡ Executing restart...")
        
        # Small delay to ensure messages are sent
        await context.application.stop()
        
        # Restart using os.execv (works in Docker/Heroku)
        os.execv(sys.executable, ['python3', '-m', 'shivu'])
        
    except Exception as e:
        LOGGER.error(f"❌ Error during restart: {e}")
        try:
            await update.message.reply_text(
                f"❌ <b>Restart Failed!</b>\n\n"
                f"<b>Error:</b> <code>{str(e)}</code>\n\n"
                f"Please check the logs or contact the developer.",
                parse_mode='HTML'
            )
        except:
            pass


async def restart_silent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Silent restart without confirmation messages
    Usage: /srestart
    Useful for maintenance restarts
    """
    user_id = update.effective_user.id
    
    # Check permissions
    if user_id not in OWNERS and str(user_id) not in sudo_users:
        return
    
    try:
        LOGGER.info(f"🔇 Silent restart initiated by {update.effective_user.first_name} (ID: {user_id})")
        
        # Notify log channel only
        try:
            await context.bot.send_message(
                chat_id=JOINLOGS,
                text=(
                    "🔇 <b>Silent Restart Initiated</b>\n\n"
                    f"👤 <b>By:</b> {update.effective_user.mention_html()}\n"
                    f"⏰ <b>Time:</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>"
                ),
                parse_mode='HTML'
            )
        except:
            pass
        
        # Stop and restart
        await context.application.stop()
        os.execv(sys.executable, ['python3', '-m', 'shivu'])
        
    except Exception as e:
        LOGGER.error(f"❌ Error during silent restart: {e}")


async def ping_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Check if bot is alive and responsive
    Usage: /ping
    """
    start_time = time.time()
    
    message = await update.message.reply_text("🏓 Pinging...")
    
    end_time = time.time()
    ping_time = round((end_time - start_time) * 1000, 2)
    
    # Get uptime if possible
    try:
        uptime = time.time() - os.path.getctime('/proc/self')
        uptime_str = time.strftime('%H:%M:%S', time.gmtime(uptime))
    except:
        uptime_str = "N/A"
    
    await message.edit_text(
        f"🏓 <b>Pong!</b>\n\n"
        f"⚡ <b>Response Time:</b> <code>{ping_time}ms</code>\n"
        f"⏱ <b>Uptime:</b> <code>{uptime_str}</code>\n"
        f"✅ <b>Status:</b> Online",
        parse_mode='HTML'
    )


async def get_bot_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Get recent bot logs
    Usage: /logs [lines]
    Default: 50 lines
    Only for owners
    """
    user_id = update.effective_user.id
    
    # Check permissions
    if user_id not in OWNERS and str(user_id) not in sudo_users:
        await update.message.reply_text("❌ You don't have permission to view logs.")
        return
    
    # Get number of lines to fetch
    num_lines = 50
    if context.args:
        try:
            num_lines = int(context.args[0])
            num_lines = max(10, min(num_lines, 500))  # Between 10 and 500
        except:
            pass
    
    try:
        # Try to read log file
        log_file = 'log.txt'
        
        if not os.path.exists(log_file):
            await update.message.reply_text(
                "⚠️ <b>Log file not found!</b>\n\n"
                "The bot might not have created any logs yet.",
                parse_mode='HTML'
            )
            return
        
        # Read last N lines
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            log_content = ''.join(lines[-num_lines:])
        
        if not log_content.strip():
            await update.message.reply_text(
                "⚠️ <b>Log file is empty!</b>",
                parse_mode='HTML'
            )
            return
        
        # Send as file if too long
        if len(log_content) > 4000:
            log_filename = f'/tmp/bot_logs_{int(time.time())}.txt'
            with open(log_filename, 'w', encoding='utf-8') as f:
                f.write(log_content)
            
            await update.message.reply_document(
                document=open(log_filename, 'rb'),
                filename=f'bot_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt',
                caption=f"📋 <b>Last {num_lines} lines of logs</b>",
                parse_mode='HTML'
            )
            
            # Cleanup
            try:
                os.remove(log_filename)
            except:
                pass
        else:
            # Send as text message
            await update.message.reply_text(
                f"📋 <b>Last {num_lines} lines of logs:</b>\n\n"
                f"<pre>{log_content}</pre>",
                parse_mode='HTML'
            )
    
    except Exception as e:
        LOGGER.error(f"Error reading logs: {e}")
        await update.message.reply_text(
            f"❌ <b>Error reading logs:</b>\n\n"
            f"<code>{str(e)}</code>",
            parse_mode='HTML'
        )


async def clear_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Clear bot logs
    Usage: /clearlogs
    Only for owners
    """
    user_id = update.effective_user.id
    
    # Check permissions (only owners, not sudo users)
    if user_id not in OWNERS:
        await update.message.reply_text(
            "❌ <b>Access Denied!</b>\n\n"
            "Only bot owners can clear logs.",
            parse_mode='HTML'
        )
        return
    
    try:
        log_file = 'log.txt'
        
        if os.path.exists(log_file):
            # Get file size before clearing
            file_size = os.path.getsize(log_file) / 1024  # KB
            
            # Clear the log file
            with open(log_file, 'w') as f:
                f.write(f"# Logs cleared by {update.effective_user.first_name} at {datetime.now()}\n")
            
            await update.message.reply_text(
                f"✅ <b>Logs Cleared!</b>\n\n"
                f"📊 <b>Previous Size:</b> <code>{file_size:.2f} KB</code>\n"
                f"👤 <b>Cleared By:</b> {update.effective_user.mention_html()}",
                parse_mode='HTML'
            )
            
            # Notify log channel
            try:
                await context.bot.send_message(
                    chat_id=JOINLOGS,
                    text=(
                        "🗑 <b>Bot Logs Cleared</b>\n\n"
                        f"👤 <b>By:</b> {update.effective_user.mention_html()}\n"
                        f"📊 <b>Size:</b> <code>{file_size:.2f} KB</code>\n"
                        f"⏰ <b>Time:</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>"
                    ),
                    parse_mode='HTML'
                )
            except:
                pass
        else:
            await update.message.reply_text(
                "⚠️ <b>No log file found!</b>",
                parse_mode='HTML'
            )
    
    except Exception as e:
        await update.message.reply_text(
            f"❌ <b>Error clearing logs:</b>\n\n"
            f"<code>{str(e)}</code>",
            parse_mode='HTML'
        )


async def shutdown_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Gracefully shutdown the bot
    Usage: /shutdown
    Only for owners (use with caution!)
    """
    user_id = update.effective_user.id
    
    # Check permissions (only owners, not sudo users)
    if user_id not in OWNERS:
        await update.message.reply_text(
            "❌ <b>Access Denied!</b>\n\n"
            "Only bot owners can shutdown the bot.",
            parse_mode='HTML'
        )
        return
    
    try:
        await update.message.reply_text(
            "🛑 <b>Shutting down bot...</b>\n\n"
            "⚠️ The bot will stop responding until manually restarted.",
            parse_mode='HTML'
        )
        
        # Notify log channel
        try:
            await context.bot.send_message(
                chat_id=JOINLOGS,
                text=(
                    "🛑 <b>Bot Shutdown</b>\n\n"
                    f"👤 <b>By:</b> {update.effective_user.mention_html()}\n"
                    f"⏰ <b>Time:</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
                    "⚠️ Bot is now offline."
                ),
                parse_mode='HTML'
            )
        except:
            pass
        
        LOGGER.info(f"🛑 Bot shutdown initiated by {update.effective_user.first_name} (ID: {user_id})")
        
        # Stop the application
        await context.application.stop()
        await context.application.shutdown()
        
        # Exit the process
        sys.exit(0)
        
    except Exception as e:
        LOGGER.error(f"Error during shutdown: {e}")
        await update.message.reply_text(
            f"❌ <b>Shutdown Failed!</b>\n\n"
            f"<code>{str(e)}</code>",
            parse_mode='HTML'
        )


# Register handlers
application.add_handler(CommandHandler("restart", restart_bot, block=False))
application.add_handler(CommandHandler("srestart", restart_silent, block=False))
application.add_handler(CommandHandler("ping", ping_bot, block=False))
application.add_handler(CommandHandler("logs", get_bot_logs, block=False))
application.add_handler(CommandHandler("clearlogs", clear_logs, block=False))
application.add_handler(CommandHandler("shutdown", shutdown_bot, block=False))