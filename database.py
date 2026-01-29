#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Database module for Telegram Manager Bot
Handles all database operations with SQLite
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_name: str = "userbot_manager.db"):
        """Инициализация базы данных"""
        self.db_name = db_name
        self._create_tables()
    
    @contextmanager
    def _get_connection(self):
        """Context manager для подключения к БД"""
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()
    
    def _create_tables(self):
        """Создание всех таблиц"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    subscription_plan TEXT DEFAULT 'trial',
                    subscription_end TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1
                )
            """)
            
            # Таблица аккаунтов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    phone_number TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    account_name TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Таблица рассылок
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mailings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    message TEXT,
                    sent_count INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Таблица запланированных рассылок
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_mailings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    message_text TEXT,
                    message_photo TEXT,
                    message_video TEXT,
                    message_caption TEXT,
                    targets TEXT,
                    account_ids TEXT,
                    schedule_type TEXT,
                    schedule_time TEXT,
                    is_active INTEGER DEFAULT 1,
                    last_run TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Таблица платежей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    plan_id TEXT NOT NULL,
                    amount REAL NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    approved_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Проверяем и добавляем недостающие столбцы
            self._migrate_tables(cursor)
            
            conn.commit()
            logger.info("✅ Database tables created/updated successfully")
    
    def _migrate_tables(self, cursor):
        """Миграция существующих таблиц"""
        try:
            # Проверяем наличие subscription_plan в users
            cursor.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'subscription_plan' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN subscription_plan TEXT DEFAULT 'trial'")
                logger.info("Added subscription_plan column")
            
            if 'subscription_end' not in columns:
                # Добавляем с триальным периодом 3 дня
                cursor.execute(f"""
                    ALTER TABLE users ADD COLUMN subscription_end TIMESTAMP 
                    DEFAULT (datetime('now', '+3 days'))
                """)
                logger.info("Added subscription_end column")
            
            # Обновляем существующих пользователей без подписки
            cursor.execute("""
                UPDATE users 
                SET subscription_end = datetime('now', '+3 days'),
                    subscription_plan = 'trial'
                WHERE subscription_end IS NULL OR subscription_end = ''
            """)
            
        except Exception as e:
            logger.error(f"Migration error: {e}")
    
    # ==================== ПОЛЬЗОВАТЕЛИ ====================
    
    def add_user(self, user_id: int, username: Optional[str] = None) -> bool:
        """Добавить нового пользователя с триальным периодом"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Проверяем существование
                cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                if cursor.fetchone():
                    return True
                
                # Добавляем с триальным периодом 3 дня
                trial_end = datetime.now() + timedelta(days=3)
                cursor.execute("""
                    INSERT INTO users (user_id, username, subscription_plan, subscription_end)
                    VALUES (?, ?, 'trial', ?)
                """, (user_id, username, trial_end))
                
                logger.info(f"✅ User {user_id} added with trial subscription")
                return True
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Получить данные пользователя"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                
                if row:
                    user_dict = dict(row)
                    # Преобразуем строку в datetime
                    if user_dict.get('subscription_end'):
                        user_dict['subscription_end'] = datetime.fromisoformat(user_dict['subscription_end'])
                    if user_dict.get('created_at'):
                        user_dict['created_at'] = user_dict['created_at']
                    return user_dict
                return None
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None
    
    def get_all_users(self, limit: int = None) -> List[Dict]:
        """Получить всех пользователей"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                query = "SELECT * FROM users ORDER BY created_at DESC"
                if limit:
                    query += f" LIMIT {limit}"
                cursor.execute(query)
                
                users = []
                for row in cursor.fetchall():
                    user_dict = dict(row)
                    if user_dict.get('subscription_end'):
                        user_dict['subscription_end'] = datetime.fromisoformat(user_dict['subscription_end'])
                    users.append(user_dict)
                return users
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []
    
    def update_user_subscription(self, user_id: int, plan_id: str, days: int) -> bool:
        """Обновить подписку пользователя"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Получаем текущую дату окончания
                cursor.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                
                if row:
                    current_end = datetime.fromisoformat(row['subscription_end'])
                    # Если подписка активна, продлеваем от текущей даты
                    if current_end > datetime.now():
                        new_end = current_end + timedelta(days=days)
                    else:
                        new_end = datetime.now() + timedelta(days=days)
                else:
                    new_end = datetime.now() + timedelta(days=days)
                
                cursor.execute("""
                    UPDATE users 
                    SET subscription_plan = ?, subscription_end = ?
                    WHERE user_id = ?
                """, (plan_id, new_end, user_id))
                
                logger.info(f"✅ Subscription updated for user {user_id}: {plan_id} until {new_end}")
                return True
        except Exception as e:
            logger.error(f"Error updating subscription: {e}")
            return False
    
    # ==================== АККАУНТЫ ====================
    
    def add_account(self, user_id: int, phone: str, session_id: str) -> Optional[int]:
        """Добавить аккаунт"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                account_name = f"Account {phone[-4:]}"
                
                cursor.execute("""
                    INSERT INTO accounts (user_id, phone_number, session_id, account_name)
                    VALUES (?, ?, ?, ?)
                """, (user_id, phone, session_id, account_name))
                
                account_id = cursor.lastrowid
                logger.info(f"✅ Account added: {phone} for user {user_id}")
                return account_id
        except Exception as e:
            logger.error(f"Error adding account: {e}")
            return None
    
    def get_user_accounts(self, user_id: int) -> List[Dict]:
        """Получить все аккаунты пользователя"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM accounts 
                    WHERE user_id = ? AND is_active = 1
                    ORDER BY created_at DESC
                """, (user_id,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting user accounts: {e}")
            return []
    
    def get_account(self, account_id: int) -> Optional[Dict]:
        """Получить аккаунт по ID"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting account: {e}")
            return None
    
    def get_account_by_phone(self, user_id: int, phone: str) -> Optional[Dict]:
        """Найти аккаунт по номеру"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM accounts 
                    WHERE user_id = ? AND phone_number = ?
                """, (user_id, phone))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting account by phone: {e}")
            return None
    
    def delete_account(self, account_id: int) -> bool:
        """Удалить аккаунт"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE accounts SET is_active = 0 WHERE id = ?", (account_id,))
                logger.info(f"✅ Account {account_id} deleted")
                return True
        except Exception as e:
            logger.error(f"Error deleting account: {e}")
            return False
    
    # ==================== РАССЫЛКИ ====================
    
    def add_mailing(self, user_id: int, message: str, sent: int, errors: int) -> Optional[int]:
        """Добавить запись о рассылке"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO mailings (user_id, message, sent_count, error_count)
                    VALUES (?, ?, ?, ?)
                """, (user_id, message, sent, errors))
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding mailing: {e}")
            return None
    
    def get_user_mailings(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Получить историю рассылок пользователя"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM mailings 
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (user_id, limit))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting user mailings: {e}")
            return []
    
    def get_user_mailings_today(self, user_id: int) -> int:
        """Получить количество рассылок пользователя за сегодня"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) as count FROM mailings
                    WHERE user_id = ? AND DATE(created_at) = DATE('now')
                """, (user_id,))
                row = cursor.fetchone()
                return row['count'] if row else 0
        except Exception as e:
            logger.error(f"Error getting today mailings: {e}")
            return 0
    
    # ==================== ЗАПЛАНИРОВАННЫЕ РАССЫЛКИ ====================
    
    def get_user_scheduled_mailings(self, user_id: int) -> List[Dict]:
        """Получить запланированные рассылки пользователя"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM scheduled_mailings
                    WHERE user_id = ? AND is_active = 1
                    ORDER BY created_at DESC
                """, (user_id,))
                
                schedules = []
                for row in cursor.fetchall():
                    schedule = dict(row)
                    # Парсим targets из строки в список
                    if schedule.get('targets'):
                        schedule['targets'] = schedule['targets'].split('|||')
                    schedules.append(schedule)
                return schedules
        except Exception as e:
            logger.error(f"Error getting scheduled mailings: {e}")
            return []
    
    def delete_scheduled_mailing(self, schedule_id: int) -> bool:
        """Удалить запланированную рассылку"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE scheduled_mailings 
                    SET is_active = 0 
                    WHERE id = ?
                """, (schedule_id,))
                return True
        except Exception as e:
            logger.error(f"Error deleting scheduled mailing: {e}")
            return False
    
    def get_active_scheduled_mailings(self) -> List[Dict]:
        """Получить все активные запланированные рассылки"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM scheduled_mailings
                    WHERE is_active = 1
                    ORDER BY created_at DESC
                """)
                
                schedules = []
                for row in cursor.fetchall():
                    schedule = dict(row)
                    # Парсим targets
                    if schedule.get('targets'):
                        try:
                            schedule['targets'] = schedule['targets'].split('|||')
                        except:
                            schedule['targets'] = []
                    
                    # Парсим account_ids
                    if schedule.get('account_ids'):
                        try:
                            schedule['account_ids'] = [int(x) for x in schedule['account_ids'].split(',') if x]
                        except:
                            schedule['account_ids'] = []
                    
                    schedules.append(schedule)
                
                return schedules
        except Exception as e:
            logger.error(f"Error getting active scheduled mailings: {e}")
            return []
    
    def add_scheduled_mailing(self, user_id: int, targets: List[str], 
                            account_ids: List[int], message_text: str = None,
                            message_photo: str = None, message_video: str = None,
                            message_caption: str = None, schedule_type: str = 'once',
                            schedule_time: str = None) -> Optional[int]:
        """Добавить запланированную рассылку"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Конвертируем списки в строки
                targets_str = '|||'.join(targets) if targets else ''
                account_ids_str = ','.join(map(str, account_ids)) if account_ids else ''
                
                cursor.execute("""
                    INSERT INTO scheduled_mailings 
                    (user_id, targets, account_ids, message_text, message_photo, 
                     message_video, message_caption, schedule_type, schedule_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, targets_str, account_ids_str, message_text, 
                      message_photo, message_video, message_caption, 
                      schedule_type, schedule_time))
                
                schedule_id = cursor.lastrowid
                logger.info(f"✅ Scheduled mailing created: #{schedule_id}")
                return schedule_id
        except Exception as e:
            logger.error(f"Error adding scheduled mailing: {e}")
            return None
    
    def update_scheduled_mailing_run(self, schedule_id: int) -> bool:
        """Обновить время последнего запуска"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE scheduled_mailings 
                    SET last_run = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (schedule_id,))
                return True
        except Exception as e:
            logger.error(f"Error updating scheduled mailing run: {e}")
            return False
    
    # ==================== ПЛАТЕЖИ ====================
    
    def add_payment(self, user_id: int, plan_id: str, amount: float) -> Optional[int]:
        """Добавить платёж"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO payments (user_id, plan_id, amount, status)
                    VALUES (?, ?, ?, 'pending')
                """, (user_id, plan_id, amount))
                payment_id = cursor.lastrowid
                logger.info(f"✅ Payment created: #{payment_id} for user {user_id}")
                return payment_id
        except Exception as e:
            logger.error(f"Error adding payment: {e}")
            return None
    
    def get_payment(self, payment_id: int) -> Optional[Dict]:
        """Получить платёж"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting payment: {e}")
            return None
    
    def get_pending_payments(self) -> List[Dict]:
        """Получить ожидающие платежи"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM payments 
                    WHERE status = 'pending'
                    ORDER BY created_at DESC
                """)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting pending payments: {e}")
            return []
    
    def update_payment_status(self, payment_id: int, status: str) -> bool:
        """Обновить статус платежа"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE payments 
                    SET status = ?, approved_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, payment_id))
                logger.info(f"✅ Payment #{payment_id} status: {status}")
                return True
        except Exception as e:
            logger.error(f"Error updating payment status: {e}")
            return False
    
    # ==================== СТАТИСТИКА ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить общую статистику"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                stats = {}
                
                # Пользователи
                cursor.execute("SELECT COUNT(*) as count FROM users")
                stats['total_users'] = cursor.fetchone()['count']
                
                cursor.execute("""
                    SELECT COUNT(*) as count FROM users 
                    WHERE subscription_end > datetime('now')
                """)
                stats['active_subscriptions'] = cursor.fetchone()['count']
                
                cursor.execute("""
                    SELECT COUNT(*) as count FROM users 
                    WHERE DATE(created_at) = DATE('now')
                """)
                stats['new_today'] = cursor.fetchone()['count']
                
                # Аккаунты
                cursor.execute("SELECT COUNT(*) as count FROM accounts WHERE is_active = 1")
                stats['total_accounts'] = cursor.fetchone()['count']
                stats['active_accounts'] = stats['total_accounts']
                
                # Рассылки
                cursor.execute("SELECT COUNT(*) as count FROM mailings")
                stats['total_mailings'] = cursor.fetchone()['count']
                
                cursor.execute("""
                    SELECT COUNT(*) as count FROM mailings 
                    WHERE DATE(created_at) = DATE('now')
                """)
                stats['mailings_today'] = cursor.fetchone()['count']
                
                cursor.execute("SELECT SUM(sent_count) as total FROM mailings")
                row = cursor.fetchone()
                stats['total_sent'] = row['total'] if row['total'] else 0
                
                # По тарифам
                for plan in ['trial', 'amateur', 'professional', 'premium']:
                    cursor.execute("""
                        SELECT COUNT(*) as count FROM users 
                        WHERE subscription_plan = ? AND subscription_end > datetime('now')
                    """, (plan,))
                    stats[f'{plan}_users'] = cursor.fetchone()['count']
                
                # Запланированные
                cursor.execute("""
                    SELECT COUNT(*) as count FROM scheduled_mailings 
                    WHERE is_active = 1
                """)
                stats['total_scheduled'] = cursor.fetchone()['count']
                
                # Платежи
                cursor.execute("""
                    SELECT COUNT(*) as count FROM payments 
                    WHERE status = 'pending'
                """)
                stats['pending_payments'] = cursor.fetchone()['count']
                
                cursor.execute("""
                    SELECT COUNT(*) as count FROM payments 
                    WHERE status = 'approved'
                """)
                stats['approved_payments'] = cursor.fetchone()['count']
                
                return stats
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}


if __name__ == '__main__':
    # Тест
    db = Database()
    print("✅ Database initialized successfully")
    
    # Тест создания пользователя
    db.add_user(123456789, "test_user")
    user = db.get_user(123456789)
    print(f"✅ Test user: {user}")
    
    # Тест статистики
    stats = db.get_stats()
    print(f"✅ Stats: {stats}")