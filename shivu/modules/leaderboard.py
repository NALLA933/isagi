import os
import asyncio
from datetime import datetime
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler

from shivu import (
    application, OWNER_ID, user_collection, 
    top_global_groups_collection, group_user_totals_collection
)
from shivu import sudo_users as SUDO_USERS

SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

def smallcaps(text: str) -> str:
    """Convert text to small caps for aesthetic appeal"""
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    small = "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return text.translate(str.maketrans(normal, small))

def get_badge(rank):
    """Get rank badge"""
    if rank == 1: return "★ 1ꜱᴛ ★"
    elif rank == 2: return "★ 2ɴᴅ ★"
    elif rank == 3: return "★ 3ʀᴅ ★"
    elif rank <= 10: return f"ᴛᴏᴘ {rank}"
    return f"#{rank}"

async def animate(msg, text):
    """Simple loading animation"""
    try:
        for i in range(10):
            frame = SPINNER[i % len(SPINNER)]
            await msg.edit_text(f"{frame} {smallcaps(text)}")
            await asyncio.sleep(0.2)
    except Exception as e:
        print(f"Animation error: {e}")

async def global_leaderboard(update: Update, context: CallbackContext) -> None:
    """Top 10 groups globally"""
    msg = await update.message.reply_text(smallcaps("loading..."))
    
    animation_task = asyncio.create_task(animate(msg, "fetching global rankings"))
    
    try:
        cursor = top_global_groups_collection.aggregate([
            {"$project": {"group_name": 1, "count": 1}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ])
        data = await cursor.to_list(length=10)
        
        animation_task.cancel()
        
        if not data:
            await msg.edit_text(smallcaps("no group data available."))
            return
        
        caption = f"""
<b>⸻ {smallcaps('top global groups')} ⸻</b>

"""
        
        for i, g in enumerate(data, 1):
            name = escape(g.get('group_name', 'Unknown'))
            if len(name) > 22:
                name = name[:19] + "..."
            count = g.get("count", 0)
            
            caption += f"<b>{get_badge(i)}</b>\n"
            caption += f"<blockquote>{smallcaps(name)}\n"
            caption += f"{smallcaps('characters')}: <b>{count:,}</b></blockquote>\n\n"
        
        caption += f"<b>⸻ {smallcaps('leaderboard system')} ⸻</b>"
        
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("ʀᴇғʀᴇꜱʜ", callback_data="refresh_topgroups"),
             InlineKeyboardButton("ᴠɪᴇᴡ ᴍᴏʀᴇ", callback_data="view_more_groups")],
            [InlineKeyboardButton("ᴄʟᴏꜱᴇ", callback_data="close_menu")]
        ])
        
        await msg.edit_text(caption.strip(), parse_mode='HTML', reply_markup=buttons)
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await msg.edit_text(smallcaps(f"error: {str(e)}"))
        print(f"Error in global_leaderboard: {e}")

async def ctop(update: Update, context: CallbackContext) -> None:
    """Top 10 users in chat"""
    msg = await update.message.reply_text(smallcaps("loading..."))
    
    animation_task = asyncio.create_task(animate(msg, "analyzing chat members"))
    
    try:
        chat_id = update.effective_chat.id
        chat_title = escape(update.effective_chat.title or "This Chat")
        
        cursor = group_user_totals_collection.aggregate([
            {"$match": {"group_id": chat_id}},
            {"$project": {"username": 1, "first_name": 1, "character_count": "$count"}},
            {"$sort": {"character_count": -1}},
            {"$limit": 10}
        ])
        data = await cursor.to_list(length=10)
        
        animation_task.cancel()
        
        if not data:
            await msg.edit_text(smallcaps("no data available for this chat."))
            return
        
        caption = f"""
<b>⸻ {smallcaps('top chat collectors')} ⸻</b>

<b>{smallcaps('chat')}</b>: {smallcaps(chat_title[:30])}

"""
        
        for i, u in enumerate(data, 1):
            user_id = u.get('_id')
            name = escape(u.get('first_name', 'Unknown'))
            if len(name) > 18:
                name = name[:15] + "..."
            count = u.get("character_count", 0)
            
            mention = f"<a href='tg://user?id={user_id}'>{smallcaps(name)}</a>"
            
            caption += f"<b>{get_badge(i)}</b>\n"
            caption += f"<blockquote>{mention}\n"
            caption += f"{smallcaps('count')}: <b>{count:,}</b></blockquote>\n\n"
        
        caption += f"<b>⸻ {smallcaps('chat rankings')} ⸻</b>"
        
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("ʀᴇғʀᴇꜱʜ", callback_data=f"refresh_ctop_{chat_id}"),
             InlineKeyboardButton("ꜱᴛᴀᴛꜱ", callback_data=f"chat_stats_{chat_id}")],
            [InlineKeyboardButton("ᴄʟᴏꜱᴇ", callback_data="close_menu")]
        ])
        
        await msg.edit_text(caption.strip(), parse_mode='HTML', reply_markup=buttons)
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await msg.edit_text(smallcaps(f"error: {str(e)}"))
        print(f"Error in ctop: {e}")

