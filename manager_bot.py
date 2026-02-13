"""
Telegram Userbot Manager Bot
Основной файл бота
"""
import sys
import asyncio
import logging
from datetime import datetime, timedelta
import random
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from telegram.error import BadRequest, NetworkError, TimedOut
from telethon import TelegramClient, errors as telethon_errors
from telethon.sessions import StringSession

from config import *
from database import Database
from userbot_manager import UserbotManager
from keyboards import *
from texts import TEXTS
from scheduler import MailingScheduler
from backup_manager import BackupManager

# ==================== LOGGING ====================
logging.basicConfig(
    format=LOG_FORMAT,
    level=getattr(logging, LOG_LEVEL),
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ==================== GLOBALS ====================
db = Database()
userbot_manager = UserbotManager()
scheduler = None
backup_manager = BackupManager()

# ==================== CONVERSATION STATES ====================
# Connect account states
CONNECT_PHONE, CONNECT_CODE, CONNECT_PASSWORD = range(3)

# Mailing states
MAILING_RECIPIENTS, MAILING_MESSAGE, MAILING_CONFIRM, MAILING_ACCOUNT = range(4)

# Admin broadcast states
ADMIN_BROADCAST_MESSAGE, ADMIN_BROADCAST_CONFIRM = range(2)

# ==================== HELPER FUNCTIONS ====================

def is_admin(user_id):
    """Проверка является ли пользователь админом"""
    return user_id == ADMIN_ID

def check_subscription(user_id):
    """Проверить активна ли подписка"""
    user = db.get_user(user_id)
    if not user:
        return False, None
    
    if user['is_banned']:
        return False, "Ваш аккаунт заблокирован"
    
    expires = user.get('subscription_expires')
    if not expires:
        return False, "Подписка не активна"
    
    # Преобразуем строку в datetime
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires)
    
    if datetime.now() > expires:
        return False, "Ваша подписка истекла"
    
    return True, user['subscription_plan']

def check_limits(user_id, check_type='accounts'):
    """Проверить лимиты пользователя"""
    user = db.get_user(user_id)
    if not user:
        return False, "Пользователь не найден"
    
    plan = user['subscription_plan']
    limits = SUBSCRIPTION_PLANS.get(plan, {}).get('limits', {})
    
    if check_type == 'accounts':
        current = db.count_user_accounts(user_id)
        limit = limits.get('accounts', 0)
        
        if limit == -1:  # Неограниченно
            return True, None
        
        if current >= limit:
            return False, f"Достигнут лимит аккаунтов ({limit})"
    
    elif check_type == 'mailings':
        current = db.count_user_mailings_today(user_id)
        limit = limits.get('mailings_per_day', 0)
        
        if limit == -1:
            return True, None
        
        if current >= limit:
            return False, f"Достигнут дневной лимит рассылок ({limit})"
    
    return True, None

async def send_admin_notification(bot, message):
    """Отправить уведомление админу"""
    try:
        await bot.send_message(ADMIN_ID, message)
    except Exception as e:
        logger.error(f"Error sending admin notification: {e}")


async def safe_edit_message(query, text, reply_markup=None, parse_mode='Markdown'):
    """Безопасное редактирование сообщения с обработкой ошибок"""
    try:
        await query.message.edit_text(
            text, 
            reply_markup=reply_markup, 
            parse_mode=parse_mode
        )
        await query.answer()
        return True
    except BadRequest as e:
        error_str = str(e).lower()
        if "message is not modified" in error_str:
            await query.answer("ℹ️ Данные уже отображены")
            return False
        elif "message to edit not found" in error_str:
            # Сообщение было удалено, отправляем новое
            try:
                await query.message.reply_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                await query.answer()
                return True
            except:
                await query.answer("❌ Ошибка отображения", show_alert=True)
                return False
        else:
            logger.error(f"BadRequest error in safe_edit_message: {e}")
            await query.answer("❌ Ошибка", show_alert=True)
            return False
    except Exception as e:
        logger.error(f"Unexpected error in safe_edit_message: {e}")
        await query.answer("❌ Ошибка", show_alert=True)
        return False

