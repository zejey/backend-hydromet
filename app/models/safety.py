from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

# ================== SAFETY CATEGORIES ==================

class SafetyCategoryBase(BaseModel):
    name: str
    description:  Optional[str] = None
    icon: Optional[str] = 'info'
    gradient_colors: Optional[List[str]] = ['#4CAF50', '#81C784']
    order_num: Optional[int] = 0
    is_active: Optional[bool] = True

class CategoryCreate(SafetyCategoryBase):
    pass

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description:  Optional[str] = None
    icon: Optional[str] = None
    gradient_colors: Optional[List[str]] = None
    order_num: Optional[int] = None
    is_active:  Optional[bool] = None

class SafetyCategory(SafetyCategoryBase):
    id: int  # ✅ Changed from VARCHAR to INTEGER
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ================== SAFETY TIP DETAILS ==================

class SafetyTipDetail(BaseModel):
    id: int  # ✅ INTEGER
    tip_id: int  # ✅ INTEGER
    description: str
    order_num: int
    created_at: datetime

    class Config:
        from_attributes = True


# ================== SAFETY TIPS ==================

class SafetyTipBase(BaseModel):
    category_id: int  # ✅ Changed to INTEGER
    range_label: Optional[str] = None
    level: str
    color: Optional[str] = '#4CAF50'
    order_num: Optional[int] = 0
    is_active: Optional[bool] = True

class TipCreate(SafetyTipBase):
    pass

class TipUpdate(BaseModel):
    category_id: Optional[int] = None
    range_label:  Optional[str] = None
    level: Optional[str] = None
    color: Optional[str] = None
    order_num:  Optional[int] = None
    is_active: Optional[bool] = None

class SafetyTip(SafetyTipBase):
    id: int  # ✅ INTEGER
    created_at: datetime
    updated_at: datetime

    class Config: 
        from_attributes = True

class SafetyTipWithDetails(SafetyTip):
    details: List[SafetyTipDetail] = []  # ✅ Include bullet points


# ================== PREVENTIVE MEASURES ==================

class PreventiveMeasureBase(BaseModel):
    category_id: int  # ✅ INTEGER
    title: str
    description: str
    order_num: Optional[int] = 0
    is_active: Optional[bool] = True

class MeasureCreate(PreventiveMeasureBase):
    pass

class MeasureUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    order_num: Optional[int] = None

class PreventiveMeasure(PreventiveMeasureBase):
    id: int  # ✅ INTEGER
    number: str
    created_at: datetime
    updated_at: datetime

    class Config: 
        from_attributes = True