async def leaderboard(update: Update, context: CallbackContext) -> None:
    """Global top 10 users"""
    msg = await update.message.reply_text(smallcaps("loading..."))
    
    animation_task = asyncio.create_task(animate(msg, "fetching global champions"))
    
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
            await msg.edit_text(smallcaps("no collector data available."))
            return
        
        caption = f"""
<b>⸻ {smallcaps('global hall of fame')} ⸻</b>

"""
        
        for i, u in enumerate(data, 1):
            user_id = u.get('_id')
            name = escape(u.get('first_name', 'Unknown'))
            if len(name) > 18:
                name = name[:15] + "..."
            count = u.get("character_count", 0)
            
            mention = f"<a href='tg://user?id={user_id}'>{smallcaps(name)}</a>"
            
            caption += f"<b>{get_badge(i)}</b>\n"
            caption += f"<blockquote>{mention}\n"
            caption += f"{smallcaps('collection')}: <b>{count:,}</b></blockquote>\n\n"
        
        caption += f"<b>⸻ {smallcaps('global rankings')} ⸻</b>"
        
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("ʀᴇғʀᴇꜱʜ", callback_data="refresh_global"),
             InlineKeyboardButton("ᴛᴏᴘ 20", callback_data="top20_global")],
            [InlineKeyboardButton("ᴍʏ ʀᴀɴᴋ", callback_data="my_rank")],
            [InlineKeyboardButton("ᴄʟᴏꜱᴇ", callback_data="close_menu")]
        ])
        
        await msg.edit_text(caption.strip(), parse_mode='HTML', reply_markup=buttons)
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await msg.edit_text(smallcaps(f"error: {str(e)}"))
        print(f"Error in leaderboard: {e}")

async def my_rank(update: Update, context: CallbackContext) -> None:
    """Show user's rank"""
    msg = update.message if update.message else update.callback_query.message
    user_id = update.effective_user.id
    
    if update.callback_query:
        await update.callback_query.answer()
        loading_msg = await msg.reply_text(smallcaps("loading..."))
    else:
        loading_msg = await msg.reply_text(smallcaps("loading..."))
    
    animation_task = asyncio.create_task(animate(loading_msg, "calculating your rank"))
    
    try:
        user_data = await user_collection.find_one({'id': user_id})
        
        animation_task.cancel()
        
        if not user_data or 'characters' not in user_data:
            caption = f"""
<b>⸻ {smallcaps('profile not found')} ⸻</b>

<blockquote>{smallcaps('you have not collected any characters yet.')}</blockquote>

<b>{smallcaps('tip')}</b>: {smallcaps('start collecting to appear in rankings!')}
"""
            await loading_msg.edit_text(caption, parse_mode='HTML')
            return
        
        char_count = len(user_data.get('characters', []))
        
        higher = await user_collection.count_documents({
            "characters": {"$exists": True, "$type": "array"},
            "$expr": {"$gt": [{"$size": "$characters"}, char_count]}
        })
        
        rank = higher + 1
        total = await user_collection.count_documents({"characters": {"$exists": True, "$type": "array"}})
        
        name = escape(user_data.get('first_name', 'Unknown'))
        mention = f"<a href='tg://user?id={user_id}'>{smallcaps(name)}</a>"
        
        # Calculate percentile
        percentile = ((total - rank) / total) * 100 if total > 0 else 0
        
        caption = f"""
<b>⸻ {smallcaps('your profile')} ⸻</b>

<b>{smallcaps('collector')}</b>
<blockquote>{mention}</blockquote>

<b>{smallcaps('statistics')}</b>
<blockquote>
{smallcaps('global rank')}: <b>#{rank:,}</b> / {total:,}
{smallcaps('characters')}: <b>{char_count:,}</b>
{smallcaps('badge')}: <b>{get_badge(rank)}</b>
{smallcaps('percentile')}: <b>ᴛᴏᴘ {100-percentile:.1f}%</b>
</blockquote>

<b>⸻ {smallcaps('keep collecting!')} ⸻</b>
"""
        
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("ʀᴇғʀᴇꜱʜ", callback_data="my_rank"),
             InlineKeyboardButton("ᴠɪᴇᴡ ᴛᴏᴘ", callback_data="refresh_global")],
            [InlineKeyboardButton("ᴄʟᴏꜱᴇ", callback_data="close_menu")]
        ])
        
        if update.callback_query:
            await loading_msg.delete()
            await msg.edit_text(caption.strip(), parse_mode='HTML', reply_markup=buttons)
        else:
            await loading_msg.edit_text(caption.strip(), parse_mode='HTML', reply_markup=buttons)
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await loading_msg.edit_text(smallcaps(f"error: {str(e)}"))
        print(f"Error in my_rank: {e}")

