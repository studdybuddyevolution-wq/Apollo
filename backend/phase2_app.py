"""Production FastAPI entrypoint with workspace and Phase 2 routes registered."""

from main import app
from phase1_routes import register as register_phase1
from phase2_routes import register as register_phase2
from phase3_routes import register as register_phase3
from socratic_routes import register as register_socratic
from history_routes import register as register_history

register_phase1(app)
register_phase2(app)
register_phase3(app)
register_socratic(app)
register_history(app)

__all__ = ["app"]