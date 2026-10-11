from datetime import datetime, timezone

from sqlmodel import Field, Session, SQLModel, create_engine


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

engine = create_engine("sqlite:///repo.db", echo=False)

def create_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session