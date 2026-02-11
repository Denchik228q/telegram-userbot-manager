#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Bot Manager - Главный файл бота
"""

import os
import logging
import asyncio
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)

# Импорты модулей
from config import BOT_TOKEN, ADMIN_ID, SUBSCRIPTION_PLANS, TEXTS, BACKUP_ENABLED, BACKUP_INTERVAL_HOURS, BACKUP_CHAT_ID
from database import Database
from userbot_core import UserbotManager
from scheduler import MailingScheduler
from backup_manager import BackupManager
from utils import *
from keyboards import *

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация компонентов
db = Database()
userbot_manager = UserbotManager(db)
scheduler = None

# Бэкап менеджер (если включен)
backup_manager = None
if BACKUP_ENABLED:
    backup_manager = BackupManager(db, BOT_TOKEN, BACKUP_CHAT_ID, BACKUP_INTERVAL_HOURS)

# Состояния для ConversationHandler
# Подключение аккаунта
PHONE, CODE, PASSWORD = range(3)

# Создание рассылки
MAILING_TARGETS, MAILING_ACCOUNTS, MAILING_MESSAGE, MAILING_CONFIRM = range(3, 7)

# Создание расписания
SCHEDULE_NAME, SCHEDULE_TARGETS, SCHEDULE_ACCOUNTS, SCHEDULE_MESSAGE, SCHEDULE_TYPE, SCHEDULE_TIME = range(7, 13)

# Админ-рассылка
ADMIN_BROADCAST_MESSAGE = 13


# ==================== ОСНОВНЫЕ КОМАНДЫ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    
    # ✅ ПРАВИЛЬНО: передаём параметры отдельно
    db.add_user(user.id, user.username, user.first_name, user.last_name)
    
    # Логируем действие
    db.add_log(user.id, 'start', 'User started bot')
    
    # Получаем данные пользователя
    user_data = db.get_user(user.id)
    
    # Проверка на None
    if not user_data:
        user_data = {'subscription_plan': 'trial', 'subscription_end': None}
    
    # Проверяем подписку
    plan_id = user_data.get('subscription_plan', 'trial')
    plan = SUBSCRIPTION_PLANS.get(plan_id, SUBSCRIPTION_PLANS['trial'])
    
    is_active = check_subscription(user_data)
    days_left = get_days_left(user_data)
    
    subscription_text = f"{plan['name']} ({'✅ активна' if is_active else '❌ истекла'})"
    
    # Формируем приветствие
    welcome_text = TEXTS['welcome'].format(
        subscription=subscription_text,
        days_left=days_left
    )
    
    # Определяем является ли админом
    is_admin = (user.id == ADMIN_ID)
    
    # Отправляем приветствие
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=get_main_menu(is_admin)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    await update.message.reply_text(
        TEXTS['help'],
        parse_mode='Markdown'  # ← Проблема в TEXTS['help']
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
    await update.message.reply_text(
        "❌ Операция отменена",
        reply_markup=get_main_menu(update.effective_user.id == ADMIN_ID)
    )
    return ConversationHandler.END


# ==================== ПОДКЛЮЧЕНИЕ АККАУНТА ====================

async def connect_userbot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало подключения аккаунта"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    # Проверяем подписку
    if not check_subscription(user_data):
        await update.message.reply_text(
            "❌ Ваша подписка истекла. Пожалуйста, продлите подписку для подключения аккаунтов.",
            reply_markup=get_subscription_menu()
        )
        return ConversationHandler.END
    
    # Проверяем лимит аккаунтов
    accounts_count = len(db.get_user_accounts(user_id))
    allowed, limit = check_limit(user_data, 'accounts', accounts_count)
    
    if not allowed:
        await update.message.reply_text(
            f"⚠️ Вы достигли лимита аккаунтов ({limit}).\n\n"
            "Для подключения большего количества аккаунтов перейдите на более высокий тариф.",
            reply_markup=get_subscription_menu()
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📱 *Подключение аккаунта Telegram*\n\n"
        "Введите номер телефона в международном формате:\n"
        "Например: +79991234567\n\n"
        "Для отмены используйте /cancel",
        parse_mode='Markdown'
    )
    
    return PHONE


async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен номер телефона"""
    phone = update.message.text.strip()
    
    # Валидация номера
    is_valid, formatted_phone = validate_phone(phone)
    if not is_valid:
        await update.message.reply_text(
            "❌ Неверный формат номера телефона.\n"
            "Пожалуйста, введите номер в международном формате.\n"
            "Например: +79991234567"
        )
        return PHONE
    
    # Сохраняем номер
    context.user_data['phone'] = formatted_phone
    context.user_data['session_name'] = f"session_{update.effective_user.id}_{int(datetime.now().timestamp())}"
    
    await update.message.reply_text(
        "⏳ Отправляю код подтверждения...",
    )
    
    # Подключаем аккаунт
    client, phone_code_hash, error = await userbot_manager.connect_account(
        formatted_phone, 
        context.user_data['session_name']
    )
    
    if error:
        await update.message.reply_text(
            f"{error}\n\nПопробуйте ещё раз или используйте /cancel"
        )
        return PHONE
    
    # Сохраняем данные
    context.user_data['client'] = client
    context.user_data['phone_code_hash'] = phone_code_hash
    
    await update.message.reply_text(
        "✅ Код отправлен!\n\n"
        "📩 Введите код подтверждения из Telegram:\n"
        "(Формат: 12345 или 1-2-3-4-5)"
    )
    
    return CODE


async def code_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен код подтверждения"""
    code = update.message.text.strip().replace('-', '').replace(' ', '')
    
    # Проверяем код
    client = context.user_data.get('client')
    phone = context.user_data.get('phone')
    phone_code_hash = context.user_data.get('phone_code_hash')
    
    if not all([client, phone, phone_code_hash]):
        await update.message.reply_text(
            "❌ Ошибка: данные сессии потеряны. Начните заново с /start"
        )
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ Проверяю код...")
    
    success, needs_password, error = await userbot_manager.verify_code(
        client, phone, code, phone_code_hash
    )
    
    if error:
        await update.message.reply_text(
            f"{error}\n\nПопробуйте ещё раз или используйте /cancel"
        )
        return CODE
    
    if needs_password:
        await update.message.reply_text(
            "🔐 *Двухфакторная аутентификация включена*\n\n"
            "Введите ваш облачный пароль (2FA):",
            parse_mode='Markdown'
        )
        return PASSWORD
    
    # Успешная авторизация
    return await finalize_account_connection(update, context)


async def password_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен 2FA пароль"""
    password = update.message.text.strip()
    
    # Удаляем сообщение с паролем
    try:
        await update.message.delete()
    except:
        pass
    
    client = context.user_data.get('client')
    
    await update.effective_chat.send_message("⏳ Проверяю пароль...")
    
    success, error = await userbot_manager.verify_password(client, password)
    
    if error:
        await update.effective_chat.send_message(
            f"{error}\n\nПопробуйте ещё раз или используйте /cancel"
        )
        return PASSWORD
    
    # Успешная авторизация
    return await finalize_account_connection(update, context)


