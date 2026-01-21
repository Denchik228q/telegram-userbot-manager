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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
PHONE, CODE, PASSWORD_2FA = range(3)
MAILING_TARGETS, MAILING_MESSAGES, MAILING_CONFIRM = range(3, 6)
SUPPORT_MESSAGE = 6


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    
    await db.register_user(user.id, user.username or user.first_name)
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
    
    await update.message.reply_text(
        f"✅ Получателей: {len(targets)}\n\n"
        f"Теперь отправьте сообщения для рассылки (по одному в строке).\n"
        f"Макс: {limits['max_messages']} сообщений\n\n"
        f"/cancel - отмена"
    )
    return MAILING_MESSAGES


async def receive_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение сообщений для рассылки"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    messages = [line.strip() for line in text.split('\n') if line.strip()]
    
    if not messages:
        await update.message.reply_text("❌ Сообщения пустые. Попробуйте снова:")
        return MAILING_MESSAGES
    
    sub_type, limits = await db.check_subscription(user_id)
    
    if len(messages) > limits['max_messages']:
        await update.message.reply_text(
            f"❌ Слишком много сообщений!\n"
            f"Ваш лимит: {limits['max_messages']}\n"
            f"Указано: {len(messages)}\n\n"
            f"Попробуйте снова:"
        )
        return MAILING_MESSAGES
    
    context.user_data['messages'] = messages
    targets = context.user_data.get('targets', [])
    
    total = len(targets) * len(messages)
    
    keyboard = [
        [InlineKeyboardButton("✅ Начать рассылку", callback_data="confirm_mailing")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel_mailing")]
    ]
    
    await update.message.reply_text(
        f"📊 Параметры рассылки:\n\n"
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
        text += f"{sub['name']}\n"
        text += f"💰 {sub['price']} руб/мес\n"
        text += f"📊 {sub['daily_limit']} сообщений/день\n"
        text += f"📝 {sub['max_messages']} сообщений за раз\n"
        text += f"👥 {sub['max_targets']} получателей\n\n"
        
        keyboard.append([InlineKeyboardButton(sub['name'], callback_data=f"sub_{key}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_subscription_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детали подписки"""
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
        f"{PAYMENT_DETAILS}"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="subscriptions")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


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
    await db.connect()
    
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
            MAILING_MESSAGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_messages)],
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
    
    # Регистрация handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(connect_conv)
    app.add_handler(mailing_conv)
    app.add_handler(support_conv)
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