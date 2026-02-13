"""
Конфигурация бота
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ==================== TELEGRAM BOT ====================
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN not found in environment variables!")

ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
if ADMIN_ID == 0:
    raise ValueError("❌ ADMIN_ID not found in environment variables!")

# ==================== TELEGRAM API ====================
API_ID = int(os.getenv('API_ID', '0'))
API_HASH = os.getenv('API_HASH')

if API_ID == 0 or not API_HASH:
    raise ValueError("❌ API_ID or API_HASH not found! Get from https://my.telegram.org")

# ==================== DATABASE ====================
DATABASE_URL = os.getenv('DATABASE_URL', 'bot_database.db')

# ==================== PATHS ====================
SESSIONS_DIR = 'sessions'
BACKUPS_DIR = 'backups'
LOGS_DIR = 'logs'

# Создаём директории если их нет
for directory in [SESSIONS_DIR, BACKUPS_DIR, LOGS_DIR]:
    os.makedirs(directory, exist_ok=True)

# ==================== SUBSCRIPTION PLANS ====================
SUBSCRIPTION_PLANS = {
    'trial': {
        'name': 'Пробный',
        'price': 0,
        'days': 7,
        'description': 'Тестовый период для новых пользователей',
        'features': [
            '✅ 1 аккаунт',
            '✅ 3 рассылки в день',
            '✅ До 50 получателей',
            '⏱ 7 дней доступа'
        ],
        'limits': {
            'accounts': 1,
            'mailings_per_day': 3,
            'messages_per_mailing': 50
        }
    },
    'basic': {
        'name': 'Базовый',
        'price': 490,
        'days': 30,
        'description': 'Идеальный старт для малого бизнеса',
        'features': [
            '✅ До 3 аккаунтов',
            '✅ 10 рассылок в день',
            '✅ До 500 получателей',
            '✅ Планировщик рассылок',
            '✅ История рассылок',
            '⏱ 30 дней доступа'
        ],
        'limits': {
            'accounts': 3,
            'mailings_per_day': 10,
            'messages_per_mailing': 500
        }
    },
    'pro': {
        'name': 'Профи',
        'price': 1990,
        'days': 30,
        'description': 'Для профессионалов и агентств',
        'features': [
            '✅ До 10 аккаунтов',
            '✅ 50 рассылок в день',
            '✅ До 5000 получателей',
            '✅ Планировщик с повторами',
            '✅ Полная статистика',
            '✅ Приоритетная поддержка',
            '⏱ 30 дней доступа'
        ],
        'limits': {
            'accounts': 10,
            'mailings_per_day': 50,
            'messages_per_mailing': 5000
        }
    },
    'premium': {
        'name': 'Премиум',
        'price': 4990,
        'days': 30,
        'description': 'Максимальные возможности без ограничений',
        'features': [
            '✅ Неограниченно аккаунтов',
            '✅ Неограниченно рассылок',
            '✅ Неограниченно получателей',
            '✅ Продвинутый планировщик',
            '✅ Детальная аналитика',
            '✅ VIP поддержка 24/7',
            '✅ API доступ',
            '⏱ 30 дней доступа'
        ],
        'limits': {
            'accounts': -1,  # -1 = unlimited
            'mailings_per_day': -1,
            'messages_per_mailing': -1
        }
    }
}

# ==================== PLAN EMOJIS ====================
PLAN_EMOJI = {
    'trial': '🆓',
    'basic': '💼',
    'pro': '🚀',
    'premium': '👑'
}

# ==================== PAYMENT METHODS ====================
PAYMENT_METHODS = {
    'card': {
        'name': '💳 Банковская карта',
        'description': 'Оплата картой через защищённый платёжный шлюз',
        'enabled': True
    },
    'manual': {
        'name': '💰 Ручной перевод',
        'description': 'Перевод на карту/счёт с ручным подтверждением',
        'enabled': True,
        'details': '''
💳 **Реквизиты для оплаты:**

**Альфа:** 2200 1536 8370 4721
**Тинькофф:** 2200 7020 4134 1848

📝 **Инструкция:**
1. Переведите точную сумму
2. Нажмите кнопку "Я оплатил"
3. Дождитесь подтверждения (обычно до 30 минут)

⚠️ В комментарии к переводу укажите ваш Telegram ID: `{user_id}`
        '''
    },
    'crypto': {
        'name': '₿ Криптовалюта',
        'description': 'Оплата в BTC, ETH, USDT',
        'enabled': False  # Отключено пока
    }
}

# ==================== MAILING SETTINGS ====================
MAILING_SETTINGS = {
    'min_delay': 5,  # Минимальная задержка между сообщениями (сек)
    'max_delay': 10,  # Максимальная задержка
    'messages_per_hour': 50000,  # Макс сообщений в час с одного аккаунта
    'retry_attempts': 3,  # Попытки повтора при ошибке
    'flood_wait_multiplier': 1.5,  # Множитель при флудвейте
}

# ==================== LOGGING ====================
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_FILE = os.path.join(LOGS_DIR, 'bot.log')

# ==================== BACKUP ====================
BACKUP_INTERVAL = 24 * 60 * 60  # 24 часа в секундах
MAX_BACKUPS = 7  # Хранить последние 7 бэкапов

# ==================== FEATURES FLAGS ====================
FEATURES = {
    'scheduler': True,
    'analytics': True,
    'auto_backup': True,
    'admin_panel': True,
    'payment_system': True,
}

# ==================== MESSAGES ====================
WELCOME_MESSAGE = """
👋 **Добро пожаловать в StarBomb Bot!**

🤖 Это профессиональный бот для массовых рассылок в Telegram.

**Ваш текущий тариф:** {subscription}
**Осталось дней:** {days_left}

📊 **Доступные функции:**
• Управление Telegram-аккаунтами
• Создание и запуск рассылок
• Планировщик автоматических рассылок
• Детальная статистика и история
• Гибкая система тарифов

💡 Нажмите на кнопки ниже для начала работы!
"""

ERROR_MESSAGE = """
❌ **Произошла ошибка**

Пожалуйста, попробуйте позже или обратитесь в поддержку.

Код ошибки: `{error_code}`
"""

SUCCESS_MESSAGE = "✅ {message}"

# ==================== DATABASE SETTINGS ====================
SQLITE_TIMEOUT = 30.0  # Таймаут для блокировки БД (секунды)
SQLITE_BUSY_TIMEOUT = 30000  # Busy timeout (миллисекунды)
SQLITE_JOURNAL_MODE = 'WAL'  # Write-Ahead Logging