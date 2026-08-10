from fastapi import APIRouter
from pydantic import BaseModel, Field


class UserLocks(BaseModel):
    passphrase: str = Field(default="test123")
    

router = APIRouter()



@router.post("/lock-files")
def locking_files(user: UserLocks):
    return user

@router.post("/show-files")
def show_files(user: UserLocks):
    return user

