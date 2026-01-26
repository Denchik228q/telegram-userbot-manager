#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Manager Bot - Бот для управления юзерботом и подписками
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

# Локальные импорты
from config_userbot import (
    MANAGER_BOT_TOKEN,
    API_ID,
    API_HASH,
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

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных и юзербота
db = Database()
userbot_manager = UserbotManager()

# ============= СОСТОЯНИЯ ДЛЯ CONVERSATION HANDLERS =============
# Подключение юзербота
PHONE, CODE, PASSWORD = range(3)

# Поддержка
SUPPORT_MESSAGE, SUPPORT_PHOTO = range(10, 12)

# Оплата
PAYMENT_PLAN, PAYMENT_CONFIRM, PAYMENT_RECEIPT = range(20, 23)

# Рассылка админа
MAILING_MESSAGE = 100
MAILING_CONFIRM = 101

# Рассылка пользователя (через его юзербот)
USER_MAILING_TARGETS, USER_MAILING_MESSAGE, USER_MAILING_CONFIRM = range(300, 303)

# ============= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =============

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверка подписки на публичный канал"""
    try:
        # Убираем @ если есть
        channel_username = PUBLIC_CHANNEL_URL.replace('@', '').replace('https://t.me/', '')
        
        # Проверяем подписку
        member = await context.bot.get_chat_member(
            chat_id=f"@{channel_username}",
            user_id=user_id
        )
        
        # Если не подписан
        if member.status in ['left', 'kicked']:
            return False
            
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        # Если ошибка - считаем что подписан (чтобы не блокировать пользователей)
        return True
    
    return True


def get_subscription_keyboard():
    """Клавиатура с кнопкой подписки на публичный канал"""
    keyboard = [
        [InlineKeyboardButton(f"{PUBLIC_CHANNEL_NAME}", url=PUBLIC_CHANNEL_URL if PUBLIC_CHANNEL_URL.startswith('http') else f"https://t.me/{PUBLIC_CHANNEL_URL.replace('@', '')}")],
        [InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_main_menu_keyboard(user_data: dict = None):
    """Главное меню бота"""
    keyboard = [
        [InlineKeyboardButton("🤖 Подключить аккаунт", callback_data="connect_userbot")],
        [InlineKeyboardButton("📨 Начать рассылку", callback_data="start_mailing")],
        [InlineKeyboardButton("📊 Мой статус", callback_data="my_status")],
        [InlineKeyboardButton("💎 Тарифы и оплата", callback_data="view_tariffs")],
        [InlineKeyboardButton("💬 Поддержка", callback_data="support")]
    ]
    
    return InlineKeyboardMarkup(keyboard)


def get_admin_keyboard():
    """Клавиатура для админа"""
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("📮 Создать рассылку", callback_data="admin_mailing")],
        [InlineKeyboardButton("✅ Подтвердить оплату", callback_data="admin_payments")],
        [InlineKeyboardButton("💾 Бэкап БД", callback_data="admin_backup")]
    ]
    return InlineKeyboardMarkup(keyboard)


# ============= КОМАНДЫ =============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    user_id = user.id
    
    # Регистрация пользователя
    if not db.get_user(user_id):
        db.add_user(
            telegram_id=user_id,
            username=user.username or "",
            first_name=user.first_name or "",
            subscription_plan="trial",
            subscription_end=datetime.now() + timedelta(days=3)
        )
        logger.info(f"✅ New user registered: {user_id}")
    
    # Проверка подписки на публичный канал
    is_subscribed = await check_subscription(user_id, context)
    
    if not is_subscribed:
        await update.message.reply_text(
            f"👋 Добро пожаловать, {user.first_name}!\n\n"
            f"🔔 Для начала работы подпишитесь на наш публичный канал:",
            reply_markup=get_subscription_keyboard()
        )
    else:
        user_data = db.get_user(user_id)
        
        await update.message.reply_text(
            f"👋 Добро пожаловать, {user.first_name}!\n\n"
            f"Выберите действие из меню ниже:",
            reply_markup=get_main_menu_keyboard(user_data)
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
📚 *Доступные команды:*

/start - Начать работу с ботом
/help - Показать эту справку
/status - Проверить статус подписки
/support - Связаться с поддержкой
/cancel - Отменить текущую операцию

💡 *Как пользоваться ботом:*

1️⃣ Подпишитесь на публичный канал
2️⃣ Выберите тариф и оплатите
3️⃣ Отправьте чек администратору
4️⃣ После подтверждения подключите аккаунт
5️⃣ Начните рассылку через свой аккаунт
6️⃣ Получите доступ к приватному каналу

❓ Возникли вопросы? Используйте /support
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /status"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    if not user_data:
        await update.message.reply_text("❌ Пользователь не найден. Используйте /start")
        return
    
    # Проверка активности подписки
    subscription_active = user_data['subscription_end'] > datetime.now()
    status_emoji = "✅" if subscription_active else "❌"
    
    # Получаем информацию о тарифе
    plan_info = SUBSCRIPTIONS.get(user_data['subscription_plan'], SUBSCRIPTIONS['trial'])
    
    # Проверка юзербота
    session_id = user_data.get('session_id', '')
    userbot_status = "✅ Подключен" if session_id else "❌ Не подключен"
    
    status_text = f"""
📊 *Ваш статус подписки:*

👤 ID: `{user_id}`
📱 Телефон: {user_data.get('phone_number', 'Не указан')}

📦 *Подписка:* {plan_info['name']}
⏰ *Действует до:* {user_data['subscription_end'].strftime('%d.%m.%Y %H:%M')}
{status_emoji} *Статус:* {'Активна' if subscription_active else 'Истекла'}

📋 *Лимиты тарифа:*
• Аккаунтов: {plan_info['accounts_limit']}
• Сообщений в день: {plan_info['messages_limit']}
• Срок: {plan_info['duration']} дней

🤖 *Юзербот:* {userbot_status}
🔒 *Приватный канал:* {status_emoji}
    """
    
    await update.message.reply_text(
        status_text,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard(user_data)
    )


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-панель"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет доступа к админ-панели")
        return
    
    # Статистика
    stats = db.get_stats()
    
    admin_text = f"""
🔧 *Панель администратора*

📊 *Статистика:*
👥 Всего пользователей: {stats.get('total_users', 0)}
💰 Активных подписок: {stats.get('active_subscriptions', 0)}
📅 Новых за сегодня: {stats.get('new_today', 0)}

💎 *По тарифам:*
• Любительская: {stats.get('amateur_users', 0)}
• Профессиональная: {stats.get('pro_users', 0)}
• Премиум: {stats.get('premium_users', 0)}
• Пробная: {stats.get('trial_users', 0)}

Выберите действие:
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


# ============= CALLBACK ОБРАБОТЧИКИ =============

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка подписки на публичный канал"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    is_subscribed = await check_subscription(user_id, context)
    
    if is_subscribed:
        user_data = db.get_user(user_id)
        
        await query.edit_message_text(
            "✅ Отлично! Вы подписаны на канал.\n\n"
            "Выберите действие:",
            reply_markup=get_main_menu_keyboard(user_data)
        )
    else:
        await query.answer(
            "❌ Вы ещё не подписались на канал!",
            show_alert=True
        )


async def my_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статус пользователя"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    if not user_data:
        await query.edit_message_text("❌ Пользователь не найден")
        return
    
    subscription_active = user_data['subscription_end'] > datetime.now()
    status_emoji = "✅" if subscription_active else "❌"
    
    plan_info = SUBSCRIPTIONS.get(user_data['subscription_plan'], SUBSCRIPTIONS['trial'])
    
    session_id = user_data.get('session_id', '')
    userbot_status = "✅ Подключен" if session_id else "❌ Не подключен"
    
    status_text = f"""
📊 *Ваш статус подписки:*

👤 ID: `{user_id}`
📱 Телефон: {user_data.get('phone_number', 'Не указан')}

📦 *Подписка:* {plan_info['name']}
⏰ *Действует до:* {user_data['subscription_end'].strftime('%d.%m.%Y %H:%M')}
{status_emoji} *Статус:* {'Активна' if subscription_active else 'Истекла'}

📋 *Лимиты тарифа:*
• Аккаунтов: {plan_info['accounts_limit']}
• Сообщений в день: {plan_info['messages_limit']}
• Срок: {plan_info['duration']} дней

🤖 *Юзербот:* {userbot_status}
    """
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
    
    await query.edit_message_text(
        status_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def view_tariffs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать тарифы"""
    query = update.callback_query
    await query.answer()
    
    tariffs_text = "💎 *Доступные тарифы:*\n\n"
    
    keyboard = []
    
    for plan_id, plan in SUBSCRIPTIONS.items():
        if plan_id == 'trial':
            continue  # Пропускаем trial
        
        tariffs_text += f"*{plan['name']}* - {plan['price']}₽/{plan['duration']} дн.\n"
        tariffs_text += f"{plan['description']}\n\n"
        
        keyboard.append([
            InlineKeyboardButton(
                f"💳 Купить {plan['name']} - {plan['price']}₽",
                callback_data=f"buy_{plan_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
    
    await query.edit_message_text(
        tariffs_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def back_to_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться в главное меню"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    await query.edit_message_text(
        "Выберите действие:",
        reply_markup=get_main_menu_keyboard(user_data)
    )


# ============= АДМИН CALLBACKS =============

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детальная статистика для админа"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    stats = db.get_stats()
    
    stats_text = f"""
📊 *Детальная статистика:*

👥 *Пользователи:*
• Всего: {stats.get('total_users', 0)}
• Активных подписок: {stats.get('active_subscriptions', 0)}
• Новых сегодня: {stats.get('new_today', 0)}
• Новых за неделю: {stats.get('new_week', 0)}

💰 *Подписки по тарифам:*
• Любительская (499₽): {stats.get('amateur_users', 0)}
• Профессиональная (1499₽): {stats.get('pro_users', 0)}
• Премиум (4999₽): {stats.get('premium_users', 0)}
• Пробная: {stats.get('trial_users', 0)}
    """
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")]]
    
    await query.edit_message_text(
        stats_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def admin_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список всех пользователей для админа"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    users = db.get_all_users()
    
    if not users:
        await query.edit_message_text(
            "ℹ️ Пользователей нет",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")
            ]])
        )
        return
    
    users_text = f"👥 *Всего пользователей: {len(users)}*\n\n"
    
    # Показываем последних 15 пользователей
    for idx, user in enumerate(users[:15], 1):
        plan_info = SUBSCRIPTIONS.get(user['subscription_plan'], SUBSCRIPTIONS['trial'])
        active = "✅" if user['subscription_end'] > datetime.now() else "❌"
        
        users_text += f"{idx}. {active} `{user['telegram_id']}`\n"
        users_text += f"   👤 {user['first_name']}\n"
        users_text += f"   📦 {plan_info['name']}\n"
        users_text += f"   ⏰ До {user['subscription_end'].strftime('%d.%m.%Y')}\n\n"
    
    if len(users) > 15:
        users_text += f"\n_...и ещё {len(users) - 15} пользователей_"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")]]
    
    await query.edit_message_text(
        users_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def admin_payments_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение оплаты - список платежей"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return ConversationHandler.END
    
    # Получаем неподтвержденные платежи
    payments = db.get_payments()
    pending_payments = [p for p in payments if p['status'] == 'pending']
    
    if not pending_payments:
        await query.edit_message_text(
            "ℹ️ Нет платежей ожидающих подтверждения",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")
            ]])
        )
        return ConversationHandler.END
    
    # Показываем список ожидающих платежей
    payments_text = "💰 *Платежи ожидающие подтверждения:*\n\n"
    
    keyboard = []
    
    for payment in pending_payments:
        user_data = db.get_user(payment['user_id'])
        plan_info = SUBSCRIPTIONS.get(payment['plan'], SUBSCRIPTIONS['trial'])
        
        if user_data:
            payments_text += f"👤 {user_data['first_name']} (`{payment['user_id']}`)\n"
            payments_text += f"💎 {plan_info['name']} - {payment['amount']}₽\n"
            payments_text += f"📅 {payment['created_at'].strftime('%d.%m.%Y %H:%M')}\n\n"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"✅ Подтвердить {user_data['first_name']} - {plan_info['name']}",
                    callback_data=f"confirm_pay_{payment['id']}_{payment['user_id']}_{payment['plan']}"
                )
            ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")])
    
    await query.edit_message_text(
        payments_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def confirm_payment_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение конкретного платежа"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    # Парсим данные из callback_data
    data_parts = query.data.split('_')
    payment_id = int(data_parts[2])
    target_user_id = int(data_parts[3])
    plan_id = data_parts[4]
    
    plan_info = SUBSCRIPTIONS.get(plan_id, SUBSCRIPTIONS['trial'])
    
    # Обновляем подписку пользователя
    new_end_date = datetime.now() + timedelta(days=plan_info['duration'])
    
    db.update_user(
        telegram_id=target_user_id,
        subscription_plan=plan_id,
        subscription_end=new_end_date
    )
    
    # Обновляем статус платежа
    db.update_payment_status(payment_id, 'confirmed')
    
    # Уведомляем пользователя
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"✅ *Оплата подтверждена!*\n\n"
                 f"💎 Подписка: {plan_info['name']}\n"
                 f"⏰ Действует до: {new_end_date.strftime('%d.%m.%Y %H:%M')}\n\n"
                 f"📋 *Ваши лимиты:*\n"
                 f"• Аккаунтов: {plan_info['accounts_limit']}\n"
                 f"• Сообщений в день: {plan_info['messages_limit']}\n"
                 f"• Срок: {plan_info['duration']} дней\n\n"
                 f"Теперь вы можете:\n"
                 f"• Подключить аккаунт через 🤖 Подключить аккаунт\n"
                 f"• Начать рассылку через 📨 Начать рассылку\n\n"
                 f"🔒 Для доступа к приватному каналу обратитесь к администратору",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Error notifying user {target_user_id}: {e}")
    
    await query.edit_message_text(
        f"✅ Платёж подтверждён!\n\n"
        f"👤 Пользователь: `{target_user_id}`\n"
        f"💎 Тариф: {plan_info['name']}\n"
        f"⏰ До: {new_end_date.strftime('%d.%m.%Y %H:%M')}",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")
        ]])
    )


async def admin_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать бэкап базы данных"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    try:
        backup_path = db.backup_database()
        users_count = len(db.get_all_users())
        
        await query.edit_message_text(
            f"✅ *Бэкап создан успешно!*\n\n"
            f"📁 Файл: `{backup_path}`\n"
            f"👥 Пользователей: {users_count}\n"
            f"⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
            f"Бэкап сохранён на сервере.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")
            ]])
        )
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        await query.edit_message_text(
            f"❌ Ошибка при создании бэкапа:\n{str(e)}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")
            ]])
        )


async def back_to_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться в админ-панель"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    stats = db.get_stats()
    
    admin_text = f"""
🔧 *Панель администратора*

📊 *Статистика:*
👥 Всего пользователей: {stats.get('total_users', 0)}
💰 Активных подписок: {stats.get('active_subscriptions', 0)}
📅 Новых за сегодня: {stats.get('new_today', 0)}

💎 *По тарифам:*
• Любительская: {stats.get('amateur_users', 0)}
• Профессиональная: {stats.get('pro_users', 0)}
• Премиум: {stats.get('premium_users', 0)}

Выберите действие:
    """
    
    await query.edit_message_text(
        admin_text,
        reply_markup=get_admin_keyboard(),
        parse_mode='Markdown'
    )


# ============= ПОДКЛЮЧЕНИЕ ЮЗЕРБОТА =============

async def connect_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало подключения юзербота"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    # Проверка активной подписки
    if not user_data or user_data['subscription_end'] < datetime.now():
        await query.answer(
            "❌ Для подключения аккаунта нужна активная подписка!",
            show_alert=True
        )
        await query.edit_message_text(
            "💎 Для подключения аккаунта необходимо приобрести подписку.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💎 Посмотреть тарифы", callback_data="view_tariffs")
            ]])
        )
        return ConversationHandler.END
    
    await query.edit_message_text(
        "📱 *Подключение аккаунта*\n\n"
        "Введите номер телефона в международном формате:\n"
        "Пример: `+79991234567`\n\n"
        "⚠️ Этот аккаунт будет использоваться для рассылок!\n\n"
        "Используйте /cancel для отмены",
        parse_mode='Markdown'
    )
    
    return PHONE


async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение номера телефона"""
    user_id = update.effective_user.id
    phone = update.message.text.strip()
    
    # Валидация номера
    if not phone.startswith('+') or not phone[1:].isdigit():
        await update.message.reply_text(
            "❌ Неверный формат номера!\n\n"
            "Используйте международный формат: `+79991234567`\n\n"
            "Попробуйте снова или /cancel для отмены",
            parse_mode='Markdown'
        )
        return PHONE
    
    # Сохраняем номер
    context.user_data['phone'] = phone
    
    try:
        # Отправляем код через юзербота
        result = await userbot_manager.send_code(phone)
        
        if result['success']:
            context.user_data['phone_code_hash'] = result['phone_code_hash']
            
            await update.message.reply_text(
                "📩 *Код отправлен!*\n\n"
                "Введите код из Telegram:\n"
                "Пример: `12345`",
                parse_mode='Markdown'
            )
            return CODE
        else:
            await update.message.reply_text(
                f"❌ Ошибка отправки кода:\n{result.get('error', 'Неизвестная ошибка')}\n\n"
                "Попробуйте снова или /cancel для отмены"
            )
            return PHONE
            
    except Exception as e:
        logger.error(f"Error sending code: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка. Попробуйте позже или /cancel"
        )
        return ConversationHandler.END


async def receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение кода подтверждения"""
    user_id = update.effective_user.id
    code = update.message.text.strip()
    
    phone = context.user_data.get('phone')
    phone_code_hash = context.user_data.get('phone_code_hash')
    
    if not phone or not phone_code_hash:
        await update.message.reply_text("❌ Ошибка сессии. Начните заново: 🤖 Подключить аккаунт")
        return ConversationHandler.END
    
    try:
        # Авторизация с кодом
        result = await userbot_manager.sign_in(phone, code, phone_code_hash)
        
        if result['success']:
            # Успешная авторизация
            session_id = result['session_id']
            
            # Сохраняем в БД
            db.update_user(
                telegram_id=user_id,
                phone_number=phone,
                session_id=session_id
            )
            
            await update.message.reply_text(
                                "✅ *Аккаунт успешно подключен!*\n\n"
                "Теперь вы можете:\n"
                "• 📨 Начать рассылку через свой аккаунт\n"
                "• 💬 Отправлять сообщения от своего имени\n\n"
                "🔒 Для доступа к приватному каналу обратитесь к администратору.",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
            
            # Уведомляем админа о новом подключении
            try:
                user_data = db.get_user(user_id)
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🤖 *Новое подключение аккаунта*\n\n"
                         f"👤 Пользователь: {update.effective_user.first_name}\n"
                         f"🆔 ID: `{user_id}`\n"
                         f"📱 Телефон: `{phone}`\n\n"
                         f"Добавьте пользователя в приватный канал: {PRIVATE_CHANNEL_URL}",
                    parse_mode='Markdown'
                )
            except:
                pass
            
            # Очистка данных
            context.user_data.clear()
            return ConversationHandler.END
            
        elif result.get('password_required'):
            # Требуется 2FA пароль
            await update.message.reply_text(
                "🔐 *Требуется двухфакторная аутентификация*\n\n"
                "Введите пароль 2FA:",
                parse_mode='Markdown'
            )
            return PASSWORD
            
        else:
            await update.message.reply_text(
                f"❌ Ошибка авторизации:\n{result.get('error', 'Неверный код')}\n\n"
                "Попробуйте ещё раз или /cancel"
            )
            return CODE
            
    except Exception as e:
        logger.error(f"Error signing in: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка. Попробуйте позже или /cancel"
        )
        return ConversationHandler.END


async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение пароля 2FA"""
    user_id = update.effective_user.id
    password = update.message.text.strip()
    
    phone = context.user_data.get('phone')
    
    if not phone:
        await update.message.reply_text("❌ Ошибка сессии. Начните заново: 🤖 Подключить аккаунт")
        return ConversationHandler.END
    
    try:
        # Авторизация с паролем
        result = await userbot_manager.sign_in_2fa(phone, password)
        
        if result['success']:
            session_id = result['session_id']
            
            # Сохраняем в БД
            db.update_user(
                telegram_id=user_id,
                phone_number=phone,
                session_id=session_id
            )
            
            await update.message.reply_text(
                "✅ *Аккаунт успешно подключен!*\n\n"
                "Теперь вы можете:\n"
                "• 📨 Начать рассылку через свой аккаунт\n"
                "• 💬 Отправлять сообщения от своего имени\n\n"
                "🔒 Для доступа к приватному каналу обратитесь к администратору.",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
            
            # Уведомляем админа
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🤖 *Новое подключение аккаунта*\n\n"
                         f"👤 Пользователь: {update.effective_user.first_name}\n"
                         f"🆔 ID: `{user_id}`\n"
                         f"📱 Телефон: `{phone}`\n\n"
                         f"Добавьте пользователя в приватный канал: {PRIVATE_CHANNEL_URL}",
                    parse_mode='Markdown'
                )
            except:
                pass
            
            context.user_data.clear()
            return ConversationHandler.END
            
        else:
            await update.message.reply_text(
                f"❌ Ошибка:\n{result.get('error', 'Неверный пароль')}\n\n"
                "Попробуйте ещё раз или /cancel"
            )
            return PASSWORD
            
    except Exception as e:
        logger.error(f"Error with 2FA: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка. Попробуйте позже или /cancel"
        )
        return ConversationHandler.END


# ============= ПОДДЕРЖКА =============

async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало обращения в поддержку"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "💬 *Техническая поддержка*\n\n"
        "Опишите вашу проблему или вопрос.\n"
        "Можете отправить текст или фото с описанием.\n\n"
        "Администратор ответит вам в ближайшее время.\n\n"
        "Используйте /cancel для отмены",
        parse_mode='Markdown'
    )
    
    return SUPPORT_MESSAGE


async def receive_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение текстового сообщения для поддержки"""
    user = update.effective_user
    message_text = update.message.text
    
    # Сохраняем обращение в БД
    db.add_support_ticket(user.id, message_text)
    
    # Отправляем админу
    admin_keyboard = [[
        InlineKeyboardButton("✉️ Ответить", url=f"tg://user?id={user.id}")
    ]]
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📩 *Новое обращение в поддержку*\n\n"
             f"👤 От: {user.first_name} (@{user.username or 'нет'})\n"
             f"🆔 ID: `{user.id}`\n\n"
             f"💬 Сообщение:\n{message_text}",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(admin_keyboard)
    )
    
    await update.message.reply_text(
        "✅ Ваше сообщение отправлено в поддержку!\n\n"
        "Администратор ответит вам в личные сообщения.",
        reply_markup=get_main_menu_keyboard()
    )
    
    return ConversationHandler.END


async def receive_support_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение фото для поддержки"""
    user = update.effective_user
    caption = update.message.caption or "Фото без описания"
    photo = update.message.photo[-1]
    
    # Сохраняем обращение в БД
    db.add_support_ticket(user.id, f"[ФОТО] {caption}")
    
    # Отправляем админу
    admin_keyboard = [[
        InlineKeyboardButton("✉️ Ответить", url=f"tg://user?id={user.id}")
    ]]
    
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo.file_id,
        caption=f"📩 *Новое обращение в поддержку*\n\n"
                f"👤 От: {user.first_name} (@{user.username or 'нет'})\n"
                f"🆔 ID: `{user.id}`\n\n"
                f"💬 Описание:\n{caption}",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(admin_keyboard)
    )
    
    await update.message.reply_text(
        "✅ Ваше фото отправлено в поддержку!\n\n"
        "Администратор ответит вам в личные сообщения.",
        reply_markup=get_main_menu_keyboard()
    )
    
    return ConversationHandler.END


