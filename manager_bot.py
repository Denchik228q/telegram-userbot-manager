#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Manager Bot - Бот для управления юзерботом и подписками
"""

import logging
import asyncio
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
    CHANNEL_1_URL,
    CHANNEL_2_URL,
    CHANNEL_3_URL,
    PRIVATE_CHANNEL_URL,
    CHANNEL_1_NAME,
    CHANNEL_2_NAME,
    CHANNEL_3_NAME,
    PRIVATE_CHANNEL_NAME,
    SUBSCRIPTIONS
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
SUPPORT_MESSAGE = 10

# Оплата
PAYMENT_PLAN, PAYMENT_CONFIRM = range(20, 22)

# Рассылка
MAILING_MESSAGE = 100
MAILING_CONFIRM = 101

# ============= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =============

async def check_subscriptions(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверка подписки на все каналы"""
    channels = [
        (CHANNEL_1_URL, CHANNEL_1_NAME),
        (CHANNEL_2_URL, CHANNEL_2_NAME),
        (CHANNEL_3_URL, CHANNEL_3_NAME)
    ]
    
    for channel_url, channel_name in channels:
        try:
            # Убираем @ если есть
            channel_username = channel_url.replace('@', '').replace('https://t.me/', '')
            
            # Проверяем подписку
            member = await context.bot.get_chat_member(
                chat_id=f"@{channel_username}",
                user_id=user_id
            )
            
            # Если не подписан
            if member.status in ['left', 'kicked']:
                return False
                
        except Exception as e:
            logger.error(f"Error checking subscription for {channel_name}: {e}")
            # Если канал приватный или ошибка - пропускаем проверку
            continue
    
    return True