# ==================== COMMAND HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    
    # Создаём или обновляем пользователя
    db.create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    user_data = db.get_user(user.id)
    
    # Проверяем подписку
    expires = user_data.get('subscription_expires')
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires)
    
    days_left = (expires - datetime.now()).days if expires else 0
    
    plan_name = SUBSCRIPTION_PLANS.get(user_data['subscription_plan'], {}).get('name', 'Неизвестный')
    
    text = TEXTS['start'].format(
        subscription=plan_name,
        days_left=max(0, days_left)
    )
    
    keyboard = get_main_menu(is_admin=is_admin(user.id))
    
    if update.message:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')
    else:
        await update.callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    keyboard = get_help_menu()
    
    if update.message:
        await update.message.reply_text(TEXTS['help'], reply_markup=keyboard, parse_mode='Markdown')
    else:
        await update.callback_query.message.edit_text(TEXTS['help'], reply_markup=keyboard, parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущего действия"""
    context.user_data.clear()
    
    await update.message.reply_text(
        "❌ Действие отменено",
        reply_markup=get_main_menu(is_admin=is_admin(update.effective_user.id))
    )
    
    return ConversationHandler.END

# ==================== CALLBACK HANDLERS ====================

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню"""
    await start(update, context)
    await update.callback_query.answer()

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь"""
    await help_command(update, context)
    await update.callback_query.answer()

# ==================== ACCOUNTS ====================

async def my_accounts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Мои аккаунты"""
    query = update.callback_query
    user_id = query.from_user.id
    
    accounts = db.get_user_accounts(user_id)
    count = len(accounts)
    
    user = db.get_user(user_id)
    plan = user['subscription_plan']
    limit = SUBSCRIPTION_PLANS[plan]['limits']['accounts']
    limit_text = str(limit) if limit != -1 else "∞"
    
    text = TEXTS['my_accounts'].format(count=count, limit=limit_text)
    keyboard = get_accounts_menu(has_accounts=count > 0)
    
    await safe_edit_message(query, text, reply_markup=keyboard, parse_mode='Markdown')

async def connect_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало подключения аккаунта"""
    query = update.callback_query
    user_id = query.from_user.id
    
    # Проверяем подписку
    is_active, plan = check_subscription(user_id)
    if not is_active:
        await query.answer("❌ " + plan, show_alert=True)
        return ConversationHandler.END
    
    # Проверяем лимиты
    can_add, error = check_limits(user_id, 'accounts')
    if not can_add:
        await query.answer("❌ " + error, show_alert=True)
        return ConversationHandler.END
    
    await query.message.edit_text(
        TEXTS['connect_account'],
        reply_markup=get_cancel_button(),
        parse_mode='Markdown'
    )
    await query.answer()
    
    return PHONE

async def phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка номера телефона"""
    phone = update.message.text.strip()
    
    # Валидация номера
    if not phone.startswith('+'):
        await update.message.reply_text(
            "❌ Номер должен начинаться с + и кода страны\n\n"
            "Пример: +79001234567"
        )
        return PHONE
    
    try:
        # Создаём клиента
        client = await userbot_manager.create_client(phone)
        phone_code_hash = await userbot_manager.send_code(client, phone)
        
        # Сохраняем в контексте
        context.user_data['phone'] = phone
        context.user_data['client'] = client
        context.user_data['phone_code_hash'] = phone_code_hash
        
        text = TEXTS['enter_code'].format(phone=phone)
        await update.message.reply_text(text, reply_markup=get_cancel_button(), parse_mode='Markdown')
        
        return CODE
    
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        return PHONE

async def code_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кода подтверждения"""
    code = update.message.text.strip()
    
    client = context.user_data.get('client')
    phone = context.user_data.get('phone')
    phone_code_hash = context.user_data.get('phone_code_hash')
    
    if not all([client, phone, phone_code_hash]):
        await update.message.reply_text("❌ Ошибка: данные сессии потеряны. Начните заново.")
        return ConversationHandler.END
    
    try:
        # Пытаемся войти
        needs_2fa = await userbot_manager.sign_in(client, phone, code, phone_code_hash)
        
        if needs_2fa is False:
            # Требуется 2FA
            await update.message.reply_text(
                TEXTS['enter_password'],
                reply_markup=get_cancel_button(),
                parse_mode='Markdown'
            )
            return PASSWORD
        
        # Успешный вход
        await complete_account_connection(update, context, client, phone)
        return ConversationHandler.END
    
    except ValueError as e:
        await update.message.reply_text(f"❌ {str(e)}")
        return CODE
    except Exception as e:
        logger.error(f"Error in code_handler: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        return CODE

async def password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка пароля 2FA"""
    password = update.message.text.strip()
    
    client = context.user_data.get('client')
    phone = context.user_data.get('phone')
    
    if not all([client, phone]):
        await update.message.reply_text("❌ Ошибка: данные сессии потеряны.")
        return ConversationHandler.END
    
    try:
        await userbot_manager.sign_in_2fa(client, password)
        await complete_account_connection(update, context, client, phone)
        return ConversationHandler.END
    
    except ValueError as e:
        await update.message.reply_text(f"❌ {str(e)}")
        return PASSWORD
    except Exception as e:
        logger.error(f"Error in password_handler: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        return PASSWORD

async def complete_account_connection(update: Update, context: ContextTypes.DEFAULT_TYPE, client, phone):
    """Завершение подключения аккаунта"""
    try:
        # Получаем информацию о пользователе
        me = await userbot_manager.get_me(client)
        
        if not me:
            await update.message.reply_text("❌ Не удалось получить информацию об аккаунте")
            return
        
        # Получаем строку сессии
        session_string = await userbot_manager.get_session_string(client)
        
        # Сохраняем в базу
        account_id = db.add_account(
            user_id=update.effective_user.id,
            phone=phone,
            session_string=session_string,
            name=f"{me.get('first_name', '')} {me.get('last_name', '')}".strip(),
            username=me.get('username')
        )
        
        if not account_id:
            await update.message.reply_text("❌ Этот аккаунт уже подключен")
            return
        
        # Загружаем клиента в менеджер
        await userbot_manager.load_client(account_id, session_string)
        
        # Очищаем временные данные
        context.user_data.clear()
        
        # Отправляем подтверждение
        text = TEXTS['account_connected'].format(
            name=me.get('first_name', 'Без имени'),
            phone=phone,
            username=me.get('username', 'Нет')
        )
        
        await update.message.reply_text(
            text,
            reply_markup=get_main_menu(is_admin=is_admin(update.effective_user.id)),
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ Account connected: {phone} for user {update.effective_user.id}")
    
    except Exception as e:
        logger.error(f"Error completing account connection: {e}")
        await update.message.reply_text(f"❌ Ошибка сохранения аккаунта: {str(e)}")

async def cancel_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена подключения аккаунта"""
    # Отключаем клиента если он был создан
    client = context.user_data.get('client')
    if client:
        try:
            await client.disconnect()
        except:
            pass
    
    context.user_data.clear()
    
    text = "❌ Подключение аккаунта отменено"
    keyboard = get_main_menu(is_admin=is_admin(update.effective_user.id))
    
    if update.message:
        await update.message.reply_text(text, reply_markup=keyboard)
    else:
        await update.callback_query.message.edit_text(text, reply_markup=keyboard)
    
    return ConversationHandler.END

async def manage_accounts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление аккаунтами"""
    query = update.callback_query
    user_id = query.from_user.id
    
    accounts = db.get_user_accounts(user_id)
    
    if not accounts:
        await query.answer("У вас нет подключенных аккаунтов", show_alert=True)
        return
    
    text = "⚙️ **Управление аккаунтами**\n\nВыберите аккаунт:"
    keyboard = get_accounts_list(accounts)
    
    await safe_edit_message(query, text, reply_markup=keyboard, parse_mode='Markdown')

async def account_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация об аккаунте"""
    query = update.callback_query
    account_id = int(query.data.split('_')[-1])
    
    account = db.get_account(account_id)
    
    if not account or account['user_id'] != query.from_user.id:
        await query.answer("❌ Аккаунт не найден", show_alert=True)
        return
    
    status = "🟢 Активен" if account['is_active'] else "🔴 Неактивен"
    last_used = account.get('last_used', 'Никогда')
    
    text = f"""
📱 **Информация об аккаунте**

**Имя:** {account.get('name', 'Не указано')}
**Телефон:** {account['phone']}
**Username:** @{account.get('username', 'Нет')}
**Статус:** {status}
**Последнее использование:** {last_used}
**Добавлен:** {account['created_at'][:16]}
"""
    
    keyboard = get_account_actions(account_id)
    
    await safe_edit_message(query, text, reply_markup=keyboard, parse_mode='Markdown')

async def disconnect_account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отключение аккаунта"""
    query = update.callback_query
    account_id = int(query.data.split('_')[-1])
    user_id = query.from_user.id
    
    account = db.get_account(account_id)
    
    if not account or account['user_id'] != user_id:
        await query.answer("❌ Аккаунт не найден", show_alert=True)
        return
    
    # Отключаем клиента из менеджера
    await userbot_manager.disconnect_client(account_id)
    
    # Удаляем из базы
    db.delete_account(account_id, user_id)
    
    await query.answer("✅ Аккаунт отключен", show_alert=True)
    
    # Возвращаемся к списку
    await manage_accounts_callback(update, context)

async def accounts_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Назад к списку аккаунтов"""
    await my_accounts_callback(update, context)

# ==================== MAILING ====================

async def create_mailing_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания рассылки"""
    query = update.callback_query
    user_id = query.from_user.id
    
    # Проверяем подписку
    is_active, plan = check_subscription(user_id)
    if not is_active:
        await query.answer("❌ " + plan, show_alert=True)
        return
    
    # Проверяем лимиты
    can_create, error = check_limits(user_id, 'mailings')
    if not can_create:
        await query.answer("❌ " + error, show_alert=True)
        return
    
    # Проверяем наличие аккаунтов
    accounts = db.get_user_accounts(user_id)
    if not accounts:
        await query.answer("❌ Сначала подключите хотя бы один аккаунт", show_alert=True)
        return
    
    await query.message.edit_text(
        TEXTS['create_mailing'],
        reply_markup=get_cancel_button(),
        parse_mode='Markdown'
    )
    await query.answer()

async def mailing_targets_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получены цели для рассылки"""
    text = update.message.text.strip()
    
    # Парсим цели (каждая строка - цель)
    targets = [line.strip() for line in text.split('\n') if line.strip()]
    
    if not targets:
        await update.message.reply_text("❌ Список целей пуст. Попробуйте снова:")
        return MAILING_TARGETS
    
    # Сохраняем в контекст
    context.user_data['targets'] = targets
    
    # Показываем список аккаунтов для выбора
    accounts = db.get_user_accounts(update.effective_user.id)
    
    text = TEXTS['select_accounts'].format(targets_count=len(targets))
    keyboard = get_account_selection(accounts, selected_ids=[])
    
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')
    
    return MAILING_ACCOUNTS

async def toggle_account_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключение выбора аккаунта"""
    query = update.callback_query
    account_id = int(query.data.split('_')[-1])
    
    # Получаем список выбранных
    selected = context.user_data.get('selected_accounts', [])
    
    if account_id in selected:
        selected.remove(account_id)
    else:
        selected.append(account_id)
    
    context.user_data['selected_accounts'] = selected
    
    # Обновляем клавиатуру
    accounts = db.get_user_accounts(query.from_user.id)
    targets_count = len(context.user_data.get('targets', []))
    
    text = TEXTS['select_accounts'].format(targets_count=targets_count)
    keyboard = get_account_selection(accounts, selected_ids=selected)
    
    await safe_edit_message(query, text, reply_markup=keyboard, parse_mode='Markdown')

async def continue_with_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Продолжить с выбранными аккаунтами"""
    query = update.callback_query
    
    selected = context.user_data.get('selected_accounts', [])
    
    if not selected:
        await query.answer("❌ Выберите хотя бы один аккаунт", show_alert=True)
        return MAILING_ACCOUNTS
    
    await query.message.edit_text(
        TEXTS['enter_message'],
        reply_markup=get_cancel_button(),
        parse_mode='Markdown'
    )
    await query.answer()
    
    return MAILING_MESSAGE

async def confirm_mailing_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение и запуск рассылки"""
    query = update.callback_query
    user_id = query.from_user.id
    
    # Получаем данные из контекста
    targets = context.user_data.get('targets', [])
    accounts = context.user_data.get('selected_accounts', [])
    message_text = context.user_data.get('message_text', '')
    message_type = context.user_data.get('message_type', 'text')
    media_path = context.user_data.get('media_path')
    
    # Создаём рассылку в БД
    mailing_id = db.create_mailing(
        user_id=user_id,
        message_text=message_text,
        targets=targets,
        accounts=accounts,
        message_type=message_type,
        media_path=media_path
    )
    
    # Запускаем рассылку асинхронно
    asyncio.create_task(run_mailing(mailing_id, context.bot))
    
    # Очищаем контекст
    context.user_data.clear()
    
    text = TEXTS['mailing_started'].format(mailing_id=mailing_id)
    
    await query.message.edit_text(
        text,
        reply_markup=get_main_menu(is_admin=is_admin(user_id)),
        parse_mode='Markdown'
    )
    await query.answer("🚀 Рассылка запущена!")
    
    return ConversationHandler.END

async def cancel_mailing_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена создания рассылки"""
    query = update.callback_query
    context.user_data.clear()
    
    await query.message.edit_text(
        "❌ Создание рассылки отменено",
        reply_markup=get_main_menu(is_admin=is_admin(query.from_user.id))
    )
    await query.answer()
    
    return ConversationHandler.END

async def run_mailing(mailing_id, bot):
    """Выполнение рассылки"""
    try:
        # Обновляем статус
        db.update_mailing(mailing_id, status='running', started_at=datetime.now())
        
        # Получаем данные рассылки
        mailing = db.get_mailing(mailing_id)
        if not mailing:
            logger.error(f"Mailing {mailing_id} not found")
            return
        
        user_id = mailing['user_id']
        targets = mailing['targets']
        account_ids = mailing['accounts']
        message_text = mailing['message_text']
        
        logger.info(f"🚀 Starting mailing {mailing_id}: {len(targets)} targets, {len(account_ids)} accounts")
        
        # Загружаем клиентов
        clients = []
        for acc_id in account_ids:
            account = db.get_account(acc_id)
            if account and account['is_active']:
                client = await userbot_manager.get_client(acc_id)
                if not client:
                    # Загружаем если не загружен
                    client = await userbot_manager.load_client(acc_id, account['session_string'])
                if client:
                    clients.append((acc_id, client))
        
        if not clients:
            db.update_mailing(mailing_id, status='failed')
            await bot.send_message(user_id, f"❌ Рассылка #{mailing_id} не запущена: нет доступных аккаунтов")
            return
        
        # Распределяем цели по аккаунтам
        sent = 0
        errors = 0
        current_client_idx = 0
        
        for target in targets:
            try:
                # Выбираем клиента по кругу
                acc_id, client = clients[current_client_idx]
                current_client_idx = (current_client_idx + 1) % len(clients)
                
                # Отправляем сообщение
                success, error = await userbot_manager.send_message(client, target, message_text)
                
                if success:
                    sent += 1
                    # Обновляем last_used для аккаунта
                    db.update_account(acc_id, last_used=datetime.now())
                else:
                    errors += 1
                    logger.warning(f"Failed to send to {target}: {error}")
                
                # Обновляем прогресс
                db.update_mailing(mailing_id, sent=sent, errors=errors)
                
                # Задержка
                import random
                delay = random.randint(MAILING_SETTINGS['min_delay'], MAILING_SETTINGS['max_delay'])
                await asyncio.sleep(delay)
                
            except Exception as e:
                errors += 1
                logger.error(f"Error sending to {target}: {e}")
        
        # Завершаем рассылку
        db.update_mailing(
            mailing_id,
            status='completed',
            sent=sent,
            errors=errors,
            completed_at=datetime.now()
        )
        
        # Уведомляем пользователя
        success_percent = int((sent / len(targets)) * 100) if targets else 0
        error_percent = 100 - success_percent
        
        duration = "несколько минут"  # TODO: рассчитать реальное время
        
        text = TEXTS['mailing_completed'].format(
            mailing_id=mailing_id,
            total=len(targets),
            success=sent,
            success_percent=success_percent,
            errors=errors,
            error_percent=error_percent,
            duration=duration,
            error_details="Нет ошибок" if errors == 0 else f"{errors} сообщений не доставлено"
        )
        
        await bot.send_message(user_id, text, parse_mode='Markdown')
        
        logger.info(f"✅ Mailing {mailing_id} completed: {sent}/{len(targets)} sent")
    
    except Exception as e:
        logger.error(f"❌ Fatal error in mailing {mailing_id}: {e}")
        db.update_mailing(mailing_id, status='failed')
        try:
            await bot.send_message(user_id, f"❌ Рассылка #{mailing_id} завершилась с ошибкой")
        except:
            pass

# ==================== SUBSCRIPTIONS ====================

async def subscriptions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тарифы"""
    query = update.callback_query
    user_id = query.from_user.id
    
    user = db.get_user(user_id)
    current_plan = user['subscription_plan']
    expires = user.get('subscription_expires')
    
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires)
    
    expires_text = expires.strftime('%d.%m.%Y') if expires else 'Не активна'
    
    plan_info = SUBSCRIPTION_PLANS.get(current_plan, {})
    current_plan_name = plan_info.get('name', 'Неизвестный')
    
    text = TEXTS['subscriptions'].format(
        current_plan=current_plan_name,
        expires_at=expires_text
    )
    
    keyboard = get_subscription_menu(current_plan)
    
    await safe_edit_message(query, text, reply_markup=keyboard, parse_mode='Markdown')

async def buy_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Покупка тарифа"""
    query = update.callback_query
    
    # Проверяем формат данных
    parts = query.data.split('_')
    if len(parts) < 2:
        await query.answer("❌ Некорректные данные", show_alert=True)
        return
    
    plan_id = parts[1]
    
    if plan_id not in SUBSCRIPTION_PLANS:
        await query.answer("❌ Тариф не найден", show_alert=True)
        return
    
    plan = SUBSCRIPTION_PLANS[plan_id]
    
    # Проверяем не пытается ли купить текущий план
    user = db.get_user(query.from_user.id)
    if user and user['subscription_plan'] == plan_id:
        current_expires = user.get('subscription_expires')
        if isinstance(current_expires, str):
            try:
                current_expires = datetime.fromisoformat(current_expires)
            except:
                current_expires = None
        
        if current_expires and current_expires > datetime.now():
            # Уже есть активная подписка этого типа
            days_left = (current_expires - datetime.now()).days
            await query.answer(
                f"ℹ️ У вас уже активен {plan['name']}\nОсталось дней: {days_left}",
                show_alert=True
            )
            return
    
    # Форматируем детали тарифа
    features = '\n'.join(plan['features'])
    
    limits = plan['limits']
    if limits['accounts'] == -1:
        accounts_text = '∞ (неограниченно)'
    else:
        accounts_text = str(limits['accounts'])
    
    if limits['mailings_per_day'] == -1:
        mailings_text = '∞ (неограниченно)'
    else:
        mailings_text = str(limits['mailings_per_day'])
    
    if limits['messages_per_mailing'] == -1:
        messages_text = '∞ (неограниченно)'
    else:
        messages_text = str(limits['messages_per_mailing'])
    
    # Получаем эмодзи
    emoji_map = {
        'trial': '🆓',
        'basic': '💼',
        'pro': '🚀',
        'premium': '👑'
    }
    emoji = emoji_map.get(plan_id, '💎')
    
    # Формируем текст БЕЗ жирного шрифта для совместимости
    text = f"""{emoji} {plan['name']} - {plan['price']} ₽/мес

📋 Описание:
{plan['description']}

✨ Возможности:
{features}

📊 Лимиты:
• Аккаунтов: {accounts_text}
• Рассылок в день: {mailings_text}
• Сообщений на рассылку: {messages_text}

💰 Цена: {plan['price']} ₽
⏱ Период: {plan['days']} дней

Выберите способ оплаты:"""
    
    keyboard = get_plan_details(plan_id)
    
    try:
        # Отправляем БЕЗ parse_mode для надёжности
        await query.message.edit_text(
            text, 
            reply_markup=keyboard
        )
        await query.answer()
    except BadRequest as e:
        error_str = str(e).lower()
        
        if "message is not modified" in error_str:
            # Сообщение не изменилось
            await query.answer()
        elif "message to edit not found" in error_str or "message can't be edited" in error_str:
            # Сообщение было удалено или не может быть отредактировано
            try:
                await query.message.reply_text(
                    text,
                    reply_markup=keyboard
                )
                await query.answer()
            except:
                await query.answer("❌ Ошибка отображения", show_alert=True)
        else:
            # Другая ошибка
            logger.error(f"BadRequest in buy_subscription: {e}")
            await query.answer("❌ Ошибка: " + str(e)[:50], show_alert=True)
    except Exception as e:
        logger.error(f"Error in buy_subscription: {e}")
        await query.answer("❌ Произошла ошибка", show_alert=True)

# ==================== MAILING FUNCTIONS ====================

async def create_mailing_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания рассылки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Проверяем наличие подключенных аккаунтов
    accounts = db.get_user_accounts(user_id)
    if not accounts:
        await query.message.edit_text(
            "❌ У вас нет подключенных аккаунтов.\n\n"
            "Сначала подключите хотя бы один аккаунт.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data='main_menu')
            ]])
        )
        return ConversationHandler.END
    
    # Проверяем лимиты
    user = db.get_user(user_id)
    plan_limits = SUBSCRIPTION_PLANS[user['subscription_plan']]['limits']
    
    # Получаем количество рассылок за сегодня
    today_mailings = db.get_today_mailings_count(user_id)
    
    if plan_limits['mailings_per_day'] != -1 and today_mailings >= plan_limits['mailings_per_day']:
        await query.message.edit_text(
            f"❌ Вы достигли лимита рассылок на сегодня.\n\n"
            f"Ваш тариф: {user['subscription_plan']}\n"
            f"Лимит: {plan_limits['mailings_per_day']} рассылок/день\n"
            f"Использовано: {today_mailings}\n\n"
            f"Обновите тариф для увеличения лимита.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💎 Улучшить тариф", callback_data='subscriptions')
            ], [
                InlineKeyboardButton("◀️ Назад", callback_data='main_menu')
            ]])
        )
        return ConversationHandler.END
    
    text = """
📨 Создание рассылки

Шаг 1/3: Укажите получателей

Введите username получателей (по одному на строку) или ID чата/группы.

Примеры:
@username1
@username2
https://t.me/username3
-1001234567890

Или отправьте /cancel для отмены.
"""
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data='cancel_mailing')]]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Инициализируем данные рассылки
    context.user_data['mailing'] = {}
    
    logger.info(f"User {user_id} started mailing creation")
    
    return MAILING_RECIPIENTS


async def mailing_recipients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка получателей рассылки"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    logger.info(f"User {user_id} entered recipients: {text[:100]}")
    
    # Парсим получателей
    recipients = []
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        # Удаляем @ если есть
        if line.startswith('@'):
            line = line[1:]
        
        # Извлекаем username из ссылки t.me
        if 't.me/' in line:
            line = line.split('t.me/')[-1].split('?')[0]
        
        recipients.append(line)
    
    if not recipients:
        await update.message.reply_text(
            "❌ Не указаны получатели.\n\n"
            "Пожалуйста, введите хотя бы одного получателя.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Отмена", callback_data='cancel_mailing')
            ]])
        )
        return MAILING_RECIPIENTS
    
    # Проверяем лимит
    user = db.get_user(user_id)
    plan_limits = SUBSCRIPTION_PLANS[user['subscription_plan']]['limits']
    
    if plan_limits['messages_per_mailing'] != -1 and len(recipients) > plan_limits['messages_per_mailing']:
        await update.message.reply_text(
            f"❌ Превышен лимит получателей.\n\n"
            f"Ваш тариф: {user['subscription_plan']}\n"
            f"Лимит: {plan_limits['messages_per_mailing']} получателей\n"
            f"Вы указали: {len(recipients)}\n\n"
            f"Обновите тариф или уменьшите количество получателей.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💎 Улучшить тариф", callback_data='subscriptions')
            ], [
                InlineKeyboardButton("❌ Отмена", callback_data='cancel_mailing')
            ]])
        )
        return MAILING_RECIPIENTS
    
    # Сохраняем получателей
    context.user_data['mailing']['recipients'] = recipients
    
    text = f"""
📨 Создание рассылки

Шаг 2/3: Введите сообщение

✅ Получатели: {len(recipients)}

Теперь введите текст сообщения, которое будет отправлено всем получателям.

Вы можете использовать форматирование:
• **жирный** 
• *курсив*
• `код`

Или отправьте /cancel для отмены.
"""
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data='cancel_mailing')]]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    logger.info(f"User {user_id} set {len(recipients)} recipients")
    
    return MAILING_MESSAGE


async def mailing_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщения рассылки"""
    user_id = update.effective_user.id
    message_text = update.message.text
    
    logger.info(f"User {user_id} entered message: {message_text[:100]}")
    
    if not message_text or len(message_text.strip()) == 0:
        await update.message.reply_text(
            "❌ Сообщение не может быть пустым.\n\n"
            "Пожалуйста, введите текст сообщения.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Отмена", callback_data='cancel_mailing')
            ]])
        )
        return MAILING_MESSAGE
    
    # Сохраняем сообщение
    context.user_data['mailing']['message'] = message_text
    
    # Получаем аккаунты пользователя
    accounts = db.get_user_accounts(user_id)
    
    if len(accounts) == 1:
        # Только один аккаунт - используем его автоматически
        context.user_data['mailing']['account_id'] = accounts[0]['id']
        return await show_mailing_confirm(update, context)
    else:
        # Несколько аккаунтов - даём выбрать
        text = f"""
📨 Создание рассылки

Шаг 3/3: Выберите аккаунт

✅ Получатели: {len(context.user_data['mailing']['recipients'])}
✅ Сообщение: установлено

Выберите аккаунт, с которого будет отправлена рассылка:
"""
        
        keyboard = []
        for account in accounts:
            keyboard.append([InlineKeyboardButton(
                f"📱 {account['phone']}",
                callback_data=f"mailing_account_{account['id']}"
            )])
        
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data='cancel_mailing')])
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return MAILING_ACCOUNT


