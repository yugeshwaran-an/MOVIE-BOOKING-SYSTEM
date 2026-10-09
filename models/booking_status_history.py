"""
BookingStatusHistory Model for auditing all status lifecycle transitions.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from models.base import Base


class BookingStatusHistory(Base):
    __tablename__ = 'booking_status_histories'

    id = Column(Integer, primary_key=True, autoincrement=True)
    reservation_id = Column(String(50), ForeignKey('reservations.id'), nullable=False)
    actor_id = Column(String(50), nullable=False)  # User or Admin who triggered transition
    old_status = Column(String(20), nullable=True)  # None on creation, or previous status
    new_status = Column(String(20), nullable=False)
    event_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    reservation = relationship('Reservation', back_populates='status_history')

    def __repr__(self):
        return f"<BookingStatusHistory id={self.id} res={self.reservation_id} {self.old_status}->{self.new_status} by={self.actor_id}>"
