from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Union, List

class CustomerBase(BaseModel):
    name: str

class CustomerCreate(CustomerBase):
    pass

class Customer(CustomerBase):
    id: int

    class Config:
        orm_mode = True

class OrderBase(BaseModel):
    customer_name: str
    material_id: int
    quantity: float
    order_date: Union[datetime, str]
    price_per_kg: float
    total_price: Optional[float] = None

class OrderCreate(OrderBase):
    pass

class Order(OrderBase):
    id: int
    material_name: str
    created_at: datetime

    class Config:
        orm_mode = True
        
    def dict(self, *args, **kwargs):
        d = super().dict(*args, **kwargs)
        if isinstance(d.get('order_date'), datetime):
            d['order_date'] = d['order_date'].strftime("%Y-%m-%d")
        if isinstance(d.get('created_at'), datetime):
            d['created_at'] = d['created_at'].strftime("%Y-%m-%d %H:%M:%S")
        return d

class BlendComponentBase(BaseModel):
    component_id: int
    ratio: float

class BlendComponentCreate(BlendComponentBase):
    pass

class BlendComponent(BlendComponentBase):
    id: int
    blend_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class MaterialBase(BaseModel):
    name: str
    type: str = Field(default="regular", description="자재 타입 (regular: 일반, blend: 블렌딩 원두, single_origin: 단일 원두)")
    unit: str = 'kg'
    processing_ratio: float = 1.0

class MaterialCreate(MaterialBase):
    pass

class Material(MaterialBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class MaterialPurchaseBase(BaseModel):
    material_id: int
    quantity_kg: float
    price_per_kg: float
    total_price: Optional[float] = None
    purchase_date: Union[datetime, str]  # datetime 또는 문자열 허용
    supplier: Optional[str] = None
    note: Optional[str] = None

class MaterialPurchaseCreate(MaterialPurchaseBase):
    pass

class MaterialPurchase(MaterialPurchaseBase):
    id: int
    material_name: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True

class InventoryBase(BaseModel):
    material_id: int
    quantity: float = 0
    safety_stock: float = 0

class InventoryCreate(InventoryBase):
    pass

class Inventory(InventoryBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class InventoryUpdate(BaseModel):
    quantity: Optional[float] = None
    safety_stock: Optional[float] = None

class SalesAnalytics(BaseModel):
    date: str
    sales: float
    cost: float
    profit: float
    quantity: float

    class Config:
        orm_mode = True