async def finalize_account_connection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение подключения аккаунта"""
    client = context.user_data.get('client')
    phone = context.user_data.get('phone')
    session_name = context.user_data.get('session_name')
    
    # Получаем информацию об аккаунте
    info = await userbot_manager.get_account_info(client)
    
    if not info:
        await update.effective_chat.send_message(
            "❌ Ошибка получения информации об аккаунте"
        )
        return ConversationHandler.END
    
    # Сохраняем в БД
    account_name = f"{info['first_name']} {info['last_name']}".strip() or info['username'] or phone
    
    account_id = db.add_account(
        user_id=update.effective_user.id,
        phone=phone,
        session_id=session_name,
        account_name=account_name,
        first_name=info['first_name'],
        last_name=info['last_name'],
        username=info['username']
    )
    
    if account_id:
        await update.effective_chat.send_message(
            f"✅ *Аккаунт успешно подключен!*\n\n"
            f"Имя: {info['first_name']} {info['last_name']}\n"
            f"Username: @{info['username']}\n"
            f"Телефон: {phone}\n\n"
            f"Теперь вы можете использовать этот аккаунт для рассылок.",
            parse_mode='Markdown',
            reply_markup=get_main_menu(update.effective_user.id == ADMIN_ID)
        )
    else:
        await update.effective_chat.send_message(
            "❌ Ошибка сохранения аккаунта в базу данных"
        )
    
    # Очищаем данные
    context.user_data.clear()
    
    return ConversationHandler.END


# ==================== УПРАВЛЕНИЕ АККАУНТАМИ ====================

async def my_accounts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки "Мои аккаунты" """
    await update.message.reply_text(
        "📱 *Управление аккаунтами*\n\n"
        "Выберите действие:",
        parse_mode='Markdown',
        reply_markup=get_accounts_menu()
    )


