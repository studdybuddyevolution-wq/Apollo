"""Production FastAPI entrypoint with workspace and Phase 2 routes registered."""

from main import app
from phase1_routes import register as register_phase1
from phase2_routes import register as register_phase2
from phase3_routes import register as register_phase3
from socratic_routes import register as register_socratic
from auth_routes import register as register_auth
from billing_routes import register as register_billing
from planner_routes import register as register_planner
from reference_schema import ensure_reference_schema

ensure_reference_schema()

register_phase1(app)
register_phase2(app)
register_phase3(app)
register_socratic(app)
register_auth(app)
register_billing(app)
register_planner(app)

__all__ = ["app"]