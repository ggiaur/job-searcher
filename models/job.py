from datetime import UTC, datetime

from pydantic import BaseModel, Field, HttpUrl


class JobListing(BaseModel):
    url: HttpUrl
    title: str = Field(min_length=3, max_length=200)
    company: str = Field(default="Nincs megadva cég")
    location: str = Field(default="Nincs megadva")
    salary: str | None = None
    description: str = Field(default="")
    relevance_score: int | None = Field(default=None, ge=0, le=100)
    ai_summary: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        data = self.model_dump()
        data["url"] = str(self.url)
        data["created_at"] = self.created_at.isoformat()
        return data
