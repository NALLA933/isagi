from dataclasses import dataclass
from html import escape
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from shivu import application, user_collection

OWNER_ID = 5147822244


@dataclass
class UserTarget:
    id: int
    username: str | None = None
    first_name: str = "Unknown"


@dataclass
class BalanceInfo:
    wallet: int
    bank: int
    
    @property
    def total(self) -> int:
        return self.wallet + self.bank


async def get_target_user(update: Update, context: CallbackContext) -> UserTarget | None:
    if reply := update.message.reply_to_message:
        return UserTarget(
            id=reply.from_user.id,
            username=reply.from_user.username,
            first_name=reply.from_user.first_name
        )
    
    if context.args:
        try:
            return UserTarget(id=int(context.args[0]))
        except ValueError:
            await update.message.reply_text(
                "<b>Invalid user ID</b>\n\n"
                "Usage: <code>/ckill [user_id]</code> or reply to user",
                parse_mode='HTML'
            )
            return None
    
    await update.message.reply_text(
        "Usage: <code>/ckill [user_id]</code> or reply to user",
        parse_mode='HTML'
    )
    return None


async def ckill(update: Update, context: CallbackContext) -> None:
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Owner only command.")
        return
    
    if not (target := await get_target_user(update, context)):
        return
    
    try:
        user = await user_collection.find_one({'id': target.id})
        
        if not user:
            await update.message.reply_text(
                f"❌ User not found\nID: <code>{target.id}</code>",
                parse_mode='HTML'
            )
            return
        
        target.username = target.username or user.get('username')
        target.first_name = user.get('first_name', target.first_name)
        
        balance = BalanceInfo(
            wallet=user.get('balance', 0),
            bank=user.get('bank', 0)
        )
        
        result = await user_collection.update_one(
            {'id': target.id},
            {'$set': {'balance': 0, 'bank': 0}}
        )
        
        if result.modified_count > 0:
            await update.message.reply_text(
                f"<b>✅ Balance Reset</b>\n\n"
                f"<b>User:</b> <a href='tg://user?id={target.id}'>{escape(target.first_name)}</a>\n"
                f"<b>ID:</b> <code>{target.id}</code>\n\n"
                f"<b>Previous:</b>\n"
                f"Wallet: <code>{balance.wallet:,}</code>\n"
                f"Bank: <code>{balance.bank:,}</code>\n"
                f"Total: <code>{balance.total:,}</code>\n\n"
                f"<b>New Balance:</b> <code>0</code>",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text("❌ Failed to update balance")
    
    except Exception as e:
        await update.message.reply_text(
            f"<b>Error:</b> <code>{str(e)}</code>",
            parse_mode='HTML'
        )


application.add_handler(CommandHandler('ckill', ckill, block=False))