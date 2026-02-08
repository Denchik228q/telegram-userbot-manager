#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Database module for Telegram Bot Manager
Все отступы - 4 пробела (без табов)
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class Database:
    """Класс для работы с базой данных"""
    
    def __init__(self, db_path: str = 'bot_database.db'):
        """Инициализация базы данных"""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()
        logger.info("✅ Database initialized")
    
    def _create_tables(self):
        """Создание таблиц"""
        cursor = self.conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                subscription_plan TEXT DEFAULT 'trial',
                subscription_end TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица аккаунтов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                phone TEXT,
                session_id TEXT,
                account_name TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Таблица рассылок
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mailings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                status TEXT,
                targets TEXT,
                message TEXT,
                accounts_used INTEGER,
                success_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Таблица расписаний
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                targets TEXT,
                message TEXT,
                accounts TEXT,
                schedule_type TEXT,
                schedule_time TEXT,
                is_active INTEGER DEFAULT 1,
                last_run TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Таблица платежей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                plan_id TEXT,
                amount INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        self.conn.commit()
        logger.info("✅ Database tables created/updated successfully")
    
    # ==================== ПОЛЬЗОВАТЕЛИ ====================
    
    def add_user(self, user_id, username=None, first_name=None, last_name=None):
        """Добавить или обновить пользователя"""
    try:
        cursor = self.conn.cursor()
        
        # Проверяем существует ли
        cursor.execute("SELECT id FROM users WHERE user_id = ?", (user_id,))
        exists = cursor.fetchone()
        
        if exists:
            # Обновляем
            cursor.execute("""
                UPDATE users 
                SET username = ?, first_name = ?, last_name = ?, last_active = ?
                WHERE user_id = ?
            """, (username, first_name, last_name, datetime.now(), user_id))
        else:
            # Создаём нового
            cursor.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, subscription_plan, subscription_end)
                VALUES (?, ?, ?, ?, 'trial', datetime('now', '+7 days'))
            """, (user_id, username, first_name, last_name))
        
        self.conn.commit()
        logger.info(f"✅ User {user_id} registered/updated successfully")
        return True
        
        except Exception as e:
        logger.error(f"Error adding user: {e}")
            self.conn.rollback()
            return False
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Получить данные пользователя"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # Парсим дату из строки
            subscription_end = row[3]
            if isinstance(subscription_end, str):
                try:
                    subscription_end = datetime.fromisoformat(subscription_end)
                except:
                    try:
                        subscription_end = datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S.%f')
                    except:
                        subscription_end = datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S')
            
            return {
                'id': row[0],
                'username': row[1],
                'subscription_plan': row[2],
                'subscription_end': subscription_end,
                'created_at': row[4]
            }
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None
    
    def update_user_subscription(self, user_id: int, plan_id: str, days: int) -> bool:
        """Обновить подписку пользователя"""
        try:
            cursor = self.conn.cursor()
            new_end = datetime.now() + timedelta(days=days)
            
            cursor.execute('''
                UPDATE users 
                SET subscription_plan = ?, subscription_end = ?
                WHERE id = ?
            ''', (plan_id, new_end, user_id))
            
            self.conn.commit()
            logger.info(f"✅ Subscription updated for user {user_id}: {plan_id} for {days} days")
            return True
        except Exception as e:
            logger.error(f"Error updating subscription: {e}")
            return False
    
    def get_all_users(self) -> List[Dict]:
        """Получить всех пользователей"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM users ORDER BY created_at DESC')
            rows = cursor.fetchall()
            
            users = []
            for row in rows:
                # Парсим дату
                subscription_end = row[3]
                if isinstance(subscription_end, str):
                    try:
                        subscription_end = datetime.fromisoformat(subscription_end)
                    except:
                        try:
                            subscription_end = datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S.%f')
                        except:
                            subscription_end = datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S')
                
                users.append({
                    'id': row[0],
                    'username': row[1],
                    'subscription_plan': row[2],
                    'subscription_end': subscription_end,
                    'created_at': row[4]
                })
            
            return users
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []
    
    # ==================== АККАУНТЫ ====================
    
    def add_account(self, user_id: int, phone: str, session_id: str, account_name: str) -> Optional[int]:
        """Добавить аккаунт"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO accounts (user_id, phone, session_id, account_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, phone, session_id, account_name))
            
            self.conn.commit()
            account_id = cursor.lastrowid
            logger.info(f"✅ Account added: {phone} for user {user_id}")
            return account_id
        except Exception as e:
            logger.error(f"Error adding account: {e}")
            return None
    
    def get_user_accounts(self, user_id: int) -> List[Dict]:
        """Получить аккаунты пользователя"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM accounts 
                WHERE user_id = ? AND is_active = 1
                ORDER BY created_at DESC
            ''', (user_id,))
            rows = cursor.fetchall()
            
            return [{
                'id': row[0],
                'user_id': row[1],
                'phone': row[2],
                'session_id': row[3],
                'account_name': row[4],
                'is_active': row[5],
                'created_at': row[6]
            } for row in rows]
        except Exception as e:
            logger.error(f"Error getting accounts: {e}")
            return []
    
    def get_account(self, account_id: int) -> Optional[Dict]:
        """Получить аккаунт по ID"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM accounts WHERE id = ?', (account_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return {
                'id': row[0],
                'user_id': row[1],
                'phone': row[2],
                'session_id': row[3],
                'account_name': row[4],
                'is_active': row[5],
                'created_at': row[6]
            }
        except Exception as e:
            logger.error(f"Error getting account: {e}")
            return None
    
    def delete_account(self, account_id: int) -> bool:
        """Удалить аккаунт"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('UPDATE accounts SET is_active = 0 WHERE id = ?', (account_id,))
            self.conn.commit()
            logger.info(f"✅ Account {account_id} deleted")
            return True
        except Exception as e:
            logger.error(f"Error deleting account: {e}")
            return False
    
    # ==================== РАССЫЛКИ ====================
    
    def add_mailing(self, user_id: int, targets: str, message: str, accounts_used: int) -> Optional[int]:
        """Добавить рассылку"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO mailings (user_id, status, targets, message, accounts_used)
                VALUES (?, 'running', ?, ?, ?)
            ''', (user_id, targets, message, accounts_used))
            
            self.conn.commit()
            mailing_id = cursor.lastrowid
            logger.info(f"✅ Mailing created: #{mailing_id} for user {user_id}")
            return mailing_id
        except Exception as e:
            logger.error(f"Error adding mailing: {e}")
            return None
    
    def update_mailing_status(self, mailing_id: int, status: str, success: int = 0, errors: int = 0) -> bool:
        """Обновить статус рассылки"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE mailings 
                SET status = ?, success_count = ?, error_count = ?
                WHERE id = ?
            ''', (status, success, errors, mailing_id))
            
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating mailing: {e}")
            return False
    
    def get_user_mailings(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Получить рассылки пользователя"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM mailings 
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (user_id, limit))
            rows = cursor.fetchall()
            
            return [{
                'id': row[0],
                'user_id': row[1],
                'status': row[2],
                'targets': row[3],
                'message': row[4],
                'accounts_used': row[5],
                'success_count': row[6],
                'error_count': row[7],
                'created_at': row[8]
            } for row in rows]
        except Exception as e:
            logger.error(f"Error getting mailings: {e}")
            return []
    
    def get_user_mailings_today(self, user_id: int) -> int:
        """Получить количество рассылок пользователя за сегодня"""
        try:
            cursor = self.conn.cursor()
            today = datetime.now().date()
            cursor.execute('''
                SELECT COUNT(*) FROM mailings 
                WHERE user_id = ? AND DATE(created_at) = ?
            ''', (user_id, today))
            
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error counting mailings: {e}")
            return 0
    
    # ==================== ПЛАТЕЖИ ====================
    
    def add_payment(self, user_id: int, plan_id: str, amount: int) -> Optional[int]:
        """Создать новый платеж"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO payments (user_id, plan_id, amount, status, created_at)
                VALUES (?, ?, ?, 'pending', ?)
            ''', (user_id, plan_id, amount, datetime.now()))
            
            self.conn.commit()
            payment_id = cursor.lastrowid
            logger.info(f"✅ Payment created: #{payment_id} for user {user_id}")
            return payment_id
        except Exception as e:
            logger.error(f"Error creating payment: {e}")
            return None
    
    def get_payment(self, payment_id: int) -> Optional[Dict]:
        """Получить данные платежа"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM payments WHERE id = ?', (payment_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return {
                'id': row[0],
                'user_id': row[1],
                'plan_id': row[2],
                'amount': row[3],
                'status': row[4],
                'created_at': row[5]
            }
        except Exception as e:
            logger.error(f"Error getting payment: {e}")
            return None
    
    def update_payment_status(self, payment_id: int, status: str) -> bool:
        """Обновить статус платежа"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE payments SET status = ? WHERE id = ?
            ''', (status, payment_id))
            
            self.conn.commit()
            logger.info(f"✅ Payment #{payment_id} status updated: {status}")
            return True
        except Exception as e:
            logger.error(f"Error updating payment status: {e}")
            return False
    
    def get_pending_payments(self) -> List[Dict]:
        """Получить ожидающие платежи"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM payments 
                WHERE status = 'pending'
                ORDER BY created_at DESC
            ''')
            rows = cursor.fetchall()
            
            return [{
                'id': row[0],
                'user_id': row[1],
                'plan_id': row[2],
                'amount': row[3],
                'status': row[4],
                'created_at': row[5]
            } for row in rows]
        except Exception as e:
            logger.error(f"Error getting pending payments: {e}")
            return []
    
    # ==================== РАСПИСАНИЯ ====================
    
    def add_schedule(self, user_id: int, targets: str, message: str, accounts: str, 
                     schedule_type: str, schedule_time: str) -> Optional[int]:
        """Добавить расписание"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO schedules (user_id, targets, message, accounts, schedule_type, schedule_time)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, targets, message, accounts, schedule_type, schedule_time))
            
            self.conn.commit()
            schedule_id = cursor.lastrowid
            logger.info(f"✅ Schedule created: #{schedule_id} for user {user_id}")
            return schedule_id
        except Exception as e:
            logger.error(f"Error creating schedule: {e}")
            return None
    
    def get_user_schedules(self, user_id: int) -> List[Dict]:
        """Получить расписания пользователя"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM schedules 
                WHERE user_id = ? AND is_active = 1
                ORDER BY created_at DESC
            ''', (user_id,))
            rows = cursor.fetchall()
            
            return [{
                'id': row[0],
                'user_id': row[1],
                'targets': row[2],
                'message': row[3],
                'accounts': row[4],
                'schedule_type': row[5],
                'schedule_time': row[6],
                'is_active': row[7],
                'last_run': row[8],
                'created_at': row[9]
            } for row in rows]
        except Exception as e:
            logger.error(f"Error getting schedules: {e}")
            return []
    
    def get_schedule(self, schedule_id: int) -> Optional[Dict]:
        """Получить расписание по ID"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM schedules WHERE id = ?', (schedule_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return {
                'id': row[0],
                'user_id': row[1],
                'targets': row[2],
                'message': row[3],
                'accounts': row[4],
                'schedule_type': row[5],
                'schedule_time': row[6],
                'is_active': row[7],
                'last_run': row[8],
                'created_at': row[9]
            }
        except Exception as e:
            logger.error(f"Error getting schedule: {e}")
            return None
    
    def delete_schedule(self, schedule_id: int) -> bool:
        """Удалить расписание"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('UPDATE schedules SET is_active = 0 WHERE id = ?', (schedule_id,))
            self.conn.commit()
            logger.info(f"✅ Schedule {schedule_id} deleted")
            return True
        except Exception as e:
            logger.error(f"Error deleting schedule: {e}")
            return False
    
    def get_all_active_schedules(self) -> List[Dict]:
        """Получить все активные расписания"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM schedules WHERE is_active = 1')
            rows = cursor.fetchall()
            
            return [{
                'id': row[0],
                'user_id': row[1],
                'targets': row[2],
                'message': row[3],
                'accounts': row[4],
                'schedule_type': row[5],
                'schedule_time': row[6],
                'is_active': row[7],
                'last_run': row[8],
                'created_at': row[9]
            } for row in rows]
        except Exception as e:
            logger.error(f"Error getting active schedules: {e}")
            return []
    
    def get_active_scheduled_mailings(self) -> List[Dict]:
        """
        Получить активные запланированные рассылки
        Алиас для get_all_active_schedules для совместимости со scheduler
        """
        return self.get_all_active_schedules()
    
    def update_schedule_last_run(self, schedule_id: int) -> bool:
        """Обновить время последнего запуска"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE schedules SET last_run = ? WHERE id = ?
            ''', (datetime.now(), schedule_id))
            
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating schedule last_run: {e}")
            return False
    
    # ==================== СТАТИСТИКА ====================
    
    def get_stats(self) -> Dict:
        """Получить общую статистику"""
        try:
            cursor = self.conn.cursor()
            
            # Пользователи
            cursor.execute('SELECT COUNT(*) FROM users')
            total_users = cursor.fetchone()[0]
            
            # Активные подписки
            cursor.execute('''
                SELECT COUNT(*) FROM users 
                WHERE subscription_end > ?
            ''', (datetime.now(),))
            active_subs = cursor.fetchone()[0]
            
            # Аккаунты
            cursor.execute('SELECT COUNT(*) FROM accounts WHERE is_active = 1')
            total_accounts = cursor.fetchone()[0]
            
            # Рассылки сегодня
            today = datetime.now().date()
            cursor.execute('''
                SELECT COUNT(*) FROM mailings 
                WHERE DATE(created_at) = ?
            ''', (today,))
            mailings_today = cursor.fetchone()[0]
            
            return {
                'total_users': total_users,
                'active_subscriptions': active_subs,
                'total_accounts': total_accounts,
                'mailings_today': mailings_today
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {
                'total_users': 0,
                'active_subscriptions': 0,
                'total_accounts': 0,
                'mailings_today': 0
            }
    
    def close(self):
        """Закрыть соединение с БД"""
        self.conn.close()
        logger.info("✅ Database connection closed")