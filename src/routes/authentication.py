import logging
from datetime import datetime, timedelta, timezone

from fastapi import (APIRouter, Depends, HTTPException, Request, WebSocket,
                     status)
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from src.authentication import active_directory
from src.authentication.roles_type import RoleType, parse_role
from src.authentication.schemas_authentication import (SYSTEM_ADMIN,
                                                       CurrentUser, Token)
from src.database.database_access import get_db_session
from src.database.models.user_entity import UserEntity
from src.database.repositories.user_repository import UserRepository
from src.utils import config
from src.utils.hasher import get_password_hash

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/authentication", tags=["Authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authentication/token", auto_error=False)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
TOKEN_COOKIE_NAME = "lotse_token"

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def create_access_token(user: UserEntity | CurrentUser) -> Token:
    if isinstance(user, UserEntity):
        data = {"sub": user.name, "uid": user.id, "role": parse_role(user.role).value}  # type: ignore
    else:
        data = {"sub": user.username, "uid": user.id, "role": user.role.value}

    data["exp"] = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    encoded_jwt = jwt.encode(data, config.JWT_SECRET_KEY, algorithm=ALGORITHM)
    return Token(access_token=encoded_jwt, token_type="bearer")


def _resolve_user(db: Session, token: str | None) -> CurrentUser:
    if not config.ENABLE_AUTH:
        return SYSTEM_ADMIN

    if not token:
        raise CREDENTIALS_EXCEPTION

    try:
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise CREDENTIALS_EXCEPTION

    user_id = payload.get("uid")
    user = UserRepository.get_user_by_id(db, user_id) if user_id else None
    if user is None:
        raise CREDENTIALS_EXCEPTION

    return CurrentUser(
        id=user.id,  # type: ignore
        username=user.name,  # type: ignore
        role=parse_role(user.role),  # type: ignore
        display_name=user.display_name,  # type: ignore
    )


def extract_token(request: Request | WebSocket, bearer_token: str | None = None) -> str | None:
    if not bearer_token:
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            bearer_token = authorization[7:].strip()

    return bearer_token or request.cookies.get(TOKEN_COOKIE_NAME) or request.query_params.get("token")


async def get_current_user(
        request: Request,
        bearer_token: str | None = Depends(oauth2_scheme),
        db: Session = Depends(get_db_session)) -> CurrentUser:
    return _resolve_user(db, extract_token(request, bearer_token))


def authenticate_connection(connection: Request | WebSocket) -> CurrentUser | None:
    db = next(get_db_session())
    try:
        return _resolve_user(db, extract_token(connection))
    except HTTPException:
        return None
    finally:
        db.close()


async def require_user(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return user


async def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin role required for this operation")
    return user


def _get_or_create_ldap_user(db: Session, ldap_user: active_directory.LdapUser) -> UserEntity | None:
    user = UserRepository.get_user_by_name(db, ldap_user.user_name)
    if user is None:
        logger.info("Creating lotse user for active directory user %s", ldap_user.user_name)
        return UserRepository.create_user(
            db,
            name=ldap_user.user_name,
            hashed_password="",
            role=RoleType.USER,
            is_ldap=True,
            display_name=ldap_user.display_name,
            email=ldap_user.email,
        )

    if not user.is_ldap:
        # Never let a directory account take over a local account with the same name (e.g. "admin").
        logger.warning("Active directory user %s collides with a local user, rejecting AD login", ldap_user.user_name)
        return None

    return UserRepository.update_user(
        db, user.id,  # type: ignore
        display_name=ldap_user.display_name,
        email=ldap_user.email,
    )


async def _authenticate(db: Session, user_name: str, password: str) -> UserEntity | None:
    if active_directory.is_configured():
        ldap_user = await run_in_threadpool(active_directory.login, user_name, password)
        if ldap_user is not None:
            user = _get_or_create_ldap_user(db, ldap_user)
            if user is not None:
                return user

    return UserRepository.login_user(db, user_name.strip(), password)


@router.post("/token", response_model=Token)
async def login_for_access_token(
        db: Session = Depends(get_db_session),
        form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
    if not config.ENABLE_AUTH:
        return create_access_token(SYSTEM_ADMIN)

    user = await _authenticate(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return create_access_token(user)


@router.post("/token/ldap", response_model=Token)
async def login_for_access_token_via_ldap(
        db: Session = Depends(get_db_session),
        form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
    return await login_for_access_token(db, form_data)


@router.post("/token/refresh", response_model=Token)
async def refresh_token(user: CurrentUser = Depends(get_current_user)) -> Token:
    return create_access_token(user)


@router.post("/register")
async def register_user(
        db: Session = Depends(get_db_session),
        form_data: OAuth2PasswordRequestForm = Depends(),
        _: CurrentUser = Depends(require_admin)):
    if UserRepository.get_user_by_name(db, form_data.username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")

    user = UserRepository.create_user(db, form_data.username, get_password_hash(form_data.password), RoleType.USER)
    return {"username": user.name, "role": user.role}


@router.get("/users/me/", response_model=CurrentUser)
async def read_users_me(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return current_user
