from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


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


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1)
    type: Literal["income", "expense"] = "expense"


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)


class Category(BaseModel):
    id: int
    name: str
    type: Literal["income", "expense"] = "expense"
    created_at: str


class TransactionCreate(BaseModel):
    type: Literal["income", "expense", "transfer"]
    account_id: int
    related_account_id: Optional[int] = None
    category_id: Optional[int] = None
    amount: int = Field(gt=0)
    counterparty: Optional[str] = None
    description: Optional[str] = None
    occurred_at: Optional[str] = None


class TransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Optional[int] = Field(default=None, gt=0)
    category_id: Optional[int] = None
    counterparty: Optional[str] = None
    description: Optional[str] = None
    occurred_at: Optional[str] = None


class Transaction(BaseModel):
    id: int
    type: str
    account_id: int
    category_id: Optional[int] = None
    related_account_id: Optional[int] = None
    amount: int
    counterparty: Optional[str] = None
    description: Optional[str] = None
    occurred_at: str
    created_at: str
    transaction_subtype: Optional[str] = None
