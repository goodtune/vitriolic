from typing import List, Optional
from uuid import UUID
from ninja import Schema


class CompetitionSchema(Schema):
    id: int
    title: str
    slug: str
    short_title: Optional[str] = None


class SeasonSchema(Schema):
    id: int
    title: str
    slug: str
    short_title: Optional[str] = None
    competition_id: int


class DivisionSchema(Schema):
    id: int
    title: str
    slug: str
    short_title: Optional[str] = None
    season_id: int


class TeamSchema(Schema):
    id: int
    title: str
    slug: str
    division_id: int


class MatchSchema(Schema):
    uuid: UUID
    home_team_id: Optional[int] = None
    away_team_id: Optional[int] = None
    home_team_score: Optional[int] = None
    away_team_score: Optional[int] = None
    date: Optional[str] = None
    time: Optional[str] = None
    round: Optional[int] = None
    is_bye: bool
    is_forfeit: bool
