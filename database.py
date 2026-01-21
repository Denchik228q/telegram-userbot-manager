import aiosqlite
import logging
from datetime import datetime, timedelta
from config_userbot import SUBSCRIPTIONS

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_name='bot.db'):
        self.db_name = db_name
        self.db = None
    
    async def connect(self):
        """Подключение к базе данных"""
        self.db = await aiosqlite.connect(self.db_name)
        self.db.row_factory = aiosqlite.Row
        await self.create_tables()
        logger.info(f"✅ Database connected: {self.db_name}")
    
    async def create_tables(self):
        """Создание таблиц"""
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                phone TEXT,
                subscription_type TEXT DEFAULT 'trial',
                subscription_expires TEXT,
                is_active BOOLEAN DEFAULT 1,
                private_channel_approved BOOLEAN DEFAULT 0,
                private_channel_requested BOOLEAN DEFAULT 0,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Миграция: добавляем колонки если их нет
        try:
            await self.db.execute('ALTER TABLE users ADD COLUMN private_channel_approved BOOLEAN DEFAULT 0')
        except:
            pass
        
        try:
            await self.db.execute('ALTER TABLE users ADD COLUMN private_channel_requested BOOLEAN DEFAULT 0')
        except:
            pass
        
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS mailings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                targets_count INTEGER,
                messages_count INTEGER,
                sent_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT,
                is_answered BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        await self.db.commit()
        logger.info("✅ Tables created")
    
    async def register_user(self, user_id: int, username: str):
        """Регистрация пользователя"""
        try:
            await self.db.execute('''
                INSERT OR IGNORE INTO users (user_id, username) 
                VALUES (?, ?)
            ''', (user_id, username))
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error registering user: {e}")
            return False
    
    async def update_user_phone(self, user_id: int, phone: str):
        """Обновление номера телефона"""
        try:
            await self.db.execute('''
                UPDATE users SET phone = ? WHERE user_id = ?
            ''', (phone, user_id))
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating phone: {e}")
            return False
    
    async def check_subscription(self, user_id: int):
        """Проверка подписки"""
        cursor = await self.db.execute('''
            SELECT subscription_type, subscription_expires 
            FROM users WHERE user_id = ?
        ''', (user_id,))
        
        result = await cursor.fetchone()
        
        if not result:
            return 'trial', SUBSCRIPTIONS['trial']
        
        sub_type = result[0] or 'trial'
        expires = result[1]
        
        # Проверка срока действия
        if expires:
            expire_date = datetime.fromisoformat(expires)
            if datetime.now() > expire_date:
                # Подписка истекла
                await self.db.execute('''
                    UPDATE users SET subscription_type = 'trial' 
                    WHERE user_id = ?
                ''', (user_id,))
                await self.db.commit()
                return 'trial', SUBSCRIPTIONS['trial']
        
        return sub_type, SUBSCRIPTIONS.get(sub_type, SUBSCRIPTIONS['trial'])
    
    async def activate_subscription(self, user_id: int, sub_type: str):
        """Активация подписки"""
        try:
            duration = SUBSCRIPTIONS[sub_type]['duration_days']
            expires = datetime.now() + timedelta(days=duration)
            
            await self.db.execute('''
                UPDATE users 
                SET subscription_type = ?, subscription_expires = ?
                WHERE user_id = ?
            ''', (sub_type, expires.isoformat(), user_id))
            await self.db.commit()
            
            logger.info(f"✅ Subscription activated: {user_id} -> {sub_type}")
            return True
        except Exception as e:
            logger.error(f"Error activating subscription: {e}")
            return False
    
    async def add_mailing(self, user_id: int, targets_count: int, messages_count: int):
        """Добавление рассылки"""
        try:
            cursor = await self.db.execute('''
                INSERT INTO mailings (user_id, targets_count, messages_count)
                VALUES (?, ?, ?)
            ''', (user_id, targets_count, messages_count))
            await self.db.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding mailing: {e}")
            return None
    
    async def update_mailing(self, mailing_id: int, sent: int, failed: int):
        """Обновление статуса рассылки"""
        try:
            await self.db.execute('''
                UPDATE mailings 
                SET sent_count = ?, failed_count = ?, 
                    status = 'completed', finished_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (sent, failed, mailing_id))
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating mailing: {e}")
            return False
    
    async def get_user_stats(self, user_id: int):
        """Статистика пользователя"""
        cursor = await self.db.execute('''
            SELECT 
                COUNT(*) as mailings_count,
                SUM(sent_count) as sent_total,
                SUM(failed_count) as failed_total
            FROM mailings WHERE user_id = ?
        ''', (user_id,))
        
        result = await cursor.fetchone()
        return result if result else (0, 0, 0)
    
    async def add_support_message(self, user_id: int, message: str):
        """Добавление обращения в поддержку"""
        try:
            await self.db.execute('''
                INSERT INTO support_messages (user_id, message)
                VALUES (?, ?)
            ''', (user_id, message))
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding support message: {e}")
            return False
    
    async def approve_private_channel(self, user_id: int):
        """Одобрение доступа к приватному каналу"""
        try:
            await self.db.execute('''
                UPDATE users 
                SET private_channel_approved = 1,
                    private_channel_requested = 1
                WHERE user_id = ?
            ''', (user_id,))
            await self.db.commit()
            logger.info(f"✅ Private channel approved for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error approving private channel: {e}")
            return False
    
    async def check_private_channel_status(self, user_id: int):
        """Проверка статуса приватного канала"""
        cursor = await self.db.execute('''
            SELECT private_channel_approved, private_channel_requested
            FROM users WHERE user_id = ?
        ''', (user_id,))
        
        result = await cursor.fetchone()
        
        if not result:
            return False, False
        
        return bool(result[0]), bool(result[1])
    
    async def close(self):
        """Закрытие соединения"""
        if self.db:
            await self.db.close()
            logger.info("✅ Database closed")


db = Database()