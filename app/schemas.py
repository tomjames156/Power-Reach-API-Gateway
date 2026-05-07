from pydantic import BaseModel
from uuid import UUID
from typing import Optional, Any, List
from datetime import datetime

import enum

class UserType(str, enum.Enum):
    admin    = "admin"
    customer = "customer"
    service_agent = "service_agent"
    engineer = "engineer"

class UserOut(BaseModel):
    id: UUID
    email: str
    user_type: UserType
    is_active: bool
    is_verified: bool

    class Config:
        from_attributes = True

class CustomerProfileOut(BaseModel):
    display_id: str
    full_name: str
    phone_number: str
    meter_number: Optional[str] = None
    address: Optional[str] = None
    location: Optional[str] = None
    profile_picture_url: Optional[str] = None
    last_updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class CustomerOut(UserOut):
    profile: Optional[CustomerProfileOut] = None

