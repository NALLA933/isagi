import random
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    Message
)
from shivu import user_collection, shivuu as app, LEAVELOGS, JOINLOGS


async def lul_message(chat_id: int, message: str):
    await app.send_message(chat_id=chat_id, text=message)


@app.on_message(filters.new_chat_members)
async def on_new_chat_members(client: Client, message: Message):
    me = await client.get_me()
    if me.id in [user.id for user in message.new_chat_members]:
        added_by = message.from_user.mention if message.from_user else "ᴜɴᴋɴᴏᴡɴ ᴜsᴇʀ"
        chat_title = message.chat.title
        chat_id = message.chat.id
        chatusername = f"@{message.chat.username}" if message.chat.username else "ᴩʀɪᴠᴀᴛᴇ ᴄʜᴀᴛ"

        text = (
            f"˹𝐆ʀᴀʙʙɪɴɢ 𝐘ᴏᴜʀ 𝐖ᴀɪғᴜ˼ 🥀\n"
            f"#NEWCHAT\n"
            f"ᴄʜᴀᴛ ᴛɪᴛʟᴇ : {chat_title}\n"
            f"ᴄʜᴀᴛ ɪᴅ : {chat_id}\n"
            f"ᴄʜᴀᴛ ᴜɴᴀᴍᴇ : {chatusername}\n"
            f"ᴀᴅᴅᴇᴅ ʙʏ : {added_by}"
        )

        await lul_message(JOINLOGS, text)


@app.on_message(filters.left_chat_member)
async def on_left_chat_member(_, message: Message):
    me = await app.get_me()
    if me.id == message.left_chat_member.id:
        remove_by = message.from_user.mention if message.from_user else "ᴜɴᴋɴᴏᴡɴ ᴜꜱᴇʀ"
        title = message.chat.title
        username = f"@{message.chat.username}" if message.chat.username else "ᴘʀɪᴠᴀᴛᴇ ᴄʜᴀᴛ"
        chat_id = message.chat.id

        text = (
            f"#ʟᴇꜰᴛ ɢʀᴏᴜᴘ ✫\n"
            f"ᴄʜᴀᴛ ᴛɪᴛʟᴇ : {title}\n"
            f"✫ ᴄʜᴀᴛ ɪᴅ : {chat_id}\n"
            f"ʀᴇᴍᴏᴠᴇᴅ ʙʏ : {remove_by}\n"
            f"id : {chat_id}"
        )

        await app.send_message(LEAVELOGS, text)