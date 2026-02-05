#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Bot Manager for Mass Mailing
"""

import logging
import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, List

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# Импорты из наших модулей
from database import Database
from userbot import UserbotManager
from scheduler import MailingScheduler
from config_userbot import (
    BOT_TOKEN,
    ADMIN_ID,
    SUBSCRIPTIONS,
    CHANNEL_ID,
    PAYMENT_METHODS,
    SUPPORT_USERNAME
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ СОСТОЯНИЙ ====================

# Подключение аккаунта
PHONE, CODE, PASSWORD = range(3)

# Рассылка
MAILING_TARGETS = 10
MAILING_ACCOUNTS = 11
MAILING_MESSAGE = 12
MAILING_CONFIRM = 13

# Планировщик
SCHEDULE_TARGETS = 100
SCHEDULE_ACCOUNTS = 101
SCHEDULE_MESSAGE = 102
SCHEDULE_TYPE = 103
SCHEDULE_TIME = 104
SCHEDULE_CONFIRM = 105

# Админ рассылка
ADMIN_MAILING_MESSAGE = 200
ADMIN_MAILING_CONFIRM = 201

# Поддержка
SUPPORT_MESSAGE = 300

# ==================== ИНИЦИАЛИЗАЦИЯ ====================

# Инициализация
db = Database()
userbot_manager = UserbotManager()
# mailing_scheduler инициализируется в main() после создания application

# ==================== КЛАВИАТУРЫ ====================

def get_main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Создать клавиатуру главного меню"""
    keyboard = [
        ['📨 Создать рассылку', '📱 Мои аккаунты'],
        ['⏰ Планировщик', '📜 История'],
        ['📊 Мой статус', '💎 Тарифы'],
        ['ℹ️ Помощь']
    ]
    
    # Добавляем админ кнопку
    if user_id == ADMIN_ID:
        keyboard.append(['⚙️ Админ'])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

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
    if not CHANNEL_ID or CHANNEL_ID == '@test':
        # Если канал не настроен - пропускаем проверку
        return True
    
    try:
        # Получаем информацию о пользователе в канале
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        
        # Проверяем статус
        if member.status in ['member', 'administrator', 'creator']:
            return True
        
        return False
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        # В случае ошибки пропускаем проверку
        return True

def check_user_limits(user_id: int, action: str = 'account') -> dict:
    """
    Проверка лимитов пользователя
    action: 'account' или 'mailing'
    """
    user_data = db.get_user(user_id)
    
    if not user_data:
        return {
            'allowed': False,
            'reason': 'Пользователь не найден'
        }
    
    # Парсим дату если это строка
    subscription_end = user_data['subscription_end']
    if isinstance(subscription_end, str):
        try:
            subscription_end = datetime.fromisoformat(subscription_end)
        except:
            subscription_end = datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S.%f')
    
    # Проверяем активность подписки
    subscription_active = subscription_end > datetime.now()
    
    if not subscription_active:
        return {
            'allowed': False,
            'reason': '⚠️ Подписка истекла!\n\nПродлите подписку для продолжения работы',
            'need_subscription': True
        }
    
    plan_id = user_data['subscription_plan']
    plan = SUBSCRIPTIONS.get(plan_id)
    
    if not plan:
        return {
            'allowed': False,
            'reason': 'Неизвестный тариф'
        }
    
    if action == 'account':
        # Проверка лимита аккаунтов
        max_accounts = plan.get('max_accounts', 1)
        if max_accounts == -1:  # Безлимит
            return {'allowed': True}
        
        current_accounts = len(db.get_user_accounts(user_id))
        
        if current_accounts >= max_accounts:
            return {
                'allowed': False,
                'reason': f'⚠️ Достигнут лимит аккаунтов!\n\n'
                         f'Текущий тариф: {plan["name"]}\n'
                         f'Лимит: {max_accounts} аккаунтов\n'
                         f'Используется: {current_accounts}\n\n'
                         f'Обновите тариф для добавления новых аккаунтов'
            }
    
    elif action == 'mailing':
        # Проверка лимита рассылок
        max_mailings = plan.get('max_mailings_per_day', 3)
        if max_mailings == -1:  # Безлимит
            return {'allowed': True}
        
        mailings_today = db.get_user_mailings_today(user_id)
        
        if mailings_today >= max_mailings:
            return {
                'allowed': False,
                'reason': f'⚠️ Достигнут лимит рассылок на сегодня!\n\n'
                         f'Текущий тариф: {plan["name"]}\n'
                         f'Лимит: {max_mailings} рассылок/день\n'
                         f'Использовано сегодня: {mailings_today}\n\n'
                         f'Обновите тариф или дождитесь завтра'
            }
    
    return {'allowed': True}

