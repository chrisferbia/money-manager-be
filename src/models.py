from typing import Optional

from pydantic import BaseModel, Field


class AccountCreate(BaseModel):
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)


class AccountUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    type: Optional[str] = Field(default=None, min_length=1)


class Account(BaseModel):
    id: int
    name: str
    type: str
    created_at: str