async def chat_stats(update: Update, context: CallbackContext) -> None:
    """Chat statistics"""
    msg = await update.message.reply_text(smallcaps("loading..."))
    
    animation_task = asyncio.create_task(animate(msg, "computing statistics"))
    
    try:
        chat_id = update.effective_chat.id
        title = escape(update.effective_chat.title or "This Chat")
        
        user_count = await group_user_totals_collection.count_documents({"group_id": chat_id})
        
        animation_task.cancel()
        
        if user_count == 0:
            await msg.edit_text(smallcaps("no activity in this chat yet."))
            return
        
        result = await group_user_totals_collection.aggregate([
            {"$match": {"group_id": chat_id}},
            {"$group": {"_id": None, "total": {"$sum": "$count"}}}
        ]).to_list(length=1)
        total = result[0]['total'] if result else 0
        
        caption = f"""
<b>⸻ {smallcaps('chat statistics')} ⸻</b>

<b>{smallcaps('chat name')}</b>
<blockquote>{smallcaps(title[:40])}</blockquote>

<b>{smallcaps('data')}</b>
<blockquote>
{smallcaps('active users')}: <b>{user_count:,}</b>
{smallcaps('total characters')}: <b>{total:,}</b>
{smallcaps('average per user')}: <b>{total/user_count:.1f}</b>
</blockquote>

<b>⸻ {smallcaps('chat analytics')} ⸻</b>
"""
        
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("ʀᴇғʀᴇꜱʜ", callback_data=f"chat_stats_{chat_id}"),
             InlineKeyboardButton("ᴛᴏᴘ ᴜꜱᴇʀꜱ", callback_data=f"refresh_ctop_{chat_id}")],
            [InlineKeyboardButton("ᴄʟᴏꜱᴇ", callback_data="close_menu")]
        ])
        
        await msg.edit_text(caption.strip(), parse_mode='HTML', reply_markup=buttons)
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await msg.edit_text(smallcaps(f"error: {str(e)}"))
        print(f"Error in chat_stats: {e}")

async def stats(update: Update, context: CallbackContext) -> None:
    """Bot statistics (Owner only)"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text(smallcaps("you are not authorized to view system statistics."))
        return
    
    msg = await update.message.reply_text(smallcaps("loading..."))
    
    animation_task = asyncio.create_task(animate(msg, "computing system stats"))
    
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
        
        caption = f"""
<b>⸻ {smallcaps('system statistics')} ⸻</b>

<b>{smallcaps('database overview')}</b>
<blockquote>
{smallcaps('total users')}: <b>{users:,}</b>
{smallcaps('active collectors')}: <b>{collectors:,}</b>
{smallcaps('total groups')}: <b>{groups:,}</b>
{smallcaps('total characters')}: <b>{total_chars:,}</b>
</blockquote>

<b>{smallcaps('analytics')}</b>
<blockquote>
{smallcaps('avg per collector')}: <b>{total_chars/collectors:.1f}</b>
</blockquote>

<b>⸻ {smallcaps('bot system')} ⸻</b>
"""
        
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("ʀᴇғʀᴇꜱʜ", callback_data="refresh_stats")],
            [InlineKeyboardButton("ᴄʟᴏꜱᴇ", callback_data="close_menu")]
        ])
        
        await msg.edit_text(caption.strip(), parse_mode='HTML', reply_markup=buttons)
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await msg.edit_text(smallcaps(f"error: {str(e)}"))
        print(f"Error in stats: {e}")

async def send_users_document(update: Update, context: CallbackContext) -> None:
    """Export users (Sudo only)"""
    if str(update.effective_user.id) not in SUDO_USERS:
        await update.message.reply_text(smallcaps('you are not authorized to export users.'))
        return
    
    msg = await update.message.reply_text(smallcaps('preparing export...'))
    
    animation_task = asyncio.create_task(animate(msg, "generating user database"))
    
    try:
        users = await user_collection.find({}).to_list(length=None)
        
        animation_task.cancel()
        
        content = f"⸻ USER DATABASE EXPORT ⸻\n\n"
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
        
        await msg.edit_text(smallcaps("export complete! sending file..."))
        
        caption = f"""
