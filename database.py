"""
Управление базой данных SQLite с WAL режимом
"""
import sqlite3
import logging
from typing import Optional, List, Dict 
from datetime import datetime, timedelta
from contextlib import contextmanager
from config import DATABASE_URL

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str = "bot_data.db"):
        """Инициализация базы данных"""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()  # <- ЭТА СТРОКА ОБЯЗАТЕЛЬНА!
        self._create_tables()
        logger.info("✅ Database initialized successfully")

    def _create_tables(self):
        """Создание таблиц в БД"""
        # Таблица пользователей
        self.self.cursor.execute("""
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

        # Таблица аккаунтов
        self.self.cursor.execute("""
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

        # Таблица рассылок
        self.self.cursor.execute("""
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

        # Таблица расписаний
        self.self.cursor.execute("""
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

        self.self.conn.commit()

    async def start_auth(self, phone: str, user_id: int) -> Dict:
        """Начать авторизацию Telegram аккаунта"""
        try:
            # API ID и Hash по умолчанию (или из переменных окружения)
            api_id = int(os.getenv('TELEGRAM_API_ID', '35118006'))  # Замените на свой
            api_hash = os.getenv('TELEGRAM_API_HASH', '9da42bc6c0367507231d2f33e9ad4873')  # Замените на свой
            
            # Создаем клиент
            client = TelegramClient(
                StringSession(),
                api_id,
                api_hash
            )
            
            await client.connect()
            
            # Отправляем код
            await client.send_code_request(phone)
            
            # Сохраняем клиент для дальнейшей авторизации
            self.clients[user_id] = {
                'client': client,
                'phone': phone,
                'api_id': api_id,
                'api_hash': api_hash
            }
            
            logger.info(f"✅ Code sent to {phone} for user {user_id}")
            
            return {
                'success': True,
                'message': 'Код отправлен'
            }
            
        except Exception as e:
            logger.error(f"Error in start_auth: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def verify_code(self, user_id: int, code: str, password: str = None) -> Dict:
        """Проверить код и завершить авторизацию"""
        try:
            if user_id not in self.clients:
                return {'success': False, 'error': 'Сессия не найдена'}
            
            session_data = self.clients[user_id]
            client = session_data['client']
            phone = session_data['phone']
            
            # Авторизуемся с кодом
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                if not password:
                    return {'success': False, 'need_password': True}
                await client.sign_in(password=password)
            
            # Получаем session string
            session_string = client.session.save()
            
            # Сохраняем в БД
            account_id = self.db.create_account(
                user_id=user_id,
                phone=phone,
                session_string=session_string,
                api_id=session_data['api_id'],
                api_hash=session_data['api_hash']
            )
            
            # Очищаем временные данные
            del self.clients[user_id]
            
            logger.info(f"✅ Account {phone} connected for user {user_id}")
            
            return {
                'success': True,
                'account_id': account_id
            }
            
        except Exception as e:
            logger.error(f"Error in verify_code: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def init_database(self):
        """Инициализация базы данных"""
        # Using direct connection
            
            # Таблица пользователей
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    subscription_plan TEXT DEFAULT 'trial',
                    subscription_expires TIMESTAMP,
                    is_banned INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица аккаунтов
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    phone TEXT NOT NULL,
                    name TEXT,
                    username TEXT,
                    session_string TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id),
                    UNIQUE(user_id, phone)
                )
            ''')
            
            # Таблица рассылок
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS mailings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    message_text TEXT NOT NULL,
                    message_type TEXT DEFAULT 'text',
                    media_path TEXT,
                    targets TEXT NOT NULL,
                    accounts TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    total INTEGER DEFAULT 0,
                    sent INTEGER DEFAULT 0,
                    errors INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id)
                )
            ''')
            
            # Таблица расписаний
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    mailing_config TEXT NOT NULL,
                    schedule_type TEXT NOT NULL,
                    schedule_time TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    last_run TIMESTAMP,
                    next_run TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id)
                )
            ''')
            
            # Таблица платежей
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    plan TEXT NOT NULL,
                    amount REAL NOT NULL,
                    payment_method TEXT NOT NULL,
                    transaction_id TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    approved_at TIMESTAMP,
                    approved_by INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id)
                )
            ''')
            
            # Таблица логов
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT NOT NULL,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id)
                )
            ''')
            
            # Индексы для оптимизации
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_accounts_user_id ON accounts(user_id)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_mailings_user_id ON mailings(user_id)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_mailings_status ON mailings(status)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_user_id ON logs(user_id)')
    
    # ==================== USERS ====================
    
    def create_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        """Создать нового пользователя"""
        try:
            self.self.cursor.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, last_activity)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, username, first_name, last_name, datetime.now()))
            self.self.conn.commit()
            logger.info(f"✅ New user created: {user_id}")
        except sqlite3.IntegrityError:
            logger.warning(f"User {user_id} already exists")
            
            # Проверяем существует ли пользователь
            self.cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,))
            exists = self.cursor.fetchone()
            
            if exists:
                # Обновляем информацию
                self.cursor.execute('''
                    UPDATE users 
                    SET username = ?, first_name = ?, last_name = ?, last_active = CURRENT_TIMESTAMP
                    WHERE telegram_id = ?
                ''', (username, first_name, last_name, telegram_id))
                return telegram_id
            else:
                # Создаём нового пользователя с trial подпиской на 7 дней
                expires = datetime.now() + timedelta(days=7)
                self.cursor.execute('''
                    INSERT INTO users (telegram_id, username, first_name, last_name, subscription_plan, subscription_expires)
                    VALUES (?, ?, ?, ?, 'trial', ?)
                ''', (telegram_id, username, first_name, last_name, expires))
                
                # Логируем БЕЗ вызова add_log (избегаем рекурсии)
                try:
                    self.cursor.execute('''
                        INSERT INTO logs (user_id, action, details)
                        VALUES (?, 'user_registered', ?)
                    ''', (telegram_id, f'New user: {username or telegram_id}'))
                except:
                    pass  # Игнорируем ошибки логирования
                
                logger.info(f"✅ New user created: {telegram_id}")
                return telegram_id
    
    def get_user(self, telegram_id):
        """Получить пользователя"""
        # Using direct connection
            self.cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
            row = self.cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_users(self, active_only=False):
        """Получить всех пользователей"""
        # Using direct connection
            query = 'SELECT * FROM users'
            if active_only:
                query += ' WHERE is_banned = 0'
            self.cursor.execute(query)
            return [dict(row) for row in self.cursor.fetchall()]
    
    def update_user_subscription(self, telegram_id, plan, days):
        """Обновить подписку пользователя"""
        # Using direct connection
            expires = datetime.now() + timedelta(days=days)
            self.cursor.execute('''
                UPDATE users 
                SET subscription_plan = ?, subscription_expires = ?
                WHERE telegram_id = ?
            ''', (plan, expires, telegram_id))
            
            try:
                self.cursor.execute('''
                    INSERT INTO logs (user_id, action, details)
                    VALUES (?, 'subscription_updated', ?)
                ''', (telegram_id, f'Plan: {plan}, Days: {days}'))
            except:
                pass
            
            logger.info(f"✅ Subscription updated for user {telegram_id}: {plan}")
    
    def ban_user(self, telegram_id):
        """Забанить пользователя"""
        # Using direct connection
            self.cursor.execute('UPDATE users SET is_banned = 1 WHERE telegram_id = ?', (telegram_id,))
            logger.info(f"🚫 User {telegram_id} banned")
    
    def unban_user(self, telegram_id):
        """Разбанить пользователя"""
        # Using direct connection
            self.cursor.execute('UPDATE users SET is_banned = 0 WHERE telegram_id = ?', (telegram_id,))
            logger.info(f"✅ User {telegram_id} unbanned")
    
    # ==================== ACCOUNTS ====================
    
    def add_account(self, user_id, phone, session_string, name=None, username=None):
        """Добавить аккаунт"""
        # Using direct connection
            try:
                self.cursor.execute('''
                    INSERT INTO accounts (user_id, phone, name, username, session_string)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, phone, name, username, session_string))
                
                account_id = self.cursor.lastrowid
                
                try:
                    self.cursor.execute('''
                        INSERT INTO logs (user_id, action, details)
                        VALUES (?, 'account_added', ?)
                    ''', (user_id, f'Phone: {phone}'))
                except:
                    pass
                
                logger.info(f"✅ Account {phone} added for user {user_id}")
                return account_id
            except sqlite3.IntegrityError:
                logger.warning(f"⚠️ Account {phone} already exists for user {user_id}")
                return None
    
    def get_user_accounts(self, user_id, active_only=True):
        """Получить аккаунты пользователя"""
        # Using direct connection
            query = 'SELECT * FROM accounts WHERE user_id = ?'
            if active_only:
                query += ' AND is_active = 1'
            self.cursor.execute(query, (user_id,))
            return [dict(row) for row in self.cursor.fetchall()]
    
    def get_account(self, account_id):
        """Получить аккаунт по ID"""
        # Using direct connection
            self.cursor.execute('SELECT * FROM accounts WHERE id = ?', (account_id,))
            row = self.cursor.fetchone()
            return dict(row) if row else None

    def get_account_by_phone(self, phone: str) -> Optional[Dict]:
        """Получить аккаунт по номеру телефона"""
        try:
            self.self.cursor.execute("""
                SELECT * FROM accounts 
                WHERE phone = ?
            """, (phone,))
        
            row = self.self.cursor.fetchone()
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
    
    def update_account(self, account_id, **kwargs):
        """Обновить аккаунт"""
        # Using direct connection
            
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
                self.cursor.execute(query, values)
    
    def delete_account(self, account_id, user_id):
        """Удалить аккаунт"""
        # Using direct connection
            self.cursor.execute('DELETE FROM accounts WHERE id = ? AND user_id = ?', (account_id, user_id))
            
            try:
                self.cursor.execute('''
                    INSERT INTO logs (user_id, action, details)
                    VALUES (?, 'account_deleted', ?)
                ''', (user_id, f'Account ID: {account_id}'))
            except:
                pass
            
            logger.info(f"✅ Account {account_id} deleted")
    
    def count_user_accounts(self, user_id):
        """Подсчитать количество аккаунтов пользователя"""
        # Using direct connection
            self.cursor.execute('SELECT COUNT(*) as count FROM accounts WHERE user_id = ? AND is_active = 1', (user_id,))
            return self.cursor.fetchone()['count']
    
    # ==================== MAILINGS ====================
    
    def create_mailing(self, user_id, message_text, targets, accounts, message_type='text', media_path=None):
        """Создать рассылку"""
        # Using direct connection
            
            import json
            targets_json = json.dumps(targets)
            accounts_json = json.dumps(accounts)
            
            self.cursor.execute('''
                INSERT INTO mailings (user_id, message_text, message_type, media_path, targets, accounts, total)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, message_text, message_type, media_path, targets_json, accounts_json, len(targets)))
            
            mailing_id = self.cursor.lastrowid
            
            try:
                self.cursor.execute('''
                    INSERT INTO logs (user_id, action, details)
                    VALUES (?, 'mailing_created', ?)
                ''', (user_id, f'Mailing ID: {mailing_id}, Targets: {len(targets)}'))
            except:
                pass
            
            logger.info(f"✅ Mailing {mailing_id} created for user {user_id}")
            return mailing_id
    
    def get_mailing(self, mailing_id):
        """Получить рассылку по ID"""
        # Using direct connection
            self.cursor.execute('SELECT * FROM mailings WHERE id = ?', (mailing_id,))
            row = self.cursor.fetchone()
            if row:
                data = dict(row)
                import json
                data['targets'] = json.loads(data['targets'])
                data['accounts'] = json.loads(data['accounts'])
                return data
            return None
    
    def get_user_mailings(self, user_id, limit=50):
        """Получить рассылки пользователя"""
        # Using direct connection
            self.cursor.execute('''
                SELECT * FROM mailings 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (user_id, limit))
            
            mailings = []
            import json
            for row in self.cursor.fetchall():
                data = dict(row)
                data['targets'] = json.loads(data['targets'])
                data['accounts'] = json.loads(data['accounts'])
                mailings.append(data)
            return mailings
    
    def update_mailing(self, mailing_id, **kwargs):
        """Обновить рассылку"""
        # Using direct connection
            
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
                self.cursor.execute(query, values)
    
    def count_user_mailings_today(self, user_id):
        """Подсчитать количество рассылок пользователя сегодня"""
        # Using direct connection
            self.cursor.execute('''
                SELECT COUNT(*) as count 
                FROM mailings 
                WHERE user_id = ? 
                AND DATE(created_at) = DATE('now')
            ''', (user_id,))
            return self.cursor.fetchone()['count']
    
    # ==================== SCHEDULES ====================
    
    def create_schedule(self, user_id, name, mailing_config, schedule_type, schedule_time):
        """Создать расписание"""
        # Using direct connection
            
            import json
            config_json = json.dumps(mailing_config)
            
            self.cursor.execute('''
                INSERT INTO schedules (user_id, name, mailing_config, schedule_type, schedule_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, name, config_json, schedule_type, schedule_time))
            
            schedule_id = self.cursor.lastrowid
            
            try:
                self.cursor.execute('''
                    INSERT INTO logs (user_id, action, details)
                    VALUES (?, 'schedule_created', ?)
                ''', (user_id, f'Schedule ID: {schedule_id}'))
            except:
                pass
            
            logger.info(f"✅ Schedule {schedule_id} created for user {user_id}")
            return schedule_id
    
    def get_schedule(self, schedule_id):
        """Получить расписание по ID"""
        # Using direct connection
            self.cursor.execute('SELECT * FROM schedules WHERE id = ?', (schedule_id,))
            row = self.cursor.fetchone()
            if row:
                data = dict(row)
                import json
                data['mailing_config'] = json.loads(data['mailing_config'])
                return data
            return None
    
    def get_user_schedules(self, user_id, active_only=True):
        """Получить расписания пользователя"""
        # Using direct connection
            query = 'SELECT * FROM schedules WHERE user_id = ?'
            if active_only:
                query += ' AND is_active = 1'
            query += ' ORDER BY created_at DESC'
            self.cursor.execute(query, (user_id,))
            
            schedules = []
            import json
            for row in self.cursor.fetchall():
                data = dict(row)
                data['mailing_config'] = json.loads(data['mailing_config'])
                schedules.append(data)
            return schedules
    
    def get_active_schedules(self):
        """Получить все активные расписания"""
        # Using direct connection
            self.cursor.execute('''
                SELECT * FROM schedules 
                WHERE is_active = 1 
                AND (next_run IS NULL OR next_run <= CURRENT_TIMESTAMP)
            ''')
            
            schedules = []
            import json
            for row in self.cursor.fetchall():
                data = dict(row)
                data['mailing_config'] = json.loads(data['mailing_config'])
                schedules.append(data)
            return schedules
    
    def update_schedule(self, schedule_id, **kwargs):
        """Обновить расписание"""
        # Using direct connection
            
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
                self.cursor.execute(query, values)
    
    def delete_schedule(self, schedule_id, user_id):
        """Удалить расписание"""
        # Using direct connection
            self.cursor.execute('DELETE FROM schedules WHERE id = ? AND user_id = ?', (schedule_id, user_id))
            
            try:
                self.cursor.execute('''
                    INSERT INTO logs (user_id, action, details)
                    VALUES (?, 'schedule_deleted', ?)
                ''', (user_id, f'Schedule ID: {schedule_id}'))
            except:
                pass
            
            logger.info(f"✅ Schedule {schedule_id} deleted")
    
    # ==================== PAYMENTS ====================
    
    def create_payment(self, user_id, plan, amount, payment_method, transaction_id=None):
        """Создать платёж"""
        # Using direct connection
            self.cursor.execute('''
                INSERT INTO payments (user_id, plan, amount, payment_method, transaction_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, plan, amount, payment_method, transaction_id))
            
            payment_id = self.cursor.lastrowid
            
            try:
                self.cursor.execute('''
                    INSERT INTO logs (user_id, action, details)
                    VALUES (?, 'payment_created', ?)
                ''', (user_id, f'Payment ID: {payment_id}, Plan: {plan}, Amount: {amount}'))
            except:
                pass
            
            logger.info(f"✅ Payment {payment_id} created for user {user_id}")
            return payment_id
    
    def get_payment(self, payment_id):
        """Получить платёж по ID"""
        # Using direct connection
            self.cursor.execute('''
                SELECT p.*, u.username, u.first_name 
                FROM payments p
                LEFT JOIN users u ON p.user_id = u.telegram_id
                WHERE p.id = ?
            ''', (payment_id,))
            row = self.cursor.fetchone()
            return dict(row) if row else None
    
    def get_pending_payments(self):
        """Получить ожидающие платежи"""
        # Using direct connection
            self.cursor.execute('''
                SELECT p.*, u.username, u.first_name 
                FROM payments p
                LEFT JOIN users u ON p.user_id = u.telegram_id
                WHERE p.status = 'pending'
                ORDER BY p.created_at DESC
            ''')
            return [dict(row) for row in self.cursor.fetchall()]
    
    def approve_payment(self, payment_id, admin_id):
        """Одобрить платёж"""
        # Using direct connection
            
            # Получаем информацию о платеже
            self.cursor.execute('SELECT * FROM payments WHERE id = ?', (payment_id,))
            payment = self.cursor.fetchone()
            
            if not payment or payment['status'] != 'pending':
                return False
            
            payment = dict(payment)
            
            # Обновляем статус платежа
            self.cursor.execute('''
                UPDATE payments 
                SET status = 'approved', approved_at = CURRENT_TIMESTAMP, approved_by = ?
                WHERE id = ?
            ''', (admin_id, payment_id))
            
            # Обновляем подписку пользователя
            from config import SUBSCRIPTION_PLANS
            plan = payment['plan']
            days = SUBSCRIPTION_PLANS.get(plan, {}).get('days', 30)
            
            # Получаем текущую дату окончания подписки
            self.cursor.execute('SELECT subscription_expires FROM users WHERE telegram_id = ?', (payment['user_id'],))
            user = self.cursor.fetchone()
            current_expires = user['subscription_expires'] if user else None
            
            # Рассчитываем новую дату
            if current_expires:
                try:
                    if isinstance(current_expires, str):
                        current_expires = datetime.fromisoformat(current_expires)
                    if current_expires > datetime.now():
                        # Продлеваем от текущей даты окончания
                        new_expires = current_expires + timedelta(days=days)
                    else:
                        # Подписка истекла, начинаем с текущего момента
                        new_expires = datetime.now() + timedelta(days=days)
                except:
                    new_expires = datetime.now() + timedelta(days=days)
            else:
                new_expires = datetime.now() + timedelta(days=days)
            
            self.cursor.execute('''
                UPDATE users 
                SET subscription_plan = ?, subscription_expires = ?
                WHERE telegram_id = ?
            ''', (plan, new_expires, payment['user_id']))
            
            try:
                self.cursor.execute('''
                    INSERT INTO logs (user_id, action, details)
                    VALUES (?, 'payment_approved', ?)
                ''', (payment['user_id'], f'Payment ID: {payment_id}, Plan: {plan}'))
            except:
                pass
            
            logger.info(f"✅ Payment {payment_id} approved by admin {admin_id}")
            return True
    
    def reject_payment(self, payment_id, admin_id):
        """Отклонить платёж"""
        # Using direct connection
            self.cursor.execute('''
                UPDATE payments 
                SET status = 'rejected', approved_at = CURRENT_TIMESTAMP, approved_by = ?
                WHERE id = ? AND status = 'pending'
            ''', (admin_id, payment_id))
            
            if cursor.rowcount > 0:
                self.cursor.execute('SELECT user_id FROM payments WHERE id = ?', (payment_id,))
                payment = self.cursor.fetchone()
                if payment:
                    try:
                        self.cursor.execute('''
                            INSERT INTO logs (user_id, action, details)
                            VALUES (?, 'payment_rejected', ?)
                        ''', (payment['user_id'], f'Payment ID: {payment_id}'))
                    except:
                        pass
                
                logger.info(f"❌ Payment {payment_id} rejected by admin {admin_id}")
                return True
            return False
    
    # ==================== LOGS ====================
    
    def add_log(self, user_id, action, details=None):
        """Добавить лог (безопасно, без вложенных транзакций)"""
        try:
            # Using direct connection
                self.cursor.execute('''
                    INSERT INTO logs (user_id, action, details)
                    VALUES (?, ?, ?)
                ''', (user_id, action, details))
        except Exception as e:
            # Не прерываем выполнение если лог не записался
            logger.debug(f"Failed to write log: {e}")
    
    def get_user_logs(self, user_id, limit=50):
        """Получить логи пользователя"""
        # Using direct connection
            self.cursor.execute('''
                SELECT * FROM logs 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (user_id, limit))
            return [dict(row) for row in self.cursor.fetchall()]
    
    # ==================== STATISTICS ====================
    
    def get_statistics(self):
        """Получить общую статистику"""
        # Using direct connection
            
            stats = {}
            
            # Всего пользователей
            self.cursor.execute('SELECT COUNT(*) as count FROM users')
            stats['total_users'] = self.cursor.fetchone()['count']
            
            # Активных сегодня
            self.cursor.execute('''
                SELECT COUNT(*) as count FROM users 
                WHERE DATE(last_active) = DATE('now')
            ''')
            stats['active_today'] = self.cursor.fetchone()['count']
            
            # Новых за неделю
            self.cursor.execute('''
                SELECT COUNT(*) as count FROM users 
                WHERE created_at >= datetime('now', '-7 days')
            ''')
            stats['new_this_week'] = self.cursor.fetchone()['count']
            
            # Доход за месяц
            self.cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) as total FROM payments 
                WHERE status = 'approved' 
                AND created_at >= datetime('now', '-30 days')
            ''')
            stats['revenue_month'] = self.cursor.fetchone()['total']
            
            # Ожидающие платежи
            self.cursor.execute('SELECT COUNT(*) as count FROM payments WHERE status = "pending"')
            stats['pending_payments'] = self.cursor.fetchone()['count']
            
            # Завершённые рассылки
            self.cursor.execute('SELECT COUNT(*) as count FROM mailings WHERE status = "completed"')
            stats['completed_mailings'] = self.cursor.fetchone()['count']
            
            # Всего отправлено сообщений
            self.cursor.execute('SELECT COALESCE(SUM(sent), 0) as total FROM mailings')
            stats['total_messages_sent'] = self.cursor.fetchone()['total']
            
            # Всего рассылок
            self.cursor.execute('SELECT COUNT(*) as count FROM mailings')
            stats['total_mailings'] = self.cursor.fetchone()['count']
            
            # Пользователи по тарифам
            self.cursor.execute('''
                SELECT subscription_plan, COUNT(*) as count 
                FROM users 
                GROUP BY subscription_plan
            ''')
            stats['users_by_plan'] = {row['subscription_plan']: row['count'] for row in self.cursor.fetchall()}
            
            return stats
    
    def close(self):
        """Закрыть соединение с БД"""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None