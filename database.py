import aiosqlite
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_name='bot.db'):
        self.db_name = db_name
        self.db = None
    
    async def connect(self):
        """Подключение к базе данных"""
        try:
            self.db = await aiosqlite.connect(self.db_name)
            await self.create_tables()
            logger.info(f"✅ Database connected: {self.db_name}")
        except Exception as e:
            logger.error(f"❌ Database connection error: {e}")
            raise
    
    async def create_tables(self):
        """Создание таблиц"""
        try:
            # Таблица пользователей
            await self.db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    phone TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    subscription_type TEXT DEFAULT 'free',
                    subscription_until TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица сессий userbot
            await self.db.execute('''
                CREATE TABLE IF NOT EXISTS userbot_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    phone TEXT,
                    session_file TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    messages_sent_today INTEGER DEFAULT 0,
                    last_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # Таблица рассылок (изменено: message_texts вместо message_text)
            await self.db.execute('''
                CREATE TABLE IF NOT EXISTS mailings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message_texts TEXT,
                    targets TEXT,
                    status TEXT DEFAULT 'pending',
                    sent_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # Таблица логов отправки
            await self.db.execute('''
                CREATE TABLE IF NOT EXISTS send_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mailing_id INTEGER,
                    target TEXT,
                    status TEXT,
                    error_message TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (mailing_id) REFERENCES mailings(id)
                )
            ''')
            
            # Таблица платежей
            await self.db.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    subscription_type TEXT,
                    amount INTEGER,
                    status TEXT DEFAULT 'pending',
                    payment_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    paid_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # Таблица обращений в поддержку
            await self.db.execute('''
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message TEXT,
                    status TEXT DEFAULT 'open',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            await self.db.commit()
            logger.info("✅ Tables created")
            
        except Exception as e:
            logger.error(f"❌ Error creating tables: {e}")
            raise
    
    async def add_user(self, user_id, username=None, first_name=None, last_name=None):
        """Добавить пользователя"""
        try:
            await self.db.execute('''
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))
            await self.db.commit()
            logger.info(f"✅ User added: {user_id}")
        except Exception as e:
            logger.error(f"❌ Error adding user: {e}")
    
    async def get_user(self, user_id):
        """Получить пользователя"""
        try:
            async with self.db.execute(
                'SELECT * FROM users WHERE user_id = ?', (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        'user_id': row[0],
                        'username': row[1],
                        'first_name': row[2],
                        'last_name': row[3],
                        'phone': row[4],
                        'is_active': row[5],
                        'subscription_type': row[6] or 'free',
                        'subscription_until': row[7],
                        'created_at': row[8]
                    }
                return None
        except Exception as e:
            logger.error(f"❌ Error getting user: {e}")
            return None
    
    async def update_subscription(self, user_id, subscription_type, duration_days):
        """Обновить подписку"""
        try:
            until = datetime.now() + timedelta(days=duration_days)
            await self.db.execute('''
                UPDATE users
                SET subscription_type = ?, subscription_until = ?
                WHERE user_id = ?
            ''', (subscription_type, until, user_id))
            await self.db.commit()
            logger.info(f"✅ Subscription updated: {user_id} -> {subscription_type}")
        except Exception as e:
            logger.error(f"❌ Error updating subscription: {e}")
    
    async def get_subscription(self, user_id):
        """Получить подписку пользователя"""
        try:
            async with self.db.execute(
                'SELECT subscription_type, subscription_until FROM users WHERE user_id = ?',
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    sub_type = row[0] or 'free'
                    sub_until = row[1]
                    # Проверка истечения
                    if sub_until:
                        try:
                            until_date = datetime.fromisoformat(sub_until)
                            if until_date < datetime.now():
                                sub_type = 'free'
                                await self.update_subscription(user_id, 'free', 0)
                        except:
                            pass
                    return sub_type
                return 'free'
        except Exception as e:
            logger.error(f"❌ Error getting subscription: {e}")
            return 'free'
    
    async def add_userbot_session(self, user_id, phone, session_file):
        """Добавить сессию userbot"""
        try:
            await self.db.execute('''
                INSERT INTO userbot_sessions (user_id, phone, session_file)
                VALUES (?, ?, ?)
            ''', (user_id, phone, session_file))
            await self.db.commit()
            logger.info(f"✅ Session added: {phone}")
        except Exception as e:
            logger.error(f"❌ Error adding session: {e}")
    
    async def get_userbot_session(self, user_id):
        """Получить сессию userbot"""
        try:
            async with self.db.execute(
                'SELECT * FROM userbot_sessions WHERE user_id = ? AND is_active = 1',
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'user_id': row[1],
                        'phone': row[2],
                        'session_file': row[3],
                        'is_active': row[4],
                        'messages_sent_today': row[5],
                        'last_reset': row[6],
                        'created_at': row[7]
                    }
                return None
        except Exception as e:
            logger.error(f"❌ Error getting session: {e}")
            return None
    
    async def update_session_stats(self, user_id, messages_sent):
        """Обновить статистику сессии"""
        try:
            await self.db.execute('''
                UPDATE userbot_sessions
                SET messages_sent_today = ?, last_reset = ?
                WHERE user_id = ? AND is_active = 1
            ''', (messages_sent, datetime.now(), user_id))
            await self.db.commit()
        except Exception as e:
            logger.error(f"❌ Error updating stats: {e}")
    
    async def deactivate_session(self, user_id):
        """Деактивировать сессию"""
        try:
            await self.db.execute('''
                UPDATE userbot_sessions
                SET is_active = 0
                WHERE user_id = ?
            ''', (user_id,))
            await self.db.commit()
            logger.info(f"✅ Session deactivated: {user_id}")
        except Exception as e:
            logger.error(f"❌ Error deactivating session: {e}")
    
    async def add_mailing(self, user_id, message_texts, targets):
        """Добавить рассылку (с поддержкой нескольких сообщений)"""
        try:
            # Преобразуем список сообщений в JSON-строку
            import json
            if isinstance(message_texts, list):
                messages_json = json.dumps(message_texts, ensure_ascii=False)
            else:
                messages_json = json.dumps([message_texts], ensure_ascii=False)
            
            cursor = await self.db.execute('''
                INSERT INTO mailings (user_id, message_texts, targets)
                VALUES (?, ?, ?)
            ''', (user_id, messages_json, ','.join(targets)))
            await self.db.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"❌ Error adding mailing: {e}")
            return None
    
    async def update_mailing_status(self, mailing_id, status, sent_count=0, failed_count=0):
        """Обновить статус рассылки"""
        try:
            now = datetime.now()
            if status == 'in_progress':
                await self.db.execute('''
                    UPDATE mailings
                    SET status = ?, started_at = ?
                    WHERE id = ?
                ''', (status, now, mailing_id))
            elif status == 'completed':
                await self.db.execute('''
                    UPDATE mailings
                    SET status = ?, sent_count = ?, failed_count = ?, completed_at = ?
                    WHERE id = ?
                ''', (status, sent_count, failed_count, now, mailing_id))
            else:
                await self.db.execute('''
                    UPDATE mailings
                    SET status = ?
                    WHERE id = ?
                ''', (status, mailing_id))
            await self.db.commit()
        except Exception as e:
            logger.error(f"❌ Error updating mailing: {e}")
    
    async def add_send_log(self, mailing_id, target, status, error_message=None):
        """Добавить лог отправки"""
        try:
            await self.db.execute('''
                INSERT INTO send_logs (mailing_id, target, status, error_message)
                VALUES (?, ?, ?, ?)
            ''', (mailing_id, target, status, error_message))
            await self.db.commit()
        except Exception as e:
            logger.error(f"❌ Error adding log: {e}")
    
    async def add_payment(self, user_id, subscription_type, amount):
        """Добавить платёж"""
        try:
            cursor = await self.db.execute('''
                INSERT INTO payments (user_id, subscription_type, amount)
                VALUES (?, ?, ?)
            ''', (user_id, subscription_type, amount))
            await self.db.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"❌ Error adding payment: {e}")
            return None
    
    async def update_payment_status(self, payment_id, status):
        """Обновить статус платежа"""
        try:
            await self.db.execute('''
                UPDATE payments
                SET status = ?, paid_at = ?
                WHERE id = ?
            ''', (status, datetime.now(), payment_id))
            await self.db.commit()
        except Exception as e:
            logger.error(f"❌ Error updating payment: {e}")
    
    async def add_support_ticket(self, user_id, message):
        """Создать обращение в поддержку"""
        try:
            cursor = await self.db.execute('''
                INSERT INTO support_tickets (user_id, message)
                VALUES (?, ?)
            ''', (user_id, message))
            await self.db.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"❌ Error adding ticket: {e}")
            return None
    
    async def close_support_ticket(self, ticket_id):
        """Закрыть обращение"""
        try:
            await self.db.execute('''
                UPDATE support_tickets
                SET status = 'closed', closed_at = ?
                WHERE id = ?
            ''', (datetime.now(), ticket_id))
            await self.db.commit()
        except Exception as e:
            logger.error(f"❌ Error closing ticket: {e}")
    
    async def get_user_mailings(self, user_id, limit=10):
        """Получить рассылки пользователя"""
        try:
            async with self.db.execute('''
                SELECT * FROM mailings
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (user_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        'id': row[0],
                        'user_id': row[1],
                        'message_texts': row[2],
                        'targets': row[3],
                        'status': row[4],
                        'sent_count': row[5],
                        'failed_count': row[6],
                        'created_at': row[7],
                        'started_at': row[8],
                        'completed_at': row[9]
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"❌ Error getting mailings: {e}")
            return []
    
    async def get_stats(self, user_id):
        """Получить статистику пользователя"""
        try:
            async with self.db.execute('''
                SELECT 
                    COUNT(*) as total_mailings,
                    SUM(sent_count) as total_sent,
                    SUM(failed_count) as total_failed
                FROM mailings
                WHERE user_id = ?
            ''', (user_id,)) as cursor:
                row = await cursor.fetchone()
                return {
                    'total_mailings': row[0] or 0,
                    'total_sent': row[1] or 0,
                    'total_failed': row[2] or 0
                }
        except Exception as e:
            logger.error(f"❌ Error getting stats: {e}")
            return {'total_mailings': 0, 'total_sent': 0, 'total_failed': 0}
    
    async def close(self):
        """Закрыть соединение"""
        if self.db:
            await self.db.close()
            logger.info("✅ Database closed")