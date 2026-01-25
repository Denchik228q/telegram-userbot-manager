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

# ============= КАНАЛЫ ДЛЯ ПОДПИСКИ =============

# Публичные каналы (формат: @username или https://t.me/username)
CHANNEL_1_URL = os.getenv('CHANNEL_1_URL', '@your_channel_1')
CHANNEL_2_URL = os.getenv('CHANNEL_2_URL', '@your_channel_2')
CHANNEL_3_URL = os.getenv('CHANNEL_3_URL', '@your_channel_3')

# Приватный канал (после оплаты)
PRIVATE_CHANNEL_URL = os.getenv('PRIVATE_CHANNEL_URL', '@your_private_channel')

# Названия каналов для кнопок
CHANNEL_1_NAME = "📢 Основной канал"
CHANNEL_2_NAME = "💎 VIP канал"
CHANNEL_3_NAME = "🔔 Новости"
PRIVATE_CHANNEL_NAME = "🔒 Приватный канал"

# ============= ТАРИФНЫЕ ПЛАНЫ =============

SUBSCRIPTIONS = {
    'basic': {
        'name': 'Basic Plan',
        'price': 299,
        'duration': 30,  # дней
        'description': '• Подключение 1 юзербота\n• Доступ к приватному каналу\n• Базовая поддержка'
    },
    'standard': {
        'name': 'Standard Plan',
        'price': 499,
        'duration': 30,
        'description': '• Подключение до 3 юзерботов\n• Приоритетная поддержка\n• Все функции Basic'
    },
    'vip': {
        'name': 'VIP Plan',
        'price': 999,
        'duration': 30,
        'description': '• Безлимит юзерботов\n• VIP поддержка 24/7\n• Эксклюзивные функции'
    },
    'trial': {
        'name': 'Trial',
        'price': 0,
        'duration': 3,
        'description': '• Пробный период 3 дня\n• Ограниченный функционал'
    }
}

# ============= БАЗА ДАННЫХ =============
DATABASE_PATH = os.getenv('DATABASE_PATH', 'bot.db')

# ============= НАСТРОЙКИ РАССЫЛКИ =============
MAILING_DELAY = float(os.getenv('MAILING_DELAY', '0.2'))  # секунд между сообщениями

# ============= ЛОГИРОВАНИЕ =============
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# ============= НАСТРОЙКИ СЕССИЙ =============
SESSIONS_DIR = os.getenv('SESSIONS_DIR', './sessions')

# ============= БЭКАПЫ =============
BACKUP_DIR = os.getenv('BACKUP_DIR', './backups')
AUTO_BACKUP = os.getenv('AUTO_BACKUP', 'True').lower() == 'true'
BACKUP_INTERVAL_HOURS = int(os.getenv('BACKUP_INTERVAL_HOURS', '24'))

# ============= ПРОВЕРКА ПОДПИСОК =============
CHECK_SUBSCRIPTION_ON_START = os.getenv('CHECK_SUBSCRIPTION_ON_START', 'True').lower() == 'true'

# ============= ПРОЧЕЕ =============
TRIAL_DAYS = int(os.getenv('TRIAL_DAYS', '3'))