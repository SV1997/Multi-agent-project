from fastapi import Header, HTTPException

from .config import INTERNAL_SHARED_SECRET

async def verify_internal_secret(x_internal_secret:str=Header(...)):
    if x_internal_secret!= INTERNAL_SHARED_SECRET:
        raise HTTPException(
            status_code= 403,
            detail="Invalid secret code"
        )
    
