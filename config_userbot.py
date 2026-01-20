import os

# API данные Telegram
API_ID = int(os.getenv('API_ID', '29648842'))
API_HASH = os.getenv('API_HASH', '0b3fe61f73c23c27870ab93212345678')

# Токен Manager бота
MANAGER_BOT_TOKEN = os.getenv('MANAGER_BOT_TOKEN', '7895008595:AAH...')

# ID администратора
ADMIN_ID = int(os.getenv('ADMIN_ID', '8416385318'))

# Обязательные каналы для подписки
REQUIRED_CHANNELS = [
    "starbombnews",           # Первый канал (публичный)
    "+WpVwOyNErI8xZmNi"       # Второй канал (приватный)
]

# Ссылки на каналы для кнопок
CHANNEL_LINKS = {
    "starbombnews": "https://t.me/starbombnews",
    "+WpVwOyNErI8xZmNi": "https://t.me/+WpVwOyNErI8xZmNi"
}

# Лимиты
DAILY_MESSAGE_LIMIT = 1000
FLOOD_SLEEP_THRESHOLD = 60

# Задержки между сообщениями (секунды)
# Увеличь эти значения при большом наплыве пользователей
MIN_DELAY_BETWEEN_MESSAGES = 60    # 1 минута (безопасно)
MAX_DELAY_BETWEEN_MESSAGES = 180   # 3 минуты (безопасно)

# Для более агрессивной рассылки (РИСКОВАННО!):
# MIN_DELAY_BETWEEN_MESSAGES = 30
# MAX_DELAY_BETWEEN_MESSAGES = 90

# Для максимальной безопасности:
# MIN_DELAY_BETWEEN_MESSAGES = 120
# MAX_DELAY_BETWEEN_MESSAGES = 300

# Тарифы подписок
SUBSCRIPTIONS = {
    'free': {
        'name': '🆓 Пробная',
        'daily_limit': 25,
        'max_targets': 5,
        'max_messages': 1,
        'price': 0,
        'duration_days': 7,
        'one_time_only': True  # Можно использовать только один раз
    },
    'hobby': {
        'name': '🌟 Любительская',
        'daily_limit': 150,
        'max_targets': 50,
        'max_messages': 3,
        'price': 499,
        'duration_days': 30,
        'one_time_only': False
    },
    'pro': {
        'name': '💎 PRO',
        'daily_limit': 1000,
        'max_targets': 150,
        'max_messages': 10,
        'price': 1499,
        'duration_days': 30,
        'one_time_only': False
    },
    'unlimited': {
        'name': '🚀 Безлимит',
        'daily_limit': 100000,
        'max_targets': 1000,
        'max_messages': 100,
        'price': 4999,
        'duration_days': 30,
        'one_time_only': False
    }
}