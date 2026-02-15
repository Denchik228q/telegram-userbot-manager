#!/usr/bin/env python3
"""
Telegram Bot Manager - Менеджер для управления Telegram аккаунтами и рассылок
"""

import os
import sys
import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, List

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

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

from database import Database
from backup_manager import BackupManager

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Переменные окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

if not BOT_TOKEN or ADMIN_ID == 0:
    logger.error("❌ BOT_TOKEN or ADMIN_ID not set!")
    sys.exit(1)

# Инициализация
db = Database()
backup_manager = BackupManager()

# Состояния для ConversationHandler
CONNECT_PHONE, CONNECT_CODE, CONNECT_PASSWORD = range(3)
MAILING_ACCOUNT, MAILING_MESSAGE, MAILING_RECIPIENTS = range(3, 6)
BROADCAST_MESSAGE = 6

# Хранилище временных данных
user_sessions = {}

# ==================== ОСНОВНЫЕ КОМАНДЫ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    
    # Создаём пользователя если его нет
    user = db.get_user(user_id)
    if not user:
        db.create_user(
            user_id=user_id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name
        )
    
    db.update_user_activity(user_id)
    
    first_name = update.effective_user.first_name or "Пользователь"
    
    keyboard = [
        [
            InlineKeyboardButton("📱 Мои аккаунты", callback_data='my_accounts'),
            InlineKeyboardButton("📤 Рассылки", callback_data='mailings')
        ],
        [
            InlineKeyboardButton("💳 Тарифы", callback_data='tariffs'),
            InlineKeyboardButton("📊 Статистика", callback_data='statistics')
        ],
        [
            InlineKeyboardButton("📜 История", callback_data='history'),
            InlineKeyboardButton("ℹ️ Помощь", callback_data='help')
        ]
    ]
    
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("👨‍💼 Админ-панель", callback_data='admin_panel')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"👋 Привет, {first_name}!\n\n"
        f"🤖 Я бот для управления Telegram аккаунтами и массовых рассылок.\n\n"
        f"📱 **Возможности:**\n"
        f"• Подключение неограниченного числа аккаунтов\n"
        f"• Массовые рассылки сообщений\n"
        f"• Планировщик отложенных рассылок\n"
        f"• Детальная статистика\n\n"
        f"Выберите действие из меню:"
    )
    
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ==================== МОИ АККАУНТЫ ====================

async def my_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список аккаунтов пользователя"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    accounts = db.get_user_accounts(user_id)
    
    text = "📱 **Мои аккаунты:**\n\n"
    keyboard = []
    
    if not accounts:
        text += "У вас пока нет подключенных аккаунтов.\n\n"
        text += "Нажмите кнопку ниже, чтобы подключить первый аккаунт."
    else:
        for acc in accounts:
            status = "✅" if acc['is_active'] else "❌"
            text += f"{status} {acc['phone']}\n"
            keyboard.append([
                InlineKeyboardButton(f"📱 {acc['phone']}", callback_data=f"account_{acc['id']}")
            ])
    
    keyboard.append([InlineKeyboardButton("➕ Подключить аккаунт", callback_data='connect_account')])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='start')])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ==================== ПОДКЛЮЧЕНИЕ АККАУНТА ====================

async def connect_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало подключения аккаунта"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Проверяем лимиты
    limits = db.check_limits(user_id)
    
    if not limits['can_add_account']:
        sub = db.get_user_subscription(user_id)
        text = (
            "❌ **Достигнут лимит аккаунтов**\n\n"
            f"Ваш тариф: **{sub['plan'].title()}**\n"
            f"Максимум аккаунтов: **{sub['limits']['accounts']}**\n\n"
            "Обновите тариф для подключения большего количества аккаунтов."
        )
        keyboard = [
            [InlineKeyboardButton("💳 Тарифы", callback_data='tariffs')],
            [InlineKeyboardButton("🔙 Назад", callback_data='my_accounts')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return ConversationHandler.END
    
    text = (
        "📱 **Подключение аккаунта**\n\n"
        f"Осталось слотов: **{limits['accounts_left']}**\n\n"
        "Введите номер телефона в международном формате:\n"
        "Например: `+79991234567`"
    )
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data='my_accounts')]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    return CONNECT_PHONE

