"""
Reservation Model representing user bookings and lifecycle status.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from models.base import Base


class Reservation(Base):
    __tablename__ = 'reservations'

    id = Column(String(50), primary_key=True)  # e.g., 'RES-1001'
    user_id = Column(String(50), ForeignKey('users.id'), nullable=False)
    status = Column(String(20), nullable=False, default='CONFIRMED')
    total_amount = Column(Float, nullable=False)
    customer_name = Column(String(100), nullable=False)
    customer_phone = Column(String(20), nullable=False)
    booking_date = Column(String(20), nullable=False)
    reference_info = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship('User', back_populates='reservations')
    items = relationship('ReservationItem', back_populates='reservation', cascade='all, delete-orphan')
    status_history = relationship('BookingStatusHistory', back_populates='reservation', cascade='all, delete-orphan', order_by='BookingStatusHistory.id.asc()')

    def is_eligible_for_cancellation(self) -> bool:
        """Only CONFIRMED bookings can be cancelled by the owner (BR9)."""
        return self.status == 'CONFIRMED'

    def get_valid_next_statuses(self) -> list:
        """
        BR8 - Normal sequence:
        CONFIRMED -> CHECKED_IN
        CHECKED_IN -> COMPLETED
        CONFIRMED -> CANCELLED
        """
        if self.status == 'CONFIRMED':
            return ['CHECKED_IN', 'CANCELLED']
        elif self.status == 'CHECKED_IN':
            return ['COMPLETED']
        return []

    def __repr__(self):
        return f"<Reservation id={self.id} user_id={self.user_id} status={self.status} total={self.total_amount}>"
