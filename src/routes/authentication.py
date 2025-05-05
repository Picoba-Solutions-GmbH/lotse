from datetime import datetime, timedelta
from typing import Union

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from src.authentication import active_directory
from src.authentication import schemas_authentication as schemas
from src.authentication.roles_type import RoleType
from src.database.database_access import get_db_session
from src.services.user_repository import UserRepository
from src.utils import config
from src.utils.hasher import get_password_hash, verify_password

router = APIRouter(prefix="/authentication", tags=["Authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def override_validate_authorization():
    return True


def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        return schemas.UserInDB(**user_dict)

    return None


def authenticate_user(fake_db, username: str, password: str):
    user = get_user(fake_db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_access_token(data: dict, expires_delta: Union[timedelta, None] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def validate_token_async(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")

        raw_role = payload.get("role", RoleType.UNAOTHORIZED)
        role = RoleType(raw_role)
        if username is None:
            raise CREDENTIALS_EXCEPTION

        token_data = schemas.TokenData(username=username, role=role)
    except JWTError:
        raise CREDENTIALS_EXCEPTION
    return token_data


async def get_current_user_async(token_data: schemas.TokenData = Depends(validate_token_async)):
    return schemas.User(**vars(token_data))


async def get_current_active_user_async(current_user: schemas.User = Depends(get_current_user_async)):
    return current_user


async def generate_token_async(user_name: str, role: RoleType):
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_name, "role": role.value}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


async def require_admin(_: Request, token: str = Depends(oauth2_scheme)):
    if not config.ENABLE_AUTH:
        return await generate_token_async("admin", RoleType.ADMIN)

    token_data = await validate_token_async(token)
    if not token_data.role:
        raise HTTPException(
            status_code=403,
            detail="Admin role required for this operation"
        )

    if RoleType.ADMIN not in token_data.role:
        raise HTTPException(
            status_code=403,
            detail="Admin role required for this operation"
        )
    return token_data


async def require_operator_or_admin(_: Request, token: str = Depends(oauth2_scheme)):
    if not config.ENABLE_AUTH:
        return await generate_token_async("admin", RoleType.ADMIN)

    token_data = await validate_token_async(token)
    if not token_data.role:
        raise HTTPException(
            status_code=403,
            detail="Operator or Admin role required for this operation"
        )

    if not (RoleType.ADMIN in token_data.role or RoleType.OPERATOR in token_data.role):
        raise HTTPException(
            status_code=403,
            detail="Operator or Admin role required for this operation"
        )
    return token_data


@router.get("/is-authentication-enabled")
async def is_authentication_enabled():
    return {"authentication_enabled": config.ENABLE_AUTH}


@router.post("/register", response_model=schemas.Token)
async def register_user(
        db: Session = Depends(get_db_session),
        form_data: OAuth2PasswordRequestForm = Depends()):
    user = UserRepository.get_user_by_name(db, form_data.username)
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    hashed_password = get_password_hash(form_data.password)
    user = UserRepository.create_user(db, form_data.username, hashed_password, RoleType.UNAOTHORIZED)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User could not be created",
        )

    return {"username": user.name, "role": user.role}


@router.post("/token", response_model=schemas.Token)
async def login_for_access_token(
        db: Session = Depends(get_db_session),
        form_data: OAuth2PasswordRequestForm = Depends()):
    if not config.ENABLE_AUTH:
        return await generate_token_async(form_data.username, RoleType.ADMIN)

    user = UserRepository.login_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role = RoleType(user.role) if user.role else RoleType.UNAOTHORIZED
    return await generate_token_async(form_data.username, role)


@router.post("/token/ldap", response_model=schemas.Token)
async def login_for_access_token_via_ldap(
        db: Session = Depends(get_db_session),
        form_data: OAuth2PasswordRequestForm = Depends()):
    if not config.ENABLE_AUTH:
        return await generate_token_async(form_data.username, RoleType.ADMIN)

    login_success = active_directory.login(form_data.username, form_data.password)
    if not login_success:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = UserRepository.get_user(db, form_data.username)
    if not user:
        user = UserRepository.create_user(db, form_data.username, "", RoleType.UNAOTHORIZED, True)

    role = RoleType(user.role) if user.role else RoleType.UNAOTHORIZED
    return await generate_token_async(form_data.username, role)


@router.post("/token/refresh", response_model=schemas.Token)
async def refresh_token(user: schemas.User = Depends(get_current_active_user_async)):
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me/", response_model=schemas.User)
async def read_users_me(current_user: schemas.User = Depends(get_current_active_user_async)):
    return current_user
