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

# Публичный канал (для всех)
PUBLIC_CHANNEL_URL = os.getenv('PUBLIC_CHANNEL_URL', '@your_public_channel')
PUBLIC_CHANNEL_NAME = "📢 Публичный канал"

# Приватный канал (после оплаты, через админа)
PRIVATE_CHANNEL_URL = os.getenv('PRIVATE_CHANNEL_URL', '@your_private_channel')
PRIVATE_CHANNEL_NAME = "🔒 Приватный канал"

# ============= ТАРИФНЫЕ ПЛАНЫ =============

SUBSCRIPTIONS = {
    'amateur': {
        'name': '🎯 Любительская',
        'price': 499,
        'duration': 30,  # дней
        'messages_limit': 1000,  # сообщений в день
        'accounts_limit': 10,    # аккаунтов
        'description': (
            '• 10 аккаунтов\n'
            '• До 1000 сообщений/день\n'
            '• Базовая поддержка\n'
            '• Доступ к приватному каналу'
        )
    },
    'pro': {
        'name': '💼 Профессиональная',
        'price': 1499,
        'duration': 30,
        'messages_limit': 5000,
        'accounts_limit': 50,
        'description': (
            '• 50 аккаунтов\n'
            '• До 5000 сообщений/день\n'
            '• Приоритетная поддержка\n'
            '• Доступ к приватному каналу\n'
            '• Дополнительные функции'
        )
    },
    'premium': {
        'name': '👑 Премиум',
        'price': 4999,
        'duration': 30,
        'messages_limit': 99999,  # практически безлимит
        'accounts_limit': 999,
        'description': (
            '• Безлимит аккаунтов\n'
            '• Безлимит сообщений\n'
            '• VIP поддержка 24/7\n'
            '• Доступ к приватному каналу\n'
            '• Эксклюзивные функции\n'
            '• Персональный менеджер'
        )
    },
    'trial': {
        'name': '🎁 Пробная',
        'price': 0,
        'duration': 3,
        'messages_limit': 100,
        'accounts_limit': 1,
        'description': '• 3 дня пробного периода\n• Ограниченный функционал'
    }
}

# ============= РЕКВИЗИТЫ ДЛЯ ОПЛАТЫ =============
PAYMENT_CARD = os.getenv('PAYMENT_CARD', '2200 1536 8370 4721')
PAYMENT_PHONE = os.getenv('PAYMENT_PHONE', '+7 982-757-23-16')

# ============= БАЗА ДАННЫХ =============
DATABASE_PATH = os.getenv('DATABASE_PATH', 'bot.db')

# ============= НАСТРОЙКИ РАССЫЛКИ =============
MAILING_DELAY = float(os.getenv('MAILING_DELAY', '1.0'))  # секунд между сообщениями (анти-флуд)

# ============= ЛОГИРОВАНИЕ =============
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# ============= НАСТРОЙКИ СЕССИЙ =============
SESSIONS_DIR = os.getenv('SESSIONS_DIR', './sessions')

# ============= БЭКАПЫ =============
BACKUP_DIR = os.getenv('BACKUP_DIR', './backups')

# ============= ПРОЧЕЕ =============
TRIAL_DAYS = int(os.getenv('TRIAL_DAYS', '3'))