async def mailing_select_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор аккаунта для рассылки"""
    query = update.callback_query
    await query.answer()
    
    account_id = int(query.data.split('_')[-1])
    context.user_data['mailing']['account_id'] = account_id
    
    return await show_mailing_confirm(update, context, edit_message=True)


async def show_mailing_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, edit_message=False):
    """Показ подтверждения рассылки"""
    mailing_data = context.user_data['mailing']
    user_id = update.effective_user.id
    
    # Получаем информацию об аккаунте
    account = db.get_account(mailing_data['account_id'])
    
    recipients_preview = '\n'.join(['@' + r for r in mailing_data['recipients'][:5]])
    if len(mailing_data['recipients']) > 5:
        recipients_preview += f"\n... и ещё {len(mailing_data['recipients']) - 5}"
    
    message_preview = mailing_data['message'][:200]
    if len(mailing_data['message']) > 200:
        message_preview += '...'
    
    text = f"""
📨 Подтверждение рассылки

📱 Аккаунт: {account['phone']}
👥 Получатели: {len(mailing_data['recipients'])}

📝 Сообщение:
{message_preview}

📋 Получатели:
{recipients_preview}

Подтвердите отправку рассылки.
"""
    
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить и отправить", callback_data='confirm_mailing')],
        [InlineKeyboardButton("❌ Отмена", callback_data='cancel_mailing')]
    ]
    
    if edit_message:
        await update.callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return MAILING_CONFIRM


async def mailing_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение и запуск рассылки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    mailing_data = context.user_data.get('mailing', {})
    
    if not mailing_data:
        await query.message.edit_text(
            "❌ Данные рассылки потеряны. Попробуйте создать рассылку заново.",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END
    
    # Создаём запись в БД
    mailing_id = db.create_mailing(
        user_id=user_id,
        account_id=mailing_data['account_id'],
        recipients=mailing_data['recipients'],
        message=mailing_data['message'],
        status='pending'
    )
    
    await query.message.edit_text(
        f"✅ Рассылка #{mailing_id} создана!\n\n"
        f"👥 Получателей: {len(mailing_data['recipients'])}\n"
        f"⏳ Статус: Запускается...\n\n"
        f"Рассылка начнётся в течение минуты.",
        reply_markup=get_main_menu()
    )
    
    # Запускаем рассылку в фоне
    asyncio.create_task(execute_mailing(mailing_id, user_id, context))
    
    # Очищаем данные
    context.user_data.pop('mailing', None)
    
    logger.info(f"Mailing {mailing_id} created and started by user {user_id}")
    
    return ConversationHandler.END


async def mailing_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена создания рассылки"""
    # Очищаем данные
    context.user_data.pop('mailing', None)
    
    text = "❌ Создание рассылки отменено."
    keyboard = get_main_menu()
    
    if update.callback_query:
        await update.callback_query.answer("Отменено")
        await update.callback_query.message.edit_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)
    
    return ConversationHandler.END