# ============= ОПЛАТА =============

async def payment_select_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор тарифного плана"""
    query = update.callback_query
    await query.answer()
    
    plan_id = query.data.replace('buy_', '')
    
    if plan_id not in SUBSCRIPTIONS:
        await query.answer("❌ Тариф не найден", show_alert=True)
        return ConversationHandler.END
    
    plan = SUBSCRIPTIONS[plan_id]
    context.user_data['selected_plan'] = plan_id
    
    keyboard = [
        [InlineKeyboardButton("📸 Отправить чек", callback_data="send_receipt")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel_payment")]
    ]
    
    await query.edit_message_text(
        f"💳 *Оформление подписки*\n\n"
        f"📦 *Тариф:* {plan['name']}\n"
        f"💰 *Цена:* {plan['price']}₽\n"
        f"⏰ *Срок:* {plan['duration']} дней\n\n"
        f"📋 *Что входит:*\n"
        f"{plan['description']}\n\n"
        f"💳 *Реквизиты для оплаты:*\n"
        f"Карта: `{PAYMENT_CARD}`\n"
        f"СБП(На любой банк): `{PAYMENT_PHONE}`\n\n"
        f"❗ После оплаты нажмите 'Отправить чек' и пришлите скриншот платежа.",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return PAYMENT_RECEIPT


async def send_receipt_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрос чека об оплате"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📸 *Отправьте скриншот чека об оплате*\n\n"
        "После проверки администратор активирует вашу подписку.\n\n"
        "Используйте /cancel для отмены",
        parse_mode='Markdown'
    )
    
    return PAYMENT_RECEIPT


async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение чека от пользователя"""
    user_id = update.effective_user.id
    plan_id = context.user_data.get('selected_plan')
    
    if not plan_id or plan_id not in SUBSCRIPTIONS:
        await update.message.reply_text("❌ Ошибка: тариф не выбран")
        return ConversationHandler.END
    
    plan = SUBSCRIPTIONS[plan_id]
    
    # Проверяем что отправлено фото
    if not update.message.photo:
        await update.message.reply_text(
            "❌ Пожалуйста, отправьте фото чека!\n\n"
            "Или используйте /cancel для отмены"
        )
        return PAYMENT_RECEIPT
    
    photo = update.message.photo[-1]
    
    # Сохраняем платёж в БД
    payment_id = db.add_payment(
        user_id=user_id,
        amount=plan['price'],
        plan=plan_id,
        status='pending'
    )
    
    # Отправляем админу чек и кнопку подтверждения
    keyboard = [[
        InlineKeyboardButton(
            "✅ Подтвердить оплату",
            callback_data=f"confirm_pay_{payment_id}_{user_id}_{plan_id}"
        )
    ]]
    
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo.file_id,
        caption=f"💰 *Новый платёж*\n\n"
                f"👤 Пользователь: {update.effective_user.first_name}\n"
                f"🆔 ID: `{user_id}`\n"
                f"📦 Тариф: {plan['name']}\n"
                f"💵 Сумма: {plan['price']}₽\n\n"
                f"❗ Проверьте чек и подтвердите оплату кнопкой ниже:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    await update.message.reply_text(
        "✅ *Чек отправлен администратору!*\n\n"
        "⏳ Ожидайте подтверждения платежа.\n"
        "Обычно это занимает несколько минут.\n\n"
        "Вы получите уведомление после активации подписки.",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )
    
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена оплаты"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    
    await query.edit_message_text(
        "❌ Оплата отменена",
        reply_markup=get_main_menu_keyboard()
    )
    
    return ConversationHandler.END


