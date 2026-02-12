"""
Клавиатуры бота
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from config import SUBSCRIPTION_PLANS, PAYMENT_METHODS

def get_main_menu(is_admin=False):
    """Главное меню"""
    keyboard = [
        [InlineKeyboardButton("👤 Мои аккаунты", callback_data="my_accounts")],
        [InlineKeyboardButton("📨 Создать рассылку", callback_data="create_mailing")],
        [InlineKeyboardButton("⏰ Планировщик", callback_data="scheduler")],
        [InlineKeyboardButton("📜 История", callback_data="history")],
        [InlineKeyboardButton("💎 Тарифы", callback_data="subscriptions")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    
    if is_admin:
        keyboard.append([InlineKeyboardButton("👨‍💼 Админ-панель", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(keyboard)

def get_accounts_menu(has_accounts=False):
    """Меню управления аккаунтами"""
    keyboard = [
        [InlineKeyboardButton("➕ Подключить аккаунт", callback_data="connect_account")]
    ]
    
    if has_accounts:
        keyboard.append([InlineKeyboardButton("⚙️ Управление аккаунтами", callback_data="manage_accounts")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
    
    return InlineKeyboardMarkup(keyboard)

def get_accounts_list(accounts):
    """Список аккаунтов для управления"""
    keyboard = []
    
    for acc in accounts:
        name = acc.get('name', 'Без имени')
        phone = acc.get('phone', 'Неизвестно')
        status = "🟢" if acc.get('is_active') else "🔴"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {name} ({phone})",
                callback_data=f"account_info_{acc['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="my_accounts")])
    
    return InlineKeyboardMarkup(keyboard)

def get_account_actions(account_id):
    """Действия с аккаунтом"""
    keyboard = [
                [InlineKeyboardButton("🗑 Отключить аккаунт", callback_data=f"disconnect_account_{account_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="manage_accounts")]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def get_account_selection(accounts, selected_ids=None):
    """Выбор аккаунтов для рассылки"""
    if selected_ids is None:
        selected_ids = []
    
    keyboard = []
    
    for acc in accounts:
        name = acc.get('name', 'Без имени')
        phone = acc.get('phone', '')
        is_selected = acc['id'] in selected_ids
        
        checkbox = "✅" if is_selected else "⬜"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{checkbox} {name} ({phone})",
                callback_data=f"toggle_account_{acc['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("✅ Продолжить", callback_data="continue_with_selected")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_mailing")])
    
    return InlineKeyboardMarkup(keyboard)

def get_mailing_confirmation():
    """Подтверждение запуска рассылки"""
    keyboard = [
        [InlineKeyboardButton("🚀 Начать рассылку", callback_data="confirm_mailing")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel_mailing")]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def get_subscription_menu(current_plan='trial'):
    """Меню тарифов"""
    keyboard = []
    
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        if plan_id != current_plan:
            emoji = {'trial': '🆓', 'basic': '💼', 'pro': '🚀', 'premium': '👑'}.get(plan_id, '💎')
            keyboard.append([
                InlineKeyboardButton(
                    f"{emoji} {plan['name']} - {plan['price']} ₽",
                    callback_data=f"buy_{plan_id}"
                )
            ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
    
    return InlineKeyboardMarkup(keyboard)

def get_plan_details(plan_id):
    """Детали тарифа с кнопкой покупки"""
    keyboard = [
        [InlineKeyboardButton("💳 Купить", callback_data=f"buy_{plan_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="subscriptions")]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def get_payment_methods(plan_id):
    """Способы оплаты"""
    keyboard = []
    
    for method_id, method in PAYMENT_METHODS.items():
        if method.get('enabled', False):
            keyboard.append([
                InlineKeyboardButton(
                    method['name'],
                    callback_data=f"payment_{plan_id}_{method_id}"
                )
            ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data=f"buy_{plan_id}")])
    
    return InlineKeyboardMarkup(keyboard)

def get_payment_confirmation(payment_id):
    """Подтверждение оплаты"""
    keyboard = [
        [InlineKeyboardButton("✅ Я оплатил", callback_data=f"paid_{payment_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="subscriptions")]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def get_scheduler_menu(has_schedules=False):
    """Меню планировщика"""
    keyboard = [
        [InlineKeyboardButton("➕ Создать расписание", callback_data="create_schedule")]
    ]
    
    if has_schedules:
        keyboard.append([InlineKeyboardButton("📋 Мои расписания", callback_data="view_schedules")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
    
    return InlineKeyboardMarkup(keyboard)

def get_schedules_list(schedules):
    """Список расписаний"""
    keyboard = []
    
    for schedule in schedules:
        status = "🟢" if schedule.get('is_active') else "🔴"
        name = schedule.get('name', f"Расписание #{schedule['id']}")
        
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {name}",
                callback_data=f"schedule_info_{schedule['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="scheduler")])
    
    return InlineKeyboardMarkup(keyboard)

def get_schedule_actions(schedule_id, is_active=True):
    """Действия с расписанием"""
    keyboard = []
    
    if is_active:
        keyboard.append([InlineKeyboardButton("⏸ Приостановить", callback_data=f"pause_schedule_{schedule_id}")])
    else:
        keyboard.append([InlineKeyboardButton("▶️ Возобновить", callback_data=f"resume_schedule_{schedule_id}")])
    
    keyboard.extend([
        [InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_schedule_{schedule_id}")],
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_schedule_{schedule_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="view_schedules")]
    ])
    
    return InlineKeyboardMarkup(keyboard)

def get_history_menu():
    """Меню истории"""
    keyboard = [
        [InlineKeyboardButton("📊 Все рассылки", callback_data="history_all")],
        [InlineKeyboardButton("✅ Успешные", callback_data="history_success")],
        [InlineKeyboardButton("❌ С ошибками", callback_data="history_errors")],
        [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def get_mailings_list(mailings):
    """Список рассылок"""
    keyboard = []
    
    for mailing in mailings:
        status_emoji = {
            'pending': '⏳',
            'running': '🚀',
            'completed': '✅',
            'failed': '❌',
            'cancelled': '🚫'
        }.get(mailing.get('status'), '❓')
        
        date = mailing.get('created_at', '')[:10]
        
        keyboard.append([
            InlineKeyboardButton(
                f"{status_emoji} {date} - {mailing.get('sent', 0)}/{mailing.get('total', 0)}",
                callback_data=f"mailing_info_{mailing['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="history")])
    
    return InlineKeyboardMarkup(keyboard)

def get_mailing_actions(mailing_id, status='completed'):
    """Действия с рассылкой"""
    keyboard = []
    
    if status == 'running':
        keyboard.append([InlineKeyboardButton("⏸ Приостановить", callback_data=f"pause_mailing_{mailing_id}")])
        keyboard.append([InlineKeyboardButton("🛑 Остановить", callback_data=f"stop_mailing_{mailing_id}")])
    elif status == 'paused':
        keyboard.append([InlineKeyboardButton("▶️ Возобновить", callback_data=f"resume_mailing_{mailing_id}")])
    
    keyboard.append([InlineKeyboardButton("📊 Статистика", callback_data=f"mailing_stats_{mailing_id}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="history_all")])
    
    return InlineKeyboardMarkup(keyboard)

def get_admin_panel():
    """Админ-панель"""
    keyboard = [
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("💰 Платежи", callback_data="admin_payments")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("💾 Резервные копии", callback_data="admin_backup")],
        [InlineKeyboardButton("📢 Рассылка всем", callback_data="admin_broadcast")],
        [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def get_admin_users_menu():
    """Меню управления пользователями"""
    keyboard = [
        [InlineKeyboardButton("📋 Список пользователей", callback_data="admin_users_list")],
        [InlineKeyboardButton("🔍 Поиск пользователя", callback_data="admin_users_search")],
        [InlineKeyboardButton("📈 Статистика по тарифам", callback_data="admin_users_stats")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def get_admin_payments_menu(pending_count=0):
    """Меню управления платежами"""
    keyboard = [
        [InlineKeyboardButton(f"⏳ Ожидающие ({pending_count})", callback_data="admin_payments_pending")],
        [InlineKeyboardButton("✅ Одобренные", callback_data="admin_payments_approved")],
        [InlineKeyboardButton("❌ Отклонённые", callback_data="admin_payments_rejected")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def get_payment_actions(payment_id):
    """Действия с платежом"""
    keyboard = [
        [InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_payment_{payment_id}")],
        [InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_payment_{payment_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_payments")]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def get_back_button(callback_data="main_menu"):
    """Универсальная кнопка назад"""
    keyboard = [
        [InlineKeyboardButton("◀️ Назад", callback_data=callback_data)]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def get_cancel_button():
    """Кнопка отмены"""
    keyboard = [
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def get_confirm_cancel():
    """Подтверждение и отмена"""
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def get_help_menu():
    """Меню помощи"""
    keyboard = [
        [InlineKeyboardButton("📖 Документация", url="https://docs.example.com")],
        [InlineKeyboardButton("💬 Поддержка", url="https://t.me/support")],
        [InlineKeyboardButton("📹 Видео-инструкции", url="https://youtube.com/playlist")],
        [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]
    ]
    
    return InlineKeyboardMarkup(keyboard)