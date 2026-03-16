import logging
from database import Database

logger = logging.getLogger(__name__)


class ShopManager:
    def __init__(self, db: Database):
        self.db = db

    def add_product(self, name: str, description: str, price: float, stock: int, file_id: str) -> int:
        return self.db.add_product(name, description, price, stock, file_id)

    def get_products(self):
        return self.db.get_active_products()

    def process_purchase(self, user_id: int, product_id: int, quantity: int, payment_method: str, receipt_photo: str = None) -> int:
        product = self.db.get_product(product_id)
        if not product:
            raise ValueError('Product not found')
        if not product['is_active']:
            raise ValueError('Product is inactive')
        if quantity <= 0:
            raise ValueError('Quantity must be positive')
        if product['stock'] < quantity:
            raise ValueError('Not enough stock')

        total_price = float(product['price']) * quantity
        purchase_id = self.db.create_purchase(
            user_id=user_id,
            product_id=product_id,
            quantity=quantity,
            total_price=total_price,
            payment_method=payment_method,
            receipt_photo=receipt_photo,
        )
        return purchase_id

    def complete_purchase(self, purchase_id: int, product_id: int, quantity: int):
        self.db.complete_purchase(purchase_id)
        self.db.update_product_stock(product_id, -abs(quantity))
        logger.info("✅ Purchase #%s completed", purchase_id)