# ============= РАССЫЛКА ПОЛЬЗОВАТЕЛЯ (ЧЕРЕЗ ЕГО ЮЗЕРБОТ) =============

async def user_mailing_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало рассылки пользователя"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    # Проверка подключения юзербота
    if not user_data or not user_data.get('session_id'):
        await query.edit_message_text(
            "❌ *Аккаунт не подключен!*\n\n"
            "Сначала подключите свой Telegram аккаунт.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🤖 Подключить аккаунт", callback_data="connect_userbot")
            ]])
        )
        return ConversationHandler.END
    
    # Проверка активной подписки
    if user_data['subscription_end'] < datetime.now():
        await query.edit_message_text(
            "❌ *Подписка истекла!*\n\n"
            "Для использования рассылки нужна активная подписка.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💎 Продлить подписку", callback_data="view_tariffs")
            ]])
        )
        return ConversationHandler.END
    
    # Получаем лимиты тарифа
    plan_info = SUBSCRIPTIONS.get(user_data['subscription_plan'], SUBSCRIPTIONS['trial'])
    
    await query.edit_message_text(
        f"📨 *Создание рассылки*\n\n"
        f"📋 *Ваши лимиты:*\n"
        f"• Сообщений в день: {plan_info['messages_limit']}\n"
        f"• Аккаунтов: {plan_info['accounts_limit']}\n\n"
        f"📝 *Шаг 1: Укажите получателей*\n\n"
        f"Отправьте usernames через запятую:\n"
        f"Пример: `@user1, @user2, @user3`\n\n"
        f"Или отправьте ссылки на группы/каналы:\n"
        f"Пример: `https://t.me/group1, https://t.me/group2`\n\n"
        f"⚠️ Рассылка будет отправлена с ВАШЕГО подключенного аккаунта!\n\n"
        f"Используйте /cancel для отмены",
        parse_mode='Markdown'
    )
    
    return USER_MAILING_TARGETS


