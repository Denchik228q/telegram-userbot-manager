import asyncio
import aiosqlite

async def migrate():
    db = await aiosqlite.connect("bot.db")
    
    try:
        # Добавляем колонку trial_used
        await db.execute("ALTER TABLE users ADD COLUMN trial_used BOOLEAN DEFAULT 0")
        print("✅ Добавлена колонка trial_used")
    except Exception as e:
        print(f"⚠️ trial_used уже существует или ошибка: {e}")
    
    try:
        # Обновляем существующих пользователей
        # Устанавливаем trial_used = 1 (использована) для всех кроме новых
        await db.execute("UPDATE users SET trial_used = 1 WHERE subscription_type != 'trial'")
        print("✅ Обновлены существующие пользователи")
    except Exception as e:
        print(f"❌ Ошибка обновления: {e}")
    
    try:
        # Меняем subscription_type с 'free' на 'trial' для новых пользователей
        # (если хотите дать им пробную версию)
        await db.execute("UPDATE users SET subscription_type = 'trial', trial_used = 0 WHERE subscription_type = 'free' AND total_messages_sent = 0")
        print("✅ Новые пользователи получили пробную версию")
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")
    
    await db.commit()
    await db.close()
    print("✅ Миграция завершена!")

if __name__ == "__main__":
    asyncio.run(migrate())