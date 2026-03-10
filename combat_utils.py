import random


def hp_from_stats(stats: dict, default: int = 10) -> int:
    try:
        return max(1, int(stats.get("hp", default) or default))
    except Exception:
        return default


def initiative_from_dex(dex_score: int) -> int:
    # Initiative is capped to a d20 roll (1..20) by current game-rule preference.
    _ = dex_score
    return random.randint(1, 20)