async def accounts_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню аккаунтов через callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    accounts = db.get_user_accounts(user_id)
    
    if not accounts:
        text = (
            "📱 *Управление аккаунтами*\n\n"
            "У вас пока нет подключенных аккаунтов\n\n"
            "Добавьте Telegram аккаунт для начала работы"
        )
        keyboard = [
            [InlineKeyboardButton("➕ Добавить аккаунт", callback_data='connect_userbot')],
            [InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')]
        ]
    else:
        text = f"📱 *Управление аккаунтами*\n\nПодключено: {len(accounts)}\n\n"
        
        keyboard = []
        for acc in accounts:
            keyboard.append([
                InlineKeyboardButton(
                    f"📱 {acc['account_name']} ({acc['phone']})",
                    callback_data=f"account_{acc['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("➕ Добавить аккаунт", callback_data='connect_userbot')])
        keyboard.append([InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')])
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def get_user_status_text(user_id: int) -> str:
    """Получить текст статуса пользователя"""
    user_data = db.get_user(user_id)
    
    if not user_data:
        return "❌ Данные не найдены"
    
    plan = SUBSCRIPTIONS.get(user_data['subscription_plan'], SUBSCRIPTIONS['trial'])
    subscription_active = user_data['subscription_end'] > datetime.now()
    
    days_left = (user_data['subscription_end'] - datetime.now()).days
    
    accounts = db.get_user_accounts(user_id)
    today_mailings = db.get_user_mailings_today(user_id)
    
    max_accounts = plan.get('max_accounts', 1)
    max_mailings = plan.get('max_mailings_per_day', 5)
    
    accounts_text = f"{len(accounts)}/{max_accounts if max_accounts != -1 else '∞'}"
    mailings_text = f"{today_mailings}/{max_mailings if max_mailings != -1 else '∞'}"
    
    status_emoji = "✅" if subscription_active else "❌"
    
    text = f"""
📊 *Ваш статус*

👤 ID: `{user_id}`
📦 Тариф: {plan['name']}
{status_emoji} Статус: {'Активна' if subscription_active else 'Истекла'}
⏰ Осталось дней: {days_left if days_left > 0 else 0}
📅 Действует до: {user_data['subscription_end'].strftime('%d.%m.%Y %H:%M')}

📱 Аккаунтов: {accounts_text}
📨 Рассылок сегодня: {mailings_text}
    """
    
    return text

# ==================== КОМАНДЫ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    user_id = user.id
    username = user.username
    
    # Проверяем подписку
    if not await check_subscription(user_id, context):
        keyboard = []
        if CHANNEL_ID and CHANNEL_ID != '@test':
            keyboard.append([InlineKeyboardButton(
                "📢 Подписаться на канал",
                url=f"https://t.me/{CHANNEL_ID.replace('@', '')}"
            )])
        keyboard.append([InlineKeyboardButton(
            "✅ Я подписался",
            callback_data='check_subscription'
        )])
        
        await update.message.reply_text(
            "⚠️ *Для использования бота требуется подписка на канал*\n\n"
            f"Подпишитесь на {CHANNEL_ID} и нажмите кнопку ниже",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Добавляем пользователя в БД
    db.add_user(user_id, username)
    
    # Показываем главное меню
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        f"🤖 Я бот для автоматизации рассылок в Telegram\n\n"
        f"Выберите действие:",
        reply_markup=get_main_menu_keyboard(user_id)
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
💰 Активных подписок: {stats.get('active_subscriptions', 0)}
📅 Новых за сегодня: {stats.get('new_today', 0)}

📱 *Аккаунты:*
• Всего подключено: {stats.get('total_accounts', 0)}
• Активных: {stats.get('active_accounts', 0)}

📨 *Рассылки:*
• Всего: {stats.get('total_mailings', 0)}
• За сегодня: {stats.get('mailings_today', 0)}
• Сообщений отправлено: {stats.get('total_sent', 0)}

💎 *По тарифам:*
• Пробный: {stats.get('trial_users', 0)}
• Любительская: {stats.get('amateur_users', 0)}
• Профессиональная: {stats.get('professional_users', 0)}
• Премиум: {stats.get('premium_users', 0)}
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
        reply_markup=get_main_menu_keyboard(update.effective_user.id)
    )
    return ConversationHandler.END

# ==================== CALLBACK ОБРАБОТЧИКИ ====================

async def back_to_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Удаляем сообщение с inline кнопками
    try:
        await query.message.delete()
    except:
        pass
    
    # Отправляем новое с обычными кнопками
    await context.bot.send_message(
        chat_id=user_id,
        text="🏠 Главное меню\n\nВыберите действие:",
        reply_markup=get_main_menu_keyboard(user_id)
    )

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка подписки callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    is_subscribed = await check_subscription(user_id, context)
    
    if is_subscribed:
        await start(update, context)
    else:
        await query.answer("❌ Вы ещё не подписались!", show_alert=True)

async def my_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статус пользователя"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    if not user_data:
        await query.edit_message_text(
            "❌ Данные не найдены",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')
            ]])
        )
        return
    
    # Парсим дату
    subscription_end = user_data['subscription_end']
    if isinstance(subscription_end, str):
        try:
            subscription_end = datetime.fromisoformat(subscription_end)
        except:
            subscription_end = datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S.%f')
    
    plan_id = user_data['subscription_plan']
    plan = SUBSCRIPTIONS.get(plan_id, {})
    
    # Проверяем активность
    subscription_active = subscription_end > datetime.now()
    days_left = (subscription_end - datetime.now()).days if subscription_active else 0
    
    # Получаем данные
    accounts = db.get_user_accounts(user_id)
    mailings_today = db.get_user_mailings_today(user_id)
    
    # Лимиты
    max_accounts = plan.get('max_accounts', 1)
    max_mailings = plan.get('max_mailings_per_day', 3)
    
    accounts_text = f"{len(accounts)}/{max_accounts}" if max_accounts != -1 else f"{len(accounts)}/♾"
    mailings_text = f"{mailings_today}/{max_mailings}" if max_mailings != -1 else f"{mailings_today}/♾"
    
    status_emoji = "✅" if subscription_active else "❌"
    status_text = f"Активна ({days_left} дн.)" if subscription_active else "Истекла"
    
    text = (
        f"📊 *Ваш статус*\n\n"
        f"💎 Тариф: {plan.get('name', 'Неизвестно')}\n"
        f"{status_emoji} Подписка: {status_text}\n"
        f"📅 До: {subscription_end.strftime('%d.%m.%Y')}\n\n"
        f"📊 *Использование:*\n"
        f"📱 Аккаунтов: {accounts_text}\n"
        f"📨 Рассылок сегодня: {mailings_text}\n"
    )
    
    keyboard = [[InlineKeyboardButton("💎 Тарифы", callback_data="view_tariffs")]]
    if not subscription_active or days_left < 3:
        keyboard.insert(0, [InlineKeyboardButton("🔄 Продлить", callback_data="view_tariffs")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def view_tariffs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать тарифы"""
    query = update.callback_query
    await query.answer()
    
    text = "💎 *Доступные тарифы*\n\n"
    
    keyboard = []
    for plan_id, plan in SUBSCRIPTIONS.items():
        price_text = "Бесплатно" if plan['price'] == 0 else f"{plan['price']}₽/мес"
        
        text += (
            f"{plan['name']}\n"
            f"💰 {price_text}\n"
            f"📱 Аккаунтов: {plan['max_accounts'] if plan['max_accounts'] != -1 else '♾'}\n"
            f"📨 Рассылок/день: {plan['max_mailings_per_day'] if plan['max_mailings_per_day'] != -1 else '♾'}\n"
            f"⏱ {plan['days']} дней\n\n"
        )
        
        if plan['price'] > 0:
            keyboard.append([InlineKeyboardButton(
                f"💎 Купить {plan['name']} - {plan['price']}₽",
                callback_data=f"buy_{plan_id}"
            )])
    
    keyboard.append([InlineKeyboardButton("🏠 Меню", callback_data="back_to_menu")])
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def select_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор тарифа для покупки"""
    query = update.callback_query
    await query.answer()
    
    plan_id = query.data.replace('buy_', '')
    plan = SUBSCRIPTIONS.get(plan_id)
    
    if not plan:
        await query.edit_message_text(
            "❌ Тариф не найден",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')
            ]])
        )
        return
    
    # Сохраняем выбор
    context.user_data['selected_plan'] = plan_id
    
    text = (
        f"💎 *{plan['name']}*\n\n"
        f"💰 Стоимость: {plan['price']}₽\n"
        f"⏱ Срок: {plan['days']} дней\n"
        f"📱 Аккаунтов: {plan['max_accounts'] if plan['max_accounts'] != -1 else '♾'}\n"
        f"📨 Рассылок/день: {plan['max_mailings_per_day'] if plan['max_mailings_per_day'] != -1 else '♾'}\n\n"
        f"Выберите способ оплаты:"
    )
    
    keyboard = [
        [InlineKeyboardButton("💳 Сбербанк", callback_data=f"payment_method_sber_{plan_id}")],
        [InlineKeyboardButton("💳 Тинькофф", callback_data=f"payment_method_tinkoff_{plan_id}")],
        [InlineKeyboardButton("💰 ЮMoney", callback_data=f"payment_method_yoomoney_{plan_id}")],
        [InlineKeyboardButton("₿ USDT TRC20", callback_data=f"payment_method_usdt_{plan_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="view_tariffs")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== ПЛАТЕЖИ ====================

async def subscribe_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор тарифа для покупки"""
    query = update.callback_query
    await query.answer()
    
    plan_id = query.data.split('_')[1]  # subscribe_amateur -> amateur
    plan = SUBSCRIPTIONS.get(plan_id)
    
    if not plan:
        await query.edit_message_text("❌ Тариф не найден")
        return
    
    user_id = update.effective_user.id
    
    # Создаем платеж
    payment_id = db.add_payment(user_id, plan_id, plan['price'])
    
    if not payment_id:
        await query.edit_message_text(
            "❌ Ошибка создания платежа\nПопробуйте позже",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data='view_tariffs')
            ]])
        )
        return
    
    max_accounts = plan.get('max_accounts', 1)
    max_mailings = plan.get('max_mailings_per_day', 3)
    
    accounts_text = "♾ Безлимит" if max_accounts == -1 else f"{max_accounts} шт"
    mailings_text = "♾ Безлимит" if max_mailings == -1 else f"{max_mailings}/день"
    
    payment_text = (
        f"💎 *Оформление подписки*\n\n"
        f"📦 Тариф: {plan['name']}\n"
        f"💰 Стоимость: {plan['price']}₽\n"
        f"📅 Период: {plan['days']} дней\n\n"
        f"📊 *Включено:*\n"
        f"📱 Аккаунтов: {accounts_text}\n"
        f"📨 Рассылок: {mailings_text}\n\n"
        f"🔢 ID платежа: #{payment_id}\n\n"
        f"💳 *Реквизиты для оплаты:*\n\n"
    )
    
    # Добавляем реквизиты из config
    for method, details in PAYMENT_METHODS.items():
        payment_text += f"*{details['name']}:*\n`{details['wallet']}`\n\n"
    
    payment_text += (
        f"⚠️ *Важно:*\n"
        f"После оплаты отправьте скриншот чека боту\n"
        f"или нажмите кнопку «Я оплатил»\n\n"
        f"Платеж будет проверен администратором"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Я оплатил", callback_data=f'paid_{payment_id}')],
        [InlineKeyboardButton("❌ Отменить", callback_data='view_tariffs')]
    ]
    
    await query.edit_message_text(
        payment_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def payment_sent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение отправки платежа"""
    query = update.callback_query
    await query.answer()
    
    payment_id = int(query.data.split('_')[1])  # paid_123 -> 123
    user_id = update.effective_user.id
    username = update.effective_user.username or "не указан"
    
    # Получаем данные платежа
    payment = db.get_payment(payment_id)
    
    if not payment:
        await query.edit_message_text("❌ Платеж не найден")
        return
    
    if payment['user_id'] != user_id:
        await query.edit_message_text("❌ Это не ваш платеж")
        return
    
    if payment['status'] != 'pending':
        await query.edit_message_text(
            f"ℹ️ Платеж уже обработан\n\n"
            f"Статус: {payment['status']}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')
            ]])
        )
        return
    
    # Уведомляем пользователя
    await query.edit_message_text(
        f"✅ *Платеж отправлен на проверку!*\n\n"
        f"🔢 ID: #{payment_id}\n"
        f"💰 Сумма: {payment['amount']}₽\n\n"
        f"⏳ Ожидайте проверки администратором\n"
        f"Обычно это занимает до 30 минут\n\n"
        f"📬 Вам придет уведомление после проверки",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 В меню", callback_data='back_to_menu')
        ]])
    )
    
    # Уведомляем админа
    plan = SUBSCRIPTIONS.get(payment['plan_id'])
    
    if not plan:
        logger.error(f"Plan {payment['plan_id']} not found")
        return
    
    admin_text = (
        f"💰 *Новый платеж!*\n\n"
        f"🔢 ID: #{payment_id}\n"
        f"👤 User ID: `{user_id}`\n"
        f"👤 Username: @{username}\n"
        f"💎 Тариф: {plan['name']}\n"
        f"💰 Сумма: {payment['amount']}₽\n"
        f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Проверьте оплату и подтвердите:"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f'approve_payment_{payment_id}'),
            InlineKeyboardButton("❌ Отклонить", callback_data=f'reject_payment_{payment_id}')
        ]
    ]
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        logger.info(f"✅ Admin notification sent for payment #{payment_id}")
    except Exception as e:
        logger.error(f"❌ Error sending admin notification: {e}")

