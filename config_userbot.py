#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Конфигурация для Telegram Userbot Manager
"""

import os
from datetime import timedelta

# ============= TELEGRAM API =============
API_ID = int(os.getenv('API_ID', '28890915'))
API_HASH = os.getenv('API_HASH', '4984bb66f393bb411bd33674db81256e')

# ============= БОТЫ =============
MANAGER_BOT_TOKEN = os.getenv('MANAGER_BOT_TOKEN', '8457587045:AAHellpvMkkHeJLVzYMCjKrE6smt9ekBja0')

# ============= АДМИНИСТРАТОР =============
ADMIN_ID = int(os.getenv('ADMIN_ID', '5688880070'))

# ============= КАНАЛЫ =============
PUBLIC_CHANNEL_URL = os.getenv('PUBLIC_CHANNEL_URL', '@your_public_channel')
PUBLIC_CHANNEL_NAME = "📢 Публичный канал"

PRIVATE_CHANNEL_URL = os.getenv('PRIVATE_CHANNEL_URL', '@your_private_channel')
PRIVATE_CHANNEL_NAME = "🔒 Приватный канал"

# Тарифы подписок
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
        'max_accounts': 3,
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
        'max_accounts': -1,  # -1 = безлимит
        'max_mailings_per_day': -1,  # -1 = безлимит
        'description': 'Без ограничений'
    }
}

# Способы оплаты
PAYMENT_METHODS = {
    'sberbank': {
        'name': '💳 Альфа',
        'wallet': '2200 1536 8370 4721'  # Замени на свой номер карты
    },
    'tinkoff': {
        'name': '💳 Т-банк',
        'wallet': '2200 7020 4134 1848'  # Замени на свой номер карты
    },
    'yoomoney': {
        'name': '💰 ЮMoney',
        'wallet': '4100118589897796'  # Замени на свой кошелек
    },
    'usdt': {
        'name': '₿ USDT TRC20',
        'wallet': 'TD5EJBjQ3zM2SpgLCaBf4XptT7CoAFWPQr'  # Замени на свой адрес
    }
}

# Username поддержки
SUPPORT_USERNAME = 'your_support_bot'  # Замени на свой

# ============= РЕКВИЗИТЫ ДЛЯ ОПЛАТЫ =============
PAYMENT_CARD = os.getenv('PAYMENT_CARD', '2200 1536 8370 4721')
PAYMENT_PHONE = os.getenv('PAYMENT_PHONE', '+7-982-757-23-16')

# ============= БАЗА ДАННЫХ =============
DATABASE_PATH = os.getenv('DATABASE_PATH', 'bot.db')

# ============= НАСТРОЙКИ РАССЫЛКИ =============
MAILING_DELAY = float(os.getenv('MAILING_DELAY', '2.0'))

# ============= ЛОГИРОВАНИЕ =============
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# ============= НАСТРОЙКИ СЕССИЙ =============
SESSIONS_DIR = os.getenv('SESSIONS_DIR', './sessions')

# ============= БЭКАПЫ =============
BACKUP_DIR = os.getenv('BACKUP_DIR', './backups')

# ============= ПРОЧЕЕ =============
TRIAL_DAYS = int(os.getenv('TRIAL_DAYS', '3'))