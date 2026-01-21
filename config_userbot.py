import os

# API данные Telegram
API_ID = int(os.getenv('API_ID', '29648842'))
API_HASH = os.getenv('API_HASH', '0b3fe61f73c23c27870ab93212345678')

# Токен Manager бота
MANAGER_BOT_TOKEN = os.getenv('MANAGER_BOT_TOKEN', '7895008595:AAH4i8JVP9bkfMvH6R_iZKx9k4sKoGmTbMI')

# ID администратора
ADMIN_ID = int(os.getenv('ADMIN_ID', '8416385318'))

# Папка для сессий
SESSIONS_DIR = os.getenv('SESSIONS_DIR', './sessions')

# Создать папку если не существует
if not os.path.exists(SESSIONS_DIR):
    os.makedirs(SESSIONS_DIR)
    print(f"📁 Sessions directory created: {SESSIONS_DIR}")
else:
    print(f"📁 Sessions directory: {SESSIONS_DIR}")

# Обязательные каналы для подписки
REQUIRED_CHANNELS = [
    "@starbombnews",  # Публичный канал
]

# Ссылка на приватный канал
PRIVATE_CHANNEL_LINK = "https://t.me/+WpVwOyNErI8xZmNi"

# Тарифы подписок
SUBSCRIPTIONS = {
    'trial': {
        'name': '🆓 Пробная',
        'price': 0,
        'duration_days': 3,
        'daily_limit': 25,
        'max_messages': 3,
        'max_targets': 10,
        'description': 'Для тестирования бота'
    },
    'basic': {
        'name': '⭐ Базовая',
        'price': 499,
        'duration_days': 30,
        'daily_limit': 150,
        'max_messages': 5,
        'max_targets': 50,
        'description': 'Для небольших рассылок'
    },
    'pro': {
        'name': '💎 Продвинутая',
        'price': 1499,
        'duration_days': 30,
        'daily_limit': 1000,
        'max_messages': 10,
        'max_targets': 200,
        'description': 'Для активного использования'
    },
    'premium': {
        'name': '👑 Премиум',
        'price': 4999,
        'duration_days': 30,
        'daily_limit': 100000,
        'max_messages': 50,
        'max_targets': 10000,
        'description': 'Безлимитная рассылка'
    }
}

# Реквизиты для оплаты
PAYMENT_DETAILS = """
💳 Реквизиты для оплаты:

• Карта:2200153683704721
• ЮMoney: 4100118589897796
• USDT (TRC20): TD5EJBjQ3zM2SpgLCaBf4XptT7CoAFWPQr

После оплаты отправьте чек поддержке

"""