import asyncio
import logging
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
from config_userbot import *
from userbot import manager, UserbotSession
from database import Database

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database()

# Состояния диалога
PHONE_INPUT, CODE_INPUT, PASSWORD_2FA = range(3)
SELECT_TARGETS, MESSAGE_INPUT, ADDITIONAL_MESSAGES, CONFIRM_SEND = range(3, 7)
SUPPORT_MESSAGE = 7

# Временные данные
user_sessions = {}

# Активные рассылки
active_mailings = {}


def get_subscription_limits(subscription_type):
    """Получить лимиты подписки"""
    return SUBSCRIPTIONS.get(subscription_type, SUBSCRIPTIONS['free'])


async def check_subscription(user_id):
    """Проверить подписку пользователя"""
    sub_type = await db.get_subscription(user_id)
    return sub_type, get_subscription_limits(sub_type)


async def check_user_subscriptions(user_id, context):
    """Проверка подписки пользователя на обязательные каналы"""
    not_subscribed = []
    
    # Проверяем только публичный канал автоматически
    public_channel = "@starbombnews"
    
    try:
        member = await context.bot.get_chat_member(public_channel, user_id)
        if member.status in ['left', 'kicked']:
            not_subscribed.append(public_channel)
            logger.info(f"User {user_id} not subscribed to {public_channel}")
    except Exception as e:
        logger.error(f"Check subscription error: {e}")
        # Если ошибка - считаем что НЕ подписан
        not_subscribed.append(public_channel)
    
    return not_subscribed


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    await db.add_user(user.id, user.username, user.first_name, user.last_name)
    
    sub_type, limits = await check_subscription(user.id)
    
    keyboard = [
        [InlineKeyboardButton("📱 Подключить аккаунт", callback_data="connect_account")],
        [InlineKeyboardButton("📮 Создать рассылку", callback_data="create_mailing")],
        [InlineKeyboardButton("💳 Подписки", callback_data="subscriptions")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("💬 Поддержка", callback_data="support")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    
    await update.message.reply_text(
        f"🤖 Telegram Userbot Manager\n\n"
        f"👋 Привет, {user.first_name}!\n\n"
        f"📋 Ваша подписка: {limits['name']}\n"
        f"📊 Лимит: {limits['daily_limit']} сообщений/день\n"
        f"📝 Макс. сообщений: {limits['max_messages']}\n"
        f"👥 Макс. получателей: {limits['max_targets']}\n\n"
        f"⚠️ ВНИМАНИЕ! Использование на свой риск!\n"
        f"• Возможен бан аккаунта (70-90%)\n"
        f"• Не спамьте незнакомым людям\n"
        f"• Соблюдайте лимиты Telegram\n\n"
        f"Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def subscriptions_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню подписок"""
    query = update.callback_query
    if query:
        await query.answer()
        user_id = query.from_user.id
        message = query.message
    else:
        user_id = update.effective_user.id
        message = update.message
    
    current_sub = await db.get_subscription(user_id)
    trial_used = await db.check_free_trial_used(user_id)
    
    keyboard = []
    for sub_key, sub_data in SUBSCRIPTIONS.items():
        # Проверка пробной подписки
        if sub_key == 'free' and trial_used:
            status = "❌ Использована"
            callback = "trial_used"
        elif current_sub == sub_key:
            status = "✅ Активна"
            callback = f"sub_{sub_key}"
        else:
            status = f"💰 {sub_data['price']} ₽" if sub_data['price'] > 0 else "🆓 Активировать"
            callback = f"sub_{sub_key}"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{sub_data['name']} - {status}",
                callback_data=callback
            )
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
    
    text = "💳 Доступные подписки\n\n"
    
    for sub_key, sub_data in SUBSCRIPTIONS.items():
        price_text = "БЕСПЛАТНО" if sub_data['price'] == 0 else f"{sub_data['price']} ₽/мес"
        one_time = " (только 1 раз)" if sub_data.get('one_time_only') else ""
        
        text += (
            f"{sub_data['name']}{one_time}\n"
            f"💰 {price_text}\n"
            f"📊 Лимит: {sub_data['daily_limit']} сообщений/день\n"
            f"📝 Сообщений: {sub_data['max_messages']}\n"
            f"👥 Получателей: {sub_data['max_targets']}\n"
            f"⏱️ Срок: {sub_data['duration_days']} дней\n\n"
        )
    
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def subscription_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детали подписки"""
    query = update.callback_query
    
    if query.data == "trial_used":
        await query.answer(
            "❌ Вы уже использовали пробную подписку!",
            show_alert=True
        )
        return
    
    await query.answer()
    
    sub_key = query.data.replace("sub_", "")
    sub_data = SUBSCRIPTIONS.get(sub_key)
    
    if not sub_data:
        await query.edit_message_text("❌ Подписка не найдена")
        return
    
    keyboard = []
    
    if sub_data['price'] == 0:
        # Проверка использования пробной
        trial_used = await db.check_free_trial_used(query.from_user.id)
        if trial_used:
            keyboard.append([
                InlineKeyboardButton("❌ Уже использована", callback_data="trial_used")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("🆓 Активировать бесплатно", callback_data=f"activate_{sub_key}")
            ])
    else:
        keyboard.append([
            InlineKeyboardButton("💳 Оплатить", callback_data=f"pay_{sub_key}")
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="subscriptions")])
    
    one_time = "\n⚠️ Можно использовать только один раз!" if sub_data.get('one_time_only') else ""
    
    text = (
        f"{sub_data['name']}\n\n"
        f"💰 Цена: {sub_data['price']} ₽/мес\n"
        f"📊 Дневной лимит: {sub_data['daily_limit']} сообщений\n"
        f"📝 Сообщений в рассылке: {sub_data['max_messages']}\n"
        f"👥 Макс. получателей: {sub_data['max_targets']}\n"
        f"⏱️ Срок действия: {sub_data['duration_days']} дней"
        f"{one_time}"
    )
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def activate_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Активация бесплатной подписки"""
    query = update.callback_query
    await query.answer()
    
    sub_key = query.data.replace("activate_", "")
    sub_data = SUBSCRIPTIONS.get(sub_key)
    
    if sub_data['price'] > 0:
        await query.answer("❌ Эта подписка платная!", show_alert=True)
        return
    
    user_id = query.from_user.id
    
    # Проверка использования пробной подписки
    if sub_data.get('one_time_only', False):
        trial_used = await db.check_free_trial_used(user_id)
        if trial_used:
            await query.edit_message_text(
                "❌ Вы уже использовали пробную подписку!\n\n"
                "Пробная подписка доступна только один раз.\n\n"
                "Выберите платный тариф: /subscriptions"
            )
            return
    
    # Активация подписки
    await db.update_subscription(user_id, sub_key, sub_data['duration_days'])
    
    # Отметить что пробная использована
    if sub_data.get('one_time_only', False):
        await db.mark_free_trial_used(user_id)
    
    await query.edit_message_text(
        f"✅ Подписка активирована!\n\n"
        f"{sub_data['name']}\n"
        f"⏱️ Срок: {sub_data['duration_days']} дней\n"
        f"📊 Лимит: {sub_data['daily_limit']} сообщений/день\n"
        f"📝 Сообщений: {sub_data['max_messages']}\n"
        f"👥 Получателей: {sub_data['max_targets']}\n\n"
        f"Используйте: /start"
    )


async def payment_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация об оплате"""
    query = update.callback_query
    await query.answer()
    
    sub_key = query.data.replace("pay_", "")
    sub_data = SUBSCRIPTIONS.get(sub_key)
    user_id = query.from_user.id
    
    # Создаем ID платежа
    payment_id = await db.add_payment(user_id, sub_key, sub_data['price'])
    
    keyboard = [
        [InlineKeyboardButton("✅ Я оплатил", callback_data=f"paid_{payment_id}_{sub_key}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="subscriptions")]
    ]
    
    await query.edit_message_text(
        f"💳 Оплата подписки\n\n"
        f"{sub_data['name']}\n"
        f"💰 Сумма: {sub_data['price']} ₽\n\n"
        f"📝 Реквизиты для оплаты:\n"
        f"💳 Карта: 2200 1536 8370 4721\n"
        f"👤 Получатель: Денис Д.\n\n"
        f"Для предоставления более удобного способа оплаты обратитесь в поддержку\n\n"
        f"⚠️ Важно:\n"
        f"1️⃣ Переведите точную сумму\n"
        f"2️⃣ Нажмите 'Я оплатил'\n"
        f"3️⃣ Ожидайте подтверждения (до 30 мин)\n\n"
        f"🔢 ID платежа: {payment_id}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def payment_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение оплаты"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    payment_id = parts[1]
    sub_key = parts[2]
    
    user_id = query.from_user.id
    user = query.from_user
    sub_data = SUBSCRIPTIONS.get(sub_key)
    
    # ПРОВЕРКА ПОДПИСКИ НА ПУБЛИЧНЫЙ КАНАЛ
    not_subscribed = await check_user_subscriptions(user_id, context)
    
    if not_subscribed:
        keyboard = [
            [InlineKeyboardButton("📢 Подписаться на @starbombnews", url="https://t.me/starbombnews")],
            [InlineKeyboardButton("📢 Подписаться на приватный канал", url="https://t.me/+WpVwOyNErI8xZmNi")],
            [InlineKeyboardButton("✅ Я подписался", callback_data=f"paid_{payment_id}_{sub_key}")]
        ]
        
        await query.edit_message_text(
            "⚠️ Для оплаты подписки необходимо:\n\n"
            "1️⃣ Подписаться на наши каналы:\n"
            "• @starbombnews (публичный)\n"
            "• Приватный канал (по ссылке)\n\n"
            "2️⃣ Оплатить подписку\n\n"
            "После подписки нажмите 'Я подписался'\n"
            "Администратор проверит вручную подписку на приватный канал.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Отправка заявки админу
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"💳 Новая заявка на оплату!\n\n"
            f"👤 Пользователь: {user.first_name} (@{user.username or 'N/A'})\n"
            f"🆔 ID: {user_id}\n"
            f"📋 Подписка: {sub_data['name']}\n"
            f"💰 Сумма: {sub_data['price']} ₽\n"
            f"🔢 Payment ID: {payment_id}\n\n"
            f"✅ Подписан на @starbombnews: Да\n"
            f"⚠️ Проверь вручную подписку на приватный канал!\n\n"
            f"Для активации:\n"
            f"/activate {user_id} {sub_key}"
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")
    
    await query.edit_message_text(
        "✅ Заявка отправлена администратору!\n\n"
        "Платёж будет проверен и подписка активирована.\n"
        "Администратор также проверит вашу подписку на приватный канал.\n\n"
        "Обычно это занимает до 30 минут.\n\n"
        "Вы получите уведомление когда подписка будет активирована."
    )
    return
    
    # Отправка заявки админу
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"💳 Новая заявка на оплату!\n\n"
            f"👤 Пользователь: {user.first_name} (@{user.username or 'N/A'})\n"
            f"🆔 ID: {user_id}\n"
            f"📋 Подписка: {sub_data['name']}\n"
            f"💰 Сумма: {sub_data['price']} ₽\n"
            f"🔢 Payment ID: {payment_id}\n\n"
            f"✅ Подписан на все каналы: Да\n\n"
            f"Для активации:\n"
            f"/activate {user_id} {sub_key}"
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")
    
    await query.edit_message_text(
        "✅ Заявка отправлена администратору!\n\n"
        "Платёж будет проверен и подписка активирована.\n"
        "Обычно это занимает до 30 минут.\n\n"
        "Вы получите уведомление когда подписка будет активирована."
    )


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поддержка"""
    query = update.callback_query if update.callback_query else None
    
    if query:
        await query.answer()
        await query.edit_message_text(
            "💬 Поддержка\n\n"
            "Опишите вашу проблему или вопрос.\n"
            "Администратор ответит в ближайшее время.\n\n"
            "Или /cancel для отмены"
        )
    else:
        await update.message.reply_text(
            "💬 Поддержка\n\n"
            "Опишите вашу проблему или вопрос.\n\n"
            "Или /cancel для отмены"
        )
    
    return SUPPORT_MESSAGE


async def support_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получено сообщение в поддержку"""
    user = update.effective_user
    message_text = update.message.text
    
    ticket_id = await db.add_support_ticket(user.id, message_text)
    
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"💬 Новое обращение в поддержку!\n\n"
            f"👤 От: {user.first_name} (@{user.username or 'N/A'})\n"
            f"🆔 ID: {user.id}\n"
            f"🔢 Ticket: #{ticket_id}\n\n"
            f"📝 Сообщение:\n{message_text}\n\n"
            f"Ответить:\n/reply {user.id} текст"
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")
    
    await update.message.reply_text(
        "✅ Ваше обращение отправлено!\n\n"
        f"🔢 Ticket ID: #{ticket_id}\n\n"
        "Администратор ответит в ближайшее время."
    )
    
    return ConversationHandler.END



async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика пользователя"""
    query = update.callback_query if update.callback_query else None
    user_id = update.effective_user.id
    
    if query:
        await query.answer()
    
    sub_type, limits = await check_subscription(user_id)
    stats = await db.get_stats(user_id)
    session = manager.get_session(user_id)
    
    session_status = "✅ Активна" if session and session.is_active else "❌ Нет активной сессии"
    session_phone = session.phone if session else "Нет"
    messages_today = session.messages_sent_today if session else 0
    
    text = (
        f"📊 Ваша статистика\n\n"
        f"📋 Подписка: {limits['name']}\n"
        f"📊 Лимит: {limits['daily_limit']}/день\n"
        f"📝 Сообщений: до {limits['max_messages']}\n"
        f"👥 Получателей: до {limits['max_targets']}\n\n"
        f"📱 Сессия: {session_status}\n"
        f"📞 Номер: {session_phone}\n"
        f"💬 Отправлено сегодня: {messages_today}/{limits['daily_limit']}\n\n"
        f"📈 Всего рассылок: {stats['total_mailings']}\n"
        f"✅ Отправлено: {stats['total_sent']}\n"
        f"❌ Ошибок: {stats['total_failed']}"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
    
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь"""
    query = update.callback_query if update.callback_query else None
    
    if query:
        await query.answer()
    
    text = (
        "❓ ПОМОЩЬ\n\n"
        "📱 ПОДКЛЮЧЕНИЕ АККАУНТА:\n"
        "1. Нажмите 'Подключить аккаунт'\n"
        "2. Введите номер телефона (+7...)\n"
        "3. Введите код из Telegram\n"
        "4. Если есть 2FA - введите пароль\n\n"
        "📮 СОЗДАНИЕ РАССЫЛКИ:\n"
        "1. Нажмите 'Создать рассылку'\n"
        "2. Введите @username или username получателей (по одному в строке)\n"
        "3. Введите текст сообщения\n"
        "4. Можете добавить до N сообщений\n"
        "5. Подтвердите отправку\n\n"
        "⏱️ ЗАДЕРЖКИ:\n"
        "Между сообщениями задержка 20-60 секунд для безопасности.\n\n"
        "⚠️ ВАЖНО:\n"
        "• Не спамьте незнакомым\n"
        "• Не превышайте лимиты\n"
        "• Используйте на свой риск\n\n"
        "💬 Поддержка: /support\n"
        "📊 Статистика: /stats"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
    
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def connect_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало подключения аккаунта"""
    query = update.callback_query if update.callback_query else None
    user_id = update.effective_user.id
    
    if query:
        await query.answer()
    
    session = manager.get_session(user_id)
    if session and session.is_active:
        text = (
            f"📱 Аккаунт уже подключен!\n\n"
            f"📞 Номер: {session.phone}\n\n"
            f"Отключить: /disconnect"
        )
        if query:
            await query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return ConversationHandler.END
    
    text = (
        "📱 Подключение аккаунта\n\n"
        "Введите номер телефона в международном формате:\n"
        "Например: +79123456789\n\n"
        "Или /cancel для отмены"
    )
    
    if query:
        await query.edit_message_text(text)
    else:
        await update.message.reply_text(text)
    
    return PHONE_INPUT


async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен номер телефона"""
    phone = update.message.text.strip()
    user_id = update.effective_user.id
    
    if not phone.startswith('+'):
        await update.message.reply_text(
            "❌ Неверный формат!\n\n"
            "Номер должен начинаться с +\n"
            "Например: +79123456789"
        )
        return PHONE_INPUT
    
    await update.message.reply_text("⏳ Отправляю код...")
    
    try:
        session = await manager.create_session(user_id, phone)
        success, result = await session.send_code_request()
        
        if not success:
            await update.message.reply_text(
                f"❌ Ошибка отправки кода:\n{result}\n\n"
                f"Попробуйте снова: /connect"
            )
            return ConversationHandler.END
        
        user_sessions[user_id] = {
            'phone': phone,
            'phone_hash': result,
            'session': session
        }
        
        await update.message.reply_text(
            "✅ Код отправлен в Telegram!\n\n"
            "Введите код (например: 12345):\n\n"
            "Или /cancel для отмены"
        )
        
        return CODE_INPUT
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Ошибка: {e}\n\n"
            f"Попробуйте снова: /connect"
        )
        return ConversationHandler.END


async def code_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен код подтверждения"""
    code = update.message.text.strip()
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("❌ Сессия истекла. Начните заново: /connect")
        return ConversationHandler.END
    
    session_data = user_sessions[user_id]
    session = session_data['session']
    phone_hash = session_data['phone_hash']
    
    await update.message.reply_text("⏳ Проверяю код...")
    
    try:
        success, result = await session.sign_in(code, phone_hash)
        
        if not success:
            if "2FA" in result or "пароль" in result.lower():
                await update.message.reply_text(
                    "🔐 Требуется двухфакторная аутентификация\n\n"
                    "Введите пароль 2FA:\n\n"
                    "Или /cancel для отмены"
                )
                return PASSWORD_2FA
            else:
                await update.message.reply_text(
                    f"❌ Ошибка входа:\n{result}\n\n"
                    f"Попробуйте снова: /connect"
                )
                if user_id in user_sessions:
                    del user_sessions[user_id]
                return ConversationHandler.END
        
        await update.message.reply_text(
            f"✅ Аккаунт подключен!\n\n"
            f"📞 Номер: {session_data['phone']}\n\n"
            f"Теперь можете создавать рассылки: /new_mailing"
        )
        
        if user_id in user_sessions:
            del user_sessions[user_id]
        
        return ConversationHandler.END
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Ошибка: {e}\n\n"
            f"Попробуйте снова: /connect"
        )
        if user_id in user_sessions:
            del user_sessions[user_id]
        return ConversationHandler.END


async def password_2fa_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен пароль 2FA"""
    password = update.message.text.strip()
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await update.message.reply_text("❌ Сессия истекла. Начните заново: /connect")
        return ConversationHandler.END
    
    session_data = user_sessions[user_id]
    session = session_data['session']
    
    await update.message.reply_text("⏳ Проверяю пароль...")
    
    try:
        success, result = await session.sign_in_2fa(password)
        
        if not success:
            await update.message.reply_text(
                f"❌ Ошибка 2FA:\n{result}\n\n"
                f"Попробуйте снова: /connect"
            )
            if user_id in user_sessions:
                del user_sessions[user_id]
            return ConversationHandler.END
        
        await update.message.reply_text(
            f"✅ Аккаунт подключен!\n\n"
            f"📞 Номер: {session_data['phone']}\n\n"
            f"Теперь можете создавать рассылки: /new_mailing"
        )
        
        if user_id in user_sessions:
            del user_sessions[user_id]
        
        return ConversationHandler.END
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Ошибка: {e}\n\n"
            f"Попробуйте снова: /connect"
        )
        if user_id in user_sessions:
            del user_sessions[user_id]
        return ConversationHandler.END


async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отключение аккаунта"""
    user_id = update.effective_user.id
    
    session = manager.get_session(user_id)
    if not session:
        await update.message.reply_text("❌ Нет подключенного аккаунта")
        return
    
    await manager.remove_session(user_id)
    
    await update.message.reply_text(
        "✅ Аккаунт отключен!\n\n"
        "Подключить снова: /connect"
    )


async def new_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создание новой рассылки"""
    query = update.callback_query if update.callback_query else None
    user_id = update.effective_user.id
    
    if query:
        await query.answer()
    
    session = manager.get_session(user_id)
    if not session or not session.is_active:
        text = (
            "❌ Нет активной сессии!\n\n"
            "Сначала подключите аккаунт: /connect"
        )
        if query:
            await query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return ConversationHandler.END
    
    sub_type, limits = await check_subscription(user_id)
    
    text = (
        f"📮 Создание рассылки\n\n"
        f"📋 Ваши лимиты:\n"
        f"👥 Получателей: {limits['max_targets']}\n"
        f"📝 Сообщений: {limits['max_messages']}\n"
        f"💬 Осталось сегодня: {limits['daily_limit'] - session.messages_sent_today}\n\n"
        f"Введите @username или username получателей (по одному в строке):\n\n"
        f"Пример:\n"
        f"@user1\n"
        f"user2\n"
        f"@user3\n\n"
        f"Или /cancel для отмены"
    )
    
    if query:
        await query.edit_message_text(text)
    else:
        await update.message.reply_text(text)
    
    user_sessions[user_id] = {
        'targets': [],
        'messages': [],
        'limits': limits
    }
    
    return SELECT_TARGETS


async def targets_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получены получатели"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if user_id not in user_sessions:
        await update.message.reply_text("❌ Сессия истекла. Начните заново: /new_mailing")
        return ConversationHandler.END
    
    targets = [line.strip().replace('@', '') for line in text.split('\n') if line.strip()]
    
    limits = user_sessions[user_id]['limits']
    
    if len(targets) > limits['max_targets']:
        await update.message.reply_text(
            f"❌ Слишком много получателей!\n\n"
            f"Ваш лимит: {limits['max_targets']}\n"
            f"Вы указали: {len(targets)}\n\n"
            f"Попробуйте снова или измените подписку: /subscriptions"
        )
        return SELECT_TARGETS
    
    user_sessions[user_id]['targets'] = targets
    
    await update.message.reply_text(
        f"✅ Получатели сохранены: {len(targets)}\n\n"
        f"Теперь введите текст первого сообщения:\n\n"
        f"Или /cancel для отмены"
    )
    
    return MESSAGE_INPUT


async def message_received_userbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получено сообщение для рассылки"""
    user_id = update.effective_user.id
    message_text = update.message.text
    
    if user_id not in user_sessions:
        await update.message.reply_text("❌ Сессия истекла. Начните заново: /new_mailing")
        return ConversationHandler.END
    
    user_sessions[user_id]['messages'].append(message_text)
    
    limits = user_sessions[user_id]['limits']
    current_count = len(user_sessions[user_id]['messages'])
    
    if current_count >= limits['max_messages']:
        keyboard = [
            [InlineKeyboardButton("✅ Начать рассылку", callback_data="start_mailing_now")],
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel_userbot_send")]
        ]
        
        await update.message.reply_text(
            f"📝 Сообщений добавлено: {current_count}/{limits['max_messages']}\n\n"
            f"Достигнут лимит сообщений.\n\n"
            f"Начать рассылку?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CONFIRM_SEND
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить ещё", callback_data="add_more_messages")],
        [InlineKeyboardButton("✅ Начать рассылку", callback_data="start_mailing_now")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel_userbot_send")]
    ]
    
    await update.message.reply_text(
        f"✅ Сообщение #{current_count} добавлено\n\n"
        f"Можете добавить ещё ({limits['max_messages'] - current_count} осталось)\n"
        f"или начать рассылку:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return ADDITIONAL_MESSAGES


async def add_more_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить ещё сообщение"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if user_id not in user_sessions:
        await query.edit_message_text("❌ Сессия истекла. Начните заново: /new_mailing")
        return ConversationHandler.END
    
    limits = user_sessions[user_id]['limits']
    current_count = len(user_sessions[user_id]['messages'])
    
    await query.edit_message_text(
        f"📝 Введите следующее сообщение:\n\n"
        f"Сообщений: {current_count}/{limits['max_messages']}\n\n"
        f"Или /cancel для отмены"
    )
    
    return MESSAGE_INPUT


async def run_mailing_background(user_id, session, targets, messages, context):
    """Выполнение рассылки в фоне"""
    try:
        active_mailings[user_id] = {
            'status': 'running',
            'sent': 0,
            'total': len(targets)
        }
        
        results = await session.mass_send(
            targets,
            messages,
            MIN_DELAY_BETWEEN_MESSAGES,
            MAX_DELAY_BETWEEN_MESSAGES
        )
        
        await db.add_mailing(user_id, messages, targets)
        
        if user_id in active_mailings and active_mailings[user_id]['status'] == 'cancelled':
            await context.bot.send_message(
                user_id,
                "🛑 Рассылка отменена!\n\n"
                f"📤 Отправлено: {results['sent']}\n"
                f"❌ Ошибок: {results['failed']}"
            )
        else:
            error_text = ""
            if results['errors']:
                error_text = "\n\n❌ Ошибки:\n"
                for err in results['errors'][:5]:
                    error_text += f"• {err['target']}: {err['error']}\n"
                if len(results['errors']) > 5:
                    error_text += f"... и ещё {len(results['errors']) - 5}"
            
            sub_type, limits = await check_subscription(user_id)
            
            await context.bot.send_message(
                user_id,
                f"✅ Рассылка завершена!\n\n"
                f"📤 Отправлено: {results['sent']}\n"
                f"❌ Ошибок: {results['failed']}\n"
                f"📊 Всего получателей: {len(targets)}\n"
                f"📝 Сообщений каждому: {len(messages)}\n"
                f"💬 Осталось сегодня: {limits['daily_limit'] - session.messages_sent_today}"
                f"{error_text}"
            )
        
        if user_id in active_mailings:
            del active_mailings[user_id]
            
    except Exception as e:
        logger.error(f"Background mailing error: {e}")
        await context.bot.send_message(
            user_id,
            f"❌ Ошибка рассылки: {e}"
        )
        if user_id in active_mailings:
            del active_mailings[user_id]


async def start_mailing_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск рассылки"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if user_id not in user_sessions:
        await query.edit_message_text("❌ Сессия истекла")
        return ConversationHandler.END
    
    session = manager.get_session(user_id)
    if not session or not session.is_active:
        await query.edit_message_text("❌ Нет активной сессии!")
        return ConversationHandler.END
    
    data = user_sessions[user_id]
    targets = data['targets']
    messages = data['messages']
    
    # Запуск в фоне
    task = asyncio.create_task(
        run_mailing_background(user_id, session, targets, messages, context)
    )
    
    await query.edit_message_text(
        f"🚀 Рассылка запущена в фоне!\n\n"
        f"👥 Получателей: {len(targets)}\n"
        f"📝 Сообщений: {len(messages)}\n\n"
        f"Вы получите уведомление когда рассылка завершится.\n"
        f"Бот остается доступным для других операций!\n\n"
        f"🛑 Остановить: /stop_mailing"
    )
    
    if user_id in user_sessions:
        del user_sessions[user_id]
    
    return ConversationHandler.END


async def stop_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Остановка активной рассылки"""
    user_id = update.effective_user.id
    
    if user_id not in active_mailings:
        await update.message.reply_text(
            "❌ У вас нет активных рассылок"
        )
        return
    
    session = manager.get_session(user_id)
    if session:
        session.cancel_mailing()
    
    active_mailings[user_id]['status'] = 'cancelled'
    
    await update.message.reply_text(
        "🛑 Рассылка останавливается...\n\n"
        "Подождите завершения текущей отправки.\n"
        "Вы получите уведомление с результатами."
    )


async def cancel_userbot_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена создания рассылки"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if user_id in user_sessions:
        del user_sessions[user_id]
    
    await query.edit_message_text("❌ Рассылка отменена")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена диалога"""
    user_id = update.effective_user.id
    
    if user_id in user_sessions:
        del user_sessions[user_id]
    
    await update.message.reply_text(
        "❌ Операция отменена\n\n"
        "Главное меню: /start"
    )
    return ConversationHandler.END


async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    sub_type, limits = await check_subscription(user.id)
    
    keyboard = [
        [InlineKeyboardButton("📱 Подключить аккаунт", callback_data="connect_account")],
        [InlineKeyboardButton("📮 Создать рассылку", callback_data="create_mailing")],
        [InlineKeyboardButton("💳 Подписки", callback_data="subscriptions")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("💬 Поддержка", callback_data="support")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    
    await query.edit_message_text(
        f"🤖 Telegram Userbot Manager\n\n"
        f"👋 Привет, {user.first_name}!\n\n"
        f"📋 Ваша подписка: {limits['name']}\n"
        f"📊 Лимит: {limits['daily_limit']} сообщений/день\n"
        f"📝 Макс. сообщений: {limits['max_messages']}\n"
        f"👥 Макс. получателей: {limits['max_targets']}\n\n"
        f"⚠️ ВНИМАНИЕ! Использование на свой риск!\n"
        f"• Не спамьте незнакомым людям\n"
        f"• Соблюдайте лимиты Telegram\n\n"
        f"Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# АДМИНСКИЕ КОМАНДЫ

async def admin_activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Активация подписки админом"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещен")
        return
    
    try:
        user_id = int(context.args[0])
        sub_key = context.args[1]
        
        sub_data = SUBSCRIPTIONS.get(sub_key)
        if not sub_data:
            await update.message.reply_text("❌ Неверный тип подписки")
            return
        
        await db.update_subscription(user_id, sub_key, sub_data['duration_days'])
        
        # Уведомление пользователю
        try:
            await context.bot.send_message(
                user_id,
                f"✅ Подписка активирована!\n\n"
                f"{sub_data['name']}\n"
                f"⏱️ Срок: {sub_data['duration_days']} дней\n"
                f"📊 Лимит: {sub_data['daily_limit']} сообщений/день\n"
                f"📝 Сообщений: {sub_data['max_messages']}\n"
                f"👥 Получателей: {sub_data['max_targets']}\n\n"
                f"Используйте: /start"
            )
        except:
            pass
        
        await update.message.reply_text(
            f"✅ Подписка активирована!\n\n"
            f"User ID: {user_id}\n"
            f"Подписка: {sub_data['name']}"
        )
        
    except (IndexError, ValueError):
        await update.message.reply_text(
            "❌ Неверный формат\n\n"
            "Использование:\n"
            "/activate USER_ID SUB_TYPE\n\n"
            "Например:\n"
            "/activate 123456789 pro"
        )


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика для админа"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещен")
        return
    
    try:
        # Получаем все сессии
        all_sessions = manager.get_all_sessions()
        active_count = len([s for s in all_sessions if s.is_active])
        
        # Получаем статистику из БД
        async with db.db.execute(
            'SELECT COUNT(*) FROM users WHERE is_active = 1'
        ) as cursor:
            total_users = (await cursor.fetchone())[0]
        
        async with db.db.execute(
            'SELECT COUNT(*) FROM mailings'
        ) as cursor:
            total_mailings = (await cursor.fetchone())[0]
        
        async with db.db.execute(
            'SELECT COALESCE(SUM(sent_count), 0) FROM mailings'
        ) as cursor:
            total_sent = (await cursor.fetchone())[0]
        
        async with db.db.execute('''
            SELECT subscription_type, COUNT(*) 
            FROM users 
            GROUP BY subscription_type
        ''') as cursor:
            subs = await cursor.fetchall()
        
        subs_text = "\n".join([f"• {sub[0]}: {sub[1]}" for sub in subs])
        
        text = (
            f"📊 СТАТИСТИКА БОТА\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"📱 Активных сессий: {active_count}\n"
            f"📮 Всего рассылок: {total_mailings}\n"
            f"📤 Отправлено сообщений: {total_sent}\n\n"
            f"💳 Подписки:\n{subs_text}\n\n"
            f"🔄 Активных рассылок: {len(active_mailings)}"
        )
        
        await update.message.reply_text(text)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ пользователю от админа"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещен")
        return
    
    try:
        user_id = int(context.args[0])
        message = ' '.join(context.args[1:])
        
        await context.bot.send_message(
            user_id,
            f"💬 Ответ от администратора:\n\n{message}"
        )
        
        await update.message.reply_text("✅ Сообщение отправлено")
        
    except (IndexError, ValueError):
        await update.message.reply_text(
            "❌ Неверный формат\n\n"
            "Использование:\n"
            "/reply USER_ID текст сообщения"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Рассылка всем пользователям"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещен")
        return
    
    try:
        message = ' '.join(context.args)
        
        if not message:
            await update.message.reply_text(
                "❌ Введите текст сообщения\n\n"
                "Использование:\n"
                "/broadcast текст сообщения"
            )
            return
        
        async with db.db.execute('SELECT user_id FROM users WHERE is_active = 1') as cursor:
            users = await cursor.fetchall()
        
        sent = 0
        failed = 0
        
        for user in users:
            try:
                await context.bot.send_message(user[0], f"📢 Объявление:\n\n{message}")
                sent += 1
                await asyncio.sleep(0.05)
            except:
                failed += 1
        
        await update.message.reply_text(
            f"✅ Рассылка завершена!\n\n"
            f"✅ Отправлено: {sent}\n"
            f"❌ Ошибок: {failed}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


# CALLBACK HANDLERS

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
    query = update.callback_query
    
    handlers = {
        "connect_account": connect_account,
        "create_mailing": new_mailing,
        "subscriptions": subscriptions_menu,
        "stats": stats_command,
        "support": support,
        "help": help_command,
        "back_to_menu": back_to_menu,
        "cancel_userbot_send": cancel_userbot_send,
        "add_more_messages": add_more_messages,
        "start_mailing_now": start_mailing_now,
    }
    
    # Обработка подписок
    if query.data.startswith("sub_"):
        await subscription_details(update, context)
        return
    
    if query.data.startswith("activate_"):
        await activate_subscription(update, context)
        return
    
    if query.data.startswith("pay_"):
        await payment_info(update, context)
        return
    
    if query.data.startswith("paid_"):
        await payment_confirmation(update, context)
        return
    
    # Остальные обработчики
    handler = handlers.get(query.data)
    if handler:
        await handler(update, context)
    else:
        await query.answer("❌ Неизвестная команда")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Update {update} caused error {context.error}")
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка. Попробуйте позже или обратитесь в поддержку."
            )
    except:
        pass


def main():
    """Запуск бота"""
    application = Application.builder().token(MANAGER_BOT_TOKEN).build()
    
    # ConversationHandler для подключения аккаунта
    connect_conv = ConversationHandler(
        entry_points=[
            CommandHandler('connect', connect_account),
            CallbackQueryHandler(connect_account, pattern="^connect_account$")
        ],
        states={
            PHONE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_received)],
            CODE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, code_received)],
            PASSWORD_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, password_2fa_received)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # ConversationHandler для создания рассылки
    mailing_conv = ConversationHandler(
        entry_points=[
            CommandHandler('new_mailing', new_mailing),
            CallbackQueryHandler(new_mailing, pattern="^create_mailing$")
        ],
        states={
            SELECT_TARGETS: [MessageHandler(filters.TEXT & ~filters.COMMAND, targets_received)],
            MESSAGE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_received_userbot)],
            ADDITIONAL_MESSAGES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, message_received_userbot),
                CallbackQueryHandler(add_more_messages, pattern="^add_more_messages$"),
                CallbackQueryHandler(start_mailing_now, pattern="^start_mailing_now$"),
                CallbackQueryHandler(cancel_userbot_send, pattern="^cancel_userbot_send$")
            ],
            CONFIRM_SEND: [
                CallbackQueryHandler(start_mailing_now, pattern="^start_mailing_now$"),
                CallbackQueryHandler(cancel_userbot_send, pattern="^cancel_userbot_send$")
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # ConversationHandler для поддержки
    support_conv = ConversationHandler(
        entry_points=[
            CommandHandler('support', support),
            CallbackQueryHandler(support, pattern="^support$")
        ],
        states={
            SUPPORT_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_message_received)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Регистрация обработчиков
    application.add_handler(connect_conv)
    application.add_handler(mailing_conv)
    application.add_handler(support_conv)
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("disconnect", disconnect))
    application.add_handler(CommandHandler("stop_mailing", stop_mailing))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("subscriptions", subscriptions_menu))
    
    # Админские команды
    application.add_handler(CommandHandler("activate", admin_activate))
    application.add_handler(CommandHandler("adminstats", admin_stats))
    application.add_handler(CommandHandler("reply", admin_reply))
    application.add_handler(CommandHandler("broadcast", admin_broadcast))
    
    # Callback кнопки
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запуск бота
    logger.info("🚀 Manager Bot started!")
    logger.info(f"📋 Subscriptions available: {len(SUBSCRIPTIONS)}")
    logger.info(f"👤 Admin ID: {ADMIN_ID}")
    
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
        


if __name__ == '__main__':
    asyncio.run(db.connect())
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        asyncio.run(db.close())
        asyncio.run(manager.stop_all())    