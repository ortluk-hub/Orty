from fastapi import Header, HTTPException
from service.config import settings

async def verify_secret(x_orty_secret: str = Header(...)):
    if x_orty_secret != settings.ORTY_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

