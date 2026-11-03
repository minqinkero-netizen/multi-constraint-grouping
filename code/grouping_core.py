"""Validate input, restore calls, and audit the stated original model.
Internal IDs start at zero; exported resource/manager/round IDs start at one.
This module contains no optimization of P1.
"""
from itertools import combinations
import math
import numpy as np
INT_TOL=1e-6


def validate_input(d):
    for key in ("n", "m", "K"):
        if not isinstance(d[key], int) or isinstance(d[key], bool) or d[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    n = d["n"]
    if len(d["points"]) != n or any(len(p) != 2 for p in d["points"]):
        raise ValueError("points must have shape n by 2")
    if not np.isfinite(np.asarray(d["points"], float)).all():
        raise ValueError("nonfinite coordinate")
    if not math.isfinite(d["r"]) or d["r"] < 0:
        raise ValueError("r must be finite and nonnegative")
    T = len(d["targets"])
    if T < 1:
        raise ValueError("at least one round is required")
    for targets in d["targets"]:
        if len(set(targets)) != len(targets):
            raise ValueError("duplicate target ID")
        if any(not isinstance(i, int) or i < 0 or i >= n for i in targets):
            raise ValueError("invalid target ID")
    if len(set(d["strict"])) != len(d["strict"]):
        raise ValueError("duplicate strict-round ID")
    if any(not isinstance(t, int) or t < 0 or t >= T for t in d["strict"]):
        raise ValueError("invalid strict-round ID")

def normalize_integer_x(d, raw_x):
    """Only remove numerical noise around 0/1. Never round a fractional LP."""
    x = np.asarray(raw_x, dtype=float)
    if x.shape != (d["n"], d["m"]) or not np.isfinite(x).all():
        raise ValueError("invalid x shape or nonfinite entry")
    nearest = np.rint(x)
    if np.max(np.abs(x - nearest)) > INT_TOL:
        raise ValueError("fractional x cannot be restored")
    if np.any(nearest < 0) or np.any(nearest > 1):
        raise ValueError("x is outside binary domain")
    x = nearest.astype(int)
    if np.any(x.sum(axis=1) != 1):
        raise ValueError("every resource must have exactly one manager")
    return x

def check_grouping(d, x):
    """Check fixed-group rules from sets/coordinates, not MILP matrix rows."""
    groups = [np.flatnonzero(x[:, g]).tolist() for g in range(d["m"])]
    issues = []
    for g, group in enumerate(groups):
        if len(group) > d["K"]:
            issues.append(f"capacity: manager {g+1}")
        for i, j in combinations(group, 2):
            # Same strict > r rule as the model; no hidden relaxed radius.
            if math.dist(d["points"][i], d["points"][j]) > d["r"]:
                issues.append(f"distance: {i+1}, {j+1}, manager {g+1}")
    for t in d["strict"]:
        for g, group in enumerate(groups):
            if len(set(group).intersection(d["targets"][t])) > 1:
                issues.append(f"strict targets collide: round {t+1}, manager {g+1}")
    if issues:
        raise ValueError("; ".join(issues))
    return groups

def restore(d, raw_x):
    validate_input(d)
    x = normalize_integer_x(d, raw_x)
    groups = check_grouping(d, x)
    n, m, T = d["n"], d["m"], len(d["targets"])
    y = np.zeros((n, T, m), dtype=int)
    # Only target occurrences are visited; no need to scan every i,t,g.
    labels = x.argmax(axis=1)
    chosen = {}
    for t, targets in enumerate(d["targets"]):
        for i in targets:
            key = (t, int(labels[i]))
            if key not in chosen or i < chosen[key]:
                chosen[key] = i
    for (t, g), i in chosen.items():
        y[i, t, g] = 1
    audit = audit_p1(d, x, y)
    if not audit["feasible"]:
        raise ValueError("restored P1 audit failed: " + repr(audit["failures"]))
    return x, y, groups, audit

def audit_p1(d, x, y):
    """Independent original-P1 checker, including calls, not reduced cost."""
    n, m, T = d["n"], d["m"], len(d["targets"])
    x, y = np.asarray(x), np.asarray(y)
    if x.shape != (n, m) or y.shape != (n, T, m):
        return {"feasible": False, "failures": ["array shape"]}
    flags = {
        "binary_x": bool(np.isin(x, [0, 1]).all()),
        "binary_y": bool(np.isin(y, [0, 1]).all()),
        "unique_assignment": bool((x.sum(axis=1) == 1).all()),
        "capacity": bool((x.sum(axis=0) <= d["K"]).all()),
        "distance": True,
        "ownership": bool((y <= x[:, None, :]).all()),
        "target_and_no_duplicate": True,
        "one_call_per_manager": bool((y.sum(axis=0) <= 1).all()),
        "strict_rounds_complete": True,
    }
    for g in range(m):
        members = np.flatnonzero(x[:, g] == 1).tolist()
        for i, j in combinations(members, 2):
            if math.dist(d["points"][i], d["points"][j]) > d["r"]:
                flags["distance"] = False
    round_records = []
    for t, targets in enumerate(d["targets"]):
        desired = np.zeros(n, dtype=int)
        desired[targets] = 1
        calls = y[:, t, :].sum(axis=1)
        if np.any(calls > desired):
            flags["target_and_no_duplicate"] = False
        if t in d["strict"] and not np.array_equal(calls, desired):
            flags["strict_rounds_complete"] = False
        active = np.flatnonzero(calls).tolist()
        missing = sorted(set(targets) - set(active))
        round_records.append({
            "round": t+1, "strict": t in d["strict"],
            "targets": [i+1 for i in sorted(targets)],
            "by_manager": [[int(i)+1 for i in np.flatnonzero(y[:, t, g])] for g in range(m)],
            "activated": [i+1 for i in active],
            "missing": [i+1 for i in missing], "omissions": len(missing),
        })
    failures = [k for k, ok in flags.items() if not ok]
    objective = sum(len(d["targets"][t]) - int(y[:, t, :].sum())
                    for t in range(T) if t not in d["strict"])
    return {"feasible": not failures, "checks": flags, "failures": failures,
            "L": objective, "round_records": round_records}
