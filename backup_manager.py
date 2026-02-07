#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Менеджер резервного копирования базы данных
"""

import os
import logging
import shutil
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)


class BackupManager:
    """Управление бэкапами базы данных"""
    
    def __init__(self, db, bot_token, chat_id, interval_hours=6):
        """
        Инициализация менеджера бэкапов
        
        Args:
            db: Объект базы данных
            bot_token: Токен бота для отправки файлов
            chat_id: ID чата для отправки бэкапов
            interval_hours: Интервал создания бэкапов (часы)
        """
        self.db = db
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.interval_hours = interval_hours
        self.scheduler = AsyncIOScheduler()
        
        # Создаём папку для бэкапов
        self.backup_dir = 'backups'
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # Запускаем планировщик
        self._start_scheduler()
        
        logger.info(f"💾 BackupManager initialized (interval: {interval_hours}h)")
    
    def _start_scheduler(self):
        """Запуск планировщика бэкапов"""
        try:
            # Добавляем задачу
            self.scheduler.add_job(
                self._create_backup,
                'interval',
                hours=self.interval_hours,
                id='auto_backup'
            )
            
            # Запускаем
            self.scheduler.start()
            logger.info("✅ Backup scheduler started")
            
        except Exception as e:
            logger.error(f"Error starting backup scheduler: {e}")
    
    async def _create_backup(self):
        """Создание бэкапа"""
        try:
            # Имя файла с временной меткой
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"backup_{timestamp}.db"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            # Копируем базу данных
            shutil.copy2(self.db.db_path, backup_path)
            
            logger.info(f"✅ Backup created: {backup_filename}")
            
            # Отправляем админу
            await self._send_backup_to_admin(backup_path, backup_filename)
            
            # Очищаем старые бэкапы (оставляем последние 5)
            self._cleanup_old_backups()
            
            return backup_path
            
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return None
    
    async def _send_backup_to_admin(self, file_path, filename):
        """Отправка бэкапа администратору"""
        try:
            from telegram import Bot
            
            bot = Bot(token=self.bot_token)
            
            with open(file_path, 'rb') as f:
                await bot.send_document(
                    chat_id=self.chat_id,
                    document=f,
                    filename=filename,
                    caption=f"💾 Автоматический бэкап базы данных\n"
                            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
                )
            
            logger.info(f"✅ Backup sent to admin (chat_id: {self.chat_id})")
            
        except Exception as e:
            logger.error(f"Error sending backup to admin: {e}")
    
    def _cleanup_old_backups(self, keep_last=5):
        """Удаление старых бэкапов"""
        try:
            # Получаем список всех бэкапов
            backups = []
            for filename in os.listdir(self.backup_dir):
                if filename.startswith('backup_') and filename.endswith('.db'):
                    filepath = os.path.join(self.backup_dir, filename)
                    backups.append((filepath, os.path.getmtime(filepath)))
            
            # Сортируем по времени (новые первыми)
            backups.sort(key=lambda x: x[1], reverse=True)
            
            # Удаляем старые
            for filepath, _ in backups[keep_last:]:
                os.remove(filepath)
                logger.info(f"🗑️ Removed old backup: {os.path.basename(filepath)}")
                
        except Exception as e:
            logger.error(f"Error cleaning up backups: {e}")
    
    async def manual_backup(self):
        """Ручное создание бэкапа"""
        logger.info("📦 Creating manual backup...")
        result = await self._create_backup()
        
        if result:
            return "✅ Бэкап успешно создан и отправлен"
        else:
            return "❌ Ошибка создания бэкапа"
    
    def shutdown(self):
        """Остановка планировщика"""
        try:
            self.scheduler.shutdown()
            logger.info("🛑 Backup scheduler stopped")
        except:
            pass