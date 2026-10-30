"""Read-only host resource sampling and conservative admission decisions."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import time

DEFAULT_CONFIG = {
    "max_workers": 20,
    "max_total_agents": 22,
    "min_available_mib": 1024,
    "estimated_worker_mib": 512,
    "min_disk_free_gib": 5,
    "max_disk_used_fraction": 0.95,
    "max_load_per_cpu": 0.9,
    "max_cpu_percent": 90,
    "max_memory_psi_avg10": 2.0,
    "max_io_psi_avg10": 10.0,
    "max_swap_io_mib_per_second": 8.0,
    "disk_path": "/home/enok/srv_projetos",
    "max_sample_age_seconds": 30,
}


def _fields(path: Path) -> dict:
    output = {}
    for line in path.read_text().splitlines():
        parts = line.replace(":", "").split()
        if len(parts) >= 2:
            try:
                output[parts[0]] = int(parts[1])
            except ValueError:
                pass
    return output


def _psi(path: Path) -> dict | None:
    try:
        result = {}
        for line in path.read_text().splitlines():
            parts = line.split()
            result[parts[0]] = {key: float(value) for key, value in (part.split("=", 1) for part in parts[1:])}
        return result
    except (OSError, ValueError):
        return None


def sample_resources(previous: dict | None = None, disk_path: str = DEFAULT_CONFIG["disk_path"],
                     proc_root: str = "/proc") -> dict:
    """Return metrics with raw counters for the next sample; no processes stopped."""
    proc = Path(proc_root)
    now = time.time()
    monotonic = time.monotonic()
    errors = []
    try:
        memory = _fields(proc / "meminfo")
    except OSError as error:
        memory = {}
        errors.append(f"meminfo:{error.__class__.__name__}")
    try:
        vmstat = _fields(proc / "vmstat")
    except OSError as error:
        vmstat = {}
        errors.append(f"vmstat:{error.__class__.__name__}")
    try:
        counters = [int(part) for part in (proc / "stat").read_text().splitlines()[0].split()[1:]]
        cpu_total = sum(counters[:8])  # guest counters already included in user/nice
        cpu_idle = sum(counters[3:5])
    except (OSError, ValueError, IndexError) as error:
        cpu_total = cpu_idle = None
        errors.append(f"cpu:{error.__class__.__name__}")
    try:
        load1 = float((proc / "loadavg").read_text().split()[0])
        process_count = sum(path.name.isdigit() for path in proc.iterdir())
    except (OSError, ValueError, IndexError) as error:
        load1 = process_count = None
        errors.append(f"processes:{error.__class__.__name__}")
    try:
        disk = shutil.disk_usage(disk_path)
        free_gib, used_fraction = disk.free / 1024**3, disk.used / disk.total
    except OSError as error:
        free_gib = used_fraction = None
        errors.append(f"disk:{error.__class__.__name__}")
    elapsed = monotonic - previous.get("monotonic", monotonic) if previous else None
    cpu_percent = swap_rate = None
    if previous and elapsed and elapsed > 0:
        old = previous.get("raw", {})
        if cpu_total is not None and old.get("cpu_total") is not None:
            total_delta = cpu_total - old["cpu_total"]
            idle_delta = cpu_idle - old["cpu_idle"]
            if total_delta > 0 and 0 <= idle_delta <= total_delta:
                cpu_percent = 100 * (1 - idle_delta / total_delta)
        if all(key in vmstat and key in old for key in ("pswpin", "pswpout")):
            pages = vmstat["pswpin"] + vmstat["pswpout"] - old["pswpin"] - old["pswpout"]
            if pages >= 0:
                swap_rate = pages * os.sysconf("SC_PAGE_SIZE") / 1024**2 / elapsed
    cpus = os.cpu_count() or 1
    return {
        "sampled_at": now, "monotonic": monotonic, "source": "local_linux_procfs",
        "memory_available_mib": memory.get("MemAvailable", 0) / 1024 if "MemAvailable" in memory else None,
        "memory_total_mib": memory.get("MemTotal", 0) / 1024 if "MemTotal" in memory else None,
        "swap_used_mib": (memory["SwapTotal"] - memory["SwapFree"]) / 1024 if "SwapTotal" in memory and "SwapFree" in memory else None,
        "swap_total_mib": memory.get("SwapTotal", 0) / 1024 if "SwapTotal" in memory else None,
        "swap_io_mib_per_second": swap_rate,
        "cpu_percent": cpu_percent, "cpu_count": cpus, "load1": load1,
        "load_per_cpu": load1 / cpus if load1 is not None else None,
        "process_count": process_count,
        "memory_psi": _psi(proc / "pressure/memory"),
        "cpu_psi": _psi(proc / "pressure/cpu"),
        "io_psi": _psi(proc / "pressure/io"),
        "disk_free_gib": free_gib, "disk_used_fraction": used_fraction,
        "disk_path": disk_path, "errors": errors,
        "raw": {"cpu_total": cpu_total, "cpu_idle": cpu_idle,
                **{key: vmstat[key] for key in ("pswpin", "pswpout") if key in vmstat}},
    }


def host_envelope(chats, workers_per_chat=10, managers_per_chat=1):
    """Dynamic host ceiling: each registered chat adds its own workers and one manager.

    There is no permanent 20/22 cap. A third chat raises the envelope again.
    """
    chat_count = max(1, int(chats))
    per_chat = int(workers_per_chat)
    managers = chat_count * int(managers_per_chat)
    workers = chat_count * per_chat
    if per_chat <= 0 or managers < 0:
        raise ValueError("workers per chat must be positive")
    return {
        "max_workers": workers,
        "max_total_agents": workers + managers,
        "chats": chat_count,
        "workers_per_chat": per_chat,
        "managers_per_chat": int(managers_per_chat),
    }


def assess_resources(config: dict | None = None, active_workers: int = 0,
                     supervisor_active: bool = False, sample: dict | None = None,
                     now: float | None = None) -> dict:
    """Admission for one new worker. Existing tasks are never killed by this code.

    MemAvailable already reflects resident workers. Reserve is therefore applied
    once for the *new* worker, not multiplied by the existing worker count.
    Scheduler must serialize admissions and re-sample after launches.
    """
    rules = {**DEFAULT_CONFIG, **(config or {})}
    if any(rules[name] <= 0 for name in ("max_workers", "max_total_agents", "estimated_worker_mib")):
        raise ValueError("Concurrency and per-worker memory reserve must be positive")
    if rules["max_workers"] > rules["max_total_agents"]:
        raise ValueError("Worker limit cannot exceed total agent limit")
    metrics = sample if sample is not None else sample_resources(disk_path=rules["disk_path"])
    now = time.time() if now is None else now
    reasons, unknown = [], []
    if active_workers >= rules["max_workers"]:
        reasons.append("worker_limit_reached")
    if active_workers + int(supervisor_active) >= rules["max_total_agents"]:
        reasons.append("total_agent_limit_reached")
    sampled_at = metrics.get("sampled_at")
    if sampled_at is None or now - sampled_at > rules["max_sample_age_seconds"] or sampled_at > now + 5:
        reasons.append("resource_sample_missing_or_stale")
    required_memory = rules["min_available_mib"] + rules["estimated_worker_mib"]
    checks = [
        ("memory_available_mib", required_memory, "min", "insufficient_available_memory"),
        ("disk_free_gib", rules["min_disk_free_gib"], "min", "insufficient_disk_space"),
        ("disk_used_fraction", rules["max_disk_used_fraction"], "max", "disk_usage_high"),
        ("load_per_cpu", rules["max_load_per_cpu"], "max", "cpu_load_high"),
    ]
    for field, threshold, direction, reason in checks:
        value = metrics.get(field)
        if value is None:
            reasons.append(f"required_metric_unknown:{field}")
        elif (direction == "min" and value < threshold) or (direction == "max" and value > threshold):
            reasons.append(reason)
    for field, threshold, reason in [
        ("cpu_percent", rules["max_cpu_percent"], "cpu_utilization_high"),
        ("swap_io_mib_per_second", rules["max_swap_io_mib_per_second"], "swap_churn_high"),
    ]:
        if metrics.get(field) is None:
            unknown.append(field)
        elif metrics[field] > threshold:
            reasons.append(reason)
    for field, threshold, reason in [
        ("memory_psi", rules["max_memory_psi_avg10"], "memory_pressure_high"),
        ("io_psi", rules["max_io_psi_avg10"], "io_pressure_high"),
    ]:
        value = ((metrics.get(field) or {}).get("some") or {}).get("avg10")
        if value is None:
            unknown.append(field)
        elif value > threshold:
            reasons.append(reason)
    # A first sample has no rate measurement. Linux load and PSI still protect
    # it, and unknown metrics are explicit rather than represented as zero.
    return {
        "allowed": not reasons, "reasons": reasons, "metrics": metrics,
        "unknown_metrics": unknown, "worker_limit": rules["max_workers"],
        "total_agent_limit": rules["max_total_agents"],
        "required_available_mib_for_next_worker": required_memory,
        "active_workers": active_workers, "supervisor_active": supervisor_active,
        "action": "admit_one" if not reasons else "keep_queued",
    }
