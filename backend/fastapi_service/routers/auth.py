from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import User, RoleEnum
from backend.security import create_access_token
from backend.fastapi_service.dependencies import get_current_user
from backend.fastapi_service.schemas.auth import Token, LoginRequest, UserProfileResponse
from backend.services import audit_service

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/token", response_model=Token)
def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """OAuth2 standard token endpoint used by Swagger UI and API clients."""
    client_ip = request.client.host if request.client else None
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not user.check_password(form_data.password):
        # Log failed attempt without recording password
        audit_service.log_login(
            db=db,
            user_id=user.id if user else None,
            ip_address=client_ip,
            success=False,
            metadata={"email": form_data.username, "channel": "oauth2_token"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user account")

    # Log successful login
    audit_service.log_login(
        db=db,
        user_id=user.id,
        ip_address=client_ip,
        success=True,
        metadata={"email": user.email, "role": user.role.value if hasattr(user.role, "value") else str(user.role), "channel": "oauth2_token"}
    )

    token_data = {"sub": str(user.id), "role": user.role.value, "email": user.email}
    access_token = create_access_token(token_data)

    return Token(
        access_token=access_token,
        token_type="bearer",
        role=user.role.value,
        user_id=user.id,
        full_name=user.full_name
    )

@router.post("/login", response_model=Token)
def login_json(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """JSON login endpoint for web and REST clients."""
    client_ip = request.client.host if request.client else None
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.check_password(payload.password):
        audit_service.log_login(
            db=db,
            user_id=user.id if user else None,
            ip_address=client_ip,
            success=False,
            metadata={"email": payload.email, "channel": "json_login"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user account")

    audit_service.log_login(
        db=db,
        user_id=user.id,
        ip_address=client_ip,
        success=True,
        metadata={"email": user.email, "role": user.role.value if hasattr(user.role, "value") else str(user.role), "channel": "json_login"}
    )

    token_data = {"sub": str(user.id), "role": user.role.value, "email": user.email}
    access_token = create_access_token(token_data)

    return Token(
        access_token=access_token,
        token_type="bearer",
        role=user.role.value,
        user_id=user.id,
        full_name=user.full_name
    )

@router.post("/logout")
def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Logs out authenticated caller and creates an audit trail entry."""
    client_ip = request.client.host if request.client else None
    audit_service.log_logout(
        db=db,
        user_id=current_user.id,
        ip_address=client_ip,
        metadata={"email": current_user.email, "status": "Logged out securely via API"}
    )
    return {"message": "Logged out successfully", "user_id": current_user.id}

@router.get("/me", response_model=UserProfileResponse)
def read_current_user_profile(current_user: User = Depends(get_current_user)):
    """Returns the authenticated profile of the caller."""
    return current_user
