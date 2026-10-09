"""
Schedule Model representing movie show date, time, and category.
"""
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from models.base import Base


class Schedule(Base):
    __tablename__ = 'schedules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    resource_id = Column(String(50), ForeignKey('resources.id'), nullable=False)
    date = Column(String(20), nullable=False)       # e.g., '2026-10-10'
    time = Column(String(20), nullable=False)       # e.g., '06:30 PM'
    category = Column(String(100), nullable=False)  # e.g., 'Evening Show - Screen 1'

    resource = relationship('Resource', back_populates='schedules')

    def __repr__(self):
        return f"<Schedule id={self.id} resource_id={self.resource_id} date={self.date} time={self.time}>"
