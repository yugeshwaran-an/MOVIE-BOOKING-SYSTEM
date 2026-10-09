"""
AvailabilityService providing business logic for quantity validation,
show availability checking, capacity reduction, and capacity restoration.
"""
from typing import Tuple, Optional
from sqlalchemy.orm import Session
from models.resource import Resource


class AvailabilityService:
    """Service handling seat availability checks and capacity management."""

    @staticmethod
    def validate_quantity(raw_quantity) -> Tuple[bool, Optional[int], str]:
        """
        Validate booking quantity according to BR1:
        - Only integer values 1, 2, 3, 4, 5 are allowed.
        - Rejects <= 0, > 5, decimals, negatives, non-numerics.
        """
        if raw_quantity is None:
            return False, None, "Quantity must be between 1 and 5."

        # Handle string input
        if isinstance(raw_quantity, str):
            raw_quantity = raw_quantity.strip()
            # If contains decimal point or non-digits, reject
            if not raw_quantity.isdigit():
                return False, None, "Quantity must be between 1 and 5."
            try:
                qty = int(raw_quantity)
            except ValueError:
                return False, None, "Quantity must be between 1 and 5."
        elif isinstance(raw_quantity, int) and not isinstance(raw_quantity, bool):
            qty = raw_quantity
        elif isinstance(raw_quantity, float):
            # Explicitly reject float/decimal numbers (e.g., 1.5, 2.0)
            return False, None, "Quantity must be between 1 and 5."
        else:
            return False, None, "Quantity must be between 1 and 5."

        if qty < 1 or qty > 5:
            return False, None, "Quantity must be between 1 and 5."

        return True, qty, ""

    @staticmethod
    def check_availability(session: Session, resource_id: str, quantity: int) -> Tuple[bool, str]:
        """
        BR2 - Check if resource is active and has sufficient seats.
        """
        resource = session.query(Resource).filter_by(id=resource_id).first()
        if not resource:
            return False, "This show is currently unavailable."

        if not resource.is_active():
            return False, "This show is currently unavailable."

        if resource.availability <= 0:
            return False, "This show is currently unavailable."

        if resource.availability < quantity:
            return False, "Requested quantity is not available."

        return True, "Show is available."

    @staticmethod
    def reduce_availability(session: Session, resource_id: str, quantity: int) -> bool:
        """
        BR2, BR7 - Reduce resource availability atomically.
        """
        resource = session.query(Resource).filter_by(id=resource_id).with_for_update().first() if session.bind.dialect.name != 'sqlite' else session.query(Resource).filter_by(id=resource_id).first()
        if not resource or not resource.is_active() or resource.availability < quantity:
            return False

        resource.availability -= quantity
        return True

    @staticmethod
    def restore_availability(session: Session, resource_id: str, quantity: int) -> bool:
        """
        BR9 - Restore resource availability exactly once upon cancellation.
        """
        resource = session.query(Resource).filter_by(id=resource_id).first()
        if not resource:
            return False

        resource.availability += quantity
        return True

    @staticmethod
    def calculate_pricing(rate: float, quantity: int) -> Tuple[float, float, float]:
        """
        BR4 - FARE & TOTAL calculation:
        base_total = rate * quantity
        IF base_total < 1000: booking_charge = 50
        IF base_total >= 1000: booking_charge = 0
        grand_total = base_total + booking_charge
        """
        base_total = round(float(rate) * quantity, 2)
        if base_total < 1000.0:
            booking_charge = 50.0
        else:
            booking_charge = 0.0
        grand_total = round(base_total + booking_charge, 2)
        return base_total, booking_charge, grand_total