async def select_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор способа оплаты"""
    query = update.callback_query
    await query.answer()
    
    # Парсим callback: payment_method_sber_starter
    parts = query.data.split('_')
    payment_method = parts[2]  # sber/tinkoff/yoomoney/usdt
    plan_id = parts[3] if len(parts) > 3 else context.user_data.get('selected_plan')
    
    if not plan_id:
        await query.edit_message_text(
            "❌ Ошибка: тариф не выбран",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')
            ]])
        )
        return
    
    plan = SUBSCRIPTIONS.get(plan_id)
    if not plan:
        await query.edit_message_text(
            "❌ Тариф не найден",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')
            ]])
        )
        return
    
    # Создаем платеж
    user_id = update.effective_user.id
    payment_id = db.add_payment(user_id, plan_id, plan['price'])
    
    if not payment_id:
        await query.edit_message_text(
            "❌ Ошибка создания платежа",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')
            ]])
        )
        return
    
    # Реквизиты в зависимости от метода
    if payment_method == 'sber':
        payment_details = (
            "💳 *Сбербанк*\n\n"
            "Карта: `2202 2068 7768 8616`\n"
            "Получатель: Иван И.\n\n"
        )
    elif payment_method == 'tinkoff':
        payment_details = (
            "💳 *Тинькофф*\n\n"
            "Карта: `5536 9137 7654 3210`\n"
            "Получатель: Иван И.\n\n"
        )
    elif payment_method == 'yoomoney':
        payment_details = (
            "💰 *ЮMoney*\n\n"
            "Кошелек: `410011234567890`\n\n"
        )
    elif payment_method == 'usdt':
        payment_details = (
            "₿ *USDT TRC20*\n\n"
            "Адрес: `TQx5Yr8RqXKvn3p2J7mL9nS8WcD6FvH4Tz`\n\n"
        )
    else:
        payment_details = ""
    
    text = (
        f"💳 *Оплата {plan['name']}*\n\n"
        f"Сумма: *{plan['price']}₽*\n"
        f"ID платежа: #{payment_id}\n\n"
        f"{payment_details}"
        f"⚠️ *Важно:*\n"
        f"1. Переведите точную сумму: {plan['price']}₽\n"
        f"2. После оплаты нажмите кнопку ниже\n"
        f"3. Ожидайте проверки (до 30 минут)\n\n"
        f"❓ Вопросы: @{SUPPORT_USERNAME}"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Я оплатил", callback_data=f"paid_{payment_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="view_tariffs")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Одобрение платежа (админ)"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await query.answer("❌ Доступ запрещен", show_alert=True)
        return
    
    payment_id = int(query.data.split('_')[-1])
    payment = db.get_payment(payment_id)
    
    if not payment:
        await query.edit_message_text("❌ Платеж не найден")
        return
    
    if payment['status'] != 'pending':
        await query.answer(f"Платеж уже обработан: {payment['status']}", show_alert=True)
        return
    
    # Обновляем статус платежа
    db.update_payment_status(payment_id, 'approved')
    
    # Обновляем подписку пользователя
    plan = SUBSCRIPTIONS.get(payment['plan_id'])
    db.update_user_subscription(payment['user_id'], payment['plan_id'], plan['days'])
    
    # Уведомляем пользователя
    max_accounts = plan.get('max_accounts', 1)
    max_mailings = plan.get('max_mailings_per_day', 3)
    
    accounts_text = "♾ Безлимит" if max_accounts == -1 else f"{max_accounts} шт"
    mailings_text = "♾ Безлимит" if max_mailings == -1 else f"{mailings_today}/♾"
    
    try:
        await context.bot.send_message(
            chat_id=payment['user_id'],
            text=(
                f"✅ *Платеж одобрен!*\n\n"
                f"💎 Тариф: {plan['name']}\n"
                f"📅 Активен: {plan['days']} дней\n\n"
                f"📊 *Ваши лимиты:*\n"
                f"📱 Аккаунтов: {accounts_text}\n"
                f"📨 Рассылок: {mailings_text}\n\n"
                f"Спасибо за покупку! 🎉"
            ),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error notifying user: {e}")
    
    # Обновляем сообщение админа
    await query.edit_message_text(
        f"{query.message.text}\n\n✅ *ОДОБРЕНО*",
        parse_mode='Markdown'
    )


async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отклонение платежа (админ)"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await query.answer("❌ Доступ запрещен", show_alert=True)
        return
    
    payment_id = int(query.data.split('_')[-1])
    payment = db.get_payment(payment_id)
    
    if not payment:
        await query.edit_message_text("❌ Платеж не найден")
        return
    
    if payment['status'] != 'pending':
        await query.answer(f"Платеж уже обработан: {payment['status']}", show_alert=True)
        return
    
    # Обновляем статус
    db.update_payment_status(payment_id, 'rejected')
    
    # Уведомляем пользователя
    try:
        await context.bot.send_message(
            chat_id=payment['user_id'],
            text=(
                f"❌ *Платеж отклонен*\n\n"
                f"🔢 ID: #{payment_id}\n\n"
                f"Возможные причины:\n"
                f"• Неверная сумма\n"
                f"• Платеж не найден\n"
                f"• Неверные реквизиты\n\n"
                f"Обратитесь в поддержку для уточнения"
            ),
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💬 Поддержка", url=f"https://t.me/{SUPPORT_USERNAME}")
            ]])
        )
    except Exception as e:
        logger.error(f"Error notifying user: {e}")
    
    # Обновляем сообщение админа
    await query.edit_message_text(
        f"{query.message.text}\n\n❌ *ОТКЛОНЕНО*",
        parse_mode='Markdown'
    )

# ==================== ПОДКЛЮЧЕНИЕ АККАУНТОВ ====================

async def connect_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало подключения юзербота"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Проверяем лимиты
    limits = check_user_limits(user_id, 'account')
    if not limits['allowed']:
        await query.edit_message_text(
            f"⚠️ {limits['reason']}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💎 Тарифы", callback_data="view_tariffs")
            ]])
        )
        return ConversationHandler.END
    
    await query.edit_message_text(
        "📱 *Подключение аккаунта*\n\n"
        "Шаг 1: Отправьте номер телефона\n"
        "Формат: +79991234567\n\n"
        "Или /cancel для отмены",
        parse_mode='Markdown'
    )
    
    return PHONE

async def connect_userbot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало подключения юзербота (callback версия)"""
    query = update.callback_query
    if query:
        await query.answer()
        user_id = update.effective_user.id
        
        # Проверяем лимиты
        limits = check_user_limits(user_id, 'account')
        if not limits['allowed']:
            await query.edit_message_text(
                f"⚠️ {limits['reason']}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💎 Тарифы", callback_data="view_tariffs"),
                    InlineKeyboardButton("🏠 Меню", callback_data="back_to_menu")
                ]])
            )
            return ConversationHandler.END
        
        await query.edit_message_text(
            "📱 *Подключение аккаунта*\n\n"
            "Шаг 1: Отправьте номер телефона\n\n"
            "Формат: +79991234567\n"
            "Или /cancel для отмены",
            parse_mode='Markdown'
        )
        
        return PHONE
    else:
        # Если вызвана как команда /connect
        user_id = update.effective_user.id
        
        limits = check_user_limits(user_id, 'account')
        if not limits['allowed']:
            await update.message.reply_text(
                f"⚠️ {limits['reason']}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💎 Тарифы", callback_data="view_tariffs")
                ]])
            )
            return ConversationHandler.END
        
        await update.message.reply_text(
            "📱 *Подключение аккаунта*\n\n"
            "Шаг 1: Отправьте номер телефона\n\n"
            "Формат: +79991234567\n"
            "Или /cancel для отмены",
            parse_mode='Markdown'
        )
        
        return PHONE


async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен номер телефона"""
    phone = update.message.text.strip()
    user_id = update.effective_user.id
    
    # Валидация номера
    if not phone.startswith('+'):
        await update.message.reply_text(
            "❌ Неверный формат!\n\n"
            "Номер должен начинаться с +\n"
            "Пример: +79991234567\n\n"
            "Попробуйте снова или /cancel"
        )
        return PHONE
    
    # Сохраняем номер
    context.user_data['phone'] = phone
    
    # Отправляем код
    await update.message.reply_text("⏳ Отправка кода...")
    
    result = await userbot_manager.send_code(phone)
    
    if not result['success']:
        await update.message.reply_text(
            f"❌ Ошибка отправки кода!\n\n"
            f"Причина: {result.get('error', 'Неизвестная ошибка')}\n\n"
            f"Попробуйте другой номер или /cancel",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Повторить", callback_data='connect_userbot'),
                InlineKeyboardButton("❌ Отмена", callback_data='back_to_menu')
            ]])
        )
        return ConversationHandler.END
    
    # Сохраняем phone_code_hash
    context.user_data['phone_code_hash'] = result['phone_code_hash']
    
    await update.message.reply_text(
        "✅ Код отправлен!\n\n"
        "📲 Введите код из Telegram\n"
        "Формат: 12345\n\n"
        "Или /cancel для отмены"
    )
    
    return CODE


async def code_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен код подтверждения"""
    code = update.message.text.strip()
    user_id = update.effective_user.id
    
    phone = context.user_data.get('phone')
    phone_code_hash = context.user_data.get('phone_code_hash')
    
    if not phone or not phone_code_hash:
        await update.message.reply_text(
            "❌ Ошибка: данные сессии потеряны\n\n"
            "Начните подключение заново",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Заново", callback_data='connect_userbot')
            ]])
        )
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ Проверка кода...")
    
    # Авторизуемся
    result = await userbot_manager.sign_in(phone, code, phone_code_hash)
    
    if not result['success']:
        error = result.get('error', 'Неизвестная ошибка')
        
        # Если требуется пароль 2FA
        if 'password' in error.lower() or '2fa' in error.lower():
            context.user_data['needs_password'] = True
            await update.message.reply_text(
                "🔐 Требуется пароль 2FA\n\n"
                "Введите пароль облачного хранилища:\n\n"
                "Или /cancel для отмены"
            )
            return PASSWORD
        
        await update.message.reply_text(
            f"❌ Ошибка авторизации!\n\n"
            f"Причина: {error}\n\n"
            f"Попробуйте ещё раз",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Повторить", callback_data='connect_userbot'),
                InlineKeyboardButton("❌ Отмена", callback_data='back_to_menu')
            ]])
        )
        return ConversationHandler.END
    
    # Сохраняем аккаунт в БД
    session_id = result['session_id']
    account_name = result.get('account_name', phone)
    
    account_id = db.add_account(user_id, phone, session_id, account_name)
    
    if account_id:
        await update.message.reply_text(
            f"✅ *Аккаунт подключен!*\n\n"
            f"📱 Номер: {phone}\n"
            f"👤 Имя: {account_name}\n"
            f"🆔 ID: #{account_id}\n\n"
            f"Теперь вы можете использовать его для рассылок",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard(user_id)
        )
    else:
        await update.message.reply_text(
            "⚠️ Аккаунт авторизован, но возникла ошибка сохранения\n\n"
            "Обратитесь в поддержку",
            reply_markup=get_main_menu_keyboard(user_id)
        )
    
    # Очищаем данные
    context.user_data.clear()
    
    return ConversationHandler.END


