import asyncio
import logging
from datetime import datetime, timedelta
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, ContextTypes, filters, PreCheckoutQueryHandler
from telegram.error import TelegramError
from database import Database
from config import *

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

SELECTING_ACTION, ADD_CONTACTS, ADD_MESSAGE, SET_DELAY, CONFIRM_MAILING, ADD_TEMPLATE_NAME, ADD_TEMPLATE_CONTENT, ADD_USER_ID, SELECT_TEMPLATE, SELECTING_PLAN, AWAITING_PAYMENT, MULTI_SEND_CONTACT, MULTI_SEND_COUNT = range(13)
db = Database()

async def check_access(update: Update, required_roles=None):
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    if not user or not user["is_active"]:
        if update.message:
            await update.message.reply_text(MESSAGES["not_registered"])
        elif update.callback_query:
            await update.callback_query.answer(MESSAGES["not_registered"], show_alert=True)
        return False
    if required_roles and user["role"] not in required_roles:
        if update.message:
            await update.message.reply_text(MESSAGES["access_denied"])
        elif update.callback_query:
            await update.callback_query.answer(MESSAGES["access_denied"], show_alert=True)
        return False
    
    # Проверка подписки
    await db.check_subscription_expired(user_id)
    
    return True

async def check_limits(user_id, messages_count):
    """Проверка лимитов перед рассылкой"""
    limits = await db.get_user_limits(user_id)
    if not limits:
        return False, "❌ Ошибка получения лимитов"
    
    subscription_type = limits["subscription_type"]
    messages_sent_today = limits["messages_sent_today"]
    plan = PLANS.get(subscription_type, PLANS["free"])
    
    if messages_sent_today + messages_count > plan["daily_limit"]:
        remaining = plan["daily_limit"] - messages_sent_today
        return False, (
            f"⛔ Недостаточно лимита!\n\n"
            f"📊 Доступно: {remaining} сообщений\n"
            f"📨 Требуется: {messages_count}\n\n"
            f"💳 Увеличьте лимит: /subscribe"
        )
    
    return True, None

def get_main_keyboard(role):
    keyboard = [
        [InlineKeyboardButton("📮 Новая рассылка", callback_data="new_mailing")],
        [InlineKeyboardButton("📋 Мои рассылки", callback_data="my_mailings")],
        [InlineKeyboardButton("📝 Шаблоны", callback_data="templates")],
        [InlineKeyboardButton("📇 Контакты", callback_data="contacts")],
        [InlineKeyboardButton("💬 Поддержка", callback_data="support")]
    ]
    if role in [ROLE_ADMIN, ROLE_SUPPORT]:
        keyboard.append([InlineKeyboardButton("👥 Пользователи", callback_data="users")])
    if role == ROLE_ADMIN:
        keyboard.append([InlineKeyboardButton("📊 Статистика", callback_data="stats")])
    return InlineKeyboardMarkup(keyboard)

