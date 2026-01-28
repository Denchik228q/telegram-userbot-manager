#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Manager Bot - Complete Version
"""

import logging
import asyncio
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

from config_userbot import (
    MANAGER_BOT_TOKEN,
    ADMIN_ID,
    PUBLIC_CHANNEL_URL,
    PRIVATE_CHANNEL_URL,
    PUBLIC_CHANNEL_NAME,
    PRIVATE_CHANNEL_NAME,
    SUBSCRIPTIONS,
    MAILING_DELAY,
    PAYMENT_CARD,
    PAYMENT_PHONE
)
from database import Database
from userbot import UserbotManager
from scheduler import MailingScheduler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация
db = Database()
userbot_manager = UserbotManager()
mailing_scheduler = MailingScheduler(db, userbot_manager)
mailing_scheduler.start()

# Состояния для ConversationHandler
PHONE, CODE, PASSWORD = range(3)
SUPPORT_MESSAGE = 10
PAYMENT_RECEIPT = 20
ADMIN_MAILING_MESSAGE, ADMIN_MAILING_CONFIRM = 100, 101
USER_MAILING_TARGETS, USER_MAILING_MESSAGE, USER_MAILING_CONFIRM = 200, 201, 202

# ==================== КЛАВИАТУРЫ ====================

def get_main_menu_keyboard():
    """Клавиатура главного меню"""
    keyboard = [
        [InlineKeyboardButton("📨 Новая рассылка", callback_data='start_mailing')],
        [InlineKeyboardButton("⏰ Планировщик", callback_data='schedule_menu')],
        [InlineKeyboardButton("📱 Мои аккаунты", callback_data='accounts_menu')],
        [InlineKeyboardButton("📊 История рассылок", callback_data='mailing_history')],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data='help')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_subscription_keyboard():
    """Клавиатура подписки на канал"""
    keyboard = [
        [InlineKeyboardButton(f"{PUBLIC_CHANNEL_NAME}", url=PUBLIC_CHANNEL_URL if PUBLIC_CHANNEL_URL.startswith('http') else f"https://t.me/{PUBLIC_CHANNEL_URL.replace('@', '')}")],
        [InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard():
    """Админ-панель"""
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("📮 Рассылка всем", callback_data="admin_mailing")],
        [InlineKeyboardButton("✅ Подтвердить оплату", callback_data="admin_payments")],
        [InlineKeyboardButton("💾 Бэкап БД", callback_data="admin_backup")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверка подписки на канал"""
    try:
        channel_username = PUBLIC_CHANNEL_URL.replace('@', '').replace('https://t.me/', '')
        member = await context.bot.get_chat_member(chat_id=f"@{channel_username}", user_id=user_id)
        if member.status in ['left', 'kicked']:
            return False
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        return True  # В случае ошибки разрешаем доступ
    return True

