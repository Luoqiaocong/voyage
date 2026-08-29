from typing import Annotated

from pydantic import BaseModel, EmailStr, Field


class VerifyEmailRequest(BaseModel):
    email: Annotated[EmailStr, Field(description="邮箱地址")]