from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.entities import AQRecommendation, BetEntryHistory


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


def recommendation_report():
    with SessionLocal() as db:
        rows=list(db.scalars(select(AQRecommendation).order_by(AQRecommendation.created_at.desc())).all())
    by_market=defaultdict(list);by_league=defaultdict(list);by_mode=defaultdict(list);by_bucket=defaultdict(list)
    for r in rows:
        by_market[r.market].append(r);by_league[r.league].append(r);by_mode[r.mode].append(r);by_bucket[bucket_for_probability(r.probability)].append(r)
    calibration=[]
    for bucket,items in sorted(by_bucket.items()):
        settled=[x for x in items if x.result in {"GREEN","RED","WIN","LOSS"}]
        if not settled: continue
        observed=sum(1 for x in settled if x.result in {"GREEN","WIN"})/len(settled)*100
        expected=mean(x.probability for x in settled)
        calibration.append({"bucket":bucket,"samples":len(settled),"expected":round(expected,2),"observed":round(observed,2),"gap":round(observed-expected,2)})
    return {
        "overall":_metric(rows),
        "by_market":[{"name":k,**_metric(v)} for k,v in sorted(by_market.items())],
        "by_league":[{"name":k,**_metric(v)} for k,v in sorted(by_league.items())],
        "by_mode":[{"name":k,**_metric(v)} for k,v in sorted(by_mode.items())],
        "calibration":calibration,
        "recommendations_total":len(rows),
    }


def bankroll_execution_report():
    with SessionLocal() as db:
        rows=list(db.scalars(select(BetEntryHistory).order_by(BetEntryHistory.created_at.desc())).all())
    by_market=defaultdict(list);by_method=defaultdict(list);by_mode=defaultdict(list)
    for r in rows:
        by_market[r.market].append(r);by_method[r.method or "Sem método"].append(r);by_mode[r.mode].append(r)
    def calc(items):
        staked=sum(r.stake for r in items);profit=sum(r.profit for r in items);greens=sum(1 for r in items if r.result=="GREEN");reds=sum(1 for r in items if r.result=="RED")
        return {"entries":len(items),"greens":greens,"reds":reds,"win_rate":round(greens/max(greens+reds,1)*100,2),"roi":round(profit/max(staked,1)*100,2),"profit":round(profit,2),"staked":round(staked,2)}
    return {"overall":calc(rows),"by_market":[{"name":k,**calc(v)} for k,v in sorted(by_market.items())],"by_method":[{"name":k,**calc(v)} for k,v in sorted(by_method.items())],"by_mode":[{"name":k,**calc(v)} for k,v in sorted(by_mode.items())]}


def calibration_weights():
    report=recommendation_report();weights={}
    for item in report["calibration"]:
        gap=item["gap"]
        weights[item["bucket"]]=round(max(0.85,min(1.05,1+gap/200)),3)
    return {"weights":weights,"policy":"Pesos só reduzem ou corrigem suavemente probabilidades; amostra pequena não aumenta confiança.","generated_at":datetime.now(timezone.utc).isoformat()}
