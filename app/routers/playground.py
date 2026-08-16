from fastapi import APIRouter
from pydantic import BaseModel


class UserLocks(BaseModel):
    passphrase: str
    

router = APIRouter()



@router.post("/lock-files")
def locking_files(user: UserLocks):
    return user

@router.post("/show-files")
def show_files(user: UserLocks):
    return user

