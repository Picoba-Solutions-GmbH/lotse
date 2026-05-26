from fastapi import APIRouter

from src.utils import config

router = APIRouter(prefix="/feature-flags", tags=["Feature Flags"])


@router.get("")
async def get_feature_flags():
    return {"authentication_enabled": config.ENABLE_AUTH, "live_coding_enabled": config.LIVE_CODING_ENABLED}
