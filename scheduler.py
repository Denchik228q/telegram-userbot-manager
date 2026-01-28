#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Планировщик для автоматических рассылок
"""

import asyncio
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from database import Database
from userbot import UserbotManager

logger = logging.getLogger(__name__)

class MailingScheduler:
    """Планировщик рассылок"""
    
    def __init__(self, db: Database, userbot_manager: UserbotManager):
        """Инициализация"""
        self.db = db
        self.userbot_manager = userbot_manager
        self.scheduler = AsyncIOScheduler()
        logger.info("📅 MailingScheduler initialized")
    
    def start(self):
        """Запуск планировщика"""
        self.scheduler.start()
        self.load_scheduled_mailings()
        logger.info("✅ Scheduler started")
    
    def stop(self):
        """Остановка планировщика"""
        self.scheduler.shutdown()
        logger.info("❌ Scheduler stopped")
    
    def load_scheduled_mailings(self):
        """Загрузка всех запланированных рассылок"""
        mailings = self.db.get_active_scheduled_mailings()
        logger.info(f"📋 Loading {len(mailings)} scheduled mailings")
        
        for mailing in mailings:
            self.add_job(mailing)
    
    def add_job(self, mailing: dict):
        """Добавление задачи в планировщик"""
        try:
            schedule_data = mailing['schedule_data']
            schedule_type = mailing['schedule_type']
            
            if schedule_type == 'weekly':
                # Еженедельная рассылка
                for day_time in schedule_data['times']:
                    day_of_week = day_time['day']  # 0=Monday, 6=Sunday
                    time_str = day_time['time']  # "HH:MM"
                    hour, minute = map(int, time_str.split(':'))
                    
                    trigger = CronTrigger(
                        day_of_week=day_of_week,
                        hour=hour,
                        minute=minute
                    )
                    
                    self.scheduler.add_job(
                        self.execute_mailing,
                        trigger=trigger,
                        args=[mailing['id']],
                        id=f"mailing_{mailing['id']}_{day_of_week}_{time_str}",
                        replace_existing=True
                    )
                    
                    logger.info(f"✅ Added job: Day {day_of_week} at {time_str}")
            
            elif schedule_type == 'daily':
                # Ежедневная рассылка
                for time_str in schedule_data['times']:
                    hour, minute = map(int, time_str.split(':'))
                    
                    trigger = CronTrigger(
                        hour=hour,
                        minute=minute
                    )
                    
                    self.scheduler.add_job(
                        self.execute_mailing,
                        trigger=trigger,
                        args=[mailing['id']],
                        id=f"mailing_{mailing['id']}_{time_str}",
                        replace_existing=True
                    )
                    
                    logger.info(f"✅ Added daily job at {time_str}")
            
            elif schedule_type == 'once':
                # Одноразовая рассылка
                run_date = datetime.fromisoformat(schedule_data['datetime'])
                
                self.scheduler.add_job(
                    self.execute_mailing,
                    trigger='date',
                    run_date=run_date,
                    args=[mailing['id']],
                    id=f"mailing_{mailing['id']}_once",
                    replace_existing=True
                )
                
                logger.info(f"✅ Added one-time job at {run_date}")
        
        except Exception as e:
            logger.error(f"❌ Error adding job: {e}")
    
    async def execute_mailing(self, mailing_id: int):
        """Выполнение рассылки"""
        try:
            logger.info(f"🚀 Executing scheduled mailing {mailing_id}")
            
            # Получаем данные рассылки
            mailings = self.db.get_active_scheduled_mailings()
            mailing = next((m for m in mailings if m['id'] == mailing_id), None)
            
            if not mailing:
                logger.error(f"❌ Mailing {mailing_id} not found")
                return
            
            user_id = mailing['user_id']
            targets = mailing['targets']
            selected_accounts = mailing['selected_accounts']
            
            # Если аккаунты не выбраны - берём все активные
            if not selected_accounts:
                accounts = self.db.get_user_accounts(user_id)
                selected_accounts = [acc['id'] for acc in accounts]
            
            if not selected_accounts:
                logger.error(f"❌ No accounts found for user {user_id}")
                return
            
            # Распределяем таргеты по аккаунтам
            accounts_data = [self.db.get_account(acc_id) for acc_id in selected_accounts]
            accounts_data = [acc for acc in accounts_data if acc]
            
            if not accounts_data:
                logger.error(f"❌ No valid accounts")
                return
            
            targets_per_account = len(targets) // len(accounts_data)
            remainder = len(targets) % len(accounts_data)
            
            start_idx = 0
            for idx, account in enumerate(accounts_data):
                # Распределяем таргеты
                end_idx = start_idx + targets_per_account + (1 if idx < remainder else 0)
                account_targets = targets[start_idx:end_idx]
                start_idx = end_idx
                
                if not account_targets:
                    continue
                
                # Запускаем рассылку для этого аккаунта
                                await self.run_account_mailing(account, account_targets, mailing)
                
                # Задержка между аккаунтами
                await asyncio.sleep(5)
            
            # Обновляем время последнего запуска
            self.db.update_scheduled_mailing_last_run(mailing_id)
            logger.info(f"✅ Scheduled mailing {mailing_id} completed")
            
        except Exception as e:
            logger.error(f"❌ Error executing mailing {mailing_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def run_account_mailing(self, account: dict, targets: list, mailing: dict):
        """Рассылка с одного аккаунта"""
        try:
            session_id = account['session_id']
            phone = account['phone_number']
            account_name = account['account_name']
            
            logger.info(f"📨 Starting mailing from {account_name} ({phone})")
            
            # Подключаемся
            connect_result = await self.userbot_manager.connect_session(phone, session_id)
            if not connect_result['success']:
                logger.error(f"❌ Failed to connect {account_name}")
                return
            
            sent = 0
            errors = 0
            
            # Фаза 1: Вступление
            for target in targets:
                try:
                    join_result = await self.userbot_manager.join_chat(
                        session_id=session_id,
                        phone=phone,
                        target=target
                    )
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Error joining {target}: {e}")
            
            # Пауза после вступлений
            await asyncio.sleep(10)
            
            # Фаза 2: Отправка
            for target in targets:
                try:
                    # Определяем тип сообщения
                    if mailing['message_text']:
                        result = await self.userbot_manager.send_message(
                            session_id=session_id,
                            phone=phone,
                            target=target,
                            message=mailing['message_text']
                        )
                    elif mailing['message_photo']:
                        result = await self.userbot_manager.send_photo(
                            session_id=session_id,
                            phone=phone,
                            target=target,
                            photo_path=mailing['message_photo'],
                            caption=mailing['message_caption'] or ""
                        )
                    elif mailing['message_video']:
                        result = await self.userbot_manager.send_video(
                            session_id=session_id,
                            phone=phone,
                            target=target,
                            video_path=mailing['message_video'],
                            caption=mailing['message_caption'] or ""
                        )
                    else:
                        continue
                    
                    if result.get('success'):
                        sent += 1
                    else:
                        errors += 1
                    
                    await asyncio.sleep(5)
                    
                except Exception as e:
                    errors += 1
                    logger.error(f"Error sending to {target}: {e}")
            
            # Сохраняем статистику
            message_text = mailing['message_text'] or mailing['message_caption'] or "[Медиа]"
            self.db.add_mailing(account['user_id'], message_text, sent, errors)
            
            logger.info(f"✅ {account_name}: sent={sent}, errors={errors}")
            
        except Exception as e:
            logger.error(f"❌ Error in account mailing: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def remove_job(self, mailing_id: int):
        """Удаление задачи из планировщика"""
        try:
            jobs = self.scheduler.get_jobs()
            for job in jobs:
                if str(mailing_id) in job.id:
                    job.remove()
                    logger.info(f"✅ Job removed: {job.id}")
        except Exception as e:
            logger.error(f"❌ Error removing job: {e}")