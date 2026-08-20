from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
import re

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.entities import AQRecommendation, BetEntryHistory
from app.services.settlement import settle_leg
from app.services.sports import SportsService


def bucket_for_probability(p: int) -> str:
    if p >= 80: return "80-99"
    if p >= 70: return "70-79"
    if p >= 60: return "60-69"
    return "01-59"


def _metric(rows):
    settled=[r for r in rows if r.result in {"GREEN","RED","REFUND","WIN","LOSS","PUSH"}]
    wins=sum(1 for r in settled if r.result in {"GREEN","WIN"})
    losses=sum(1 for r in settled if r.result in {"RED","LOSS"})
    staked=float(len([r for r in settled if r.result not in {"REFUND","PUSH"}]))
    profit=sum(float(getattr(r,"settled_profit_unit",0) or 0) for r in settled)
    return {"entries":len(settled),"wins":wins,"losses":losses,"win_rate":round(wins/max(wins+losses,1)*100,2),"roi":round(profit/max(staked,1)*100,2),"profit_units":round(profit,2)}


def log_recommendations(payload: dict, analysis: dict) -> int:
    fixture_id=int(payload.get("fixture_id") or 0)
    if fixture_id <= 0: return 0
    entries=analysis.get("recommended_entries") or []
    created=0
    with SessionLocal() as db:
        for item in entries:
            market=str(item.get("market") or "")
            selection=str(item.get("selection") or "")
            duplicate=db.scalar(select(AQRecommendation).where(AQRecommendation.fixture_id==fixture_id,AQRecommendation.market==market,AQRecommendation.selection==selection,AQRecommendation.result=="PENDING"))
            if duplicate: continue
            odd=None
            for source in payload.get("market_probabilities") or []:
                if source.get("market")==market and source.get("selection")==selection:
                    odd=source.get("best_odd")
                    break
            row=AQRecommendation(
                fixture_id=fixture_id,league=str(payload.get("league") or ""),home_team=str(payload.get("home_team") or ""),away_team=str(payload.get("away_team") or ""),
                market=market,selection=selection,probability=int(item.get("probability") or 0),confidence=int(item.get("confidence") or payload.get("data_confidence") or 0),
                risk=str(item.get("risk") or "ALTO"),mode="PRE_LIVE",offered_odd=float(odd) if odd else None,calibration_bucket=bucket_for_probability(int(item.get("probability") or 0)),
            )
            db.add(row);created+=1
        db.commit()
    return created


def _recommendation_to_leg(row: AQRecommendation):
    text=row.selection.upper();market=row.market.upper();line_match=re.search(r"(\d+(?:\.\d+)?)",row.selection);line=float(line_match.group(1)) if line_match else None
    side="OVER" if "OVER" in text else "UNDER" if "UNDER" in text else text
    if "DUPLA" in market:
        mapping={"1X":"double_chance_1x","X2":"double_chance_x2","12":"double_chance_12"};return mapping.get(text,text.lower()),text,None
    if "ESCANTE" in market: return "corners_total",side,line
    if "GOLS" in market: return "goals_total",side,line
    if "AMBAS" in market: return "btts", "YES" if text in {"SIM","YES"} else "NO",None
    return "",side,line


async def sync_recommendations(limit: int=100):
    sports=SportsService();checked=settled=waiting=errors=0
    with SessionLocal() as db:
        rows=list(db.scalars(select(AQRecommendation).where(AQRecommendation.result=="PENDING").order_by(AQRecommendation.created_at.asc()).limit(limit)).all())
        for row in rows:
            checked+=1
            try:
                match=await sports.final_match_data(row.fixture_id)
                if not match: waiting+=1;continue
                market_id,side,line=_recommendation_to_leg(row)
                if not market_id: waiting+=1;continue
                odd=row.offered_odd or (100.0/max(row.probability,1))
                settlement=settle_leg(market_id,side,line,odd,match)
                if settlement.status in {"WAITING_STATS","PENDING"}: waiting+=1;continue
                if settlement.status in {"WIN","HALF_WIN"}: row.result="GREEN"
                elif settlement.status in {"LOSS","HALF_LOSS"}: row.result="RED"
                else: row.result="REFUND"
                row.settled_profit_unit=round((settlement.multiplier or 0)-1,4)
                row.settled_at=datetime.now(timezone.utc);settled+=1
            except Exception:
                errors+=1
        db.commit()
    return {"checked":checked,"settled":settled,"waiting":waiting,"errors":errors}


def recommendation_report():
    with SessionLocal() as db: rows=list(db.scalars(select(AQRecommendation).order_by(AQRecommendation.created_at.desc())).all())
    by_market=defaultdict(list);by_league=defaultdict(list);by_mode=defaultdict(list);by_bucket=defaultdict(list)
    for r in rows:
        by_market[r.market].append(r);by_league[r.league].append(r);by_mode[r.mode].append(r);by_bucket[bucket_for_probability(r.probability)].append(r)
    calibration=[]
    for bucket,items in sorted(by_bucket.items()):
        settled=[x for x in items if x.result in {"GREEN","RED","WIN","LOSS"}]
        if not settled: continue
        observed=sum(1 for x in settled if x.result in {"GREEN","WIN"})/len(settled)*100;expected=mean(x.probability for x in settled)
        calibration.append({"bucket":bucket,"samples":len(settled),"expected":round(expected,2),"observed":round(observed,2),"gap":round(observed-expected,2)})
    return {"overall":_metric(rows),"by_market":[{"name":k,**_metric(v)} for k,v in sorted(by_market.items())],"by_league":[{"name":k,**_metric(v)} for k,v in sorted(by_league.items())],"by_mode":[{"name":k,**_metric(v)} for k,v in sorted(by_mode.items())],"calibration":calibration,"recommendations_total":len(rows)}


def bankroll_execution_report():
    with SessionLocal() as db: rows=list(db.scalars(select(BetEntryHistory).order_by(BetEntryHistory.created_at.desc())).all())
    by_market=defaultdict(list);by_method=defaultdict(list);by_mode=defaultdict(list)
    for r in rows: by_market[r.market].append(r);by_method[r.method or "Sem método"].append(r);by_mode[r.mode].append(r)
    def calc(items):
        staked=sum(r.stake for r in items);profit=sum(r.profit for r in items);greens=sum(1 for r in items if r.result=="GREEN");reds=sum(1 for r in items if r.result=="RED")
        return {"entries":len(items),"greens":greens,"reds":reds,"win_rate":round(greens/max(greens+reds,1)*100,2),"roi":round(profit/max(staked,1)*100,2),"profit":round(profit,2),"staked":round(staked,2)}
    return {"overall":calc(rows),"by_market":[{"name":k,**calc(v)} for k,v in sorted(by_market.items())],"by_method":[{"name":k,**calc(v)} for k,v in sorted(by_method.items())],"by_mode":[{"name":k,**calc(v)} for k,v in sorted(by_mode.items())]}


def calibration_weights():
    report=recommendation_report();weights={}
    for item in report["calibration"]:
        gap=item["gap"]
        # conservative recalibration: never inflate more than 2%, can reduce up to 15%
        weights[item["bucket"]]=round(max(0.85,min(1.02,1+gap/200)),3)
    return {"weights":weights,"policy":"Pesos corrigem suavemente probabilidades; amostra pequena nunca aumenta confiança.","generated_at":datetime.now(timezone.utc).isoformat()}