async def list_accounts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список аккаунтов"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    accounts = db.get_user_accounts(user_id)
    
    if not accounts:
        await query.edit_message_text(
            TEXTS['no_accounts'],
            parse_mode='Markdown',
            reply_markup=get_accounts_menu()
        )
        return
    
    text = "📱 *Ваши подключенные аккаунты:*\n\n"
    
    keyboard = []
    for account in accounts:
        name = account.get('account_name', f"Account {account['id']}")
        phone = account.get('phone', 'Не указан')
        
        text += f"• {name} ({phone})\n"
        keyboard.append([InlineKeyboardButton(
            f"📱 {name}",
            callback_data=f"account_info_{account['id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("➕ Подключить новый", callback_data="connect_account")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def account_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать информацию об аккаунте"""
    query = update.callback_query
    await query.answer()
    
    account_id = int(query.data.split('_')[-1])
    account = db.get_account(account_id)
    
    if not account:
        await query.edit_message_text(
            "❌ Аккаунт не найден",
            reply_markup=get_accounts_menu()
        )
        return
    
    info_text = format_account_info(account)
    
    await query.edit_message_text(
        info_text,
        parse_mode='Markdown',
        reply_markup=get_account_actions(account_id)
    )


async def delete_account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить аккаунт"""
    query = update.callback_query
    await query.answer()
    
    account_id = int(query.data.split('_')[-1])
    
    if db.delete_account(account_id):
        await query.edit_message_text(
            "✅ Аккаунт успешно удалён",
            reply_markup=get_accounts_menu()
        )
    else:
        await query.edit_message_text(
            "❌ Ошибка удаления аккаунта",
            reply_markup=get_accounts_menu()
        )


# ==================== СОЗДАНИЕ РАССЫЛКИ ====================

async def create_mailing_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания рассылки"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    # Проверяем подписку
    if not check_subscription(user_data):
        await update.message.reply_text(
            "❌ Ваша подписка истекла. Пожалуйста, продлите подписку.",
            reply_markup=get_subscription_menu()
        )
        return ConversationHandler.END
    
    # Проверяем наличие аккаунтов
    accounts = db.get_user_accounts(user_id)
    if not accounts:
        await update.message.reply_text(
            TEXTS['no_accounts'],
            parse_mode='Markdown',
            reply_markup=get_accounts_menu()
        )
        return ConversationHandler.END
    
    # Проверяем лимит рассылок за сегодня
    mailings_today = db.count_user_mailings_today(user_id)
    allowed, limit = check_limit(user_data, 'mailings_per_day', mailings_today)
    
    if not allowed:
        await update.message.reply_text(
            f"⚠️ Вы достигли дневного лимита рассылок ({limit}).\n\n"
            "Для увеличения лимитов перейдите на более высокий тариф.",
            reply_markup=get_subscription_menu()
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📨 *Создание новой рассылки*\n\n"
        "Шаг 1/3: Введите список целей для рассылки\n\n"
        "Формат: по одному username или номеру телефона на строку\n\n"
        "Пример:\n"
        "@username1\n"
        "+79991234567\n"
        "@username2\n\n"
        "Для отмены используйте /cancel",
        parse_mode='Markdown'
    )
    
    return MAILING_TARGETS


async def mailing_targets_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен список целей"""
    targets_text = update.message.text.strip()
    
    # Парсим цели
    targets = parse_targets(targets_text)
    
    if not targets:
        await update.message.reply_text(
            "❌ Не удалось распознать цели. Попробуйте ещё раз."
        )
        return MAILING_TARGETS
    
    # Проверяем лимит целей
    user_data = db.get_user(update.effective_user.id)
    allowed, limit = check_limit(user_data, 'targets_per_mailing', len(targets))
    
    if not allowed:
        await update.message.reply_text(
            f"⚠️ Слишком много целей ({len(targets)}).\n"
            f"Ваш лимит: {limit} целей на рассылку.\n\n"
            "Для увеличения лимитов перейдите на более высокий тариф.",
            reply_markup=get_subscription_menu()
        )
        return MAILING_TARGETS
    
    # Сохраняем
    context.user_data['mailing_targets'] = targets_text
    context.user_data['mailing_targets_count'] = len(targets)
    
    # Показываем выбор аккаунтов
    accounts = db.get_user_accounts(update.effective_user.id)
    context.user_data['selected_accounts'] = []
    
    await update.message.reply_text(
        f"✅ Целей распознано: {len(targets)}\n\n"
        f"Шаг 2/3: Выберите аккаунты для рассылки:",
        reply_markup=get_account_selection(accounts, [])
    )
    
    return MAILING_ACCOUNTS


async def toggle_account_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключить выбор аккаунта"""
    query = update.callback_query
    await query.answer()
    
    account_id = int(query.data.split('_')[-1])
    
    selected = context.user_data.get('selected_accounts', [])
    
    if account_id in selected:
        selected.remove(account_id)
    else:
        selected.append(account_id)
    
    context.user_data['selected_accounts'] = selected
    
    # Обновляем клавиатуру
    accounts = db.get_user_accounts(update.effective_user.id)
    
    await query.edit_message_reply_markup(
        reply_markup=get_account_selection(accounts, selected)
    )


async def continue_with_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Продолжить с выбранными аккаунтами"""
    query = update.callback_query
    await query.answer()
    
    selected = context.user_data.get('selected_accounts', [])
    
    if not selected:
        await query.answer("⚠️ Выберите хотя бы один аккаунт", show_alert=True)
        return MAILING_ACCOUNTS
    
    await query.edit_message_text(
                f"✅ Выбрано аккаунтов: {len(selected)}\n\n"
        f"Шаг 3/3: Введите текст сообщения для рассылки:\n\n"
        f"💡 Вы можете отправить фото, видео или документ с подписью.",
        parse_mode='Markdown'
    )
    
    return MAILING_MESSAGE


async def mailing_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен текст сообщения"""
    message = update.message
    
    # Сохраняем текст
    if message.text:
        context.user_data['mailing_message'] = message.text
        context.user_data['media_type'] = None
        context.user_data['media_path'] = None
    
    # Или медиа с подписью
    elif message.photo:
        context.user_data['mailing_message'] = message.caption or ''
        context.user_data['media_type'] = 'photo'
        # Скачиваем файл
        file = await message.photo[-1].get_file()
        file_path = f"media/photo_{update.effective_user.id}_{int(datetime.now().timestamp())}.jpg"
        os.makedirs('media', exist_ok=True)
        await file.download_to_drive(file_path)
        context.user_data['media_path'] = file_path
    
    elif message.video:
        context.user_data['mailing_message'] = message.caption or ''
        context.user_data['media_type'] = 'video'
        file = await message.video.get_file()
        file_path = f"media/video_{update.effective_user.id}_{int(datetime.now().timestamp())}.mp4"
        os.makedirs('media', exist_ok=True)
        await file.download_to_drive(file_path)
        context.user_data['media_path'] = file_path
    
    elif message.document:
        context.user_data['mailing_message'] = message.caption or ''
        context.user_data['media_type'] = 'document'
        file = await message.document.get_file()
        file_path = f"media/doc_{update.effective_user.id}_{int(datetime.now().timestamp())}"
        os.makedirs('media', exist_ok=True)
        await file.download_to_drive(file_path)
        context.user_data['media_path'] = file_path
    
    else:
        await message.reply_text(
            "❌ Неподдерживаемый тип сообщения. Отправьте текст, фото, видео или документ."
        )
        return MAILING_MESSAGE
    
    # Формируем предпросмотр
    targets_count = context.user_data.get('mailing_targets_count', 0)
    accounts_count = len(context.user_data.get('selected_accounts', []))
    msg_text = context.user_data.get('mailing_message', '')
    media_type = context.user_data.get('media_type')
    
    preview = f"""
📨 *Предпросмотр рассылки*

📊 Целей: {targets_count}
📱 Аккаунтов: {accounts_count}
"""
    
    if media_type:
        preview += f"📎 Медиа: {media_type}\n"
    
    preview += f"\n📝 Текст:\n{msg_text[:200]}{'...' if len(msg_text) > 200 else ''}\n\n"
    preview += "❓ Запустить рассылку?"
    
    await message.reply_text(
        preview,
        parse_mode='Markdown',
        reply_markup=get_confirm_mailing()
    )
    
    return MAILING_CONFIRM


async def confirm_mailing_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение и запуск рассылки"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Получаем данные
    targets_text = context.user_data.get('mailing_targets')
    message_text = context.user_data.get('mailing_message')
    selected_accounts = context.user_data.get('selected_accounts', [])
    media_type = context.user_data.get('media_type')
    media_path = context.user_data.get('media_path')
    
    # Создаём запись в БД
    accounts_str = ','.join(map(str, selected_accounts))
    
    mailing_id = db.add_mailing(
        user_id=user_id,
        targets=targets_text,
        message=message_text,
        accounts_used=accounts_str,
        media_type=media_type,
        media_path=media_path
    )
    
    if not mailing_id:
        await query.edit_message_text(
            "❌ Ошибка создания рассылки",
            reply_markup=get_main_menu(user_id == ADMIN_ID)
        )
        context.user_data.clear()
        return ConversationHandler.END
    
    await query.edit_message_text(
        f"⏳ Запускаю рассылку #{mailing_id}...\n\n"
        "Вы получите уведомление о завершении."
    )
    
    # Запускаем рассылку в фоне
    asyncio.create_task(execute_mailing(mailing_id, context.application.bot, user_id))
    
    # Очищаем данные
    context.user_data.clear()
    
    return ConversationHandler.END


async def cancel_mailing_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена рассылки"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "❌ Рассылка отменена",
        reply_markup=get_main_menu(update.effective_user.id == ADMIN_ID)
    )
    
    context.user_data.clear()
    return ConversationHandler.END


async def execute_mailing(mailing_id: int, bot, user_id: int):
    """Выполнение рассылки (асинхронная задача)"""
    try:
        logger.info(f"🚀 Starting mailing {mailing_id}")
        
        # Получаем данные рассылки
        mailing = db.get_user_mailings(user_id, limit=1000)
        mailing_data = None
        for m in mailing:
            if m['id'] == mailing_id:
                mailing_data = m
                break
        
        if not mailing_data:
            logger.error(f"Mailing {mailing_id} not found")
            return
        
        # Обновляем статус
        db.update_mailing_status(mailing_id, 'running')
        
        # Парсим данные
        targets = parse_targets(mailing_data['targets'])
        message = mailing_data['message']
        account_ids = list(map(int, mailing_data['accounts_used'].split(',')))
        media_path = mailing_data.get('media_path')
        
        success_count = 0
        error_count = 0
        
        # Отправляем сообщения
        for i, target in enumerate(targets):
            target = target.strip()
            if not target:
                continue
            
            # Выбираем аккаунт по очереди
            account_id = account_ids[i % len(account_ids)]
            
            # Получаем клиент
            client = await userbot_manager.get_client(account_id)
            if not client:
                logger.error(f"Client {account_id} not available")
                error_count += 1
                continue
            
            # Отправляем
            success, error = await userbot_manager.send_message(
                client, target, message, media_path
            )
            
            if success:
                success_count += 1
                logger.info(f"  ✅ Sent to {target} via account {account_id}")
            else:
                error_count += 1
                logger.warning(f"  ❌ Failed to send to {target}: {error}")
            
            # Обновляем статус аккаунта
            db.update_account_usage(account_id)
            
            # Задержка между отправками (3-5 секунд)
            await asyncio.sleep(3)
        
        # Обновляем статус рассылки
        status = 'completed' if success_count > 0 else 'failed'
        db.update_mailing_status(mailing_id, status, success_count, error_count)
        
        # Уведомляем пользователя
        result_text = f"""
✅ *Рассылка #{mailing_id} завершена!*

📊 Статистика:
• Успешно: {success_count}
• Ошибок: {error_count}
• Всего: {len(targets)}
"""
        
        await bot.send_message(
            chat_id=user_id,
            text=result_text,
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ Mailing {mailing_id} completed: {success_count}/{len(targets)}")
        
    except Exception as e:
        logger.error(f"Error executing mailing {mailing_id}: {e}")
        db.update_mailing_status(mailing_id, 'failed', 0, len(targets))
        
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"❌ Рассылка #{mailing_id} завершилась с ошибкой:\n{str(e)}"
            )
        except:
            pass


# ==================== ИСТОРИЯ РАССЫЛОК ====================

async def history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать историю рассылок"""
    user_id = update.effective_user.id
    mailings = db.get_user_mailings(user_id, limit=10)
    
    if not mailings:
        await update.message.reply_text(
            "📜 У вас пока нет рассылок\n\n"
            "Создайте первую рассылку, нажав *📨 Создать рассылку*",
            parse_mode='Markdown'
        )
        return
    
    text = "📜 *Ваши последние рассылки:*\n\n"
    
    for mailing in mailings[:10]:
        info = format_mailing_info(mailing)
        text += info + "\n" + "—"*30 + "\n"
    
    await update.message.reply_text(
        text,
        parse_mode='Markdown'
    )


# ==================== ПЛАНИРОВЩИК ====================

async def scheduler_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню планировщика"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    # Проверяем подписку
    if not check_subscription(user_data):
        await update.message.reply_text(
            "❌ Ваша подписка истекла. Планировщик доступен только для подписчиков.",
            reply_markup=get_subscription_menu()
        )
        return
    
    schedules = db.get_user_schedules(user_id)
    
    keyboard = [
        [InlineKeyboardButton("➕ Создать расписание", callback_data="create_schedule")],
        [InlineKeyboardButton("📋 Мои расписания", callback_data="list_schedules")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
    ]
    
    await update.message.reply_text(
        f"⏰ *Планировщик рассылок*\n\n"
        f"Активных расписаний: {len(schedules)}\n\n"
        f"Выберите действие:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def list_schedules_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список расписаний"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    schedules = db.get_user_schedules(user_id)
    
    if not schedules:
        await query.edit_message_text(
            "📋 У вас пока нет активных расписаний\n\n"
            "Создайте первое расписание!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Создать", callback_data="create_schedule")
            ], [
                InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")
            ]])
        )
        return
    
    text = "📋 *Ваши расписания:*\n\n"
    keyboard = []
    
    for schedule in schedules:
        name = schedule['name']
        schedule_type = "📅 Ежедневно" if schedule['schedule_type'] == 'daily' else "📆 Еженедельно"
        schedule_time = schedule['schedule_time']
        
        text += f"• {name} ({schedule_type} в {schedule_time})\n"
        keyboard.append([InlineKeyboardButton(
            f"⏰ {name}",
            callback_data=f"schedule_info_{schedule['id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("➕ Создать новое", callback_data="create_schedule")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def schedule_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать информацию о расписании"""
    query = update.callback_query
    await query.answer()
    
    schedule_id = int(query.data.split('_')[-1])
    schedule = db.get_schedule(schedule_id)
    
    if not schedule:
        await query.edit_message_text("❌ Расписание не найдено")
        return
    
    schedule_type = "📅 Ежедневно" if schedule['schedule_type'] == 'daily' else "📆 Еженедельно"
    
    targets_count = len(parse_targets(schedule['targets']))
    accounts_count = len(schedule['accounts'].split(','))
    
    last_run = schedule.get('last_run')
    if last_run:
        try:
            last_run_date = datetime.fromisoformat(last_run.replace('Z', '+00:00'))
            last_run_str = last_run_date.strftime('%d.%m.%Y %H:%M')
        except:
            last_run_str = 'Никогда'
    else:
        last_run_str = 'Никогда'
    
    text = f"""
⏰ *Расписание: {schedule['name']}*

Тип: {schedule_type}
Время: {schedule['schedule_time']}
Целей: {targets_count}
Аккаунтов: {accounts_count}
Последний запуск: {last_run_str}

📝 Сообщение:
{schedule['message'][:200]}{'...' if len(schedule['message']) > 200 else ''}
"""
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=get_schedule_actions(schedule_id)
    )


async def delete_schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить расписание"""
    query = update.callback_query
    await query.answer()
    
    schedule_id = int(query.data.split('_')[-1])
    
    if db.delete_schedule(schedule_id):
        scheduler.remove_schedule(schedule_id)
        await query.edit_message_text(
            "✅ Расписание удалено",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="list_schedules")
            ]])
        )
    else:
        await query.edit_message_text("❌ Ошибка удаления")


# ==================== ТАРИФЫ И ОПЛАТА ====================

async def tariffs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать тарифы"""
    await update.message.reply_text(
        "💎 *Доступные тарифы*\n\n"
        "Выберите подходящий тариф:",
        parse_mode='Markdown',
        reply_markup=get_subscription_menu()
    )


async def view_tariffs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать тарифы (callback)"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "💎 *Доступные тарифы*\n\n"
        "Выберите подходящий тариф:",
        parse_mode='Markdown',
        reply_markup=get_subscription_menu()
    )


async def plan_details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать детали тарифа"""
    query = update.callback_query
    await query.answer()
    
    plan_id = query.data.split('_')[1]
    plan = SUBSCRIPTION_PLANS.get(plan_id)
    
    if not plan:
        await query.answer("❌ Тариф не найден", show_alert=True)
        return
    
    limits = plan['limits']
    limits_text = []
    for key, value in limits.items():
        key_names = {
            'accounts': 'Аккаунтов',
            'mailings_per_day': 'Рассылок в день',
            'targets_per_mailing': 'Целей на рассылку',
            'schedule_tasks': 'Расписаний'
        }
        name = key_names.get(key, key)
        val = '∞' if value == -1 else str(value)
        limits_text.append(f"  • {name}: {val}")
    
    price_text = f"{plan['price']}₽" if plan['price'] > 0 else "Бесплатно"
    
    text = f"""
{plan['name']}

{plan['description']}

💰 Стоимость: {price_text}
📅 Период: {plan['days']} дней

*Лимиты:*
{chr(10).join(limits_text)}
"""
    
    if plan['price'] > 0:
        keyboard = get_payment_methods(plan_id)
    else:
        # Для бесплатного тарифа - кнопка активации
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Активировать", callback_data=f"activate_{plan_id}")
        ], [
            InlineKeyboardButton("🔙 Назад", callback_data="view_tariffs")
        ]])
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=keyboard
    )


async def activate_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Активировать бесплатный тариф"""
    query = update.callback_query
    await query.answer()
    
    plan_id = query.data.split('_')[1]
    plan = SUBSCRIPTION_PLANS.get(plan_id)
    
    if not plan or plan['price'] > 0:
        await query.answer("❌ Ошибка активации", show_alert=True)
        return
    
    user_id = update.effective_user.id
    
    if db.update_subscription(user_id, plan_id, plan['days']):
        await query.edit_message_text(
            f"✅ Тариф *{plan['name']}* успешно активирован!\n\n"
            f"Срок действия: {plan['days']} дней",
            parse_mode='Markdown'
        )
    else:
        await query.edit_message_text("❌ Ошибка активации тарифа")


async def payment_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора способа оплаты"""
    query = update.callback_query
    await query.answer()
    
    _, plan_id, method_id = query.data.split('_')
    plan = SUBSCRIPTION_PLANS.get(plan_id)
    method = PAYMENT_METHODS.get(method_id)
    
    if not plan or not method:
        await query.answer("❌ Ошибка", show_alert=True)
        return
    
    user_id = update.effective_user.id
    
    # Создаём платёж в БД
    payment_db_id = db.add_payment(
        user_id=user_id,
        plan_id=plan_id,
        amount=plan['price'],
        payment_method=method_id,
        payment_id=f"manual_{int(datetime.now().timestamp())}"
    )
    
    # Инструкции по оплате
    text = f"""
💳 *Оплата тарифа {plan['name']}*

Сумма: {plan['price']}₽
Способ: {method['name']}

📋 *Инструкция:*
1. Переведите {plan['price']}₽ на реквизиты:
   [ЗДЕСЬ ВАШИ РЕКВИЗИТЫ]

2. После оплаты отправьте скриншот чека администратору: @admin

3. После проверки ваша подписка будет активирована автоматически.

ID платежа: `{payment_db_id}`
"""
    
    await query.edit_message_text(
                text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Я оплатил", callback_data=f"paid_{payment_db_id}"),
            InlineKeyboardButton("🔙 Назад", callback_data="view_tariffs")
        ]])
    )


async def paid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь подтвердил оплату"""
    query = update.callback_query
    await query.answer()
    
    payment_db_id = int(query.data.split('_')[1])
    
    await query.edit_message_text(
        "✅ *Спасибо!*\n\n"
        "Ваш платёж отправлен на проверку администратору.\n"
        "После подтверждения подписка будет активирована автоматически.\n\n"
        "Обычно это занимает 5-30 минут.",
        parse_mode='Markdown'
    )
    
    # Уведомляем админа
    try:
        payment = db.get_payment(payment_db_id)
        user = db.get_user(payment['user_id'])
        plan = SUBSCRIPTION_PLANS.get(payment['plan_id'])
        
        admin_text = f"""
💳 *Новый платёж на проверку*

👤 Пользователь: {user.get('first_name', '')} @{user.get('username', 'нет')}
ID: `{user['id']}`

💎 Тариф: {plan['name']}
💰 Сумма: {payment['amount']}₽
🆔 ID платежа: `{payment_db_id}`
"""
        
        await context.application.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            parse_mode='Markdown',
            reply_markup=get_payment_approval(payment_db_id)
        )
    except Exception as e:
        logger.error(f"Error notifying admin about payment: {e}")


# ==================== АДМИН-ПАНЕЛЬ ====================

async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-панель"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет доступа к админ-панели")
        return
    
    stats = db.get_stats()
    
    text = f"""
👨‍💼 *Админ-панель*

📊 *Статистика:*
• Пользователей: {stats.get('total_users', 0)}
• Активных подписок: {stats.get('active_subscriptions', 0)}
• Аккаунтов: {stats.get('total_accounts', 0)}
• Рассылок: {stats.get('total_mailings', 0)}
• Рассылок сегодня: {stats.get('mailings_today', 0)}
• Доход: {stats.get('total_revenue', 0)}₽

Выберите действие:
"""
    
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=get_admin_menu()
    )


