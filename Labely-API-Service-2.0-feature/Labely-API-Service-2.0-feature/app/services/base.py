from typing import Generic, List, Optional, Type, TypeVar

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException

ModelType = TypeVar("ModelType")

class BaseService(Generic[ModelType]):
    """Base service with common CRUD operations"""

    def __init__(self, model: Type[ModelType], db: Session):
        self.model = model
        self.db = db

    def get(self, id: int) -> Optional[ModelType]:
        return self.db.query(self.model).filter(self.model.id == id).first()

    def get_or_404(self, id: int) -> ModelType:
        obj = self.get(id)
        if not obj:
            raise NotFoundException(f"{self.model.__name__} not found")
        return obj

    def get_by_user(self, user_id: int, skip: int = 0, limit: int = 100) -> List[ModelType]:
        return self.db.query(self.model).filter(
            self.model.user_id == user_id
        ).offset(skip).limit(limit).all()

    def create(self, **kwargs) -> ModelType:
        obj = self.model(**kwargs)
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, id: int, **kwargs) -> ModelType:
        obj = self.get_or_404(id)
        for key, value in kwargs.items():
            setattr(obj, key, value)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, id: int) -> bool:
        obj = self.get_or_404(id)
        self.db.delete(obj)
        self.db.commit()
        return True