# ==================== КОМАНДЫ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    db.add_user(user_id, username)
    
    # Проверяем аккаунты
    accounts = db.get_user_accounts(user_id)
    accounts_text = f"📱 Аккаунтов: {len(accounts)}" if accounts else "⚠️ Аккаунты не добавлены"
    
    if update.message:
        await update.message.reply_text(
            f"👋 Добро пожаловать в бот массовых рассылок!\n\n"
            f"{accounts_text}\n\n"
            f"🎯 Возможности:\n"
            f"• Рассылка в группы/каналы\n"
            f"• Несколько аккаунтов\n"
            f"• Планировщик рассылок\n"
            f"• Автоматическое вступление\n\n"
            f"Выберите действие:",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        query = update.callback_query
        await query.edit_message_text(
            f"👋 Добро пожаловать в бот массовых рассылок!\n\n"
            f"{accounts_text}\n\n"
            f"🎯 Возможности:\n"
            f"• Рассылка в группы/каналы\n"
            f"• Несколько аккаунтов\n"
            f"• Планировщик рассылок\n"
            f"• Автоматическое вступление\n\n"
            f"Выберите действие:",
            reply_markup=get_main_menu_keyboard()
        )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-панель"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет доступа")
        return
    
    stats = db.get_stats()
    
    admin_text = f"""
🔧 *Панель администратора*

📊 *Статистика:*
👥 Всего пользователей: {stats.get('total_users', 0)}
📱 Всего аккаунтов: {stats.get('total_accounts', 0)}
📨 Всего рассылок: {stats.get('total_mailings', 0)}
⏰ Запланировано: {stats.get('total_scheduled', 0)}
    """
    
    await update.message.reply_text(
        admin_text,
        reply_markup=get_admin_keyboard(),
        parse_mode='Markdown'
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущей операции"""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Операция отменена",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END

# ==================== CALLBACK ОБРАБОТЧИКИ ====================

async def back_to_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    accounts = db.get_user_accounts(user_id)
    accounts_text = f"📱 Аккаунтов: {len(accounts)}" if accounts else "⚠️ Аккаунты не добавлены"
    
    await query.edit_message_text(
        f"Главное меню\n\n{accounts_text}\n\nВыберите действие:",
        reply_markup=get_main_menu_keyboard()
    )

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка подписки callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    is_subscribed = await check_subscription(user_id, context)
    
    if is_subscribed:
        await query.edit_message_text(
            "✅ Отлично! Вы подписаны.\n\nВыберите действие:",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await query.answer("❌ Вы ещё не подписались!", show_alert=True)

# ==================== ПОДКЛЮЧЕНИЕ АККАУНТА ====================

async def connect_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало подключения аккаунта"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📱 *Добавление аккаунта*\n\n"
        "Введите номер телефона в международном формате:\n"
        "Пример: `+79991234567`\n\n"
        "Или /cancel для отмены",
        parse_mode='Markdown'
    )
    
    return PHONE

async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка номера телефона"""
    phone = update.message.text.strip()
    
    if not phone.startswith('+'):
        phone = '+' + phone
    
    user_id = update.effective_user.id
    
    # Проверяем, есть ли уже такой аккаунт
    existing = db.get_account_by_phone(user_id, phone)
    if existing:
        await update.message.reply_text(
            "⚠️ Этот номер уже добавлен!\n\n"
            "Используйте /start для возврата в меню."
        )
        return ConversationHandler.END
    
    context.user_data['phone'] = phone
    
    # Отправляем код
    result = await userbot_manager.send_code(phone)
    
    if result['success']:
        context.user_data['phone_code_hash'] = result['phone_code_hash']
        await update.message.reply_text(
            "✅ Код отправлен в Telegram!\n\n"
            "📲 Введите код подтверждения:"
        )
        return CODE
    else:
        await update.message.reply_text(
            f"❌ Ошибка: {result['error']}\n\n"
            "Используйте /start для повтора."
        )
        return ConversationHandler.END

async def receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кода подтверждения"""
    code = update.message.text.strip()
    phone = context.user_data['phone']
    phone_code_hash = context.user_data['phone_code_hash']
    
    result = await userbot_manager.sign_in(phone, code, phone_code_hash)
    
    if result['success']:
        session_id = result['session_id']
        user_id = update.effective_user.id
        
        # Добавляем аккаунт в БД
        account_id = db.add_account(user_id, phone, session_id)
        
        if account_id:
            await update.message.reply_text(
                "✅ *Аккаунт успешно добавлен!*\n\n"
                "Теперь вы можете:\n"
                "• Добавить ещё аккаунты\n"
                "• Начать рассылку\n"
                "• Настроить расписание",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
        else:
            await update.message.reply_text("❌ Ошибка сохранения аккаунта")
        
        context.user_data.clear()
        return ConversationHandler.END
    
    elif result.get('password_required'):
        await update.message.reply_text(
            "🔐 Требуется пароль 2FA\n\n"
            "Введите пароль:"
        )
        return PASSWORD
    
    else:
        await update.message.reply_text(
            f"❌ Ошибка: {result['error']}\n\n"
            "Используйте /start для повтора."
        )
        return ConversationHandler.END

async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка пароля 2FA"""
    password = update.message.text.strip()
    phone = context.user_data['phone']
    
    result = await userbot_manager.sign_in_2fa(phone, password)
    
    if result['success']:
        session_id = result['session_id']
        user_id = update.effective_user.id
        
        # Добавляем аккаунт в БД
        account_id = db.add_account(user_id, phone, session_id)
        
        if account_id:
            await update.message.reply_text(
                "✅ *Аккаунт успешно добавлен!*\n\n"
                "Теперь вы можете:\n"
                "• Добавить ещё аккаунты\n"
                "• Начать рассылку\n"
                "• Настроить расписание",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
        else:
            await update.message.reply_text("❌ Ошибка сохранения аккаунта")
        
        context.user_data.clear()
        return ConversationHandler.END
    
    else:
        await update.message.reply_text(
            f"❌ Ошибка: {result['error']}\n\n"
            "Используйте /start для повтора."
        )
        return ConversationHandler.END

# ==================== УПРАВЛЕНИЕ АККАУНТАМИ ====================

async def accounts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню управления аккаунтами"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    accounts = db.get_user_accounts(user_id)
    
    if not accounts:
        keyboard = [
            [InlineKeyboardButton("➕ Добавить аккаунт", callback_data='connect_userbot')],
            [InlineKeyboardButton("◀️ Назад", callback_data='back_to_menu')]
        ]
        await query.edit_message_text(
            "📱 *Управление аккаунтами*\n\n"
            "У вас пока нет добавленных аккаунтов.\n"
            "Добавьте первый аккаунт для начала работы!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    # Формируем список аккаунтов
    accounts_text = "📱 *Ваши аккаунты:*\n\n"
    keyboard = []
    
    for idx, acc in enumerate(accounts, 1):
        status = "✅" if acc['is_active'] else "❌"
        accounts_text += f"{idx}. {status} {acc['account_name']}\n   📞 {acc['phone_number']}\n\n"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{acc['account_name']}", 
                callback_data=f"account_{acc['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("➕ Добавить аккаунт", callback_data='connect_userbot')])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='back_to_menu')])
    
    await query.edit_message_text(
        accounts_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def account_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детали конкретного аккаунта"""
    query = update.callback_query
    await query.answer()
    
    account_id = int(query.data.split('_')[1])
    account = db.get_account(account_id)
    
    if not account:
        await query.edit_message_text("❌ Аккаунт не найден")
        return
    
    status = "✅ Активен" if account['is_active'] else "❌ Отключен"
    
    text = (
        f"📱 *{account['account_name']}*\n\n"
        f"📞 Телефон: `{account['phone_number']}`\n"
        f"📊 Статус: {status}\n"
        f"📅 Добавлен: {account['created_at'][:16]}"
    )
    
    keyboard = [
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_account_{account_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data='accounts_menu')]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def delete_account_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления аккаунта"""
    query = update.callback_query
    await query.answer()
    
    account_id = int(query.data.split('_')[2])
    account = db.get_account(account_id)
    
    if not account:
        await query.edit_message_text("❌ Аккаунт не найден")
        return
    
    keyboard = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{account_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"account_{account_id}")]
    ]
    
    await query.edit_message_text(
        f"⚠️ *Подтверждение удаления*\n\n"
        f"Вы уверены, что хотите удалить аккаунт?\n\n"
        f"📱 {account['account_name']}\n"
        f"📞 {account['phone_number']}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def confirm_delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Окончательное удаление аккаунта"""
    query = update.callback_query
    await query.answer()
    
    account_id = int(query.data.split('_')[2])
    
    # Отключаем сессию
    account = db.get_account(account_id)
    if account:
        await userbot_manager.disconnect_session(account['session_id'])
    
    # Удаляем из БД
    db.delete_account(account_id)
    
    await query.edit_message_text(
        "✅ Аккаунт успешно удален!",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ К аккаунтам", callback_data='accounts_menu')
        ]])
    )

