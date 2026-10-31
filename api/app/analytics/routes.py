"""api/app/analytics/routes.py - Aggregates all S3 Analytics sub-routers."""

from fastapi import APIRouter

from api.app.analytics import (
    base,
    summary,
    trend,
    breakdown,
    sources,
    targets,
    score,
    anomaly,
    reports,
    live,
    me,
)

router = APIRouter(prefix="/analytics", tags=["S3 Analytics"])

@router.get("/ping")
def analytics_ping():
    return {"ok": True, "service": "S3 Analytics & Reporting"}

# Include all sub-routers
router.include_router(base.router)
router.include_router(summary.router)
router.include_router(trend.router)
router.include_router(breakdown.router)
router.include_router(sources.router)
router.include_router(targets.router)
router.include_router(score.router)
router.include_router(anomaly.router)
router.include_router(reports.router)
router.include_router(live.router)
router.include_router(me.router)
