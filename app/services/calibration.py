from __future__ import annotations

import time
from collections import defaultdict

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.entities import AQRecommendation

_CACHE={"at":0.0,"weights":{}}
TTL_SECONDS=300


def _bucket(p:int)->str:
    if p>=80:return "80-99"
    if p>=70:return "70-79"
    if p>=60:return "60-69"
    return "01-59"


def calibration_weights()->dict[str,float]:
    now=time.time()
    if now-_CACHE["at"]<TTL_SECONDS:
        return dict(_CACHE["weights"])
    groups=defaultdict(list)
    with SessionLocal() as db:
        rows=list(db.scalars(select(AQRecommendation).where(AQRecommendation.result.in_(["GREEN","RED"]))).all())
    for r in rows: groups[_bucket(r.probability)].append(r)
    weights={}
    for bucket,items in groups.items():
        # exige amostra razoável antes de alterar o modelo
        if len(items)<20:
            weights[bucket]=1.0;continue
        expected=sum(r.probability for r in items)/len(items)
        observed=sum(1 for r in items if r.result=="GREEN")/len(items)*100
        gap=observed-expected
        weights[bucket]=round(max(0.85,min(1.02,1+gap/200)),3)
    _CACHE["at"]=now;_CACHE["weights"]=weights
    return dict(weights)


def recalibrate_probability(probability_pct:int)->tuple[int,float]:
    weight=calibration_weights().get(_bucket(probability_pct),1.0)
    adjusted=round(probability_pct*weight)
    return max(1,min(99,adjusted)),weight
