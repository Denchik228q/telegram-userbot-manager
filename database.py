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
        """Создание таблиц с сохранением данных"""
    
    # ========================================
    # ТАБЛИЦА USERS - НЕ УДАЛЯЕМ, ТОЛЬКО ДОБАВЛЯЕМ КОЛОНКИ!
    # ========================================
    
    # Проверяем существует ли таблица
    cursor = await self.db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    )
    table_exists = await cursor.fetchone()
    
    if not table_exists:
        # Таблица не существует - создаём с нуля
        await self.db.execute('''
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                phone TEXT,
                subscription_type TEXT DEFAULT 'trial',
                subscription_expires TEXT,
                is_active INTEGER DEFAULT 1,
                private_channel_approved INTEGER DEFAULT 0,
                private_channel_requested INTEGER DEFAULT 0,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logger.info("✅ Table 'users' created")
    else:
        logger.info("✅ Table 'users' already exists, checking columns...")
    
    # Получаем список существующих колонок
    cursor = await self.db.execute("PRAGMA table_info(users)")
    columns = await cursor.fetchall()
    column_names = [col[1] for col in columns]
    
    # Добавляем недостающие колонки (если их нет)
    columns_to_add = {
        'username': 'TEXT',
        'phone': 'TEXT',
        'subscription_type': "TEXT DEFAULT 'trial'",
        'subscription_expires': 'TEXT',
        'is_active': 'INTEGER DEFAULT 1',
        'private_channel_approved': 'INTEGER DEFAULT 0',
        'private_channel_requested': 'INTEGER DEFAULT 0',
        'registered_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
    }
    
    for col_name, col_type in columns_to_add.items():
        if col_name not in column_names:
            try:
                await self.db.execute(f'ALTER TABLE users ADD COLUMN {col_name} {col_type}')
                logger.info(f"✅ Added column: {col_name}")
            except Exception as e:
                logger.warning(f"⚠️ Column {col_name} already exists or error: {e}")
    
    # ========================================
    # ТАБЛИЦА MAILINGS
    # ========================================
    
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
    
    # ========================================
    # ТАБЛИЦА SUPPORT_MESSAGES
    # ========================================
    
    await self.db.execute('''
        CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT,
            is_answered INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    await self.db.commit()
    logger.info("✅ All tables created/updated successfully")
    
    async def register_user(self, user_id: int, username: str):
        """Регистрация пользователя"""
        try:
            await self.db.execute('''
                INSERT OR IGNORE INTO users (user_id, username) 
                VALUES (?, ?)
            ''', (user_id, username))
            await self.db.commit()
            logger.info(f"✅ User registered: {user_id}")
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
            try:
                expire_date = datetime.fromisoformat(expires)
                if datetime.now() > expire_date:
                    # Подписка истекла
                    await self.db.execute('''
                        UPDATE users SET subscription_type = 'trial' 
                        WHERE user_id = ?
                    ''', (user_id,))
                    await self.db.commit()
                    return 'trial', SUBSCRIPTIONS['trial']
            except:
                pass
        
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
    
    async def check_private_channel_status(self, user_id: int):
        """Проверка статуса приватного канала"""
        try:
            cursor = await self.db.execute('''
                SELECT private_channel_approved, private_channel_requested
                FROM users WHERE user_id = ?
            ''', (user_id,))
            
            result = await cursor.fetchone()
            
            if not result:
                # Пользователь не найден - регистрируем
                await self.register_user(user_id, str(user_id))
                return False, False
            
            approved = bool(result[0])
            requested = bool(result[1])
            
            logger.info(f"🔍 User {user_id} status from DB: approved={result[0]}, requested={result[1]}")
            
            return approved, requested
            
        except Exception as e:
            logger.error(f"Error checking private channel status: {e}")
            return False, False
    
    async def approve_private_channel(self, user_id: int):
        """Одобрение доступа к приватному каналу"""
        try:
            # Обновляем статус
            await self.db.execute('''
                UPDATE users 
                SET private_channel_approved = 1,
                    private_channel_requested = 1
                WHERE user_id = ?
            ''', (user_id,))
            await self.db.commit()
            
            # Проверяем что обновилось
            cursor = await self.db.execute('''
                SELECT private_channel_approved, private_channel_requested
                FROM users WHERE user_id = ?
            ''', (user_id,))
            result = await cursor.fetchone()
            
            logger.info(f"✅ Private channel approved for user {user_id}")
            logger.info(f"✅ DB values after update: approved={result[0]}, requested={result[1]}")
            
            return True
        except Exception as e:
            logger.error(f"Error approving private channel: {e}")
            return False
    
    async def request_private_channel(self, user_id: int):
        """Отметить запрос на приватный канал"""
        try:
            await self.db.execute('''
                UPDATE users 
                SET private_channel_requested = 1
                WHERE user_id = ?
            ''', (user_id,))
            await self.db.commit()
            
            logger.info(f"✅ Private channel requested by user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error requesting private channel: {e}")
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
    
    async def close(self):
        """Закрытие соединения"""
        if self.db:
            await self.db.close()
            logger.info("✅ Database closed")

    async def backup_database(self, backup_path='bot_backup.db'):
        """Создание бэкапа базы данных"""
    try:
        import shutil
        shutil.copy2(self.db_name, backup_path)
        logger.info(f"✅ Database backup created: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"❌ Backup failed: {e}")
        return False

async def get_all_users(self):
    """Получить всех пользователей (для миграции)"""
    try:
        cursor = await self.db.execute('''
            SELECT user_id, username, phone, subscription_type, 
                   subscription_expires, is_active, registered_at
            FROM users
        ''')
        users = await cursor.fetchall()
        return users
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        return []

async def migrate_user_data(self, old_db_path='bot_backup.db'):
    """Миграция данных из старой базы"""
    try:
        # Подключаемся к старой базе
        old_db = await aiosqlite.connect(old_db_path)
        
        # Получаем пользователей
        cursor = await old_db.execute('SELECT * FROM users')
        old_users = await cursor.fetchall()
        
        # Переносим в новую базу
        for user in old_users:
            await self.db.execute('''
                INSERT OR REPLACE INTO users 
                (user_id, username, phone, subscription_type, subscription_expires, is_active, registered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', user[:7])  # Первые 7 колонок
        
        await self.db.commit()
        await old_db.close()
        
        logger.info(f"✅ Migrated {len(old_users)} users from backup")
        return True
        
    except Exception as e:
        logger.error(f"Migration error: {e}")
        return False


db = Database()