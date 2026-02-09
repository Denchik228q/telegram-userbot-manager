#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_menu(is_admin=False):
    keyboard = [
        [InlineKeyboardButton("📱 Мои аккаунты", callback_data="my_accounts")],
        [InlineKeyboardButton("📨 Создать рассылку", callback_data="create_mailing")],
        [InlineKeyboardButton("⏰ Планировщик", callback_data="scheduler")],
        [InlineKeyboardButton("📜 История", callback_data="history")],
        [InlineKeyboardButton("💎 Тарифы", callback_data="subscriptions")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
    ]
    if is_admin:
        keyboard.append([InlineKeyboardButton("👨‍💼 Админ", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def get_accounts_menu():
    keyboard = [
        [InlineKeyboardButton("➕ Подключить аккаунт", callback_data="connect_account")],
        [InlineKeyboardButton("⚙️ Управление", callback_data="manage_accounts")],
        [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_subscription_menu(current_plan='trial'):
    from config import SUBSCRIPTION_PLANS
    keyboard = []
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        if plan_id != current_plan:
            keyboard.append([InlineKeyboardButton(
                f"{plan['name']} - {plan['price']} ₽",
                callback_data=f"buy_{plan_id}"
            )])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_payment_methods_menu(plan_id):
    keyboard = [
        [InlineKeyboardButton("💳 Банковская карта", callback_data=f"payment_card_{plan_id}")],
        [InlineKeyboardButton("💰 Ручной перевод", callback_data=f"payment_manual_{plan_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="subscriptions")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_button(callback_data="main_menu"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data=callback_data)]])

def get_admin_menu():
    """Меню админ-панели"""
    keyboard = [
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("💰 Платежи", callback_data="admin_payments")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("💾 Бэкап БД", callback_data="admin_backup")],
        [InlineKeyboardButton("📢 Рассылка всем", callback_data="admin_broadcast")],
        [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)
