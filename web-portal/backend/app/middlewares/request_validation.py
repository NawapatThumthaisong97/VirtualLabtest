"""
Request validation middlewares - FastAPI Dependencies
"""
from fastapi import Request, HTTPException, status
import logging

logger = logging.getLogger(__name__)


async def require_non_empty_body(request: Request) -> None:
    """
    Middleware-like dependency ที่เช็คว่า request body ไม่เป็น empty object {}
    
    ใช้กับ POST/PUT/PATCH endpoints ที่ต้องการ body
    
    Usage:
        @router.post("/", dependencies=[Depends(require_non_empty_body)])
        async def create_item(data: CreateSchema):
            ...
    
    Raises:
        HTTPException 400: ถ้า body เป็น {} หรือ None
    """
    if request.method not in ["POST", "PUT", "PATCH"]:
        return
    
    try:
        body = await request.json()
        
        if body is None or (isinstance(body, dict) and len(body) == 0):
            logger.warning(f"Empty/null body for {request.method} {request.url.path}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request body cannot be empty"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Invalid JSON: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON format"
        )
