import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from userbot import manager
from config_userbot import ADMIN_ID, SUBSCRIPTIONS

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """Проверка админа"""
    return user_id == ADMIN_ID


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ панель"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ У вас нет доступа к админ-панели")
        return
    
    # Статистика
    cursor = await db.db.execute('SELECT COUNT(*) FROM users')
    total_users = (await cursor.fetchone())[0]
    
    cursor = await db.db.execute('SELECT COUNT(*) FROM users WHERE is_active = 1')
    active_users = (await cursor.fetchone())[0]
    
    cursor = await db.db.execute('SELECT COUNT(*) FROM mailings WHERE date(started_at) = date("now")')
    mailings_today = (await cursor.fetchone())[0]
    
    cursor = await db.db.execute('SELECT COUNT(*) FROM support_messages WHERE is_answered = 0')
    support_pending = (await cursor.fetchone())[0]
    
    active_sessions = len(manager.get_all_sessions())
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("💳 Управление подписками", callback_data="admin_subscriptions")],
        [InlineKeyboardButton("📮 Рассылка всем", callback_data="admin_broadcast")],
        [InlineKeyboardButton("💬 Поддержка", callback_data="admin_support")],
        [InlineKeyboardButton("📋 Логи", callback_data="admin_logs")]
    ]
    
    text = (
        f"🔧 Админ-панель\n\n"
        f"📊 Статистика:\n"
        f"👥 Пользователей: {total_users}\n"
        f"✅ Активных: {active_users}\n"
        f"📱 Подключенных сессий: {active_sessions}\n"
        f"📮 Рассылок сегодня: {mailings_today}\n"
        f"💬 Обращений в поддержку: {support_pending}\n\n"
        f"Выберите действие:"
    )
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детальная статистика"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    # Общая статистика
    cursor = await db.db.execute('SELECT COUNT(*) FROM users')
    total_users = (await cursor.fetchone())[0]
    
    cursor = await db.db.execute('SELECT COUNT(*) FROM mailings')
    total_mailings = (await cursor.fetchone())[0]
    
    cursor = await db.db.execute('SELECT SUM(sent_count), SUM(failed_count) FROM mailings')
    result = await cursor.fetchone()
    total_sent = result[0] or 0
    total_failed = result[1] or 0
    
    # За сегодня
    cursor = await db.db.execute(
        'SELECT COUNT(*), SUM(sent_count) FROM mailings WHERE date(started_at) = date("now")'
    )
    result = await cursor.fetchone()
    mailings_today = result[0] or 0
    sent_today = result[1] or 0
    
    # За неделю
    cursor = await db.db.execute(
        'SELECT COUNT(*), SUM(sent_count) FROM mailings WHERE started_at >= date("now", "-7 days")'
    )
    result = await cursor.fetchone()
    mailings_week = result[0] or 0
    sent_week = result[1] or 0
    
    # По подпискам
    sub_stats = ""
    for sub_key, sub_data in SUBSCRIPTIONS.items():
        cursor = await db.db.execute(
            'SELECT COUNT(*) FROM users WHERE subscription_type = ?', (sub_key,)
        )
        count = (await cursor.fetchone())[0]
        sub_stats += f"• {sub_data['name']}: {count}\n"
    
    text = (
        f"📊 Детальная статистика\n\n"
        f"👥 Пользователи:\n"
        f"• Всего: {total_users}\n\n"
        f"📮 Рассылки:\n"
        f"• Всего: {total_mailings}\n"
        f"• Сегодня: {mailings_today}\n"
        f"• За неделю: {mailings_week}\n\n"
        f"📨 Отправлено сообщений:\n"
        f"• Всего: {total_sent}\n"
        f"• Сегодня: {sent_today}\n"
        f"• За неделю: {sent_week}\n"
        f"• Ошибок всего: {total_failed}\n\n"
        f"💳 По подпискам:\n{sub_stats}"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список пользователей"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    cursor = await db.db.execute(
        'SELECT user_id, username, phone, subscription_type, registered_at FROM users ORDER BY registered_at DESC LIMIT 20'
    )
    users = await cursor.fetchall()
    
    text = "👥 Последние 20 пользователей:\n\n"
    
    for user in users:
        user_id, username, phone, sub_type, registered = user
        sub_name = SUBSCRIPTIONS.get(sub_type, {}).get('name', 'Нет')
        
        text += f"ID: {user_id}\n"
        text += f"Username: @{username or 'нет'}\n"
        text += f"Телефон: {phone or 'не указан'}\n"
        text += f"Подписка: {sub_name}\n"
        text += f"Регистрация: {registered[:10]}\n\n"
    
    text += "Для активации подписки:\n/activate <user_id> <sub_type>"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление подписками"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    text = (
        "💳 Управление подписками\n\n"
        "Команды:\n\n"
        "/activate <user_id> <sub_type>\n"
        "Активировать подписку\n\n"
        "Пример:\n"
        "/activate 123456789 pro\n\n"
        "Доступные типы:\n"
        "• trial - Пробная\n"
        "• basic - Базовая\n"
        "• pro - Продвинутая\n"
        "• premium - Премиум\n\n"
        "/ban <user_id>\n"
        "Забанить пользователя\n\n"
        "/unban <user_id>\n"
        "Разбанить пользователя"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню рассылки"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    text = (
        "📮 Рассылка всем пользователям\n\n"
        "Для рассылки используйте команду:\n\n"
        "/broadcast <текст сообщения>\n\n"
        "Пример:\n"
        "/broadcast Привет! Обновление бота!\n\n"
        "⚠️ Сообщение получат ВСЕ пользователи!"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обращения в поддержку"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    cursor = await db.db.execute(
        'SELECT id, user_id, message, created_at, is_answered FROM support_messages ORDER BY created_at DESC LIMIT 10'
    )
    messages = await cursor.fetchall()
    
    if not messages:
        text = "💬 Обращений в поддержку нет"
    else:
        text = "💬 Последние 10 обращений:\n\n"
        
        for msg in messages:
            msg_id, user_id, message, created_at, is_answered = msg
            status = "✅ Отвечено" if is_answered else "⏳ Ожидает"
            
            text += f"ID: {msg_id}\n"
            text += f"От: {user_id}\n"
            text += f"Дата: {created_at[:16]}\n"
            text += f"Статус: {status}\n"
            text += f"Сообщение: {message[:100]}\n\n"
    
    text += "\nДля ответа:\n/reply <user_id> <текст>"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Логи системы"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    # Последние ошибки из рассылок
    cursor = await db.db.execute(
        'SELECT user_id, status, finished_at FROM mailings WHERE status != "completed" ORDER BY finished_at DESC LIMIT 5'
    )
    failed_mailings = await cursor.fetchall()
    
    text = "📋 Логи системы\n\n"
    
    if failed_mailings:
        text += "❌ Проблемные рассылки:\n\n"
        for mailing in failed_mailings:
            user_id, status, finished = mailing
            text += f"User: {user_id}\n"
            text += f"Статус: {status}\n"
            text += f"Дата: {finished or 'В процессе'}\n\n"
    else:
        text += "✅ Ошибок не обнаружено"
    
    # Активные сессии
    sessions = manager.get_all_sessions()
    text += f"\n📱 Активных сессий: {len(sessions)}\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def activate_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Активация подписки"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    try:
        target_user_id = int(context.args[0])
        sub_type = context.args[1]
        
        if sub_type not in SUBSCRIPTIONS:
            await update.message.reply_text("❌ Неверный тип подписки")
            return
        
        success = await db.activate_subscription(target_user_id, sub_type)
        
        if success:
            await update.message.reply_text(
                f"✅ Подписка активирована!\n\n"
                f"User ID: {target_user_id}\n"
                f"Подписка: {SUBSCRIPTIONS[sub_type]['name']}"
            )
            
            # Уведомление пользователю
            try:
                await context.bot.send_message(
                    target_user_id,
                    f"🎉 Ваша подписка активирована!\n\n"
                    f"Тариф: {SUBSCRIPTIONS[sub_type]['name']}\n"
                    f"Срок: {SUBSCRIPTIONS[sub_type]['duration_days']} дней\n\n"
                    f"/start"
                )
            except:
                pass
        else:
            await update.message.reply_text("❌ Ошибка активации")
    
    except (IndexError, ValueError):
        await update.message.reply_text(
            "❌ Неверный формат\n\n"
            "Используйте:\n/activate <user_id> <sub_type>"
        )


