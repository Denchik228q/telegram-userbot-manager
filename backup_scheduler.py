#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Автоматический планировщик бэкапов
"""

import os
import logging
import asyncio
from datetime import datetime, time
from database import Database
from telegram import Bot
from config_userbot import ADMIN_ID, MANAGER_BOT_TOKEN

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class BackupScheduler:
    """Планировщик автоматических бэкапов"""
    
    def __init__(self):
        """Инициализация"""
        self.db = Database()
        self.bot = Bot(token=MANAGER_BOT_TOKEN)
        self.backup_time = time(23, 55)  # 23:55 каждый день
        self.backup_dir = 'backups'
        os.makedirs(self.backup_dir, exist_ok=True)
        logger.info("📦 BackupScheduler initialized")
    
    async def create_backup(self):
        """Создание бэкапа"""
        try:
            logger.info("🔄 Starting backup...")
            
            # Создаём бэкап
            backup_path = self.db.backup_database()
            
            # Получаем статистику
            stats = self.db.get_stats()
            file_size = os.path.getsize(backup_path) / 1024  # KB
            
            backup_info = (
                f"✅ *Автоматический бэкап создан!*\n\n"
                f"📅 *Дата:* {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
                f"📁 *Файл:* `{os.path.basename(backup_path)}`\n"
                f"💾 *Размер:* {file_size:.2f} KB\n\n"
                f"📊 *Статистика БД:*\n"
                f"👥 Всего пользователей: {stats.get('total_users', 0)}\n"
                f"💰 Активных подписок: {stats.get('active_subscriptions', 0)}\n"
                f"📅 Новых сегодня: {stats.get('new_today', 0)}\n\n"
                f"🔒 Бэкап сохранён на сервере"
            )
            
            # Отправляем уведомление админу
            await self.bot.send_message(
                chat_id=ADMIN_ID,
                text=backup_info,
                parse_mode='Markdown'
            )
            
            # Отправляем файл админу
            try:
                with open(backup_path, 'rb') as backup_file:
                    await self.bot.send_document(
                        chat_id=ADMIN_ID,
                        document=backup_file,
                        filename=os.path.basename(backup_path),
                        caption="📦 Файл бэкапа базы данных"
                    )
                logger.info("✅ Backup file sent to admin")
            except Exception as e:
                logger.error(f"❌ Error sending backup file: {e}")
            
            # Очищаем старые бэкапы (старше 7 дней)
            self.cleanup_old_backups(days=7)
            
            logger.info(f"✅ Backup created: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Backup error: {e}")
            
            # Уведомляем админа об ошибке
            try:
                await self.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"❌ *Ошибка при создании бэкапа!*\n\n"
                         f"⚠️ {str(e)}\n\n"
                         f"Проверьте логи сервера.",
                    parse_mode='Markdown'
                )
            except:
                pass
            
            return False
    
    def cleanup_old_backups(self, days: int = 7):
        """Удаление старых бэкапов"""
        try:
            import time
            current_time = time.time()
            
            for filename in os.listdir(self.backup_dir):
                if filename.startswith('backup_') and filename.endswith('.db'):
                    filepath = os.path.join(self.backup_dir, filename)
                    file_age_days = (current_time - os.path.getmtime(filepath)) / 86400
                    
                    if file_age_days > days:
                        os.remove(filepath)
                        logger.info(f"🗑️ Deleted old backup: {filename}")
        
        except Exception as e:
            logger.error(f"❌ Cleanup error: {e}")
    
    async def run_daily_backup(self):
        """Ежедневный бэкап в заданное время"""
        logger.info(f"⏰ Backup scheduled at {self.backup_time.strftime('%H:%M')}")
        
        while True:
            try:
                now = datetime.now().time()
                
                # Проверяем, наступило ли время бэкапа
                if now.hour == self.backup_time.hour and now.minute == self.backup_time.minute:
                    await self.create_backup()
                    # Ждём 61 секунду чтобы не запустить дважды
                    await asyncio.sleep(61)
                else:
                    # Проверяем каждую минуту
                    await asyncio.sleep(60)
            
            except Exception as e:
                logger.error(f"❌ Scheduler error: {e}")
                await asyncio.sleep(60)
    
    async def manual_backup(self):
        """Ручной бэкап (для команды /backup)"""
        return await self.create_backup()


# Глобальный экземпляр планировщика
backup_scheduler = BackupScheduler()