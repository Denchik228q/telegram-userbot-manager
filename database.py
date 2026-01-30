'schedule_time': row[6],
'is_active': row[7],
'last_run': row[8],
'created_at': row[9]
} for row in rows]
except Exception as e:
logger.error(f"Error getting schedules: {e}")
return []

def get_schedule(self, schedule_id: int) -> Optional[Dict]:
"""Получить расписание по ID"""
try:
cursor = self.conn.cursor()
cursor.execute('SELECT * FROM schedules WHERE id = ?', (schedule_id,))
row = cursor.fetchone()

if not row:
return None

return {
'id': row[0],
'user_id': row[1],
'targets': row[2],
'message': row[3],
'accounts': row[4],
'schedule_type': row[5],
'schedule_time': row[6],
'is_active': row[7],
'last_run': row[8],
'created_at': row[9]
}
except Exception as e:
logger.error(f"Error getting schedule: {e}")
return None

def delete_schedule(self, schedule_id: int) -> bool:
"""Удалить расписание"""
try:
cursor = self.conn.cursor()
cursor.execute('UPDATE schedules SET is_active = 0 WHERE id = ?', (schedule_id,))
self.conn.commit()
logger.info(f"✅ Schedule {schedule_id} deleted")
return True
except Exception as e:
logger.error(f"Error deleting schedule: {e}")
return False

def get_all_active_schedules(self) -> List[Dict]:
"""Получить все активные расписания"""
try:
cursor = self.conn.cursor()
cursor.execute('SELECT * FROM schedules WHERE is_active = 1')
rows = cursor.fetchall()

return [{
'id': row[0],
'user_id': row[1],
'targets': row[2],
'message': row[3],
'accounts': row[4],
'schedule_type': row[5],
'schedule_time': row[6],
'is_active': row[7],
'last_run': row[8],
'created_at': row[9]
} for row in rows]
except Exception as e:
logger.error(f"Error getting active schedules: {e}")
return []

def update_schedule_last_run(self, schedule_id: int) -> bool:
"""Обновить время последнего запуска"""
try:
cursor = self.conn.cursor()
cursor.execute('''
UPDATE schedules SET last_run = ? WHERE id = ?
''', (datetime.now(), schedule_id))

self.conn.commit()
return True
except Exception as e:
logger.error(f"Error updating schedule last_run: {e}")
return False

# ==================== СТАТИСТИКА ====================

def get_stats(self) -> Dict:
"""Получить общую статистику"""
try:
cursor = self.conn.cursor()

# Пользователи
cursor.execute('SELECT COUNT(*) FROM users')
total_users = cursor.fetchone()[0]

# Активные подписки
cursor.execute('''
SELECT COUNT(*) FROM users
WHERE subscription_end > ?
''', (datetime.now(),))
active_subs = cursor.fetchone()[0]

# Аккаунты
cursor.execute('SELECT COUNT(*) FROM accounts WHERE is_active = 1')
total_accounts = cursor.fetchone()[0]

# Рассылки сегодня
today = datetime.now().date()
cursor.execute('''
SELECT COUNT(*) FROM mailings
WHERE DATE(created_at) = ?
''', (today,))
mailings_today = cursor.fetchone()[0]

return {
                'total_users': total_users,
                'active_subscriptions': active_subs,
                'total_accounts': total_accounts,
                'mailings_today': mailings_today
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {
                'total_users': 0,
                'active_subscriptions': 0,
                'total_accounts': 0,
                'mailings_today': 0
            }
    
    def close(self):
        """Закрыть соединение с БД"""
        self.conn.close()
        logger.info("✅ Database connection closed")