async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Рассылка всем"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Укажите текст сообщения")
        return
    
    message_text = ' '.join(context.args)
    
    await update.message.reply_text("⏳ Начинаю рассылку...")
    
    cursor = await db.db.execute('SELECT user_id FROM users WHERE is_active = 1')
    users = await cursor.fetchall()
    
    sent = 0
    failed = 0
    
    for user in users:
        try:
            await context.bot.send_message(user[0], message_text)
            sent += 1
        except:
            failed += 1
    
    await update.message.reply_text(
        f"✅ Рассылка завершена!\n\n"
        f"Отправлено: {sent}\n"
        f"Ошибок: {failed}"
    )


async def reply_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ на обращение"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    try:
        target_user_id = int(context.args[0])
        reply_text = ' '.join(context.args[1:])
        
        await context.bot.send_message(
            target_user_id,
            f"💬 Ответ от поддержки:\n\n{reply_text}"
        )
        
        await update.message.reply_text(f"✅ Ответ отправлен пользователю {target_user_id}")
    
    except (IndexError, ValueError):
        await update.message.reply_text(
            "❌ Неверный формат\n\n"
            "Используйте:\n/reply <user_id> <текст>"
        )


async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Назад в админ панель"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    # Копируем код из admin_panel
    cursor = await db.db.execute('SELECT COUNT(*) FROM users')
    total_users = (await cursor.fetchone())[0]
    
    cursor = await db.db.execute('SELECT COUNT(*) FROM users WHERE is_active = 1')
    active_users = (await cursor.fetchone())[0]
    
    cursor = await db.db.execute('SELECT COUNT(*) FROM mailings WHERE date(started_at) = date("now")')
    mailings_today = (await cursor.fetchone())[0]
    
    cursor = await db.db.execute('SELECT COUNT(*) FROM support_messages WHERE is_answered = 0')
    support_pending = (await cursor.fetchone())[0]
    
    active_sessions = len(manager.get_all_sessions())
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("💳 Управление подписками", callback_data="admin_subscriptions")],
        [InlineKeyboardButton("📮 Рассылка всем", callback_data="admin_broadcast")],
        [InlineKeyboardButton("💬 Поддержка", callback_data="admin_support")],
        [InlineKeyboardButton("📋 Логи", callback_data="admin_logs")]
    ]
    
    text = (
        f"🔧 Админ-панель\n\n"
        f"📊 Статистика:\n"
        f"👥 Пользователей: {total_users}\n"
        f"✅ Активных: {active_users}\n"
        f"📱 Подключенных сессий: {active_sessions}\n"
        f"📮 Рассылок сегодня: {mailings_today}\n"
        f"💬 Обращений в поддержку: {support_pending}\n\n"
        f"Выберите действие:"
    )
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))