# ==================== ПЛАНИРОВЩИК РАССЫЛОК ====================

async def schedule_mailing_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню планирования рассылок"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📋 Мои расписания", callback_data='my_schedules')],
        [InlineKeyboardButton("◀️ Назад", callback_data='back_to_menu')]
    ]
    
    await query.edit_message_text(
        "⏰ *Планировщик рассылок*\n\n"
        "Функция планировщика позволит настроить автоматические рассылки.\n\n"
        "⚠️ В данный момент доступен только ручной запуск рассылок.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def my_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список запланированных рассылок"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    schedules = db.get_user_scheduled_mailings(user_id)
    
    if not schedules:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='schedule_menu')]]
        await query.edit_message_text(
            "📋 У вас нет запланированных рассылок",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    text = "📋 *Ваши запланированные рассылки:*\n\n"
    keyboard = []
    
    for idx, schedule in enumerate(schedules, 1):
        targets_count = len(schedule['targets'])
        text += f"{idx}. 📨 {targets_count} чатов\n"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{idx}. Рассылка",
                callback_data=f"schedule_detail_{schedule['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='schedule_menu')])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def schedule_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детали запланированной рассылки"""
    query = update.callback_query
    await query.answer()
    
    schedule_id = int(query.data.split('_')[2])
    schedules = db.get_user_scheduled_mailings(update.effective_user.id)
    schedule = next((s for s in schedules if s['id'] == schedule_id), None)
    
    if not schedule:
        await query.edit_message_text("❌ Расписание не найдено")
        return
    
    message_preview = schedule['message_text'] or schedule['message_caption'] or "[Медиа]"
    message_preview = message_preview[:50] + "..." if len(message_preview) > 50 else message_preview
    
    text = (
        f"📋 *Детали рассылки #{schedule['id']}*\n\n"
        f"📨 Сообщение: {message_preview}\n"
        f"🎯 Чатов: {len(schedule['targets'])}\n"
        f"📅 Создано: {schedule['created_at'][:16]}\n"
    )
    
    if schedule['last_run']:
        text += f"⏰ Последний запуск: {schedule['last_run'][:16]}\n"
    
    keyboard = [
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_schedule_{schedule_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data='my_schedules')]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def delete_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление запланированной рассылки"""
    query = update.callback_query
    await query.answer()
    
    schedule_id = int(query.data.split('_')[2])
    
    # Удаляем из планировщика
    mailing_scheduler.remove_job(schedule_id)
    
    # Удаляем из БД
    db.delete_scheduled_mailing(schedule_id)
    
    await query.edit_message_text(
        "✅ Запланированная рассылка удалена!",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ К расписаниям", callback_data='my_schedules')
        ]])
    )

# ==================== ВЫБОР АККАУНТОВ ДЛЯ РАССЫЛКИ ====================

async def select_accounts_for_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор аккаунтов для рассылки"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    accounts = db.get_user_accounts(user_id)
    
    if not accounts:
        await query.edit_message_text(
            "❌ У вас нет добавленных аккаунтов!\n"
            "Сначала добавьте хотя бы один аккаунт.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Добавить аккаунт", callback_data='connect_userbot')
            ]])
        )
        return
    
    # Инициализируем список выбранных аккаунтов если его нет
    if 'selected_accounts' not in context.user_data:
        context.user_data['selected_accounts'] = []
    
    selected = context.user_data['selected_accounts']
    
    text = "👥 *Выберите аккаунты для рассылки:*\n\n"
    keyboard = []
    
    for acc in accounts:
        is_selected = acc['id'] in selected
        checkbox = "☑️" if is_selected else "⬜️"
        text += f"{checkbox} {acc['account_name']} ({acc['phone_number']})\n"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{checkbox} {acc['account_name']}",
                callback_data=f"toggle_account_{acc['id']}"
            )
        ])
    
    text += f"\n✅ Выбрано: {len(selected)}/{len(accounts)}"
    
    keyboard.append([
        InlineKeyboardButton("✅ Выбрать все", callback_data='select_all_accounts'),
        InlineKeyboardButton("❌ Снять все", callback_data='deselect_all_accounts')
    ])
    keyboard.append([InlineKeyboardButton("➡️ Продолжить", callback_data='continue_with_selected')])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='back_to_menu')])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def toggle_account_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключение выбора аккаунта"""
    query = update.callback_query
    await query.answer()
    
    account_id = int(query.data.split('_')[2])
    
    if 'selected_accounts' not in context.user_data:
        context.user_data['selected_accounts'] = []
    
    if account_id in context.user_data['selected_accounts']:
        context.user_data['selected_accounts'].remove(account_id)
    else:
        context.user_data['selected_accounts'].append(account_id)
    
    # Обновляем меню
    await select_accounts_for_mailing(update, context)

async def select_all_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбрать все аккаунты"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    accounts = db.get_user_accounts(user_id)
    context.user_data['selected_accounts'] = [acc['id'] for acc in accounts]
    
    await select_accounts_for_mailing(update, context)

async def deselect_all_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Снять выбор со всех аккаунтов"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['selected_accounts'] = []
    await select_accounts_for_mailing(update, context)

async def use_all_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Использовать все аккаунты"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    accounts = db.get_user_accounts(user_id)
    
    if not accounts:
        await query.edit_message_text(
            "❌ У вас нет добавленных аккаунтов!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Добавить", callback_data='connect_userbot')
            ]])
        )
        return ConversationHandler.END
    
    context.user_data['selected_accounts'] = [acc['id'] for acc in accounts]
    
    await query.edit_message_text(
        f"✅ Выбраны все аккаунты ({len(accounts)} шт.)\n\n"
        f"📨 Теперь отправьте сообщение для рассылки:"
    )
    
    return USER_MAILING_MESSAGE

