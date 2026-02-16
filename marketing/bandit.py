"""
Marketing Engine 2.0 — Multi-Armed Bandit (Local Optimization)
Epsilon-greedy + UCB1 for automatic template/variant selection.
No external ML — pure Python with DB-backed state.
"""
import math
import random

from marketing.models import BanditArm


# ═══════════════════════════ CONFIG ═══════════════════════════════════

EPSILON = 0.15          # exploration rate for epsilon-greedy
UCB_C = 1.41            # exploration constant for UCB1 (sqrt(2))
DEFAULT_ALGO = "ucb1"   # "ucb1" or "epsilon_greedy"


# ═══════════════════════════ ARM MANAGEMENT ═══════════════════════════

def get_or_create_arm(agency, arm_key):
    """Get or create a bandit arm for an agency."""
    arm, _ = BanditArm.objects.get_or_create(
        agency=agency, arm_key=arm_key,
    )
    return arm


def get_arms(agency, prefix=""):
    """Get all arms for an agency, optionally filtered by prefix."""
    qs = BanditArm.objects.filter(agency=agency)
    if prefix:
        qs = qs.filter(arm_key__startswith=prefix)
    return list(qs)


# ═══════════════════════════ SELECTION ════════════════════════════════

def select_arm(agency, arm_keys, algo=DEFAULT_ALGO):
    """
    Select the best arm from a list of arm_keys.
    Returns the chosen arm_key string.
    """
    if not arm_keys:
        return None

    # Ensure all arms exist
    arms = []
    for key in arm_keys:
        arm, _ = BanditArm.objects.get_or_create(agency=agency, arm_key=key)
        arms.append(arm)

    # If any arm has zero pulls, explore it first
    unpulled = [a for a in arms if a.pulls == 0]
    if unpulled:
        chosen = random.choice(unpulled)
        return chosen.arm_key

    if algo == "epsilon_greedy":
        return _epsilon_greedy(arms)
    else:
        return _ucb1(arms)


def _epsilon_greedy(arms):
    """Epsilon-greedy selection."""
    if random.random() < EPSILON:
        # Explore: random arm
        return random.choice(arms).arm_key
    else:
        # Exploit: best conversion rate
        best = max(arms, key=lambda a: a.conversion_rate)
        return best.arm_key


def _ucb1(arms):
    """UCB1 selection — balances exploration and exploitation."""
    total_pulls = sum(a.pulls for a in arms)
    if total_pulls == 0:
        return random.choice(arms).arm_key

    log_total = math.log(total_pulls)

    def ucb_score(arm):
        if arm.pulls == 0:
            return float("inf")
        exploitation = arm.conversion_rate
        exploration = UCB_C * math.sqrt(log_total / arm.pulls)
        return exploitation + exploration

    best = max(arms, key=ucb_score)
    return best.arm_key


# ═══════════════════════════ REWARD RECORDING ═════════════════════════

def record_pull(agency, arm_key):
    """Record that an arm was pulled (message sent)."""
    arm = get_or_create_arm(agency, arm_key)
    arm.pulls += 1
    arm.save(update_fields=["pulls", "updated_at"])
    return arm


def record_reward(agency, arm_key, converted=True):
    """Record a reward (conversion) for an arm."""
    arm = get_or_create_arm(agency, arm_key)
    if converted:
        arm.rewards += 1
        arm.save(update_fields=["rewards", "updated_at"])
    return arm


# ═══════════════════════════ STATS ════════════════════════════════════

def get_arm_stats(agency, prefix=""):
    """Get stats for all arms, sorted by conversion rate."""
    arms = get_arms(agency, prefix)
    stats = []
    for arm in arms:
        stats.append({
            "arm_key": arm.arm_key,
            "pulls": arm.pulls,
            "rewards": arm.rewards,
            "rate": round(arm.conversion_rate * 100, 1),
        })
    stats.sort(key=lambda x: x["rate"], reverse=True)
    return stats


def best_arm_key(agency, prefix=""):
    """Return the arm_key with the highest conversion rate."""
    arms = get_arms(agency, prefix)
    if not arms:
        return None
    best = max(arms, key=lambda a: a.conversion_rate)
    return best.arm_key if best.pulls > 0 else None