async def admin_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список пользователей"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    users = db.get_all_users()
    
    text = "👥 *Все пользователи:*\n\n"
    
    for user in users[:20]:  # Первые 20
        username = user.get('username', 'нет')
        name = user.get('first_name', 'Нет имени')
        plan = user.get('subscription_plan', 'нет')
        
        user_data = db.get_user(user['id'])
        is_active = "✅" if check_subscription(user_data) else "❌"
        
        text += f"{is_active} {name} @{username} ({plan})\n"
    
    if len(users) > 20:
        text += f"\n... и ещё {len(users) - 20} пользователей"
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
        ]])
    )


async def admin_payments_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ожидающие платежи"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    payments = db.get_pending_payments()
    
    if not payments:
        await query.edit_message_text(
            "💳 *Ожидающих платежей нет*",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
            ]])
        )
        return
    
    text = "💳 *Ожидающие платежи:*\n\n"
    keyboard = []
    
    for payment in payments:
        plan = SUBSCRIPTION_PLANS.get(payment['plan_id'])
        username = payment.get('username', 'нет')
        name = payment.get('first_name', 'Нет имени')
        
        text += f"• {name} @{username}\n"
        text += f"  Тариф: {plan['name']} ({payment['amount']}₽)\n"
        text += f"  ID: `{payment['id']}`\n\n"
        
        keyboard.append([InlineKeyboardButton(
            f"✅ Подтвердить #{payment['id']}",
            callback_data=f"approve_payment_{payment['id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_back")])
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def approve_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтвердить платёж"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    payment_id = int(query.data.split('_')[-1])
    payment = db.get_payment(payment_id)
    
    if not payment:
        await query.answer("❌ Платёж не найден", show_alert=True)
        return
    
    plan = SUBSCRIPTION_PLANS.get(payment['plan_id'])
    
    # Обновляем подписку
    if db.update_subscription(payment['user_id'], payment['plan_id'], plan['days']):
        db.update_payment_status(payment_id, 'paid')
        
        await query.answer("✅ Платёж подтверждён", show_alert=True)
        
        # Уведомляем пользователя
        try:
            await context.application.bot.send_message(
                chat_id=payment['user_id'],
                text=f"✅ *Ваш платёж подтверждён!*\n\n"
                     f"Тариф *{plan['name']}* активирован на {plan['days']} дней.\n\n"
                     f"Спасибо за покупку! 🎉",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error notifying user about payment: {e}")
        
        # Обновляем сообщение
        await query.edit_message_text(
            f"✅ Платёж #{payment_id} подтверждён",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="admin_payments")
            ]])
        )
    else:
        await query.answer("❌ Ошибка активации", show_alert=True)


