from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, HttpUrl, Field

class JobListing(BaseModel):
    url: HttpUrl
    title: str = Field(min_length=3, max_length=200)
    company: str = Field(default="Nincs megadva cég")
    location: str = Field(default="Nincs megadva")
    salary: Optional[str] = None
    description: str = Field(default="")
    relevance_score: Optional[int] = Field(default=None, ge=0, le=100)
    ai_summary: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        data = self.model_dump()
        data["url"] = str(self.url)
        data["created_at"] = self.created_at.isoformat()
        return data
