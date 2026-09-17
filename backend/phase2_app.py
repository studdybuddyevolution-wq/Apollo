"""Production FastAPI entrypoint with workspace and Phase 2 routes registered."""

from main import app
from phase1_routes import register as register_phase1
from phase2_routes import register as register_phase2

register_phase1(app)
register_phase2(app)

__all__ = ["app"]
