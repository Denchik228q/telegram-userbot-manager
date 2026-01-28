import asyncio
import aiosqlite

async def reset_database():
    db = await aiosqlite.connect('bot.db')
    
    # Удаляем старую таблицу
    await db.execute('DROP TABLE IF EXISTS users')
    
    # Создаём заново с правильными колонками
    await db.execute('''
        CREATE TABLE users (
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
    
    await db.commit()
    await db.close()
    print("✅ Database reset complete!")

asyncio.run(reset_database())