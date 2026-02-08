#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Клавиатуры бота
"""

from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton
from config import SUBSCRIPTION_PLANS, PAYMENT_METHODS


def get_main_menu(is_admin=False):
    """Главное меню"""
    keyboard = [
        [InlineKeyboardButton("📱 Мои аккаунты", callback_data="my_accounts")],
        [InlineKeyboardButton("📨 Создать рассылку", callback_data="create_mailing")],
        [InlineKeyboardButton("⏰ Планировщик", callback_data="scheduler")],
        [InlineKeyboardButton("📜 История", callback_data="history")],
        [InlineKeyboardButton("💎 Тарифы", callback_data="subscriptions")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
    ]
    
    if is_admin:
        keyboard.append([InlineKeyboardButton("👨‍💼 Админ-панель", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(keyboard)


def get_back_button():
    """Кнопка назад"""
    return ReplyKeyboardMarkup([[KeyboardButton("🔙 Назад")]], resize_keyboard=True)


def get_accounts_menu():
    """Меню аккаунтов"""
    keyboard = [
        [InlineKeyboardButton("➕ Подключить аккаунт", callback_data="connect_account")],
        [InlineKeyboardButton("📋 Мои аккаунты", callback_data="list_accounts")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_account_actions(account_id: int):
    """Действия с аккаунтом"""
    keyboard = [
        [InlineKeyboardButton("ℹ️ Информация", callback_data=f"account_info_{account_id}")],
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_account_{account_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="list_accounts")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_tariffs_menu():
    """Меню тарифов"""
    keyboard = []
    
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        price_text = f"{plan['price']}₽" if plan['price'] > 0 else "Бесплатно"
        button_text = f"{plan['name']} - {price_text}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"plan_{plan_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(keyboard)


def get_payment_methods(plan_id: str):
    """Способы оплаты"""
    keyboard = []
    
    for method_id, method in PAYMENT_METHODS.items():
        if method['enabled']:
            keyboard.append([InlineKeyboardButton(
                method['name'], 
                callback_data=f"pay_{plan_id}_{method_id}"
            )])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="view_tariffs")])
    return InlineKeyboardMarkup(keyboard)


def get_schedule_type_menu():
    """Выбор типа расписания"""
    keyboard = [
        [InlineKeyboardButton("📅 Ежедневно", callback_data="schedule_type_daily")],
        [InlineKeyboardButton("📆 Еженедельно", callback_data="schedule_type_weekly")],
        [InlineKeyboardButton("🔙 Отмена", callback_data="cancel_schedule")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_schedule_actions(schedule_id: int):
    """Действия с расписанием"""
    keyboard = [
        [InlineKeyboardButton("ℹ️ Информация", callback_data=f"schedule_info_{schedule_id}")],
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_schedule_{schedule_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="list_schedules")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_menu():
    """Админ-меню"""
    keyboard = [
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("💳 Платежи", callback_data="admin_payments")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("💾 Бэкап", callback_data="admin_backup")],
        [InlineKeyboardButton("📢 Рассылка всем", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_payment_approval(payment_id: int):
    """Подтверждение платежа"""
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_payment_{payment_id}")],
        [InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_payment_{payment_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_confirm_mailing():
    """Подтверждение рассылки"""
    keyboard = [
        [InlineKeyboardButton("✅ Запустить", callback_data="confirm_mailing")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel_mailing")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_account_selection(accounts: list, selected_ids: list = None):
    """Выбор аккаунтов для рассылки"""
    if selected_ids is None:
        selected_ids = []
    
    keyboard = []
    
    for account in accounts:
        account_id = account['id']
        name = account.get('account_name', f"Account {account_id}")
        
        # Чекбокс: выбран или нет
        checkbox = "☑️" if account_id in selected_ids else "⬜️"
        button_text = f"{checkbox} {name}"
        
        keyboard.append([InlineKeyboardButton(
            button_text, 
            callback_data=f"toggle_account_{account_id}"
        )])
    
    keyboard.append([InlineKeyboardButton("✅ Продолжить", callback_data="continue_with_selected")])
    keyboard.append([InlineKeyboardButton("🔙 Отмена", callback_data="cancel_mailing")])
    
    return InlineKeyboardMarkup(keyboard)


def get_cancel_button():
    """Кнопка отмены"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data="cancel")]])