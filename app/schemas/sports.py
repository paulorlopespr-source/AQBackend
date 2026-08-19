from pydantic import BaseModel


class FixtureOut(BaseModel):
    fixture_id: int
    league: str
    kickoff: str
    home_team_id: int
    home_team: str
    away_team_id: int
    away_team: str
    status: str
    home_goals: int | None = None
    away_goals: int | None = None


class TeamFormOut(BaseModel):
    team_id: int
    team: str
    wins: int
    draws: int
    losses: int
    avg_goals_for: float
    avg_goals_against: float
    form_score: int
    form_label: str