async def reject_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отклонить платёж"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    payment_id = int(query.data.split('_')[-1])
    
    if db.update_payment_status(payment_id, 'rejected'):
        await query.answer("✅ Платёж отклонён", show_alert=True)
        
        payment = db.get_payment(payment_id)
        
        # Уведомляем пользователя
        try:
            await context.application.bot.send_message(
                chat_id=payment['user_id'],
                text="❌ *Ваш платёж отклонён*\n\n"
                     "Пожалуйста, свяжитесь с поддержкой для уточнения деталей.",
                parse_mode='Markdown'
            )
        except:
            pass
        
        await query.edit_message_text(
            f"❌ Платёж #{payment_id} отклонён",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="admin_payments")
            ]])
        )


async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    stats = db.get_stats()
    logs = db.get_logs(limit=10)
    
    text = f"""
📊 *Подробная статистика*

👥 Пользователей: {stats.get('total_users', 0)}
✅ Активных подписок: {stats.get('active_subscriptions', 0)}
📱 Аккаунтов: {stats.get('total_accounts', 0)}
📨 Всего рассылок: {stats.get('total_mailings', 0)}
📊 Рассылок сегодня: {stats.get('mailings_today', 0)}
💰 Общий доход: {stats.get('total_revenue', 0)}₽

📜 *Последние действия:*
"""
    
    for log in logs[:5]:
        username = log.get('username', 'Unknown')
        action = log.get('action', 'unknown')
        text += f"\n• @{username}: {action}"
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
        ]])
    )


