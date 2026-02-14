import sqlite3
import logging
from typing import Optional, List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str = "bot_data.db"):
        """Инициализация базы данных"""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_tables()
        logger.info("✅ Database initialized successfully")

    def _create_tables(self):
        """Создание таблиц в БД"""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_admin BOOLEAN DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                subscription_end TIMESTAMP,
                messages_sent INTEGER DEFAULT 0,
                last_activity TIMESTAMP
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                phone TEXT UNIQUE,
                session_string TEXT,
                api_id INTEGER,
                api_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                last_used TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS mailings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                account_id INTEGER,
                message TEXT,
                recipients TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                total_recipients INTEGER DEFAULT 0,
                sent_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                account_id INTEGER,
                message TEXT,
                recipients TEXT,
                schedule_time TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            )
        """)

        self.conn.commit()

    def get_user(self, user_id: int) -> Optional[Dict]:
        """Получить пользователя"""
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = self.cursor.fetchone()
        if row:
            return {
                'user_id': row[0],
                'username': row[1],
                'first_name': row[2],
                'last_name': row[3],
                'created_at': row[4],
                'is_admin': row[5],
                'is_active': row[6],
                'subscription_end': row[7],
                'messages_sent': row[8],
                'last_activity': row[9]
            }
        return None

    def create_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        """Создать нового пользователя"""
        try:
            self.cursor.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, last_activity)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, username, first_name, last_name, datetime.now()))
            self.conn.commit()
            logger.info(f"✅ New user created: {user_id}")
        except sqlite3.IntegrityError:
            logger.warning(f"User {user_id} already exists")

    def update_user_activity(self, user_id: int):
        """Обновить последнюю активность пользователя"""
        self.cursor.execute("""
            UPDATE users SET last_activity = ? WHERE user_id = ?
        """, (datetime.now(), user_id))
        self.conn.commit()

    def get_all_users(self) -> List[Dict]:
        """Получить всех пользователей"""
        self.cursor.execute("SELECT * FROM users")
        rows = self.cursor.fetchall()
        return [{
            'user_id': row[0],
            'username': row[1],
            'first_name': row[2],
            'last_name': row[3],
            'created_at': row[4],
            'is_admin': row[5],
            'is_active': row[6],
            'subscription_end': row[7],
            'messages_sent': row[8],
            'last_activity': row[9]
        } for row in rows]

    def create_account(self, user_id: int, phone: str, session_string: str, api_id: int, api_hash: str) -> int:
        """Создать аккаунт"""
        self.cursor.execute("""
            INSERT INTO accounts (user_id, phone, session_string, api_id, api_hash, last_used)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, phone, session_string, api_id, api_hash, datetime.now()))
        self.conn.commit()
        return self.cursor.lastrowid

    def get_account(self, account_id: int) -> Optional[Dict]:
        """Получить аккаунт по ID"""
        self.cursor.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        row = self.cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'user_id': row[1],
                'phone': row[2],
                'session_string': row[3],
                'api_id': row[4],
                'api_hash': row[5],
                'created_at': row[6],
                'is_active': row[7],
                'last_used': row[8]
            }
        return None

    def get_account_by_phone(self, phone: str) -> Optional[Dict]:
        """Получить аккаунт по номеру телефона"""
        try:
            self.cursor.execute("SELECT * FROM accounts WHERE phone = ?", (phone,))
            row = self.cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'user_id': row[1],
                    'phone': row[2],
                    'session_string': row[3],
                    'api_id': row[4],
                    'api_hash': row[5],
                    'created_at': row[6],
                    'is_active': row[7],
                    'last_used': row[8]
                }
            return None
        except Exception as e:
            logger.error(f"Error getting account by phone: {e}")
            return None

    def get_user_accounts(self, user_id: int) -> List[Dict]:
        """Получить все аккаунты пользователя"""
        self.cursor.execute("SELECT * FROM accounts WHERE user_id = ?", (user_id,))
        rows = self.cursor.fetchall()
        return [{
            'id': row[0],
            'user_id': row[1],
            'phone': row[2],
            'session_string': row[3],
            'api_id': row[4],
            'api_hash': row[5],
            'created_at': row[6],
            'is_active': row[7],
            'last_used': row[8]
        } for row in rows]

    def delete_account(self, account_id: int):
        """Удалить аккаунт"""
        self.cursor.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        self.conn.commit()

    def update_account_session(self, account_id: int, session_string: str):
        """Обновить сессию аккаунта"""
        self.cursor.execute("""
            UPDATE accounts SET session_string = ?, last_used = ? WHERE id = ?
        """, (session_string, datetime.now(), account_id))
        self.conn.commit()

    def create_mailing(self, user_id: int, account_id: int, message: str, recipients: str, total_recipients: int) -> int:
        """Создать рассылку"""
        self.cursor.execute("""
            INSERT INTO mailings (user_id, account_id, message, recipients, total_recipients, started_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, account_id, message, recipients, total_recipients, datetime.now()))
        self.conn.commit()
        return self.cursor.lastrowid

    def get_mailing(self, mailing_id: int) -> Optional[Dict]:
        """Получить рассылку"""
        self.cursor.execute("SELECT * FROM mailings WHERE id = ?", (mailing_id,))
        row = self.cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'user_id': row[1],
                'account_id': row[2],
                'message': row[3],
                'recipients': row[4],
                'status': row[5],
                'created_at': row[6],
                'started_at': row[7],
                'completed_at': row[8],
                'total_recipients': row[9],
                'sent_count': row[10],
                'failed_count': row[11]
            }
        return None

    def get_user_mailings(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Получить рассылки пользователя"""
        self.cursor.execute("""
            SELECT * FROM mailings WHERE user_id = ? ORDER BY created_at DESC LIMIT ?
        """, (user_id, limit))
        rows = self.cursor.fetchall()
        return [{
            'id': row[0],
            'user_id': row[1],
            'account_id': row[2],
            'message': row[3],
            'recipients': row[4],
            'status': row[5],
            'created_at': row[6],
            'started_at': row[7],
            'completed_at': row[8],
            'total_recipients': row[9],
            'sent_count': row[10],
            'failed_count': row[11]
        } for row in rows]

    def update_mailing_status(self, mailing_id: int, status: str, sent_count: int = 0, failed_count: int = 0):
        """Обновить статус рассылки"""
        completed_at = datetime.now() if status == 'completed' else None
        self.cursor.execute("""
            UPDATE mailings 
            SET status = ?, sent_count = ?, failed_count = ?, completed_at = ?
            WHERE id = ?
        """, (status, sent_count, failed_count, completed_at, mailing_id))
        self.conn.commit()

    def create_schedule(self, user_id: int, account_id: int, message: str, recipients: str, schedule_time: str) -> int:
        """Создать расписание"""
        self.cursor.execute("""
            INSERT INTO schedules (user_id, account_id, message, recipients, schedule_time)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, account_id, message, recipients, schedule_time))
        self.conn.commit()
        return self.cursor.lastrowid

    def get_active_schedules(self) -> List[Dict]:
        """Получить активные расписания"""
        self.cursor.execute("SELECT * FROM schedules WHERE is_active = 1")
        rows = self.cursor.fetchall()
        return [{
            'id': row[0],
            'user_id': row[1],
            'account_id': row[2],
            'message': row[3],
            'recipients': row[4],
            'schedule_time': row[5],
            'is_active': row[6],
            'created_at': row[7]
        } for row in rows]

    def get_user_schedules(self, user_id: int) -> List[Dict]:
        """Получить расписания пользователя"""
        self.cursor.execute("SELECT * FROM schedules WHERE user_id = ?", (user_id,))
        rows = self.cursor.fetchall()
        return [{
            'id': row[0],
            'user_id': row[1],
            'account_id': row[2],
            'message': row[3],
            'recipients': row[4],
            'schedule_time': row[5],
            'is_active': row[6],
            'created_at': row[7]
        } for row in rows]

    def delete_schedule(self, schedule_id: int):
        """Удалить расписание"""
        self.cursor.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        self.conn.commit()

    def close(self):
        """Закрыть соединение с БД"""
        self.conn.close()
        logger.info("Database connection closed")