async def receive_mailing_targets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение списка получателей"""
    user_id = update.effective_user.id
    targets_text = update.message.text.strip()
    
    # Парсим получателей
    targets = [t.strip() for t in targets_text.split(',') if t.strip()]
    
    if not targets:
        await update.message.reply_text(
            "❌ Не указаны получатели!\n\n"
            "Отправьте usernames или ссылки через запятую.\n"
            "Или /cancel для отмены"
        )
        return USER_MAILING_TARGETS
    
    # Проверка лимитов
    user_data = db.get_user(user_id)
    plan_info = SUBSCRIPTIONS.get(user_data['subscription_plan'], SUBSCRIPTIONS['trial'])
    
    if len(targets) > plan_info['messages_limit']:
        await update.message.reply_text(
            f"❌ Превышен лимит!\n\n"
            f"Ваш лимит: {plan_info['messages_limit']} сообщений\n"
            f"Вы указали: {len(targets)}\n\n"
            f"Уберите лишних получателей или /cancel"
        )
        return USER_MAILING_TARGETS
    
    # Сохраняем получателей
    context.user_data['mailing_targets'] = targets
    
    await update.message.reply_text(
        f"✅ Получателей: {len(targets)}\n\n"
        f"📝 *Шаг 2: Отправьте сообщение для рассылки*\n\n"
        f"Можете отправить:\n"
        f"• Текст\n"
        f"• Фото с подписью\n"
        f"• Видео с подписью\n\n"
        f"Это сообщение будет отправлено всем получателям с ВАШЕГО аккаунта.",
        parse_mode='Markdown'
    )
    
    return USER_MAILING_MESSAGE


async def receive_user_mailing_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение сообщения для рассылки"""
    user_id = update.effective_user.id
    
    # Сохраняем сообщение
    context.user_data['mailing_message'] = update.message
    
    targets = context.user_data.get('mailing_targets', [])
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Начать рассылку", callback_data="start_user_mailing"),
            InlineKeyboardButton("❌ Отменить", callback_data="cancel_user_mailing")
        ]
    ]
    
    await update.message.reply_text(
        f"📨 *Подтверждение рассылки*\n\n"
        f"👥 Получателей: {len(targets)}\n"
        f"📝 Сообщение готово к отправке\n\n"
        f"⚠️ Рассылка будет отправлена с ВАШЕГО подключенного аккаунта!\n"
        f"⏱️ Задержка между сообщениями: {MAILING_DELAY}s (защита от флуда)\n\n"
        f"Начать?",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return USER_MAILING_CONFIRM


async def start_user_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск рассылки через юзербот пользователя"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    if not user_data or not user_data.get('session_id'):
        await query.edit_message_text("❌ Аккаунт не подключен")
        return ConversationHandler.END
    
    targets = context.user_data.get('mailing_targets', [])
    mailing_message = context.user_data.get('mailing_message')
    
    if not targets or not mailing_message:
        await query.edit_message_text("❌ Ошибка: данные рассылки не найдены")
        return ConversationHandler.END
    
    session_id = user_data['session_id']
    phone = user_data['phone_number']
    
    sent = 0
    errors = 0
    
    await query.edit_message_text(
        f"📨 *Рассылка запущена!*\n\n"
        f"Отправлено: 0/{len(targets)}\n"
        f"⏱️ Задержка между сообщениями: {MAILING_DELAY}s",
        parse_mode='Markdown'
    )
    
    # Отправка через юзербот
    for idx, target in enumerate(targets, 1):
        try:
            # Определяем тип сообщения
            if mailing_message.text:
                result = await userbot_manager.send_message(
                    session_id=session_id,
                    phone=phone,
                    target=target,
                    message=mailing_message.text
                )
            elif mailing_message.photo:
                # Скачиваем фото
                photo = mailing_message.photo[-1]
                file = await context.bot.get_file(photo.file_id)
                photo_path = f"temp_{user_id}_{photo.file_id}.jpg"
                await file.download_to_drive(photo_path)
                
                result = await userbot_manager.send_photo(
                    session_id=session_id,
                    phone=phone,
                    target=target,
                    photo_path=photo_path,
                    caption=mailing_message.caption or ""
                )
                
                # Удаляем временный файл
                import os
                if os.path.exists(photo_path):
                    os.remove(photo_path)
            
            elif mailing_message.video:
                # Скачиваем видео
                video = mailing_message.video
                file = await context.bot.get_file(video.file_id)
                video_path = f"temp_{user_id}_{video.file_id}.mp4"
                await file.download_to_drive(video_path)
                
                result = await userbot_manager.send_video(
                    session_id=session_id,
                    phone=phone,
                    target=target,
                    video_path=video_path,
                    caption=mailing_message.caption or ""
                )
                
                # Удаляем временный файл
                import os
                if os.path.exists(video_path):
                    os.remove(video_path)
            
            if result.get('success'):
                sent += 1
            else:
                errors += 1
                logger.error(f"Error sending to {target}: {result.get('error')}")
            
            # Обновляем прогресс каждые 5 сообщений
            if idx % 5 == 0 or idx == len(targets):
                try:
                    await query.edit_message_text(
                        f"📨 *Рассылка в процессе...*\n\n"
                        f"✅ Отправлено: {sent}/{len(targets)}\n"
                        f"❌ Ошибок: {errors}\n"
                        f"⏱️ Осталось ~{int((len(targets) - idx) * MAILING_DELAY)}s",
                        parse_mode='Markdown'
                    )
                except:
                    pass
            
            # Задержка между сообщениями (анти-флуд)
            if idx < len(targets):  # Не ждём после последнего сообщения
                await asyncio.sleep(MAILING_DELAY)
            
        except Exception as e:
            errors += 1
            logger.error(f"Error in mailing to {target}: {e}")
    
    # Сохраняем рассылку в БД
    message_text = mailing_message.text or mailing_message.caption or "[Медиа]"
    db.add_mailing(user_id, message_text, sent, errors)
    
    # Финальный отчёт
    await query.edit_message_text(
        f"✅ *Рассылка завершена!*\n\n"
        f"📊 Статистика:\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Ошибок: {errors}\n"
        f"👥 Всего получателей: {len(targets)}\n"
        f"⏱️ Время выполнения: ~{int(len(targets) * MAILING_DELAY)}s",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )
    
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_user_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена рассылки пользователя"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    
    await query.edit_message_text(
        "❌ Рассылка отменена",
        reply_markup=get_main_menu_keyboard()
    )
    
    return ConversationHandler.END


# ============= РАССЫЛКА АДМИНА (ПО ВСЕМ ПОЛЬЗОВАТЕЛЯМ БОТА) =============

async def start_admin_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания рассылки админа"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await query.answer("❌ Доступно только администратору!", show_alert=True)
        return ConversationHandler.END
    
    try:
        await query.edit_message_text(
            "📮 *Создание рассылки для всех пользователей бота*\n\n"
            "Отправьте сообщение для рассылки:\n"
            "• Текст\n"
            "• Фото с подписью\n"
            "• Видео с подписью\n\n"
            "Это сообщение получат ВСЕ пользователи бота!\n\n"
            "Используйте /cancel для отмены",
            parse_mode='Markdown'
        )
        return MAILING_MESSAGE
    except Exception as e:
        logger.error(f"Error starting admin mailing: {e}")
        await query.message.reply_text("❌ Ошибка при запуске рассылки")
        return ConversationHandler.END


async def receive_admin_mailing_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение сообщения для рассылки админа"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        return ConversationHandler.END
    
    # Сохраняем сообщение
    context.user_data['admin_mailing_message'] = update.message
    
    # Получаем всех пользователей
    users = db.get_all_users()
    total_users = len(users)
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Отправить всем", callback_data="confirm_admin_mailing"),
            InlineKeyboardButton("❌ Отменить", callback_data="cancel_admin_mailing")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📮 *Предпросмотр рассылки*\n\n"
        f"👥 Получателей: {total_users}\n"
        f"⏱️ Задержка: {MAILING_DELAY}s между сообщениями\n"
        f"⏱️ Примерное время: ~{int(total_users * MAILING_DELAY / 60)} минут\n\n"
        f"Отправить рассылку ВСЕМ пользователям бота?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    return MAILING_CONFIRM


async def confirm_admin_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение и отправка рассылки админа"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return ConversationHandler.END
    
    mailing_message = context.user_data.get('admin_mailing_message')
    
    if not mailing_message:
        await query.edit_message_text("❌ Сообщение для рассылки не найдено")
        return ConversationHandler.END
    
    users = db.get_all_users()
    total = len(users)
    sent = 0
    errors = 0
    
    await query.edit_message_text(
        f"📮 *Рассылка запущена!*\n\n"
        f"⏱️ Задержка: {MAILING_DELAY}s\n"
        f"Отправлено: 0/{total}",
        parse_mode='Markdown'
    )
    
    for idx, user in enumerate(users, 1):
        try:
            # Определяем тип сообщения и отправляем
            if mailing_message.text:
                await context.bot.send_message(
                    chat_id=user['telegram_id'],
                    text=mailing_message.text
                )
            elif mailing_message.photo:
                await context.bot.send_photo(
                    chat_id=user['telegram_id'],
                    photo=mailing_message.photo[-1].file_id,
                    caption=mailing_message.caption
                )
            elif mailing_message.video:
                await context.bot.send_video(
                    chat_id=user['telegram_id'],
                    video=mailing_message.video.file_id,
                    caption=mailing_message.caption
                )
            
            sent += 1
            
            # Обновляем прогресс каждые 10 пользователей
            if idx % 10 == 0 or idx == total:
                try:
                    await query.edit_message_text(
                        f"📮 *Рассылка в процессе...*\n\n"
                        f"✅ Отправлено: {sent}/{total}\n"
                        f"❌ Ошибок: {errors}\n"
                        f"⏱️ Осталось ~{int((total - idx) * MAILING_DELAY)}s",
                        parse_mode='Markdown'
                    )
                except:
                    pass
            
            # Задержка между сообщениями
            if idx < total:
                await asyncio.sleep(MAILING_DELAY)
            
        except Exception as e:
            errors += 1
            logger.error(f"Error sending to {user['telegram_id']}: {e}")
    
    # Сохраняем рассылку в БД
    message_text = mailing_message.text or mailing_message.caption or "[Медиа]"
    db.add_mailing(user_id, message_text, sent, errors)
    
    # Финальное сообщение
    await query.edit_message_text(
        f"✅ *Рассылка завершена!*\n\n"
        f"📊 Статистика:\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Ошибок: {errors}\n"
        f"👥 Всего пользователей: {total}\n"
        f"⏱️ Задержка: {MAILING_DELAY}s",
        parse_mode='Markdown'
    )
    
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_admin_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена рассылки админа"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    
    await query.edit_message_text("❌ Рассылка отменена")
    
    return ConversationHandler.END


# ============= CONVERSATION HANDLERS =============

# Подключение юзербота
connect_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(connect_start, pattern="^connect_userbot$")],
    states={
        PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
        CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_code)],
        PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=True,
    per_chat=True,
    per_user=True,
)

