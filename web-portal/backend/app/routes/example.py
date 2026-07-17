"""
Example Routes
API endpoints สำหรับ example
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.configs.db import get_db
from app.controllers.example_controller import ExampleController
from app.schemas.example import ExampleResponse
from app.schemas.response import ApiResponse
from app.configs.settings import settings
from typing import List, Optional

router = APIRouter()


@router.get("", response_model=ApiResponse[List[ExampleResponse]])
def get_examples(db: Optional[Session] = Depends(get_db)):
    """Get all examples"""
    if settings.DEBUG:
        db = None
    examples = ExampleController.get_all(db)
    return {
        "success": True,
        "message": "Examples retrieved successfully",
        "data": examples,
    }


@router.get("/{example_id}", response_model=ApiResponse[ExampleResponse])
def get_example(example_id: int, db: Optional[Session] = Depends(get_db)):
    """Get example by ID"""
    if settings.DEBUG:
        db = None
    example = ExampleController.get_by_id(db, example_id)
    return {
        "success": True,
        "message": f"Example {example_id} retrieved successfully",
        "data": example,
    }
