"""
Restart Command for Heroku Docker Bot
Handles bot restart using os.execv() for containerized environment
"""

import os
import sys
import time
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from shivu import application, sudo_users, LOGGER

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
        # Send restart message
        restart_msg = await update.message.reply_text(
            "🔄 <b>Restarting Bot...</b>\n\n"
            "⏳ Please wait, this may take a few seconds.",
            parse_mode='HTML'
        )
        
        LOGGER.info(f"Bot restart initiated by {update.effective_user.first_name} (ID: {user_id})")
        
        # Small delay to ensure message is sent
        await context.application.bot.send_message(
            chat_id=update.effective_chat.id,
            text="✅ <b>Bot is restarting...</b>\n\n"
                 "🔄 The bot will be back online shortly!",
            parse_mode='HTML'
        )
        
        # Give time for message to send
        time.sleep(1)
        
        # Restart the bot process
        # This works in Docker/Heroku by replacing the current process
        LOGGER.info("Executing restart...")
        os.execv(sys.executable, ['python3'] + sys.argv)
        
    except Exception as e:
        LOGGER.error(f"Error during restart: {e}")
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
        LOGGER.info(f"Silent restart initiated by {update.effective_user.first_name} (ID: {user_id})")
        
        # Immediate restart without waiting
        os.execv(sys.executable, ['python3'] + sys.argv)
        
    except Exception as e:
        LOGGER.error(f"Error during silent restart: {e}")


async def ping_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Check if bot is alive and responsive
    Usage: /ping
    """
    start_time = time.time()
    
    message = await update.message.reply_text("🏓 Pinging...")
    
    end_time = time.time()
    ping_time = round((end_time - start_time) * 1000, 2)
    
    await message.edit_text(
        f"🏓 <b>Pong!</b>\n\n"
        f"⚡ <b>Response Time:</b> <code>{ping_time}ms</code>\n"
        f"✅ <b>Status:</b> Online",
        parse_mode='HTML'
    )


async def get_bot_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Get recent bot logs (last 50 lines)
    Usage: /logs
    Only for owners
    """
    user_id = update.effective_user.id
    
    # Check permissions
    if user_id not in OWNERS and str(user_id) not in sudo_users:
        await update.message.reply_text("❌ You don't have permission to view logs.")
        return
    
    try:
        # Try to read logs from common locations
        log_files = [
            'bot.log',
            'shivu.log',
            '/tmp/bot.log',
            '/var/log/bot.log'
        ]
        
        log_content = None
        for log_file in log_files:
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    log_content = ''.join(lines[-50:])  # Last 50 lines
                break
        
        if log_content:
            # Send as file if too long
            if len(log_content) > 4000:
                with open('/tmp/recent_logs.txt', 'w') as f:
                    f.write(log_content)
                await update.message.reply_document(
                    document=open('/tmp/recent_logs.txt', 'rb'),
                    filename='bot_logs.txt',
                    caption="📋 <b>Recent Bot Logs</b>",
                    parse_mode='HTML'
                )
                os.remove('/tmp/recent_logs.txt')
            else:
                await update.message.reply_text(
                    f"📋 <b>Recent Logs (Last 50 lines):</b>\n\n"
                    f"<pre>{log_content}</pre>",
                    parse_mode='HTML'
                )
        else:
            await update.message.reply_text(
                "⚠️ No log file found.\n\n"
                "The bot might not be configured to write logs to a file."
            )
    
    except Exception as e:
        await update.message.reply_text(
            f"❌ <b>Error reading logs:</b>\n\n"
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
        
        LOGGER.info(f"Bot shutdown initiated by {update.effective_user.first_name} (ID: {user_id})")
        
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
application.add_handler(CommandHandler("shutdown", shutdown_bot, block=False))