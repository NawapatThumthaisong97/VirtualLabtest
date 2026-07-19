"""
Example Service
Business logic สำหรับ example
"""
from sqlalchemy.orm import Session
from datetime import datetime


# Mock data สำหรับ testing ตอนยังไม่ migrate DB
MOCK_EXAMPLES = [
    {
        "id": 1,
        "title": "Example 1",
        "description": "First example",
        "is_active": True,
        "created_at": datetime.now().isoformat(),
        "updated_at": None,
    },
    {
        "id": 2,
        "title": "Example 2",
        "description": "Second example",
        "is_active": True,
        "created_at": datetime.now().isoformat(),
        "updated_at": None,
    },
]


class ExampleService:
    @staticmethod
    def get_all_examples(db: Session = None, use_mock: bool = False):
        """ดึงทั้งหมด example"""
        if use_mock:
            return MOCK_EXAMPLES
        
        if db is None:
            raise ValueError("Database connection is not available")
        # TODO: implement database query when Example model is available
        return []
    
    @staticmethod
    def get_example_by_id(db: Session = None, example_id: int = None, use_mock: bool = False):
        """ดึง example ตาม ID"""
        if use_mock:
            return next((ex for ex in MOCK_EXAMPLES if ex["id"] == example_id), None)
        
        if example_id < 1:
            raise ValueError("ID must be a positive number")
        if db is None:
            raise ValueError("Database connection is not available")
        # TODO: implement database query when Example model is available
        return None