# Поддержка
support_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(support_start, pattern="^support$")],
    states={
        SUPPORT_MESSAGE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_support_message),
            MessageHandler(filters.PHOTO, receive_support_photo)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=True,
    per_chat=True,
    per_user=True,
)

# Оплата
payment_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(payment_select_plan, pattern="^buy_")],
    states={
        PAYMENT_RECEIPT: [
            CallbackQueryHandler(send_receipt_prompt, pattern="^send_receipt$"),
            CallbackQueryHandler(cancel_payment, pattern="^cancel_payment$"),
            MessageHandler(filters.PHOTO, receive_receipt)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=True,
    per_chat=True,
    per_user=True,
)

# Рассылка пользователя
user_mailing_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(user_mailing_start, pattern="^start_mailing$")],
    states={
        USER_MAILING_TARGETS: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_mailing_targets)
        ],
        USER_MAILING_MESSAGE: [
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.VIDEO) & ~filters.COMMAND,
                receive_user_mailing_message
            )
        ],
        USER_MAILING_CONFIRM: [
            CallbackQueryHandler(start_user_mailing, pattern="^start_user_mailing$"),
            CallbackQueryHandler(cancel_user_mailing, pattern="^cancel_user_mailing$")
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=True,
    per_chat=True,
    per_user=True,
)

