#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Вспомогательные функции
"""

import logging
from datetime import datetime
from typing import Dict, Optional
from config import SUBSCRIPTION_PLANS

logger = logging.getLogger(__name__)


def check_subscription(user: Dict) -> bool:
    """Проверить активность подписки"""
    if not user:
        return False
    
    subscription_end = user.get('subscription_end')
    if not subscription_end:
        return False
    
    try:
        if isinstance(subscription_end, str):
            end_date = datetime.fromisoformat(subscription_end.replace('Z', '+00:00'))
        else:
            end_date = subscription_end
        
        return datetime.now() < end_date
    except:
        return False


def get_days_left(user: Dict) -> int:
    """Получить количество оставшихся дней подписки"""
    if not user:
        return 0
    
    subscription_end = user.get('subscription_end')
    if not subscription_end:
        return 0
    
    try:
        if isinstance(subscription_end, str):
            end_date = datetime.fromisoformat(subscription_end.replace('Z', '+00:00'))
        else:
            end_date = subscription_end
        
        delta = end_date - datetime.now()
        return max(0, delta.days)
    except:
        return 0


def get_user_limits(user: Dict) -> Dict:
    """Получить лимиты пользователя"""
    if not user:
        return {
            'accounts': 0,
            'mailings_per_day': 0,
            'targets_per_mailing': 0,
            'schedule_tasks': 0
        }
    
    plan_id = user.get('subscription_plan', 'trial')
    plan = SUBSCRIPTION_PLANS.get(plan_id)
    
    if not plan:
        plan = SUBSCRIPTION_PLANS['trial']
    
    return plan['limits']


def check_limit(user: Dict, limit_type: str, current_value: int) -> tuple:
    """
    Проверить лимит
    Возвращает: (allowed: bool, limit: int)
    """
    limits = get_user_limits(user)
    limit = limits.get(limit_type, 0)
    
    # -1 означает безлимит
    if limit == -1:
        return (True, -1)
    
    return (current_value < limit, limit)


def format_subscription_info(user: Dict) -> str:
    """Форматировать информацию о подписке"""
    if not user:
        return "❌ Нет подписки"
    
    plan_id = user.get('subscription_plan', 'trial')
    plan = SUBSCRIPTION_PLANS.get(plan_id, SUBSCRIPTION_PLANS['trial'])
    
    days_left = get_days_left(user)
    is_active = check_subscription(user)
    
    status = "✅ Активна" if is_active else "❌ Не активна"
    
    limits = plan['limits']
    limits_text = []
    for key, value in limits.items():
        if value == -1:
            limits_text.append(f"  • {key}: ∞ (безлимит)")
        else:
            limits_text.append(f"  • {key}: {value}")
    
    return f"""
📊 *Информация о подписке*

Тариф: {plan['name']}
Статус: {status}
Осталось дней: {days_left}

*Лимиты:*
{chr(10).join(limits_text)}
"""


def format_account_info(account: Dict) -> str:
    """Форматировать информацию об аккаунте"""
    name = account.get('account_name', 'Не указано')
    phone = account.get('phone', 'Не указано')
    username = account.get('username', 'Не указано')
    
    first_name = account.get('first_name', '')
    last_name = account.get('last_name', '')
    full_name = f"{first_name} {last_name}".strip() or 'Не указано'
    
    last_used = account.get('last_used')
    if last_used:
        try:
            last_used_date = datetime.fromisoformat(last_used.replace('Z', '+00:00'))
            last_used_str = last_used_date.strftime('%d.%m.%Y %H:%M')
        except:
            last_used_str = 'Никогда'
    else:
        last_used_str = 'Никогда'
    
    return f"""
📱 *Аккаунт #{account['id']}*

Название: {name}
Имя: {full_name}
Username: @{username}
Телефон: {phone}
Последнее использование: {last_used_str}
"""


def format_mailing_info(mailing: Dict) -> str:
    """Форматировать информацию о рассылке"""
    status_emoji = {
        'pending': '⏳',
        'running': '🔄',
        'completed': '✅',
        'failed': '❌',
        'cancelled': '🚫'
    }
    
    status = mailing.get('status', 'pending')
    emoji = status_emoji.get(status, '❓')
    
    created_at = mailing.get('created_at')
    if created_at:
        try:
            created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            created_str = created_date.strftime('%d.%m.%Y %H:%M')
        except:
            created_str = 'Не указано'
    else:
        created_str = 'Не указано'
    
    targets_count = len(mailing.get('targets', '').split('\n'))
    accounts_count = len(mailing.get('accounts_used', '').split(','))
    
    success = mailing.get('success_count', 0)
    errors = mailing.get('error_count', 0)
    
    return f"""
{emoji} *Рассылка #{mailing['id']}*

Статус: {status}
Создана: {created_str}
Целей: {targets_count}
Аккаунтов: {accounts_count}
Успешно: {success}
Ошибок: {errors}
"""


def validate_phone(phone: str) -> tuple:
    """
    Валидация номера телефона
    Возвращает: (is_valid: bool, formatted_phone: str)
    """
    # Убираем все лишние символы
    clean_phone = ''.join(filter(str.isdigit, phone))
    
    # Проверяем длину
    if len(clean_phone) < 10 or len(clean_phone) > 15:
        return (False, phone)
    
    # Добавляем + если нет
    if not phone.startswith('+'):
        formatted = '+' + clean_phone
    else:
        formatted = '+' + clean_phone
    
    return (True, formatted)


def parse_targets(targets_text: str) -> list:
    """Парсинг списка целей"""
    targets = []
    for line in targets_text.split('\n'):
        line = line.strip()
        if line and not line.startswith('#'):
            targets.append(line)
    return targets