async def continue_with_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Продолжить с выбранными аккаунтами"""
    query = update.callback_query
    await query.answer()
    
    selected = context.user_data.get('selected_accounts', [])
    
    if not selected:
        await query.answer("❌ Выберите хотя бы один аккаунт!", show_alert=True)
        return
    
    await query.edit_message_text(
        f"✅ Выбрано аккаунтов: {len(selected)}\n\n"
        f"📨 Теперь отправьте сообщение для рассылки:"
    )
    
    return USER_MAILING_MESSAGE

# ==================== РАССЫЛКА ====================

async def start_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания рассылки"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Проверяем аккаунты
    accounts = db.get_user_accounts(user_id)
    if not accounts:
        await query.edit_message_text(
            "❌ Сначала добавьте хотя бы один аккаунт!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Добавить аккаунт", callback_data='connect_userbot')
            ]])
        )
        return ConversationHandler.END
    
    await query.edit_message_text(
        "📨 *Создание рассылки*\n\n"
        "Отправьте список ссылок на группы/каналы (по одной на строку):\n\n"
        "Примеры:\n"
        "• https://t.me/channel\n"
        "• @username\n"
        "• https://t.me/+invitehash\n\n"
        "Или /cancel для отмены",
        parse_mode='Markdown'
    )
    
    return USER_MAILING_TARGETS

async def mailing_targets_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка полученных таргетов"""
    message = update.message
    
    targets_text = message.text.strip()
    targets = [t.strip() for t in targets_text.split('\n') if t.strip()]
    
    if not targets:
        await message.reply_text(
            "❌ Не найдено ни одной ссылки!\n\n"
            "Отправьте ссылки заново или используйте /cancel"
        )
        return USER_MAILING_TARGETS
    
    context.user_data['mailing_targets'] = targets
    
    # Переходим к выбору аккаунтов
    keyboard = [
        [InlineKeyboardButton("👥 Выбрать аккаунты", callback_data='select_accounts')],
        [InlineKeyboardButton("🚀 Использовать все", callback_data='use_all_accounts')]
    ]
    
    await message.reply_text(
        f"✅ Получено {len(targets)} ссылок\n\n"
        f"Выберите аккаунты для рассылки:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return USER_MAILING_MESSAGE

async def mailing_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщения для рассылки"""
    message = update.message
    
    context.user_data['mailing_message'] = message
    
    targets_count = len(context.user_data.get('mailing_targets', []))
    accounts_count = len(context.user_data.get('selected_accounts', []))
    
    preview = ""
    if message.text:
        preview = message.text[:100] + "..." if len(message.text) > 100 else message.text
    elif message.photo:
        preview = "[Фото]" + (f"\n{message.caption}" if message.caption else "")
    elif message.video:
        preview = "[Видео]" + (f"\n{message.caption}" if message.caption else "")
    
    keyboard = [
        [InlineKeyboardButton("✅ Запустить", callback_data='confirm_mailing')],
        [InlineKeyboardButton("❌ Отмена", callback_data='cancel_mailing')]
    ]
    
    await message.reply_text(
        f"📋 *Подтверждение рассылки*\n\n"
        f"👥 Аккаунтов: {accounts_count}\n"
        f"🎯 Чатов: {targets_count}\n"
        f"📨 Сообщение:\n{preview}\n\n"
        f"⏱ Примерное время: ~{targets_count * 5 // 60} мин",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return USER_MAILING_CONFIRM

async def cancel_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена рассылки"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    
    await query.edit_message_text(
        "❌ Рассылка отменена",
        reply_markup=get_main_menu_keyboard()
    )
    
    return ConversationHandler.END

async def start_user_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск рассылки через юзербот"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    targets = context.user_data.get('mailing_targets', [])
    mailing_message = context.user_data.get('mailing_message')
    selected_accounts = context.user_data.get('selected_accounts', [])
    
    if not targets or not mailing_message:
        await query.edit_message_text("❌ Ошибка: данные не найдены")
        return ConversationHandler.END
    
    # Получаем аккаунты
    if not selected_accounts:
        accounts = db.get_user_accounts(user_id)
        selected_accounts = [acc['id'] for acc in accounts]
    
    if not selected_accounts:
        await query.edit_message_text("❌ Нет активных аккаунтов")
        return ConversationHandler.END
    
    accounts_data = [db.get_account(acc_id) for acc_id in selected_accounts]
    accounts_data = [acc for acc in accounts_data if acc]
    
    if not accounts_data:
        await query.edit_message_text("❌ Не удалось загрузить аккаунты")
        return ConversationHandler.END
    
    await query.edit_message_text(
        f"📨 *Рассылка запущена!*\n\n"
        f"👥 Аккаунтов: {len(accounts_data)}\n"
        f"🎯 Чатов: {len(targets)}\n"
        f"📊 На аккаунт: ~{len(targets) // len(accounts_data)}",
        parse_mode='Markdown'
    )
    
    # Распределяем таргеты по аккаунтам
    targets_per_account = len(targets) // len(accounts_data)
    remainder = len(targets) % len(accounts_data)
    
    total_sent = 0
    total_errors = 0
    
    start_idx = 0
    for idx, account in enumerate(accounts_data):
        # Распределяем таргеты
        end_idx = start_idx + targets_per_account + (1 if idx < remainder else 0)
        account_targets = targets[start_idx:end_idx]
        start_idx = end_idx
        
        if not account_targets:
            continue
        
        await query.edit_message_text(
            f"📨 *Рассылка:*\n\n"
            f"🔄 Аккаунт {idx + 1}/{len(accounts_data)}\n"
            f"📱 {account['account_name']}\n"
            f"🎯 Чатов: {len(account_targets)}",
            parse_mode='Markdown'
        )
        
        # Запускаем рассылку для этого аккаунта
        sent, errors = await run_single_account_mailing(
            account, account_targets, mailing_message, context
        )
        
        total_sent += sent
        total_errors += errors
        
        # Задержка между аккаунтами
        if idx < len(accounts_data) - 1:
            await asyncio.sleep(10)
    
    success_rate = int((total_sent / len(targets)) * 100) if targets else 0
    
    await query.edit_message_text(
        f"✅ *Рассылка завершена!*\n\n"
        f"📊 *Статистика:*\n\n"
        f"👥 Использовано аккаунтов: {len(accounts_data)}\n"
        f"✅ Отправлено: {total_sent}/{len(targets)}\n"
        f"❌ Ошибок: {total_errors}\n"
        f"📈 Успешность: {success_rate}%",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )
    
    context.user_data.clear()
    return ConversationHandler.END

async def run_single_account_mailing(account: dict, targets: list, mailing_message, context):
    """Рассылка с одного аккаунта"""
    session_id = account['session_id']
    phone = account['phone_number']
    user_id = account['user_id']
    
    connect_result = await userbot_manager.connect_session(phone, session_id)
    if not connect_result['success']:
        return 0, len(targets)
    
    sent = 0
    errors = 0
    
    # Фаза 1: Вступление
    for target in targets:
        try:
            await userbot_manager.join_chat(session_id, phone, target)
            await asyncio.sleep(2)
        except:
            pass
    
    await asyncio.sleep(10)
    
    # Фаза 2: Отправка
    for target in targets:
        try:
            if mailing_message.text:
                result = await userbot_manager.send_message(
                    session_id, phone, target, mailing_message.text
                )
            elif mailing_message.photo:
                photo = mailing_message.photo[-1]
                file = await context.bot.get_file(photo.file_id)
                photo_path = f"temp_{user_id}_{photo.file_id}.jpg"
                await file.download_to_drive(photo_path)
                
                result = await userbot_manager.send_photo(
                    session_id, phone, target, photo_path,
                    caption=mailing_message.caption or ""
                )
                
                import os
                if os.path.exists(photo_path):
                    os.remove(photo_path)
            
            elif mailing_message.video:
                video = mailing_message.video
                file = await context.bot.get_file(video.file_id)
                video_path = f"temp_{user_id}_{video.file_id}.mp4"
                await file.download_to_drive(video_path)
                
                result = await userbot_manager.send_video(
                    session_id, phone, target, video_path,
                    caption=mailing_message.caption or ""
                )
                
                import os
                if os.path.exists(video_path):
                    os.remove(video_path)
            
            if result.get('success'):
                sent += 1
            else:
                errors += 1
            
            await asyncio.sleep(5)
            
        except Exception as e:
            errors += 1
            logger.error(f"Error: {e}")
    
    message_text = mailing_message.text or mailing_message.caption or "[Медиа]"
    db.add_mailing(user_id, message_text, sent, errors)
    
    return sent, errors

# ==================== ИСТОРИЯ РАССЫЛОК ====================

async def mailing_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """История рассылок"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    mailings = db.get_user_mailings(user_id, limit=10)
    
    if not mailings:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back_to_menu')]]
        await query.edit_message_text(
            "📊 История рассылок пуста",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    history_text = "📊 *История рассылок:*\n\n"
    
    for idx, mailing in enumerate(mailings, 1):
        message_preview = mailing['message'][:30] + "..." if len(mailing['message']) > 30 else mailing['message']
        date = mailing['created_at'][:16]
        
        history_text += (
            f"{idx}. 📅 {date}\n"
            f"   📨 {message_preview}\n"
            f"   ✅ Успешно: {mailing['sent_count']}\n"
            f"   ❌ Ошибок: {mailing['error_count']}\n\n"
        )
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back_to_menu')]]
    
    await query.edit_message_text(
        history_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ==================== ПОМОЩЬ ====================

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь"""
    query = update.callback_query
    await query.answer()
    
    help_text = """
ℹ️ *Справка*

*Как начать:*
1. Добавьте Telegram аккаунт
2. Создайте рассылку
3. Выберите аккаунты
4. Отправьте сообщение

*Форматы ссылок:*
• https://t.me/channel
• @username
• https://t.me/+invitehash

*Ограничения:*
• Задержка 5 сек между сообщениями
• Автоматическое вступление в группы

*Команды:*
/start - Главное меню
/cancel - Отмена операции
/admin - Админ-панель (только для админа)

*Поддержка:*
Используйте кнопку "💬 Поддержка" в меню
    """
    
    keyboard = [
        [InlineKeyboardButton("💬 Поддержка", callback_data='support')],
        [InlineKeyboardButton("◀️ Назад", callback_data='back_to_menu')]
    ]
    
    await query.edit_message_text(
        help_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ==================== ПОДДЕРЖКА ====================

async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало обращения в поддержку"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "💬 *Поддержка*\n\n"
        "Опишите вашу проблему или вопрос.\n"
        "Администратор получит ваше сообщение.\n\n"
        "Или /cancel для отмены",
        parse_mode='Markdown'
    )
    
    return SUPPORT_MESSAGE

async def support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщения в поддержку"""
    message = update.message
    user_id = update.effective_user.id
    username = update.effective_user.username or "Без username"
    
    # Отправляем админу
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 *Новое обращение*\n\n"
                 f"👤 От: {username} (ID: {user_id})\n\n"
                 f"💬 Сообщение:\n{message.text}",
            parse_mode='Markdown'
        )
        
        await message.reply_text(
            "✅ Ваше сообщение отправлено администратору!\n"
            "Ожидайте ответа.",
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Error sending to admin: {e}")
        await message.reply_text(
            "❌ Ошибка отправки. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )
    
    return ConversationHandler.END

# ==================== АДМИНКА ====================

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика для админа"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Нет доступа", show_alert=True)
        return
    
    stats = db.get_stats()
    
    stats_text = f"""
📊 *Детальная статистика*

👥 *Пользователи:*
• Всего: {stats.get('total_users', 0)}
• Активных: {stats.get('active_users', 0)}
• Новых за сегодня: {stats.get('new_today', 0)}

📱 *Аккаунты:*
• Всего подключено: {stats.get('total_accounts', 0)}
• Активных: {stats.get('active_accounts', 0)}

📨 *Рассылки:*
• Всего: {stats.get('total_mailings', 0)}
• За сегодня: {stats.get('mailings_today', 0)}
• Сообщений отправлено: {stats.get('total_sent', 0)}

⏰ *Запланировано:*
• Рассылок: {stats.get('total_scheduled', 0)}
    """
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='admin_menu')]]
    
    await query.edit_message_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список пользователей"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Нет доступа", show_alert=True)
        return
    
    users = db.get_all_users(limit=10)
    
    if not users:
        await query.edit_message_text("👥 Пользователей нет")
        return
    
    users_text = "👥 *Последние пользователи:*\n\n"
    
    for idx, user in enumerate(users, 1):
        username = user.get('username') or 'Без username'
        accounts_count = len(db.get_user_accounts(user['user_id']))
        
        users_text += (
            f"{idx}. {username} (ID: {user['user_id']})\n"
            f"   📱 Аккаунтов: {accounts_count}\n"
            f"   📅 Регистрация: {user['created_at'][:10]}\n\n"
        )
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='admin_menu')]]
    
    await query.edit_message_text(
        users_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_mailing_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало админской рассылки"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Нет доступа", show_alert=True)
        return ConversationHandler.END
    
    await query.edit_message_text(
        "📮 *Рассылка всем пользователям*\n\n"
        "Отправьте сообщение для рассылки:\n"
        "(текст, фото или видео)\n\n"
        "Или /cancel для отмены",
        parse_mode='Markdown'
    )
    
    return ADMIN_MAILING_MESSAGE

