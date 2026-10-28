"""Solve reduced P2, restore P1 actions, and check the ORIGINAL P1 rules.

Internal input IDs are zero-based. Exported resource/manager/round IDs are
one-based. This solves the paper's stated simulation model, not an unavailable
industrial DLL, brightness metric, or industrial acceptance instance.
"""
from pathlib import Path
from itertools import combinations, product
import argparse
import json
import math
import platform
import time
import numpy as np
import scipy
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

ROOT = Path(__file__).resolve().parent
INT_TOL = 1e-6
VALUE_TOL = 1e-6


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


def build_p2(d):
    validate_input(d)
    n, m, K = d["n"], d["m"], d["K"]
    T = len(d["targets"])
    S = set(d["strict"])
    F = [t for t in range(T) if t not in S]
    nx = n * m
    nz = len(F) * m
    nv = nx + nz
    fpos = {t: k for k, t in enumerate(F)}
    ix = lambda i, g: i * m + g
    iz = lambda t, g: nx + fpos[t] * m + g
    c = np.r_[np.zeros(nx), np.ones(nz)]
    integrality = np.r_[np.ones(nx, dtype=int), np.zeros(nz, dtype=int)]
    bounds = Bounds(np.zeros(nv), np.r_[np.ones(nx), np.full(nz, np.inf)])
    rr, cc, vv, lower, upper = [], [], [], [], []

    def row(terms, lo=-np.inf, hi=np.inf):
        k = len(lower)
        for j, value in terms:
            rr.append(k)
            cc.append(j)
            vv.append(value)
        lower.append(lo)
        upper.append(hi)

    for i in range(n):
        row([(ix(i, g), 1) for g in range(m)], 1, 1)
    for g in range(m):
        row([(ix(i, g), 1) for i in range(n)], hi=K)
    distance_pairs = 0
    for i, j in combinations(range(n), 2):
        if math.dist(d["points"][i], d["points"][j]) > d["r"]:
            distance_pairs += 1
            for g in range(m):
                row([(ix(i, g), 1), (ix(j, g), 1)], hi=1)
    for t, g in product(sorted(S), range(m)):
        row([(ix(i, g), 1) for i in d["targets"][t]], hi=1)
    for t, g in product(F, range(m)):
        row([(ix(i, g), 1) for i in d["targets"][t]] + [(iz(t, g), -1)], hi=1)
    A = coo_matrix((vv, (rr, cc)), shape=(len(lower), nv)).tocsc()
    return c, integrality, bounds, LinearConstraint(A, lower, upper), {
        "nx": nx, "nz": nz, "rows": len(lower), "distance_pairs": distance_pairs,
        "approximate_rounds": F,
    }


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


def finite_float(v):
    return float(v) if v is not None and math.isfinite(float(v)) else None


def solve_restore(d, time_limit=10.0):
    c, integrality, bounds, constraints, metadata = build_p2(d)
    start = time.perf_counter()
    res = milp(c, integrality=integrality, bounds=bounds, constraints=constraints,
               options={"presolve": True, "time_limit": time_limit, "mip_rel_gap": 0.0})
    elapsed = time.perf_counter() - start
    out = {"status": int(res.status), "message": res.message,
           "has_solver_vector": res.x is not None,
           "solver_objective": finite_float(res.fun),
           "solver_lower_bound": finite_float(getattr(res, "mip_dual_bound", None)),
           "solver_relative_gap": finite_float(getattr(res, "mip_gap", None)),
           "solver_node_count": int(res.mip_node_count) if getattr(res, "mip_node_count", None) is not None else None,
           "elapsed_seconds_for_log_only": elapsed, "model_size": metadata,
           "time_limit_seconds": time_limit, "mip_rel_gap_requested": 0.0,
           "outcome": "no_verified_solution"}
    if res.status == 2:
        out["outcome"] = "solver_reports_infeasible"
        return out
    if res.status not in (0, 1):
        out["outcome"] = "solver_abnormal"
        return out
    if res.x is None:
        return out
    try:
        x, y, groups, audit = restore(d, res.x[:metadata["nx"]].reshape(d["n"], d["m"]))
    except ValueError as exc:
        out["outcome"] = "candidate_rejected"
        out["reason"] = str(exc)
        return out
    U = audit["L"]
    F = metadata["approximate_rounds"]
    q = sum(max(sum(x[i, g] for i in d["targets"][t]) - 1, 0)
            for t in F for g in range(d["m"]))
    assert q == U
    if out["solver_objective"] is None or U > out["solver_objective"] + VALUE_TOL:
        raise ValueError("restored cost exceeds solver epigraph cost")
    b = out["solver_lower_bound"]
    count_bound = sum(max(len(d["targets"][t]) - d["m"], 0) for t in F)
    lower = max(float(count_bound), b) if b is not None else float(count_bound)
    if lower > U + VALUE_TOL:
        raise ValueError("lower bound exceeds restored feasible upper bound")
    gap = max(0.0, U - lower)
    optimal = (U == count_bound) or (res.status == 0 and gap <= VALUE_TOL)
    out.update(outcome="verified_optimal_within_tolerance" if optimal else "verified_feasible",
               x=x.tolist(), y=y.tolist(),
               groups=[[i+1 for i in group] for group in groups],
               original_P1_audit=audit, Q=int(q), upper_bound=U,
               lower_bound=lower, elementary_count_lower_bound=count_bound, absolute_gap=gap,
               optimality_basis="nonnegative_objective_and_zero_feasible_loss" if U == 0
               else ("elementary_target_count_bound" if U == count_bound
                     else ("solver_bounds_within_tolerance" if optimal else "not_certified")))
    return out