async def connect_phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен номер телефона"""
    user_id = update.effective_user.id
    phone = update.message.text.strip()
    
    # Проверяем формат
    if not phone.startswith('+') or not phone[1:].isdigit():
        await update.message.reply_text(
            "❌ Неверный формат номера!\n\n"
            "Введите номер в формате: `+79991234567`",
            parse_mode='Markdown'
        )
        return CONNECT_PHONE
    
    # Проверяем, не подключен ли уже
    existing = db.get_account_by_phone(phone)
    if existing:
        await update.message.reply_text(
            "❌ Этот номер уже подключен!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data='my_accounts')
            ]])
        )
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ Отправляем код...")
    
    try:
        # Создаём клиент Telethon
        api_id = int(os.getenv('TELEGRAM_API_ID', '94575'))
        api_hash = os.getenv('TELEGRAM_API_HASH', 'a3406de8d171bb422bb6ddf3bbd800e2')
        
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        
        # Отправляем код
        await client.send_code_request(phone)
        
        # Сохраняем сессию
        user_sessions[user_id] = {
            'client': client,
            'phone': phone,
            'api_id': api_id,
            'api_hash': api_hash
        }
        
        await update.message.reply_text(
            "✅ Код отправлен!\n\n"
            "Введите код из Telegram (например: `12345`):",
            parse_mode='Markdown'
        )
        
        return CONNECT_CODE
        
    except Exception as e:
        logger.error(f"Error sending code: {e}")
        await update.message.reply_text(
            f"❌ Ошибка: {str(e)}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data='my_accounts')
            ]])
        )
        return ConversationHandler.END

async def connect_code_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен код подтверждения"""
    user_id = update.effective_user.id
    code = update.message.text.strip()
    
    if user_id not in user_sessions:
        await update.message.reply_text("❌ Сессия истекла. Начните заново.")
        return ConversationHandler.END
    
    session_data = user_sessions[user_id]
    client = session_data['client']
    phone = session_data['phone']
    
    try:
        await client.sign_in(phone, code)
        
        # Получаем session string
        session_string = client.session.save()
        
        # Сохраняем в БД
        account_id = db.create_account(
            user_id=user_id,
            phone=phone,
            session_string=session_string,
            api_id=session_data['api_id'],
            api_hash=session_data['api_hash']
        )
        
        # Очищаем сессию
        del user_sessions[user_id]
        await client.disconnect()
        
        await update.message.reply_text(
            f"✅ Аккаунт {phone} успешно подключен!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📱 Мои аккаунты", callback_data='my_accounts')
            ]])
        )
        
        return ConversationHandler.END
        
    except SessionPasswordNeededError:
        await update.message.reply_text(
            "🔐 Требуется пароль 2FA.\n\n"
            "Введите пароль:"
        )
        return CONNECT_PASSWORD
        
    except PhoneCodeInvalidError:
        await update.message.reply_text(
            "❌ Неверный код!\n\n"
            "Попробуйте ещё раз:"
        )
        return CONNECT_CODE
        
    except Exception as e:
        logger.error(f"Error in sign_in: {e}")
        await update.message.reply_text(
            f"❌ Ошибка: {str(e)}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data='my_accounts')
            ]])
        )
        return ConversationHandler.END

async def connect_password_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получен пароль 2FA"""
    user_id = update.effective_user.id
    password = update.message.text.strip()
    
    if user_id not in user_sessions:
        await update.message.reply_text("❌ Сессия истекла. Начните заново.")
        return ConversationHandler.END
    
    session_data = user_sessions[user_id]
    client = session_data['client']
    phone = session_data['phone']
    
    try:
        await client.sign_in(password=password)
        
        # Получаем session string
        session_string = client.session.save()
        
        # Сохраняем в БД
        db.create_account(
            user_id=user_id,
            phone=phone,
            session_string=session_string,
            api_id=session_data['api_id'],
            api_hash=session_data['api_hash']
        )
        
        # Очищаем сессию
        del user_sessions[user_id]
        await client.disconnect()
        
        await update.message.reply_text(
            f"✅ Аккаунт {phone} успешно подключен!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📱 Мои аккаунты", callback_data='my_accounts')
            ]])
        )
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error with 2FA: {e}")
        await update.message.reply_text(
            f"❌ Неверный пароль: {str(e)}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data='my_accounts')
            ]])
        )
        return ConversationHandler.END

async def connect_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена подключения"""
    user_id = update.effective_user.id
    
    if user_id in user_sessions:
        try:
            await user_sessions[user_id]['client'].disconnect()
        except:
            pass
        del user_sessions[user_id]
    
    return ConversationHandler.END

# ==================== РАССЫЛКИ ====================

async def show_mailings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список рассылок"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    mailings = db.get_user_mailings(user_id, limit=20)
    
    text = "📤 **Рассылки:**\n\n"
    keyboard = []
    
    if not mailings:
        text += "У вас пока нет рассылок."
    else:
        for m in mailings:
            status_emoji = {'pending': '⏳', 'running': '▶️', 'completed': '✅', 'failed': '❌'}.get(m['status'], '❓')
            text += f"{status_emoji} **#{m['id']}** - {m['sent_count']}/{m['total_recipients']}\n"
    
    keyboard.append([InlineKeyboardButton("➕ Создать рассылку", callback_data='create_mailing')])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='start')])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ==================== ПЛАНИРОВЩИК ====================

