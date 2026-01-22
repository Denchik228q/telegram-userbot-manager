import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, ConversationHandler, ContextTypes, filters
)
from database import db
from userbot import manager
from config_userbot import (
    MANAGER_BOT_TOKEN, ADMIN_ID, SUBSCRIPTIONS, 
    REQUIRED_CHANNELS, PRIVATE_CHANNEL_LINK, PAYMENT_DETAILS
)
from admin_commands import (
    admin_panel, admin_stats, admin_users, admin_subscriptions,
    admin_broadcast_menu, admin_support, admin_logs, admin_back,
    activate_subscription, broadcast_message, reply_support
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
PHONE, CODE, PASSWORD_2FA = range(3)
MAILING_TARGETS, MAILING_MESSAGES, MAILING_CONFIRM = range(3, 6)
SUPPORT_MESSAGE = 6
PAYMENT_PROOF = 7


async def check_subscription_channels(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Проверка подписки на каналы"""
    not_subscribed = []
    
    for channel in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                not_subscribed.append(channel)
        except Exception as e:
            logger.error(f"Error checking subscription: {e}")
            not_subscribed.append(channel)
    
    return not_subscribed


# ========================================
# АДМИН КОМАНДЫ
# ========================================

async def admin_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создание бэкапа базы данных (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    await update.message.reply_text("⏳ Создаю бэкап базы данных...")
    
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = f'backups/manual_backup_{timestamp}.db'
    
    success = await db.backup_database(backup_file)
    
    if success:
        # Получаем статистику
        cursor = await db.db.execute('SELECT COUNT(*) FROM users')
        users_count = (await cursor.fetchone())[0]
        
        cursor = await db.db.execute('SELECT COUNT(*) FROM mailings')
        mailings_count = (await cursor.fetchone())[0]
        
        await update.message.reply_text(
            f"✅ Бэкап создан успешно!\n\n"
            f"📁 Файл: {backup_file}\n"
            f"👥 Пользователей: {users_count}\n"
            f"📮 Рассылок: {mailings_count}\n\n"
            f"Бэкап сохранён локально на сервере."
        )
    else:
        await update.message.reply_text("❌ Ошибка создания бэкапа")


# ========================================
# ОСНОВНЫЕ ФУНКЦИИ БОТА
# ========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start с проверкой подписки"""
    # ... остальной код


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start с проверкой подписки"""
    user = update.effective_user
    
    # Сначала регистрируем пользователя
    await db.register_user(user.id, user.username or user.first_name)
    
    # Проверка подписки на публичные каналы
    not_subscribed = await check_subscription_channels(user.id, context)
    
    if not_subscribed:
        keyboard = []
        for channel in not_subscribed:
            keyboard.append([InlineKeyboardButton(f"Подписаться на {channel}", url=f"https://t.me/{channel.replace('@', '')}")])
        
        keyboard.append([InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription")])
        
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            f"Для использования бота необходимо подписаться на каналы:\n"
            f"{''.join([f'• {ch}' + chr(10) for ch in not_subscribed])}\n"
            f"После подписки нажмите кнопку ниже:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Проверка подписки на приватный канал
    approved, requested = await db.check_private_channel_status(user.id)
    
    logger.info(f"User {user.id} private channel status: approved={approved}, requested={requested}")
    
    if not approved:
        if requested:
            # Уже запросил, ждёт одобрения
            await update.message.reply_text(
                "⏳ Ваш запрос на доступ к приватному каналу\n"
                "находится на рассмотрении.\n\n"
                "Вы получите уведомление после проверки администратором.\n\n"
                "Обычно это занимает до 24 часов."
            )
            return
        else:
            # Первый раз - показываем кнопку подписки
            keyboard = [
                [InlineKeyboardButton("📱 Подписаться на приватный канал", url=PRIVATE_CHANNEL_LINK)],
                [InlineKeyboardButton("✅ Я подписался (ожидание проверки)", callback_data="request_approval")]
            ]
            
            await update.message.reply_text(
                f"👋 Привет, {user.first_name}!\n\n"
                f"Последний шаг - подпишитесь на приватный канал.\n"
                f"После подписки нажмите кнопку ниже.\n\n"
                f"Админ проверит подписку и одобрит доступ.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
    
    # Всё ОК - показываем главное меню
    sub_type, limits = await db.check_subscription(user.id)
    
    keyboard = [
        [InlineKeyboardButton("📱 Подключить аккаунт", callback_data="connect_account")],
        [InlineKeyboardButton("📮 Создать рассылку", callback_data="create_mailing")],
        [InlineKeyboardButton("💳 Подписки", callback_data="subscriptions")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("💬 Поддержка", callback_data="support")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    
    text = (
        f"🤖 Telegram Userbot Manager\n\n"
        f"👋 Привет, {user.first_name}!\n\n"
        f"📋 Ваша подписка: {limits['name']}\n"
        f"📊 Лимит: {limits['daily_limit']} сообщений/день\n"
        f"📝 Макс. сообщений: {limits['max_messages']}\n"
        f"👥 Макс. получателей: {limits['max_targets']}\n\n"
        f"⚠️ ВНИМАНИЕ! Использование на свой риск!\n"
        f"• Возможен бан аккаунта\n"
        f"• Не спамьте незнакомым людям\n"
        f"• Соблюдайте лимиты Telegram\n\n"
        f"Выберите действие:"
    )
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка подписки на публичные каналы"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    not_subscribed = await check_subscription_channels(user.id, context)
    
    if not_subscribed:
        await query.answer("❌ Вы ещё не подписались на все каналы!", show_alert=True)
        return
    
    # Проверка приватного канала
    cursor = await db.db.execute(
        'SELECT private_channel_approved FROM users WHERE user_id = ?',
        (user.id,)
    )
    result = await cursor.fetchone()
    
    if not result or not result[0]:
        keyboard = [
            [InlineKeyboardButton("📱 Подписаться на приватный канал", url=PRIVATE_CHANNEL_LINK)],
            [InlineKeyboardButton("✅ Я подписался (ожидание проверки)", callback_data="request_approval")]
        ]
        
        await query.edit_message_text(
            f"✅ Подписка на публичные каналы подтверждена!\n\n"
            f"Теперь подпишитесь на приватный канал.\n"
            f"После подписки нажмите кнопку ниже.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await query.message.reply_text("✅ Проверка пройдена! Используйте /start")


async def request_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрос одобрения приватного канала"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    # Проверяем статус
    approved, requested = await db.check_private_channel_status(user.id)
    
    if approved:
        await query.edit_message_text("✅ Вы уже одобрены! Используйте /start")
        return
    
    if requested:
        await query.answer("⏳ Запрос уже отправлен!", show_alert=True)
        return
    
    # Сохраняем запрос через функцию БД
    success = await db.request_private_channel(user.id)
    
    if not success:
        await query.answer("❌ Ошибка запроса", show_alert=True)
        return
    
    # Уведомление админу
    keyboard = [
        [InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_private_{user.id}")],
        [InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_private_{user.id}")]
    ]
    
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"📱 Новый запрос на доступ к приватному каналу\n\n"
            f"👤 User ID: {user.id}\n"
            f"📝 Username: @{user.username or 'нет'}\n"
            f"👤 Имя: {user.first_name}\n\n"
            f"Проверьте подписку и одобрите доступ:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")
    
    await query.edit_message_text(
        "⏳ Запрос отправлен администратору!\n\n"
        "Вы получите уведомление после проверки.\n"
        "Обычно это занимает до 24 часов."
    )


async def approve_private_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Одобрение доступа к приватному каналу"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Нет доступа", show_alert=True)
        return
    
    user_id = int(query.data.split("_")[2])
    
    logger.info(f"Admin approving private channel for user {user_id}")
    
    # Используем функцию из database.py
    success = await db.approve_private_channel(user_id)
    
    if success:
        # Уведомление пользователю
        try:
            await context.bot.send_message(
                user_id,
                "✅ Доступ к приватному каналу одобрен!\n\n"
                "Теперь вы можете использовать бота.\n\n"
                "Отправьте /start для начала работы! 🎉"
            )
            logger.info(f"User {user_id} notified about approval")
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")
        
        await query.edit_message_text(
            f"{query.message.text}\n\n"
            f"✅ ОДОБРЕНО ✅\n"
            f"Пользователь уведомлён!"
        )
    else:
        await query.answer("❌ Ошибка одобрения", show_alert=True)


async def reject_private_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отклонение доступа"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    user_id = int(query.data.split("_")[2])
    
    try:
        await context.bot.send_message(
            user_id,
            "❌ Доступ к приватному каналу отклонён.\n\n"
            "Возможные причины:\n"
            "• Не подписались на канал\n"
            "• Нарушение правил\n\n"
            "Свяжитесь с поддержкой: /support"
        )
    except:
        pass
    
    await query.edit_message_text(
        f"{query.message.text}\n\n"
        f"❌ ОТКЛОНЕНО"
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "connect_account":
        await connect_account_start(update, context)
    elif query.data == "create_mailing":
        await create_mailing_start(update, context)
    elif query.data == "subscriptions":
        await show_subscriptions(update, context)
    elif query.data == "stats":
        await show_stats(update, context)
    elif query.data == "support":
        await support_start(update, context)
    elif query.data == "help":
        await show_help(update, context)
    elif query.data.startswith("sub_"):
        await show_subscription_details(update, context)


async def connect_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало подключения аккаунта"""
    query = update.callback_query
    
    text = (
        "📱 Подключение аккаунта\n\n"
        "Введите номер телефона в международном формате:\n"
        "Например: +79123456789\n\n"
        "Отправьте /cancel для отмены"
    )
    
    await query.edit_message_text(text)
    return PHONE


async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение номера телефона"""
    phone = update.message.text.strip()
    user_id = update.effective_user.id
    
    if not phone.startswith('+'):
        await update.message.reply_text("❌ Номер должен начинаться с +\nПопробуйте снова:")
        return PHONE
    
    await update.message.reply_text("⏳ Отправляю код...")
    
    session = await manager.create_session(user_id, phone)
    success, result = await session.send_code_request()
    
    if success:
        context.user_data['phone'] = phone
        context.user_data['phone_code_hash'] = result
        
        await db.update_user_phone(user_id, phone)
        
        await update.message.reply_text(
            "✅ Код отправлен!\n\n"
            "Введите код из Telegram:\n"
            "(Например: 12345)\n\n"
            "/cancel - отмена"
        )
        return CODE
    else:
        await update.message.reply_text(f"❌ Ошибка: {result}\n\nПопробуйте /start")
        return ConversationHandler.END


async def receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение кода подтверждения"""
    code = update.message.text.strip()
    user_id = update.effective_user.id
    
    phone = context.user_data.get('phone')
    phone_code_hash = context.user_data.get('phone_code_hash')
    
    session = manager.get_session(user_id)
    
    if not session:
        await update.message.reply_text("❌ Сессия не найдена. Начните с /start")
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ Проверяю код...")
    
    success, result = await session.sign_in(code, phone_code_hash)
    
    if success:
        await update.message.reply_text(
            "✅ Аккаунт успешно подключён!\n\n"
            "Теперь вы можете создать рассылку.\n\n"
            "/start - главное меню"
        )
        return ConversationHandler.END
    elif result == "2FA":
        await update.message.reply_text(
            "🔐 Требуется пароль двухфакторной аутентификации.\n\n"
            "Введите пароль:\n\n"
            "/cancel - отмена"
        )
        return PASSWORD_2FA
    else:
        await update.message.reply_text(f"❌ Ошибка: {result}\n\nПопробуйте /start")
        return ConversationHandler.END


async def receive_2fa_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение пароля 2FA"""
    password = update.message.text.strip()
    user_id = update.effective_user.id
    
    session = manager.get_session(user_id)
    
    if not session:
        await update.message.reply_text("❌ Сессия не найдена. Начните с /start")
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ Проверяю пароль...")
    
    success, result = await session.sign_in_2fa(password)
    
    if success:
        await update.message.reply_text(
            "✅ Аккаунт успешно подключён!\n\n"
            "/start - главное меню"
        )
    else:
        await update.message.reply_text(f"❌ Ошибка: {result}\n\n/start")
    
    return ConversationHandler.END


async def create_mailing_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания рассылки"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    session = manager.get_session(user_id)
    if not session or not session.is_active:
        await query.edit_message_text(
            "❌ Сначала подключите аккаунт!\n\n/start"
        )
        return ConversationHandler.END
    
    # ОЧИЩАЕМ СТАРЫЕ ДАННЫЕ! 👇
    context.user_data['messages'] = []
    context.user_data['targets'] = []
    
    sub_type, limits = await db.check_subscription(user_id)
    
    text = (
        f"📮 Создание рассылки\n\n"
        f"📊 Ваши лимиты:\n"
        f"• Сообщений в день: {limits['daily_limit']}\n"
        f"• Макс. сообщений: {limits['max_messages']}\n"
        f"• Макс. получателей: {limits['max_targets']}\n\n"
        f"Отправьте список получателей (по одному в строке):\n"
        f"@username1\n"
        f"@username2\n"
        f"@username3\n\n"
        f"/cancel - отмена"
    )
    
    await query.edit_message_text(text)
    return MAILING_TARGETS


async def receive_targets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение списка получателей"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    targets = [line.strip() for line in text.split('\n') if line.strip()]
    
    if not targets:
        await update.message.reply_text("❌ Список пустой. Попробуйте снова:")
        return MAILING_TARGETS
    
    sub_type, limits = await db.check_subscription(user_id)
    
    if len(targets) > limits['max_targets']:
        await update.message.reply_text(
            f"❌ Слишком много получателей!\n"
            f"Ваш лимит: {limits['max_targets']}\n"
            f"Указано: {len(targets)}\n\n"
            f"Попробуйте снова:"
        )
        return MAILING_TARGETS
    
    context.user_data['targets'] = targets
    context.user_data['messages'] = []  # 👈 Очищаем сообщения
    
    await update.message.reply_text(
        f"✅ Получателей: {len(targets)}\n\n"
        f"📝 Теперь отправьте ПЕРВОЕ сообщение для рассылки.\n\n"
        f"Макс: {limits['max_messages']} сообщений\n\n"
        f"/cancel - отмена"
    )
    return MAILING_MESSAGES


async def receive_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение сообщений для рассылки"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Получаем уже собранные сообщения или создаём новый список
    messages = context.user_data.get('messages', [])
    
    # Добавляем новое сообщение
    messages.append(text)
    context.user_data['messages'] = messages
    
    sub_type, limits = await db.check_subscription(user_id)
    
    # Проверка лимита
    if len(messages) >= limits['max_messages']:
        # Достигнут лимит - переходим к подтверждению
        targets = context.user_data.get('targets', [])
        total = len(targets) * len(messages)
        
        keyboard = [
            [InlineKeyboardButton("✅ Начать рассылку", callback_data="confirm_mailing")],
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel_mailing")]
        ]
        
        msg_list = "\n\n".join([f"{i+1}. {msg[:100]}..." if len(msg) > 100 else f"{i+1}. {msg}" 
                                for i, msg in enumerate(messages)])
        
        await update.message.reply_text(
            f"⚠️ Достигнут лимит сообщений ({limits['max_messages']})!\n\n"
            f"📝 Ваши сообщения:\n\n{msg_list}\n\n"
            f"📊 Параметры рассылки:\n"
            f"👥 Получателей: {len(targets)}\n"
            f"💬 Сообщений: {len(messages)}\n"
            f"📮 Всего отправок: {total}\n\n"
            f"⚠️ Задержка между сообщениями: 60-180 сек\n\n"
            f"Начать рассылку?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MAILING_CONFIRM
    
    # Показываем что добавлено и спрашиваем про ещё
    keyboard = [
        [InlineKeyboardButton("✅ Да, добавить ещё", callback_data="add_more_messages")],
        [InlineKeyboardButton("🚀 Нет, начать рассылку", callback_data="finish_messages")]
    ]
    
    msg_list = "\n\n".join([f"{i+1}. {msg[:100]}..." if len(msg) > 100 else f"{i+1}. {msg}" 
                            for i, msg in enumerate(messages)])
    
    await update.message.reply_text(
        f"✅ Сообщение {len(messages)} добавлено!\n\n"
        f"📝 Текущие сообщения:\n\n{msg_list}\n\n"
        f"💬 Добавлено: {len(messages)} / {limits['max_messages']}\n\n"
        f"Добавить ещё одно сообщение?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return MAILING_MESSAGES

async def add_more_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить ещё сообщение"""
    query = update.callback_query
    await query.answer()
    
    messages = context.user_data.get('messages', [])
    user_id = query.from_user.id
    sub_type, limits = await db.check_subscription(user_id)
    
    await query.edit_message_text(
        f"📝 Отправьте следующее сообщение для рассылки\n\n"
        f"Добавлено: {len(messages)} / {limits['max_messages']}\n\n"
        f"/cancel - отмена"
    )
    
    return MAILING_MESSAGES


async def finish_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закончить добавление сообщений и перейти к подтверждению"""
    query = update.callback_query
    await query.answer()
    
    messages = context.user_data.get('messages', [])
    targets = context.user_data.get('targets', [])
    
    if not messages:
        await query.edit_message_text("❌ Нет сообщений для рассылки!\n\n/start")
        return ConversationHandler.END
    
    total = len(targets) * len(messages)
    
    keyboard = [
        [InlineKeyboardButton("✅ Начать рассылку", callback_data="confirm_mailing")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel_mailing")]
    ]
    
    msg_list = "\n\n".join([f"{i+1}. {msg[:100]}..." if len(msg) > 100 else f"{i+1}. {msg}" 
                            for i, msg in enumerate(messages)])
    
    await query.edit_message_text(
        f"📊 Параметры рассылки:\n\n"
        f"📝 Сообщения:\n{msg_list}\n\n"
        f"👥 Получателей: {len(targets)}\n"
        f"💬 Сообщений: {len(messages)}\n"
        f"📮 Всего отправок: {total}\n\n"
        f"⚠️ Задержка между сообщениями: 60-180 сек\n\n"
        f"Начать рассылку?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return MAILING_CONFIRM


async def confirm_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение и запуск рассылки"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if query.data == "cancel_mailing":
        await query.edit_message_text("❌ Рассылка отменена.\n\n/start")
        return ConversationHandler.END
    
    targets = context.user_data.get('targets', [])
    messages = context.user_data.get('messages', [])
    
    session = manager.get_session(user_id)
    if not session:
                await query.edit_message_text("❌ Сессия не найдена.\n\n/start")
                return ConversationHandler.END
    
    mailing_id = await db.add_mailing(user_id, len(targets), len(messages))
    
    await query.edit_message_text(
        f"🚀 Рассылка запущена!\n\n"
        f"📊 ID: {mailing_id}\n"
        f"👥 Получателей: {len(targets)}\n"
        f"💬 Сообщений: {len(messages)}\n\n"
        f"⏳ Это займёт время...\n\n"
        f"/cancel_mailing - остановить"
    )
    
    asyncio.create_task(run_mailing(user_id, session, targets, messages, mailing_id, query.message))
    
    return ConversationHandler.END


async def run_mailing(user_id, session, targets, messages, mailing_id, message):
    """Запуск рассылки в фоне"""
    try:
        results = await session.mass_send(targets, messages)
        
        await db.update_mailing(mailing_id, results['sent'], results['failed'])
        
        error_text = ""
        if results['errors']:
            error_text = "\n\n❌ Ошибки:\n" + "\n".join([
                f"• {e['target']}: {e['error']}" for e in results['errors'][:5]
            ])
        
        await message.reply_text(
            f"✅ Рассылка завершена!\n\n"
            f"📊 Статистика:\n"
            f"• Отправлено: {results['sent']}\n"
            f"• Ошибок: {results['failed']}\n"
            f"• ID: {mailing_id}"
            f"{error_text}\n\n"
            f"/start"
        )
    except Exception as e:
        logger.error(f"Mailing error: {e}")
        await message.reply_text(f"❌ Ошибка рассылки: {e}\n\n/start")


async def show_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать тарифы"""
    query = update.callback_query
    
    text = "💳 Доступные подписки:\n\n"
    keyboard = []
    
    for key, sub in SUBSCRIPTIONS.items():
        if key == 'trial':
            continue
        
        text += f"{sub['name']}\n"
        text += f"💰 {sub['price']} руб/мес\n"
        text += f"📊 {sub['daily_limit']} сообщений/день\n"
        text += f"📝 {sub['max_messages']} сообщений за раз\n"
        text += f"👥 {sub['max_targets']} получателей\n\n"
        
        keyboard.append([InlineKeyboardButton(f"Купить {sub['name']}", callback_data=f"sub_{key}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_subscription_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детали подписки с кнопкой оплаты"""
    query = update.callback_query
    await query.answer()
    
    sub_key = query.data.replace("sub_", "")
    sub = SUBSCRIPTIONS.get(sub_key)
    
    if not sub:
        return
    
    text = (
        f"{sub['name']}\n\n"
        f"💰 Цена: {sub['price']} руб\n"
        f"⏱ Срок: {sub['duration_days']} дней\n"
        f"📊 Лимит: {sub['daily_limit']} сообщений/день\n"
        f"📝 Макс. сообщений: {sub['max_messages']}\n"
        f"👥 Макс. получателей: {sub['max_targets']}\n\n"
        f"{sub['description']}\n\n"
        f"{PAYMENT_DETAILS}\n\n"
        f"⚠️ После оплаты нажмите кнопку ниже!"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Я оплатил", callback_data=f"paid_{sub_key}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="subscriptions")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def payment_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение оплаты"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    sub_key = query.data.replace("paid_", "")
    sub = SUBSCRIPTIONS.get(sub_key)
    
    if not sub:
        return
    
    # Сохраняем запрос на оплату
    context.user_data['pending_subscription'] = sub_key
    
    await query.edit_message_text(
        f"📸 Отправьте скриншот или чек оплаты\n\n"
        f"Подписка: {sub['name']}\n"
        f"Сумма: {sub['price']} руб\n\n"
        f"После отправки чека, администратор проверит оплату\n"
        f"и активирует подписку.\n\n"
        f"/cancel - отмена"
    )
    
    return PAYMENT_PROOF


async def receive_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение чека оплаты"""
    user = update.effective_user
    sub_key = context.user_data.get('pending_subscription')
    
    if not sub_key:
        await update.message.reply_text("❌ Ошибка. Начните с /start")
        return ConversationHandler.END
    
    sub = SUBSCRIPTIONS.get(sub_key)
    
    # Получаем фото
    if update.message.photo:
        photo = update.message.photo[-1]
        file_id = photo.file_id
    elif update.message.document:
        file_id = update.message.document.file_id
    else:
        await update.message.reply_text("❌ Отправьте фото или документ с чеком")
        return PAYMENT_PROOF
    
    # Уведомление админу с кнопкой активации
    keyboard = [
        [InlineKeyboardButton("✅ Активировать подписку", callback_data=f"activate_payment_{user.id}_{sub_key}")],
        [InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_payment_{user.id}")]
    ]
    
    try:
        if update.message.photo:
            await context.bot.send_photo(
                ADMIN_ID,
                photo=file_id,
                caption=(
                    f"💳 Новый платёж!\n\n"
                    f"👤 User ID: {user.id}\n"
                    f"📝 Username: @{user.username or 'нет'}\n"
                    f"👤 Имя: {user.first_name}\n\n"
                    f"📦 Подписка: {sub['name']}\n"
                    f"💰 Сумма: {sub['price']} руб\n\n"
                    f"Для активации используйте:\n"
                    f"/activate {user.id} {sub_key}"
                ),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await context.bot.send_document(
                ADMIN_ID,
                document=file_id,
                caption=(
                    f"💳 Новый платёж!\n\n"
                    f"👤 User ID: {user.id}\n"
                    f"📝 Username: @{user.username or 'нет'}\n"
                    f"👤 Имя: {user.first_name}\n\n"
                    f"📦 Подписка: {sub['name']}\n"
                    f"💰 Сумма: {sub['price']} руб\n\n"
                    f"Для активации используйте:\n"
                    f"/activate {user.id} {sub_key}"
                ),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")
    
    await update.message.reply_text(
        "✅ Чек отправлен администратору!\n\n"
        "⏳ Ожидайте проверки и активации подписки.\n"
        "Обычно это занимает до 24 часов.\n\n"
        "Вы получите уведомление после активации.\n\n"
        "/start"
    )
    
    return ConversationHandler.END


async def activate_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Активация подписки по кнопке"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    parts = query.data.split("_")
    user_id = int(parts[2])
    sub_key = parts[3]
    
    success = await db.activate_subscription(user_id, sub_key)
    
    if success:
        sub = SUBSCRIPTIONS[sub_key]
        
        # Уведомление пользователю
        try:
            await context.bot.send_message(
                user_id,
                f"🎉 Подписка активирована!\n\n"
                f"Тариф: {sub['name']}\n"
                f"Срок: {sub['duration_days']} дней\n"
                f"Лимит: {sub['daily_limit']} сообщений/день\n\n"
                f"Спасибо за покупку! 💚\n\n"
                f"/start"
            )
        except:
            pass
        
        await query.edit_message_caption(
            caption=f"{query.message.caption}\n\n✅ АКТИВИРОВАНО"
        )
    else:
        await query.answer("❌ Ошибка активации", show_alert=True)


async def reject_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отклонение платежа"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    user_id = int(query.data.split("_")[2])
    
    try:
        await context.bot.send_message(
            user_id,
            "❌ Ваш платёж отклонён.\n\n"
            "Возможные причины:\n"
            "• Неверная сумма\n"
            "• Некорректный чек\n"
            "• Дубликат платежа\n\n"
            "Свяжитесь с поддержкой: /support"
        )
    except:
        pass
    
    await query.edit_message_caption(
        caption=f"{query.message.caption}\n\n❌ ОТКЛОНЕНО"
    )


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    sub_type, limits = await db.check_subscription(user_id)
    stats = await db.get_user_stats(user_id)
    
    mailings_count, sent_total, failed_total = stats
    
    text = (
        f"📊 Ваша статистика\n\n"
        f"📋 Подписка: {limits['name']}\n"
        f"📮 Рассылок: {mailings_count}\n"
        f"✅ Отправлено: {sent_total or 0}\n"
        f"❌ Ошибок: {failed_total or 0}\n\n"
        f"📊 Лимиты:\n"
        f"• {limits['daily_limit']} сообщений/день\n"
        f"• {limits['max_messages']} сообщений за раз\n"
        f"• {limits['max_targets']} получателей"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало обращения в поддержку"""
    query = update.callback_query
    
    await query.edit_message_text(
        "💬 Поддержка\n\n"
        "Опишите вашу проблему или вопрос.\n\n"
        "/cancel - отмена"
    )
    return SUPPORT_MESSAGE


async def receive_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение сообщения в поддержку"""
    user_id = update.effective_user.id
    message = update.message.text
    
    await db.add_support_message(user_id, message)
    
    await update.message.reply_text(
        "✅ Сообщение отправлено в поддержку!\n\n"
        "Мы ответим в ближайшее время.\n\n"
        "/start"
    )
    
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"💬 Новое сообщение в поддержку\n\n"
            f"👤 От: {user_id}\n"
            f"📝 Сообщение:\n{message}"
        )
    except:
        pass
    
    return ConversationHandler.END


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь"""
    query = update.callback_query
    
    text = (
        "❓ Помощь\n\n"
        "📱 Подключение аккаунта:\n"
        "1. Нажмите 'Подключить аккаунт'\n"
        "2. Введите номер телефона\n"
        "3. Введите код из Telegram\n"
        "4. При необходимости введите пароль 2FA\n\n"
        "📮 Создание рассылки:\n"
        "1. Нажмите 'Создать рассылку'\n"
        "2. Отправьте список @username\n"
        "3. Отправьте текст сообщений\n"
        "4. Подтвердите запуск\n\n"
        "⚠️ Важно:\n"
        "• Соблюдайте лимиты\n"
        "• Не спамьте\n"
        "💬 Поддержка: /support"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена"""
    await update.message.reply_text("❌ Отменено.\n\n/start")
    return ConversationHandler.END


async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в меню"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    sub_type, limits = await db.check_subscription(user.id)
    
    keyboard = [
        [InlineKeyboardButton("📱 Подключить аккаунт", callback_data="connect_account")],
        [InlineKeyboardButton("📮 Создать рассылку", callback_data="create_mailing")],
        [InlineKeyboardButton("💳 Подписки", callback_data="subscriptions")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("💬 Поддержка", callback_data="support")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    
    text = (
        f"🤖 Telegram Userbot Manager\n\n"
        f"👋 {user.first_name}\n\n"
        f"📋 Подписка: {limits['name']}\n"
        f"📊 Лимит: {limits['daily_limit']} сообщений/день\n\n"
        f"Выберите действие:"
    )
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Произошла ошибка. Попробуйте /start"
        )


async def init_and_run():
    """Инициализация и запуск"""
    
    # ========================================
    # АВТОМАТИЧЕСКИЙ БЭКАП ПРИ ЗАПУСКЕ
    # ========================================
    
    import os
    from datetime import datetime
    import shutil
    
    db_file = 'bot.db'
    
    if os.path.exists(db_file):
        # Создаём папку для бэкапов
        backup_dir = 'backups'
        os.makedirs(backup_dir, exist_ok=True)
        
        # Бэкап с датой
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f"{backup_dir}/auto_backup_{timestamp}.db"
        
        try:
            shutil.copy2(db_file, backup_file)
            logger.info(f"✅ Auto backup created: {backup_file}")
            
            # Удаляем старые бэкапы (оставляем последние 10)
            backups = sorted([f for f in os.listdir(backup_dir) if f.startswith('auto_backup_')])
            if len(backups) > 10:
                for old_backup in backups[:-10]:
                    os.remove(os.path.join(backup_dir, old_backup))
                    logger.info(f"🗑 Removed old backup: {old_backup}")
        
        except Exception as e:
            logger.error(f"❌ Auto backup failed: {e}")
    
    # ========================================
    
    await db.connect()
    
    # Добавляем недостающие колонки в базу
    try:
        await db.db.execute('ALTER TABLE users ADD COLUMN private_channel_approved BOOLEAN DEFAULT 0')
        await db.db.execute('ALTER TABLE users ADD COLUMN private_channel_requested BOOLEAN DEFAULT 0')
        await db.db.commit()
    except:
        pass
    
    app = Application.builder().token(MANAGER_BOT_TOKEN).build()
    
    # ConversationHandler для подключения аккаунта
    connect_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(connect_account_start, pattern="^connect_account$")],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_code)],
            PASSWORD_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_2fa_password)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )
    
    # ConversationHandler для рассылки
    mailing_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_mailing_start, pattern="^create_mailing$")],
        states={
            MAILING_TARGETS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_targets)],
            MAILING_MESSAGES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_messages),
                CallbackQueryHandler(add_more_messages, pattern="^add_more_messages$"),
                CallbackQueryHandler(finish_messages, pattern="^finish_messages$")
            ],
            MAILING_CONFIRM: [CallbackQueryHandler(confirm_mailing, pattern="^(confirm|cancel)_mailing$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )   
    
    # ConversationHandler для поддержки
    support_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(support_start, pattern="^support$")],
        states={
            SUPPORT_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_support_message)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )
    
    # ConversationHandler для оплаты
    payment_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(payment_confirmation, pattern="^paid_")],
        states={
            PAYMENT_PROOF: [MessageHandler((filters.PHOTO | filters.Document.IMAGE) & ~filters.COMMAND, receive_payment_proof)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )
    
    # Админ команды
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("activate", activate_subscription))
    app.add_handler(CommandHandler("broadcast", broadcast_message))
    app.add_handler(CommandHandler("reply", reply_support))
    app.add_handler(CommandHandler("backup", admin_backup))
    
    # Админ callback handlers
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_users, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_subscriptions, pattern="^admin_subscriptions$"))
    app.add_handler(CallbackQueryHandler(admin_broadcast_menu, pattern="^admin_broadcast$"))
    app.add_handler(CallbackQueryHandler(admin_support, pattern="^admin_support$"))
    app.add_handler(CallbackQueryHandler(admin_logs, pattern="^admin_logs$"))
    app.add_handler(CallbackQueryHandler(admin_back, pattern="^admin_back$"))
    
    # Callback для одобрения приватного канала
    app.add_handler(CallbackQueryHandler(approve_private_channel, pattern="^approve_private_"))
    app.add_handler(CallbackQueryHandler(reject_private_channel, pattern="^reject_private_"))
    
    # Callback для оплаты
    app.add_handler(CallbackQueryHandler(activate_payment_callback, pattern="^activate_payment_"))
    app.add_handler(CallbackQueryHandler(reject_payment_callback, pattern="^reject_payment_"))
    
    # Проверка подписки
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_subscription$"))
    app.add_handler(CallbackQueryHandler(request_approval, pattern="^request_approval$"))
        # Регистрация handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(connect_conv)
    app.add_handler(mailing_conv)
    app.add_handler(support_conv)
    app.add_handler(payment_conv)
    app.add_handler(CallbackQueryHandler(show_subscriptions, pattern="^subscriptions$"))
    app.add_handler(CallbackQueryHandler(show_stats, pattern="^stats$"))
    app.add_handler(CallbackQueryHandler(show_help, pattern="^help$"))
    app.add_handler(CallbackQueryHandler(show_subscription_details, pattern="^sub_"))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
    app.add_error_handler(error_handler)
    
    logger.info(f"🚀 Manager Bot started!")
    logger.info(f"📋 Subscriptions available: {len(SUBSCRIPTIONS)}")
    logger.info(f"👤 Admin ID: {ADMIN_ID}")
    
    # Запуск бота
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    
    # Держим бота запущенным
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("🛑 Stopping bot...")
    finally:
        await app.stop()
        await app.shutdown()
        await db.close()


if __name__ == '__main__':
    asyncio.run(init_and_run())