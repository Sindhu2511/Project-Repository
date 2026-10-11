import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal, get_args
from urllib.parse import quote

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, SQLModel, col, select

from database import ProjectFile, Team, create_tables, get_session

load_dotenv()
AWS_REGION = os.environ["AWS_REGION"]
S3_BUCKET = os.environ["S3_BUCKET"]
s3 = boto3.client(
    "s3",
    region_name=AWS_REGION,
    endpoint_url=f"https://s3.{AWS_REGION}.amazonaws.com",
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield

templates = Jinja2Templates(directory="templates")

IST = timezone(timedelta(hours=5, minutes=30))

def to_ist(dt: datetime) -> str:
    if dt.tzinfo is None:              # SQLite drops the timezone tag; we stored UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).strftime("%d %b %Y, %I:%M %p")

templates.env.filters["ist"] = to_ist

app = FastAPI(title="Project Repository", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

Status = Literal["Submitted", "Under Review", "Changes Requested", "Approved"]

class TeamCreate(SQLModel):
    title: str
    abstract: str
    guide: str
    members: str

class StatusUpdate(SQLModel):
    status: Status

@app.get("/", response_class=HTMLResponse)
def home(request: Request, session: Annotated[Session, Depends(get_session)]):
    teams = session.exec(select(Team)).all()
    return templates.TemplateResponse(request, "index.html", {"teams": teams})

@app.get("/team/{team_id}", response_class=HTMLResponse)
def team_page(request: Request, team_id: int,
              session: Annotated[Session, Depends(get_session)]):
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    files = session.exec(
        select(ProjectFile)
        .where(ProjectFile.team_id == team_id)
        .order_by(col(ProjectFile.uploaded_at).desc())
    ).all()
    return templates.TemplateResponse(
        request, "team.html",
        {"team": team, "files": files, "statuses": get_args(Status)},
    )

@app.post("/team/{team_id}/status")
def update_status_form(
    team_id: int,
    status: Annotated[Status, Form()],
    session: Annotated[Session, Depends(get_session)],
):
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    team.status = status
    session.commit()
    return RedirectResponse(f"/team/{team_id}", status_code=303)
@app.get("/new-team", response_class=HTMLResponse)
def new_team_form(request: Request):
    return templates.TemplateResponse(request, "new_team.html", {})

@app.post("/new-team")
def create_team_form(
    title: Annotated[str, Form()],
    abstract: Annotated[str, Form()],
    guide: Annotated[str, Form()],
    members: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
):
    team = Team(title=title.strip(), abstract=abstract.strip(),
                guide=guide.strip(), members=members.strip())
    session.add(team)
    session.commit()
    session.refresh(team)
    return RedirectResponse(f"/team/{team.id}", status_code=303)

@app.post("/teams")
def create_team(data: TeamCreate, session: Session = Depends(get_session)):  # noqa: B008
    team = Team(**data.model_dump())
    session.add(team)
    session.commit()
    session.refresh(team)
    return team

@app.get("/teams")
def list_teams(session: Session = Depends(get_session)):  # noqa: B008
    return session.exec(select(Team)).all()

@app.get("/teams/{team_id}")
def get_team(team_id: int, session: Session = Depends(get_session)):  # noqa: B008
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team

@app.patch("/teams/{team_id}/status")
def update_status(team_id: int, data: StatusUpdate, session: Session = Depends(get_session)):  # noqa: B008
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    team.status = data.status
    session.commit()
    session.refresh(team)
    return team

FileType = Literal["Doc", "PPT", "Code"]

def save_upload(team_id: int, file_type: str, file: UploadFile, session: Session) -> ProjectFile:
    if not session.get(Team, team_id):
        raise HTTPException(status_code=404, detail="Team not found")
    filename = file.filename
    if not filename:
        raise HTTPException(status_code=400, detail="File has no name")

    safe_name = Path(filename).name
    key = f"team_{team_id}/{uuid.uuid4().hex}_{safe_name}"
    try:
        s3.upload_fileobj(
            file.file, S3_BUCKET, key,
            ExtraArgs={"ContentType": file.content_type or "application/octet-stream"},
        )
    except ClientError as e:
        raise HTTPException(status_code=502, detail="Upload to storage failed") from e

    record = ProjectFile(team_id=team_id, file_type=file_type,
                         filename=safe_name, path=key)      # path now holds the S3 key
    session.add(record)
    session.commit()
    session.refresh(record)
    return record

@app.post("/teams/{team_id}/files")
def upload_file(
    team_id: int,
    file_type: Annotated[FileType, Form()],
    file: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_session)],
):
    return save_upload(team_id, file_type, file, session)

@app.get("/teams/{team_id}/files")
def list_files(team_id: int, session: Annotated[Session, Depends(get_session)]):
    return session.exec(select(ProjectFile).where(ProjectFile.team_id == team_id)).all()

@app.post("/team/{team_id}/upload")
def upload_file_form(
    team_id: int,
    file_type: Annotated[FileType, Form()],
    file: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_session)],
):
    save_upload(team_id, file_type, file, session)
    return RedirectResponse(f"/team/{team_id}", status_code=303)

@app.get("/files/{file_id}/download")
def download_file(file_id: int,
                  session: Annotated[Session, Depends(get_session)],
                  inline: bool = False):
    record = session.get(ProjectFile, file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    disposition = "inline" if inline else "attachment"
    url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": S3_BUCKET,
            "Key": record.path,
            "ResponseContentDisposition": f"{disposition}; filename*=UTF-8''{quote(record.filename)}",
        },
        ExpiresIn=300,   # link works for 5 minutes
    )
    return RedirectResponse(url)

@app.post("/files/{file_id}/delete")
def delete_file(file_id: int, session: Annotated[Session, Depends(get_session)]):
    record = session.get(ProjectFile, file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    team_id = record.team_id
    try:
        s3.delete_object(Bucket=S3_BUCKET, Key=record.path)
    except ClientError as e:
        raise HTTPException(status_code=502, detail="Delete from storage failed") from e
    session.delete(record)
    session.commit()
    return RedirectResponse(f"/team/{team_id}", status_code=303)