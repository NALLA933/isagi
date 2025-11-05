import os
import asyncio
from datetime import datetime
from html import escape
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import (
    application, OWNER_ID, user_collection, 
    top_global_groups_collection, group_user_totals_collection
)
from shivu import sudo_users as SUDO_USERS

SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

def get_badge(rank):
    """Get rank badge"""
    if rank == 1: return "[★ 1ST ★]"
    elif rank == 2: return "[★ 2ND ★]"
    elif rank == 3: return "[★ 3RD ★]"
    elif rank <= 10: return f"[TOP {rank}]"
    return f"[#{rank}]"

async def animate(msg, text):
    """Simple loading animation"""
    try:
        for i in range(10):
            frame = SPINNER[i % len(SPINNER)]
            await msg.edit_text(f"{frame} {text}")
            await asyncio.sleep(0.2)
    except Exception as e:
        print(f"Animation error: {e}")

async def global_leaderboard(update: Update, context: CallbackContext) -> None:
    """Top 10 groups globally"""
    msg = await update.message.reply_text("⏳ Loading...")
    
    # Start animation in background
    animation_task = asyncio.create_task(animate(msg, "Fetching global groups"))
    
    try:
        cursor = top_global_groups_collection.aggregate([
            {"$project": {"group_name": 1, "count": 1}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ])
        data = await cursor.to_list(length=10)
        
        # Cancel animation
        animation_task.cancel()
        
        if not data:
            await msg.edit_text("║ No group data available ║")
            return
        
        text = "╔══════════════════════════╗\n"
        text += "║   TOP GLOBAL GROUPS      ║\n"
        text += "╚══════════════════════════╝\n\n"
        
        for i, g in enumerate(data, 1):
            name = escape(g.get('group_name', 'Unknown'))
            if len(name) > 25:
                name = name[:22] + "..."
            count = g.get("count", 0)
            text += f'<b>{get_badge(i)}</b> {name}\n'
            text += f'│ Characters: <b>{count:,}</b>\n'
            text += f'└─────────────────────\n\n'
        
        text += "═══════════════════════════\n"
        text += "     Powered by @waifukunbot"
        
        await msg.edit_text(text, parse_mode='HTML')
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")
        print(f"Error in global_leaderboard: {e}")

async def ctop(update: Update, context: CallbackContext) -> None:
    """Top 10 users in chat"""
    msg = await update.message.reply_text("⏳ Loading...")
    
    animation_task = asyncio.create_task(animate(msg, "Analyzing chat members"))
    
    try:
        chat_id = update.effective_chat.id
        
        cursor = group_user_totals_collection.aggregate([
            {"$match": {"group_id": chat_id}},
            {"$project": {"username": 1, "first_name": 1, "character_count": "$count"}},
            {"$sort": {"character_count": -1}},
            {"$limit": 10}
        ])
        data = await cursor.to_list(length=10)
        
        animation_task.cancel()
        
        if not data:
            await msg.edit_text("║ No data available for this chat ║")
            return
        
        text = "╔══════════════════════════╗\n"
        text += "║  TOP CHAT COLLECTORS     ║\n"
        text += "╚══════════════════════════╝\n\n"
        
        for i, u in enumerate(data, 1):
            name = escape(u.get('first_name', 'Unknown'))
            if len(name) > 20:
                name = name[:17] + "..."
            username = u.get('username', 'user')
            count = u.get("character_count", 0)
            
            text += f'<b>{get_badge(i)}</b> <a href="https://t.me/{username}">{name}</a>\n'
            text += f'│ Count: <b>{count:,}</b>\n'
            text += f'└─────────────────────\n\n'
        
        await msg.edit_text(text, parse_mode='HTML', disable_web_page_preview=True)
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")
        print(f"Error in ctop: {e}")

async def leaderboard(update: Update, context: CallbackContext) -> None:
    """Global top 10 users"""
    msg = await update.message.reply_text("⏳ Loading...")
    
    animation_task = asyncio.create_task(animate(msg, "Fetching global rankings"))
    
    try:
        cursor = user_collection.aggregate([
            {"$match": {"characters": {"$exists": True, "$type": "array"}}},
            {"$project": {"username": 1, "first_name": 1, "character_count": {"$size": "$characters"}}},
            {"$sort": {"character_count": -1}},
            {"$limit": 10}
        ])
        data = await cursor.to_list(length=10)
        
        animation_task.cancel()
        
        if not data:
            await msg.edit_text("║ No collector data available ║")
            return
        
        text = "╔══════════════════════════╗\n"
        text += "║   GLOBAL CHAMPIONS       ║\n"
        text += "╚══════════════════════════╝\n\n"
        
        for i, u in enumerate(data, 1):
            name = escape(u.get('first_name', 'Unknown'))
            if len(name) > 20:
                name = name[:17] + "..."
            username = u.get('username', 'user')
            count = u.get("character_count", 0)
            
            text += f'<b>{get_badge(i)}</b> <a href="https://t.me/{username}">{name}</a>\n'
            text += f'│ Collection: <b>{count:,}</b>\n'
            text += f'└─────────────────────\n\n'
        
        await msg.edit_text(text, parse_mode='HTML', disable_web_page_preview=True)
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")
        print(f"Error in leaderboard: {e}")

async def my_rank(update: Update, context: CallbackContext) -> None:
    """Show user's rank"""
    msg = await update.message.reply_text("⏳ Loading...")
    
    animation_task = asyncio.create_task(animate(msg, "Calculating your rank"))
    
    try:
        user_id = update.effective_user.id
        user_data = await user_collection.find_one({'id': user_id})
        
        animation_task.cancel()
        
        if not user_data or 'characters' not in user_data:
            await msg.edit_text("║ No profile found ║\n\n<i>Start collecting characters!</i>", parse_mode='HTML')
            return
        
        char_count = len(user_data.get('characters', []))
        
        higher = await user_collection.count_documents({
            "characters": {"$exists": True, "$type": "array"},
            "$expr": {"$gt": [{"$size": "$characters"}, char_count]}
        })
        
        rank = higher + 1
        total = await user_collection.count_documents({"characters": {"$exists": True, "$type": "array"}})
        
        name = escape(user_data.get('first_name', 'Unknown'))
        
        text = "╔══════════════════════════╗\n"
        text += "║   YOUR PROFILE           ║\n"
        text += "╚══════════════════════════╝\n\n"
        text += f"👤 <b>Name:</b> {name}\n"
        text += f"🏆 <b>Rank:</b> #{rank:,} / {total:,}\n"
        text += f"🎴 <b>Characters:</b> {char_count:,}\n"
        text += f"⭐ <b>Badge:</b> {get_badge(rank)}"
        
        await msg.edit_text(text, parse_mode='HTML')
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")
        print(f"Error in my_rank: {e}")

async def chat_stats(update: Update, context: CallbackContext) -> None:
    """Chat statistics"""
    msg = await update.message.reply_text("⏳ Loading...")
    
    animation_task = asyncio.create_task(animate(msg, "Computing statistics"))
    
    try:
        chat_id = update.effective_chat.id
        title = escape(update.effective_chat.title or "This Chat")
        
        user_count = await group_user_totals_collection.count_documents({"group_id": chat_id})
        
        animation_task.cancel()
        
        if user_count == 0:
            await msg.edit_text("║ No activity in this chat yet ║")
            return
        
        result = await group_user_totals_collection.aggregate([
            {"$match": {"group_id": chat_id}},
            {"$group": {"_id": None, "total": {"$sum": "$count"}}}
        ]).to_list(length=1)
        total = result[0]['total'] if result else 0
        
        text = "╔══════════════════════════╗\n"
        text += "║   CHAT STATISTICS        ║\n"
        text += "╚══════════════════════════╝\n\n"
        text += f"💬 <b>Chat:</b> {title}\n"
        text += f"👥 <b>Active Users:</b> {user_count:,}\n"
        text += f"🎴 <b>Total Characters:</b> {total:,}\n"
        text += f"📊 <b>Average per User:</b> {total/user_count:.1f}"
        
        await msg.edit_text(text, parse_mode='HTML')
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")
        print(f"Error in chat_stats: {e}")

async def stats(update: Update, context: CallbackContext) -> None:
    """Bot statistics (Owner only)"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Unauthorized - Owner only")
        return
    
    msg = await update.message.reply_text("⏳ Loading...")
    
    animation_task = asyncio.create_task(animate(msg, "Computing system stats"))
    
    try:
        users = await user_collection.count_documents({})
        groups = len(await group_user_totals_collection.distinct('group_id'))
        collectors = await user_collection.count_documents({"characters": {"$exists": True, "$type": "array"}})
        
        result = await user_collection.aggregate([
            {"$match": {"characters": {"$exists": True, "$type": "array"}}},
            {"$project": {"char_count": {"$size": "$characters"}}},
            {"$group": {"_id": None, "total": {"$sum": "$char_count"}}}
        ]).to_list(length=1)
        total_chars = result[0]['total'] if result else 0
        
        animation_task.cancel()
        
        text = "╔══════════════════════════╗\n"
        text += "║  SYSTEM STATISTICS       ║\n"
        text += "╚══════════════════════════╝\n\n"
        text += f"👥 <b>Total Users:</b> {users:,}\n"
        text += f"⭐ <b>Active Collectors:</b> {collectors:,}\n"
        text += f"💬 <b>Total Groups:</b> {groups:,}\n"
        text += f"🎴 <b>Total Characters:</b> {total_chars:,}\n\n"
        
        if collectors > 0:
            avg = total_chars / collectors
            text += f"📊 <b>Avg per Collector:</b> {avg:.1f}"
        
        await msg.edit_text(text, parse_mode='HTML')
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")
        print(f"Error in stats: {e}")

async def send_users_document(update: Update, context: CallbackContext) -> None:
    """Export users (Sudo only)"""
    if str(update.effective_user.id) not in SUDO_USERS:
        await update.message.reply_text('❌ Unauthorized - Sudo only')
        return
    
    msg = await update.message.reply_text('📄 Exporting users...')
    
    animation_task = asyncio.create_task(animate(msg, "Generating user database"))
    
    try:
        users = await user_collection.find({}).to_list(length=None)
        
        animation_task.cancel()
        
        content = f"═══════════════════════════════════\n"
        content += f"    USER DATABASE EXPORT\n"
        content += f"═══════════════════════════════════\n\n"
        content += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        content += f"Total Users: {len(users):,}\n"
        content += f"{'='*50}\n\n"
        
        for u in users:
            user_id = u.get('id', 'N/A')
            first_name = u.get('first_name', 'Unknown')
            username = u.get('username', 'N/A')
            char_count = len(u.get('characters', []))
            content += f"[{user_id}] {first_name} | @{username} | {char_count} characters\n"
        
        with open('users.txt', 'w', encoding='utf-8') as f:
            f.write(content)
        
        await msg.edit_text("✅ Export complete! Sending file...")
        
        with open('users.txt', 'rb') as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id, 
                document=f, 
                caption=f"📊 <b>User Database Export</b>\n\nTotal Users: <b>{len(users):,}</b>",
                parse_mode='HTML'
            )
        
        os.remove('users.txt')
        await msg.delete()
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")
        print(f"Error in send_users_document: {e}")

async def send_groups_document(update: Update, context: CallbackContext) -> None:
    """Export groups (Sudo only)"""
    if str(update.effective_user.id) not in SUDO_USERS:
        await update.message.reply_text('❌ Unauthorized - Sudo only')
        return
    
    msg = await update.message.reply_text('📄 Exporting groups...')
    
    animation_task = asyncio.create_task(animate(msg, "Generating group database"))
    
    try:
        groups = await top_global_groups_collection.find({}).to_list(length=None)
        groups.sort(key=lambda x: x.get('count', 0), reverse=True)
        
        animation_task.cancel()
        
        content = f"═══════════════════════════════════\n"
        content += f"    GROUP DATABASE EXPORT\n"
        content += f"═══════════════════════════════════\n\n"
        content += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        content += f"Total Groups: {len(groups):,}\n"
        content += f"{'='*50}\n\n"
        
        for i, g in enumerate(groups, 1):
            group_name = g.get('group_name', 'Unknown')
            count = g.get('count', 0)
            content += f"[{i}] {group_name} | {count:,} characters\n"
        
        with open('groups.txt', 'w', encoding='utf-8') as f:
            f.write(content)
        
        await msg.edit_text("✅ Export complete! Sending file...")
        
        with open('groups.txt', 'rb') as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id, 
                document=f, 
                caption=f"📊 <b>Group Database Export</b>\n\nTotal Groups: <b>{len(groups):,}</b>",
                parse_mode='HTML'
            )
        
        os.remove('groups.txt')
        await msg.delete()
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")
        print(f"Error in send_groups_document: {e}")

# Register handlers
application.add_handler(CommandHandler('topgroups', global_leaderboard, block=False))
application.add_handler(CommandHandler('topchat', ctop, block=False))
application.add_handler(CommandHandler(['gstop', 'top'], leaderboard, block=False))
application.add_handler(CommandHandler(['myrank', 'rank'], my_rank, block=False))
application.add_handler(CommandHandler('chatstats', chat_stats, block=False))
application.add_handler(CommandHandler('stats', stats, block=False))
application.add_handler(CommandHandler('list', send_users_document, block=False))
application.add_handler(CommandHandler('groups', send_groups_document, block=False))