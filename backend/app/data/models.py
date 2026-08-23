from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from backend.app.data.database import Base

# Stubs for Database Models. Will be updated/extended during Phase 2 to map to actual Excel sheets.

class Account(Base):
    __tablename__ = "accounts"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    # Customer specific fields, SLA structures, tier, etc., will be added after inspecting Excel.

    orders = relationship("Order", back_populates="account")
    tickets = relationship("Ticket", back_populates="account")


class Order(Base):
    __tablename__ = "orders"
    
    id = Column(String, primary_key=True, index=True)
    account_id = Column(String, ForeignKey("accounts.id"), nullable=False)
    # Order items, status, ship dates, carrier, delivery times, etc., will be added after inspecting Excel.

    account = relationship("Account", back_populates="orders")
    tickets = relationship("Ticket", back_populates="order")


class Ticket(Base):
    __tablename__ = "tickets"
    
    id = Column(String, primary_key=True, index=True)
    account_id = Column(String, ForeignKey("accounts.id"), nullable=False)
    order_id = Column(String, ForeignKey("orders.id"), nullable=True)
    # Title, issue details, status, severity, created at, SLA deadline, agent notes, etc., will be added after inspecting Excel.

    account = relationship("Account", back_populates="tickets")
    order = relationship("Order", back_populates="tickets")
