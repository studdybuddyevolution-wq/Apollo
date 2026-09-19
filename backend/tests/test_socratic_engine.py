import json

import pytest

import socratic_engine
import workspace_service


def test_tier_boundaries_are_adaptive():
    assert socratic_engine.tier_for_score(0) == "Beginner"
    assert socratic_engine.tier_for_score(24.9) == "Beginner"
    assert socratic_engine.tier_for_score(25) == "Developing"
    assert socratic_engine.tier_for_score(49.9) == "Developing"
    assert socratic_engine.tier_for_score(50) == "Proficient"
    assert socratic_engine.tier_for_score(75) == "Advanced"
    assert socratic_engine.tier_for_score(90) == "Master"


def test_phase_routing_initial_to_elenchus():
    state = socratic_engine.SocraticState()
    assert socratic_engine.next_phase(state, "I think memorizing formulas is best") == socratic_engine.SocraticPhase.ELENCHUS


def test_elenchus_routes_to_maieutics_when_student_is_stuck():
    state = socratic_engine.SocraticState(phase="elenchus", user_response_count=1)
    assert socratic_engine.next_phase(state, "I don't know, I'm confused") == socratic_engine.SocraticPhase.MAIEUTICS


def test_elenchus_routes_to_aporia_after_reasoning():
    state = socratic_engine.SocraticState(phase="elenchus", user_response_count=1)
    assert socratic_engine.next_phase(state, "Because repeated practice strengthens recall") == socratic_engine.SocraticPhase.APORIA


def test_maieutics_is_bounded_to_two_consecutive_turns():
    first = socratic_engine.SocraticState(phase="maieutics", maieutics_count=1)
    second = socratic_engine.SocraticState(phase="maieutics", maieutics_count=2)
    assert socratic_engine.next_phase(first, "I am still stuck") == socratic_engine.SocraticPhase.MAIEUTICS
    assert socratic_engine.next_phase(second, "I am still stuck") == socratic_engine.SocraticPhase.APORIA


def test_aporia_routes_to_dialectic_when_student_can_reason():
    state = socratic_engine.SocraticState(phase="aporia", user_response_count=3)
    assert socratic_engine.next_phase(state, "That counterexample means my rule only works for ideal cases") == socratic_engine.SocraticPhase.DIALECTIC


def test_dialectic_can_conclude_on_explicit_finish():
    state = socratic_engine.SocraticState(phase="dialectic", in_dialectic_loop=True, user_response_count=6)
    assert socratic_engine.next_phase(state, "That's enough, I'm done") == socratic_engine.SocraticPhase.CONCLUSION


def test_force_advance_uses_valid_transitions():
    assert socratic_engine.next_phase(socratic_engine.SocraticState(phase="elenchus"), "", force_advance=True) == socratic_engine.SocraticPhase.APORIA
    assert socratic_engine.next_phase(socratic_engine.SocraticState(phase="aporia"), "", force_advance=True) == socratic_engine.SocraticPhase.DIALECTIC


def test_apply_phase_tracks_state():
    state = socratic_engine.apply_phase(socratic_engine.SocraticState(), socratic_engine.SocraticPhase.ELENCHUS, "Newton's laws")
    assert state.phase == "elenchus"
    assert state.topic == "Newton's laws"
    assert state.user_response_count == 1
    assert state.recent_moves == ["elenchus"]


@pytest.mark.parametrize("phase_a,phase_b", [("elenchus", "aporia"), ("maieutics", "aporia"), ("aporia", "dialectic")])
def test_phase_prompts_differ_by_stage(phase_a, phase_b):
    a = socratic_engine.SocraticState(phase=phase_a)
    b = socratic_engine.SocraticState(phase=phase_b)
    prompt_a = socratic_engine.build_socratic_system_prompt("Ohm's law", a, "V = IR")
    prompt_b = socratic_engine.build_socratic_system_prompt("Ohm's law", b, "V = IR")
    assert prompt_a != prompt_b
    assert "INDEXED NOTEBOOK CONTEXT" in prompt_a


def test_filesystem_mastery_persists(monkeypatch, tmp_path):
    monkeypatch.setattr(socratic_engine, "STORE", None)
    monkeypatch.setattr(socratic_engine, "MASTERY_FILE", tmp_path / "mastery.json")
    created = socratic_engine.upsert_mastery("u1", "Ohm's Law", 56, correct_delta=1, attempt_delta=1)
    assert created["tier"] == "Proficient"
    loaded = socratic_engine.get_mastery("u1", "ohm's law")
    assert loaded["score"] == 56
    assert loaded["attempts"] == 1
    assert json.loads((tmp_path / "mastery.json").read_text())["u1:ohm's law"]["score"] == 56


def test_workspace_socratic_state_persists(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace_service, "STORE", None)
    monkeypatch.setattr(workspace_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(workspace_service, "WORKSPACE_FILE", tmp_path / "workspace.json")

    session = workspace_service.create_session("u1", "nb1", "Socratic chat")
    state = {"phase": "aporia", "in_dialectic_loop": False, "mastery_score": 52, "mastery_tier": "Proficient"}
    assert workspace_service.save_socratic_state("u1", "nb1", session["id"], state) is True
    assert workspace_service.get_socratic_state("u1", "nb1", session["id"]) == state
