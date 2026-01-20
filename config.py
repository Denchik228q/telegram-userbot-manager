import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

ROLE_ADMIN = "admin"
ROLE_SUPPORT = "support"
ROLE_USER = "user"

# Subscription plans
PLANS = {
    "trial": {
        "name": "🎁 Пробная версия",
        "price": 0,
        "daily_limit": 10,
        "max_contacts": 10,
        "features": [
            "✅ Одна бесплатная рассылка",
            "✅ До 10 контактов",
            "⚠️ Только один раз",
            "❌ После использования - платная подписка"
        ]
    },
    "free": {
        "name": "🆓 Бесплатный (закончилась пробная)",
        "price": 0,
        "daily_limit": 0,
        "features": [
            "❌ Рассылки недоступны",
            "💡 Оформите подписку для продолжения"
        ]
    },
    "pro": {
        "name": "💎 Профессиональный",
        "price": 799,
        "daily_limit": 2000,
        "duration_days": 30,
        "features": [
            "✅ 2000 сообщений в день",
            "✅ Неограниченно шаблонов",
            "✅ Неограниченно контактов",
            "✅ Приоритетная поддержка",
            "✅ Расширенная статистика",
            "✅ API доступ",
            "✅ Отложенные рассылки"
        ]
    },
    "unlimited": {
        "name": "🚀 Безлимитный",
        "price": 1999,
        "daily_limit": 999999,
        "duration_days": 30,
        "features": [
            "✅ Безлимитные рассылки",
            "✅ Все функции PRO",
            "✅ Персональный менеджер",
            "✅ Белый список IP"
        ]
    }
}

MAX_MESSAGES_PER_SECOND = 30
DEFAULT_DELAY = 0.1

MESSAGES = {
    "start": "👋 Добро пожаловать в бота для рассылок!\n\n🎁 Вы получили пробную версию!\n🎯 Лимит: одна рассылка до 10 контактов\n\n📋 Команды:\n/help - помощь\n/subscribe - тарифы\n/trial - информация о пробной версии",
    "trial_available": "🎁 У вас доступна пробная версия!\n\n✅ Одна бесплатная рассылка\n📨 До 10 контактов\n⚠️ Только одна попытка\n\n💡 После использования нужно будет оформить подписку",
    "trial_used": "⚠️ Пробная версия уже использована!\n\n💳 Оформите подписку для продолжения:\n/subscribe",
    "trial_warning": "⚠️ Это ваша единственная бесплатная рассылка!\n\nПосле использования будет доступна только платная подписка.\n\n❓ Продолжить?",
    "help_admin": "👑 Команды администратора:\n/add_support [user_id] - добавить поддержку\n/add_user [user_id] - добавить пользователя\n/remove_user [user_id] - удалить пользователя\n/users - список пользователей\n/stats - статистика бота\n/give_subscription [user_id] [plan] [days] - выдать подписку",
    "help_support": "🛠 Команды поддержки:\n/users - список пользователей\n/give_subscription [user_id] [plan] [days] - выдать подписку",
    "help_user": "📖 Команды пользователя:\n/subscribe - управление подпиской\n/limits - мои лимиты\n/referral - реферальная ссылка\n/trial - информация о пробной версии",
    "access_denied": "❌ Доступ запрещён",
    "not_registered": "❌ Вы не зарегистрированы.\n\nНажмите /start для регистрации",
    "limit_reached": "⛔ Достигнут дневной лимит сообщений!\n\n🔓 Увеличьте лимит: /subscribe",
    "subscription_expired": "⏰ Ваша подписка истекла!\n\n💳 Продлить: /subscribe",
    "no_trial": "❌ Пробная версия уже использована или недоступна\n\n💳 Оформите подписку: /subscribe"
}