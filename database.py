import aiosqlite
import logging
from datetime import datetime
from config_userbot import SUBSCRIPTIONS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path='bot.db'):
        self.db_path = db_path
        self.db = None
    
    async def connect(self):
        """Подключение к базе данных"""
        try:
            self.db = await aiosqlite.connect(self.db_path)
            await self.create_tables()
            logger.info(f"✅ Database connected: {self.db_path}")
        except Exception as e:
            logger.error(f"❌ Database connection error: {e}")
    
    async def create_tables(self):
        """Создание таблиц"""
        try:
            # Таблица пользователей
            await self.db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    phone TEXT,
                    subscription_type TEXT DEFAULT 'trial',
                    subscription_end TEXT,
                    messages_sent_today INTEGER DEFAULT 0,
                    last_reset_date TEXT,
                    registered_at TEXT,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Таблица статистики рассылок
            await self.db.execute('''
                CREATE TABLE IF NOT EXISTS mailings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    targets_count INTEGER,
                    messages_count INTEGER,
                    sent_count INTEGER,
                    failed_count INTEGER,
                    status TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # Таблица сообщений в поддержку
            await self.db.execute('''
                CREATE TABLE IF NOT EXISTS support_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message TEXT,
                    created_at TEXT,
                    is_answered BOOLEAN DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            await self.db.commit()
            logger.info("✅ Tables created")
        except Exception as e:
            logger.error(f"❌ Create tables error: {e}")
    
    async def register_user(self, user_id: int, username: str):
        """Регистрация нового пользователя"""
        try:
            now = datetime.now().isoformat()
            await self.db.execute('''
                INSERT OR IGNORE INTO users (user_id, username, registered_at, last_reset_date)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, now, now))
            await self.db.commit()
            logger.info(f"✅ User registered: {user_id}")
        except Exception as e:
            logger.error(f"❌ Register user error: {e}")
    
    async def get_user(self, user_id: int):
        """Получить данные пользователя"""
        try:
            async with self.db.execute('''
                SELECT * FROM users WHERE user_id = ?
            ''', (user_id,)) as cursor:
                return await cursor.fetchone()
        except Exception as e:
            logger.error(f"❌ Get user error: {e}")
            return None
    
    async def update_user_phone(self, user_id: int, phone: str):
        """Обновить номер телефона"""
        try:
            await self.db.execute('''
                UPDATE users SET phone = ? WHERE user_id = ?
            ''', (phone, user_id))
            await self.db.commit()
            logger.info(f"✅ Phone updated for user {user_id}")
        except Exception as e:
            logger.error(f"❌ Update phone error: {e}")
    
    async def check_subscription(self, user_id: int):
        """Проверка подписки пользователя"""
        try:
            async with self.db.execute('''
                SELECT subscription_type, subscription_end 
                FROM users WHERE user_id = ?
            ''', (user_id,)) as cursor:
                row = await cursor.fetchone()
                
                if not row:
                    return 'trial', SUBSCRIPTIONS['trial']
                
                sub_type, sub_end = row
                
                if not sub_type:
                    return 'trial', SUBSCRIPTIONS['trial']
                
                if sub_end:
                    if datetime.fromisoformat(sub_end) < datetime.now():
                        return 'trial', SUBSCRIPTIONS['trial']
                
                return sub_type, SUBSCRIPTIONS.get(sub_type, SUBSCRIPTIONS['trial'])
                
        except Exception as e:
            logger.error(f"❌ Check subscription error: {e}")
            return 'trial', SUBSCRIPTIONS['trial']
    
    async def activate_subscription(self, user_id: int, sub_type: str):
        """Активация подписки"""
        try:
            from datetime import timedelta
            
            sub_data = SUBSCRIPTIONS.get(sub_type)
            if not sub_data:
                return False
            
            duration = sub_data['duration_days']
            end_date = (datetime.now() + timedelta(days=duration)).isoformat()
            
            await self.db.execute('''
                UPDATE users 
                SET subscription_type = ?, subscription_end = ?
                WHERE user_id = ?
            ''', (sub_type, end_date, user_id))
            await self.db.commit()
            
            logger.info(f"✅ Subscription activated: {user_id} -> {sub_type}")
            return True
        except Exception as e:
            logger.error(f"❌ Activate subscription error: {e}")
            return False
    
    async def increment_messages_sent(self, user_id: int):
        """Увеличить счётчик отправленных сообщений"""
        try:
            await self.db.execute('''
                UPDATE users 
                SET messages_sent_today = messages_sent_today + 1
                WHERE user_id = ?
            ''', (user_id,))
            await self.db.commit()
        except Exception as e:
            logger.error(f"❌ Increment messages error: {e}")
    
    async def reset_daily_limits(self):
        """Сброс дневных лимитов (вызывается раз в день)"""
        try:
            today = datetime.now().date().isoformat()
            await self.db.execute('''
                UPDATE users 
                SET messages_sent_today = 0, last_reset_date = ?
            ''', (today,))
            await self.db.commit()
            logger.info("✅ Daily limits reset")
        except Exception as e:
            logger.error(f"❌ Reset daily limits error: {e}")
    
    async def add_mailing(self, user_id: int, targets_count: int, messages_count: int):
        """Добавить запись о рассылке"""
        try:
            now = datetime.now().isoformat()
            await self.db.execute('''
                INSERT INTO mailings 
                (user_id, targets_count, messages_count, sent_count, failed_count, status, started_at)
                VALUES (?, ?, ?, 0, 0, 'running', ?)
            ''', (user_id, targets_count, messages_count, now))
            await self.db.commit()
            
            cursor = await self.db.execute('SELECT last_insert_rowid()')
            row = await cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.error(f"❌ Add mailing error: {e}")
            return None
    
    async def update_mailing(self, mailing_id: int, sent: int, failed: int, status: str = 'completed'):
        """Обновить статистику рассылки"""
        try:
            now = datetime.now().isoformat()
            await self.db.execute('''
                UPDATE mailings 
                SET sent_count = ?, failed_count = ?, status = ?, finished_at = ?
                WHERE id = ?
            ''', (sent, failed, status, now, mailing_id))
            await self.db.commit()
        except Exception as e:
            logger.error(f"❌ Update mailing error: {e}")
    
    async def get_user_stats(self, user_id: int):
        """Получить статистику пользователя"""
        try:
            async with self.db.execute('''
                SELECT COUNT(*), SUM(sent_count), SUM(failed_count)
                FROM mailings WHERE user_id = ?
            ''', (user_id,)) as cursor:
                return await cursor.fetchone()
        except Exception as e:
            logger.error(f"❌ Get stats error: {e}")
            return (0, 0, 0)
    
    async def add_support_message(self, user_id: int, message: str):
        """Добавить сообщение в поддержку"""
        try:
            now = datetime.now().isoformat()
            await self.db.execute('''
                INSERT INTO support_messages (user_id, message, created_at)
                VALUES (?, ?, ?)
            ''', (user_id, message, now))
            await self.db.commit()
            logger.info(f"✅ Support message added from {user_id}")
        except Exception as e:
            logger.error(f"❌ Add support message error: {e}")

    async def add_user(self, user_id: int, username: str):
        """Алиас для register_user"""
        await self.register_user(user_id, username)
    
    async def close(self):
        """Закрытие соединения"""
        if self.db:
            await self.db.close()
            logger.info("🔌 Database closed")


# Глобальный экземпляр базы данных
db = Database()