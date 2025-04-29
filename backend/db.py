from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum
import enum
import datetime

DATABASE_URL = "sqlite+aiosqlite:///./onefit.db"

engine = create_async_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class UserRole(enum.Enum):
    trainer = "trainer"
    client = "client"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True)
    username = Column(String, index=True)
    full_name = Column(String)
    gender = Column(String, nullable=True)  # М/Ж
    age = Column(Integer, nullable=True)
    weight = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    goal = Column(String, nullable=True)
    role = Column(Enum(UserRole))
    experience = Column(Integer, nullable=True)  # опыт работы (лет) для тренера
    specialization = Column(String, nullable=True)  # специализация для тренера
    contacts = Column(String, nullable=True)  # контакты для тренера
    about = Column(String, nullable=True)  # о себе для тренера
    photo_file_id = Column(String, nullable=True)  # file_id фото
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class TrainerClient(Base):
    __tablename__ = "trainer_clients"
    id = Column(Integer, primary_key=True, index=True)
    trainer_id = Column(Integer, ForeignKey("users.id"))
    client_id = Column(Integer, ForeignKey("users.id"))

class Workout(Base):
    __tablename__ = "workouts"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"))
    trainer_id = Column(Integer, ForeignKey("users.id"))
    date = Column(DateTime, default=datetime.datetime.utcnow)
    exercises = Column(String)  # Можно сделать JSON, но для MVP — строка
    notes = Column(String)

class PendingInvite(Base):
    __tablename__ = "pending_invites"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    trainer_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    remind_at = Column(DateTime, index=True)
    text = Column(String)
    sent = Column(Integer, default=0)

# Функция для создания таблиц
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
