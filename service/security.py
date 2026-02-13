from fastapi import Header, HTTPException
# from service.config import settings  ← remove this

from service.config import Settings  # import class only

def verify_secret(x_orty_secret: str = Header(...)):
    settings = Settings()  # instantiate here
    if not settings.ORTY_SHARED_SECRET:
        raise RuntimeError("ORTY_SHARED_SECRET not set")
    if x_orty_secret != settings.ORTY_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return x_orty_secret

