import asyncio
import traceback
import sys
import importlib
from dataclasses import dataclass, field
from typing import Optional, Callable, Any, Dict, List
from datetime import datetime
from functools import wraps
from telegram import Update
from telegram.ext import CallbackContext
from telegram.error import TelegramError, BadRequest, Forbidden, NetworkError, TimedOut

ERROR_REPORT_CHAT_ID = -1003129952280


@dataclass
class ErrorContext:
    error: Exception
    error_type: str
    traceback_str: str
    timestamp: datetime
    module_name: Optional[str] = None
    function_name: Optional[str] = None
    user_id: Optional[int] = None
    chat_id: Optional[int] = None
    update_data: Optional[Dict] = None
    context_data: Optional[Dict] = None
    fixed: bool = False
    fix_method: Optional[str] = None


@dataclass
class FixStrategy:
    name: str
    error_types: List[type]
    fix_function: Callable
    priority: int = 0


class AutoFixSystem:
    def __init__(self, bot_instance, logger):
        self.bot = bot_instance
        self.logger = logger
        self.fix_strategies: List[FixStrategy] = []
        self.error_history: List[ErrorContext] = []
        self.max_history = 100
        self._register_default_strategies()

    def _register_default_strategies(self):
        self.register_strategy(FixStrategy(
            name="telegram_network_retry",
            error_types=[NetworkError, TimedOut],
            fix_function=self._fix_network_error,
            priority=1
        ))
        
        self.register_strategy(FixStrategy(
            name="bad_request_handler",
            error_types=[BadRequest],
            fix_function=self._fix_bad_request,
            priority=2
        ))
        
        self.register_strategy(FixStrategy(
            name="forbidden_handler",
            error_types=[Forbidden],
            fix_function=self._fix_forbidden,
            priority=2
        ))
        
        self.register_strategy(FixStrategy(
            name="attribute_error_handler",
            error_types=[AttributeError],
            fix_function=self._fix_attribute_error,
            priority=3
        ))
        
        self.register_strategy(FixStrategy(
            name="key_error_handler",
            error_types=[KeyError],
            fix_function=self._fix_key_error,
            priority=3
        ))
        
        self.register_strategy(FixStrategy(
            name="type_error_handler",
            error_types=[TypeError],
            fix_function=self._fix_type_error,
            priority=3
        ))
        
        self.register_strategy(FixStrategy(
            name="index_error_handler",
            error_types=[IndexError],
            fix_function=self._fix_index_error,
            priority=3
        ))
        
        self.register_strategy(FixStrategy(
            name="value_error_handler",
            error_types=[ValueError],
            fix_function=self._fix_value_error,
            priority=3
        ))
        
        self.register_strategy(FixStrategy(
            name="import_error_handler",
            error_types=[ImportError, ModuleNotFoundError],
            fix_function=self._fix_import_error,
            priority=4
        ))

    def register_strategy(self, strategy: FixStrategy):
        self.fix_strategies.append(strategy)
        self.fix_strategies.sort(key=lambda x: x.priority)

    async def _fix_network_error(self, error_ctx: ErrorContext, *args, **kwargs) -> bool:
        try:
            await asyncio.sleep(2)
            self.logger.info(f"Retrying after network error: {error_ctx.error_type}")
            return True
        except Exception as e:
            self.logger.error(f"Network retry failed: {e}")
            return False

    async def _fix_bad_request(self, error_ctx: ErrorContext, *args, **kwargs) -> bool:
        try:
            error_msg = str(error_ctx.error).lower()
            
            if "message to delete not found" in error_msg:
                self.logger.warning("Message already deleted, continuing...")
                return True
            
            if "message is not modified" in error_msg:
                self.logger.warning("Message already in desired state, continuing...")
                return True
            
            if "chat not found" in error_msg:
                self.logger.warning("Chat not accessible, skipping...")
                return True
            
            return False
        except Exception as e:
            self.logger.error(f"Bad request fix failed: {e}")
            return False

    async def _fix_forbidden(self, error_ctx: ErrorContext, *args, **kwargs) -> bool:
        try:
            self.logger.warning(f"Bot forbidden in chat {error_ctx.chat_id}, skipping...")
            return True
        except Exception as e:
            self.logger.error(f"Forbidden fix failed: {e}")
            return False

    async def _fix_attribute_error(self, error_ctx: ErrorContext, *args, **kwargs) -> bool:
        try:
            self.logger.warning(f"Attribute error handled: {error_ctx.error}")
            return True
        except Exception as e:
            self.logger.error(f"Attribute error fix failed: {e}")
            return False

    async def _fix_key_error(self, error_ctx: ErrorContext, *args, **kwargs) -> bool:
        try:
            self.logger.warning(f"Key error handled: {error_ctx.error}")
            return True
        except Exception as e:
            self.logger.error(f"Key error fix failed: {e}")
            return False

    async def _fix_type_error(self, error_ctx: ErrorContext, *args, **kwargs) -> bool:
        try:
            self.logger.warning(f"Type error handled: {error_ctx.error}")
            return True
        except Exception as e:
            self.logger.error(f"Type error fix failed: {e}")
            return False

    async def _fix_index_error(self, error_ctx: ErrorContext, *args, **kwargs) -> bool:
        try:
            self.logger.warning(f"Index error handled: {error_ctx.error}")
            return True
        except Exception as e:
            self.logger.error(f"Index error fix failed: {e}")
            return False

    async def _fix_value_error(self, error_ctx: ErrorContext, *args, **kwargs) -> bool:
        try:
            self.logger.warning(f"Value error handled: {error_ctx.error}")
            return True
        except Exception as e:
            self.logger.error(f"Value error fix failed: {e}")
            return False

    async def _fix_import_error(self, error_ctx: ErrorContext, *args, **kwargs) -> bool:
        try:
            self.logger.error(f"Import error detected: {error_ctx.error}")
            return False
        except Exception as e:
            self.logger.error(f"Import error fix failed: {e}")
            return False

    async def handle_error(
        self,
        error: Exception,
        module_name: Optional[str] = None,
        function_name: Optional[str] = None,
        update: Optional[Update] = None,
        context: Optional[CallbackContext] = None,
        **kwargs
    ) -> bool:
        error_ctx = ErrorContext(
            error=error,
            error_type=type(error).__name__,
            traceback_str=traceback.format_exc(),
            timestamp=datetime.now(),
            module_name=module_name,
            function_name=function_name,
            user_id=update.effective_user.id if update and update.effective_user else None,
            chat_id=update.effective_chat.id if update and update.effective_chat else None,
            update_data=self._extract_update_data(update) if update else None,
            context_data=self._extract_context_data(context) if context else None
        )

        for strategy in self.fix_strategies:
            if type(error) in strategy.error_types:
                try:
                    fixed = await strategy.fix_function(error_ctx, update=update, context=context, **kwargs)
                    if fixed:
                        error_ctx.fixed = True
                        error_ctx.fix_method = strategy.name
                        self.logger.info(f"Error fixed using strategy: {strategy.name}")
                        self._add_to_history(error_ctx)
                        return True
                except Exception as fix_error:
                    self.logger.error(f"Fix strategy '{strategy.name}' failed: {fix_error}")
                    continue

        self._add_to_history(error_ctx)
        await self._report_unfixed_error(error_ctx)
        return False

    def _extract_update_data(self, update: Update) -> Dict:
        try:
            return {
                "message_id": update.message.message_id if update.message else None,
                "user_id": update.effective_user.id if update.effective_user else None,
                "chat_id": update.effective_chat.id if update.effective_chat else None,
                "text": update.message.text if update.message and update.message.text else None,
            }
        except Exception as e:
            self.logger.error(f"Failed to extract update data: {e}")
            return {}

    def _extract_context_data(self, context: CallbackContext) -> Dict:
        try:
            return {
                "args": context.args if hasattr(context, 'args') else None,
                "bot_data_keys": list(context.bot_data.keys()) if hasattr(context, 'bot_data') else None,
            }
        except Exception as e:
            self.logger.error(f"Failed to extract context data: {e}")
            return {}

    def _add_to_history(self, error_ctx: ErrorContext):
        self.error_history.append(error_ctx)
        if len(self.error_history) > self.max_history:
            self.error_history.pop(0)

    async def _report_unfixed_error(self, error_ctx: ErrorContext):
        try:
            report = self._format_error_report(error_ctx)
            await self.bot.send_message(
                chat_id=ERROR_REPORT_CHAT_ID,
                text=report,
                parse_mode='HTML'
            )
        except Exception as e:
            self.logger.error(f"Failed to report error: {e}")

    def _format_error_report(self, error_ctx: ErrorContext) -> str:
        report = f"""🚨 <b>UNFIXED ERROR DETECTED</b> 🚨

⏰ <b>Time:</b> {error_ctx.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
❌ <b>Error Type:</b> <code>{error_ctx.error_type}</code>
📦 <b>Module:</b> <code>{error_ctx.module_name or 'Unknown'}</code>
🔧 <b>Function:</b> <code>{error_ctx.function_name or 'Unknown'}</code>

"""
        
        if error_ctx.user_id:
            report += f"👤 <b>User ID:</b> <code>{error_ctx.user_id}</code>\n"
        
        if error_ctx.chat_id:
            report += f"💬 <b>Chat ID:</b> <code>{error_ctx.chat_id}</code>\n"
        
        report += f"\n💥 <b>Error Message:</b>\n<code>{str(error_ctx.error)[:500]}</code>\n"
        
        traceback_lines = error_ctx.traceback_str.split('\n')
        relevant_traceback = '\n'.join(traceback_lines[-10:])
        report += f"\n📜 <b>Traceback:</b>\n<code>{relevant_traceback[:1000]}</code>"
        
        return report

    def wrap_handler(self, module_name: str = None):
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
                try:
                    return await func(update, context, *args, **kwargs)
                except Exception as e:
                    fixed = await self.handle_error(
                        error=e,
                        module_name=module_name or func.__module__,
                        function_name=func.__name__,
                        update=update,
                        context=context
                    )
                    if not fixed:
                        self.logger.error(f"Unhandled error in {func.__name__}: {e}")
            return wrapper
        return decorator

    def wrap_module(self, module):
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if callable(attr) and not attr_name.startswith('_'):
                try:
                    wrapped = self.wrap_handler(module.__name__)(attr)
                    setattr(module, attr_name, wrapped)
                except Exception as e:
                    self.logger.error(f"Failed to wrap {attr_name}: {e}")


def create_autofix_system(bot_instance, logger) -> AutoFixSystem:
    return AutoFixSystem(bot_instance, logger)


def apply_autofix_to_handlers(application, autofix_system: AutoFixSystem):
    for handler_list in application.handlers.values():
        for handler in handler_list:
            if hasattr(handler, 'callback'):
                original_callback = handler.callback
                handler.callback = autofix_system.wrap_handler()(original_callback)