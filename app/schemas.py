import datetime
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class LinkCreate(BaseModel):
    url: str = Field(..., max_length=2048, description="Target URL (http/https)")
    custom_code: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=32,
        description="Optional custom alias for the link",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        if len(v) > 2048:
            raise ValueError("URL exceeds maximum length of 2048 characters")
        return v

    @field_validator("custom_code")
    @classmethod
    def validate_custom_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not re.match(r"^[A-Za-z0-9_-]{3,32}$", v):
            err = "custom_code must be 3-32 characters (letters, digits, '_' or '-')"
            raise ValueError(err)
        return v


class LinkResponse(BaseModel):
    code: str
    short_url: str
    url: str
    created_at: datetime.datetime


class LinkListResponse(BaseModel):
    items: list[LinkResponse]
    total: int
    limit: int
    offset: int


class DailyClickStat(BaseModel):
    day: str
    count: int


class ReferrerStat(BaseModel):
    referrer: str
    count: int


class LinkStatsResponse(BaseModel):
    code: str
    target_url: str
    total_clicks: int
    clicks_last_7_days: list[DailyClickStat]
    top_referrers: list[ReferrerStat]


class VersionResponse(BaseModel):
    version: str
    git_sha: str
    pod: str


class DependencyHealth(BaseModel):
    database: str
    redis: str
    status: str
