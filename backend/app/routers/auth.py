from fastapi import APIRouter

from app.dependencies import CurrentUser, DbDep
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, UserCreate, UserResponse
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=201)
async def signup(body: UserCreate, db: DbDep) -> TokenResponse:
    _user, tokens = await auth_service.signup(db, body)
    return tokens


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: DbDep) -> TokenResponse:
    _user, tokens = await auth_service.login(db, body.email, body.password)
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: DbDep) -> TokenResponse:
    return await auth_service.refresh(db, body.refresh_token)


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)