def get_subscription_keyboard():
    """Клавиатура с кнопками подписки на каналы"""
    keyboard = [
        [InlineKeyboardButton(f"📢 {CHANNEL_1_NAME}", url=CHANNEL_1_URL if CHANNEL_1_URL.startswith('http') else f"https://t.me/{CHANNEL_1_URL.replace('@', '')}")],
        [InlineKeyboardButton(f"💎 {CHANNEL_2_NAME}", url=CHANNEL_2_URL if CHANNEL_2_URL.startswith('http') else f"https://t.me/{CHANNEL_2_URL.replace('@', '')}")],
        [InlineKeyboardButton(f"🔔 {CHANNEL_3_NAME}", url=CHANNEL_3_URL if CHANNEL_3_URL.startswith('http') else f"https://t.me/{CHANNEL_3_URL.replace('@', '')}")],
        [InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_main_menu_keyboard(has_subscription: bool = False):
    """Главное меню бота"""
    keyboard = []
    
    if has_subscription:
        keyboard.append([InlineKeyboardButton("🤖 Подключить юзербота", callback_data="connect_userbot")])
    
    keyboard.extend([
        [InlineKeyboardButton("📊 Мой статус", callback_data="my_status")],
        [InlineKeyboardButton("💎 Тарифы", callback_data="view_tariffs")],
        [InlineKeyboardButton("💬 Поддержка", callback_data="support")]
    ])
    
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
            subscription_plan="Trial",
            subscription_end=datetime.now() + timedelta(days=3)
        )
        logger.info(f"✅ New user registered: {user_id}")
    
    # Проверка подписок
    is_subscribed = await check_subscriptions(user_id, context)
    
    if not is_subscribed:
        await update.message.reply_text(
            f"👋 Добро пожаловать, {user.first_name}!\n\n"
            f"🔔 Для начала работы подпишитесь на наши каналы:",
            reply_markup=get_subscription_keyboard()
        )
    else:
        user_data = db.get_user(user_id)
        has_subscription = user_data and user_data['subscription_plan'] != 'Trial'
        
        await update.message.reply_text(
            f"👋 С возвращением, {user.first_name}!\n\n"
            f"Выберите действие:",
            reply_markup=get_main_menu_keyboard(has_subscription)
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
📚 *Доступные команды:*

/start - Начать работу с ботом
/help - Показать эту справку
/status - Проверить статус подписки
/connect - Подключить юзербота
/support - Связаться с поддержкой
/tariffs - Посмотреть тарифы
/cancel - Отменить текущую операцию

💡 *Как использовать бота:*

1️⃣ Подпишитесь на все каналы
2️⃣ Выберите тариф и оплатите
3️⃣ Подключите свой Telegram аккаунт через /connect
4️⃣ Получите доступ к приватному каналу

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
    
    # Проверка юзербота
    session_id = user_data.get('session_id', '')
    userbot_status = "✅ Подключен" if session_id else "❌ Не подключен"
    
    status_text = f"""
📊 *Ваш статус:*

👤 ID: `{user_id}`
📱 Телефон: {user_data.get('phone_number', 'Не указан')}
📦 Подписка: {user_data['subscription_plan']}
⏰ Действует до: {user_data['subscription_end'].strftime('%d.%m.%Y %H:%M')}
{status_emoji} Статус: {'Активна' if subscription_active else 'Истекла'}

🤖 Юзербот: {userbot_status}
🔒 Доступ к приватному каналу: {status_emoji}
    """
    
    await update.message.reply_text(
        status_text,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard(subscription_active)
    )


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-панель"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет доступа к админ-панели")
        return
    
    # Статистика
    users = db.get_all_users()
    total_users = len(users)
    active_subs = len([u for u in users if u['subscription_end'] > datetime.now() and u['subscription_plan'] != 'Trial'])
    new_today = len([u for u in users if u['created_at'].date() == datetime.now().date()])
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("📮 Создать рассылку", callback_data="admin_mailing")],
        [InlineKeyboardButton("💸 Платежи", callback_data="admin_payments")],
        [InlineKeyboardButton("💾 Бэкап БД", callback_data="admin_backup")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    admin_text = f"""
🔧 *Панель администратора*

📊 *Статистика:*
👥 Всего пользователей: {total_users}
💰 Активных подписок: {active_subs}
📅 Новых за сегодня: {new_today}

Выберите действие:
    """
    
    await update.message.reply_text(admin_text, reply_markup=reply_markup, parse_mode='Markdown')


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущей операции"""
    await update.message.reply_text(
        "❌ Операция отменена",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END


# ============= CALLBACK ОБРАБОТЧИКИ =============

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка подписки на каналы"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    is_subscribed = await check_subscriptions(user_id, context)
    
    if is_subscribed:
        user_data = db.get_user(user_id)
        has_subscription = user_data and user_data['subscription_plan'] != 'Trial'
        
        await query.edit_message_text(
            "✅ Отлично! Вы подписаны на все каналы.\n\n"
            "Выберите действие:",
            reply_markup=get_main_menu_keyboard(has_subscription)
        )
    else:
        await query.answer(
            "❌ Вы ещё не подписались на все каналы!",
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
    
    session_id = user_data.get('session_id', '')
    userbot_status = "✅ Подключен" if session_id else "❌ Не подключен"
    
    status_text = f"""
📊 *Ваш статус:*

👤 ID: `{user_id}`
📱 Телефон: {user_data.get('phone_number', 'Не указан')}
📦 Подписка: {user_data['subscription_plan']}
⏰ Действует до: {user_data['subscription_end'].strftime('%d.%m.%Y %H:%M')}
{status_emoji} Статус: {'Активна' if subscription_active else 'Истекла'}

🤖 Юзербот: {userbot_status}
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
        tariffs_text += f"*{plan['name']}* - {plan['price']}₽/{plan['duration']} дн.\n"
        tariffs_text += f"_{plan['description']}_\n\n"
        
        keyboard.append([
            InlineKeyboardButton(
                f"Купить {plan['name']}",
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
    has_subscription = user_data and user_data['subscription_plan'] != 'Trial'
    
    await query.edit_message_text(
        "Выберите действие:",
        reply_markup=get_main_menu_keyboard(has_subscription)
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
    
    users = db.get_all_users()
    total_users = len(users)
    
    # Подсчёт по тарифам
    trial_users = len([u for u in users if u['subscription_plan'] == 'Trial'])
    basic_users = len([u for u in users if u['subscription_plan'] == 'basic'])
    standard_users = len([u for u in users if u['subscription_plan'] == 'standard'])
    vip_users = len([u for u in users if u['subscription_plan'] == 'vip'])
    
    # Активные подписки
    active_subs = len([u for u in users if u['subscription_end'] > datetime.now() and u['subscription_plan'] != 'Trial'])
    
    # Новые пользователи
    today = datetime.now().date()
    new_today = len([u for u in users if u['created_at'].date() == today])
    new_week = len([u for u in users if u['created_at'].date() >= (today - timedelta(days=7))])
    
    stats_text = f"""
📊 *Детальная статистика:*

👥 *Пользователи:*
• Всего: {total_users}
• Активных подписок: {active_subs}
• Новых сегодня: {new_today}
• Новых за неделю: {new_week}

💰 *Подписки по тарифам:*
• Trial: {trial_users}
• Basic: {basic_users}
• Standard: {standard_users}
• VIP: {vip_users}
    """
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")]]
    
    await query.edit_message_text(
        stats_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
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
    
    users = db.get_all_users()
    total_users = len(users)
    active_subs = len([u for u in users if u['subscription_end'] > datetime.now() and u['subscription_plan'] != 'Trial'])
    new_today = len([u for u in users if u['created_at'].date() == datetime.now().date()])
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("📮 Создать рассылку", callback_data="admin_mailing")],
        [InlineKeyboardButton("💸 Платежи", callback_data="admin_payments")],
        [InlineKeyboardButton("💾 Бэкап БД", callback_data="admin_backup")]
    ]
    
    admin_text = f"""
🔧 *Панель администратора*

📊 *Статистика:*
👥 Всего пользователей: {total_users}
💰 Активных подписок: {active_subs}
📅 Новых за сегодня: {new_today}

Выберите действие:
    """
    
    await query.edit_message_text(
        admin_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


# ============= ПОДКЛЮЧЕНИЕ ЮЗЕРБОТА =============

async def connect_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало подключения юзербота"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    # Проверка подписки
    if not user_data or user_data['subscription_plan'] == 'Trial':
        await query.answer(
            "❌ Для подключения юзербота нужна активная подписка!",
            show_alert=True
        )
        await query.edit_message_text(
            "💎 Для подключения юзербота необходимо приобрести подписку.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💎 Посмотреть тарифы", callback_data="view_tariffs")
            ]])
        )
        return ConversationHandler.END
    
        await query.edit_message_text(
        "📱 *Подключение юзербота*\n\n"
        "Введите номер телефона в международном формате:\n"
        "Пример: `+79991234567`\n\n"
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
        await update.message.reply_text("❌ Ошибка сессии. Начните заново с /connect")
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
            
            # Добавляем в приватный канал
            try:
                await context.bot.approve_chat_join_request(
                    chat_id=PRIVATE_CHANNEL_URL,
                    user_id=user_id
                )
            except:
                pass
            
            await update.message.reply_text(
                "✅ *Юзербот успешно подключен!*\n\n"
                "🔒 Вы получили доступ к приватному каналу.",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard(True)
            )
            
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
        await update.message.reply_text("❌ Ошибка сессии. Начните заново с /connect")
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
            
            # Добавляем в приватный канал
            try:
                await context.bot.approve_chat_join_request(
                    chat_id=PRIVATE_CHANNEL_URL,
                    user_id=user_id
                )
            except:
                pass
            
            await update.message.reply_text(
                "✅ *Юзербот успешно подключен!*\n\n"
                "🔒 Вы получили доступ к приватному каналу.",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard(True)
            )
            
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
        "Администратор ответит вам в ближайшее время.\n\n"
        "Используйте /cancel для отмены",
        parse_mode='Markdown'
    )
    
    return SUPPORT_MESSAGE


async def receive_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение сообщения для поддержки"""
    user = update.effective_user
    message_text = update.message.text
    
    # Отправляем админу
    admin_keyboard = [[
        InlineKeyboardButton("✉️ Ответить", callback_data=f"support_reply_{user.id}")
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
    
    # Сохраняем в контекст для ответа
    context.bot_data[f'support_{user.id}'] = {
        'user_id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'message': message_text
    }
    
    await update.message.reply_text(
        "✅ Ваше сообщение отправлено в поддержку!\n\n"
        "Ожидайте ответа.",
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
        [InlineKeyboardButton("✅ Подтвердить оплату", callback_data="confirm_payment")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel_payment")]
    ]
    
    await query.edit_message_text(
        f"💳 *Оформление подписки*\n\n"
        f"📦 Тариф: {plan['name']}\n"
        f"💰 Цена: {plan['price']}₽\n"
        f"⏰ Срок: {plan['duration']} дней\n\n"
        f"🔸 {plan['description']}\n\n"
        f"Для оплаты переведите {plan['price']}₽ на карту или более удобным способом:\n"
        f"`2200 1536 8370 4721` \n"
        f"Юмани: '4100 1185 8989 7796' \n"
        f"Криптоперевод (TRC20): 'TD5EJBjQ3zM2SpgLCaBf4XptT7CoAFWPQr' \n\n"
        f"После оплаты нажмите 'Подтвердить оплату'",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return PAYMENT_CONFIRM


async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение оплаты"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    plan_id = context.user_data.get('selected_plan')
    
    if not plan_id or plan_id not in SUBSCRIPTIONS:
        await query.edit_message_text("❌ Ошибка: тариф не выбран")
        return ConversationHandler.END
    
    plan = SUBSCRIPTIONS[plan_id]
    
    # Уведомление админу о платеже
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"💰 *Новый платёж (ожидает подтверждения)*\n\n"
             f"👤 Пользователь: {update.effective_user.first_name}\n"
             f"🆔 ID: `{user_id}`\n"
             f"📦 Тариф: {plan['name']}\n"
             f"💵 Сумма: {plan['price']}₽\n\n"
             f"Проверьте поступление средств и выдайте подписку командой:\n"
             f"`/give_sub {user_id} {plan_id} {plan['duration']}`",
        parse_mode='Markdown'
    )
    
    await query.edit_message_text(
        "✅ Заявка на оплату отправлена!\n\n"
        "Администратор проверит платёж и активирует подписку.\n"
        "Обычно это занимает несколько минут.\n\n"
        "Вы получите уведомление после активации.",
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


# ============= РАССЫЛКА =============

async def start_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания рассылки"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await query.answer("❌ Доступно только администратору!", show_alert=True)
        return ConversationHandler.END
    
    try:
        await query.edit_message_text(
            "📮 *Создание рассылки*\n\n"
            "Отправьте сообщение для рассылки:\n"
            "• Текст\n"
            "• Фото с подписью\n"
            "• Видео с подписью\n\n"
            "Используйте /cancel для отмены",
            parse_mode='Markdown'
        )
        return MAILING_MESSAGE
    except Exception as e:
        logger.error(f"Error starting mailing: {e}")
        await query.message.reply_text("❌ Ошибка при запуске рассылки")
        return ConversationHandler.END


async def receive_mailing_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение сообщения для рассылки"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        return ConversationHandler.END
    
    # Сохраняем сообщение
    context.user_data['mailing_message'] = update.message
    
    # Получаем всех пользователей
    users = db.get_all_users()
    total_users = len(users)
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Отправить всем", callback_data="confirm_mailing"),
            InlineKeyboardButton("❌ Отменить", callback_data="cancel_mailing")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📮 *Предпросмотр рассылки*\n\n"
        f"👥 Получателей: {total_users}\n\n"
        f"Отправить рассылку?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    return MAILING_CONFIRM


async def confirm_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение и отправка рассылки"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return ConversationHandler.END
    
    mailing_message = context.user_data.get('mailing_message')
    
    if not mailing_message:
        await query.edit_message_text("❌ Сообщение для рассылки не найдено")
        return ConversationHandler.END
    
    users = db.get_all_users()
    total = len(users)
    sent = 0
    errors = 0
    
    await query.edit_message_text(
        f"📮 *Рассылка запущена!*\n\n"
        f"Отправлено: 0/{total}",
        parse_mode='Markdown'
    )
    
    for user in users:
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
            if sent % 10 == 0:
                try:
                    await query.edit_message_text(
                        f"📮 *Рассылка в процессе...*\n\n"
                        f"✅ Отправлено: {sent}/{total}\n"
                        f"❌ Ошибок: {errors}",
                        parse_mode='Markdown'
                    )
                except:
                    pass
            
            # Задержка для избежания лимитов Telegram
            await asyncio.sleep(0.1)
            
        except Exception as e:
            errors += 1
            logger.error(f"Error sending to {user['telegram_id']}: {e}")
    
    # Финальное сообщение
    await query.edit_message_text(
        f"✅ *Рассылка завершена!*\n\n"
        f"📊 Статистика:\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Ошибок: {errors}\n"
        f"👥 Всего пользователей: {total}",
        parse_mode='Markdown'
    )
    
    # Очистка данных
    context.user_data.clear()
    
    return ConversationHandler.END


async def cancel_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена рассылки"""
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
        SUPPORT_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_support_message)],
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
        PAYMENT_CONFIRM: [
            CallbackQueryHandler(confirm_payment, pattern="^confirm_payment$"),
            CallbackQueryHandler(cancel_payment, pattern="^cancel_payment$"),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=True,
    per_chat=True,
    per_user=True,
)

