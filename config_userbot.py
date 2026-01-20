import os

# API данные Telegram
API_ID = int(os.getenv('API_ID', '31287145'))
API_HASH = os.getenv('API_HASH', '7fc3ca5b8471a2ad219e72fbd7db6211')

# Токен Manager бота
MANAGER_BOT_TOKEN = os.getenv('MANAGER_BOT_TOKEN', '7895008595:AAH...')

# ID администратора
ADMIN_ID = int(os.getenv('ADMIN_ID', '8416385318'))

# Лимиты
DAILY_MESSAGE_LIMIT = 1000
FLOOD_SLEEP_THRESHOLD = 60

# Задержки между сообщениями (секунды)
MIN_DELAY_BETWEEN_MESSAGES = 30
MAX_DELAY_BETWEEN_MESSAGES = 120

# Тарифы подписок
SUBSCRIPTIONS = {
    'free': {
        'name': '🆓 Пробная',
        'daily_limit': 50,
        'max_targets': 10,
        'max_messages': 1,
        'price': 0,
        'duration_days': 7
    },
    'hobby': {
        'name': '🌟 Любительская',
        'daily_limit': 200,
        'max_targets': 50,
        'max_messages': 3,
        'price': 500,
        'duration_days': 30
    },
    'pro': {
        'name': '💎 PRO',
        'daily_limit': 1000,
        'max_targets': 200,
        'max_messages': 10,
        'price': 1500,
        'duration_days': 30
    },
    'unlimited': {
        'name': '🚀 Безлимит',
        'daily_limit': 999999,
        'max_targets': 1000,
        'max_messages': 50,
        'price': 5000,
        'duration_days': 30
    }
}