def get_main_keyboard(role):
    keyboard = [
        [InlineKeyboardButton("Новая рассылка", callback_data="new_mailing")],
        [InlineKeyboardButton("Мои рассылки", callback_data="my_mailings")],
        [InlineKeyboardButton("Шаблоны", callback_data="templates")],
        [InlineKeyboardButton("Мои контакты", callback_data="contacts")],
        [InlineKeyboardButton("💬 Поддержка", callback_data="support")]
    ]
    if role in [ROLE_ADMIN, ROLE_SUPPORT]:
        keyboard.append([InlineKeyboardButton("Users", callback_data="users")])
    if role == ROLE_ADMIN:
        keyboard.append([InlineKeyboardButton("Statistics", callback_data="stats")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    user = await db.get_user(user_id)
    
    # Проверка реферального кода
    if context.args and not user:
        referral_code = context.args[0]
        referrer_id = await db.use_referral_code(user_id, referral_code)
        if referrer_id:
            await context.bot.send_message(
                chat_id=referrer_id,
                text="🎉 По вашей реферальной ссылке зарегистрировался новый пользователь!\n+100 бесплатных сообщений в подарок!"
            )
    
    if not user:
        if user_id == ADMIN_ID:
            await db.add_user(user_id, username, ROLE_ADMIN)
            # Админу сразу безлимит
            await db.db.execute(
                "UPDATE users SET subscription_type = 'unlimited', trial_used = 1 WHERE user_id = ?",
                (user_id,)
            )
            await db.db.commit()
            role = ROLE_ADMIN
            subscription_type = "unlimited"
        else:
            await db.add_user(user_id, username, ROLE_USER)
            role = ROLE_USER
            subscription_type = "trial"
            await db.generate_referral_code(user_id)
    else:
        role = user["role"]
        subscription_type = user.get("subscription_type", "free")
        await db.check_subscription_expired(user_id)
    
    # Проверка пробной версии
    trial_available = await db.check_trial_available(user_id)
    
    if trial_available:
        welcome_text = (
            f"👋 Добро пожаловать в бота для массовых рассылок!\n\n"
            f"🎁 Вам доступна ПРОБНАЯ версия:\n"
            f"✅ Одна бесплатная рассылка\n"
            f"📨 До 10 контактов\n"
            f"⚠️ Только один раз!\n\n"
            f"💡 После использования потребуется оформить подписку\n\n"
            f"📋 Команды:\n"
            f"/trial - подробнее о пробной версии\n"
            f"/subscribe - посмотреть тарифы\n"
            f"/help - помощь"
        )
    else:
        plan_info = PLANS.get(subscription_type, PLANS["free"])
        if subscription_type == "free":
            welcome_text = (
                f"👋 Добро пожаловать!\n\n"
                f"⚠️ Пробная версия использована\n\n"
                f"💳 Оформите подписку для продолжения работы:\n"
                f"/subscribe - доступные тарифы\n\n"
                f"📋 Другие команды:\n"
                f"/help - помощь\n"
                f"/referral - пригласите друзей и получите бонусы"
            )
        else:
            daily_limit = plan_info["daily_limit"]
            welcome_text = (
                f"👋 Добро пожаловать!\n\n"
                f"📊 Ваш тариф: {plan_info['name']}\n"
                f"📨 Лимит в день: {daily_limit} сообщений\n\n"
                f"📋 Команды:\n"
                f"/help - помощь\n"
                f"/subscribe - управление подпиской\n"
                f"/limits - мои лимиты\n"
                f"/referral - реферальная программа"
            )
    
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(role))

async def trial_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    trial_available = await db.check_trial_available(user_id)
    trial_stats = await db.get_trial_stats(user_id)
    
    if trial_available:
        text = (
            "🎁 Пробная версия ДОСТУПНА!\n\n"
            "✅ Одна бесплатная рассылка\n"
            "📨 До 10 контактов\n"
            "⚠️ Можно использовать только ОДИН РАЗ\n\n"
            "💡 После использования будут доступны только платные тарифы\n\n"
            "📋 Начать: нажмите «📮 Новая рассылка»\n"
            "💳 Тарифы: /subscribe"
        )
    elif trial_stats and trial_stats["trial_used"]:
        text = (
            "⚠️ Пробная версия УЖЕ ИСПОЛЬЗОВАНА\n\n"
            "💳 Для продолжения работы оформите подписку:\n"
            "/subscribe - посмотреть тарифы\n\n"
            "🎁 Пригласите друзей и получите бонусы:\n"
            "/referral - реферальная программа"
        )
    else:
        text = "❌ Информация о пробной версии недоступна"
    
    await update.message.reply_text(text)

async def subscribe_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user_id = query.from_user.id
    else:
        user_id = update.effective_user.id
    
    user = await db.get_user(user_id)
    current_plan = user.get("subscription_type", "free")
    subscription_until = user.get("subscription_until")
    
    text = "💳 Управление подпиской\n\n"
    text += f"📊 Текущий тариф: {PLANS[current_plan]['name']}\n"
    
    if subscription_until:
        expires = datetime.fromisoformat(subscription_until)
        days_left = (expires - datetime.now()).days
        text += f"⏰ Действует до: {expires.strftime('%d.%m.%Y')}\n"
        text += f"📅 Осталось дней: {days_left}\n\n"
    else:
        text += "\n"
    
    text += "🎯 Выберите тариф:\n\n"
    
    keyboard = []
    for plan_id, plan in PLANS.items():
        if plan_id == "free":
            continue
        features = "\n".join(plan["features"][:3])
        button_text = f"{plan['name']} - {plan['price']}₽/мес"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"plan_{plan_id}")])
    
    keyboard.append([InlineKeyboardButton("❓ Сравнить тарифы", callback_data="compare_plans")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
    
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def compare_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = "📊 Сравнение тарифов:\n\n"
    
    for plan_id, plan in PLANS.items():
        text += f"{plan['name']}\n"
        if plan['price'] > 0:
            text += f"💰 Цена: {plan['price']}₽/месяц\n"
        else:
            text += f"💰 Цена: Бесплатно\n"
        text += f"📨 Лимит: {plan['daily_limit']} сообщений/день\n"
        text += "Возможности:\n"
        for feature in plan['features']:
            text += f"  {feature}\n"
        text += "\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад к тарифам", callback_data="subscribe")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def select_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    plan_id = query.data.split("_")[1]
    plan = PLANS[plan_id]
    
    context.user_data["selected_plan"] = plan_id
    
    text = f"📋 Выбран тариф: {plan['name']}\n\n"
    text += f"💰 Стоимость: {plan['price']}₽\n"
    text += f"📅 Период: {plan['duration_days']} дней\n\n"
    text += "Возможности:\n"
    for feature in plan['features']:
        text += f"{feature}\n"
    text += "\n💳 Выберите способ оплаты:"
    
    keyboard = [
        [InlineKeyboardButton("⭐ Telegram Stars", callback_data=f"pay_stars_{plan_id}")],
        [InlineKeyboardButton("💳 ЮMoney", callback_data=f"pay_yoomoney_{plan_id}")],
        [InlineKeyboardButton("₿ Криптовалюта", callback_data=f"pay_crypto_{plan_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="subscribe")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def process_payment_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    plan_id = query.data.split("_")[2]
    plan = PLANS[plan_id]
    
    # Telegram Stars оплата
    title = f"Подписка {plan['name']}"
    description = f"Подписка на {plan['duration_days']} дней"
    payload = f"subscription_{plan_id}_{query.from_user.id}"
    currency = "XTR"  # Telegram Stars
    prices = [LabeledPrice(plan['name'], plan['price'] * 100)]  # в копейках
    
    await context.bot.send_invoice(
        chat_id=query.from_user.id,
        title=title,
        description=description,
        payload=payload,
        provider_token="",  # Для Stars не нужен
        currency=currency,
        prices=prices
    )
    
    await query.edit_message_text("💫 Счёт на оплату отправлен! Проверьте сообщения выше.")

async def process_payment_yoomoney(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    plan_id = query.data.split("_")[2]
    plan = PLANS[plan_id]
    
    # Генерация ссылки на оплату (нужен кошелёк ЮMoney)
    # Здесь упрощённый вариант - просто инструкция
    
    text = (
        f"💳 Оплата через ЮMoney\n\n"
        f"📋 Тариф: {plan['name']}\n"
        f"💰 Сумма: {plan['price']}₽\n\n"
        f"Переведите {plan['price']}₽ на кошелёк:\n"
        f"🔗 410011234567890\n\n"
        f"В комментарии укажите: USER_{query.from_user.id}\n\n"
        f"После оплаты нажмите кнопку ниже:"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Я оплатил", callback_data=f"confirm_payment_{plan_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="subscribe")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def process_payment_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    plan_id = query.data.split("_")[2]
    plan = PLANS[plan_id]
    
    text = (
        f"₿ Оплата криптовалютой\n\n"
        f"📋 Тариф: {plan['name']}\n"
        f"💰 Сумма: {plan['price']}₽ (~$3.3 USDT)\n\n"
        f"Адрес для оплаты (USDT TRC20):\n"
        f"`TXmBj1234567890abcdefg`\n\n"
        f"После отправки нажмите:"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Отправил криптовалюту", callback_data=f"confirm_payment_{plan_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="subscribe")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    plan_id = query.data.split("_")[2]
    user_id = query.from_user.id
    
    # Создание записи о платеже (ожидает подтверждения админом)
    import uuid
    transaction_id = str(uuid.uuid4())
    plan = PLANS[plan_id]
    
    await db.create_payment(
        user_id=user_id,
        amount=plan['price'],
        currency="RUB",
        payment_method="manual",
        transaction_id=transaction_id
    )
    
    # Уведомление админу
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"💰 Новая заявка на оплату!\n\n"
             f"👤 Пользователь: {user_id}\n"
             f"📋 Тариф: {plan['name']}\n"
             f"💵 Сумма: {plan['price']}₽\n"
             f"🔑 ID транзакции: `{transaction_id}`\n\n"
             f"Подтвердить: /confirm_payment {transaction_id}",
        parse_mode="Markdown"
    )
    
    await query.edit_message_text(
        "✅ Заявка на оплату отправлена!\n\n"
        "⏳ Ожидайте подтверждения (обычно до 10 минут)\n"
        "📧 Вы получите уведомление после активации подписки"
    )

async def confirm_payment_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /confirm_payment [transaction_id]")
        return
    
    transaction_id = context.args[0]
    
    # Обновление статуса платежа
    await db.update_payment_status(transaction_id, "completed")
    
    # Получение информации о платеже
    # Здесь упрощённо - нужно получить user_id и plan из БД
    # Допустим уже знаем:
    # user_id = ... из БД
    # plan_id = ... из БД
    
    await update.message.reply_text(
        f"✅ Платеж {transaction_id} подтверждён!\n"
        f"Подписка активирована."
    )

async def give_subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /give_subscription [user_id] [plan] [days]\n\n"
            "Планы: basic, pro, unlimited\n"
            "Пример: /give_subscription 123456789 pro 30"
        )
        return
    
    try:
        target_user_id = int(context.args[0])
        plan = context.args[1]
        days = int(context.args[2]) if len(context.args) > 2 else 30
        
        if plan not in ["basic", "pro", "unlimited"]:
            await update.message.reply_text("❌ Неверный план. Доступны: basic, pro, unlimited")
            return
        
        from datetime import timedelta
        expires_at = (datetime.now() + timedelta(days=days)).isoformat()
        
        await db.create_subscription(
            user_id=target_user_id,
            plan=plan,
            price=0,
            payment_method="admin_gift",
            transaction_id=f"admin_{target_user_id}_{datetime.now().timestamp()}",
            expires_at=expires_at
        )
        
        plan_name = PLANS[plan]['name']
        await update.message.reply_text(
            f"✅ Подписка выдана!\n\n"
            f"👤 Пользователь: {target_user_id}\n"
            f"📋 Тариф: {plan_name}\n"
            f"📅 Срок: {days} дней"
        )
        
        # Уведомление пользователю
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"🎉 Вам выдана подписка!\n\n"
                     f"📋 Тариф: {plan_name}\n"
                     f"📅 Срок: {days} дней\n\n"
                     f"Приятного использования!"
            )
        except:
            pass
            
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Проверьте user_id и количество дней")

async def limits_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    limits = await db.get_user_limits(user_id)
    
    if not limits:
        await update.message.reply_text("❌ Информация недоступна")
        return
    
    subscription_type = limits["subscription_type"]
    messages_sent_today = limits["messages_sent_today"]
    plan = PLANS.get(subscription_type, PLANS["free"])
    
    remaining = plan["daily_limit"] - messages_sent_today
    percentage = (messages_sent_today / plan["daily_limit"]) * 100
    
    # Прогресс-бар
    filled = int(percentage / 10)
    bar = "█" * filled + "░" * (10 - filled)
    
    text = (
        f"📊 Ваши лимиты\n\n"
        f"📋 Тариф: {plan['name']}\n"
        f"📨 Дневной лимит: {plan['daily_limit']}\n"
        f"✅ Отправлено сегодня: {messages_sent_today}\n"
        f"🔓 Осталось: {remaining}\n\n"
        f"Использовано: {bar} {percentage:.1f}%\n\n"
    )
    
    if subscription_type == "free":
        text += "💡 Увеличьте лимит: /subscribe"
    
    await update.message.reply_text(text)

async def referral_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    referral_code = await db.get_referral_code(user_id)
    
    if not referral_code:
        referral_code = await db.generate_referral_code(user_id)
    
    referrals_count = await db.get_referrals_count(user_id)
    
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={referral_code}"
    
    text = (
        f"🎁 Реферальная программа\n\n"
        f"👥 Приглашённых пользователей: {referrals_count}\n"
        f"🎉 Бонус за каждого: +100 сообщений\n\n"
        f"📎 Ваша реферальная ссылка:\n"
        f"`{referral_link}`\n\n"
        f"Поделитесь ссылкой с друзьями и получайте бонусы!"
    )
    
    keyboard = [[InlineKeyboardButton("📤 Поделиться", url=f"https://t.me/share/url?url={referral_link}&text=Попробуй этого бота для рассылок!")]]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Связаться с поддержкой"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Без имени"
    
    if context.args:
        # Пользователь отправляет сообщение поддержке
        message = " ".join(context.args)
        
        # Отправка админу/поддержке
        support_text = (
            f"💬 Новое сообщение в поддержку\n\n"
            f"👤 От: {username} (ID: {user_id})\n"
            f"📝 Сообщение:\n{message}\n\n"
            f"Ответить: /reply {user_id} [текст]"
        )
        
        await context.bot.send_message(chat_id=ADMIN_ID, text=support_text)
        
        await update.message.reply_text(
            "✅ Ваше сообщение отправлено в поддержку!\n\n"
            "⏰ Мы ответим вам в ближайшее время."
        )
    else:
        # Инструкция как написать в поддержку
        text = (
            "💬 Связаться с поддержкой\n\n"
            "📝 Чтобы отправить сообщение:\n"
            "/support [ваше сообщение]\n\n"
            "Пример:\n"
            "/support Не могу создать рассылку, помогите!\n\n"
            "📧 Или напишите напрямую:\n"
            f"@{(await context.bot.get_me()).username}"
        )
        
        keyboard = [
            [InlineKeyboardButton("📞 Написать в поддержку", url=f"https://t.me/{(await context.bot.get_me()).username}?start=support")]
        ]
        
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ пользователю от поддержки/админа"""
    if update.effective_user.id not in [ADMIN_ID]:
        # Проверка роли поддержки
        user = await db.get_user(update.effective_user.id)
        if not user or user["role"] not in [ROLE_ADMIN, ROLE_SUPPORT]:
            await update.message.reply_text("❌ Доступ запрещён")
            return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /reply [user_id] [текст]\n\n"
            "Пример:\n"
            "/reply 123456789 Здравствуйте! Мы проверили вашу проблему..."
        )
        return
    
    try:
        target_user_id = int(context.args[0])
        message = " ".join(context.args[1:])
        
        # Отправка пользователю
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"💬 Ответ от поддержки:\n\n{message}\n\n"
                 f"Задать ещё вопрос: /support [текст]"
        )
        
        await update.message.reply_text(
            f"✅ Ответ отправлен пользователю {target_user_id}"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Неверный ID пользователя")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка отправки: {e}")

async def support_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню поддержки через кнопку"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    username = query.from_user.username or "Без имени"
    
    text = (
        "💬 Поддержка\n\n"
        "Чтобы написать в поддержку, используйте команду:\n"
        "/support [ваше сообщение]\n\n"
        "Пример:\n"
        "/support У меня не работает рассылка\n\n"
        "⏰ Мы ответим вам в течение 24 часов"
    )
    
    keyboard = [
        [InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_menu")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    if not user:
        await update.message.reply_text(MESSAGES["not_registered"])
        return
    
    role = user["role"]
    if role == ROLE_ADMIN:
        help_text = (
            "👑 Команды администратора:\n\n"
            "👥 Управление пользователями:\n"
            "/add_support [user_id] - добавить поддержку\n"
            "/add_user [user_id] - добавить пользователя\n"
            "/remove_user [user_id] - удалить пользователя\n"
            "/users - список всех пользователей\n\n"
            "💳 Подписки:\n"
            "/give_subscription [user_id] [plan] [days] - выдать подписку\n\n"
            "💬 Поддержка:\n"
            "/reply [user_id] [текст] - ответить пользователю\n\n"
            "📊 Аналитика:\n"
            "/stats - статистика бота\n\n"
            "🎁 Реферальная программа:\n"
            "/referral - реферальная ссылка\n\n"
            "❓ Другое:\n"
            "/trial - информация о пробной версии\n"
            "/limits - мои лимиты\n"
            "/support [текст] - написать в поддержку"
        )
    elif role == ROLE_SUPPORT:
        help_text = (
            "🛠 Команды поддержки:\n\n"
            "👥 Пользователи:\n"
            "/users - список пользователей\n\n"
            "💳 Подписки:\n"
            "/give_subscription [user_id] [plan] [days] - выдать подписку\n\n"
            "💬 Поддержка:\n"
            "/reply [user_id] [текст] - ответить пользователю\n\n"
            "❓ Другое:\n"
            "/referral - реферальная программа\n"
            "/limits - мои лимиты"
        )
    else:
        help_text = (
            "📖 Команды пользователя:\n\n"
            "📮 Рассылки:\n"
            "Используйте кнопки в главном меню\n\n"
            "💳 Подписка:\n"
            "/subscribe - управление подпиской\n"
            "/limits - мои лимиты\n"
            "/trial - информация о пробной версии\n\n"
            "🎁 Бонусы:\n"
            "/referral - реферальная программа\n\n"
            "💬 Помощь:\n"
            "/support [текст] - написать в поддержку\n\n"
            "Пример:\n"
            "/support Не могу создать рассылку"
        )
    
    await update.message.reply_text(help_text)

async def add_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, [ROLE_ADMIN]):
        return
    if not context.args:
        await update.message.reply_text("Использование: /add_support [user_id]")
        return
    try:
        new_user_id = int(context.args[0])
        username = context.args[1] if len(context.args) > 1 else None
        if await db.add_user(new_user_id, username, ROLE_SUPPORT):
            await update.message.reply_text(f"✅ Пользователь {new_user_id} добавлен как поддержка")
        else:
            await db.update_user_role(new_user_id, ROLE_SUPPORT)
            await update.message.reply_text(f"✅ Роль пользователя {new_user_id} изменена на поддержку")
    except ValueError:
        await update.message.reply_text("❌ Неверный формат user_id")

async def add_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, [ROLE_ADMIN]):
        return
    if not context.args:
        await update.message.reply_text("Usage: /add_support [user_id]")
        return
    try:
        new_user_id = int(context.args[0])
        username = context.args[1] if len(context.args) > 1 else None
        if await db.add_user(new_user_id, username, ROLE_SUPPORT):
            await update.message.reply_text(f"User {new_user_id} added as support")
        else:
            await db.update_user_role(new_user_id, ROLE_SUPPORT)
            await update.message.reply_text(f"User {new_user_id} role changed to support")
    except ValueError:
        await update.message.reply_text("Invalid user_id format")

async def add_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, [ROLE_ADMIN, ROLE_SUPPORT]):
        return
    if not context.args:
        await update.message.reply_text("Использование: /add_user [user_id]")
        return
    try:
        new_user_id = int(context.args[0])
        username = context.args[1] if len(context.args) > 1 else None
        if await db.add_user(new_user_id, username, ROLE_USER):
            await update.message.reply_text(f"✅ Пользователь {new_user_id} добавлен")
        else:
            await update.message.reply_text(f"⚠️ Пользователь {new_user_id} уже существует")
    except ValueError:
        await update.message.reply_text("❌ Неверный формат user_id")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, [ROLE_ADMIN]):
        return
    if not context.args:
        await update.message.reply_text("Использование: /remove_user [user_id]")
        return
    try:
        user_id = int(context.args[0])
        await db.deactivate_user(user_id)
        await update.message.reply_text(f"✅ Пользователь {user_id} деактивирован")
    except ValueError:
        await update.message.reply_text("❌ Неверный формат user_id")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, [ROLE_ADMIN, ROLE_SUPPORT]):
        return
    users = await db.get_all_users()
    if not users:
        await update.message.reply_text("👥 Пользователи не найдены")
        return
    text = "📋 Список пользователей:\n\n"
    for user in users:
        status = "✅ Активен" if user["is_active"] else "❌ Неактивен"
        username = f"@{user['username']}" if user["username"] else "Без имени"
        text += f"{status} | ID: {user['user_id']} | {username} | Роль: {user['role']}\n"
    await update.message.reply_text(text)

async def users_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not await check_access(update, [ROLE_ADMIN, ROLE_SUPPORT]):
        await query.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    users = await db.get_all_users()
    if not users:
        await query.edit_message_text(
            "👥 Пользователи не найдены",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]])
        )
        return
    
    text = "📋 Список пользователей:\n\n"
    for user in users[:20]:  # Показываем первых 20
        status = "✅" if user["is_active"] else "❌"
        username = f"@{user['username']}" if user["username"] else "Без имени"
        sub_type = user.get("subscription_type", "free")
        text += f"{status} ID: {user['user_id']} | {username} | {sub_type}\n"
    
    if len(users) > 20:
        text += f"\n... и ещё {len(users) - 20} пользователей"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def contacts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    contacts = await db.get_user_contacts(query.from_user.id)
    text = "📇 Ваши контакты:\n\n"
    if contacts:
        for contact in contacts:
            name = contact["name"] or "Без имени"
            text += f"• {name}: {contact['value']} ({contact['type']})\n"
    else:
        text += "У вас пока нет сохранённых контактов"
    keyboard = [
        [InlineKeyboardButton("➕ Добавить контакт", callback_data="add_contact")],
        [InlineKeyboardButton("🗑 Удалить контакт", callback_data="delete_contact")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def add_contact_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 Отправьте контакт в формате:\n\n"
        "username;@username;Имя\n"
        "или\n"
        "phone;+79991234567;Имя\n\n"
        "/cancel для отмены"
    )
    return ADD_CONTACTS

async def add_contact_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "/cancel":
        await update.message.reply_text("❌ Отменено")
        return ConversationHandler.END
    try:
        parts = text.split(";")
        if len(parts) != 3:
            raise ValueError("Неверный формат")
        contact_type, contact_value, name = parts
        contact_type = contact_type.strip()
        contact_value = contact_value.strip()
        name = name.strip()
        if contact_type not in ["username", "phone"]:
            raise ValueError("Тип должен быть username или phone")
        await db.add_contact(update.effective_user.id, contact_type, contact_value, name)
        await update.message.reply_text(f"✅ Контакт {name} добавлен!")
    except ValueError as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}\nПопробуйте ещё раз")
        return ADD_CONTACTS
    return ConversationHandler.END

async def templates_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    templates = await db.get_user_templates(query.from_user.id)
    text = "Your templates:\n\n"
    if templates:
        for template in templates:
            text += f"- {template['name']}\n"
    else:
        text += "No saved templates yet"
    keyboard = [
        [InlineKeyboardButton("Add template", callback_data="add_template")],
        [InlineKeyboardButton("Delete template", callback_data="delete_template")],
        [InlineKeyboardButton("Back", callback_data="back_to_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def add_template_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📝 Введите название шаблона:\n\n/cancel для отмены")
    return ADD_TEMPLATE_NAME

async def add_template_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "/cancel":
        await update.message.reply_text("❌ Отменено")
        return ConversationHandler.END
    context.user_data["template_name"] = update.message.text
    await update.message.reply_text("✅ Теперь введите текст шаблона:")
    return ADD_TEMPLATE_CONTENT

async def add_template_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "/cancel":
        await update.message.reply_text("❌ Отменено")
        return ConversationHandler.END
    name = context.user_data["template_name"]
    content = update.message.text
    await db.add_template(update.effective_user.id, name, content)
    await update.message.reply_text(f"✅ Шаблон '{name}' сохранён!")
    return ConversationHandler.END

async def new_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not await check_access(update):
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton("✍️ Написать новое сообщение", callback_data="new_message")],
        [InlineKeyboardButton("📄 Использовать шаблон", callback_data="use_template")],
        [InlineKeyboardButton("🔁 Множественная отправка (N раз одному)", callback_data="multi_send")],
        [InlineKeyboardButton("❌ Отмена", callback_data="back_to_menu")]
    ]
    
    await query.edit_message_text(
        "📮 Создание новой рассылки\n\n"
        "Выберите способ:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return SELECTING_ACTION

async def use_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    templates = await db.get_user_templates(query.from_user.id)
    keyboard = []
    for template in templates:
        keyboard.append([InlineKeyboardButton(template["name"], callback_data=f"template_{template['id']}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="new_mailing")])
    await query.edit_message_text("📝 Выберите шаблон:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_TEMPLATE

async def multi_send_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало множественной отправки"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🔁 Множественная отправка\n\n"
        "Отправьте ID или username получателя:\n"
        "Примеры:\n"
        "• 123456789\n"
        "• @username\n\n"
        "Или /cancel для отмены"
    )
    
    return MULTI_SEND_CONTACT

async def multi_send_contact_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение контакта для множественной отправки"""
    contact = update.message.text.strip()
    
    # Проверка формата
    if contact.startswith("@"):
        # Username
        context.user_data["multi_contact"] = contact
    else:
        # Пробуем как ID
        try:
            contact_id = int(contact)
            context.user_data["multi_contact"] = contact_id
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат!\n\n"
                "Отправьте ID (число) или username (@username)"
            )
            return MULTI_SEND_CONTACT
    
    await update.message.reply_text(
        "🔢 Сколько раз отправить сообщение?\n\n"
        "Введите число (от 1 до 100):\n\n"
        "Или /cancel для отмены"
    )
    
    return MULTI_SEND_COUNT

async def multi_send_count_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение количества отправок"""
    try:
        count = int(update.message.text.strip())
        
        if count < 1 or count > 100:
            await update.message.reply_text(
                "❌ Неверное количество!\n\n"
                "Введите число от 1 до 100"
            )
            return MULTI_SEND_COUNT
        
        context.user_data["multi_count"] = count
        
        keyboard = [
            [InlineKeyboardButton("✍️ Написать новое", callback_data="new_message")],
            [InlineKeyboardButton("📄 Из шаблона", callback_data="use_template")],
            [InlineKeyboardButton("❌ Отмена", callback_data="back_to_menu")]
        ]
        
        await update.message.reply_text(
            f"✅ Получатель: {context.user_data['multi_contact']}\n"
            f"🔢 Количество: {count} раз\n\n"
            "Выберите сообщение:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return SELECTING_ACTION
        
    except ValueError:
        await update.message.reply_text(
            "❌ Введите число!\n\n"
            "Пример: 5"
        )
        return MULTI_SEND_COUNT

async def confirm_multi_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение множественной рассылки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_mailing":
        await query.edit_message_text("❌ Рассылка отменена")
        return ConversationHandler.END
    
    user_id = query.from_user.id
    message = context.user_data["mailing_message"]
    contact = context.user_data["multi_contact"]
    count = context.user_data["multi_count"]
    delay = context.user_data.get("mailing_delay", 1)
    
    # Проверка лимитов
    trial_available = await db.check_trial_available(user_id)
    
    if trial_available:
        if count > 10:
            await query.edit_message_text(
                f"❌ Превышен лимит пробной версии!\n\n"
                f"📨 Максимум: 10 сообщений\n"
                f"📊 Вы хотите отправить: {count}\n\n"
                f"💳 Оформите подписку: /subscribe"
            )
            return ConversationHandler.END
        
        keyboard = [
            [InlineKeyboardButton("✅ Использовать пробную версию", callback_data="confirm_trial_multi")],
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel_mailing")]
        ]
        
        await query.edit_message_text(
            f"⚠️ Это ваша ЕДИНСТВЕННАЯ бесплатная рассылка!\n\n"
            f"👤 Получатель: {contact}\n"
            f"🔢 Количество: {count} раз\n"
            f"📄 Сообщение: {message[:50]}...\n\n"
            f"Продолжить?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CONFIRM_MAILING
    
    # Проверка обычных лимитов
    can_send, error_message = await check_limits(user_id, count)
    if not can_send:
        await query.edit_message_text(error_message)
        return ConversationHandler.END
    
    # Создаём список контактов (повторяем N раз)
    contacts = [contact] * count
    
    # Создаём рассылку
    mailing_id = await db.create_mailing(user_id, message, contacts, delay)
    
    await query.edit_message_text(
        f"🚀 Рассылка #{mailing_id} запущена!\n\n"
        f"👤 Получатель: {contact}\n"
        f"🔢 Отправок: {count}\n"
        f"⏱ Задержка: {delay} сек\n\n"
        f"Вы получите уведомление по завершению."
    )
    
    asyncio.create_task(run_mailing(context.bot, mailing_id, user_id))
    return ConversationHandler.END

async def confirm_trial_multi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение пробной множественной рассылки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    message = context.user_data["mailing_message"]
    contact = context.user_data["multi_contact"]
    count = context.user_data["multi_count"]
    delay = context.user_data.get("mailing_delay", 1)
    
    # Помечаем пробную как использованную
    await db.use_trial(user_id)
    
    # Создаём список контактов
    contacts = [contact] * count
    
    # Создаём рассылку
    mailing_id = await db.create_mailing(user_id, message, contacts, delay)
    
    await query.edit_message_text(
        f"🎁 Пробная рассылка #{mailing_id} запущена!\n\n"
        f"👤 Получатель: {contact}\n"
        f"🔢 Отправок: {count}\n\n"
        f"⚠️ Это была ваша единственная бесплатная рассылка\n"
        f"💳 Для дальнейшей работы оформите подписку: /subscribe"
    )
    
    asyncio.create_task(run_mailing(context.bot, mailing_id, user_id))
    return ConversationHandler.END

async def template_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    template_id = int(query.data.split("_")[1])
    templates = await db.get_user_templates(query.from_user.id)
    template = next((t for t in templates if t["id"] == template_id), None)
    if not template:
        await query.edit_message_text("❌ Шаблон не найден")
        return ConversationHandler.END
    context.user_data["mailing_message"] = template["content"]
    await query.edit_message_text(
        f"✅ Выбран шаблон: {template['name']}\n\n"
        f"📄 Текст сообщения:\n{template['content']}\n\n"
        f"👥 Теперь выберите контакты. Отправьте их одним сообщением:\n\n"
        f"Каждый контакт с новой строки:\n"
        f"@username или +79991234567\n\n"
        f"Или напишите 'все' для отправки всем сохранённым контактам\n\n"
        f"/cancel для отмены"
    )
    return ADD_CONTACTS

async def new_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✍️ Введите текст сообщения для рассылки:\n\n"
        "/cancel для отмены"
    )
    return ADD_MESSAGE

async def message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "/cancel":
        await update.message.reply_text("❌ Отменено")
        return ConversationHandler.END
    context.user_data["mailing_message"] = update.message.text
    await update.message.reply_text(
        "✅ Текст сохранён!\n\n"
        "👥 Теперь выберите контакты. Отправьте их одним сообщением:\n\n"
        "Каждый контакт с новой строки:\n"
        "@username или +79991234567\n\n"
        "Или напишите 'все' для отправки всем сохранённым контактам"
    )
    return ADD_CONTACTS

async def contacts_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "/cancel":
        await update.message.reply_text("❌ Отменено")
        return ConversationHandler.END
    text = update.message.text.strip().lower()
    if text == "все" or text == "all":
        saved_contacts = await db.get_user_contacts(update.effective_user.id)
        contacts = [c["value"] for c in saved_contacts]
    else:
        contacts = [line.strip() for line in update.message.text.split("\n") if line.strip()]
    if not contacts:
        await update.message.reply_text("❌ Не удалось распознать контакты. Попробуйте ещё раз.")
        return ADD_CONTACTS
    context.user_data["mailing_contacts"] = contacts
    await update.message.reply_text(
        f"✅ Контактов для рассылки: {len(contacts)}\n\n"
        f"⏱ Теперь установите задержку между сообщениями в секундах:\n"
        f"(рекомендуется: 0.1 - 1.0)\n\n"
        f"Введите число или напишите 'нет' для отправки без задержки"
    )
    return SET_DELAY

async def delay_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        delay = float(update.message.text)
        if delay < 0:
            await update.message.reply_text("⚠️ Задержка не может быть отрицательной. Попробуйте снова:")
            return SET_DELAY
        
        context.user_data["mailing_delay"] = delay
        
        # Проверяем режим отправки
        if "multi_contact" in context.user_data:
            # Множественная отправка
            contact = context.user_data["multi_contact"]
            count = context.user_data["multi_count"]
            message = context.user_data["mailing_message"]
            
            keyboard = [
                [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_multi_mailing")],
                [InlineKeyboardButton("❌ Отменить", callback_data="cancel_mailing")]
            ]
            
            await update.message.reply_text(
                f"📋 Проверьте данные:\n\n"
                f"👤 Получатель: {contact}\n"
                f"🔢 Количество: {count} раз\n"
                f"📄 Сообщение: {message[:100]}...\n"
                f"⏱ Задержка: {delay} сек\n\n"
                f"Все верно?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            # Обычная рассылка
            contacts = context.user_data["mailing_contacts"]
            message = context.user_data["mailing_message"]
            
            keyboard = [
                [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_mailing")],
                [InlineKeyboardButton("❌ Отменить", callback_data="cancel_mailing")]
            ]
            
            await update.message.reply_text(
                f"📋 Проверьте данные:\n\n"
                f"📨 Контактов: {len(contacts)}\n"
                f"📄 Сообщение: {message[:100]}...\n"
                f"⏱ Задержка: {delay} сек\n\n"
                f"Все верно?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        return CONFIRM_MAILING
        
    except ValueError:
        await update.message.reply_text("⚠️ Введите число (можно с точкой).\nПример: 1.5")
        return SET_DELAY

async def confirm_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_mailing":
        await query.edit_message_text("❌ Рассылка отменена")
        return ConversationHandler.END
    
    user_id = query.from_user.id
    message = context.user_data["mailing_message"]
    contacts = context.user_data["mailing_contacts"]
    delay = context.user_data["mailing_delay"]
    
    # НОВАЯ ПРОВЕРКА: Проверка пробной версии
    trial_available = await db.check_trial_available(user_id)
    
    if trial_available:
        # Лимит 10 контактов для пробной версии
        if len(contacts) > 10:
            await query.edit_message_text(
                f"❌ Превышен лимит пробной версии!\n\n"
                f"📨 Максимум: 10 контактов\n"
                f"📊 Вы указали: {len(contacts)}\n\n"
                f"💡 Решения:\n"
                f"1. Уменьшите количество контактов\n"
                f"2. Оформите подписку: /subscribe"
            )
            return ConversationHandler.END
        
        # Предупреждение что это единственная попытка
        keyboard = [
            [InlineKeyboardButton("✅ Да, использовать пробную версию!", callback_data="confirm_trial_mailing")],
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel_mailing")]
        ]
        
        await query.edit_message_text(
            f"⚠️ ВНИМАНИЕ! Это ваша ЕДИНСТВЕННАЯ бесплатная рассылка!\n\n"
            f"📨 Контактов: {len(contacts)}\n"
            f"📄 Сообщение: {message[:50]}...\n\n"
            f"После использования будут доступны только платные тарифы.\n\n"
            f"❓ Вы уверены?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CONFIRM_MAILING
    
    # Проверка лимитов для платных подписок
    can_send, error_message = await check_limits(user_id, len(contacts))
    if not can_send:
        await query.edit_message_text(error_message)
        return ConversationHandler.END
    
    # Обычный процесс рассылки
    mailing_id = await db.create_mailing(user_id, message, contacts, delay)
    
    await query.edit_message_text(
        f"🚀 Рассылка #{mailing_id} запущена!\n\n"
        f"📤 Отправка {len(contacts)} сообщений...\n"
        f"Вы получите уведомление по завершению."
    )
    
    asyncio.create_task(run_mailing(context.bot, mailing_id, user_id))
    return ConversationHandler.END

async def confirm_trial_mailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    message = context.user_data["mailing_message"]
    contacts = context.user_data["mailing_contacts"]
    delay = context.user_data["mailing_delay"]
    
    # Пометить пробную версию как использованную
    await db.use_trial(user_id)
    
    # Создать рассылку
    mailing_id = await db.create_mailing(user_id, message, contacts, delay)
    
    await query.edit_message_text(
        f"🎁 Пробная рассылка #{mailing_id} запущена!\n\n"
        f"📤 Отправка {len(contacts)} сообщений...\n\n"
        f"⚠️ Это была ваша единственная бесплатная рассылка\n"
        f"💳 Для дальнейшей работы оформите подписку: /subscribe"
    )
    
    asyncio.create_task(run_mailing(context.bot, mailing_id, user_id))
    return ConversationHandler.END

async def run_mailing(bot, mailing_id, user_id):
    """Выполнение рассылки"""
    try:
        mailing = await db.get_mailing(mailing_id)
        if not mailing:
            logger.error(f"Mailing {mailing_id} not found")
            return
        
        await db.update_mailing_status(mailing_id, "in_progress")
        
        message_text = mailing["message_text"]
        contacts = mailing["contacts"]
        delay = mailing["delay"]
        
        sent_count = 0
        failed_count = 0
        
        logger.info(f"Starting mailing {mailing_id} with {len(contacts)} contacts")
        
        for contact in contacts:
            try:
                # Отправка сообщения
                await bot.send_message(chat_id=contact, text=message_text)
                sent_count += 1
                await db.add_mailing_log(mailing_id, contact, "success")
                logger.info(f"Message sent to {contact}")
                
                # Задержка между сообщениями
                if delay > 0:
                    await asyncio.sleep(delay)
                    
            except TelegramError as e:
                failed_count += 1
                await db.add_mailing_log(mailing_id, contact, "failed", str(e))
                logger.error(f"Failed to send to {contact}: {e}")
            except Exception as e:
                failed_count += 1
                await db.add_mailing_log(mailing_id, contact, "failed", str(e))
                logger.error(f"Unexpected error for {contact}: {e}")
        
        # Обновление статистики
        await db.update_mailing_stats(mailing_id, sent_count, failed_count)
        await db.update_mailing_status(mailing_id, "completed")
        await db.update_messages_count(user_id, sent_count)
        
        # Уведомление пользователю
        result_text = (
            f"✅ Рассылка #{mailing_id} завершена!\n\n"
            f"📤 Отправлено: {sent_count}\n"
            f"❌ Ошибок: {failed_count}\n"
            f"📊 Всего: {len(contacts)}"
        )
        
        await bot.send_message(chat_id=user_id, text=result_text)
        logger.info(f"Mailing {mailing_id} completed: {sent_count} sent, {failed_count} failed")
        
    except Exception as e:
        logger.error(f"Mailing {mailing_id} failed: {e}")
        await db.update_mailing_status(mailing_id, "failed")
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"❌ Ошибка рассылки #{mailing_id}: {str(e)}"
            )
        except:
            pass

async def my_mailings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mailings = await db.get_user_mailings(query.from_user.id)
    if not mailings:
        await query.edit_message_text(
            "📋 У вас пока нет рассылок",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]])
        )
        return
    text = "📋 Ваши рассылки:\n\n"
    for m in mailings[:10]:
        status_emoji = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌"}
        emoji = status_emoji.get(m['status'], "❓")
        text += (
            f"{emoji} Рассылка #{m['id']}\n"
            f"📅 Дата: {m['created_at'][:16]}\n"
            f"📤 Отправлено: {m['sent']}/{m['total']}\n"
            f"❌ Ошибок: {m['failed']}\n"
            f"📊 Статус: {m['status']}\n\n"
        )
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    users = await db.get_all_users()
    active_users = len([u for u in users if u["is_active"]])
    admins = len([u for u in users if u["role"] == ROLE_ADMIN])
    support = len([u for u in users if u["role"] == ROLE_SUPPORT])
    regular = len([u for u in users if u["role"] == ROLE_USER])
    async with db.db.execute("SELECT COUNT(*), SUM(sent_count), SUM(failed_count) FROM mailings") as cursor:
        row = await cursor.fetchone()
        total_mailings = row[0] or 0
        total_sent = row[1] or 0
        total_failed = row[2] or 0
    text = (
        f"📊 Статистика бота:\n\n"
        f"👥 Пользователи:\n"
        f"📈 Всего: {len(users)}\n"
        f"✅ Активных: {active_users}\n"
        f"👑 Админов: {admins}\n"
        f"🛠 Поддержки: {support}\n"
        f"👤 Пользователей: {regular}\n\n"
        f"📮 Рассылки:\n"
        f"📊 Всего рассылок: {total_mailings}\n"
        f"✅ Сообщений отправлено: {total_sent}\n"
        f"❌ Ошибок: {total_failed}\n"
    )
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = await db.get_user(query.from_user.id)
    role = user["role"]
    await query.edit_message_text("🏠 Главное меню", reply_markup=get_main_keyboard(role))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    # Логирование
    print(f"🔘 Нажата кнопка: {query.data}")
    logger.info(f"Button pressed: {query.data} by user {query.from_user.id}")
    
    # Обработка платежей
    if query.data.startswith("pay_stars_"):
        await process_payment_stars(update, context)
        return
    if query.data.startswith("pay_yoomoney_"):
        await process_payment_yoomoney(update, context)
        return
    if query.data.startswith("pay_crypto_"):
        await process_payment_crypto(update, context)
        return
    if query.data.startswith("confirm_payment_"):
        await confirm_payment(update, context)
        return
    if query.data.startswith("plan_"):
        await select_plan(update, context)
        return
    
    # Основные обработчики
    handlers = {
    "new_mailing": new_mailing,
    "my_mailings": my_mailings,
    "templates": templates_menu,
    "contacts": contacts_menu,
    "stats": stats,
    "users": users_menu,
    "back_to_menu": back_to_menu,
    "add_contact": add_contact_start,
    "add_template": add_template_start,
    "new_message": new_message,
    "use_template": use_template,
    "subscribe": subscribe_menu,
    "compare_plans": compare_plans,
    "confirm_trial_mailing": confirm_trial_mailing,
    "support": support_menu  # ДОБАВЬ ЭТУ СТРОКУ

    }
    
    if query.data.startswith("template_"):
        await template_selected(update, context)
        return
    
    handler = handlers.get(query.data)
    if handler:
        await handler(update, context)
    else:
        await query.answer("⚠️ Функция в разработке")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Действие отменено")
    return ConversationHandler.END

async def main():
    await db.connect()
    logger.info("Database connected")
    
    # Создаём приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # 1. Регистрируем ВСЕ команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add_support", add_support))
    application.add_handler(CommandHandler("add_user", add_user_command))
    application.add_handler(CommandHandler("remove_user", remove_user))
    application.add_handler(CommandHandler("users", list_users))
    application.add_handler(CommandHandler("trial", trial_command))
    application.add_handler(CommandHandler("subscribe", subscribe_menu))
    application.add_handler(CommandHandler("limits", limits_info))
    application.add_handler(CommandHandler("referral", referral_info))
    application.add_handler(CommandHandler("give_subscription", give_subscription_command))
    application.add_handler(CommandHandler("support", support_command))
    application.add_handler(CommandHandler("reply", reply_to_user))
    
    # 2. ConversationHandlers
    mailing_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(new_mailing, pattern="^new_mailing$")
    ],
    states={
        SELECTING_ACTION: [
            CallbackQueryHandler(new_message, pattern="^new_message$"),
            CallbackQueryHandler(use_template, pattern="^use_template$"),
            CallbackQueryHandler(multi_send_start, pattern="^multi_send$")
        ],
        MULTI_SEND_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, multi_send_contact_received)],
        MULTI_SEND_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, multi_send_count_received)],
        SELECT_TEMPLATE: [CallbackQueryHandler(template_selected, pattern="^template_")],
        ADD_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_received)],
        ADD_CONTACTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, contacts_received)],
        SET_DELAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, delay_received)],
        CONFIRM_MAILING: [
            CallbackQueryHandler(confirm_mailing, pattern="^confirm_mailing$"),
            CallbackQueryHandler(confirm_trial_mailing, pattern="^confirm_trial_mailing$"),
            CallbackQueryHandler(confirm_multi_mailing, pattern="^confirm_multi_mailing$"),
            CallbackQueryHandler(confirm_trial_multi, pattern="^confirm_trial_multi$"),
            CallbackQueryHandler(confirm_mailing, pattern="^cancel_mailing$")
        ]
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False,
    per_chat=True,
    per_user=True
)
    
    contact_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_contact_start, pattern="^add_contact$")],
        states={
            ADD_CONTACTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_contact_process)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        per_chat=True,
        per_user=True
    )
    
    template_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_template_start, pattern="^add_template$")],
        states={
            ADD_TEMPLATE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_template_name)],
            ADD_TEMPLATE_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_template_content)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        per_chat=True,
        per_user=True
    )
    
    # 3. Регистрируем handlers
    application.add_handler(mailing_conv)
    application.add_handler(contact_conv)
    application.add_handler(template_conv)
    
    # 4. ПОСЛЕДНИМ - общий обработчик кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("Bot started!")
    
    # Запуск бота
    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    
    try:
        # Бесконечный цикл работы бота
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopping...")
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        await db.close()
        logger.info("Bot stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")