# Рассылка
mailing_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_mailing, pattern="^admin_mailing$")],
    states={
        MAILING_MESSAGE: [
            MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO & ~filters.COMMAND, receive_mailing_message)
        ],
        MAILING_CONFIRM: [
            CallbackQueryHandler(confirm_mailing, pattern="^confirm_mailing$"),
            CallbackQueryHandler(cancel_mailing, pattern="^cancel_mailing$"),
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
    application.add_handler(mailing_conv)
    
    # Callback обработчики
    application.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_subscription$"))
    application.add_handler(CallbackQueryHandler(my_status_callback, pattern="^my_status$"))
    application.add_handler(CallbackQueryHandler(view_tariffs_callback, pattern="^view_tariffs$"))
    application.add_handler(CallbackQueryHandler(back_to_menu_callback, pattern="^back_to_menu$"))
    
    # Админ callbacks
    application.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(admin_backup, pattern="^admin_backup$"))
    application.add_handler(CallbackQueryHandler(back_to_admin_callback, pattern="^back_to_admin$"))
    
    logger.info("🚀 Manager Bot started!")
    logger.info(f"📋 Subscriptions available: {len(SUBSCRIPTIONS)}")
    logger.info(f"👤 Admin ID: {ADMIN_ID}")
    
    # Запуск polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()