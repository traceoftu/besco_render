from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    email = Column(String(100), unique=True, index=True)
    hashed_password = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    orders = relationship("Order", back_populates="customer", cascade="all, delete-orphan")

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String(100), ForeignKey("customers.name", ondelete="CASCADE"), index=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="SET NULL"), nullable=True)
    material_name = Column(String(100))  # 주문 시점의 자재 이름 저장
    order_date = Column(DateTime, index=True)
    created_at = Column(DateTime, server_default=func.now())
    quantity = Column(Float)
    price_per_kg = Column(Float, nullable=True)
    total_price = Column(Float, nullable=True)
    
    customer = relationship("Customer", back_populates="orders")
    material = relationship("Material")

class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    type = Column(String(20), default="regular")  # 'regular', 'blend', 'single_origin'
    unit = Column(String(10), default='kg')
    processing_ratio = Column(Float, default=1.0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    inventory = relationship("Inventory", back_populates="material", uselist=False)
    purchases = relationship("MaterialPurchase", back_populates="material")

class MaterialPurchase(Base):
    __tablename__ = "material_purchases"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), index=True)
    material_name = Column(String(100))  # 구매 시점의 자재 이름 저장
    quantity_kg = Column(Float)
    price_per_kg = Column(Float)
    total_price = Column(Float)
    purchase_date = Column(DateTime, index=True)
    supplier = Column(String(100), nullable=True)
    note = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    
    material = relationship("Material", back_populates="purchases")

class BlendComponent(Base):
    __tablename__ = "blend_components"

    id = Column(Integer, primary_key=True, index=True)
    blend_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), index=True)
    component_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), index=True)
    ratio = Column(Float)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    blend = relationship("Material", foreign_keys=[blend_id])
    component = relationship("Material", foreign_keys=[component_id])

class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), unique=True, index=True)
    quantity = Column(Float, default=0)
    safety_stock = Column(Float, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    material = relationship("Material", back_populates="inventory")
