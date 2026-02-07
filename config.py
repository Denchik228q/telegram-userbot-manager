#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Конфигурация бота
"""

import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# ==================== ОСНОВНЫЕ НАСТРОЙКИ ====================

BOT_TOKEN = os.getenv('BOT_TOKEN')
API_ID = int(os.getenv('API_ID', '0'))
API_HASH = os.getenv('API_HASH', '')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

# База данных
DATABASE_PATH = os.getenv('DATABASE_PATH', 'bot_database.db')

# ==================== ПЛАТЕЖИ ====================

YOOKASSA_SHOP_ID = os.getenv('YOOKASSA_SHOP_ID', '')
YOOKASSA_SECRET_KEY = os.getenv('YOOKASSA_SECRET_KEY', '')

PAYMENT_METHODS = {
    'card': {
        'name': '💳 Банковская карта',
        'enabled': True
    },
    'yookassa': {
        'name': '🔵 ЮКassa',
        'enabled': bool(YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY)
    },
    'manual': {
        'name': '📱 Ручной перевод',
        'enabled': True
    }
}

# ==================== ТАРИФНЫЕ ПЛАНЫ ====================

SUBSCRIPTION_PLANS = {
    'trial': {
        'name': '🎁 Пробный',
        'price': 0,
        'days': 3,
        'description': 'Бесплатный пробный период на 3 дня',
        'limits': {
            'accounts': 1,
            'mailings_per_day': 3,
            'targets_per_mailing': 10,
            'schedule_tasks': 0
        }
    },
    'basic': {
        'name': '📦 Базовый',
        'price': 490,
        'days': 30,
        'description': 'Для начинающих пользователей',
        'limits': {
            'accounts': 3,
            'mailings_per_day': 10,
            'targets_per_mailing': 100,
            'schedule_tasks': 2
        }
    },
    'pro': {
        'name': '🚀 Профи',
        'price': 990,
        'days': 30,
        'description': 'Для активных пользователей',
        'limits': {
            'accounts': 10,
            'mailings_per_day': 50,
            'targets_per_mailing': 500,
            'schedule_tasks': 10
        }
    },
    'premium': {
        'name': '💎 Премиум',
        'price': 1990,
        'days': 30,
        'description': 'Без ограничений',
        'limits': {
            'accounts': -1,  # -1 = безлимит
            'mailings_per_day': -1,
            'targets_per_mailing': -1,
            'schedule_tasks': -1
        }
    }
}

# ==================== ТЕКСТЫ БОТА ====================

TEXTS = {
    'welcome': """
👋 *Добро пожаловать в Manager Bot!*

🤖 Я помогу вам управлять рассылками через Telegram.

📊 *Ваша подписка:*
• Тариф: {subscription}
• Осталось дней: {days_left}

💡 *Возможности:*
• Подключение нескольких аккаунтов
• Массовые рассылки
• Планировщик автоматических рассылок
• Статистика и история

Используйте меню ниже для начала работы 👇
""",
    
    'help': """
📖 *Справка по использованию бота*

*📱 Мои аккаунты*
Подключение и управление вашими Telegram аккаунтами

*📨 Создать рассылку*
Массовая отправка сообщений по списку

*⏰ Планировщик*
Автоматические рассылки по расписанию

*📜 История*
Просмотр всех ваших рассылок

*💎 Тарифы*
Информация о тарифных планах

*ℹ️ Помощь*
Это сообщение

Нужна помощь? Напишите @your_support
""",
    
    'no_accounts': """
❌ *У вас нет подключенных аккаунтов*

Для создания рассылок необходимо подключить хотя бы один Telegram аккаунт.

Нажмите *📱 Мои аккаунты* → *➕ Подключить аккаунт*
"""
}

# ==================== НАСТРОЙКИ БЭКАПОВ ====================

BACKUP_ENABLED = os.getenv('BACKUP_ENABLED', 'true').lower() == 'true'
BACKUP_INTERVAL_HOURS = int(os.getenv('BACKUP_INTERVAL_HOURS', '6'))
BACKUP_CHAT_ID = int(os.getenv('BACKUP_CHAT_ID', os.getenv('ADMIN_ID', '0')))

# ==================== НАСТРОЙКИ РАССЫЛОК ====================

# Задержка между отправками (секунды)
SEND_DELAY_MIN = 3
SEND_DELAY_MAX = 5

# Лимиты по умолчанию
DEFAULT_LIMITS = {
    'accounts': 1,
    'mailings_per_day': 3,
    'targets_per_mailing': 10,
    'schedule_tasks': 0
}