import aiosqlite
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path='bot.db'):
        self.db_path = db_path
        self.db = None
    
    async def connect(self):
        """Подключение к БД"""
        self.db = await aiosqlite.connect(self.db_path)
        await self.create_tables()
        logger.info(f"✅ Database connected: {self.db_path}")
    
    async def create_tables(self):
        """Создание таблиц"""
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone TEXT,
                subscription_type TEXT DEFAULT 'free',
                subscription_until TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                used_free_trial INTEGER DEFAULT 0
            )
        ''')
        
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS mailings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                messages TEXT,
                targets TEXT,
                sent_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                subscription_type TEXT,
                amount REAL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT,
                status TEXT DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        await self.db.commit()
        logger.info("✅ Tables created")
    
    async def add_user(self, user_id, username, first_name, last_name):
        """Добавить пользователя"""
        try:
            await self.db.execute('''
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))
            await self.db.commit()
        except Exception as e:
            logger.error(f"Add user error: {e}")
    
    async def get_user(self, user_id):
        """Получить данные пользователя"""
        async with self.db.execute(
            'SELECT * FROM users WHERE user_id = ?',
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
    
    async def get_subscription(self, user_id):
        """Получить тип подписки"""
        async with self.db.execute(
            'SELECT subscription_type, subscription_until FROM users WHERE user_id = ?',
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                sub_type, sub_until = row
                if sub_until:
                    until_date = datetime.fromisoformat(sub_until)
                    if datetime.now() > until_date:
                        await self.update_subscription(user_id, 'free', 0)
                        return 'free'
                return sub_type
            return 'free'
    
    async def check_free_trial_used(self, user_id):
        """Проверить использовалась ли пробная подписка"""
        async with self.db.execute(
            'SELECT used_free_trial FROM users WHERE user_id = ?',
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] == 1 if row else False
    
    async def mark_free_trial_used(self, user_id):
        """Отметить что пробная подписка использована"""
        await self.db.execute(
            'UPDATE users SET used_free_trial = 1 WHERE user_id = ?',
            (user_id,)
        )
        await self.db.commit()
    
    async def update_subscription(self, user_id, sub_type, duration_days):
        """Обновить подписку"""
        until_date = datetime.now() + timedelta(days=duration_days)
        await self.db.execute('''
            UPDATE users 
            SET subscription_type = ?, subscription_until = ?
            WHERE user_id = ?
        ''', (sub_type, until_date.isoformat(), user_id))
        await self.db.commit()
    
    async def add_mailing(self, user_id, messages, targets):
        """Добавить рассылку"""
        import json
        try:
            await self.db.execute('''
                INSERT INTO mailings (user_id, messages, targets, sent_count)
                VALUES (?, ?, ?, ?)
            ''', (user_id, json.dumps(messages), json.dumps(targets), len(targets)))
            await self.db.commit()
        except Exception as e:
            logger.error(f"Add mailing error: {e}")
    
    async def get_stats(self, user_id):
        """Получить статистику"""
        async with self.db.execute('''
            SELECT 
                COUNT(*) as total_mailings,
                COALESCE(SUM(sent_count), 0) as total_sent,
                COALESCE(SUM(failed_count), 0) as total_failed
            FROM mailings
            WHERE user_id = ?
        ''', (user_id,)) as cursor:
            row = await cursor.fetchone()
            return {
                'total_mailings': row[0] or 0,
                'total_sent': row[1] or 0,
                'total_failed': row[2] or 0
            }
    
    async def add_payment(self, user_id, sub_type, amount):
        """Добавить платеж"""
        async with self.db.execute('''
            INSERT INTO payments (user_id, subscription_type, amount)
            VALUES (?, ?, ?)
        ''', (user_id, sub_type, amount)) as cursor:
            await self.db.commit()
            return cursor.lastrowid
    
    async def add_support_ticket(self, user_id, message):
        """Добавить обращение в поддержку"""
        async with self.db.execute('''
            INSERT INTO support_tickets (user_id, message)
            VALUES (?, ?)
        ''', (user_id, message)) as cursor:
            await self.db.commit()
            return cursor.lastrowid
    
    async def close(self):
        """Закрыть БД"""
        if self.db:
            await self.db.close()
            logger.info("Database closed")