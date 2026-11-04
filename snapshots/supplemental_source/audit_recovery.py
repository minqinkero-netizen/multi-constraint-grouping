"""Read saved records and write a separate recovery ledger; never run a solver."""
from pathlib import Path
from collections import Counter
import csv
import datetime
import hashlib
import importlib.util
import json
import math
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
CODE = ROOT / "code"
OUT = ROOT / "audit"
OUT.mkdir(exist_ok=True)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


spec = importlib.util.spec_from_file_location("recovery_independent_check", CODE / "independent_check.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
protocol = read(CODE / "protocol.json")
manifest = read(CODE / "data/input_manifest.json")
core = ["benchmark.py", "solver_backend.py", "round_repair.py", "grouping_core.py"]
implementation_sha = hashlib.sha256("".join(sha(CODE / f) for f in core).encode()).hexdigest()
protocol_sha = sha(CODE / "protocol.json")
methods = protocol["main_methods"]
assert len(manifest) == 18 and len(methods) == 5

ledger, witnesses, lp_checks, missing, errors, recovered = [], [], [], [], [], []
finished = {}
for rec in manifest:
    name = rec["name"]
    folder = CODE / "data" / name
    instance = read(folder / "instance.json")
    assert instance == rec["input"], name
    assert [instance["n"], instance["m"], len(instance["targets"])] == rec["config"]
    witness = checker.check_labels(instance, read(folder / "witness.json")["labels"])
    assert witness["H"] == 0
    witnesses.append({"instance": name, "checked": True, "L": witness["L"]})
    expected_key = {"input_sha256": sha(folder / "instance.json"),
                    "implementation_sha256": implementation_sha,
                    "protocol_sha256": protocol_sha}
    recovered_rec = {k: rec[k] for k in ["name", "config", "family", "replicate", "seed"]}
    recovered_rec["input"] = instance
    recovered_rec["results"] = {}
    for method in methods:
        path = folder / (method + ".json")
        row = {"instance": name, "method": method, "input_seed": rec["seed"],
               "algorithm_seed": rec["seed"] + 70000,
               "path": str(path.relative_to(ROOT)), "budget_seconds": 600,
               "state": "absent", "checked": False}
        if not path.exists():
            missing.append({**row, "reason": "No standalone result file"})
            ledger.append(row)
            continue
        result = read(path)
        row.update(sha256=sha(path), status=result.get("status"),
                   total_seconds=result.get("total_seconds"), feasible=result.get("feasible"),
                   L=result.get("L"), H=result.get("H"))
        if "total_seconds" not in result:
            row["state"] = "interrupted_checkpoint"
            missing.append({**row, "reason": "No parent termination/timing or run_key; not a completed run"})
            ledger.append(row)
            continue
        row["state"] = "ended"
        try:
            assert result["run_key"] == expected_key, "run_key mismatch"
            assert result["method"] == method and result["seed"] == rec["seed"] + 70000
            assert result["version"] == protocol["version"]
            assert result["budget"] == result["end_to_end_limit"] == 600
            assert result["reserve_seconds"] == 30
            assert math.isfinite(result["total_seconds"]) and result["total_seconds"] >= 0
            assert "watchdog_timeout" in result and "process_error" in result
            assert result.get("solver_status") not in ["kInfeasible", "kUnboundedOrInfeasible"]
            count_bound = sum(max(len(targets) - instance["m"], 0)
                              for t, targets in enumerate(instance["targets"]) if t not in instance["strict"])
            assert result["count_bound"] == count_bound
            check = checker.audit_result(instance, result)
            if result.get("lower_bound") is not None:
                assert result["lower_bound"] <= witness["L"] + 2e-6
            if result["status"] == "optimal":
                assert result["feasible"] and abs(result["lower_bound"] - result["L"]) < 1e-5
            if "lp_rows" in result:
                lp_checks.append({"instance": name, "method": method,
                                  **checker.audit_lp(instance, checker.unpack_lp(instance, result), result["lp_objective"])})
            row.update(checked=True, **{k: check[k] for k in ["feasible", "L", "H"]})
            finished[(name, method)] = result
            recovered_rec["results"][method] = result
        except Exception as exc:
            row["state"] = "audit_failed"
            row["error"] = type(exc).__name__ + ": " + str(exc)
            errors.append(dict(row))
        ledger.append(row)
    if all((name, m) in finished for m in ["G", "LS"]):
        g, ls = (finished[(name, m)] for m in ["G", "LS"])
        if g.get("first_constructed_labels") is not None and ls.get("first_constructed_labels") is not None:
            assert g["first_constructed_labels"] == ls["first_constructed_labels"], name
    recovered.append(recovered_rec)

aggregated = read(CODE / "data/results.json")
aggregate_rows = [(rec["name"], method, result) for rec in aggregated["instances"]
                  for method, result in rec["results"].items()]
aggregate_mismatches = []
for name, method, result in aggregate_rows:
    if finished.get((name, method)) != result:
        aggregate_mismatches.append({"instance": name, "method": method})
aggregate_keys = {(name, method) for name, method, _ in aggregate_rows}
unaggregated = [{"instance": name, "method": method} for name, method in finished if (name, method) not in aggregate_keys]

archive = []
for path in sorted((ROOT / "qa").rglob("*.json")):
    result = read(path)
    archive.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path),
                    "has_end_record": "total_seconds" in result,
                    "has_run_key": "run_key" in result, "status": result.get("status"),
                    "candidate_feasible": result.get("feasible")})

summary = {
    "audited_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "solver_runs_started": 0, "protocol_version": protocol["version"],
    "implementation_sha256": implementation_sha, "protocol_sha256": protocol_sha,
    "expected_main_runs": 90, "ended_standalone_records": sum(r["state"] in ["ended", "audit_failed"] for r in ledger),
    "verified_completed_runs": len(finished), "remaining_main_runs": len(missing) + len(errors),
    "completed_by_method": dict(Counter(m for name, m in finished)),
    "feasible_by_method": dict(Counter(m for (name, m), r in finished.items() if r["feasible"])),
    "status_counts": dict(Counter(r["status"] for r in finished.values())),
    "witness_checks": witnesses, "lp_checks": lp_checks, "audit_errors": errors,
    "aggregate_record_count": len(aggregate_rows), "aggregate_complete_flag": aggregated["complete"],
    "aggregate_mismatches": aggregate_mismatches, "completed_not_in_aggregate": unaggregated,
    "archived_attempts": archive, "missing_or_interrupted": missing,
    "extra_results_present": (CODE / "extra").exists(),
    "scenario_results_present": (CODE / "scenario_data").exists(),
    "complete": len(finished) == 90,
}
assert not aggregate_mismatches, aggregate_mismatches
assert not errors, errors
assert not any(a["has_end_record"] for a in archive), "Review archived completed candidates"
(OUT / "recovery_audit.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
(OUT / "remaining_main.json").write_text(json.dumps(missing, ensure_ascii=False, indent=2) + "\n")
(OUT / "recovered_results.json").write_text(json.dumps({"protocol": read(CODE / "data/protocol.json"),
    "instances": recovered, "complete": summary["complete"], "recovery_note": "Rebuilt from verified standalone records; original aggregate retained unchanged"}, ensure_ascii=False) + "\n")
fields = list(dict.fromkeys(k for row in ledger for k in row))
with (OUT / "main_run_ledger.csv").open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(ledger)
print(json.dumps({k: summary[k] for k in ["expected_main_runs", "verified_completed_runs", "remaining_main_runs", "completed_by_method", "feasible_by_method", "aggregate_record_count", "completed_not_in_aggregate", "audit_errors"]}))
