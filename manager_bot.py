import asyncio
import logging
import json
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


def get_subscription_limits(subscription_type):
    """Получить лимиты подписки"""
    return SUBSCRIPTIONS.get(subscription_type, SUBSCRIPTIONS['free'])


async def check_subscription(user_id):
    """Проверить подписку пользователя"""
    sub_type = await db.get_subscription(user_id)
    return sub_type, get_subscription_limits(sub_type)


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
    
    keyboard = []
    for sub_key, sub_data in SUBSCRIPTIONS.items():
        status = "✅ Активна" if current_sub == sub_key else f"💰 {sub_data['price']} ₽"
        keyboard.append([
            InlineKeyboardButton(
                f"{sub_data['name']} - {status}",
                callback_data=f"sub_{sub_key}"
            )
        ])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
    
    text = "💳 Подписки\n\nВыберите подходящий тариф:\n\n"
    
    for sub_key, sub_data in SUBSCRIPTIONS.items():
        text += (
            f"{sub_data['name']}\n"
            f"💰 Цена: {sub_data['price']} ₽/мес\n"
            f"📊 Лимит: {sub_data['daily_limit']} сообщений/день\n"
            f"📝 Сообщений в рассылке: {sub_data['max_messages']}\n"
            f"👥 Получателей: {sub_data['max_targets']}\n\n"
        )
    
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def subscription_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детали подписки"""
    query = update.callback_query
    await query.answer()
    
    sub_key = query.data.replace("sub_", "")
    sub_data = SUBSCRIPTIONS.get(sub_key)
    
    if not sub_data:
        return
    
    user_id = query.from_user.id
    current_sub = await db.get_subscription(user_id)
    
    if current_sub == sub_key:
        await query.answer("✅ Эта подписка уже активна!", show_alert=True)
        return
    
    keyboard = []
    
    if sub_data['price'] > 0:
        keyboard.append([
            InlineKeyboardButton("💳 Оплатить", callback_data=f"pay_{sub_key}")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("✅ Активировать", callback_data=f"activate_{sub_key}")
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="subscriptions")])
    
    text = (
        f"{sub_data['name']}\n\n"
        f"💰 Цена: {sub_data['price']} ₽\n"
        f"⏱️ Срок: {sub_data['duration_days']} дней\n\n"
        f"📊 Возможности:\n"
        f"• {sub_data['daily_limit']} сообщений в день\n"
        f"• До {sub_data['max_messages']} сообщений в одной рассылке\n"
        f"• До {sub_data['max_targets']} получателей\n\n"
    )
    
    if sub_data['price'] > 0:
        text += "Для оплаты нажмите кнопку ниже 👇"
    
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
    await db.update_subscription(user_id, sub_key, sub_data['duration_days'])
    
    await query.edit_message_text(
        f"✅ Подписка активирована!\n\n"
        f"{sub_data['name']}\n"
        f"⏱️ Срок: {sub_data['duration_days']} дней\n\n"
        f"Используйте: /start"
    )


async def payment_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация об оплате"""
    query = update.callback_query
    await query.answer()
    
    sub_key = query.data.replace("pay_", "")
    sub_data = SUBSCRIPTIONS.get(sub_key)
    
    user_id = query.from_user.id
    
    payment_id = await db.add_payment(user_id, sub_key, sub_data['price'])
    
    keyboard = [
        [InlineKeyboardButton("✅ Я оплатил", callback_data=f"paid_{payment_id}_{sub_key}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="subscriptions")]
    ]
    
    text = (
        f"💳 Оплата подписки\n\n"
        f"{sub_data['name']}\n"
        f"💰 Сумма: {sub_data['price']} ₽\n\n"
        f"📱 Реквизиты для оплаты:\n"
        f"Карта: 2200 1536 8370 4721\n"
        f"Получатель: Денис Д.\n\n"
        f"Или\n\n"
        f"💎 TON: UQBhHChlOnv0QfN7_V39xzSKK3y8i0wXpFB0z-jY-aa3kj8C\n"
        f"🥝 QIWI: +7-982-757-23-16\n\n"
        f"⚠️ После оплаты нажмите 'Я оплатил'\n"
        f"Администратор проверит платёж и активирует подписку."
    )
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


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
    
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"💳 Новая заявка на оплату!\n\n"
            f"👤 Пользователь: {user.first_name} (@{user.username or 'N/A'})\n"
            f"🆔 ID: {user_id}\n"
            f"📋 Подписка: {sub_data['name']}\n"
            f"💰 Сумма: {sub_data['price']} ₽\n"
            f"🔢 Payment ID: {payment_id}\n\n"
            f"Для активации:\n"
            f"/activate {user_id} {sub_key}"
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")
    
    await query.edit_message_text(
        "✅ Заявка отправлена!\n\n"
        "Администратор проверит платёж и активирует подписку.\n"
        "Обычно это занимает до 30 минут.\n\n"
        "Вы получите уведомление когда подписка будет активирована."
    )


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обращение в поддержку"""
    query = update.callback_query if update.callback_query else None
    
    if query:
        await query.answer()
        message = query.message
    else:
        message = update.message
    
    text = (
        "💬 Поддержка\n\n"
        "Опишите вашу проблему или вопрос.\n"
        "Администратор ответит в ближайшее время.\n\n"
        "Или напишите напрямую: @SBbotadmin\n\n"
        "Введите сообщение или /cancel:"
    )
    
    if query:
        await query.edit_message_text(text)
    else:
        await message.reply_text(text)
    
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
            f"Ответить: /reply {user.id} текст ответа"
        )
    except Exception as e:
        logger.error(f"Failed to send to admin: {e}")
    
    await update.message.reply_text(
        "✅ Ваше обращение отправлено!\n\n"
        f"📝 Номер обращения: #{ticket_id}\n\n"
        "Администратор ответит в ближайшее время.\n\n"
        "Меню: /start"
    )
    
    return ConversationHandler.END


async def connect_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подключение Telegram аккаунта"""
    if update.callback_query:
        await update.callback_query.answer()
        user_id = update.callback_query.from_user.id
        message = update.callback_query.message
    else:
        user_id = update.effective_user.id
        message = update.message
    
    session = manager.get_session(user_id)
    if session and session.is_active:
        await message.reply_text(
            f"✅ Аккаунт уже подключён!\n\n"
            f"📱 Номер: {session.phone}\n\n"
            "Для отключения: /disconnect"
        )
        return ConversationHandler.END
    
    await message.reply_text(
        "📱 Подключение Telegram аккаунта\n\n"
        "⚠️ ВАЖНО:\n"
        "• Используйте ТЕСТОВЫЙ аккаунт\n"
        "• НЕ используйте основной номер\n"
        "• Риск бана очень высокий (70-90%)\n\n"
        "Введите номер телефона в формате:\n"
        "+79123456789\n\n"
        "Или /cancel для отмены"
    )
    
    return PHONE_INPUT


async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен номер телефона"""
    user_id = update.effective_user.id
    phone = update.message.text.strip()
    
    if not phone.startswith('+'):
        await update.message.reply_text(
            "❌ Номер должен начинаться с +\n\n"
            "Пример: +79123456789\n\n"
            "Попробуйте снова:"
        )
        return PHONE_INPUT
    
    wait_msg = await update.message.reply_text("⏳ Отправка кода...")
    
    try:
        session = await manager.create_session(user_id, phone)
        success, result = await session.send_code_request()
        
        await wait_msg.delete()
        
        if success:
            phone_hash = result
            if user_id not in user_sessions:
                user_sessions[user_id] = {}
            user_sessions[user_id]['phone_hash'] = phone_hash
            user_sessions[user_id]['phone'] = phone
            
            await update.message.reply_text(
                f"✅ Код отправлен на номер:\n{phone}\n\n"
                "📨 Введите код из Telegram:\n\n"
                "Или /cancel для отмены"
            )
            return CODE_INPUT
        else:
            await update.message.reply_text(
                f"❌ Ошибка отправки кода:\n{result}\n\n"
                "Попробуйте снова: /connect"
            )
            return ConversationHandler.END
            
    except Exception as e:
        await wait_msg.delete()
        await update.message.reply_text(
            f"❌ Ошибка: {str(e)}\n\n"
            "Попробуйте снова: /connect"
        )
        return ConversationHandler.END


async def code_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен код подтверждения"""
    user_id = update.effective_user.id
    code = update.message.text.strip()
    
    if user_id not in user_sessions or 'phone_hash' not in user_sessions[user_id]:
        await update.message.reply_text(
            "❌ Сессия истекла. Начните заново: /connect"
        )
        return ConversationHandler.END
    
    phone_hash = user_sessions[user_id]['phone_hash']
    session = manager.get_session(user_id)
    
    wait_msg = await update.message.reply_text("⏳ Проверка кода...")
    
    try:
        success, result = await session.sign_in(code, phone_hash)
        await wait_msg.delete()
        
        if success:
            await update.message.reply_text(
                "✅ Аккаунт подключён успешно!\n\n"
                f"📱 Номер: {session.phone}\n\n"
                "Теперь можете создать рассылку:\n"
                "/new_mailing"
            )
            if user_id in user_sessions:
                del user_sessions[user_id]
            return ConversationHandler.END
        else:
            if result == "Требуется 2FA пароль":
                await update.message.reply_text(
                    "🔐 Требуется 2FA пароль\n\n"
                    "Введите пароль двухфакторной аутентификации:"
                )
                return PASSWORD_2FA
            else:
                await update.message.reply_text(
                    f"❌ Ошибка авторизации:\n{result}\n\n"
                    "Попробуйте снова: /connect"
                )
                return ConversationHandler.END
                
    except Exception as e:
        await wait_msg.delete()
        await update.message.reply_text(
            f"❌ Ошибка: {str(e)}\n\n"
            "Попробуйте снова: /connect"
        )
        return ConversationHandler.END


async def password_2fa_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен 2FA пароль"""
    user_id = update.effective_user.id
    password = update.message.text
    
    await update.message.delete()
    
    session = manager.get_session(user_id)
    wait_msg = await update.message.reply_text("⏳ Проверка пароля...")
    
    try:
        success, result = await session.sign_in_2fa(password)
        await wait_msg.delete()
        
        if success:
            await update.message.reply_text(
                "✅ Аккаунт подключён успешно!\n\n"
                f"📱 Номер: {session.phone}\n\n"
                "Теперь можете создать рассылку:\n"
                "/new_mailing"
            )
            if user_id in user_sessions:
                del user_sessions[user_id]
            return ConversationHandler.END
        else:
            await update.message.reply_text(
                f"❌ {result}\n\n"
                "Попробуйте снова: /connect"
            )
            return ConversationHandler.END
            
    except Exception as e:
        await wait_msg.delete()
        await update.message.reply_text(
            f"❌ Ошибка: {str(e)}\n\n"
            "Попробуйте снова: /connect"
        )
        return ConversationHandler.END


async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отключение аккаунта"""
    user_id = update.effective_user.id
    
    session = manager.get_session(user_id)
    if not session:
        await update.message.reply_text(
            "❌ Аккаунт не подключён\n\n"
            "Подключить: /connect"
        )
        return
    
    await manager.remove_session(user_id)
    
    await update.message.reply_text(
        "✅ Аккаунт отключён\n\n"
        "Для повторного подключения: /connect"
    )


async def new_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создание новой рассылки"""
    if update.callback_query:
        user_id = update.callback_query.from_user.id
        message = update.callback_query.message
        is_callback = True
    else:
        user_id = update.effective_user.id
        message = update.message
        is_callback = False
    
    session = manager.get_session(user_id)
    if not session or not session.is_active:
        text = (
            "❌ Аккаунт не подключён!\n\n"
                        "Сначала подключите аккаунт: /connect"
        )
        if is_callback:
            await message.reply_text(text)
        else:
            await message.reply_text(text)
        return ConversationHandler.END
    
    sub_type, limits = await check_subscription(user_id)
    
    session.reset_daily_counter()
    if session.messages_sent_today >= limits['daily_limit']:
        text = (
            f"❌ Достигнут дневной лимит!\n\n"
            f"📊 Отправлено: {session.messages_sent_today}/{limits['daily_limit']}\n"
            f"⏰ Попробуйте завтра\n\n"
            f"Или улучшите подписку: /subscriptions"
        )
        if is_callback:
            await message.reply_text(text)
        else:
            await message.reply_text(text)
        return ConversationHandler.END
    
    text = (
        "📮 Создание рассылки\n\n"
        "Введите список получателей (каждый с новой строки):\n\n"
        "Форматы:\n"
        "• @username\n"
        "• ID чата (число)\n"
        "• Ссылка на чат\n\n"
        f"⚠️ Максимум: {limits['max_targets']} получателей\n\n"
        "Пример:\n"
        "@username1\n"
        "@username2\n"
        "123456789\n\n"
        "Или /cancel для отмены"
    )
    
    if is_callback:
        await message.reply_text(text)
    else:
        await message.reply_text(text)
    
    return SELECT_TARGETS


async def targets_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получены целевые контакты"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    sub_type, limits = await check_subscription(user_id)
    
    if len(lines) > limits['max_targets']:
        await update.message.reply_text(
            f"❌ Слишком много получателей!\n\n"
            f"📊 Ваш лимит: {limits['max_targets']}\n"
            f"📝 Вы указали: {len(lines)}\n\n"
            f"Улучшите подписку: /subscriptions\n\n"
            "Или попробуйте снова:"
        )
        return SELECT_TARGETS
    
    if user_id not in user_sessions:
        user_sessions[user_id] = {}
    user_sessions[user_id]['targets'] = lines
    user_sessions[user_id]['messages'] = []
    
    await update.message.reply_text(
        f"✅ Получателей: {len(lines)}\n\n"
        f"📝 Теперь введите текст первого сообщения:\n\n"
        f"💡 Вы можете отправить до {limits['max_messages']} сообщений каждому получателю\n\n"
        "Или /cancel для отмены"
    )
    
    return MESSAGE_INPUT


async def message_received_userbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен текст сообщения для рассылки"""
    user_id = update.effective_user.id
    message_text = update.message.text
    
    if user_id not in user_sessions or 'targets' not in user_sessions[user_id]:
        await update.message.reply_text(
            "❌ Сессия истекла. Начните заново: /new_mailing"
        )
        return ConversationHandler.END
    
    user_sessions[user_id]['messages'].append(message_text)
    
    sub_type, limits = await check_subscription(user_id)
    current_count = len(user_sessions[user_id]['messages'])
    
    keyboard = []
    
    if current_count < limits['max_messages']:
        keyboard.append([
            InlineKeyboardButton(
                f"➕ Добавить ещё сообщение ({current_count}/{limits['max_messages']})",
                callback_data="add_more_messages"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("✅ Готово, запустить рассылку", callback_data="confirm_userbot_send")
    ])
    keyboard.append([
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_userbot_send")
    ])
    
    targets = user_sessions[user_id]['targets']
    
    preview = (
        f"📮 Сообщение {current_count} добавлено!\n\n"
        f"👥 Получателей: {len(targets)}\n"
        f"📝 Сообщений: {current_count}/{limits['max_messages']}\n\n"
    )
    
    if current_count < limits['max_messages']:
        preview += "Добавить ещё сообщение или запустить рассылку?"
    else:
        preview += "Достигнут лимит сообщений. Запустить рассылку?"
    
    await update.message.reply_text(
        preview,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return ADDITIONAL_MESSAGES


async def add_more_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить ещё сообщение"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if user_id not in user_sessions:
        await query.edit_message_text(
            "❌ Сессия истекла. Начните заново: /new_mailing"
        )
        return ConversationHandler.END
    
    sub_type, limits = await check_subscription(user_id)
    current_count = len(user_sessions[user_id]['messages'])
    
    await query.edit_message_text(
        f"📝 Введите текст сообщения #{current_count + 1}:\n\n"
        f"Всего можно: {limits['max_messages']}\n\n"
        "Или /cancel для отмены"
    )
    
    return MESSAGE_INPUT


async def confirm_userbot_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение/отмена рассылки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "cancel_userbot_send":
        await query.edit_message_text(
            "❌ Рассылка отменена\n\n"
            "Создать новую: /new_mailing"
        )
        if user_id in user_sessions:
            del user_sessions[user_id]
        return ConversationHandler.END
    
    if user_id not in user_sessions:
        await query.edit_message_text(
            "❌ Сессия истекла. Начните заново: /new_mailing"
        )
        return ConversationHandler.END
    
    session = manager.get_session(user_id)
    if not session:
        await query.edit_message_text(
            "❌ Аккаунт не подключён: /connect"
        )
        return ConversationHandler.END
    
    targets = user_sessions[user_id]['targets']
    messages = user_sessions[user_id]['messages']
    
    preview_text = "📮 Подтверждение рассылки\n\n"
    preview_text += f"👥 Получателей: {len(targets)}\n"
    preview_text += f"📝 Сообщений: {len(messages)}\n\n"
    
    for i, msg in enumerate(messages, 1):
        preview_text += f"Сообщение {i}:\n{msg[:100]}{'...' if len(msg) > 100 else ''}\n\n"
    
    preview_text += f"⏱️ Примерное время: {len(targets) * len(messages) * 60 // 60} мин\n"
    preview_text += f"🔒 Задержка: {MIN_DELAY_BETWEEN_MESSAGES}-{MAX_DELAY_BETWEEN_MESSAGES} сек\n\n"
    
    keyboard = [
        [InlineKeyboardButton("🚀 ЗАПУСТИТЬ", callback_data="start_mailing_now")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_userbot_send")]
    ]
    
    await query.edit_message_text(
        preview_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return CONFIRM_SEND


async def start_mailing_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск рассылки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if user_id not in user_sessions:
        await query.edit_message_text(
            "❌ Сессия истекла. Начните заново: /new_mailing"
        )
        return ConversationHandler.END
    
    session = manager.get_session(user_id)
    if not session:
        await query.edit_message_text(
            "❌ Аккаунт не подключён: /connect"
        )
        return ConversationHandler.END
    
    targets = user_sessions[user_id]['targets']
    messages = user_sessions[user_id]['messages']
    
    await query.edit_message_text(
        f"🚀 Рассылка запущена!\n\n"
        f"👥 Получателей: {len(targets)}\n"
        f"📝 Сообщений: {len(messages)}\n"
        f"⏳ Ожидайте завершения...\n\n"
        "Это может занять некоторое время."
    )
    
    results = await session.mass_send(
        targets,
        messages,
        MIN_DELAY_BETWEEN_MESSAGES,
        MAX_DELAY_BETWEEN_MESSAGES
    )
    
    await db.add_mailing(user_id, messages, targets)
    
    error_text = ""
    if results['errors']:
        error_text = "\n\n❌ Ошибки:\n"
        for err in results['errors'][:5]:
            error_text += f"• {err['target']}: {err['error']}\n"
        if len(results['errors']) > 5:
            error_text += f"... и ещё {len(results['errors']) - 5}"
    
    sub_type, limits = await check_subscription(user_id)
    
    await query.message.reply_text(
        f"✅ Рассылка завершена!\n\n"
        f"📤 Отправлено: {results['sent']}\n"
        f"❌ Ошибок: {results['failed']}\n"
        f"📊 Всего получателей: {len(targets)}\n"
        f"📝 Сообщений каждому: {len(messages)}\n"
        f"💬 Осталось сегодня: {limits['daily_limit'] - session.messages_sent_today}"
        f"{error_text}"
    )
    
    if user_id in user_sessions:
        del user_sessions[user_id]
    
    return ConversationHandler.END


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика"""
    query = update.callback_query if update.callback_query else None
    user_id = update.effective_user.id
    
    session = manager.get_session(user_id)
    sub_type, limits = await check_subscription(user_id)
    stats = await db.get_stats(user_id)
    
    if not session:
        text = (
            "📊 Статистика\n\n"
            f"📋 Подписка: {limits['name']}\n"
            f"📊 Всего рассылок: {stats['total_mailings']}\n"
            f"✅ Отправлено: {stats['total_sent']}\n"
            f"❌ Ошибок: {stats['total_failed']}\n\n"
            "❌ Аккаунт не подключён\n"
            "Подключите: /connect"
        )
    else:
        session.reset_daily_counter()
        text = (
            f"📊 Статистика аккаунта\n\n"
            f"📱 Номер: {session.phone}\n"
            f"📈 Статус: {'🟢 Активен' if session.is_active else '🔴 Неактивен'}\n\n"
            f"📋 Подписка: {limits['name']}\n"
            f"📤 Сегодня отправлено: {session.messages_sent_today}/{limits['daily_limit']}\n"
            f"💬 Осталось: {limits['daily_limit'] - session.messages_sent_today}\n\n"
            f"📊 Всего рассылок: {stats['total_mailings']}\n"
            f"✅ Всего отправлено: {stats['total_sent']}\n"
            f"❌ Всего ошибок: {stats['total_failed']}\n\n"
            f"⚙️ Настройки подписки:\n"
            f"• Макс. сообщений: {limits['max_messages']}\n"
            f"• Макс. получателей: {limits['max_targets']}\n"
        )
    
    if query:
        await query.answer()
        await query.edit_message_text(text)
    else:
        await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь"""
    query = update.callback_query if update.callback_query else None
    
    text = (
        "❓ Помощь - Userbot Manager\n\n"
        "📱 Подключение аккаунта:\n"
        "/connect - подключить Telegram аккаунт\n"
        "/disconnect - отключить аккаунт\n\n"
        "📮 Рассылки:\n"
        "/new_mailing - создать рассылку\n"
        "/stats - статистика\n\n"
        "💳 Подписки:\n"
        "/subscriptions - управление подписками\n\n"
        "💬 Поддержка:\n"
        "/support - связаться с администратором\n\n"
        "⚠️ ВАЖНО:\n"
        "• Используйте ТОЛЬКО тестовый аккаунт\n"
        "• НЕ спамьте незнакомым людям\n"
        "• Соблюдайте лимиты Telegram\n"
        "• Риск бана 70-90%\n\n"
        "🔒 Безопасность:\n"
        "• Задержка между сообщениями\n"
        "• Дневные лимиты\n"
        "• Защита от FloodWait\n\n"
        "📚 Поддержка: @yoursupport"
    )
    
    if query:
        await query.answer()
        await query.edit_message_text(text)
    else:
        await update.message.reply_text(text)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена диалога"""
    user_id = update.effective_user.id
    
    if user_id in user_sessions:
        del user_sessions[user_id]
    
    await update.message.reply_text(
        "❌ Операция отменена\n\n"
        "Вернуться в меню: /start"
    )
    
    return ConversationHandler.END


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка callback кнопок"""
    query = update.callback_query
    data = query.data
    
    if data == "connect_account":
        return await connect_account(update, context)
    elif data == "create_mailing":
        return await new_mailing(update, context)
    elif data == "subscriptions":
        await subscriptions_menu(update, context)
    elif data.startswith("sub_"):
        await subscription_details(update, context)
    elif data.startswith("activate_"):
        await activate_subscription(update, context)
    elif data.startswith("pay_"):
        await payment_info(update, context)
    elif data.startswith("paid_"):
        await payment_confirmation(update, context)
    elif data == "stats":
        await stats_command(update, context)
    elif data == "support":
        return await support(update, context)
    elif data == "help":
        await help_command(update, context)
    elif data == "back_to_menu":
        await query.answer()
        await query.message.delete()
        update.message = query.message
        await start(update, context)
    elif data == "add_more_messages":
        return await add_more_messages(update, context)
    elif data == "start_mailing_now":
        return await start_mailing_now(update, context)
    else:
        await query.answer()


async def admin_activate_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Активировать подписку пользователю (только для админа)"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        target_user_id = int(context.args[0])
        sub_type = context.args[1]
        
        sub_data = SUBSCRIPTIONS.get(sub_type)
        if not sub_data:
            await update.message.reply_text("❌ Неверный тип подписки!")
            return
        
        await db.update_subscription(target_user_id, sub_type, sub_data['duration_days'])
        
        try:
            await context.bot.send_message(
                target_user_id,
                f"✅ Ваша подписка активирована!\n\n"
                f"{sub_data['name']}\n"
                f"⏱️ Срок: {sub_data['duration_days']} дней\n\n"
                f"Возможности:\n"
                f"• {sub_data['daily_limit']} сообщений/день\n"
                f"• {sub_data['max_messages']} сообщений в рассылке\n"
                f"• {sub_data['max_targets']} получателей\n\n"
                f"Используйте: /start"
            )
        except:
            pass
        
        await update.message.reply_text(
            f"✅ Подписка активирована!\n\n"
            f"User ID: {target_user_id}\n"
            f"Тип: {sub_data['name']}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def admin_reply_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответить на обращение в поддержку"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        target_user_id = int(context.args[0])
        message = ' '.join(context.args[1:])
        
        await context.bot.send_message(
            target_user_id,
            f"💬 Ответ от поддержки:\n\n{message}"
        )
        
        await update.message.reply_text(
            f"✅ Ответ отправлен пользователю {target_user_id}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Общая статистика бота (только для админа)"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        async with db.db.execute('SELECT COUNT(*) FROM users') as cursor:
            total_users = (await cursor.fetchone())[0]
        
        async with db.db.execute('''
            SELECT subscription_type, COUNT(*) 
            FROM users 
            GROUP BY subscription_type
        ''') as cursor:
            subs_stats = await cursor.fetchall()
        
        async with db.db.execute('''
            SELECT 
                COUNT(*) as total_mailings,
                SUM(sent_count) as total_sent,
                SUM(failed_count) as total_failed
            FROM mailings
        ''') as cursor:
            row = await cursor.fetchone()
            total_mailings = row[0] or 0
            total_sent = row[1] or 0
            total_failed = row[2] or 0
        
        active_sessions = len(manager.get_all_sessions())
        
        async with db.db.execute('''
            SELECT COUNT(*) FROM support_tickets WHERE status = 'open'
        ''') as cursor:
            open_tickets = (await cursor.fetchone())[0]
        
        text = (
            "📊 СТАТИСТИКА БОТА\n\n"
            f"👥 Пользователей: {total_users}\n"
            f"📱 Активных сессий: {active_sessions}\n\n"
            f"📋 Подписки:\n"
        )
        
        for sub_type, count in subs_stats:
            sub_name = SUBSCRIPTIONS.get(sub_type, {}).get('name', sub_type)
            text += f"  {sub_name}: {count}\n"
        
        text += (
            f"\n📮 Рассылки:\n"
            f"  Всего: {total_mailings}\n"
            f"  ✅ Отправлено: {total_sent}\n"
                        f"  ❌ Ошибок: {total_failed}\n\n"
            f"💬 Открытых обращений: {open_tickets}\n"
        )
        
        await update.message.reply_text(text)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        logger.error(f"Admin stats error: {e}")


async def admin_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список пользователей (только для админа)"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        limit = 20
        if context.args and context.args[0].isdigit():
            limit = int(context.args[0])
        
        async with db.db.execute(f'''
            SELECT user_id, username, first_name, subscription_type, created_at
            FROM users
            ORDER BY created_at DESC
            LIMIT {limit}
        ''') as cursor:
            users = await cursor.fetchall()
        
        if not users:
            await update.message.reply_text("👥 Пользователей нет")
            return
        
        text = f"👥 Последние {len(users)} пользователей:\n\n"
        
        for user in users:
            user_id, username, first_name, sub_type, created = user
            sub_name = SUBSCRIPTIONS.get(sub_type, {}).get('name', sub_type)
            username_str = f"@{username}" if username else "нет"
            text += (
                f"🆔 {user_id}\n"
                f"👤 {first_name} ({username_str})\n"
                f"📋 {sub_name}\n"
                f"📅 {created[:10]}\n\n"
            )
        
        await update.message.reply_text(text)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        logger.error(f"Admin list users error: {e}")


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Рассылка всем пользователям (только для админа)"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        await update.message.reply_text(
            "📢 Рассылка всем пользователям\n\n"
            "Использование:\n"
            "/broadcast текст сообщения"
        )
        return
    
    message_text = ' '.join(context.args)
    
    try:
        async with db.db.execute('SELECT user_id FROM users WHERE is_active = 1') as cursor:
            users = await cursor.fetchall()
        
        sent = 0
        failed = 0
        
        status_msg = await update.message.reply_text(
            f"📤 Начинаю рассылку для {len(users)} пользователей..."
        )
        
        for user_id, in users:
            try:
                await context.bot.send_message(user_id, f"📢 Объявление:\n\n{message_text}")
                sent += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                failed += 1
                logger.error(f"Broadcast error for {user_id}: {e}")
        
        await status_msg.edit_text(
            f"✅ Рассылка завершена!\n\n"
            f"📤 Отправлено: {sent}\n"
            f"❌ Ошибок: {failed}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        logger.error(f"Admin broadcast error: {e}")


async def admin_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о пользователе (только для админа)"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "ℹ️ Информация о пользователе\n\n"
            "Использование:\n"
            "/userinfo USER_ID"
        )
        return
    
    user_id = int(context.args[0])
    
    try:
        user = await db.get_user(user_id)
        if not user:
            await update.message.reply_text(f"❌ Пользователь {user_id} не найден")
            return
        
        stats = await db.get_stats(user_id)
        
        sub_type = user['subscription_type']
        sub_name = SUBSCRIPTIONS.get(sub_type, {}).get('name', sub_type)
        sub_until = user.get('subscription_until', 'Не указано')
        
        session = manager.get_session(user_id)
        session_status = "✅ Активна" if session and session.is_active else "❌ Нет"
        session_phone = session.phone if session else "Нет"
        
        text = (
            f"ℹ️ Информация о пользователе\n\n"
            f"🆔 ID: {user_id}\n"
            f"👤 Имя: {user['first_name']} {user.get('last_name', '')}\n"
            f"📱 Username: @{user.get('username', 'нет')}\n"
            f"📞 Телефон: {user.get('phone', 'нет')}\n\n"
            f"📋 Подписка: {sub_name}\n"
            f"⏱️ До: {sub_until}\n\n"
            f"📱 Сессия: {session_status}\n"
            f"📞 Номер сессии: {session_phone}\n\n"
            f"📊 Статистика:\n"
            f"  Рассылок: {stats['total_mailings']}\n"
            f"  ✅ Отправлено: {stats['total_sent']}\n"
            f"  ❌ Ошибок: {stats['total_failed']}\n\n"
            f"📅 Регистрация: {user['created_at']}"
        )
        
        await update.message.reply_text(text)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        logger.error(f"Admin user info error: {e}")


async def admin_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Заблокировать пользователя (только для админа)"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "🚫 Блокировка пользователя\n\n"
            "Использование:\n"
            "/ban USER_ID"
        )
        return
    
    user_id = int(context.args[0])
    
    try:
        await db.db.execute(
            'UPDATE users SET is_active = 0 WHERE user_id = ?',
            (user_id,)
        )
        await db.db.commit()
        
        await manager.remove_session(user_id)
        
        await update.message.reply_text(f"✅ Пользователь {user_id} заблокирован")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def admin_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Разблокировать пользователя (только для админа)"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "✅ Разблокировка пользователя\n\n"
            "Использование:\n"
            "/unban USER_ID"
        )
        return
    
    user_id = int(context.args[0])
    
    try:
        await db.db.execute(
            'UPDATE users SET is_active = 1 WHERE user_id = ?',
            (user_id,)
        )
        await db.db.commit()
        
        await update.message.reply_text(f"✅ Пользователь {user_id} разблокирован")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь для админа"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    text = (
        "👨‍💼 КОМАНДЫ АДМИНИСТРАТОРА\n\n"
        "📋 Управление подписками:\n"
        "/activate USER_ID TYPE - активировать подписку\n"
        "  Типы: free, hobby, pro, unlimited\n\n"
        "💬 Поддержка:\n"
        "/reply USER_ID текст - ответить пользователю\n\n"
        "📊 Статистика:\n"
        "/adminstats - общая статистика бота\n"
        "/userinfo USER_ID - инфо о пользователе\n"
        "/listusers [N] - список последних N пользователей\n\n"
        "📢 Рассылки:\n"
        "/broadcast текст - рассылка всем\n\n"
        "🚫 Модерация:\n"
        "/ban USER_ID - заблокировать\n"
        "/unban USER_ID - разблокировать\n\n"
        "❓ Помощь:\n"
        "/adminhelp - эта справка\n\n"
        "Примеры:\n"
        "/activate 123456789 pro\n"
        "/reply 123456789 Проблема решена\n"
        "/userinfo 123456789\n"
        "/broadcast Техработы 10 минут"
    )
    
    await update.message.reply_text(text)


async def main():
    """Запуск бота"""
    await db.connect()
    logger.info("Database connected")
    
    application = Application.builder().token(MANAGER_BOT_TOKEN).build()
    
    connect_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(connect_account, pattern="^connect_account$"),
            CommandHandler("connect", connect_account)
        ],
        states={
            PHONE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_received)],
            CODE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, code_received)],
            PASSWORD_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, password_2fa_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        per_chat=True,
        per_user=True,
        allow_reentry=True
    )
    
    mailing_conv = ConversationHandler(
        entry_points=[
            CommandHandler("new_mailing", new_mailing),
            CallbackQueryHandler(new_mailing, pattern="^create_mailing$")
        ],
        states={
            SELECT_TARGETS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, targets_received)
            ],
            MESSAGE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, message_received_userbot)
            ],
            ADDITIONAL_MESSAGES: [
                CallbackQueryHandler(add_more_messages, pattern="^add_more_messages$"),
                CallbackQueryHandler(confirm_userbot_send, pattern="^confirm_userbot_send$"),
                CallbackQueryHandler(confirm_userbot_send, pattern="^cancel_userbot_send$")
            ],
            CONFIRM_SEND: [
                CallbackQueryHandler(start_mailing_now, pattern="^start_mailing_now$"),
                CallbackQueryHandler(confirm_userbot_send, pattern="^cancel_userbot_send$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start)
        ],
        per_message=False,
        per_chat=True,
        per_user=True,
        allow_reentry=True,
        conversation_timeout=600
    )
    
    support_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(support, pattern="^support$"),
            CommandHandler("support", support)
        ],
        states={
            SUPPORT_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support_message_received)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        per_chat=True,
        per_user=True,
        allow_reentry=True
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("disconnect", disconnect))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("subscriptions", subscriptions_menu))
    
    application.add_handler(CommandHandler("activate", admin_activate_subscription))
    application.add_handler(CommandHandler("reply", admin_reply_support))
    application.add_handler(CommandHandler("adminstats", admin_stats))
    application.add_handler(CommandHandler("listusers", admin_list_users))
    application.add_handler(CommandHandler("broadcast", admin_broadcast))
    application.add_handler(CommandHandler("userinfo", admin_user_info))
    application.add_handler(CommandHandler("ban", admin_ban_user))
    application.add_handler(CommandHandler("unban", admin_unban_user))
    application.add_handler(CommandHandler("adminhelp", admin_help))
    
    application.add_handler(connect_conv)
    application.add_handler(mailing_conv)
    application.add_handler(support_conv)
    
    application.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("🚀 Manager Bot started!")
    logger.info(f"📋 Subscriptions available: {len(SUBSCRIPTIONS)}")
    logger.info(f"👤 Admin ID: {ADMIN_ID}")
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Остановка...")
    finally:
        await manager.stop_all()
        await application.stop()
        await application.shutdown()
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")