async def admin_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать бэкап вручную"""
    query = update.callback_query
    await query.answer("⏳ Создаю бэкап...", show_alert=True)
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    if backup_manager:
        result = await backup_manager.manual_backup()
        await query.answer(result, show_alert=True)
    else:
        await query.answer("❌ Бэкап менеджер не настроен", show_alert=True)


async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало админ-рассылки"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    await query.edit_message_text(
        "📢 *Рассылка всем пользователям*\n\n"
        "Введите текст сообщения для рассылки:\n\n"
        "Для отмены используйте /cancel",
        parse_mode='Markdown'
    )
    
    return ADMIN_BROADCAST_MESSAGE


async def admin_broadcast_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получено сообщение для рассылки"""
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    
    message_text = update.message.text
    
    await update.message.reply_text(
        "⏳ Запускаю рассылку всем пользователям...\n\n"
        "Это может занять некоторое время."
    )
    
    # Получаем всех пользователей
    users = db.get_all_users()
    
    success = 0
    failed = 0
    
    for user in users:
        try:
            await context.application.bot.send_message(
                chat_id=user['id'],
                text=message_text,
                parse_mode='Markdown'
            )
            success += 1
            await asyncio.sleep(0.1)  # Небольшая задержка
        except Exception as e:
            logger.error(f"Error sending to {user['id']}: {e}")
            failed += 1
    
    await update.message.reply_text(
        f"✅ *Рассылка завершена*\n\n"
        f"Успешно: {success}\n"
        f"Ошибок: {failed}",
        parse_mode='Markdown',
        reply_markup=get_main_menu(is_admin=True)
    )
    
    return ConversationHandler.END


# ==================== CALLBACK HANDLERS ====================

async def back_to_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_data = db.get_user(user.id)
    
    is_active = check_subscription(user_data)
    days_left = get_days_left(user_data)
    
    plan_id = user_data.get('subscription_plan', 'trial')
    plan = SUBSCRIPTION_PLANS.get(plan_id, SUBSCRIPTION_PLANS['trial'])
    
    subscription_text = f"{plan['name']} ({'✅ активна' if is_active else '❌ истекла'})"
    
    welcome_text = TEXTS['welcome'].format(
        subscription=subscription_text,
        days_left=days_left
    )
    
    await query.edit_message_text(
        welcome_text,
        parse_mode='Markdown'
    )


async def admin_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в админ-панель"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        return
    
    stats = db.get_stats()
    
    text = f"""
👨‍💼 *Админ-панель*

📊 *Статистика:*
• Пользователей: {stats.get('total_users', 0)}
• Активных подписок: {stats.get('active_subscriptions', 0)}
• Аккаунтов: {stats.get('total_accounts', 0)}
• Рассылок: {stats.get('total_mailings', 0)}
• Рассылок сегодня: {stats.get('mailings_today', 0)}
• Доход: {stats.get('total_revenue', 0)}₽

Выберите действие:
"""
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=get_admin_menu()
    )


# ==================== ОБРАБОТЧИКИ ТЕКСТОВЫХ КОМАНД ====================

async def my_accounts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка: Мои аккаунты"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    logger.info(f"User {user_id} pressed: my_accounts")
    
    # Получаем аккаунты
    accounts = db.get_user_accounts(user_id)
    
    if not accounts:
        text = "❌ У вас нет подключенных аккаунтов\n\nПодключите аккаунт для начала работы."
    else:
        text = f"📱 *Ваши аккаунты ({len(accounts)}):*\n\n"
        for acc in accounts:
            status = "✅" if acc['is_active'] else "❌"
            name = acc.get('account_name') or acc['phone']
            text += f"{status} {name} ({acc['phone']})\n"
    
    keyboard = get_accounts_menu()
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=keyboard
    )


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка: Помощь"""
    query = update.callback_query
    await query.answer()
    
    logger.info(f"User {query.from_user.id} pressed: help")
    
    text = TEXTS['help']
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]
    ])
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=keyboard
    )


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    is_admin = (user.id == ADMIN_ID)
    
    user_data = db.get_user(user.id)
    plan_id = user_data.get('subscription_plan', 'trial')
    plan = SUBSCRIPTION_PLANS[plan_id]
    days_left = get_days_left(user_data)
    
    text = TEXTS['welcome'].format(
        subscription=plan['name'],
        days_left=days_left
    )
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=get_main_menu(is_admin)
    )

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых команд из ReplyKeyboard"""
    text = update.message.text
    
    if text == "📱 Мои аккаунты":
        await my_accounts_handler(update, context)
    
    elif text == "📨 Создать рассылку":
        return await create_mailing_start(update, context)
    
    elif text == "⏰ Планировщик":
        await scheduler_handler(update, context)
    
    elif text == "📜 История":
        await history_handler(update, context)
    
    elif text == "💎 Тарифы":
        await tariffs_handler(update, context)
    
    elif text == "ℹ️ Помощь":
        await help_command(update, context)
    
    elif text == "👨‍💼 Админ-панель":
        await admin_panel_handler(update, context)
    
    elif text == "🔙 Назад":
        await start(update, context)
    
    else:
        await update.message.reply_text(
            "❓ Неизвестная команда. Используйте меню ниже.",
            reply_markup=get_main_menu(update.effective_user.id == ADMIN_ID)
        )


# ==================== ОБРАБОТЧИКИ ПОДКЛЮЧЕНИЯ АККАУНТОВ ====================

async def connect_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало подключения аккаунта (через кнопку)"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    logger.info(f"User {user_id} started account connection")
    
    # Проверяем лимит аккаунтов
    user_data = db.get_user(user_id)
    plan_id = user_data.get('subscription_plan', 'trial')
    plan = SUBSCRIPTION_PLANS[plan_id]
    
    current_accounts = len(db.get_user_accounts(user_id))
    max_accounts = plan['limits']['accounts']
    
    if max_accounts != -1 and current_accounts >= max_accounts:
        await query.edit_message_text(
            f"❌ Достигнут лимит аккаунтов ({max_accounts})\n\n"
            f"Обновите тариф для подключения большего количества аккаунтов.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💎 Тарифы", callback_data="subscriptions"),
                InlineKeyboardButton("◀️ Назад", callback_data="my_accounts")
            ]])
        )
        return ConversationHandler.END
    
    # Запрашиваем номер телефона
    await query.edit_message_text(
        "📱 *Подключение аккаунта*\n\n"
        "Отправьте номер телефона в международном формате:\n"
        "Пример: `+79991234567`\n\n"
        "Или /cancel для отмены",
        parse_mode='Markdown'
    )
    
    return PHONE


