#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль для работы с базой данных SQLite
"""

import sqlite3
import logging
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class Database:
    """Класс для работы с базой данных"""
    
    def __init__(self, db_path: str = 'bot.db'):
        """Инициализация подключения к БД"""
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        logger.info(f"✅ Database connected: {db_path}")
        self.create_tables()
    
    def create_tables(self):
        """Создание всех необходимых таблиц"""
        
        # Таблица пользователей
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                is_admin BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # НОВАЯ: Таблица аккаунтов (мультиаккаунт)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                phone_number TEXT NOT NULL,
                session_id TEXT NOT NULL,
                account_name TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица рассылок
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS mailings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                sent_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # НОВАЯ: Таблица запланированных рассылок
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_mailings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                targets TEXT NOT NULL,
                message_text TEXT,
                message_photo TEXT,
                message_video TEXT,
                message_caption TEXT,
                schedule_type TEXT NOT NULL,
                schedule_data TEXT NOT NULL,
                selected_accounts TEXT,
                is_active BOOLEAN DEFAULT 1,
                last_run TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        self.connection.commit()
        logger.info("✅ All tables created successfully")
    
    # ==================== ПОЛЬЗОВАТЕЛИ ====================
    
    def add_user(self, user_id: int, username: str = None):
        """Добавление пользователя"""
        try:
            self.cursor.execute(
                'INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)',
                (user_id, username)
            )
            self.connection.commit()
            logger.info(f"✅ User added: {user_id}")
        except Exception as e:
            logger.error(f"❌ Error adding user: {e}")
    
    def get_user(self, user_id: int):
        """Получение данных пользователя"""
        try:
            self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = self.cursor.fetchone()
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"❌ Error getting user: {e}")
            return None
    
    def is_admin(self, user_id: int) -> bool:
        """Проверка прав администратора"""
        try:
            self.cursor.execute('SELECT is_admin FROM users WHERE user_id = ?', (user_id,))
            result = self.cursor.fetchone()
            return bool(result[0]) if result else False
        except Exception as e:
            logger.error(f"❌ Error checking admin: {e}")
            return False
    
    def set_admin(self, user_id: int, is_admin: bool = True):
        """Установка прав администратора"""
        try:
            self.cursor.execute(
                'UPDATE users SET is_admin = ? WHERE user_id = ?',
                (int(is_admin), user_id)
            )
            self.connection.commit()
            logger.info(f"✅ Admin status set for {user_id}: {is_admin}")
        except Exception as e:
            logger.error(f"❌ Error setting admin: {e}")
    
    # ==================== АККАУНТЫ (НОВОЕ) ====================
    
    def add_account(self, user_id: int, phone_number: str, session_id: str, account_name: str = None):
        """Добавление нового аккаунта"""
        try:
            if not account_name:
                account_name = f"Аккаунт {phone_number[-4:]}"
            
            self.cursor.execute('''
                INSERT INTO accounts (user_id, phone_number, session_id, account_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, phone_number, session_id, account_name))
            self.connection.commit()
            logger.info(f"✅ Account added: {phone_number} for user {user_id}")
            return self.cursor.lastrowid
        except Exception as e:
            logger.error(f"❌ Error adding account: {e}")
            return None
    
    def get_user_accounts(self, user_id: int, active_only: bool = True):
        """Получение всех аккаунтов пользователя"""
        try:
            if active_only:
                self.cursor.execute('''
                    SELECT * FROM accounts 
                    WHERE user_id = ? AND is_active = 1
                    ORDER BY created_at DESC
                ''', (user_id,))
            else:
                self.cursor.execute('''
                    SELECT * FROM accounts 
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                ''', (user_id,))
            
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error getting accounts: {e}")
            return []
    
    def get_account(self, account_id: int):
        """Получение конкретного аккаунта"""
        try:
            self.cursor.execute('SELECT * FROM accounts WHERE id = ?', (account_id,))
            row = self.cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ Error getting account: {e}")
            return None
    
    def get_account_by_phone(self, user_id: int, phone_number: str):
        """Получение аккаунта по номеру телефона"""
        try:
            self.cursor.execute('''
                SELECT * FROM accounts 
                WHERE user_id = ? AND phone_number = ?
            ''', (user_id, phone_number))
            row = self.cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ Error getting account by phone: {e}")
            return None
    
    def update_account_name(self, account_id: int, new_name: str):
        """Обновление имени аккаунта"""
        try:
            self.cursor.execute('''
                UPDATE accounts SET account_name = ?
                WHERE id = ?
            ''', (new_name, account_id))
            self.connection.commit()
            logger.info(f"✅ Account name updated: {account_id}")
        except Exception as e:
            logger.error(f"❌ Error updating account name: {e}")
    
    def delete_account(self, account_id: int):
        """Удаление аккаунта (мягкое удаление)"""
        try:
            self.cursor.execute('''
                UPDATE accounts SET is_active = 0
                WHERE id = ?
            ''', (account_id,))
            self.connection.commit()
            logger.info(f"✅ Account deactivated: {account_id}")
        except Exception as e:
            logger.error(f"❌ Error deleting account: {e}")
    
    def hard_delete_account(self, account_id: int):
        """Полное удаление аккаунта из БД"""
        try:
            self.cursor.execute('DELETE FROM accounts WHERE id = ?', (account_id,))
            self.connection.commit()
            logger.info(f"✅ Account permanently deleted: {account_id}")
        except Exception as e:
            logger.error(f"❌ Error hard deleting account: {e}")
    
    # ==================== РАССЫЛКИ ====================
    
    def add_mailing(self, user_id: int, message: str, sent_count: int, error_count: int):
        """Добавление записи о рассылке"""
        try:
            self.cursor.execute('''
                INSERT INTO mailings (user_id, message, sent_count, error_count)
                VALUES (?, ?, ?, ?)
            ''', (user_id, message, sent_count, error_count))
            self.connection.commit()
            logger.info(f"✅ Mailing added for user {user_id}")
        except Exception as e:
            logger.error(f"❌ Error adding mailing: {e}")
    
    def get_user_mailings(self, user_id: int, limit: int = 10):
        """Получение истории рассылок пользователя"""
        try:
            self.cursor.execute('''
                SELECT * FROM mailings 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (user_id, limit))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error getting mailings: {e}")
            return []
    
    # ==================== ЗАПЛАНИРОВАННЫЕ РАССЫЛКИ (НОВОЕ) ====================
    
    def add_scheduled_mailing(self, user_id: int, targets: list, message_data: dict, 
                             schedule_type: str, schedule_data: dict, selected_accounts: list = None):
        """Добавление запланированной рассылки"""
        try:
            self.cursor.execute('''
                INSERT INTO scheduled_mailings 
                (user_id, targets, message_text, message_photo, message_video, 
                 message_caption, schedule_type, schedule_data, selected_accounts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                json.dumps(targets),
                message_data.get('text'),
                message_data.get('photo'),
                message_data.get('video'),
                message_data.get('caption'),
                schedule_type,
                json.dumps(schedule_data),
                json.dumps(selected_accounts) if selected_accounts else None
            ))
            self.connection.commit()
            logger.info(f"✅ Scheduled mailing added for user {user_id}")
            return self.cursor.lastrowid
        except Exception as e:
            logger.error(f"❌ Error adding scheduled mailing: {e}")
            return None
    
    def get_active_scheduled_mailings(self):
        """Получение всех активных запланированных рассылок"""
        try:
            self.cursor.execute('''
                SELECT * FROM scheduled_mailings 
                WHERE is_active = 1
                ORDER BY created_at DESC
            ''')
            rows = self.cursor.fetchall()
            result = []
            for row in rows:
                data = dict(row)
                data['targets'] = json.loads(data['targets'])
                data['schedule_data'] = json.loads(data['schedule_data'])
                if data['selected_accounts']:
                    data['selected_accounts'] = json.loads(data['selected_accounts'])
                result.append(data)
            return result
        except Exception as e:
            logger.error(f"❌ Error getting scheduled mailings: {e}")
            return []
    
    def get_user_scheduled_mailings(self, user_id: int):
        """Получение запланированных рассылок пользователя"""
        try:
            self.cursor.execute('''
                SELECT * FROM scheduled_mailings 
                WHERE user_id = ? AND is_active = 1
                ORDER BY created_at DESC
            ''', (user_id,))
            rows = self.cursor.fetchall()
            result = []
            for row in rows:
                data = dict(row)
                data['targets'] = json.loads(data['targets'])
                data['schedule_data'] = json.loads(data['schedule_data'])
                if data['selected_accounts']:
                    data['selected_accounts'] = json.loads(data['selected_accounts'])
                result.append(data)
            return result
        except Exception as e:
            logger.error(f"❌ Error getting user scheduled mailings: {e}")
            return []
    
    def update_scheduled_mailing_last_run(self, mailing_id: int):
        """Обновление времени последнего запуска"""
        try:
            self.cursor.execute('''
                UPDATE scheduled_mailings 
                SET last_run = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (mailing_id,))
            self.connection.commit()
        except Exception as e:
            logger.error(f"❌ Error updating last run: {e}")
    
    def delete_scheduled_mailing(self, mailing_id: int):
        """Удаление запланированной рассылки"""
        try:
            self.cursor.execute('''
                UPDATE scheduled_mailings 
                SET is_active = 0
                WHERE id = ?
            ''', (mailing_id,))
            self.connection.commit()
            logger.info(f"✅ Scheduled mailing deleted: {mailing_id}")
        except Exception as e:
            logger.error(f"❌ Error deleting scheduled mailing: {e}")
    
    # ==================== УТИЛИТЫ ====================
    
    def get_stats(self):
        """Получение общей статистики"""
        try:
            self.cursor.execute('SELECT COUNT(*) FROM users')
            total_users = self.cursor.fetchone()[0]
            
            self.cursor.execute('SELECT COUNT(*) FROM accounts WHERE is_active = 1')
            total_accounts = self.cursor.fetchone()[0]
            
            self.cursor.execute('SELECT COUNT(*) FROM mailings')
            total_mailings = self.cursor.fetchone()[0]
            
            self.cursor.execute('SELECT COUNT(*) FROM scheduled_mailings WHERE is_active = 1')
            total_scheduled = self.cursor.fetchone()[0]
            
            return {
                'total_users': total_users,
                'total_accounts': total_accounts,
                'total_mailings': total_mailings,
                'total_scheduled': total_scheduled
            }
        except Exception as e:
            logger.error(f"❌ Error getting stats: {e}")
            return {}
    
    def close(self):
        """Закрытие соединения"""
        self.connection.close()
        logger.info("❌ Database connection closed")