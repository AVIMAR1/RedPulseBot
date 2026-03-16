from __future__ import annotations

def total_xp_required_for_level(level: int) -> int:
    """
    Total XP needed to reach a given level.

    Level 1 starts at 0 XP.
    Each next level requires +100 * current_level XP:
      L2: 100
      L3: 100 + 200 = 300
      L4: 100 + 200 + 300 = 600
    """
    level = max(1, int(level))
    # sum_{k=1..level-1} 100*k = 100 * (level-1)*level/2
    return 50 * (level - 1) * level


def xp_required_to_next_level(level: int) -> int:
    level = max(1, int(level))
    return 100 * level


def level_from_xp(xp: int) -> int:
    xp = max(0, int(xp))
    level = 1
    # Levels won't be huge in practice; simple loop is fine.
    while xp >= total_xp_required_for_level(level + 1):
        level += 1
    return level


def progress_for_xp(xp: int) -> dict:
    """
    Returns:
      level, xp, xp_in_level, xp_to_next, pct (0..100)
    """
    xp = max(0, int(xp))
    level = level_from_xp(xp)
    cur_level_start = total_xp_required_for_level(level)
    next_level_start = total_xp_required_for_level(level + 1)
    xp_in_level = xp - cur_level_start
    xp_to_next = max(1, next_level_start - cur_level_start)
    pct = int((xp_in_level / xp_to_next) * 100) if xp_to_next else 100
    pct = max(0, min(100, pct))
    return {
        "level": level,
        "xp": xp,
        "xp_in_level": xp_in_level,
        "xp_to_next": xp_to_next,
        "pct": pct,
    }


def render_progress_bar(pct: int, width: int = 10) -> str:
    pct = max(0, min(100, int(pct)))
    width = max(5, min(20, int(width)))
    filled = round((pct / 100) * width)
    empty = width - filled
    return "█" * filled + "░" * empty

