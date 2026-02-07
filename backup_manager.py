import asyncio
import aiosqlite
from datetime import datetime
import shutil
import os

async def create_backup():
    """Создание бэкапа базы данных"""
    
    db_file = 'bot.db'
    
    if not os.path.exists(db_file):
        print("❌ База данных не найдена!")
        return
    
    # Создаём папку для бэкапов
    backup_dir = 'backups'
    os.makedirs(backup_dir, exist_ok=True)
    
    # Имя бэкапа с датой
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = f"{backup_dir}/bot_backup_{timestamp}.db"
    
    try:
        # Копируем базу
        shutil.copy2(db_file, backup_file)
        
        # Проверяем что скопировалось
        db = await aiosqlite.connect(backup_file)
        cursor = await db.execute('SELECT COUNT(*) FROM users')
        count = (await cursor.fetchone())[0]
        await db.close()
        
        print(f"✅ Бэкап создан: {backup_file}")
        print(f"📊 Пользователей в бэкапе: {count}")
        
        return backup_file
        
    except Exception as e:
        print(f"❌ Ошибка создания бэкапа: {e}")
        return None


async def list_backups():
    """Список бэкапов"""
    backup_dir = 'backups'
    
    if not os.path.exists(backup_dir):
        print("📁 Папка с бэкапами пуста")
        return
    
    backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.db')])
    
    if not backups:
        print("📁 Бэкапы не найдены")
        return
    
    print(f"\n📋 Найдено бэкапов: {len(backups)}\n")
    
    for backup in backups:
        filepath = os.path.join(backup_dir, backup)
        size = os.path.getsize(filepath) / 1024  # KB
        mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
        
        print(f"📦 {backup}")
        print(f"   Размер: {size:.1f} KB")
        print(f"   Дата: {mtime.strftime('%Y-%m-%d %H:%M:%S')}\n")


async def restore_backup(backup_file):
    """Восстановление из бэкапа"""
    
    if not os.path.exists(backup_file):
        print(f"❌ Файл не найден: {backup_file}")
        return False
    
    try:
        # Создаём бэкап текущей базы перед восстановлением
        current_backup = await create_backup()
        print(f"💾 Текущая база сохранена: {current_backup}")
        
        # Восстанавливаем из бэкапа
        shutil.copy2(backup_file, 'bot.db')
        
        # Проверяем
        db = await aiosqlite.connect('bot.db')
        cursor = await db.execute('SELECT COUNT(*) FROM users')
        count = (await cursor.fetchone())[0]
        await db.close()
        
        print(f"✅ База восстановлена из: {backup_file}")
        print(f"📊 Пользователей: {count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка восстановления: {e}")
        return False


async def main():
    """Главное меню"""
    print("=" * 50)
    print("🔧 УПРАВЛЕНИЕ БЭКАПАМИ БД")
    print("=" * 50)
    print("\n1. Создать бэкап")
    print("2. Показать все бэкапы")
    print("3. Восстановить из бэкапа")
    print("4. Выход\n")
    
    choice = input("Выберите действие (1-4): ").strip()
    
    if choice == '1':
        await create_backup()
    
    elif choice == '2':
        await list_backups()
    
    elif choice == '3':
        await list_backups()
        backup_name = input("\nВведите имя файла для восстановления: ").strip()
        backup_path = os.path.join('backups', backup_name)
        
        confirm = input(f"⚠️ Восстановить из {backup_name}? (yes/no): ").strip().lower()
        if confirm == 'yes':
            await restore_backup(backup_path)
        else:
            print("❌ Отменено")
    
    elif choice == '4':
        print("👋 До свидания!")
        return
    
    else:
        print("❌ Неверный выбор")


if __name__ == '__main__':
    asyncio.run(main())