# Рассылка админа
admin_mailing_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_admin_mailing, pattern="^admin_mailing$")],
    states={
        MAILING_MESSAGE: [
            MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO & ~filters.COMMAND, receive_admin_mailing_message)
        ],
        MAILING_CONFIRM: [
            CallbackQueryHandler(confirm_admin_mailing, pattern="^confirm_admin_mailing$"),
            CallbackQueryHandler(cancel_admin_mailing, pattern="^cancel_admin_mailing$"),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=True,
    per_chat=True,
    per_user=True,
)


# ============= ГЛАВНАЯ ФУНКЦИЯ =============

def main():
    """Запуск бота"""
    # Создание приложения
    application = Application.builder().token(MANAGER_BOT_TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("admin", admin_panel))
    
    # ConversationHandlers (ВАЖНО: добавляем ДО обычных callback'ов!)
    application.add_handler(connect_conv)
    application.add_handler(support_conv)
    application.add_handler(payment_conv)
    application.add_handler(user_mailing_conv)
    application.add_handler(admin_mailing_conv)
    
    # Callback обработчики
    application.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_subscription$"))
    application.add_handler(CallbackQueryHandler(my_status_callback, pattern="^my_status$"))
    application.add_handler(CallbackQueryHandler(view_tariffs_callback, pattern="^view_tariffs$"))
    application.add_handler(CallbackQueryHandler(back_to_menu_callback, pattern="^back_to_menu$"))
    
    # Админ callbacks
    application.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(admin_users_list, pattern="^admin_users$"))
    application.add_handler(CallbackQueryHandler(admin_payments_callback, pattern="^admin_payments$"))
    application.add_handler(CallbackQueryHandler(confirm_payment_admin, pattern="^confirm_pay_"))
    application.add_handler(CallbackQueryHandler(admin_backup, pattern="^admin_backup$"))
    application.add_handler(CallbackQueryHandler(back_to_admin_callback, pattern="^back_to_admin$"))
    
    logger.info("🚀 Manager Bot started!")
    logger.info(f"📋 Subscriptions available: {len(SUBSCRIPTIONS)}")
    logger.info(f"👤 Admin ID: {ADMIN_ID}")
    logger.info(f"📢 Public channel: {PUBLIC_CHANNEL_URL}")
    logger.info(f"🔒 Private channel: {PRIVATE_CHANNEL_URL}")
    
    # Запуск polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()