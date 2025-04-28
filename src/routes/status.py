from fastapi import APIRouter

router = APIRouter(tags=["Status"])


@router.get("/health", include_in_schema=False)
def health_check():
    return {"status": "UP"}


@router.get("/liveness", include_in_schema=False)
def liveness_check():
    return {"status": "UP"}
