#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Configuration file for Userbot Manager
"""

import os

# ==================== ОСНОВНЫЕ НАСТРОЙКИ ====================

# Токен бота от @BotFather
BOT_TOKEN = os.getenv('BOT_TOKEN', '8457587045:AAHellpvMkkHeJLVzYMCjKrE6smt9ekBja0')

# ID администратора
ADMIN_ID = int(os.getenv('ADMIN_ID', '7637526159'))

# ID канала для обязательной подписки
CHANNEL_ID = os.getenv('CHANNEL_ID', '@test')

# Username поддержки
SUPPORT_USERNAME = os.getenv('SUPPORT_USERNAME', 'support')

# ==================== TELEGRAM API ====================

TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID')
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')

# ==================== ТАРИФЫ ====================

SUBSCRIPTIONS = {
    'trial': {
        'name': '🆓 Пробный',
        'price': 0,
        'days': 3,
        'max_accounts': 1,
        'max_mailings_per_day': 3,
        'description': '3 дня бесплатно для теста'
    },
    'amateur': {
        'name': '🌱 Любительский',
        'price': 499,
        'days': 30,
        'max_accounts': 2,
        'max_mailings_per_day': 10,
        'description': 'Для начинающих'
    },
    'professional': {
        'name': '💼 Профессиональный',
        'price': 1499,
        'days': 30,
        'max_accounts': 10,
        'max_mailings_per_day': 50,
        'description': 'Для активных пользователей'
    },
    'premium': {
        'name': '💎 Премиум',
        'price': 4999,
        'days': 30,
        'max_accounts': -1,
        'max_mailings_per_day': -1,
        'description': 'Без ограничений'
    }
}

# ==================== СПОСОБЫ ОПЛАТЫ ====================

PAYMENT_METHODS = {
    'sberbank': {
        'name': '💳 Альфа',
        'wallet': '2200 1536 8370 4721'
    },
    'tinkoff': {
        'name': '💳 Т-банк',
        'wallet': '2200 7020 4134 1848'
    },
    'yoomoney': {
        'name': '💰 ЮMoney',
        'wallet': '4100118589897796'
    },
    'usdt': {
        'name': '₿ USDT TRC20',
        'wallet': 'TD5EJBjQ3zM2SpgLCaBf4XptT7CoAFWPQr'
    }
}

# ==================== НАСТРОЙКИ РАССЫЛОК ====================

# Задержки (в секундах)
DELAY_BETWEEN_JOINS = 3  # Задержка между вступлениями
DELAY_BETWEEN_MESSAGES = 5  # Задержка между сообщениями
DELAY_BETWEEN_ACCOUNTS = 10  # Задержка между аккаунтами

# Лимиты
MAX_JOINS_PER_ACCOUNT = 50  # Максимум вступлений за раз
MAX_MESSAGES_PER_ACCOUNT = 100  # Максимум сообщений за раз