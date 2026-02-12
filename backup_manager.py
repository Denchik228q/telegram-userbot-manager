"""
Резервное копирование базы данных
"""
import os
import shutil
import logging
from datetime import datetime
from pathlib import Path
from config import DATABASE_URL, BACKUPS_DIR, MAX_BACKUPS

logger = logging.getLogger(__name__)

class BackupManager:
    def __init__(self):
        self.backup_dir = Path(BACKUPS_DIR)
        self.backup_dir.mkdir(exist_ok=True)
        logger.info("✅ BackupManager initialized")
    
    def create_backup(self):
        """Создать резервную копию"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"backup_{timestamp}.db"
            backup_path = self.backup_dir / backup_name
            
            # Копируем базу данных
            shutil.copy2(DATABASE_URL, backup_path)
            
            logger.info(f"✅ Backup created: {backup_name}")
            
            # Очищаем старые бэкапы
            self.cleanup_old_backups()
            
            return backup_path
        
        except Exception as e:
            logger.error(f"❌ Error creating backup: {e}")
            return None
    
    def cleanup_old_backups(self):
        """Удалить старые бэкапы"""
        try:
            backups = sorted(self.backup_dir.glob('backup_*.db'), key=os.path.getmtime)
            
            # Удаляем самые старые если превышен лимит
            while len(backups) > MAX_BACKUPS:
                old_backup = backups.pop(0)
                old_backup.unlink()
                logger.info(f"🗑 Deleted old backup: {old_backup.name}")
        
        except Exception as e:
            logger.error(f"❌ Error cleaning up backups: {e}")
    
    def restore_backup(self, backup_name):
        """Восстановить из бэкапа"""
        try:
            backup_path = self.backup_dir / backup_name
            
            if not backup_path.exists():
                logger.error(f"❌ Backup not found: {backup_name}")
                return False
            
            # Создаём бэкап текущей БД перед восстановлением
            self.create_backup()
            
            # Восстанавливаем
            shutil.copy2(backup_path, DATABASE_URL)
            
            logger.info(f"✅ Restored from backup: {backup_name}")
            return True
        
        except Exception as e:
            logger.error(f"❌ Error restoring backup: {e}")
            return False
    
    def list_backups(self):
        """Список всех бэкапов"""
        backups = sorted(self.backup_dir.glob('backup_*.db'), key=os.path.getmtime, reverse=True)
        return [
            {
                'name': backup.name,
                'size': backup.stat().st_size,
                'created': datetime.fromtimestamp(backup.stat().st_mtime)
            }
            for backup in backups
        ]
    
    def shutdown(self):
        """Завершение работы (для совместимости)"""
        pass