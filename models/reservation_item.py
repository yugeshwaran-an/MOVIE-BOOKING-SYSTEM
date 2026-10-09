"""
ReservationItem Model representing individual line items and fare snapshots in a booking.
"""
from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from models.base import Base


class ReservationItem(Base):
    __tablename__ = 'reservation_items'

    id = Column(Integer, primary_key=True, autoincrement=True)
    reservation_id = Column(String(50), ForeignKey('reservations.id'), nullable=False)
    resource_id = Column(String(50), ForeignKey('resources.id'), nullable=False)
    quantity = Column(Integer, nullable=False)
    rate_snapshot = Column(Float, nullable=False)   # Fare snapshot at booking time (BR3)
    base_amount = Column(Float, nullable=False)     # rate_snapshot * quantity (BR4)
    booking_charge = Column(Float, nullable=False)  # Rs.50 if base_amount < 1000 else Rs.0 (BR4)
    grand_total = Column(Float, nullable=False)     # base_amount + booking_charge (BR4)

    reservation = relationship('Reservation', back_populates='items')
    resource = relationship('Resource', back_populates='reservation_items')

    def __repr__(self):
        return f"<ReservationItem id={self.id} resource={self.resource_id} qty={self.quantity} total={self.grand_total}>"
