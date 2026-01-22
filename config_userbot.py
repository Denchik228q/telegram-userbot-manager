import os

# API данные Telegram
API_ID = int(os.getenv('API_ID', '32052311'))
API_HASH = os.getenv('API_HASH', '7f3947e9a7d911cc83793f21c18cb7c8')

# Токен Manager бота
MANAGER_BOT_TOKEN = os.getenv('MANAGER_BOT_TOKEN', '8457587045:AAHellpvMkkHeJLVzYMCjKrE6smt9ekBja0')

# ID администратора
ADMIN_ID = int(os.getenv('ADMIN_ID', '5688880070'))

# Папка для сессий
SESSIONS_DIR = os.getenv('SESSIONS_DIR', './sessions')

# Создать папку если не существует
if not os.path.exists(SESSIONS_DIR):
    os.makedirs(SESSIONS_DIR)
    print(f"📁 Sessions directory created: {SESSIONS_DIR}")

# Обязательные каналы для подписки
REQUIRED_CHANNELS = [
    "@starbombnews",
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

• По карте: 2200 1536 8370 4721
• ЮMoney: 4100118589897796
• USDT (TRC20): TD5EJBjQ3zM2SpgLCaBf4XptT7CoAFWPQr
За реквизитами более удобными вам, обратитесь в поддержку: /support

После оплаты отправьте чек поддержке
"""