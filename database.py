import os
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy.engine import URL
from sqlmodel import Field, Session, SQLModel, create_engine

load_dotenv()

class Team(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    abstract: str
    guide: str
    members: str
    status: str = "Submitted"

class ProjectFile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    team_id: int = Field(foreign_key="team.id")
    file_type: str                    # "Doc", "PPT" or "Code"
    filename: str
    path: str                         # local path now, S3 key later
    uploaded_at: datetime = Field(default_factory= lambda: datetime.now(timezone.utc))

DATABASE_URL = URL.create(
    "postgresql+psycopg",
    username=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    host=os.environ["DB_HOST"],
    port=int(os.environ["DB_PORT"]),
    database=os.environ["DB_NAME"],
)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"sslmode": "require"},
)

def create_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session