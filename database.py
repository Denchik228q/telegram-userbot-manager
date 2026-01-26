#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
База данных для Telegram Manager Bot
"""

import sqlite3
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class Database:
    """Класс для работы с базой данных SQLite"""
    
    def __init__(self, db_path: str = 'bot.db'):
        """Инициализация базы данных"""
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self.connect()
        self.create_tables()
    
    def connect(self):
        """Подключение к базе данных"""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.cursor = self.conn.cursor()
            logger.info(f"✅ Database connected: {self.db_path}")
        except Exception as e:
            logger.error(f"❌ Database connection error: {e}")
            raise
    
    def create_tables(self):
        """Создание таблиц"""
        try:
            # Таблица пользователей
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    phone_number TEXT,
                    session_id TEXT,
                    subscription_plan TEXT DEFAULT 'trial',
                    subscription_end TIMESTAMP,
                    is_banned BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("✅ Table 'users' created")
            
            # Таблица платежей
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    plan TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id)
                )
            """)
            logger.info("✅ Table 'payments' created")
            
            # Таблица рассылок
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS mailings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message_text TEXT,
                    sent_count INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id)
                )
            """)
            logger.info("✅ Table 'mailings' created")
            
            # Таблица обращений в поддержку
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT DEFAULT 'open',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id)
                )
            """)
            logger.info("✅ Table 'support_tickets' created")
            
            self.conn.commit()
            logger.info("✅ All tables created/updated successfully")
            
        except Exception as e:
            logger.error(f"❌ Error creating tables: {e}")
            raise
    
    # ============= ПОЛЬЗОВАТЕЛИ =============
    
    def add_user(self, telegram_id: int, username: str = "", first_name: str = "", 
                 subscription_plan: str = "trial", subscription_end: datetime = None):
        """Добавление нового пользователя"""
        try:
            if subscription_end is None:
                subscription_end = datetime.now() + timedelta(days=3)
            
            self.cursor.execute("""
                INSERT INTO users (telegram_id, username, first_name, subscription_plan, subscription_end)
                VALUES (?, ?, ?, ?, ?)
            """, (telegram_id, username, first_name, subscription_plan, subscription_end))
            
            self.conn.commit()
            logger.info(f"✅ User registered: {telegram_id}")
            return True
            
        except sqlite3.IntegrityError:
            logger.warning(f"⚠️ User {telegram_id} already exists")
            return False
        except Exception as e:
            logger.error(f"❌ Error adding user: {e}")
            return False
    
    def get_user(self, telegram_id: int) -> Optional[Dict]:
        """Получение пользователя по Telegram ID"""
        try:
            self.cursor.execute("""
                SELECT * FROM users WHERE telegram_id = ?
            """, (telegram_id,))
            
            row = self.cursor.fetchone()
            
            if row:
                return {
                    'id': row['id'],
                    'telegram_id': row['telegram_id'],
                    'username': row['username'],
                    'first_name': row['first_name'],
                    'phone_number': row['phone_number'],
                    'session_id': row['session_id'],
                    'subscription_plan': row['subscription_plan'],
                    'subscription_end': datetime.fromisoformat(row['subscription_end']) if row['subscription_end'] else None,
                    'is_banned': bool(row['is_banned']),
                    'created_at': datetime.fromisoformat(row['created_at']),
                    'updated_at': datetime.fromisoformat(row['updated_at'])
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting user: {e}")
            return None
    
    def get_all_users(self) -> List[Dict]:
        """Получение всех пользователей"""
        try:
            self.cursor.execute("SELECT * FROM users WHERE is_banned = 0")
            rows = self.cursor.fetchall()
            
            users = []
            for row in rows:
                users.append({
                    'id': row['id'],
                    'telegram_id': row['telegram_id'],
                    'username': row['username'],
                    'first_name': row['first_name'],
                    'phone_number': row['phone_number'],
                    'session_id': row['session_id'],
                    'subscription_plan': row['subscription_plan'],
                    'subscription_end': datetime.fromisoformat(row['subscription_end']) if row['subscription_end'] else None,
                    'is_banned': bool(row['is_banned']),
                    'created_at': datetime.fromisoformat(row['created_at']),
                    'updated_at': datetime.fromisoformat(row['updated_at'])
                })
            
            return users
            
        except Exception as e:
            logger.error(f"❌ Error getting all users: {e}")
            return []
    
    def update_user(self, telegram_id: int, **kwargs):
        """Обновление данных пользователя"""
        try:
            # Разрешенные поля для обновления
            allowed_fields = ['username', 'first_name', 'phone_number', 'session_id', 
                            'subscription_plan', 'subscription_end', 'is_banned']
            
            updates = []
            values = []
            
            for key, value in kwargs.items():
                if key in allowed_fields:
                    updates.append(f"{key} = ?")
                    values.append(value)
            
            if not updates:
                logger.warning("⚠️ No valid fields to update")
                return False
            
            # Добавляем updated_at
            updates.append("updated_at = ?")
            values.append(datetime.now())
            
            # Добавляем telegram_id в конец для WHERE
            values.append(telegram_id)
            
            query = f"UPDATE users SET {', '.join(updates)} WHERE telegram_id = ?"
            
            self.cursor.execute(query, values)
            self.conn.commit()
            
            logger.info(f"✅ User {telegram_id} updated")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating user: {e}")
            return False
    
    def ban_user(self, telegram_id: int):
        """Блокировка пользователя"""
        return self.update_user(telegram_id, is_banned=1)
    
    def unban_user(self, telegram_id: int):
        """Разблокировка пользователя"""
        return self.update_user(telegram_id, is_banned=0)
    
    # ============= ПЛАТЕЖИ =============
    
    def add_payment(self, user_id: int, amount: float, plan: str, status: str = 'pending'):
        """Добавление платежа"""
        try:
            self.cursor.execute("""
                INSERT INTO payments (user_id, amount, plan, status)
                VALUES (?, ?, ?, ?)
            """, (user_id, amount, plan, status))
            
            self.conn.commit()
            logger.info(f"✅ Payment added for user {user_id}")
            return self.cursor.lastrowid
            
        except Exception as e:
            logger.error(f"❌ Error adding payment: {e}")
            return None
    
    def get_payments(self, user_id: int = None) -> List[Dict]:
        """Получение платежей"""
        try:
            if user_id:
                self.cursor.execute("""
                    SELECT * FROM payments WHERE user_id = ? ORDER BY created_at DESC
                """, (user_id,))
            else:
                self.cursor.execute("""
                    SELECT * FROM payments ORDER BY created_at DESC
                """)
            
            rows = self.cursor.fetchall()
            
            payments = []
            for row in rows:
                payments.append({
                    'id': row['id'],
                    'user_id': row['user_id'],
                    'amount': row['amount'],
                    'plan': row['plan'],
                    'status': row['status'],
                    'created_at': datetime.fromisoformat(row['created_at'])
                })
            
            return payments
            
        except Exception as e:
            logger.error(f"❌ Error getting payments: {e}")
            return []
    
    def update_payment_status(self, payment_id: int, status: str):
        """Обновление статуса платежа"""
        try:
            self.cursor.execute("""
                UPDATE payments SET status = ? WHERE id = ?
            """, (status, payment_id))
            
            self.conn.commit()
            logger.info(f"✅ Payment {payment_id} status updated to {status}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating payment status: {e}")
            return False
    
    # ============= РАССЫЛКИ =============
    
    def add_mailing(self, user_id: int, message_text: str, sent_count: int = 0, error_count: int = 0):
        """Добавление рассылки"""
        try:
            self.cursor.execute("""
                INSERT INTO mailings (user_id, message_text, sent_count, error_count)
                VALUES (?, ?, ?, ?)
            """, (user_id, message_text, sent_count, error_count))
            
            self.conn.commit()
            logger.info(f"✅ Mailing added for user {user_id}")
            return self.cursor.lastrowid
            
        except Exception as e:
            logger.error(f"❌ Error adding mailing: {e}")
            return None
    
    # ============= ПОДДЕРЖКА =============
    
    def add_support_ticket(self, user_id: int, message: str):
        """Добавление обращения в поддержку"""
        try:
            self.cursor.execute("""
                INSERT INTO support_tickets (user_id, message)
                VALUES (?, ?)
            """, (user_id, message))
            
            self.conn.commit()
            logger.info(f"✅ Support ticket created for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error creating support ticket: {e}")
            return False
    
    def get_support_tickets(self, status: str = None) -> List[Dict]:
        """Получение обращений в поддержку"""
        try:
            if status:
                self.cursor.execute("""
                    SELECT * FROM support_tickets WHERE status = ? ORDER BY created_at DESC
                """, (status,))
            else:
                self.cursor.execute("""
                    SELECT * FROM support_tickets ORDER BY created_at DESC
                """)
            
            rows = self.cursor.fetchall()
            
            tickets = []
            for row in rows:
                tickets.append({
                    'id': row['id'],
                    'user_id': row['user_id'],
                    'message': row['message'],
                    'status': row['status'],
                    'created_at': datetime.fromisoformat(row['created_at'])
                })
            
            return tickets
            
        except Exception as e:
            logger.error(f"❌ Error getting support tickets: {e}")
            return []
    
    # ============= СТАТИСТИКА =============
    
    def get_stats(self) -> Dict:
        """Получение статистики"""
        try:
            stats = {}
            
            # Всего пользователей
            self.cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_banned = 0")
            stats['total_users'] = self.cursor.fetchone()['count']
            
            # Активные подписки
            self.cursor.execute("""
                SELECT COUNT(*) as count FROM users 
                WHERE subscription_end > ? AND subscription_plan != 'trial' AND is_banned = 0
            """, (datetime.now(),))
            stats['active_subscriptions'] = self.cursor.fetchone()['count']
            
            # Новые пользователи за сегодня
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            self.cursor.execute("""
                SELECT COUNT(*) as count FROM users WHERE created_at >= ?
            """, (today,))
            stats['new_today'] = self.cursor.fetchone()['count']
            
            # Новые за неделю
            week_ago = datetime.now() - timedelta(days=7)
            self.cursor.execute("""
                SELECT COUNT(*) as count FROM users WHERE created_at >= ?
            """, (week_ago,))
            stats['new_week'] = self.cursor.fetchone()['count']
            
            # По тарифам
            for plan in ['trial', 'amateur', 'pro', 'premium']:
                self.cursor.execute("""
                    SELECT COUNT(*) as count FROM users 
                    WHERE subscription_plan = ? AND is_banned = 0
                """, (plan,))
                stats[f'{plan}_users'] = self.cursor.fetchone()['count']
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error getting stats: {e}")
            return {}
    
    # ============= БЭКАП =============
    
    def backup_database(self) -> str:
        """Создание бэкапа базы данных"""
        try:
            # Создаём директорию для бэкапов
            backup_dir = 'backups'
            os.makedirs(backup_dir, exist_ok=True)
            
            # Имя файла бэкапа
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = os.path.join(backup_dir, f'backup_{timestamp}.db')
            
            # Копируем базу данных
            import shutil
            shutil.copy2(self.db_path, backup_path)
            
            logger.info(f"✅ Database backup created: {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"❌ Error creating backup: {e}")
            raise
    
    def close(self):
        """Закрытие соединения с БД"""
        if self.conn:
            self.conn.close()
            logger.info("✅ Database connection closed")