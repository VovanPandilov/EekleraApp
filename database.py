"""
Модуль для работы с базой данных
Использует SQLAlchemy для управления задачами и целями
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

# URL базы данных из переменной окружения или SQLite по умолчанию
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tasks.db")

# Создание движка базы данных
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    """Модель пользователя"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Настройки AI агента
    agent_name = Column(String, default="AI Помощник")
    agent_prompt = Column(Text, default="Ты полезный AI помощник, который помогает управлять задачами и целями.")
    
    # Связь с задачами и целями
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.telegram_id}: {self.first_name}>"


class Goal(Base):
    """Модель цели (долгосрочная)"""
    __tablename__ = "goals"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    deadline = Column(DateTime, nullable=True)
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    
    # AI агент для этой цели
    agent_name = Column(String, nullable=True)
    agent_prompt = Column(Text, nullable=True)
    
    # Связь
    user = relationship("User", back_populates="goals")
    tasks = relationship("Task", back_populates="goal", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Goal {self.id}: {self.title}>"


class Task(Base):
    """Модель задачи"""
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    goal_id = Column(Integer, ForeignKey("goals.id"), nullable=True)
    
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    scheduled_date = Column(DateTime, nullable=True)  # Когда запланировано
    deadline = Column(DateTime, nullable=True)  # Крайний срок
    
    # Статус
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    
    # Приоритет: low, medium, high
    priority = Column(String, default="medium")
    
    # AI агент для этой задачи
    agent_name = Column(String, nullable=True)
    agent_notes = Column(Text, nullable=True)  # Заметки от AI
    
    # Связи
    user = relationship("User", back_populates="tasks")
    goal = relationship("Goal", back_populates="tasks")
    
    def __repr__(self):
        return f"<Task {self.id}: {self.title}>"


def init_db():
    """Инициализация базы данных"""
    Base.metadata.create_all(bind=engine)
    print("✅ База данных инициализирована")


def get_db():
    """Получение сессии базы данных"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


if __name__ == "__main__":
    # Создание таблиц при запуске модуля
    init_db()
