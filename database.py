"""
Управление базой данных
"""
import sqlite3
import logging
from datetime import datetime, timedelta
from contextlib import contextmanager
from config import DATABASE_URL

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path=DATABASE_URL):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для работы с БД"""
        conn = sqlite3.connect(self.db_path)
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
    
    def init_database(self):
        """Инициализация базы данных"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    subscription_plan TEXT DEFAULT 'trial',
                    subscription_expires TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    is_banned BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица аккаунтов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    phone TEXT NOT NULL,
                    name TEXT,
                    username TEXT,
                    session_string TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    UNIQUE(user_id, phone)
                )
            ''')
            
            # Таблица рассылок
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mailings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    message_text TEXT,
                    message_type TEXT DEFAULT 'text',
                    media_path TEXT,
                    targets TEXT NOT NULL,
                    accounts TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    total INTEGER DEFAULT 0,
                    sent INTEGER DEFAULT 0,
                    errors INTEGER DEFAULT 0,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Таблица расписаний
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT,
                    mailing_config TEXT NOT NULL,
                    schedule_type TEXT NOT NULL,
                    schedule_time TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    last_run TIMESTAMP,
                    next_run TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Таблица платежей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    plan TEXT NOT NULL,
                    amount REAL NOT NULL,
                    payment_method TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    transaction_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    approved_at TIMESTAMP,
                    approved_by INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Таблица логов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT NOT NULL,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Индексы для оптимизации
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_accounts_user_id ON accounts(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mailings_user_id ON mailings(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mailings_status ON mailings(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)')
            
            logger.info("✅ Database initialized successfully")
    
    # ==================== USERS ====================
    
    def create_user(self, telegram_id, username=None, first_name=None, last_name=None):
        """Создать пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Проверяем существует ли пользователь
            cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,))
            existing = cursor.fetchone()
            
            if existing:
                # Обновляем last_active
                cursor.execute('''
                    UPDATE users 
                    SET last_active = CURRENT_TIMESTAMP,
                        username = ?,
                        first_name = ?,
                        last_name = ?
                    WHERE telegram_id = ?
                ''', (username, first_name, last_name, telegram_id))
                return existing['id']
            
            # Создаём нового пользователя с trial подпиской
            expires = datetime.now() + timedelta(days=7)
            cursor.execute('''
                INSERT INTO users (telegram_id, username, first_name, last_name, subscription_expires)
                VALUES (?, ?, ?, ?, ?)
            ''', (telegram_id, username, first_name, last_name, expires))
            
            user_id = cursor.lastrowid
            
            # Логируем регистрацию
            self.add_log(user_id, 'user_registered', f'New user registered: {username or telegram_id}')
            
            logger.info(f"✅ New user created: {telegram_id}")
            return user_id
    
    def get_user(self, telegram_id):
        """Получить пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_user_subscription(self, user_id, plan, days=30):
        """Обновить подписку пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            expires = datetime.now() + timedelta(days=days)
            cursor.execute('''
                UPDATE users
                SET subscription_plan = ?,
                    subscription_expires = ?
                WHERE id = ?
            ''', (plan, expires, user_id))
            
            self.add_log(user_id, 'subscription_updated', f'Plan: {plan}, Days: {days}')
            logger.info(f"✅ Subscription updated for user {user_id}: {plan}")
    
    def get_all_users(self, active_only=False):
        """Получить всех пользователей"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM users'
            if active_only:
                query += ' WHERE is_active = 1 AND is_banned = 0'
            query += ' ORDER BY created_at DESC'
            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]
    
    def ban_user(self, user_id, banned=True):
        """Заблокировать/разблокировать пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET is_banned = ? WHERE id = ?', (banned, user_id))
            action = 'banned' if banned else 'unbanned'
            self.add_log(user_id, f'user_{action}', f'User was {action}')
    
    # ==================== ACCOUNTS ====================
    
    def add_account(self, user_id, phone, session_string, name=None, username=None):
        """Добавить аккаунт"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO accounts (user_id, phone, name, username, session_string)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, phone, name, username, session_string))
                
                account_id = cursor.lastrowid
                self.add_log(user_id, 'account_added', f'Phone: {phone}')
                logger.info(f"✅ Account added for user {user_id}: {phone}")
                return account_id
            except sqlite3.IntegrityError:
                logger.warning(f"Account {phone} already exists for user {user_id}")
                return None
    
    def get_user_accounts(self, user_id, active_only=True):
        """Получить аккаунты пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM accounts WHERE user_id = ?'
            if active_only:
                query += ' AND is_active = 1'
            query += ' ORDER BY created_at DESC'
            cursor.execute(query, (user_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_account(self, account_id):
        """Получить аккаунт по ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM accounts WHERE id = ?', (account_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_account(self, account_id, **kwargs):
        """Обновить аккаунт"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            allowed_fields = ['name', 'username', 'is_active', 'last_used', 'session_string']
            updates = []
            values = []
            
            for key, value in kwargs.items():
                if key in allowed_fields:
                    updates.append(f"{key} = ?")
                    values.append(value)
            
            if updates:
                values.append(account_id)
                query = f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?"
                cursor.execute(query, values)
                logger.info(f"✅ Account {account_id} updated")
    
    def delete_account(self, account_id, user_id):
        """Удалить аккаунт"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM accounts WHERE id = ? AND user_id = ?', (account_id, user_id))
            self.add_log(user_id, 'account_deleted', f'Account ID: {account_id}')
            logger.info(f"✅ Account {account_id} deleted")
    
    def count_user_accounts(self, user_id):
        """Подсчитать количество аккаунтов пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM accounts WHERE user_id = ? AND is_active = 1', (user_id,))
            return cursor.fetchone()['count']
    
    # ==================== MAILINGS ====================
    
    def create_mailing(self, user_id, message_text, targets, accounts, message_type='text', media_path=None):
        """Создать рассылку"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            import json
            targets_json = json.dumps(targets)
            accounts_json = json.dumps(accounts)
            
            cursor.execute('''
                INSERT INTO mailings (user_id, message_text, message_type, media_path, targets, accounts, total)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, message_text, message_type, media_path, targets_json, accounts_json, len(targets)))
            
            mailing_id = cursor.lastrowid
            self.add_log(user_id, 'mailing_created', f'Mailing ID: {mailing_id}, Targets: {len(targets)}')
            logger.info(f"✅ Mailing {mailing_id} created for user {user_id}")
            return mailing_id
    
    def get_mailing(self, mailing_id):
        """Получить рассылку по ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM mailings WHERE id = ?', (mailing_id,))
            row = cursor.fetchone()
            if row:
                data = dict(row)
                import json
                data['targets'] = json.loads(data['targets'])
                data['accounts'] = json.loads(data['accounts'])
                return data
            return None
    
    def get_user_mailings(self, user_id, limit=50):
        """Получить рассылки пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM mailings 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (user_id, limit))
            
            mailings = []
            import json
            for row in cursor.fetchall():
                data = dict(row)
                data['targets'] = json.loads(data['targets'])
                data['accounts'] = json.loads(data['accounts'])
                mailings.append(data)
            return mailings
    
    def update_mailing(self, mailing_id, **kwargs):
        """Обновить рассылку"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            allowed_fields = ['status', 'sent', 'errors', 'started_at', 'completed_at']
            updates = []
            values = []
            
            for key, value in kwargs.items():
                if key in allowed_fields:
                    updates.append(f"{key} = ?")
                    values.append(value)
            
            if updates:
                values.append(mailing_id)
                query = f"UPDATE mailings SET {', '.join(updates)} WHERE id = ?"
                cursor.execute(query, values)
    
    def count_user_mailings_today(self, user_id):
        """Подсчитать количество рассылок пользователя сегодня"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as count 
                FROM mailings 
                WHERE user_id = ? 
                AND DATE(created_at) = DATE('now')
            ''', (user_id,))
            return cursor.fetchone()['count']
    
    # ==================== SCHEDULES ====================
    
    def create_schedule(self, user_id, name, mailing_config, schedule_type, schedule_time):
        """Создать расписание"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            import json
            config_json = json.dumps(mailing_config)
            
            cursor.execute('''
                INSERT INTO schedules (user_id, name, mailing_config, schedule_type, schedule_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, name, config_json, schedule_type, schedule_time))
            
            schedule_id = cursor.lastrowid
            self.add_log(user_id, 'schedule_created', f'Schedule ID: {schedule_id}')
            logger.info(f"✅ Schedule {schedule_id} created for user {user_id}")
            return schedule_id
    
    def get_schedule(self, schedule_id):
        """Получить расписание по ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM schedules WHERE id = ?', (schedule_id,))
            row = cursor.fetchone()
            if row:
                data = dict(row)
                import json
                data['mailing_config'] = json.loads(data['mailing_config'])
                return data
            return None
    
    def get_user_schedules(self, user_id, active_only=True):
        """Получить расписания пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM schedules WHERE user_id = ?'
            if active_only:
                query += ' AND is_active = 1'
            query += ' ORDER BY created_at DESC'
            cursor.execute(query, (user_id,))
            
            schedules = []
            import json
            for row in cursor.fetchall():
                data = dict(row)
                data['mailing_config'] = json.loads(data['mailing_config'])
                schedules.append(data)
            return schedules
    
    def get_active_schedules(self):
        """Получить все активные расписания"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM schedules 
                WHERE is_active = 1 
                AND (next_run IS NULL OR next_run <= CURRENT_TIMESTAMP)
            ''')
            
            schedules = []
            import json
            for row in cursor.fetchall():
                data = dict(row)
                data['mailing_config'] = json.loads(data['mailing_config'])
                schedules.append(data)
            return schedules
    
    def update_schedule(self, schedule_id, **kwargs):
        """Обновить расписание"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            allowed_fields = ['name', 'is_active', 'last_run', 'next_run', 'mailing_config']
            updates = []
            values = []
            
            for key, value in kwargs.items():
                if key in allowed_fields:
                    if key == 'mailing_config':
                        import json
                        value = json.dumps(value)
                    updates.append(f"{key} = ?")
                    values.append(value)
            
            if updates:
                values.append(schedule_id)
                query = f"UPDATE schedules SET {', '.join(updates)} WHERE id = ?"
                cursor.execute(query, values)
    
    def delete_schedule(self, schedule_id, user_id):
        """Удалить расписание"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM schedules WHERE id = ? AND user_id = ?', (schedule_id, user_id))
            self.add_log(user_id, 'schedule_deleted', f'Schedule ID: {schedule_id}')
            logger.info(f"✅ Schedule {schedule_id} deleted")
    
    # ==================== PAYMENTS ====================
    
    def create_payment(self, user_id, plan, amount, payment_method, transaction_id=None):
        """Создать платёж"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO payments (user_id, plan, amount, payment_method, transaction_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, plan, amount, payment_method, transaction_id))
            
            payment_id = cursor.lastrowid
            self.add_log(user_id, 'payment_created', f'Plan: {plan}, Amount: {amount}')
            logger.info(f"✅ Payment {payment_id} created for user {user_id}")
            return payment_id
    
    def get_payment(self, payment_id):
        """Получить платёж по ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM payments WHERE id = ?', (payment_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_pending_payments(self):
        """Получить все ожидающие платежи"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT p.*, u.username, u.first_name 
                FROM payments p
                JOIN users u ON p.user_id = u.id
                WHERE p.status = 'pending'
                ORDER BY p.created_at DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def approve_payment(self, payment_id, admin_id):
        """Одобрить платёж"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Получаем информацию о платеже
            cursor.execute('SELECT user_id, plan FROM payments WHERE id = ?', (payment_id,))
            payment = cursor.fetchone()
            
            if not payment:
                return False
            
            user_id = payment['user_id']
            plan = payment['plan']
            
            # Обновляем статус платежа
            cursor.execute('''
                UPDATE payments 
                SET status = 'approved', approved_at = CURRENT_TIMESTAMP, approved_by = ?
                WHERE id = ?
            ''', (admin_id, payment_id))
            
            # Обновляем подписку пользователя
            from config import SUBSCRIPTION_PLANS
            days = SUBSCRIPTION_PLANS[plan]['days']
            self.update_user_subscription(user_id, plan, days)
            
            self.add_log(user_id, 'payment_approved', f'Payment ID: {payment_id}, Plan: {plan}')
            logger.info(f"✅ Payment {payment_id} approved by admin {admin_id}")
            return True
    
    def reject_payment(self, payment_id, admin_id):
        """Отклонить платёж"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT user_id FROM payments WHERE id = ?', (payment_id,))
            payment = cursor.fetchone()
            
            if not payment:
                return False
            
            cursor.execute('''
                UPDATE payments 
                SET status = 'rejected', approved_by = ?
                WHERE id = ?
            ''', (admin_id, payment_id))
            
            self.add_log(payment['user_id'], 'payment_rejected', f'Payment ID: {payment_id}')
            logger.info(f"❌ Payment {payment_id} rejected by admin {admin_id}")
            return True
    
    def get_user_payments(self, user_id):
        """Получить платежи пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM payments 
                WHERE user_id = ? 
                ORDER BY created_at DESC
            ''', (user_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== LOGS ====================
    
    def add_log(self, user_id, action, details=None):
        """Добавить лог"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO logs (user_id, action, details)
                VALUES (?, ?, ?)
            ''', (user_id, action, details))
    
    def get_logs(self, user_id=None, limit=100):
        """Получить логи"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute('''
                    SELECT * FROM logs 
                    WHERE user_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ''', (user_id, limit))
            else:
                cursor.execute('''
                    SELECT * FROM logs 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def cleanup_old_logs(self, days=7):
        """Очистить старые логи"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM logs 
                WHERE created_at < datetime('now', '-' || ? || ' days')
            ''', (days,))
            deleted = cursor.rowcount
            logger.info(f"✅ Cleaned up {deleted} old logs")
            return deleted
    
    # ==================== STATISTICS ====================
    
    def get_statistics(self):
        """Получить общую статистику"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Пользователи
            cursor.execute('SELECT COUNT(*) as count FROM users')
            stats['total_users'] = cursor.fetchone()['count']
            
            cursor.execute('SELECT COUNT(*) as count FROM users WHERE DATE(last_active) = DATE("now")')
            stats['active_today'] = cursor.fetchone()['count']
            
            cursor.execute('SELECT COUNT(*) as count FROM users WHERE DATE(created_at) >= DATE("now", "-7 days")')
            stats['new_this_week'] = cursor.fetchone()['count']
            
            # Рассылки
            cursor.execute('SELECT COUNT(*) as count FROM mailings')
            stats['total_mailings'] = cursor.fetchone()['count']
            
            cursor.execute('SELECT COUNT(*) as count FROM mailings WHERE status = "completed"')
            stats['completed_mailings'] = cursor.fetchone()['count']
            
            cursor.execute('SELECT SUM(sent) as total FROM mailings')
            result = cursor.fetchone()
            stats['total_messages_sent'] = result['total'] or 0
            
            # Платежи
            cursor.execute('SELECT COUNT(*) as count FROM payments WHERE status = "pending"')
            stats['pending_payments'] = cursor.fetchone()['count']
            
            cursor.execute('SELECT SUM(amount) as total FROM payments WHERE status = "approved" AND DATE(approved_at) >= DATE("now", "-30 days")')
            result = cursor.fetchone()
            stats['revenue_month'] = result['total'] or 0
            
            # По тарифам
            cursor.execute('SELECT subscription_plan, COUNT(*) as count FROM users GROUP BY subscription_plan')
            stats['users_by_plan'] = {row['subscription_plan']: row['count'] for row in cursor.fetchall()}
            
            return stats
    
    def close(self):
        """Закрыть соединение (для совместимости)"""
        pass