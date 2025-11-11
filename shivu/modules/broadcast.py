from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import (
    FloodWait, UserIsBlocked, ChatWriteForbidden, 
    PeerIdInvalid, ChannelPrivate, UserDeactivated
)
import asyncio
import logging
from typing import List, Set, Tuple
from datetime import datetime

from shivu import app, top_global_groups_collection, user_collection

# Configuration
OWNER_ID = 5147822244
BATCH_SIZE = 50  # Higher batch size for pyrogram
BATCH_DELAY = 0.5  # Shorter delay between batches
MAX_RETRIES = 1

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def send_to_chat(
    client: Client,
    chat_id: int,
    from_chat_id: int,
    message_id: int,
    retry: int = 0
) -> Tuple[bool, str]:
    """Send message to single chat with retry logic."""
    try:
        await client.forward_messages(
            chat_id=chat_id,
            from_chat_id=from_chat_id,
            message_ids=message_id
        )
        return (True, "success")
    
    except FloodWait as e:
        if retry < MAX_RETRIES:
            wait_time = min(e.value, 10)
            await asyncio.sleep(wait_time)
            try:
                await client.forward_messages(
                    chat_id=chat_id,
                    from_chat_id=from_chat_id,
                    message_ids=message_id
                )
                return (True, "success_retry")
            except Exception:
                return (False, "flood_wait")
        return (False, "flood_wait")
    
    except (UserIsBlocked, ChatWriteForbidden, PeerIdInvalid, 
            ChannelPrivate, UserDeactivated):
        return (False, "permanent")
    
    except Exception as e:
        logger.error(f"Error sending to {chat_id}: {e}")
        return (False, "error")

async def process_batch(
    client: Client,
    chat_ids: List[int],
    from_chat_id: int,
    message_id: int
) -> Tuple[int, int]:
    """Process batch concurrently."""
    tasks = [
        send_to_chat(client, chat_id, from_chat_id, message_id)
        for chat_id in chat_ids
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success = sum(1 for r in results if not isinstance(r, Exception) and r[0])
    failed = sum(1 for r in results if isinstance(r, Exception) or not r[0])
    
    return success, failed

@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast_handler(client: Client, message: Message):
    """Optimized broadcast using pyrogram."""
    
    # Validate reply
    if not message.reply_to_message:
        await message.reply_text("Reply to a message to broadcast.")
        return
    
    replied_msg = message.reply_to_message
    status = await message.reply_text("Fetching recipients...")
    
    start_time = datetime.now()
    
    try:
        # Fetch recipients concurrently
        chats_task = top_global_groups_collection.distinct("group_id")
        users_task = user_collection.distinct("id")
        
        all_chats, all_users = await asyncio.gather(chats_task, users_task)
        
        # Deduplicate
        recipients: Set[int] = set(all_chats + all_users)
        total = len(recipients)
        
        if total == 0:
            await status.edit_text("No recipients found.")
            return
        
        await status.edit_text(
            f"Broadcasting to {total} recipients...\n"
            f"Batch size: {BATCH_SIZE}"
        )
        
    except Exception as e:
        await status.edit_text(f"Error fetching recipients: {e}")
        return
    
    # Process batches
    recipients_list = list(recipients)
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    
    success = 0
    failed = 0
    
    for i in range(0, total, BATCH_SIZE):
        batch = recipients_list[i:i + BATCH_SIZE]
        current_batch = (i // BATCH_SIZE) + 1
        
        batch_success, batch_fail = await process_batch(
            client,
            batch,
            replied_msg.chat.id,
            replied_msg.id
        )
        
        success += batch_success
        failed += batch_fail
        
        # Update progress
        if current_batch % 10 == 0 or current_batch == total_batches:
            progress = (i + len(batch)) / total * 100
            try:
                await status.edit_text(
                    f"Broadcasting... {progress:.1f}%\n\n"
                    f"Sent: {success}\n"
                    f"Failed: {failed}\n"
                    f"Progress: {i + len(batch)}/{total}"
                )
            except Exception:
                pass
        
        # Delay between batches
        if current_batch < total_batches:
            await asyncio.sleep(BATCH_DELAY)
    
    # Calculate duration
    duration = (datetime.now() - start_time).total_seconds()
    rate = success / duration if duration > 0 else 0
    
    # Final report
    await status.edit_text(
        f"Broadcast Complete\n\n"
        f"Sent: {success}\n"
        f"Failed: {failed}\n"
        f"Total: {total}\n"
        f"Success rate: {(success/total*100):.1f}%\n"
        f"Duration: {duration:.1f}s\n"
        f"Speed: {rate:.1f} msg/s"
    )

logger.info("Broadcast module loaded with pyrogram")