async def show_scheduler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать планировщик"""
    query = update.callback_query
    await query.answer()
    
    text = "⏰ **Планировщик**\n\nФункция в разработке..."
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='start')]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ==================== СТАТИСТИКА ====================

async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    accounts = db.get_user_accounts(user_id)
    mailings = db.get_user_mailings(user_id)
    
    total_sent = sum(m['sent_count'] for m in mailings)
    
    text = (
        "📊 **Статистика:**\n\n"
        f"📱 Аккаунтов: {len(accounts)}\n"
        f"📤 Рассылок: {len(mailings)}\n"
        f"✅ Отправлено: {total_sent}"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='start')]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ==================== ИСТОРИЯ ====================

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать историю"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    mailings = db.get_user_mailings(user_id, limit=10)
    
    text = "📜 **История (последние 10):**\n\n"
    
    if not mailings:
        text += "Пусто"
    else:
        for m in mailings:
            text += f"#{m['id']} - {m['status']}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='start')]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ==================== ПОМОЩЬ ====================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать помощь"""
    query = update.callback_query
    await query.answer()
    
    text = (
        "ℹ️ **Помощь**\n\n"
        "**Как подключить аккаунт:**\n"
        "1. Нажмите '📱 Мои аккаунты'\n"
        "2. Нажмите '➕ Подключить аккаунт'\n"
        "3. Введите номер телефона\n"
        "4. Введите код из Telegram\n\n"
        "**Поддержка:** @support"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='start')]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def show_tariffs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать тарифы"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    sub = db.get_user_subscription(user_id)
    
    current_plan = sub['plan']
    
    plans = {
        'free': {'emoji': '🆓', 'name': 'Бесплатный', 'price': '0₽', 'accounts': 1, 'messages': 100},
        'standard': {'emoji': '⭐', 'name': 'Стандарт', 'price': '490₽/мес', 'accounts': 5, 'messages': 1000},
        'premium': {'emoji': '💎', 'name': 'Премиум', 'price': '1990₽/мес', 'accounts': '∞', 'messages': '∞'}
    }
    
    text = "💳 **Тарифы:**\n\n"
    
    for plan_id, plan in plans.items():
        active = "✅ " if current_plan == plan_id else ""
        text += f"{active}{plan['emoji']} **{plan['name']}** - {plan['price']}\n"
        text += f"   📱 Аккаунтов: {plan['accounts']}\n"
        text += f"   📤 Сообщений/день: {plan['messages']}\n\n"
    
    if current_plan != 'free':
        text += f"📅 Ваша подписка до: {sub['end_date'][:10] if sub['end_date'] else 'Не указано'}\n\n"
    
    text += f"📊 Использовано сегодня: {sub['messages_sent']} сообщений"
    
    keyboard = []
    
    if current_plan == 'free':
        keyboard.append([InlineKeyboardButton("⭐ Купить Стандарт", callback_data='buy_standard')])
        keyboard.append([InlineKeyboardButton("💎 Купить Премиум", callback_data='buy_premium')])
    elif current_plan == 'standard':
        keyboard.append([InlineKeyboardButton("💎 Upgrade до Премиум", callback_data='buy_premium')])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='start')])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def buy_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Покупка тарифа"""
    query = update.callback_query
    await query.answer()
    
    plan = 'standard' if 'standard' in query.data else 'premium'
    price = '490₽' if plan == 'standard' else '1990₽'
    
    text = (
        f"💳 **Оплата тарифа**\n\n"
        f"Тариф: **{plan.title()}**\n"
        f"Стоимость: **{price}**\n\n"
        f"Для оплаты свяжитесь с @support\n"
        f"После оплаты отправьте чек администратору."
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='tariffs')]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ==================== ГЛАВНАЯ ФУНКЦИЯ ====================

def main():
    """Запуск бота"""
    logger.info("🚀 Starting Bot...")
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Обработчик /start
    application.add_handler(CommandHandler("start", start))
    
    # Обработчики callback
    application.add_handler(CallbackQueryHandler(start, pattern='^start$'))
    application.add_handler(CallbackQueryHandler(my_accounts, pattern='^my_accounts$'))
    application.add_handler(CallbackQueryHandler(show_mailings, pattern='^mailings$'))
    application.add_handler(CallbackQueryHandler(show_scheduler, pattern='^scheduler$'))
    application.add_handler(CallbackQueryHandler(show_statistics, pattern='^statistics$'))
    application.add_handler(CallbackQueryHandler(show_history, pattern='^history$'))
    application.add_handler(CallbackQueryHandler(help_command, pattern='^help$'))
    application.add_handler(CallbackQueryHandler(show_tariffs, pattern='^tariffs$'))
    application.add_handler(CallbackQueryHandler(buy_plan, pattern='^buy_(standard|premium)$'))
    
    # ConversationHandler для подключения аккаунта
    connect_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(connect_account_start, pattern="^connect_account$")],
        states={
            CONNECT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, connect_phone_received)],
            CONNECT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, connect_code_received)],
            CONNECT_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, connect_password_received)],
        },
        fallbacks=[CallbackQueryHandler(connect_cancel, pattern="^my_accounts$")],
        per_user=True,
        per_chat=True
    )
    
    application.add_handler(connect_conv)
    
    logger.info("✅ Bot started!")
    application.run_polling()

if __name__ == '__main__':
    main()