async def admin_mailing_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение сообщения для админской рассылки"""
    message = update.message
    context.user_data['admin_mailing_message'] = message
    
    all_users = db.get_all_users()
    users_count = len(all_users)
    
    preview = ""
    if message.text:
        preview = message.text[:100] + "..." if len(message.text) > 100 else message.text
    elif message.photo:
        preview = "[Фото]" + (f"\n{message.caption}" if message.caption else "")
    elif message.video:
        preview = "[Видео]" + (f"\n{message.caption}" if message.caption else "")
    
    keyboard = [
        [InlineKeyboardButton("✅ Отправить", callback_data='admin_confirm_mailing')],
        [InlineKeyboardButton("❌ Отмена", callback_data='back_to_menu')]
    ]
    
    await message.reply_text(
        f"📋 *Подтверждение рассылки*\n\n"
        f"👥 Получателей: {users_count}\n"
        f"📨 Сообщение:\n{preview}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ADMIN_MAILING_CONFIRM

async def admin_mailing_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение и запуск админской рассылки"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Нет доступа", show_alert=True)
        return ConversationHandler.END
    
    mailing_msg = context.user_data.get('admin_mailing_message')
    if not mailing_msg:
        await query.edit_message_text("❌ Сообщение не найдено")
        return ConversationHandler.END
    
    all_users = db.get_all_users()
    
    await query.edit_message_text(
        f"📮 Рассылка запущена!\n\n"
        f"👥 Пользователей: {len(all_users)}"
    )
    
    sent = 0
    errors = 0
    
    for user in all_users:
        try:
            if mailing_msg.text:
                await context.bot.send_message(
                    chat_id=user['user_id'],
                    text=mailing_msg.text
                )
            elif mailing_msg.photo:
                await context.bot.send_photo(
                    chat_id=user['user_id'],
                    photo=mailing_msg.photo[-1].file_id,
                    caption=mailing_msg.caption
                )
            elif mailing_msg.video:
                await context.bot.send_video(
                    chat_id=user['user_id'],
                    video=mailing_msg.video.file_id,
                    caption=mailing_msg.caption
                )
            
            sent += 1
            await asyncio.sleep(0.05)  # Защита от флуда
            
        except Exception as e:
            errors += 1
            logger.error(f"Error sending to {user['user_id']}: {e}")
    
    await query.edit_message_text(
        f"✅ *Рассылка завершена!*\n\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Ошибок: {errors}",
        parse_mode='Markdown',
        reply_markup=get_admin_keyboard()
    )
    
    context.user_data.clear()
    return ConversationHandler.END

async def admin_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ожидающие оплаты"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Нет доступа", show_alert=True)
        return
    
    # Заглушка - реализуй логику получения платежей из БД
    await query.edit_message_text(
        "💳 *Ожидающие оплаты*\n\n"
        "Функция в разработке...",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад", callback_data='admin_menu')
        ]])
    )

async def admin_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Бэкап базы данных"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Нет доступа", show_alert=True)
        return
    
    try:
        import shutil
        from datetime import datetime
        
        # Создаем бэкап
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f"backup_{timestamp}.db"
        shutil.copy('userbot_manager.db', backup_file)
        
        # Отправляем файл
        with open(backup_file, 'rb') as f:
            await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=f,
                filename=backup_file,
                caption="💾 Бэкап базы данных"
            )
        
        # Удаляем временный файл
        os.remove(backup_file)
        
        await query.edit_message_text(
            "✅ Бэкап создан и отправлен!",
            reply_markup=get_admin_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Backup error: {e}")
        await query.edit_message_text(
            f"❌ Ошибка создания бэкапа: {e}",
            reply_markup=get_admin_keyboard()
        )

async def admin_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в админ меню"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Нет доступа", show_alert=True)
        return
    
    stats = db.get_stats()
    
    admin_text = f"""
