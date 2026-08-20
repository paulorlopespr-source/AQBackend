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
    avg_corners: float = 0
    avg_shots: float = 0
    avg_shots_on_target: float = 0
    form_score: int
    form_label: str
    last_five: list[str] = []


class MarketProbabilityOut(BaseModel):
    market: str
    selection: str
    probability: int
    data_confidence: int
    confidence_label: str
    risk: str
    rationale: str
    fair_odd: float
    best_odd: float | None = None
    bookmaker: str | None = None
    ev_percent: float | None = None
    value_label: str = "SEM ODD"


class FixtureAnalysisOut(BaseModel):
    fixture_id: int
    league: str
    kickoff: str
    status: str
    home_team_id: int
    home_team: str
    away_team_id: int
    away_team: str
    home_form: TeamFormOut
    away_form: TeamFormOut
    aq_score: int
    confidence: str
    data_confidence: int = 0
    expected_goals_home: float
    expected_goals_away: float
    expected_corners: float
    expected_shots: float
    expected_shots_on_target: float
    market_probabilities: list[MarketProbabilityOut] = []
    summary: str