async def password_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен пароль 2FA"""
    password = update.message.text.strip()
    user_id = update.effective_user.id
    
    phone = context.user_data.get('phone')
    
    if not phone:
        await update.message.reply_text(
            "❌ Ошибка: данные сессии потеряны",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Заново", callback_data='connect_userbot')
            ]])
        )
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ Проверка пароля...")
    
    # Авторизация с паролем
    result = await userbot_manager.check_password(phone, password)
    
    if not result['success']:
        await update.message.reply_text(
            f"❌ Неверный пароль!\n\n"
            f"Попробуйте ещё раз или /cancel",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Повторить", callback_data='connect_userbot')
            ]])
        )
        return ConversationHandler.END
    
    # Сохраняем аккаунт
    session_id = result['session_id']
    account_name = result.get('account_name', phone)
    
    account_id = db.add_account(user_id, phone, session_id, account_name)
    
    if account_id:
        await update.message.reply_text(
            f"✅ *Аккаунт подключен!*\n\n"
            f"📱 Номер: {phone}\n"
            f"👤 Имя: {account_name}\n"
            f"🆔 ID: #{account_id}\n\n"
            f"Теперь вы можете использовать его для рассылок",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard(user_id)
        )
    else:
        await update.message.reply_text(
            "⚠️ Ошибка сохранения аккаунта",
            reply_markup=get_main_menu_keyboard(user_id)
        )
    
    context.user_data.clear()
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

# ==================== ПЛАНИРОВЩИК ====================

async def schedule_mailing_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню планировщика"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Проверяем лимиты
    limits = check_user_limits(user_id, 'mailing')
    if not limits['allowed']:
        keyboard = [[InlineKeyboardButton("💎 Обновить тариф", callback_data="view_tariffs")]]
        await query.edit_message_text(
            f"⚠️ {limits['reason']}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Создать расписание", callback_data='create_schedule')],
        [InlineKeyboardButton("📋 Мои расписания", callback_data='my_schedules')],
        [InlineKeyboardButton("◀️ Назад", callback_data='back_to_menu')]
    ]
    
    await query.edit_message_text(
        "⏰ *Планировщик рассылок*\n\n"
        "Автоматическая отправка сообщений по расписанию:\n"
        "• Разовая рассылка\n"
        "• Ежедневная рассылка\n"
        "• Ежечасная рассылка",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def create_schedule_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания расписания"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📝 *Создание расписания*\n\n"
        "Шаг 1: Отправьте список ссылок на группы/каналы\n"
        "(по одной на строку)\n\n"
        "Или /cancel для отмены",
        parse_mode='Markdown'
    )
    
    return SCHEDULE_TARGETS

async def schedule_targets_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получены таргеты для расписания"""
    message = update.message
    
    targets_text = message.text.strip()
    targets = [t.strip() for t in targets_text.split('\n') if t.strip()]
    
    if not targets:
        await message.reply_text("❌ Не найдено ни одной ссылки!\nПопробуйте снова или /cancel")
        return SCHEDULE_TARGETS
    
    context.user_data['schedule_targets'] = targets
    
    # Выбор аккаунтов
    user_id = update.effective_user.id
    accounts = db.get_user_accounts(user_id)
    
    if not accounts:
        await message.reply_text("❌ Сначала добавьте хотя бы один аккаунт!")
        return ConversationHandler.END
    
    keyboard = []
    for account in accounts:
        keyboard.append([InlineKeyboardButton(
            f"📱 {account['account_name']} ({account['phone_number'][-4:]})",
            callback_data=f"sched_toggle_{account['id']}"
        )])
    
    keyboard.append([
        InlineKeyboardButton("✅ Выбрать все", callback_data='sched_select_all'),
        InlineKeyboardButton("❌ Снять все", callback_data='sched_deselect_all')
    ])
    keyboard.append([InlineKeyboardButton("➡️ Далее", callback_data='sched_accounts_done')])
    
    context.user_data['schedule_selected_accounts'] = []
    
    await message.reply_text(
        f"✅ Получено {len(targets)} ссылок\n\n"
        f"Шаг 2: Выберите аккаунты для рассылки:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return SCHEDULE_ACCOUNTS

async def schedule_toggle_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключение аккаунта для расписания"""
    query = update.callback_query
    await query.answer()
    
    account_id = int(query.data.split('_')[-1])
    selected = context.user_data.get('schedule_selected_accounts', [])
    
    if account_id in selected:
        selected.remove(account_id)
    else:
        selected.append(account_id)
    
    context.user_data['schedule_selected_accounts'] = selected
    
    # Обновляем клавиатуру
    user_id = update.effective_user.id
    accounts = db.get_user_accounts(user_id)
    
    keyboard = []
    for account in accounts:
        is_selected = account['id'] in selected
        emoji = "✅" if is_selected else "⬜️"
        keyboard.append([InlineKeyboardButton(
            f"{emoji} {account['account_name']} ({account['phone_number'][-4:]})",
            callback_data=f"sched_toggle_{account['id']}"
        )])
    
    keyboard.append([
        InlineKeyboardButton("✅ Выбрать все", callback_data='sched_select_all'),
        InlineKeyboardButton("❌ Снять все", callback_data='sched_deselect_all')
    ])
    keyboard.append([InlineKeyboardButton("➡️ Далее", callback_data='sched_accounts_done')])
    
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
    return SCHEDULE_ACCOUNTS

async def schedule_select_all_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбрать все аккаунты для расписания"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    accounts = db.get_user_accounts(user_id)
    context.user_data['schedule_selected_accounts'] = [acc['id'] for acc in accounts]
    
    await schedule_toggle_account(update, context)
    return SCHEDULE_ACCOUNTS

async def schedule_deselect_all_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Снять выбор со всех аккаунтов"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['schedule_selected_accounts'] = []
    await schedule_toggle_account(update, context)
    return SCHEDULE_ACCOUNTS

async def schedule_accounts_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Аккаунты выбраны, переход к сообщению"""
    query = update.callback_query
    await query.answer()
    
    selected = context.user_data.get('schedule_selected_accounts', [])
    
    if not selected:
        await query.answer("❌ Выберите хотя бы один аккаунт!", show_alert=True)
        return SCHEDULE_ACCOUNTS
    
    await query.edit_message_text(
        f"✅ Выбрано аккаунтов: {len(selected)}\n\n"
        f"Шаг 3: Отправьте сообщение для рассылки\n"
        f"(текст, фото или видео)",
        parse_mode='Markdown'
    )
    
    return SCHEDULE_MESSAGE

async def schedule_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получено сообщение для расписания"""
    message = update.message
    
    context.user_data['schedule_message'] = message
    
    keyboard = [
        [InlineKeyboardButton("🔂 Один раз", callback_data='sched_type_once')],
        [InlineKeyboardButton("📅 Ежедневно", callback_data='sched_type_daily')],
        [InlineKeyboardButton("⏰ Каждый час", callback_data='sched_type_hourly')]
    ]
    
    await message.reply_text(
        "✅ Сообщение получено!\n\n"
        "Шаг 4: Выберите тип расписания:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return SCHEDULE_TYPE

async def schedule_type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбран тип расписания"""
    query = update.callback_query
    await query.answer()
    
    schedule_type = query.data.split('_')[-1]
    context.user_data['schedule_type'] = schedule_type
    
    if schedule_type == 'once':
        await query.edit_message_text(
            "📅 Укажите дату и время запуска:\n\n"
            "Формат: ДД.ММ.ГГГГ ЧЧ:ММ\n"
            "Пример: 25.12.2024 15:30"
        )
    elif schedule_type == 'daily':
        await query.edit_message_text(
            "⏰ Укажите время ежедневного запуска:\n\n"
            "Формат: ЧЧ:ММ\n"
            "Пример: 09:00"
        )
    elif schedule_type == 'hourly':
        await schedule_confirm(update, context)
        return SCHEDULE_CONFIRM
    
    return SCHEDULE_TIME

async def schedule_time_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получено время для расписания"""
    message = update.message
    schedule_type = context.user_data.get('schedule_type')
    
    try:
        if schedule_type == 'once':
            # Парсим дату и время
            time_str = message.text.strip()
            schedule_time = datetime.strptime(time_str, '%d.%m.%Y %H:%M')
            
            if schedule_time < datetime.now():
                await message.reply_text("❌ Время должно быть в будущем!\nПопробуйте снова:")
                return SCHEDULE_TIME
            
            context.user_data['schedule_time'] = schedule_time.isoformat()
            
        elif schedule_type == 'daily':
            # Парсим только время
            time_str = message.text.strip()
            time_parts = time_str.split(':')
            if len(time_parts) != 2:
                raise ValueError()
            
            hour, minute = int(time_parts[0]), int(time_parts[1])
            if not (0 <= hour < 24 and 0 <= minute < 60):
                raise ValueError()
            
            context.user_data['schedule_time'] = f"{hour:02d}:{minute:02d}"
        
        # Показываем подтверждение
        await schedule_confirm(update, context)
        return SCHEDULE_CONFIRM
        
    except:
        await message.reply_text(
            "❌ Неверный формат!\n\n"
            f"{'Формат: ДД.ММ.ГГГГ ЧЧ:ММ' if schedule_type == 'once' else 'Формат: ЧЧ:ММ'}\n"
            "Попробуйте снова:"
        )
        return SCHEDULE_TIME

async def schedule_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение создания расписания"""
    schedule_type = context.user_data.get('schedule_type')
    schedule_time = context.user_data.get('schedule_time', 'Каждый час')
    targets = context.user_data.get('schedule_targets', [])
    accounts = context.user_data.get('schedule_selected_accounts', [])
    
    type_names = {
        'once': '🔂 Один раз',
        'daily': '📅 Ежедневно',
        'hourly': '⏰ Каждый час'
    }
    
    if schedule_type == 'once':
        time_display = datetime.fromisoformat(schedule_time).strftime('%d.%m.%Y в %H:%M')
    elif schedule_type == 'daily':
        time_display = f"Ежедневно в {schedule_time}"
    else:
        time_display = "Каждый час"
    
    keyboard = [
        [InlineKeyboardButton("✅ Создать", callback_data='confirm_schedule')],
        [InlineKeyboardButton("❌ Отмена", callback_data='cancel_schedule')]
    ]
    
    text = (
        f"📋 *Подтверждение расписания*\n\n"
        f"📨 Тип: {type_names.get(schedule_type, 'Неизвестно')}\n"
        f"⏰ Время: {time_display}\n"
        f"🎯 Чатов: {len(targets)}\n"
        f"👥 Аккаунтов: {len(accounts)}\n\n"
        f"Создать расписание?"
    )
    
    if isinstance(update, Update) and update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    return SCHEDULE_CONFIRM

async def schedule_confirm_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создание расписания подтверждено"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    targets = context.user_data.get('schedule_targets', [])
    accounts = context.user_data.get('schedule_selected_accounts', [])
    message = context.user_data.get('schedule_message')
    schedule_type = context.user_data.get('schedule_type')
    schedule_time = context.user_data.get('schedule_time')
    
    # Извлекаем данные сообщения
    message_text = message.text if message.text else None
    message_photo = message.photo[-1].file_id if message.photo else None
    message_video = message.video.file_id if message.video else None
    message_caption = message.caption if message.caption else None
    
    # Сохраняем в БД
    schedule_id = db.add_scheduled_mailing(
        user_id=user_id,
        targets=targets,
        account_ids=accounts,
        message_text=message_text,
        message_photo=message_photo,
        message_video=message_video,
        message_caption=message_caption,
        schedule_type=schedule_type,
        schedule_time=schedule_time
    )
    
    if schedule_id:
        # Добавляем в планировщик
        mailing_data = {
            'id': schedule_id,
            'user_id': user_id,
            'targets': targets,
            'account_ids': accounts,
            'message_text': message_text,
            'message_photo': message_photo,
            'message_video': message_video,
            'message_caption': message_caption,
            'schedule_type': schedule_type,
            'schedule_time': schedule_time
        }
        
        mailing_scheduler.add_job(mailing_data)
        
        type_names = {
            'once': '🔂 Один раз',
            'daily': '📅 Ежедневно',
            'hourly': '⏰ Каждый час'
        }
        
        if schedule_type == 'once':
            time_display = datetime.fromisoformat(schedule_time).strftime('%d.%m.%Y в %H:%M')
        elif schedule_type == 'daily':
            time_display = f"Ежедневно в {schedule_time}"
        else:
            time_display = "Каждый час"
        
        await query.edit_message_text(
            f"✅ *Расписание создано!*\n\n"
            f"📨 Тип: {type_names.get(schedule_type)}\n"
            f"⏰ Время: {time_display}\n"
            f"🎯 Чатов: {len(targets)}\n"
            f"👥 Аккаунтов: {len(accounts)}\n\n"
            f"ID расписания: #{schedule_id}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Мои расписания", callback_data='my_schedules')
            ]])
        )
    else:
        await query.edit_message_text(
            "❌ Ошибка создания расписания!\nПопробуйте позже.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data='schedule_menu')
            ]])
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def schedule_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена создания расписания"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    
    await query.edit_message_text(
        "❌ Создание расписания отменено",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ В меню", callback_data='back_to_menu')
        ]])
    )
    
    return ConversationHandler.END

