# Telegram API (получи на https://my.telegram.org)
API_ID = 30648359  # ← ЗАМЕНИ НА СВОЙ
API_HASH = "1d1ccac98ded3ff15d050cabc65b8013"  # ← ЗАМЕНИ НА СВОЙ

# Бот для управления
MANAGER_BOT_TOKEN = "7555314078:AAE7aFR3X2J2qc42XgcsXCR8wQT3IvGzdn8"
ADMIN_ID = 7809505549

# Настройки безопасности
MAX_MESSAGES_PER_HOUR = 30
MIN_DELAY_BETWEEN_MESSAGES = 30
MAX_DELAY_BETWEEN_MESSAGES = 120

# Флудвейт защита
ENABLE_FLOOD_PROTECTION = True
FLOOD_SLEEP_THRESHOLD = 60

# Лимиты безопасности
MAX_TARGETS_PER_MAILING = 50
DAILY_MESSAGE_LIMIT = 200

# Предупреждения
SHOW_WARNINGS = True
REQUIRE_CONFIRMATION = True

# === ПОДПИСКИ ===
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

# ID администратора (твой Telegram ID)
ADMIN_ID = 8416385318  # ЗАМЕНИ НА СВОЙ!

# Платёжные данные (для приёма оплаты)
PAYMENT_TOKEN = "YOUR_PAYMENT_TOKEN"  # Получить на @BotFather -> /mybots -> Bot Settings -> Payments