def run_checks():
    previous = json.loads((ROOT / "reduction_checks.json").read_text())
    base = previous["base_instance"]
    cases = [("base8", base)] + [(f"seed{e['instance']['seed']}", e["instance"])
                                     for e in previous["extra_instances"]]
    results = []
    from verify_reduction import solve as solve_reference_p1
    for name, d in cases:
        result = solve_restore(d)
        reference = solve_reference_p1(d, "P1")
        assert result["outcome"] == "verified_optimal_within_tolerance", (name, result)
        assert reference["status"] == 0
        assert abs(reference["objective"] - result["upper_bound"]) < VALUE_TOL
        results.append({"name": name, "instance": d, "result": result,
                        "direct_P1_optimum": reference["objective"]})
    feasible_count, rejected_count = 0, 0
    for labels in product(range(base["m"]), repeat=base["n"]):
        x = np.eye(base["m"], dtype=int)[list(labels)]
        try:
            restore(base, x)
            feasible_count += 1
        except ValueError:
            rejected_count += 1
    assert (feasible_count, rejected_count) == (32, 224)
    B = np.eye(2, dtype=int)[[0, 0, 1, 1, 0, 0, 1, 1]]
    A = np.eye(2, dtype=int)[[0, 0, 0, 0, 1, 1, 1, 1]]
    examples = {}
    for name, x in [("A", A), ("B", B)]:
        xx, yy, groups, audit = restore(base, x)
        examples[name] = {"x": xx.tolist(), "y": yy.tolist(),
                          "groups": [[i+1 for i in g] for g in groups], "audit": audit}
    assert examples["A"]["audit"]["L"] == 2
    assert examples["B"]["audit"]["L"] == 0
    # Guard against the fractional counterexample from Section 3.
    try:
        restore(base, np.full((8, 2), .5))
    except ValueError:
        fractional_rejected = True
    else:
        raise AssertionError("fractional input accepted")
    x, y, _, _ = restore(base, B)
    corrupted = {}
    z = y.copy(); z[0, 0, 0] = 0
    corrupted["missing_strict_target"] = audit_p1(base, x, z)
    z = y.copy(); z[0, 0, 0] = 0; z[0, 0, 1] = 1
    corrupted["wrong_manager"] = audit_p1(base, x, z)
    z = y.copy(); z[4, 2, 0] = 1
    corrupted["off_target_and_two_calls"] = audit_p1(base, x, z)
    assert all(not a["feasible"] for a in corrupted.values())
    # Empty groups, empty target rounds, and no approximate rounds are legal.
    empty_case = {"n": 2, "m": 3, "K": 5, "r": 1., "points": [[0., 0.], [.1, 0.]],
                  "targets": [[], [0]], "strict": [0, 1]}
    ex = np.eye(3, dtype=int)[[0, 0]]
    _, _, empty_groups, empty_audit = restore(empty_case, ex)
    assert empty_audit["feasible"] and empty_audit["L"] == 0 and len(empty_groups[1]) == 0
    tight = previous["tight_distance_instance"]
    tight_result = solve_restore(tight)
    assert tight_result["outcome"] == "solver_reports_infeasible"
    # One larger-round check; planted input is only a reproducibility example.
    from verify_reduction import planted
    d32 = planted(2026, 20, 4, 32, True)
    result32 = solve_restore(d32)
    assert result32["outcome"] == "verified_optimal_within_tolerance"
    reference32 = solve_reference_p1(d32, "P1")
    assert reference32["status"] == 0 and abs(reference32["objective"] - result32["upper_bound"]) < VALUE_TOL
    data = {"scope": "P1 simulation-model recovery and exact-reference verification; not industrial acceptance",
            "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
            "tolerances": {"integrality": INT_TOL, "bound_gap": VALUE_TOL, "distance": "strict double-precision > r; no added slack"},
            "cases": results, "illustrated_partitions": examples,
            "exhaustive_base_grouping_guard": {"accepted": feasible_count, "rejected": rejected_count},
            "fractional_input_rejected": fractional_rejected, "corrupted_actions": corrupted,
            "empty_groups_case": {"instance": empty_case, "audit": empty_audit},
            "tight_distance_case": {"instance": tight, "result": tight_result},
            "round32_case": {"instance": d32, "result": result32,
                             "direct_P1_optimum": reference32["objective"]}}
    (ROOT / "recovery_checks.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"verified_optima": [[e["name"], e["result"]["upper_bound"]] for e in results],
                      "round32": {k: result32[k] for k in ("outcome", "upper_bound", "lower_bound", "groups")},
                      "accepted": feasible_count, "rejected": rejected_count,
                      "fractional_rejected": fractional_rejected, "corruption_tests": len(corrupted)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="zero-based JSON instance")
    parser.add_argument("--output", type=Path, help="result JSON")
    parser.add_argument("--time-limit", type=float, default=10.)
    args = parser.parse_args()
    if args.input:
        if not math.isfinite(args.time_limit) or args.time_limit <= 0:
            parser.error("--time-limit must be positive and finite")
        result = solve_restore(json.loads(args.input.read_text()), args.time_limit)
        if args.output:
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        run_checks()