async def my_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать мои расписания"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    schedules = db.get_user_scheduled_mailings(user_id)
    
    if not schedules:
        await query.edit_message_text(
            "📋 *Мои расписания*\n\n"
            "У вас пока нет активных расписаний",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Создать", callback_data='create_schedule'),
                InlineKeyboardButton("◀️ Назад", callback_data='schedule_menu')
            ]])
        )
        return
    
    schedules_text = "📋 *Мои расписания:*\n\n"
    keyboard = []
    
    type_names = {
        'once': '🔂 Один раз',
        'daily': '📅 Ежедневно',
        'hourly': '⏰ Каждый час'
    }
    
    for idx, schedule in enumerate(schedules, 1):
        schedule_type = schedule.get('schedule_type', 'unknown')
        schedule_time = schedule.get('schedule_time')
        
        if schedule_type == 'once':
            time_display = datetime.fromisoformat(schedule_time).strftime('%d.%m %H:%M')
        elif schedule_type == 'daily':
            time_display = schedule_time
        else:
            time_display = "Каждый час"
        
        schedules_text += (
            f"{idx}. {type_names.get(schedule_type, 'Неизвестно')}\n"
            f"   ⏰ {time_display}\n"
            f"   🎯 Чатов: {len(schedule.get('targets', []))}\n\n"
        )
        
        keyboard.append([InlineKeyboardButton(
            f"#{schedule['id']} - {type_names.get(schedule_type)}",
            callback_data=f"schedule_detail_{schedule['id']}"
        )])
    
    keyboard.append([
        InlineKeyboardButton("➕ Создать новое", callback_data='create_schedule'),
        InlineKeyboardButton("◀️ Назад", callback_data='schedule_menu')
    ])
    
    await query.edit_message_text(
        schedules_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def schedule_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детали расписания"""
    query = update.callback_query
    await query.answer()
    
    schedule_id = int(query.data.split('_')[-1])
    user_id = update.effective_user.id
    
    # Получаем все расписания и фильтруем
    schedules = db.get_user_scheduled_mailings(user_id)
    schedule = next((s for s in schedules if s['id'] == schedule_id), None)
    
    if not schedule:
        await query.answer("❌ Расписание не найдено", show_alert=True)
        return
    
    type_names = {
        'once': '🔂 Один раз',
        'daily': '📅 Ежедневно',
        'hourly': '⏰ Каждый час'
    }
    
    schedule_type = schedule.get('schedule_type', 'unknown')
    schedule_time = schedule.get('schedule_time')
    
    if schedule_type == 'once':
        time_display = datetime.fromisoformat(schedule_time).strftime('%d.%m.%Y в %H:%M')
    elif schedule_type == 'daily':
        time_display = f"Ежедневно в {schedule_time}"
    else:
        time_display = "Каждый час"
    
    last_run = schedule.get('last_run')
    last_run_display = "Ещё не запускалось"
    if last_run:
        last_run_display = datetime.fromisoformat(last_run).strftime('%d.%m.%Y %H:%M')
    
    detail_text = (
        f"📋 *Расписание #{schedule['id']}*\n\n"
        f"📨 Тип: {type_names.get(schedule_type, 'Неизвестно')}\n"
        f"⏰ Время: {time_display}\n"
        f"🎯 Чатов: {len(schedule.get('targets', []))}\n"
        f"👥 Аккаунтов: {len(schedule.get('account_ids', []))}\n"
        f"📅 Последний запуск: {last_run_display}\n"
        f"📅 Создано: {schedule['created_at'][:16]}"
    )
    
    keyboard = [
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_schedule_{schedule_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data='my_schedules')]
    ]
    
    await query.edit_message_text(
        detail_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def delete_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление расписания"""
    query = update.callback_query
    await query.answer()
    
    schedule_id = int(query.data.split('_')[-1])
    
    # Удаляем из БД
    if db.delete_scheduled_mailing(schedule_id):
        # Удаляем из планировщика
        mailing_scheduler.remove_job(schedule_id)
        
        await query.edit_message_text(
            f"✅ Расписание #{schedule_id} удалено",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ К расписаниям", callback_data='my_schedules')
            ]])
        )
    else:
        await query.edit_message_text(
            "❌ Ошибка удаления расписания",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data='my_schedules')
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
    
    # Проверяем лимиты
    limits = check_user_limits(user_id, 'mailing')
    if not limits['allowed']:
        keyboard = [[InlineKeyboardButton("💎 Обновить тариф", callback_data="view_tariffs")]]
        await query.edit_message_text(
            f"⚠️ {limits['reason']}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END
    
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
        return MAILING_TARGETS
    
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
    
    return MAILING_MESSAGE

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
    
    # Расчёт примерного времени
    estimated_time = (targets_count * 5) // 60  # 5 сек на сообщение
    
    keyboard = [
        [InlineKeyboardButton("✅ Запустить", callback_data='confirm_mailing')],
        [InlineKeyboardButton("❌ Отмена", callback_data='cancel_mailing')]
    ]
    
    await message.reply_text(
        f"📋 *Подтверждение рассылки*\n\n"
        f"👥 Аккаунтов: {accounts_count}\n"
        f"🎯 Чатов: {targets_count}\n"
        f"📨 Сообщение:\n{preview}\n\n"
        f"⏱ Примерное время: ~{estimated_time} мин\n"
        f"⏳ Задержка между сообщениями: 5 сек",
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
        reply_markup=get_main_menu_keyboard(update.effective_user.id)
    )
    
    return ConversationHandler.END

async def start_user_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск рассылки"""
    query = update.callback_query
    await query.answer("🚀 Запускаем рассылку...")
    
    user_id = update.effective_user.id
    
    # Получаем данные
    targets = context.user_data.get('mailing_targets', [])
    selected_accounts = context.user_data.get('selected_accounts', [])
    message_data = context.user_data.get('mailing_message', {})
    
    if not targets or not selected_accounts:
        await query.edit_message_text(
            "❌ Недостаточно данных для рассылки",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')
            ]])
        )
        return ConversationHandler.END
    
    # Создаем запись в БД
    mailing_id = db.add_mailing(
        user_id=user_id,
        targets='\n'.join(targets),
        message=message_data.get('text', ''),
        accounts_used=len(selected_accounts)
    )
    
    await query.edit_message_text(
        "🚀 *Рассылка запущена!*\n\n"
        f"🆔 ID: #{mailing_id}\n"
        f"📊 Целей: {len(targets)}\n"
        f"📱 Аккаунтов: {len(selected_accounts)}\n\n"
        "⏳ Рассылка выполняется...\n"
        "Вам придет уведомление по завершению",
        parse_mode='Markdown'
    )
    
    # Запускаем рассылку в фоне
    asyncio.create_task(
        execute_mailing(
            user_id=user_id,
            mailing_id=mailing_id,
            targets=targets,
            accounts=selected_accounts,
            message_data=message_data,
            context=context
        )
    )
    
    # Очищаем данные
    context.user_data.clear()
    
    return ConversationHandler.END


async def run_mailing_background(user_id: int, accounts_data: list, targets: list, 
                                mailing_message, context, progress_message):
    """Фоновая рассылка (не блокирует бота для других пользователей)"""
    
    try:
        # Распределяем таргеты по аккаунтам
        targets_per_account = len(targets) // len(accounts_data)
        remainder = len(targets) % len(accounts_data)
        
        total_sent = 0
        total_errors = 0
        start_time = datetime.now()
        
        start_idx = 0
        for idx, account in enumerate(accounts_data):
            # Распределяем таргеты
            end_idx = start_idx + targets_per_account + (1 if idx < remainder else 0)
            account_targets = targets[start_idx:end_idx]
            start_idx = end_idx
            
            if not account_targets:
                continue
            
            # Обновляем прогресс
            try:
                elapsed = (datetime.now() - start_time).seconds
                remaining_accounts = len(accounts_data) - idx
                estimated_remaining = (elapsed / (idx + 1)) * remaining_accounts if idx > 0 else 0
                
                await progress_message.edit_text(
                    f"📨 *Рассылка:*\n\n"
                    f"🔄 Аккаунт {idx + 1}/{len(accounts_data)}\n"
                    f"📱 {account['account_name']}\n"
                    f"🎯 Чатов на этом аккаунте: {len(account_targets)}\n\n"
                    f"✅ Отправлено всего: {total_sent}/{len(targets)}\n"
                    f"❌ Ошибок: {total_errors}\n"
                    f"⏱ Прошло: {elapsed // 60} мин {elapsed % 60} сек\n"
                    f"⏳ Осталось: ~{int(estimated_remaining // 60)} мин",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error updating progress: {e}")
            
            # Запускаем рассылку для этого аккаунта
            sent, errors = await run_single_account_mailing(
                account, account_targets, mailing_message, context
            )
            
            total_sent += sent
            total_errors += errors
            
            # Задержка между аккаунтами (чтобы не палить)
            if idx < len(accounts_data) - 1:
                await asyncio.sleep(10)
        
        # Рассылка завершена - итоговая статистика
        total_time = (datetime.now() - start_time).seconds
        success_rate = int((total_sent / len(targets)) * 100) if targets else 0
        
        # Сохраняем в историю
        message_preview = mailing_message.text[:50] if mailing_message.text else '[Медиа]'
        db.add_mailing(user_id, message_preview, total_sent, total_errors)
        
        try:
            await progress_message.edit_text(
                f"✅ *Рассылка завершена!*\n\n"
                f"📊 *Статистика:*\n\n"
                f"👥 Использовано аккаунтов: {len(accounts_data)}\n"
                f"✅ Отправлено: {total_sent}/{len(targets)}\n"
                f"❌ Ошибок: {total_errors}\n"
                f"📈 Успешность: {success_rate}%\n"
                f"⏱ Время: {total_time // 60} мин {total_time % 60} сек\n\n"
                f"💡 Рассылка сохранена в истории",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📜 История", callback_data="mailing_history"),
                    InlineKeyboardButton("🏠 Меню", callback_data="back_to_menu")
                ]])
            )
        except Exception as e:
            logger.error(f"Error sending final message: {e}")
    
    except Exception as e:
        logger.error(f"Background mailing error: {e}")
        try:
            await progress_message.edit_text(
                f"❌ *Ошибка рассылки!*\n\n"
                f"Произошла ошибка при выполнении рассылки.\n"
                f"Обратитесь в поддержку.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💬 Поддержка", callback_data="support")
                ]])
            )
        except:
            pass


async def run_single_account_mailing(account: dict, targets: list, mailing_message, context):
    """Рассылка с одного аккаунта"""
    
    session_id = account['session_id']
    phone = account['phone_number']
    
    sent = 0
    errors = 0
    
    try:
        # Подключаем сессию
        connect_result = await userbot_manager.connect_session(phone, session_id)
        if not connect_result['success']:
            logger.error(f"Failed to connect account {phone}: {connect_result.get('error')}")
            return 0, len(targets)
        
        logger.info(f"✅ Connected account {phone} for mailing")
        
        # ФАЗА 1: Вступление в чаты (быстро, без задержек)
        logger.info(f"📥 Phase 1: Joining {len(targets)} chats...")
        for target in targets:
            try:
                await userbot_manager.join_chat(session_id, phone, target)
                await asyncio.sleep(1)  # Минимальная задержка
            except Exception as e:
                logger.debug(f"Join error {target}: {e}")
        
        # Пауза между фазами
        await asyncio.sleep(10)
        
        # ФАЗА 2: Отправка сообщений (с задержками)
        logger.info(f"📤 Phase 2: Sending messages to {len(targets)} chats...")
        
        for idx, target in enumerate(targets, 1):
            try:
                # Определяем тип сообщения
                if mailing_message.text:
                    # Текстовое сообщение
                    result = await userbot_manager.send_message(
                        session_id, phone, target, mailing_message.text
                    )
                    
                elif mailing_message.photo:
                    # Фото
                    photo_file = await context.bot.get_file(mailing_message.photo[-1].file_id)
                    photo_path = f"temp_photo_{phone}_{idx}.jpg"
                    await photo_file.download_to_drive(photo_path)
                    
                    result = await userbot_manager.send_photo(
                        session_id, phone, target, photo_path, 
                        mailing_message.caption
                    )
                    
                    # Удаляем временный файл
                    try:
                        import os
                        os.remove(photo_path)
                    except:
                        pass
                    
                elif mailing_message.video:
                    # Видео
                    video_file = await context.bot.get_file(mailing_message.video.file_id)
                    video_path = f"temp_video_{phone}_{idx}.mp4"
                    await video_file.download_to_drive(video_path)
                    
                    result = await userbot_manager.send_video(
                        session_id, phone, target, video_path,
                        mailing_message.caption
                    )
                    
                    # Удаляем временный файл
                    try:
                        import os
                        os.remove(video_path)
                    except:
                        pass
                else:
                    result = {'success': False}
                
                # Проверяем результат
                if result.get('success'):
                    sent += 1
                    logger.debug(f"✅ Sent to {target} ({sent}/{len(targets)})")
                else:
                    errors += 1
                    logger.debug(f"❌ Failed to {target}: {result.get('error')}")
                
                # Задержка между сообщениями (антибан)
                await asyncio.sleep(5)
                
            except Exception as e:
                errors += 1
                logger.error(f"Error sending to {target}: {e}")
                await asyncio.sleep(3)
        
        logger.info(f"✅ Account {phone} completed: {sent} sent, {errors} errors")
        
    except Exception as e:
        logger.error(f"Account {phone} mailing error: {e}")
        errors = len(targets)
    
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
    
    text = (
        "ℹ️ *Помощь*\n\n"
        "📱 Подключайте аккаунты\n"
        "📨 Создавайте рассылки\n"
        "⏰ Настраивайте расписание"
    )
    
    # ✅ ОБЯЗАТЕЛЬНО передаем reply_markup
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')
        ]])
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
            reply_markup=get_main_menu_keyboard(user_id)
        )
    except Exception as e:
        logger.error(f"Error sending to admin: {e}")
        await message.reply_text(
            "❌ Ошибка отправки. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard(user_id)
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
• Активных подписок: {stats.get('active_subscriptions', 0)}
• Новых за сегодня: {stats.get('new_today', 0)}

📱 *Аккаунты:*
• Всего подключено: {stats.get('total_accounts', 0)}
• Активных: {stats.get('active_accounts', 0)}

📨 *Рассылки:*
• Всего: {stats.get('total_mailings', 0)}
• За сегодня: {stats.get('mailings_today', 0)}
• Сообщений отправлено: {stats.get('total_sent', 0)}

💎 *По тарифам:*
• Пробный: {stats.get('trial_users', 0)}
• Любительская: {stats.get('amateur_users', 0)}
• Профессиональная: {stats.get('professional_users', 0)}
• Премиум: {stats.get('premium_users', 0)}

⏰ *Запланировано:*
• Рассылок: {stats.get('total_scheduled', 0)}

💰 *Финансы:*
• Ожидают оплаты: {stats.get('pending_payments', 0)}
• Подтверждено платежей: {stats.get('approved_payments', 0)}
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
        plan = SUBSCRIPTIONS.get(user.get('subscription_plan', 'trial'), {})
        plan_name = plan.get('name', 'Неизвестно')
        
        subscription_active = user['subscription_end'] > datetime.now()
        status = "✅" if subscription_active else "❌"
        
        users_text += (
            f"{idx}. {username} (ID: {user['user_id']})\n"
            f"   💎 Тариф: {plan_name} {status}\n"
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
        [InlineKeyboardButton("❌ Отмена", callback_data='admin_menu')]
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
    
    progress_msg = await query.edit_message_text(
        f"📮 Рассылка запущена!\n\n"
        f"👥 Пользователей: {len(all_users)}\n"
        f"⏳ Идёт отправка..."
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
            
            # Обновляем прогресс каждые 10 пользователей
            if sent % 10 == 0:
                await progress_msg.edit_text(
                    f"📮 Рассылка:\n\n"
                    f"✅ Отправлено: {sent}/{len(all_users)}\n"
                    f"❌ Ошибок: {errors}"
                )
            
            await asyncio.sleep(0.05)  # Защита от флуда
            
        except Exception as e:
            errors += 1
            logger.error(f"Error sending to {user['user_id']}: {e}")
    
    await progress_msg.edit_text(
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
    
    pending = db.get_pending_payments()
    
    if not pending:
        await query.edit_message_text(
            "💳 *Ожидающие оплаты*\n\n"
            "Нет ожидающих платежей",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data='admin_menu')
            ]])
        )
        return
    
    payments_text = "💳 *Ожидающие оплаты:*\n\n"
    keyboard = []
    
    for idx, payment in enumerate(pending, 1):
        plan = SUBSCRIPTIONS.get(payment['plan_id'], {})
        username = db.get_user(payment['user_id']).get('username', 'Без username')
        
        payments_text += (
            f"{idx}. 👤 {username} (ID: {payment['user_id']})\n"
            f"   💎 Тариф: {plan.get('name', 'Неизвестно')}\n"
            f"   💵 Сумма: {payment['amount']}₽\n"
            f"   📅 {payment['created_at'][:16]}\n\n"
        )
        
        keyboard.append([
            InlineKeyboardButton(
                f"#{payment['id']} - {username}",
                callback_data=f"view_payment_{payment['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='admin_menu')])
    
    await query.edit_message_text(
        payments_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Бэкап базы данных"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Нет доступа", show_alert=True)
        return
    
    try:
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
                caption=f"💾 Бэкап базы данных\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
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
💰 Активных подписок: {stats.get('active_subscriptions', 0)}
📱 Всего аккаунтов: {stats.get('total_accounts', 0)}
📨 Всего рассылок: {stats.get('total_mailings', 0)}
⏰ Запланировано: {stats.get('total_scheduled', 0)}
💳 Ожидают оплаты: {stats.get('pending_payments', 0)}
    """
    
    await query.edit_message_text(
        admin_text,
        reply_markup=get_admin_keyboard(),
        parse_mode='Markdown'
    )

# ==================== ОБРАБОТЧИКИ КНОПОК МЕНЮ ====================

async def accounts_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Мои аккаунты'"""
    user_id = update.effective_user.id
    accounts = db.get_user_accounts(user_id)
    
    if not accounts:
        text = (
            "📱 *Управление аккаунтами*\n\n"
            "У вас пока нет подключенных аккаунтов\n\n"
            "Добавьте Telegram аккаунт для начала работы"
        )
        keyboard = [
            [InlineKeyboardButton("➕ Добавить аккаунт", callback_data='connect_userbot')],
            [InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')]
        ]
    else:
        text = f"📱 *Управление аккаунтами*\n\nПодключено: {len(accounts)}\n\n"
        
        keyboard = []
        for acc in accounts:
            keyboard.append([
                InlineKeyboardButton(
                    f"📱 {acc['account_name']} ({acc['phone']})",
                    callback_data=f"account_{acc['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("➕ Добавить аккаунт", callback_data='connect_userbot')])
        keyboard.append([InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')])
    
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def accounts_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню управления аккаунтами через callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    accounts = db.get_user_accounts(user_id)
    
    if not accounts:
        text = (
            "📱 *Управление аккаунтами*\n\n"
            "У вас пока нет подключенных аккаунтов\n\n"
            "Добавьте Telegram аккаунт для начала работы"
        )
        keyboard = [
            [InlineKeyboardButton("➕ Добавить аккаунт", callback_data='connect_userbot')],
            [InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')]
        ]
    else:
        text = f"📱 *Управление аккаунтами*\n\nПодключено: {len(accounts)}\n\n"
        
        keyboard = []
        for acc in accounts:
            keyboard.append([
                InlineKeyboardButton(
                    f"📱 {acc['account_name']} ({acc['phone']})",
                    callback_data=f"account_{acc['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("➕ Добавить аккаунт", callback_data='connect_userbot')])
        keyboard.append([InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')])
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def create_mailing_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Создать рассылку'"""
    user_id = update.effective_user.id
    
    # Проверяем лимиты
    limits = check_user_limits(user_id, 'mailing')
    if not limits['allowed']:
        await update.message.reply_text(
            f"⚠️ {limits['reason']}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💎 Тарифы", callback_data="view_tariffs")
            ]])
        )
        return ConversationHandler.END
    
    # Проверяем наличие аккаунтов
    accounts = db.get_user_accounts(user_id)
    if not accounts:
        await update.message.reply_text(
            "❌ У вас нет подключенных аккаунтов!\n\n"
            "Сначала подключите хотя бы один аккаунт",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Добавить аккаунт", callback_data='connect_userbot'),
                InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')
            ]])
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📨 *Создание рассылки*\n\n"
        "Шаг 1: Отправьте список целевых чатов/каналов\n\n"
        "Формат:\n"
        "```\nhttps://t.me/example_chat\n"
        "@example_channel\n"
        "https://t.me/joinchat/XXXXX```\n\n"
        "По одной ссылке на строку\n"
        "Или /cancel для отмены",
        parse_mode='Markdown'
    )
    
    return MAILING_TARGETS

async def cancel_mailing_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена рассылки через callback"""
    query = update.callback_query
    await query.answer("❌ Рассылка отменена")
    
    # Очищаем данные
    context.user_data.clear()
    
    # Удаляем сообщение
    try:
        await query.message.delete()
    except:
        pass
    
    # Отправляем в меню
    user_id = update.effective_user.id
    await context.bot.send_message(
        chat_id=user_id,
        text="❌ Рассылка отменена\n\n🏠 Главное меню:",
        reply_markup=get_main_menu_keyboard(user_id)
    )
    
    return ConversationHandler.END


async def schedule_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Планировщик'"""
    user_id = update.effective_user.id
    schedules = db.get_user_schedules(user_id)
    
    if not schedules:
        text = (
            "⏰ *Планировщик рассылок*\n\n"
            "У вас нет активных расписаний\n\n"
            "Создайте автоматическую рассылку по расписанию"
        )
        keyboard = [
            [InlineKeyboardButton("➕ Создать расписание", callback_data='create_schedule')],
            [InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')]
        ]
    else:
        text = f"⏰ *Планировщик рассылок*\n\nАктивных расписаний: {len(schedules)}\n\n"
        
        keyboard = []
        for sched in schedules[:5]:  # Показываем первые 5
            schedule_type = sched['schedule_type']
            emoji = "🔂" if schedule_type == "once" else "📅" if schedule_type == "daily" else "⏰"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"{emoji} {schedule_type.capitalize()} - {sched['schedule_time']}",
                    callback_data=f"schedule_{sched['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("➕ Создать расписание", callback_data='create_schedule')])
        keyboard.append([InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')])
    
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'История'"""
    user_id = update.effective_user.id
    mailings = db.get_user_mailings(user_id, limit=10)
    
    if not mailings:
        await update.message.reply_text(
            "📜 *История рассылок*\n\n"
            "У вас пока нет рассылок\n\n"
            "Создайте первую рассылку!",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📨 Создать рассылку", callback_data='start_mailing'),
                InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')
            ]])
        )
        return
    
    text = f"📜 *История рассылок*\n\nВсего рассылок: {len(mailings)}\n\n"
    
    for m in mailings[:10]:
        status_emoji = "✅" if m['status'] == 'completed' else "⏳" if m['status'] == 'running' else "❌"
        created = m['created_at']
        
        text += (
            f"{status_emoji} *Рассылка #{m['id']}*\n"
            f"📅 {created}\n"
            f"✅ Успешно: {m['success_count']}\n"
            f"❌ Ошибок: {m['error_count']}\n"
            f"📱 Аккаунтов: {m['accounts_used']}\n\n"
        )
    
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')
        ]])
    )


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Мой статус'"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    if not user_data:
        await update.message.reply_text(
            "❌ Данные не найдены",
            reply_markup=get_main_menu_keyboard(user_id)
        )
        return
    
    # Парсим дату
    subscription_end = user_data['subscription_end']
    if isinstance(subscription_end, str):
        try:
            subscription_end = datetime.fromisoformat(subscription_end)
        except:
            subscription_end = datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S.%f')
    
    plan_id = user_data['subscription_plan']
    plan = SUBSCRIPTIONS.get(plan_id, {})
    
    # Проверяем активность
    subscription_active = subscription_end > datetime.now()
    days_left = (subscription_end - datetime.now()).days if subscription_active else 0
    
    # Получаем данные
    accounts = db.get_user_accounts(user_id)
    mailings_today = db.get_user_mailings_today(user_id)
    
    # Лимиты
    max_accounts = plan.get('max_accounts', 1)
    max_mailings = plan.get('max_mailings_per_day', 3)
    
    accounts_text = f"{len(accounts)}/{max_accounts}" if max_accounts != -1 else f"{len(accounts)}/♾"
    mailings_text = f"{mailings_today}/{max_mailings}" if max_mailings != -1 else f"{mailings_today}/♾"
    
    status_emoji = "✅" if subscription_active else "❌"
    status_text = f"Активна ({days_left} дн.)" if subscription_active else "Истекла"
    
    text = (
        f"📊 *Ваш статус*\n\n"
        f"💎 Тариф: {plan.get('name', 'Неизвестно')}\n"
        f"{status_emoji} Подписка: {status_text}\n"
        f"📅 До: {subscription_end.strftime('%d.%m.%Y')}\n\n"
        f"📊 *Использование:*\n"
        f"📱 Аккаунтов: {accounts_text}\n"
        f"📨 Рассылок сегодня: {mailings_text}\n"
    )
    
    keyboard = [[InlineKeyboardButton("💎 Тарифы", callback_data="view_tariffs")]]
    if not subscription_active or days_left < 3:
        keyboard.insert(0, [InlineKeyboardButton("🔄 Продлить", callback_data="view_tariffs")])
    
    keyboard.append([InlineKeyboardButton("🏠 Меню", callback_data="back_to_menu")])
    
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def tariffs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Тарифы'"""
    text = "💎 *Доступные тарифы*\n\n"
    
    keyboard = []
    for plan_id, plan in SUBSCRIPTIONS.items():
        price_text = "Бесплатно" if plan['price'] == 0 else f"{plan['price']}₽/мес"
        
        text += (
            f"{plan['name']}\n"
            f"💰 {price_text}\n"
            f"📱 Аккаунтов: {plan['max_accounts'] if plan['max_accounts'] != -1 else '♾'}\n"
            f"📨 Рассылок/день: {plan['max_mailings_per_day'] if plan['max_mailings_per_day'] != -1 else '♾'}\n"
            f"⏱ {plan['days']} дней\n\n"
        )
        
        if plan['price'] > 0:
            keyboard.append([InlineKeyboardButton(
                f"💎 Купить {plan['name']} - {plan['price']}₽",
                callback_data=f"buy_{plan_id}"
            )])
    
    keyboard.append([InlineKeyboardButton("🏠 Меню", callback_data="back_to_menu")])
    
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Помощь'"""
    text = (
        "ℹ️ *Помощь по использованию*\n\n"
        "📱 *Аккаунты*\n"
        "Подключите свои Telegram аккаунты для рассылок\n\n"
        "📨 *Рассылки*\n"
        "Создавайте рассылки в группы и каналы\n"
        "Поддержка текста, фото и видео\n\n"
        "⏰ *Планировщик*\n"
        "Настраивайте автоматические рассылки:\n"
        "• Один раз - в указанное время\n"
        "• Ежедневно - каждый день\n"
        "• Ежечасно - каждый час\n\n"
        "💎 *Тарифы*\n"
        "🆓 Пробный - 3 дня бесплатно\n"
        "🌱 Любительский - 199₽/мес\n"
        "💼 Профессиональный - 499₽/мес\n"
        "💎 Премиум - 999₽/мес (безлимит)\n\n"
        f"💬 Поддержка: @{SUPPORT_USERNAME}"
    )
    
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Меню", callback_data="back_to_menu")
        ]])
    )


async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Админ'"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет доступа")
        return
    
    stats = db.get_stats()
    
    text = (
        "⚙️ *Админ панель*\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"✅ Активных подписок: {stats['active_subscriptions']}\n"
        f"📱 Всего аккаунтов: {stats['total_accounts']}\n"
        f"📨 Рассылок сегодня: {stats['mailings_today']}"
    )
    
    keyboard = [
        [InlineKeyboardButton("👥 Пользователи", callback_data='admin_users')],
        [InlineKeyboardButton("💰 Платежи", callback_data='admin_payments')],
        [InlineKeyboardButton("📤 Рассылка всем", callback_data='admin_broadcast')],
        [InlineKeyboardButton("💾 Бэкап БД", callback_data='admin_backup')],
        [InlineKeyboardButton("🏠 Меню", callback_data='back_to_menu')]
    ]
    
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== MAIN ====================

def main():
    """Главная функция запуска бота"""
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # ==================== CONVERSATION HANDLERS ====================
    
    # Подключение аккаунта
    connect_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('connect', connect_userbot_start),
            CallbackQueryHandler(connect_userbot_start, pattern='^connect_userbot$')
        ],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_received)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, code_received)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, password_received)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(connect_conv_handler)
    
    # Рассылка
    user_mailing_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex('^📨 Создать рассылку$'), create_mailing_handler)
        ],
        states={
            MAILING_TARGETS: [MessageHandler(filters.TEXT & ~filters.COMMAND, mailing_targets_received)],
            MAILING_ACCOUNTS: [
                CallbackQueryHandler(toggle_account_selection, pattern=r'^toggle_account_\d+$'),
                CallbackQueryHandler(select_all_accounts, pattern='^select_all_accounts$'),
                CallbackQueryHandler(deselect_all_accounts, pattern='^deselect_all_accounts$'),
                CallbackQueryHandler(continue_with_selected, pattern='^continue_with_selected$')
            ],
            MAILING_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, mailing_message_received),
                MessageHandler(filters.PHOTO, mailing_message_received),
                MessageHandler(filters.VIDEO, mailing_message_received)
            ],
            MAILING_CONFIRM: [
                CallbackQueryHandler(start_user_mailing, pattern='^confirm_mailing$'),
                CallbackQueryHandler(cancel_mailing_callback, pattern='^cancel_mailing$')
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(user_mailing_handler)
    
    # Планировщик
    schedule_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_schedule_start, pattern='^create_schedule$')],
        states={
            SCHEDULE_TARGETS: [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_targets_received)],
            SCHEDULE_ACCOUNTS: [
                CallbackQueryHandler(toggle_schedule_account, pattern=r'^toggle_schedule_account_\d+$'),
                CallbackQueryHandler(select_all_schedule_accounts, pattern='^select_all_schedule_accounts$'),
                CallbackQueryHandler(continue_schedule_with_selected, pattern='^continue_schedule_with_selected$')
            ],
            SCHEDULE_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_message_received),
                MessageHandler(filters.PHOTO, schedule_message_received)
            ],
            SCHEDULE_TYPE: [
                CallbackQueryHandler(schedule_type_selected, pattern='^schedule_type_')
            ],
            SCHEDULE_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_time_received)
            ],
            SCHEDULE_CONFIRM: [
                CallbackQueryHandler(create_schedule_confirm, pattern='^confirm_schedule$'),
                CallbackQueryHandler(cancel, pattern='^cancel_schedule$')
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(schedule_handler)
    
    # ==================== ОСНОВНЫЕ КОМАНДЫ ====================
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    
    # ==================== CALLBACK HANDLERS ====================
    
    # Главное меню
    application.add_handler(CallbackQueryHandler(back_to_menu_callback, pattern='^back_to_menu$'))
    application.add_handler(CallbackQueryHandler(check_subscription_callback, pattern='^check_subscription$'))
    
    # Аккаунты (УЖЕ в ConversationHandler, НЕ добавляем отдельно!)
    # application.add_handler(CallbackQueryHandler(connect_userbot_start, pattern='^connect_userbot$'))  # УДАЛИ
    application.add_handler(CallbackQueryHandler(accounts_menu_callback, pattern='^accounts_menu$'))
    application.add_handler(CallbackQueryHandler(account_info_callback, pattern='^account_'))
    application.add_handler(CallbackQueryHandler(delete_account_callback, pattern='^delete_account_'))
    application.add_handler(CallbackQueryHandler(confirm_delete_account, pattern='^confirm_delete_'))
    
    # Тарифы
    application.add_handler(CallbackQueryHandler(view_tariffs_callback, pattern='^view_tariffs$'))
    application.add_handler(CallbackQueryHandler(select_plan_callback, pattern='^buy_'))
    application.add_handler(CallbackQueryHandler(select_payment_method, pattern='^payment_method_'))
    application.add_handler(CallbackQueryHandler(payment_sent, pattern='^paid_'))
    
    # Статус
    application.add_handler(CallbackQueryHandler(my_status_callback, pattern='^my_status$'))
    
    # Помощь
    application.add_handler(CallbackQueryHandler(help_callback, pattern='^help$'))
    
    # Планировщик
    application.add_handler(CallbackQueryHandler(schedule_mailing_menu, pattern='^schedule_menu$'))
    application.add_handler(CallbackQueryHandler(schedule_info_callback, pattern='^schedule_'))
    application.add_handler(CallbackQueryHandler(delete_schedule_callback, pattern='^delete_schedule_'))
    application.add_handler(CallbackQueryHandler(confirm_delete_schedule, pattern='^confirm_delete_schedule_'))
    
    # История
    application.add_handler(CallbackQueryHandler(mailing_history, pattern='^mailing_history$'))
    
    # Админ
    if ADMIN_ID:
        application.add_handler(CallbackQueryHandler(admin_menu_callback, pattern='^admin_menu$'))
        application.add_handler(CallbackQueryHandler(admin_users_callback, pattern='^admin_users$'))
        application.add_handler(CallbackQueryHandler(admin_payments_callback, pattern='^admin_payments$'))
        application.add_handler(CallbackQueryHandler(approve_payment_callback, pattern='^approve_payment_'))
        application.add_handler(CallbackQueryHandler(reject_payment_callback, pattern='^reject_payment_'))
        application.add_handler(CallbackQueryHandler(admin_broadcast_start, pattern='^admin_broadcast$'))
        application.add_handler(CallbackQueryHandler(admin_backup_callback, pattern='^admin_backup$'))
    
    # ==================== ОБРАБОТЧИКИ КНОПОК МЕНЮ ====================
    
    application.add_handler(MessageHandler(filters.Regex('^📱 Мои аккаунты$'), accounts_menu_handler))
    application.add_handler(MessageHandler(filters.Regex('^📨 Создать рассылку$'), create_mailing_handler))
    application.add_handler(MessageHandler(filters.Regex('^⏰ Планировщик$'), schedule_menu_handler))
    application.add_handler(MessageHandler(filters.Regex('^📜 История$'), history_handler))
    application.add_handler(MessageHandler(filters.Regex('^📊 Мой статус$'), status_handler))
    application.add_handler(MessageHandler(filters.Regex('^💎 Тарифы$'), tariffs_handler))
    application.add_handler(MessageHandler(filters.Regex('^ℹ️ Помощь$'), help_handler))
    
    if ADMIN_ID:
        application.add_handler(MessageHandler(filters.Regex('^⚙️ Админ$'), admin_handler))
    
    # Запуск
    logger.info("🤖 Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)