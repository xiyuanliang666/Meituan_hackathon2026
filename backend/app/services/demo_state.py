from __future__ import annotations

from app.services.business_db import (
    clear_user_demo_data,
    get_latest_recommendation_snapshot,
    get_latest_user_tune,
    get_recommendation_snapshot,
    get_selected_user_hand_asset,
    get_user_demo_state,
    get_user_hand_profile,
)
from app.services.tryon_history import list_tryon_history


def get_demo_state_bundle(user_id: str) -> dict:
    state = get_user_demo_state(user_id) or {}
    current_hand = get_selected_user_hand_asset(user_id)

    hand_profile = None
    hand_profile_id = state.get("current_hand_profile_id")
    if hand_profile_id:
        hand_profile = get_user_hand_profile(hand_profile_id)

    recommendation_snapshot = None
    snapshot_id = state.get("current_recommendation_snapshot_id")
    if snapshot_id:
        recommendation_snapshot = get_recommendation_snapshot(snapshot_id)
    elif hand_profile_id:
        recommendation_snapshot = get_latest_recommendation_snapshot(user_id, hand_profile_id=hand_profile_id)

    current_tune = None
    tune_id = state.get("current_tune_id")
    if tune_id:
        current_tune = get_latest_user_tune(user_id) if False else None
    if tune_id:
        from app.services.business_db import get_user_tune_history_item

        current_tune = get_user_tune_history_item(tune_id)
    elif recommendation_snapshot and recommendation_snapshot.get("recommendations"):
        first_style_id = recommendation_snapshot["recommendations"][0].get("style_id")
        current_tune = get_latest_user_tune(user_id, source_style_id=first_style_id) if first_style_id else None
    else:
        current_tune = get_latest_user_tune(user_id)

    tryon_records, _ = list_tryon_history(user_id=user_id, limit=100, offset=0)
    return {
        "user_id": user_id,
        "current_hand": current_hand,
        "hand_profile": hand_profile,
        "recommendation_snapshot": recommendation_snapshot,
        "current_tune": current_tune,
        "tryon_records": tryon_records,
    }


def clear_demo_state_bundle(user_id: str) -> None:
    clear_user_demo_data(user_id)

