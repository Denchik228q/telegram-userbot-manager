"""
Планировщик рассылок
"""
import asyncio
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

logger = logging.getLogger(__name__)

class MailingScheduler:
    def __init__(self, database, userbot_manager, bot):
        self.db = database
        self.userbot_manager = userbot_manager
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()
        logger.info("✅ Scheduler started")
        
        # Запускаем проверку активных расписаний
        asyncio.create_task(self.check_schedules())
    
    async def check_schedules(self):
        """Проверка и запуск активных расписаний"""
        while True:
            try:
                schedules = self.db.get_active_schedules()
                
                for schedule in schedules:
                    schedule_id = schedule['id']
                    user_id = schedule['user_id']
                    
                    # Проверяем пора ли запускать
                    if self._should_run(schedule):
                        logger.info(f"🚀 Running schedule {schedule_id}")
                        await self._run_scheduled_mailing(schedule)
                        
                        # Обновляем время следующего запуска
                        next_run = self._calculate_next_run(schedule)
                        self.db.update_schedule(
                            schedule_id,
                            last_run=datetime.now(),
                            next_run=next_run
                        )
                
            except Exception as e:
                logger.error(f"❌ Error in check_schedules: {e}")
            
            # Проверяем каждую минуту
            await asyncio.sleep(60)
    
    def _should_run(self, schedule):
        """Проверить нужно ли запускать расписание"""
        next_run = schedule.get('next_run')
        
        if not next_run:
            return True  # Первый запуск
        
        # Преобразуем строку в datetime если нужно
        if isinstance(next_run, str):
            next_run = datetime.fromisoformat(next_run)
        
        return datetime.now() >= next_run
    
    def _calculate_next_run(self, schedule):
        """Рассчитать время следующего запуска"""
        schedule_type = schedule['schedule_type']
        
        if schedule_type == 'once':
            return None  # Разовое расписание
        
        elif schedule_type == 'daily':
            return datetime.now() + timedelta(days=1)
        
        elif schedule_type == 'weekly':
            return datetime.now() + timedelta(weeks=1)
        
        elif schedule_type == 'monthly':
            return datetime.now() + timedelta(days=30)
        
        else:
            return None
    
    async def _run_scheduled_mailing(self, schedule):
        """Запустить рассылку по расписанию"""
        try:
            user_id = schedule['user_id']
            config = schedule['mailing_config']
            
            # Создаём рассылку из конфига
            mailing_id = self.db.create_mailing(
                user_id=user_id,
                message_text=config.get('message_text'),
                targets=config.get('targets'),
                accounts=config.get('accounts'),
                message_type=config.get('message_type', 'text'),
                media_path=config.get('media_path')
            )
            
            # Уведомляем пользователя
            await self.bot.send_message(
                user_id,
                f"🚀 **Запущена запланированная рассылка**\n\n"
                f"Расписание: {schedule['name']}\n"
                f"ID рассылки: `{mailing_id}`"
            )
            
            logger.info(f"✅ Scheduled mailing {mailing_id} started for user {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Error running scheduled mailing: {e}")
    
    def shutdown(self):
        """Остановить планировщик"""
        self.scheduler.shutdown()
        logger.info("✅ Scheduler stopped")