from fastapi import Depends, APIRouter, HTTPException, status, Form as FastAPIForm
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from app.services.auth_service import AccessTokenService, RefreshTokenService
from app.dependencies.auth import get_refresh_token_service, get_access_token_service, get_user_pass_phrase
from app.dependencies.cryptography import get_encrypt_file_service
from services.cryptography_service import EncryptFileService

router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)

class Form(BaseModel):
    passphrase: str


@router.post("/init-session")
def initialize_session(
        user_form: Form,
        user_id: str = Depends(get_user_pass_phrase),
        acc_tkn_serv: AccessTokenService = Depends(get_access_token_service),
        rfs_tkn_serv: RefreshTokenService = Depends(get_refresh_token_service)
):
    if user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")

    if rfs_tkn_serv.get_token():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")

    try:
        acc_tkn_serv.create_token(subject=user_form.passphrase)
        rfs_tkn_serv.create_token(subject=user_form.passphrase)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad request")

@router.post("/init-session-v1")
def initialize_session_v1(
        passphrase: str = FastAPIForm(...),
        user_id: str = Depends(get_user_pass_phrase),
        acc_tkn_serv: AccessTokenService = Depends(get_access_token_service),
        rfs_tkn_serv: RefreshTokenService = Depends(get_refresh_token_service),
        encrypt_file_serv: EncryptFileService = Depends(get_encrypt_file_service)
):
    if user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")


    if rfs_tkn_serv.get_token():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")


    try:
        initial_check = encrypt_file_serv.check_my_files(passphrase)
        if not initial_check:


        _locked_my_files = encrypt_file_serv.lock_my_files(passphrase=passphrase)
        if not _locked_my_files:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User already exists")

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User already exists")



    try:
        acc_tkn_serv.create_token(subject=passphrase)
        rfs_tkn_serv.create_token(subject=passphrase)
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad request")


@router.delete("/delete-vaults")
def delete_vaults_for_testing(
        user_id: str = Depends(get_user_pass_phrase),
):
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    file_status = {}
    from app.services.cryptography_service import lock_res
    if lock_res.validation_file.exists():
        lock_res.validation_file.unlink()
        file_status["canary_vault"] = "unlinked!"

    if lock_res.output_file.exists():
        lock_res.output_file.unlink()
        file_status["master_vault"] = "unlinked!"

    if not file_status:
        file_status["status"] = "Nothing"

    return file_status

@router.delete("clear-web-cookies", status_code=status.HTTP_204_NO_CONTENT)
def logout_user(
        acc_tkn_serv: AccessTokenService = Depends(get_access_token_service),
        rfs_tkn_serv: RefreshTokenService = Depends(get_refresh_token_service)
):
    acc_tkn_serv.cache.clear()
    rfs_tkn_serv.cache.clear()



@router.get("/me")
def get_me(
        user_id: str=Depends(get_user_pass_phrase),
):
    if user_id:
        return {"user_id": user_id}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)