async def phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка номера телефона"""
    user_id = update.effective_user.id
    phone = update.message.text.strip()
    
    # Валидация номера
    if not phone.startswith('+') or not phone[1:].isdigit():
        await update.message.reply_text(
            "❌ Неверный формат номера!\n\n"
            "Используйте международный формат: `+79991234567`",
            parse_mode='Markdown'
        )
        return PHONE
    
    # Сохраняем номер
    context.user_data['phone'] = phone
    
    # Инициируем подключение через Telethon
    try:
        await update.message.reply_text("⏳ Отправляю код...")
        
        # Используем userbot_manager для отправки кода
        result = await userbot_manager.send_code(user_id, phone)
        
        if result['success']:
            context.user_data['phone_code_hash'] = result['phone_code_hash']
            
            await update.message.reply_text(
                "✅ Код отправлен на ваш Telegram!\n\n"
                "Введите код подтверждения:\n"
                "Пример: `12345`\n\n"
                "Или /cancel для отмены",
                parse_mode='Markdown'
            )
            return CODE
        else:
            await update.message.reply_text(
                f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}\n\n"
                "Попробуйте снова или /cancel",
                parse_mode='Markdown'
            )
            return PHONE
            
    except Exception as e:
        logger.error(f"Error sending code: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при отправке кода\n\n"
            "Попробуйте позже или /cancel",
            parse_mode='Markdown'
        )
        return ConversationHandler.END


async def code_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кода подтверждения"""
    user_id = update.effective_user.id
    code = update.message.text.strip().replace('-', '').replace(' ', '')
    
    if not code.isdigit():
        await update.message.reply_text(
            "❌ Код должен содержать только цифры!\n\n"
            "Введите код еще раз:",
            parse_mode='Markdown'
        )
        return CODE
    
    phone = context.user_data.get('phone')
    phone_code_hash = context.user_data.get('phone_code_hash')
    
    try:
        await update.message.reply_text("⏳ Проверяю код...")
        
        # Пробуем авторизоваться
        result = await userbot_manager.sign_in(user_id, phone, code, phone_code_hash)
        
        if result['success']:
            # Успешно подключено
            await update.message.reply_text(
                "✅ Аккаунт успешно подключен!\n\n"
                f"📱 {phone}\n\n"
                "Теперь вы можете создавать рассылки.",
                reply_markup=get_accounts_menu()
            )
            
            # Логируем
            db.add_log(user_id, 'account_connected', f'Phone: {phone}')
            
            return ConversationHandler.END
            
        elif result.get('password_required'):
            # Нужен пароль 2FA
            await update.message.reply_text(
                "🔐 Аккаунт защищен двухфакторной аутентификацией\n\n"
                "Введите пароль облачной защиты:\n\n"
                "Или /cancel для отмены",
                parse_mode='Markdown'
            )
            return PASSWORD
            
        else:
            await update.message.reply_text(
                f"❌ Ошибка: {result.get('error', 'Неверный код')}\n\n"
                "Попробуйте еще раз или /cancel",
                parse_mode='Markdown'
            )
            return CODE
            
    except Exception as e:
        logger.error(f"Error verifying code: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка\n\n"
            "Попробуйте позже или /cancel",
            parse_mode='Markdown'
        )
        return ConversationHandler.END


async def password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка пароля 2FA"""
    user_id = update.effective_user.id
    password = update.message.text.strip()
    
    phone = context.user_data.get('phone')
    
    try:
        await update.message.reply_text("⏳ Проверяю пароль...")
        
        result = await userbot_manager.check_password(user_id, password)
        
        if result['success']:
            await update.message.reply_text(
                "✅ Аккаунт успешно подключен!\n\n"
                f"📱 {phone}\n\n"
                "Теперь вы можете создавать рассылки.",
                reply_markup=get_accounts_menu()
            )
            
            db.add_log(user_id, 'account_connected', f'Phone: {phone} (with 2FA)')
            
            return ConversationHandler.END
        else:
            await update.message.reply_text(
                "❌ Неверный пароль!\n\n"
                "Попробуйте еще раз или /cancel",
                parse_mode='Markdown'
            )
            return PASSWORD
            
    except Exception as e:
        logger.error(f"Error checking password: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка\n\n"
            "Попробуйте позже или /cancel",
            parse_mode='Markdown'
        )
        return ConversationHandler.END


async def cancel_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена подключения аккаунта"""
    await update.message.reply_text(
        "❌ Подключение отменено",
        reply_markup=get_accounts_menu()
    )
    return ConversationHandler.END


# ==================== CALLBACK ОБРАБОТЧИКИ ====================

async def accounts_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат к списку аккаунтов"""
    query = update.callback_query
    await query.answer()
    await my_accounts_callback(update, context)


async def manage_accounts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление аккаунтами"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    accounts = db.get_user_accounts(user_id)
    
    if not accounts:
        await query.edit_message_text(
            "❌ Нет аккаунтов для управления",
            reply_markup=get_accounts_menu()
        )
        return
    
    keyboard = []
    for acc in accounts:
        name = acc.get('account_name') or acc['phone']
        status = "✅" if acc['is_active'] else "❌"
        keyboard.append([InlineKeyboardButton(
            f"{status} {name}",
            callback_data=f"disconnect_account_{acc['id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="my_accounts")])
    
    await query.edit_message_text(
        "📱 *Управление аккаунтами*\n\nВыберите аккаунт для отключения:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def disconnect_account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отключить аккаунт"""
    query = update.callback_query
    await query.answer()
    
    account_id = int(query.data.split('_')[-1])
    user_id = query.from_user.id
    
    # Отключаем аккаунт
    result = await userbot_manager.disconnect_account(user_id, account_id)
    
    if result:
        await query.edit_message_text(
            "✅ Аккаунт успешно отключен",
            reply_markup=get_accounts_menu()
        )
        db.add_log(user_id, 'account_disconnected', f'Account ID: {account_id}')
    else:
        await query.edit_message_text(
            "❌ Ошибка при отключении аккаунта",
            reply_markup=get_accounts_menu()
        )


async def create_mailing_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать рассылку"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    accounts = db.get_user_accounts(user_id)
    
    if not accounts:
        await query.edit_message_text(
            TEXTS['no_accounts'],
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📱 Подключить аккаунт", callback_data="connect_account"),
                InlineKeyboardButton("◀️ Назад", callback_data="main_menu")
            ]])
        )
        return
    
    await query.edit_message_text(
        "📨 *Создание рассылки*\n\n"
        "Отправьте список получателей (username или ID):\n"
        "Пример:\n`@username1\n@username2\n123456789`\n\n"
        "Или /cancel для отмены",
        parse_mode='Markdown'
    )


async def scheduler_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Планировщик"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "⏰ *Планировщик рассылок*\n\n"
        "Функция в разработке",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад", callback_data="main_menu")
        ]])
    )


