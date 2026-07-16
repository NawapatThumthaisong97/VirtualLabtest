"""
Example Controller
จัดการ request/response สำหรับ example
"""
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.services.example_service import ExampleService
from app.schemas.example import ExampleResponse
from app.configs.settings import settings
from typing import List


class ExampleController:
    @staticmethod
    def get_all(db: Session = None) -> List[ExampleResponse]:
        """Get all examples"""
        try:
            use_mock = settings.DEBUG  # ใช้ mock ตอน DEBUG=True
            examples = ExampleService.get_all_examples(db, use_mock=use_mock)
            return examples
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @staticmethod
    def get_by_id(db: Session = None, example_id: int = None) -> ExampleResponse:
        """Get example by ID"""
        try:
            use_mock = settings.DEBUG  # ใช้ mock ตอน DEBUG=True
            example = ExampleService.get_example_by_id(db, example_id, use_mock=use_mock)
            if not example:
                raise HTTPException(status_code=404, detail="Example not found")
            return example
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
