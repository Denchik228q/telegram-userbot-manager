import logging
from typing import Optional

from database import Database

logger = logging.getLogger(__name__)


class PaymentHandler:
    PLAN_PRICES = {
        'basic': 399.0,
        'pro': 1499.0,
        'ultimate': 4999.0,
        # legacy aliases
        'standard': 490.0,
        'premium': 1990.0,
    }

    def __init__(self, db: Database):
        self.db = db

    def create_payment(self, user_id: int, plan: str, payment_method: str, receipt_photo: Optional[str] = None) -> int:
        if plan not in self.PLAN_PRICES:
            raise ValueError(f'Unsupported plan: {plan}')
        amount = self.PLAN_PRICES[plan]
        return self.db.create_payment(user_id, plan, amount, payment_method, receipt_photo)

    def approve_payment(self, payment_id: int) -> bool:
        payment = self.db.get_payment(payment_id)
        if not payment or payment['status'] != 'pending':
            return False

        self.db.update_payment_status(payment_id, 'confirmed')
        self.db.set_user_plan(payment['user_id'], payment['plan'], days=30)
        logger.info("✅ Payment #%s approved", payment_id)
        return True

    def reject_payment(self, payment_id: int) -> bool:
        payment = self.db.get_payment(payment_id)
        if not payment or payment['status'] != 'pending':
            return False

        self.db.update_payment_status(payment_id, 'rejected')
        logger.info("❌ Payment #%s rejected", payment_id)
        return True
