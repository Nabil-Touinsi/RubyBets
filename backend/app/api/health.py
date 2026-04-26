from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/")
def read_root():
    return {"message": "RubyBets API is running"}


@router.get("/health")
def health_check():
    return {"status": "ok"}