async def history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """История рассылок"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    mailings = db.get_user_mailings(user_id, limit=10)
    
    if not mailings:
        text = "📜 История рассылок пуста"
    else:
        text = "📜 *Последние рассылки:*\n\n"
        for m in mailings:
            status_emoji = {
                'pending': '⏳',
                'running': '▶️',
                'completed': '✅',
                'cancelled': '❌',
                'failed': '⚠️'
            }.get(m['status'], '❓')
            
            text += f"{status_emoji} ID {m['id']}: {m['sent_count']}/{m['total_count']}\n"
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад", callback_data="main_menu")
        ]])
    )


async def subscriptions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать тарифы"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = db.get_user(user_id)
    current_plan = user_data.get('subscription_plan', 'trial')
    
    text = "💎 *Тарифные планы:*\n\n"
    
    keyboard = []
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        is_current = (plan_id == current_plan)
        status = " ✅ Текущий" if is_current else ""
        
        text += f"*{plan['name']}*{status}\n"
        text += f"💰 {plan['price']} ₽/мес\n"
        text += f"📝 {plan['description']}\n\n"
        
        if not is_current:
            keyboard.append([InlineKeyboardButton(
                f"Купить {plan['name']} - {plan['price']} ₽",
                callback_data=f"buy_{plan_id}"
            )])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def buy_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Покупка подписки"""
    query = update.callback_query
    await query.answer()
    
    plan_id = query.data.split('_')[1]
    plan = SUBSCRIPTION_PLANS.get(plan_id)
    
    if not plan:
        await query.edit_message_text("❌ Тариф не найден")
        return
    
    text = f"💎 *{plan['name']}*\n\n"
    text += f"💰 Стоимость: {plan['price']} ₽\n"
    text += f"📅 Период: {plan['days']} дней\n\n"
    text += "Выберите способ оплаты:"
    
    keyboard = []
    for method_id, method in PAYMENT_METHODS.items():
        if method['enabled']:
            keyboard.append([InlineKeyboardButton(
                method['name'],
                callback_data=f"payment_{method_id}_{plan_id}"
            )])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="subscriptions")])
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def subscriptions_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Назад к тарифам"""
    await subscriptions_callback(update, context)


async def history_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Назад к истории"""
    await history_callback(update, context)


async def scheduler_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Назад к планировщику"""
    await scheduler_callback(update, context)


# Заглушки для остальных функций (добавьте по необходимости)
async def view_mailing_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Функция в разработке")


async def create_schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Функция в разработке")


async def view_schedules_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Функция в разработке")


async def edit_schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Функция в разработке")


async def toggle_schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Функция в разработке")


async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Админ-панель в разработке")


def main():
    """Запуск бота"""
    logger.info("="*50)
    logger.info("🚀 Starting Telegram Bot Manager...")
    logger.info("="*50)
    
    # Создаём приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # ConversationHandler для подключения аккаунта
    connect_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(connect_userbot_start, pattern="^connect_account$")
        ],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_received)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, code_received)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, password_received)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # ConversationHandler для создания рассылки
    mailing_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^📨 Создать рассылку$"), create_mailing_start)
        ],
        states={
            MAILING_TARGETS: [MessageHandler(filters.TEXT & ~filters.COMMAND, mailing_targets_received)],
            MAILING_ACCOUNTS: [
                CallbackQueryHandler(toggle_account_selection, pattern="^toggle_account_"),
                CallbackQueryHandler(continue_with_selected, pattern="^continue_with_selected$")
            ],
            MAILING_MESSAGE: [
                MessageHandler(
                    (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND,
                    mailing_message_received
                )
            ],
            MAILING_CONFIRM: [
                CallbackQueryHandler(confirm_mailing_callback, pattern="^confirm_mailing$"),
                CallbackQueryHandler(cancel_mailing_callback, pattern="^cancel_mailing$")
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # ConversationHandler для админ-рассылки
    admin_broadcast_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast$")
        ],
        states={
            ADMIN_BROADCAST_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_message_received)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel))
    
    # ConversationHandlers
    application.add_handler(connect_conv)
    application.add_handler(mailing_conv)
    application.add_handler(admin_broadcast_conv)

     # Главное меню
    application.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(my_accounts_callback, pattern="^my_accounts$"))
    application.add_handler(CallbackQueryHandler(create_mailing_callback, pattern="^create_mailing$"))
    application.add_handler(CallbackQueryHandler(scheduler_callback, pattern="^scheduler$"))
    application.add_handler(CallbackQueryHandler(history_callback, pattern="^history$"))
    application.add_handler(CallbackQueryHandler(subscriptions_callback, pattern="^subscriptions$"))
    application.add_handler(CallbackQueryHandler(help_callback, pattern="^help$"))
    
    # Аккаунты
    application.add_handler(CallbackQueryHandler(connect_account_start, pattern="^connect_account$"))
    application.add_handler(CallbackQueryHandler(manage_accounts_callback, pattern="^manage_accounts$"))
    application.add_handler(CallbackQueryHandler(disconnect_account_callback, pattern="^disconnect_account_"))
    
    # Подписки
    application.add_handler(CallbackQueryHandler(buy_subscription_callback, pattern="^buy_"))
    application.add_handler(CallbackQueryHandler(payment_method_callback, pattern="^payment_"))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(back_to_menu_callback, pattern="^back_to_menu$"))
    application.add_handler(CallbackQueryHandler(list_accounts_callback, pattern="^list_accounts$"))
    application.add_handler(CallbackQueryHandler(account_info_callback, pattern="^account_info_"))
    application.add_handler(CallbackQueryHandler(delete_account_callback, pattern="^delete_account_"))
    application.add_handler(CallbackQueryHandler(view_tariffs_callback, pattern="^view_tariffs$"))
    application.add_handler(CallbackQueryHandler(plan_details_callback, pattern="^plan_"))
    application.add_handler(CallbackQueryHandler(activate_plan_callback, pattern="^activate_"))
    application.add_handler(CallbackQueryHandler(payment_method_callback, pattern="^pay_"))
    application.add_handler(CallbackQueryHandler(paid_callback, pattern="^paid_"))
    application.add_handler(CallbackQueryHandler(list_schedules_callback, pattern="^list_schedules$"))
    application.add_handler(CallbackQueryHandler(schedule_info_callback, pattern="^schedule_info_"))
    application.add_handler(CallbackQueryHandler(delete_schedule_callback, pattern="^delete_schedule_"))
    application.add_handler(CallbackQueryHandler(my_accounts_callback, pattern="^my_accounts$"))
    application.add_handler(CallbackQueryHandler(connect_account_start, pattern="^connect_account$"))
    application.add_handler(CallbackQueryHandler(accounts_back_callback, pattern="^accounts_back$"))
    
    # Админ callbacks
    application.add_handler(CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$"))
    application.add_handler(CallbackQueryHandler(admin_users_callback, pattern="^admin_users$"))
    application.add_handler(CallbackQueryHandler(admin_payments_callback, pattern="^admin_payments$"))
    application.add_handler(CallbackQueryHandler(admin_stats_callback, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(admin_backup_callback, pattern="^admin_backup$"))
    application.add_handler(CallbackQueryHandler(admin_back_callback, pattern="^admin_back$"))
    application.add_handler(CallbackQueryHandler(approve_payment_callback, pattern="^approve_payment_"))
    application.add_handler(CallbackQueryHandler(reject_payment_callback, pattern="^reject_payment_"))
    
    # Текстовые сообщения
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    # Запуск
    logger.info("🤖 Bot starting polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Critical error: {e}")
        logger.exception("Full traceback:")
    finally:
        # Очистка
        try:
            asyncio.run(userbot_manager.disconnect_all())
        except:
            pass
        
        if scheduler:
            scheduler.shutdown()
        
        if backup_manager:
            backup_manager.shutdown()
        
        db.close()
        logger.info("✅ Cleanup completed")
        logger.info("✅ Cleanup completed")