async def execute_mailing(mailing_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Выполнение рассылки"""
    try:
        # Получаем данные рассылки
        mailing = db.get_mailing(mailing_id)
        if not mailing:
            logger.error(f"Mailing {mailing_id} not found")
            return
        
        account = db.get_account(mailing['account_id'])
        if not account:
            logger.error(f"Account {mailing['account_id']} not found")
            db.update_mailing_status(mailing_id, 'failed', 'Account not found')
            return
        
        # Получаем клиент
        client = await userbot_manager.get_client(account['id'])
        if not client:
            logger.error(f"Failed to get client for account {account['id']}")
            db.update_mailing_status(mailing_id, 'failed', 'Failed to connect account')
            return
        
        # Обновляем статус
        db.update_mailing_status(mailing_id, 'in_progress')
        
        recipients = mailing['recipients']
        message = mailing['message']
        
        sent = 0
        failed = 0
        
        for recipient in recipients:
            try:
                # Отправляем сообщение
                await client.send_message(recipient, message)
                sent += 1
                logger.info(f"Message sent to {recipient} (mailing {mailing_id})")
                
                # Задержка между сообщениями (анти-спам)
                await asyncio.sleep(random.uniform(2, 5))
                
            except Exception as e:
                failed += 1
                logger.error(f"Failed to send message to {recipient}: {e}")
                await asyncio.sleep(1)
        
        # Обновляем статус
        status = 'completed' if failed == 0 else 'partial'
        db.update_mailing_status(
            mailing_id, 
            status, 
            f'Sent: {sent}, Failed: {failed}'
        )
        
        # Уведомляем пользователя
        result_text = f"""
✅ Рассылка #{mailing_id} завершена!

📊 Статистика:
• Отправлено: {sent}
• Не доставлено: {failed}
• Всего получателей: {len(recipients)}

{"✅ Все сообщения доставлены!" if failed == 0 else "⚠️ Некоторые сообщения не доставлены"}
"""
        
        await context.bot.send_message(
            chat_id=user_id,
            text=result_text
        )
        
        logger.info(f"Mailing {mailing_id} completed: sent={sent}, failed={failed}")
        
    except Exception as e:
        logger.error(f"Error executing mailing {mailing_id}: {e}", exc_info=True)
        db.update_mailing_status(mailing_id, 'failed', str(e))
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ Ошибка при выполнении рассылки #{mailing_id}:\n{str(e)}"
            )
        except:
            pass

async def payment_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора метода оплаты"""
    query = update.callback_query
    
    # Формат: pay_card_premium или pay_crypto_premium
    parts = query.data.split('_')
    if len(parts) < 3:
        await query.answer("❌ Некорректные данные", show_alert=True)
        return
    
    payment_method = parts[1]  # card или crypto
    plan_id = parts[2]  # basic, pro, premium
    
    if plan_id not in SUBSCRIPTION_PLANS:
        await query.answer("❌ Тариф не найден", show_alert=True)
        return
    
    plan = SUBSCRIPTION_PLANS[plan_id]
    user = db.get_user(query.from_user.id)
    
    if payment_method == 'card':
        # Оплата картой
        text = f"""
💳 Оплата картой

📦 Тариф: {plan['name']}
💰 Сумма: {plan['price']} ₽

Для оплаты картой переведите {plan['price']} ₽ на карту:

💳 **Номер карты:**
`2200 1536 8370 4721`

**Получатель:** Денис Д.

После оплаты отправьте скриншот чека боту или нажмите "Я оплатил".

⚠️ Платёж будет проверен администратором в течение 1-24 часов.
"""
        
        keyboard = [
            [InlineKeyboardButton("✅ Я оплатил", callback_data=f'paid_card_{plan_id}')],
            [InlineKeyboardButton("◀️ Назад", callback_data=f'buy_{plan_id}')]
        ]
        
    elif payment_method == 'crypto':
        # Оплата криптой
        text = f"""
🪙 Оплата криптовалютой

📦 Тариф: {plan['name']}
💰 Сумма: {plan['price']} ₽ (~{plan['price'] // 100} USDT)

Для оплаты криптовалютой переведите эквивалент {plan['price']} ₽ на адрес:

🪙 **USDT (TRC-20):**
`TQx2tg6539Q4vaE1nb57XzPAbdwczmMNX4`

**Сеть:** Tron (TRC-20)

После оплаты отправьте:
1. Скриншот транзакции
2. Хэш транзакции

⚠️ Платёж будет проверен администратором в течение 1-24 часов.
"""
        
        keyboard = [
            [InlineKeyboardButton("✅ Я оплатил", callback_data=f'paid_crypto_{plan_id}')],
            [InlineKeyboardButton("◀️ Назад", callback_data=f'buy_{plan_id}')]
        ]
    else:
        await query.answer("❌ Неизвестный метод оплаты", show_alert=True)
        return
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        await query.answer()
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            await query.answer()
        else:
            logger.error(f"Error in payment_method_callback: {e}")
            await query.answer("❌ Ошибка", show_alert=True)


async def payment_confirmation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение оплаты пользователем"""
    query = update.callback_query
    
    # Формат: paid_card_premium или paid_crypto_premium
    parts = query.data.split('_')
    if len(parts) < 3:
        await query.answer("❌ Некорректные данные", show_alert=True)
        return
    
    payment_method = parts[1]  # card или crypto
    plan_id = parts[2]  # basic, pro, premium
    
    if plan_id not in SUBSCRIPTION_PLANS:
        await query.answer("❌ Тариф не найден", show_alert=True)
        return
    
    plan = SUBSCRIPTION_PLANS[plan_id]
    user_id = query.from_user.id
    
    # Создаём запись о платеже
    method_name = "Банковская карта" if payment_method == 'card' else "Криптовалюта"
    payment_id = db.create_payment(
        user_id=user_id,
        plan=plan_id,
        amount=plan['price'],
        payment_method=method_name
    )
    
    # Отправляем уведомление администратору
    admin_text = f"""
🔔 **Новая заявка на оплату!**

👤 Пользователь: {query.from_user.first_name} (@{query.from_user.username})
🆔 ID: {user_id}
📦 Тариф: {plan['name']}
💰 Сумма: {plan['price']} ₽
💳 Способ: {method_name}
🆔 Заявка: #{payment_id}

Ожидает подтверждения платежа.
"""
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f'approve_{payment_id}'),
            InlineKeyboardButton("❌ Отклонить", callback_data=f'reject_{payment_id}')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error sending admin notification: {e}")
    
    # Уведомляем пользователя
    text = f"""
✅ Заявка на оплату отправлена!

📦 Тариф: {plan['name']}
💰 Сумма: {plan['price']} ₽
💳 Способ: {method_name}
🆔 Номер заявки: #{payment_id}

⏳ Ваш платёж будет проверен администратором в течение 1-24 часов.
После подтверждения подписка будет активирована автоматически.

📧 Вы получите уведомление, когда платёж будет обработан.
"""
    
    keyboard = [
        [InlineKeyboardButton("◀️ В главное меню", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.message.edit_text(text, reply_markup=reply_markup)
        await query.answer("✅ Заявка отправлена администратору!")
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            await query.answer("✅ Заявка отправлена!")
        else:
            await query.message.reply_text(text, reply_markup=reply_markup)
            await query.answer("✅ Заявка отправлена!")

async def approve_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Одобрение платежа администратором"""
    query = update.callback_query
    
    # Проверяем права администратора
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Недостаточно прав", show_alert=True)
        return
    
    # Получаем ID платежа из callback_data
    payment_id = query.data.split('_')[1]
    
    # Получаем информацию о платеже
    payment = db.get_payment(payment_id)
    
    if not payment:
        await query.answer("❌ Платёж не найден", show_alert=True)
        return
    
    if payment['status'] != 'pending':
        await query.answer(f"⚠️ Платёж уже обработан: {payment['status']}", show_alert=True)
        return
    
    # Одобряем платёж
    success = db.approve_payment(payment_id, query.from_user.id)
    
    if success:
        # Обновляем сообщение администратора
        admin_text = f"""
✅ **Платёж одобрен!**

👤 Пользователь: {payment.get('first_name', 'N/A')} (@{payment.get('username', 'N/A')})
🆔 ID: {payment['user_id']}
📦 Тариф: {payment['plan']}
💰 Сумма: {payment['amount']} ₽
💳 Способ: {payment['payment_method']}
🆔 Заявка: #{payment_id}

✅ Подписка активирована
👤 Одобрил: @{query.from_user.username}
"""
        
        try:
            await query.message.edit_text(admin_text, parse_mode='Markdown')
        except:
            pass
        
        await query.answer("✅ Платёж одобрен, подписка активирована!")
        
        # Уведомляем пользователя
        user_text = f"""
🎉 **Отличные новости!**

Ваш платёж подтверждён, подписка активирована!

📦 Тариф: **{payment['plan']}**
💰 Сумма: {payment['amount']} ₽
🆔 Заявка: #{payment_id}

✨ Теперь вам доступны все возможности выбранного тарифа.
Используйте команду /start для начала работы.

Спасибо за покупку! 🚀
"""
        
        try:
            await context.bot.send_message(
                chat_id=payment['user_id'],
                text=user_text,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error notifying user about approved payment: {e}")
    else:
        await query.answer("❌ Ошибка одобрения платежа", show_alert=True)


async def reject_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отклонение платежа администратором"""
    query = update.callback_query
    
    # Проверяем права администратора
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Недостаточно прав", show_alert=True)
        return
    
    # Получаем ID платежа из callback_data
    payment_id = query.data.split('_')[1]
    
    # Получаем информацию о платеже
    payment = db.get_payment(payment_id)
    
    if not payment:
        await query.answer("❌ Платёж не найден", show_alert=True)
        return
    
    if payment['status'] != 'pending':
        await query.answer(f"⚠️ Платёж уже обработан: {payment['status']}", show_alert=True)
        return
    
    # Отклоняем платёж
    success = db.reject_payment(payment_id, query.from_user.id)
    
    if success:
        # Обновляем сообщение администратора
        admin_text = f"""
❌ **Платёж отклонён!**

👤 Пользователь: {payment.get('first_name', 'N/A')} (@{payment.get('username', 'N/A')})
🆔 ID: {payment['user_id']}
📦 Тариф: {payment['plan']}
💰 Сумма: {payment['amount']} ₽
💳 Способ: {payment['payment_method']}
🆔 Заявка: #{payment_id}

❌ Платёж отклонён
👤 Отклонил: @{query.from_user.username}
"""
        
        try:
            await query.message.edit_text(admin_text, parse_mode='Markdown')
        except:
            pass
        
        await query.answer("❌ Платёж отклонён")
        
        # Уведомляем пользователя
        user_text = f"""
😔 **К сожалению, ваш платёж отклонён**

📦 Тариф: {payment['plan']}
💰 Сумма: {payment['amount']} ₽
🆔 Заявка: #{payment_id}

❓ Возможные причины:
• Не поступила оплата
• Неверная сумма
• Технические проблемы

💬 Свяжитесь с поддержкой для уточнения: @starbombbotadmin

Вы можете попробовать оплатить снова.
"""
        
        try:
            await context.bot.send_message(
                chat_id=payment['user_id'],
                text=user_text,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error notifying user about rejected payment: {e}")
    else:
        await query.answer("❌ Ошибка отклонения платежа", show_alert=True)

async def paid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь подтвердил оплату"""
    query = update.callback_query
    payment_id = int(query.data.split('_')[1])
    
    payment = db.get_payment(payment_id)
    
    if not payment or payment['user_id'] != query.from_user.id:
        await query.answer("❌ Платёж не найден", show_alert=True)
        return
    
    if payment['status'] != 'pending':
        await query.answer("ℹ️ Платёж уже обработан", show_alert=True)
        return
    
    text = TEXTS['payment_pending'].format(
        amount=payment['amount'],
        plan=SUBSCRIPTION_PLANS[payment['plan']]['name']
    )
    
    await query.message.edit_text(text, reply_markup=get_back_button('subscriptions'), parse_mode='Markdown')
    await query.answer("✅ Ожидайте подтверждения")

# ==================== SCHEDULER ====================

async def scheduler_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Планировщик"""
    query = update.callback_query
    user_id = query.from_user.id
    
    # Проверяем подписку
    is_active, plan = check_subscription(user_id)
    if not is_active:
        await query.answer("❌ " + plan, show_alert=True)
        return
    
    schedules = db.get_user_schedules(user_id)
    active_count = len([s for s in schedules if s.get('is_active')])
    
    text = TEXTS['scheduler'].format(active_count=active_count)
    keyboard = get_scheduler_menu(has_schedules=len(schedules) > 0)
    
    await safe_edit_message(query, text, reply_markup=keyboard, parse_mode='Markdown')

async def list_schedules_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список расписаний"""
    query = update.callback_query
    user_id = query.from_user.id
    
    schedules = db.get_user_schedules(user_id)
    
    if not schedules:
        await query.answer("У вас нет расписаний", show_alert=True)
        return
    
    text = "📅 **Ваши расписания:**"
    keyboard = get_schedules_list(schedules)
    
    await safe_edit_message(query, text, reply_markup=keyboard, parse_mode='Markdown')

async def schedule_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о расписании"""
    query = update.callback_query
    schedule_id = int(query.data.split('_')[-1])
    
    schedule = db.get_schedule(schedule_id)
    
    if not schedule or schedule['user_id'] != query.from_user.id:
        await query.answer("❌ Расписание не найдено", show_alert=True)
        return
    
    status = "🟢 Активно" if schedule['is_active'] else "🔴 Приостановлено"
    
    text = f"""
📅 **{schedule.get('name', 'Расписание')}**

**Статус:** {status}
**Тип:** {schedule['schedule_type']}
**Время:** {schedule['schedule_time']}
**Последний запуск:** {schedule.get('last_run', 'Никогда')}
**Следующий запуск:** {schedule.get('next_run', 'Не запланирован')}
**Создано:** {schedule['created_at'][:16]}
"""
    
    keyboard = get_schedule_actions(schedule_id, schedule['is_active'])
    
    await safe_edit_message(query, text, reply_markup=keyboard, parse_mode='Markdown')

async def delete_schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление расписания"""
    query = update.callback_query
    schedule_id = int(query.data.split('_')[-1])
    user_id = query.from_user.id
    
    schedule = db.get_schedule(schedule_id)
    
    if not schedule or schedule['user_id'] != user_id:
        await query.answer("❌ Расписание не найдено", show_alert=True)
        return
    
    db.delete_schedule(schedule_id, user_id)
    
    await query.answer("✅ Расписание удалено", show_alert=True)
    
    # Возвращаемся к списку
    schedules = db.get_user_schedules(user_id)
    if schedules:
        await list_schedules_callback(update, context)
    else:
        await scheduler_callback(update, context)

# ==================== HISTORY ====================

async def history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """История рассылок"""
    query = update.callback_query
    user_id = query.from_user.id
    
    mailings = db.get_user_mailings(user_id, limit=10)
    total = len(mailings)
    
    today_mailings = [m for m in mailings if m['created_at'][:10] == datetime.now().strftime('%Y-%m-%d')]
    
    text = TEXTS['history'].format(
        total=total,
        today=len(today_mailings)
    )
    
    keyboard = get_history_menu()
    
    await safe_edit_message(query, text, reply_markup=keyboard, parse_mode='Markdown')

async def history_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Все рассылки"""
    query = update.callback_query
    user_id = query.from_user.id
    
    mailings = db.get_user_mailings(user_id, limit=20)
    
    if not mailings:
        await query.answer("У вас нет рассылок", show_alert=True)
        return
    
    text = "📜 **Все рассылки:**"
    keyboard = get_mailings_list(mailings)
    
    await safe_edit_message(query, text, reply_markup=keyboard, parse_mode='Markdown')

async def mailing_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о рассылке"""
    query = update.callback_query
    mailing_id = int(query.data.split('_')[-1])
    
    mailing = db.get_mailing(mailing_id)
    
    if not mailing or mailing['user_id'] != query.from_user.id:
        await query.answer("❌ Рассылка не найдена", show_alert=True)
        return
    
    status_emoji = STATUS_EMOJI.get(mailing['status'], '❓')
    status_text = {
        'pending': 'Ожидает запуска',
        'running': 'Выполняется',
        'completed': 'Завершена',
        'failed': 'Ошибка',
        'cancelled': 'Отменена',
        'paused': 'Приостановлена'
    }.get(mailing['status'], 'Неизвестно')
    
    progress = int((mailing['sent'] / mailing['total']) * 100) if mailing['total'] > 0 else 0
    
    text = f"""
📊 **Рассылка #{mailing_id}**

**Статус:** {status_emoji} {status_text}
**Прогресс:** {progress}%

📈 **Статистика:**
• Всего целей: {mailing['total']}
• Отправлено: {mailing['sent']}
• Ошибок: {mailing['errors']}

⏱ **Время:**
• Создана: {mailing['created_at'][:16]}
• Запущена: {mailing.get('started_at', 'Не запущена')[:16] if mailing.get('started_at') else 'Не запущена'}
• Завершена: {mailing.get('completed_at', 'Не завершена')[:16] if mailing.get('completed_at') else 'Не завершена'}

**Аккаунтов использовано:** {len(mailing['accounts'])}
"""
    
    keyboard = get_mailing_actions(mailing_id, mailing['status'])
    
    await safe_edit_message(query, text, reply_markup=keyboard, parse_mode='Markdown')

# ==================== ADMIN PANEL ====================

async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-панель"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    stats = db.get_statistics()
    
    text = TEXTS['admin_panel'].format(
        total_users=stats['total_users'],
        active_today=stats['active_today'],
        new_week=stats['new_this_week'],
        revenue_month=stats['revenue_month'],
        pending_payments=stats['pending_payments'],
        mailings_completed=stats['completed_mailings'],
        messages_sent=stats['total_messages_sent']
    )
    
    keyboard = get_admin_panel()
    
    await safe_edit_message(query, text, reply_markup=keyboard, parse_mode='Markdown')

async def admin_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление пользователями"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    text = "👥 **Управление пользователями**"
    keyboard = get_admin_users_menu()
    
    await safe_edit_message(query, text, reply_markup=keyboard, parse_mode='Markdown')

async def admin_payments_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление платежами"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    pending = db.get_pending_payments()
    
    text = "💰 **Управление платежами**"
    keyboard = get_admin_payments_menu(pending_count=len(pending))
    
    await safe_edit_message(query, text, reply_markup=keyboard, parse_mode='Markdown')

async def admin_payments_pending_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ожидающие платежи"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    payments = db.get_pending_payments()
    
    if not payments:
        await query.answer("✅ Нет ожидающих платежей", show_alert=True)
        return
    
    text = "⏳ **Ожидающие платежи:**\n\n"
    
    for payment in payments[:10]:  # Показываем первые 10
        plan_name = SUBSCRIPTION_PLANS[payment['plan']]['name']
        text += f"💳 **#{payment['id']}**\n"
        text += f"• User: {payment['first_name']} (@{payment['username']})\n"
        text += f"• Тариф: {plan_name}\n"
        text += f"• Сумма: {payment['amount']} ₽\n"
        text += f"• Дата: {payment['created_at'][:16]}\n\n"
    
    # Показываем кнопки для первого платежа
    if payments:
        keyboard = get_payment_actions(payments[0]['id'])
    else:
        keyboard = get_back_button('admin_payments')
    
    await safe_edit_message(query, text, reply_markup=keyboard, parse_mode='Markdown')

async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    stats = db.get_statistics()
    
    # Статистика по тарифам
    plans_stats = ""
    for plan_id, count in stats.get('users_by_plan', {}).items():
        plan_name = SUBSCRIPTION_PLANS.get(plan_id, {}).get('name', plan_id)
        plans_stats += f"• {plan_name}: {count}\n"
    
    text = f"""
📊 **Детальная статистика**

👥 **Пользователи:**
• Всего: {stats['total_users']}
• Активных сегодня: {stats['active_today']}
• Новых за неделю: {stats['new_this_week']}

💎 **По тарифам:**
{plans_stats}

📨 **Рассылки:**
• Всего: {stats['total_mailings']}
• Завершено: {stats['completed_mailings']}
• Сообщений отправлено: {stats['total_messages_sent']}

💰 **Финансы:**
• Доход за месяц: {stats['revenue_month']} ₽
• Ожидает оплаты: {stats['pending_payments']}
"""
    
    keyboard = get_back_button('admin_panel')
    
    await safe_edit_message(query, text, reply_markup=keyboard, parse_mode='Markdown')

async def admin_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Резервные копии"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    await query.answer("⏳ Создаю резервную копию...", show_alert=True)
    
    # Создаём бэкап
    backup_path = backup_manager.create_backup()
    
    if backup_path:
        # Отправляем файл
        try:
            await context.bot.send_document(
                query.from_user.id,
                document=open(backup_path, 'rb'),
                caption=f"💾 Резервная копия базы данных\n{backup_path.name}"
            )
        except Exception as e:
            logger.error(f"Error sending backup: {e}")
            await query.message.reply_text(f"❌ Ошибка отправки файла: {str(e)}")
    else:
        await query.message.reply_text("❌ Ошибка создания резервной копии")

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало рассылки всем пользователям"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return ConversationHandler.END
    
    await query.message.edit_text(
        "📢 **Рассылка всем пользователям**\n\n"
        "Отправьте сообщение которое хотите разослать:\n\n"
        "❌ Отмена: /cancel",
        reply_markup=get_cancel_button()
    )
    await query.answer()
    
    return ADMIN_BROADCAST_MESSAGE

async def admin_broadcast_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получено сообщение для админ-рассылки"""
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    
    message_text = update.message.text
    
    # Получаем всех активных пользователей
    users = db.get_all_users(active_only=True)
    
    await update.message.reply_text(
        f"📢 Начинаю рассылку {len(users)} пользователям...",
        reply_markup=get_main_menu(is_admin=True)
    )
    
    # Рассылаем
    sent = 0
    errors = 0
    
    for user in users:
        try:
            await context.bot.send_message(
                user['telegram_id'],
                message_text,
                parse_mode='Markdown'
            )
            sent += 1
            await asyncio.sleep(0.05)  # Небольшая задержка между отправками
        except Exception as e:
            errors += 1
            logger.error(f"Error broadcasting to {user['telegram_id']}: {e}")
    
    # Отчёт
    await update.message.reply_text(
        f"✅ **Рассылка завершена**\n\n"
        f"• Отправлено: {sent}\n"
        f"• Ошибок: {errors}",
        parse_mode='Markdown'
    )
    
    return ConversationHandler.END

async def admin_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Назад к админ-панели"""
    await admin_panel_callback(update, context)

# ==================== OTHER CALLBACKS ====================

async def back_to_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Назад в главное меню"""
    await main_menu_callback(update, context)

# ==================== TEXT HANDLER ====================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    text = update.message.text
    user_id = update.effective_user.id
    
    # Логируем
    logger.info(f"Text from {user_id}: {text}")
    
    # Отправляем в главное меню
    await start(update, context)

# ==================== DEBUG ====================

async def debug_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Логирование всех callback'ов для отладки"""
    if update.callback_query:
        query = update.callback_query
        logger.info("=" * 60)
        logger.info(f"🔘 CALLBACK RECEIVED:")
        logger.info(f"   User ID: {query.from_user.id}")
        logger.info(f"   Username: @{query.from_user.username}")
        logger.info(f"   Callback Data: '{query.data}'")
        logger.info(f"   Message ID: {query.message.message_id}")
        logger.info("=" * 60)

# ==================== ERROR HANDLER ====================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    error = context.error
    
    # Игнорируем некритичные ошибки
    if isinstance(error, telegram.error.BadRequest):
        if "message is not modified" in str(error).lower():
            # Сообщение не изменилось - это не ошибка
            logger.debug(f"Message not modified (ignored): {error}")
            return
        elif "message to edit not found" in str(error).lower():
            logger.debug(f"Message to edit not found (ignored): {error}")
            return
        elif "query is too old" in str(error).lower():
            logger.debug(f"Query too old (ignored): {error}")
            if update and update.callback_query:
                try:
                    await update.callback_query.answer("⚠️ Запрос устарел, попробуйте снова")
                except:
                    pass
            return
    
    # Логируем серьёзные ошибки
    logger.error(f"Update {update} caused error {error}", exc_info=error)
    
    try:
        if update and update.effective_user:
            error_text = "❌ Произошла ошибка. Попробуйте позже или обратитесь в поддержку."
            
            if update.callback_query:
                try:
                    await update.callback_query.answer(error_text, show_alert=True)
                except:
                    await context.bot.send_message(update.effective_user.id, error_text)
            elif update.message:
                await update.message.reply_text(error_text)
            else:
                await context.bot.send_message(update.effective_user.id, error_text)
    except Exception as e:
        logger.error(f"Error in error_handler: {e}")

# ==================== MAIN ====================

def main():
    """Запуск бота"""
    logger.info("=" * 50)
    logger.info("🚀 Starting Telegram Bot Manager...")
    logger.info("=" * 50)
    
    # Создаём приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем debug handler (первым с группой -1)
    application.add_handler(CallbackQueryHandler(debug_callback_handler), group=-1)
    
    # Планировщик
    global scheduler
    scheduler = MailingScheduler(db, userbot_manager, application.bot)
    
    # Функция для запуска async задач после старта бота
    async def post_init(application):
        """Запускается после инициализации бота"""
        # Запускаем проверку расписаний
        scheduler.start_checking()
        
        # Запускаем автобэкап
        async def auto_backup():
            while True:
                await asyncio.sleep(24 * 60 * 60)  # 24 часа
                logger.info("🔄 Creating automatic backup...")
                backup_manager.create_backup()
        
        asyncio.create_task(auto_backup())
        logger.info("✅ Background tasks started")
    
    # Добавляем post_init callback
    application.post_init = post_init
    
    # ==================== КОМАНДЫ ====================
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("admin", admin_panel))
    
    # ==================== CONVERSATION HANDLERS ====================
    
    # ConversationHandler для подключения аккаунта
    connect_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(connect_account_callback, pattern="^connect_account$")
        ],
        states={
            CONNECT_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, connect_phone_received)
            ],
            CONNECT_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, connect_code_received)
            ],
            CONNECT_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, connect_password_received)
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(cancel_connect_callback, pattern="^cancel_connect$")
        ],
        per_message=False,
        allow_reentry=True
    )
    application.add_handler(connect_conv)
    
    # ConversationHandler для создания рассылки
    mailing_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(create_mailing_start, pattern='^create_mailing$')
        ],
        states={
            MAILING_RECIPIENTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, mailing_recipients)
            ],
            MAILING_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, mailing_message)
            ],
            MAILING_CONFIRM: [
                CallbackQueryHandler(mailing_confirm, pattern='^confirm_mailing$'),
                CallbackQueryHandler(mailing_cancel, pattern='^cancel_mailing$')
            ],
            MAILING_ACCOUNT: [
                CallbackQueryHandler(mailing_select_account, pattern='^mailing_account_')
            ]
        },
        fallbacks=[
            CallbackQueryHandler(mailing_cancel, pattern='^cancel_mailing$'),
            CommandHandler('cancel', mailing_cancel)
        ],
        per_message=False,
        per_chat=True,
        per_user=True,
        allow_reentry=True
    )
    application.add_handler(mailing_conv)
    
    # ConversationHandler для админ-рассылки
    admin_broadcast_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast$")
        ],
        states={
            ADMIN_BROADCAST_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_message_received)
            ],
            ADMIN_BROADCAST_CONFIRM: [
                CallbackQueryHandler(admin_broadcast_confirm, pattern='^confirm_broadcast$'),
                CallbackQueryHandler(admin_broadcast_cancel, pattern='^cancel_broadcast$')
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(admin_broadcast_cancel, pattern='^cancel_broadcast$')
        ],
        allow_reentry=True
    )
    application.add_handler(admin_broadcast_conv)
    
    # ==================== PAYMENT HANDLERS ====================
    application.add_handler(CallbackQueryHandler(
        payment_method_callback, 
        pattern='^pay_(card|crypto)_'
    ))
    
    application.add_handler(CallbackQueryHandler(
        payment_confirmation_callback, 
        pattern='^paid_(card|crypto)_'
    ))
    
    # ==================== ADMIN PAYMENT HANDLERS ====================
    application.add_handler(CallbackQueryHandler(
        approve_payment_callback, 
        pattern='^approve_[0-9]+$'
    ))
    
    application.add_handler(CallbackQueryHandler(
        reject_payment_callback, 
        pattern='^reject_[0-9]+$'
    ))
    
    # ==================== CALLBACK HANDLERS ====================
    
    # Главное меню
    application.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(my_accounts_callback, pattern="^my_accounts$"))
    application.add_handler(CallbackQueryHandler(mailings_callback, pattern="^mailings$"))
    application.add_handler(CallbackQueryHandler(scheduler_callback, pattern="^scheduler$"))
    application.add_handler(CallbackQueryHandler(history_callback, pattern="^history$"))
    application.add_handler(CallbackQueryHandler(subscriptions_callback, pattern="^subscriptions$"))
    application.add_handler(CallbackQueryHandler(help_callback, pattern="^help$"))
    
    # Управление аккаунтами
    application.add_handler(CallbackQueryHandler(manage_accounts_callback, pattern="^manage_accounts$"))
    application.add_handler(CallbackQueryHandler(account_info_callback, pattern="^account_info_"))
    application.add_handler(CallbackQueryHandler(disconnect_account_callback, pattern="^disconnect_account_"))
    application.add_handler(CallbackQueryHandler(confirm_disconnect_callback, pattern="^confirm_disconnect_"))
    application.add_handler(CallbackQueryHandler(accounts_back_callback, pattern="^accounts_back$"))
    
    # Подписки
    application.add_handler(CallbackQueryHandler(buy_subscription_callback, pattern="^buy_"))
    
    # Планировщик
    application.add_handler(CallbackQueryHandler(create_schedule_callback, pattern="^create_schedule$"))
    application.add_handler(CallbackQueryHandler(list_schedules_callback, pattern="^list_schedules$"))
    application.add_handler(CallbackQueryHandler(schedule_info_callback, pattern="^schedule_info_"))
    application.add_handler(CallbackQueryHandler(delete_schedule_callback, pattern="^delete_schedule_"))
    application.add_handler(CallbackQueryHandler(confirm_delete_schedule_callback, pattern="^confirm_delete_schedule_"))
    
    # История
    application.add_handler(CallbackQueryHandler(history_all_callback, pattern="^history_all$"))
    application.add_handler(CallbackQueryHandler(mailing_info_callback, pattern="^mailing_info_"))
    
    # Админ панель
    application.add_handler(CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$"))
    application.add_handler(CallbackQueryHandler(admin_users_callback, pattern="^admin_users$"))
    application.add_handler(CallbackQueryHandler(admin_user_info_callback, pattern="^admin_user_"))
    application.add_handler(CallbackQueryHandler(admin_payments_callback, pattern="^admin_payments$"))
    application.add_handler(CallbackQueryHandler(admin_payments_pending_callback, pattern="^admin_payments_pending$"))
    application.add_handler(CallbackQueryHandler(admin_stats_callback, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(admin_backup_callback, pattern="^admin_backup$"))
    application.add_handler(CallbackQueryHandler(create_backup_callback, pattern="^create_backup$"))
    application.add_handler(CallbackQueryHandler(admin_back_callback, pattern="^admin_back$"))
    
    # Общие
    application.add_handler(CallbackQueryHandler(back_to_menu_callback, pattern="^back_to_menu$"))
    
    # Общий обработчик callback (ДОЛЖЕН БЫТЬ ПОСЛЕДНИМ!)
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Текстовые сообщения
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запуск
    logger.info("🤖 Bot starting polling...")
    logger.info(f"Bot Token: {BOT_TOKEN[:10]}...")
    logger.info(f"Admin ID: {ADMIN_ID}")
    logger.info("=" * 50)
    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
    finally:
        # Очистка
        logger.info("🧹 Cleaning up...")
        asyncio.run(userbot_manager.disconnect_all())
        if scheduler:
            scheduler.shutdown()
        backup_manager.shutdown()
        logger.info("✅ Cleanup complete")


if __name__ == '__main__':
    main()