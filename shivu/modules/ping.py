import time
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import application, sudo_users

# Store bot start time
bot_start_time = time.time()

async def ping(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) not in sudo_users:
        await update.message.reply_text("Nouu.. its Sudo user's Command..")
        return
    
    start_time = time.time()
    message = await update.message.reply_text('Pong!')
    end_time = time.time()
    elapsed_time = round((end_time - start_time) * 1000, 3)
    
    # Calculate uptime
    uptime_seconds = int(time.time() - bot_start_time)
    uptime = timedelta(seconds=uptime_seconds)
    
    # Format uptime
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    uptime_text = f"{days}d {hours}h {minutes}m {seconds}s"
    
    response = f'<blockquote> Pong! {elapsed_time}ms\n\n>**Bot Uptime:** {uptime_text} </blockquote>'
    await message.edit_text(response)

application.add_handler(CommandHandler("ping", ping))