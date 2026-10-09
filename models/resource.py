"""
Resource Model representing movie shows and bookable seat categories.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, DateTime
from sqlalchemy.orm import relationship
from models.base import Base


class Resource(Base):
    __tablename__ = 'resources'

    id = Column(String(50), primary_key=True)  # e.g., 'R101'
    name = Column(String(100), nullable=False)  # e.g., 'Show Seat A'
    rate = Column(Float, nullable=False)
    availability = Column(Integer, nullable=False, default=0)
    status = Column(String(20), default='ACTIVE')  # 'ACTIVE' or 'INACTIVE'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    schedules = relationship('Schedule', back_populates='resource', cascade='all, delete-orphan')
    reservation_items = relationship('ReservationItem', back_populates='resource')

    def is_active(self) -> bool:
        return self.status == 'ACTIVE'

    def has_availability(self, qty: int) -> bool:
        return self.is_active() and self.availability >= qty

    def __repr__(self):
        return f"<Resource id={self.id} name={self.name} rate={self.rate} availability={self.availability}>"