<b>⸻ {smallcaps('user database export')} ⸻</b>

<blockquote>
{smallcaps('total users')}: <b>{len(users):,}</b>
{smallcaps('generated')}: <b>{datetime.now().strftime('%H:%M:%S')}</b>
</blockquote>
"""
        
        with open('users.txt', 'rb') as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id, 
                document=f, 
                caption=caption.strip(),
                parse_mode='HTML'
            )
        
        os.remove('users.txt')
        await msg.delete()
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await msg.edit_text(smallcaps(f"error: {str(e)}"))
        print(f"Error in send_users_document: {e}")

async def send_groups_document(update: Update, context: CallbackContext) -> None:
    """Export groups (Sudo only)"""
    if str(update.effective_user.id) not in SUDO_USERS:
        await update.message.reply_text(smallcaps('you are not authorized to export groups.'))
        return
    
    msg = await update.message.reply_text(smallcaps('preparing export...'))
    
    animation_task = asyncio.create_task(animate(msg, "generating group database"))
    
    try:
        groups = await top_global_groups_collection.find({}).to_list(length=None)
        groups.sort(key=lambda x: x.get('count', 0), reverse=True)
        
        animation_task.cancel()
        
        content = f"⸻ GROUP DATABASE EXPORT ⸻\n\n"
        content += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        content += f"Total Groups: {len(groups):,}\n"
        content += f"{'='*50}\n\n"
        
        for i, g in enumerate(groups, 1):
            group_name = g.get('group_name', 'Unknown')
            count = g.get('count', 0)
            content += f"[{i}] {group_name} | {count:,} characters\n"
        
        with open('groups.txt', 'w', encoding='utf-8') as f:
            f.write(content)
        
        await msg.edit_text(smallcaps("export complete! sending file..."))
        
        caption = f"""
<b>⸻ {smallcaps('group database export')} ⸻</b>

<blockquote>
{smallcaps('total groups')}: <b>{len(groups):,}</b>
{smallcaps('generated')}: <b>{datetime.now().strftime('%H:%M:%S')}</b>
</blockquote>
"""
        
        with open('groups.txt', 'rb') as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id, 
                document=f, 
                caption=caption.strip(),
                parse_mode='HTML'
            )
        
        os.remove('groups.txt')
        await msg.delete()
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await msg.edit_text(smallcaps(f"error: {str(e)}"))
        print(f"Error in send_groups_document: {e}")

async def button_callback(update: Update, context: CallbackContext) -> None:
    """Handle button clicks"""
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data == "refresh_global":
            await query.message.delete()
            update.message = query.message
            await leaderboard(update, context)
        
        elif query.data == "my_rank":
            await my_rank(update, context)
        
        elif query.data == "refresh_topgroups":
            await query.message.delete()
            update.message = query.message
            await global_leaderboard(update, context)
        
        elif query.data.startswith("refresh_ctop_"):
            chat_id = int(query.data.split("_")[2])
            await query.message.delete()
            update.message = query.message
            await ctop(update, context)
        
        elif query.data.startswith("chat_stats_"):
            chat_id = int(query.data.split("_")[2])
            await query.message.delete()
            update.message = query.message
            await chat_stats(update, context)
        
        elif query.data == "refresh_stats":
            await query.message.delete()
            update.message = query.message
            await stats(update, context)
        
        elif query.data == "close_menu":
            await query.message.delete()
    
    except Exception as e:
        await query.message.reply_text(smallcaps(f"error: {str(e)}"))
        print(f"Error in button_callback: {e}")

# Register handlers
application.add_handler(CommandHandler('topgroups', global_leaderboard, block=False))
application.add_handler(CommandHandler('topchat', ctop, block=False))
application.add_handler(CommandHandler(['gstop', 'top'], leaderboard, block=False))
application.add_handler(CommandHandler(['myrank', 'rank'], my_rank, block=False))
application.add_handler(CommandHandler('chatstats', chat_stats, block=False))
application.add_handler(CommandHandler('stats', stats, block=False))
application.add_handler(CommandHandler('list', send_users_document, block=False))
application.add_handler(CommandHandler('groups', send_groups_document, block=False))
application.add_handler(CallbackQueryHandler(button_callback))