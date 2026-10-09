"""
User Model representing system actors (USER and ADMINISTRATOR).
"""
from sqlalchemy import Column, String
from sqlalchemy.orm import relationship
from models.base import Base


class User(Base):
    __tablename__ = 'users'

    id = Column(String(50), primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False)  # 'USER' or 'ADMINISTRATOR'
    status = Column(String(20), default='ACTIVE')

    reservations = relationship('Reservation', back_populates='user', cascade='all, delete-orphan')

    def is_admin(self) -> bool:
        return self.role == 'ADMINISTRATOR'

    def is_user(self) -> bool:
        return self.role == 'USER'

    def __repr__(self):
        return f"<User id={self.id} username={self.username} role={self.role}>"