🔧 *Панель администратора*

📊 *Статистика:*
👥 Всего пользователей: {stats.get('total_users', 0)}
📱 Всего аккаунтов: {stats.get('total_accounts', 0)}
📨 Всего рассылок: {stats.get('total_mailings', 0)}
⏰ Запланировано: {stats.get('total_scheduled', 0)}
    """
    
    await query.edit_message_text(
        admin_text,
        reply_markup=get_admin_keyboard(),
        parse_mode='Markdown'
    )

# ==================== MAIN ====================

def main():
    """Запуск бота"""
    application = Application.builder().token(MANAGER_BOT_TOKEN).build()
    
    # ==================== ConversationHandlers ====================
    
    # Подключение аккаунта
    connect_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(connect_start, pattern='^connect_userbot$')],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_code)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Рассылка пользователя
    user_mailing_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_mailing, pattern='^start_mailing$')],
        states={
            USER_MAILING_TARGETS: [MessageHandler(filters.TEXT & ~filters.COMMAND, mailing_targets_received)],
            USER_MAILING_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, mailing_message_received),
                MessageHandler(filters.PHOTO, mailing_message_received),
                MessageHandler(filters.VIDEO, mailing_message_received),
                CallbackQueryHandler(use_all_accounts, pattern='^use_all_accounts$'),
                CallbackQueryHandler(select_accounts_for_mailing, pattern='^select_accounts$')
            ],
            USER_MAILING_CONFIRM: [
                CallbackQueryHandler(start_user_mailing, pattern='^confirm_mailing$'),
                CallbackQueryHandler(cancel_mailing, pattern='^cancel_mailing$')
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Админская рассылка
    admin_mailing_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_mailing_start, pattern='^admin_mailing$')],
        states={
            ADMIN_MAILING_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_mailing_message),
                MessageHandler(filters.PHOTO, admin_mailing_message),
                MessageHandler(filters.VIDEO, admin_mailing_message)
            ],
            ADMIN_MAILING_CONFIRM: [
                CallbackQueryHandler(admin_mailing_confirm, pattern='^admin_confirm_mailing$'),
                CallbackQueryHandler(back_to_menu_callback, pattern='^back_to_menu$')
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Поддержка
    support_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(support_start, pattern='^support$')],
        states={
            SUPPORT_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_message)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # ==================== Команды ====================
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('admin', admin_panel))
    application.add_handler(CommandHandler('cancel', cancel))
    
    # ==================== ConversationHandlers ====================
    application.add_handler(connect_conv_handler)
    application.add_handler(user_mailing_handler)
    application.add_handler(admin_mailing_handler)
    application.add_handler(support_handler)
    
    # ==================== Callback Handlers ====================
    
    # Главное меню
    application.add_handler(CallbackQueryHandler(back_to_menu_callback, pattern='^back_to_menu$'))
    application.add_handler(CallbackQueryHandler(check_subscription_callback, pattern='^check_subscription$'))
    
    # Аккаунты
    application.add_handler(CallbackQueryHandler(accounts_menu, pattern='^accounts_menu$'))
    application.add_handler(CallbackQueryHandler(account_detail, pattern='^account_\d+$'))
    application.add_handler(CallbackQueryHandler(delete_account_confirm, pattern='^delete_account_\d+$'))
    application.add_handler(CallbackQueryHandler(confirm_delete_account, pattern='^confirm_delete_\d+$'))
    
    # Планировщик
    application.add_handler(CallbackQueryHandler(schedule_mailing_menu, pattern='^schedule_menu$'))
    application.add_handler(CallbackQueryHandler(my_schedules, pattern='^my_schedules$'))
    application.add_handler(CallbackQueryHandler(schedule_detail, pattern='^schedule_detail_\d+$'))
    application.add_handler(CallbackQueryHandler(delete_schedule, pattern='^delete_schedule_\d+$'))
    
    # Выбор аккаунтов
    application.add_handler(CallbackQueryHandler(toggle_account_selection, pattern='^toggle_account_\d+$'))
    application.add_handler(CallbackQueryHandler(select_all_accounts, pattern='^select_all_accounts$'))
    application.add_handler(CallbackQueryHandler(deselect_all_accounts, pattern='^deselect_all_accounts$'))
    application.add_handler(CallbackQueryHandler(continue_with_selected, pattern='^continue_with_selected$'))
    
    # История рассылок
    application.add_handler(CallbackQueryHandler(mailing_history, pattern='^mailing_history$'))
    
    # Помощь
    application.add_handler(CallbackQueryHandler(help_callback, pattern='^help$'))
    
    # Админка
    application.add_handler(CallbackQueryHandler(admin_stats, pattern='^admin_stats$'))
    application.add_handler(CallbackQueryHandler(admin_users, pattern='^admin_users$'))
    application.add_handler(CallbackQueryHandler(admin_payments, pattern='^admin_payments$'))
    application.add_handler(CallbackQueryHandler(admin_backup, pattern='^admin_backup$'))
    application.add_handler(CallbackQueryHandler(admin_menu_callback, pattern='^admin_menu$'))
    
    # Запуск
    logger.info("🤖 Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()