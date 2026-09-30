"""The rule engine: plugin discovery, hot reload, isolated evaluation and risk aggregation.

The engine knows nothing about specific rules. It scans a directory for ``Rule``
subclasses, keeps them fresh when files change on disk, and fuses whatever they
report into a single 0-100 risk score.
"""
import importlib.util
import inspect
import logging
import sys
import threading
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from .base import Rule, RuleContext, Txn

log = logging.getLogger("aegis.engine")


@dataclass
class Hit:
    rule_id: str
    rule_name: str
    score: float
    weight: float
    contribution: float
    reason: str
    evidence: dict


@dataclass
class Evaluation:
    score: float                      # 0..100
    level: str                        # low | medium | high | critical
    flagged: bool
    alert: bool
    hits: List[Hit] = field(default_factory=list)
    rules_run: int = 0
    errors: List[dict] = field(default_factory=list)
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LoadedRule:
    cls: type
    file: str
    loaded_at: float
    enabled: bool = True
    weight: float = 1.0
    overrides: Dict[str, float] = field(default_factory=dict)
    evaluations: int = 0
    hits: int = 0
    errors: int = 0
    total_ms: float = 0.0
    last_error: str = ""
    instance: Optional[Rule] = None

    def build(self) -> None:
        self.instance = self.cls(self.overrides)


class RuleEngine:
    def __init__(self, rules_dir: Path, flag_threshold: float = 35, alert_threshold: float = 80):
        self.rules_dir = Path(rules_dir)
        self.flag_threshold = flag_threshold
        self.alert_threshold = alert_threshold
        self.rules: Dict[str, LoadedRule] = {}
        self.load_errors: Dict[str, str] = {}
        self.persisted: Dict[str, dict] = {}   # rule_id -> {enabled, weight, params}
        self._mtimes: Dict[str, float] = {}
        self._lock = threading.RLock()
        self.version = 0

    # ------------------------------------------------------------------ discovery
    def _scan(self) -> Dict[str, float]:
        return {str(p): p.stat().st_mtime for p in sorted(self.rules_dir.glob("*.py"))
                if not p.name.startswith("_")}

    def reload_if_changed(self) -> Optional[dict]:
        """Called periodically. Returns a change summary when the rules folder changed."""
        current = self._scan()
        if current == self._mtimes:
            return None
        return self.load_all(current)

    def load_all(self, snapshot: Optional[Dict[str, float]] = None) -> dict:
        snapshot = snapshot if snapshot is not None else self._scan()
        found: Dict[str, LoadedRule] = {}
        errors: Dict[str, str] = {}
        for path_str, mtime in snapshot.items():
            path = Path(path_str)
            try:
                for cls in self._load_module(path, mtime):
                    if cls.id in found:
                        raise ValueError(f"duplicate rule id '{cls.id}' (also in {Path(found[cls.id].file).name})")
                    prev = self.rules.get(cls.id)
                    lr = LoadedRule(cls=cls, file=path.name, loaded_at=time.time(),
                                    weight=cls.default_weight)
                    if prev:  # keep live stats across reloads
                        lr.evaluations, lr.hits, lr.errors, lr.total_ms = prev.evaluations, prev.hits, prev.errors, prev.total_ms
                    self._apply_persisted(lr)
                    lr.build()
                    found[cls.id] = lr
            except Exception as exc:  # a broken plugin never takes the engine down
                errors[path.name] = f"{type(exc).__name__}: {exc}"
                log.warning("rule file %s failed to load:\n%s", path.name, traceback.format_exc())
        with self._lock:
            before = set(self.rules)
            self.rules = found
            self.load_errors = errors
            self._mtimes = snapshot
            self.version += 1
        added, removed = sorted(set(found) - before), sorted(before - set(found))
        log.info("rules loaded: %s (added=%s removed=%s errors=%s)", sorted(found), added, removed, list(errors))
        return {"added": added, "removed": removed, "errors": errors, "active": sorted(found)}

    def _load_module(self, path: Path, mtime: float) -> List[type]:
        mod_name = f"aegis_rules.{path.stem}_{int(mtime * 1000)}"
        spec = importlib.util.spec_from_file_location(mod_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        classes = []
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Rule) and obj is not Rule and obj.__module__ == mod_name and not inspect.isabstract(obj):
                if not obj.id:
                    raise ValueError(f"{obj.__name__} must define a non-empty `id`")
                classes.append(obj)
        return classes

    # ------------------------------------------------------------------ config
    def _apply_persisted(self, lr: LoadedRule) -> None:
        cfg = self.persisted.get(lr.cls.id, {})
        lr.enabled = cfg.get("enabled", True)
        lr.weight = float(cfg.get("weight", lr.cls.default_weight))
        lr.overrides = {k: v for k, v in cfg.get("params", {}).items() if k in lr.cls.params}

    def configure(self, rule_id: str, enabled: Optional[bool] = None, weight: Optional[float] = None,
                  params: Optional[Dict[str, float]] = None) -> dict:
        with self._lock:
            lr = self.rules[rule_id]
            cfg = self.persisted.setdefault(rule_id, {})
            if enabled is not None:
                cfg["enabled"] = bool(enabled)
            if weight is not None:
                cfg["weight"] = max(0.0, min(3.0, float(weight)))
            if params:
                merged = {**cfg.get("params", {})}
                for k, v in params.items():
                    if k not in lr.cls.params:
                        raise KeyError(f"unknown param '{k}' for rule {rule_id}")
                    merged[k] = float(v)
                cfg["params"] = merged
            self._apply_persisted(lr)
            lr.build()
            self.version += 1
            return self.describe_rule(rule_id)

    # ------------------------------------------------------------------ evaluation
    def evaluate(self, txn: Txn, history: Iterable[Txn], only: Optional[Callable[[str], bool]] = None) -> Evaluation:
        t0 = time.perf_counter()
        ctx = RuleContext(txn, history)
        hits: List[Hit] = []
        errors: List[dict] = []
        with self._lock:
            active = [lr for lr in self.rules.values() if lr.enabled and (only is None or only(lr.cls.id))]
        for lr in active:
            r0 = time.perf_counter()
            try:
                res = lr.instance.evaluate(txn, ctx)
                lr.evaluations += 1
                if res is not None and res.score > 0:
                    lr.hits += 1
                    contribution = min(1.0, res.score * lr.weight)
                    hits.append(Hit(lr.cls.id, lr.cls.name, round(res.score, 4), lr.weight,
                                    round(contribution, 4), res.reason, _jsonable(res.evidence)))
            except Exception as exc:  # isolate misbehaving rules
                lr.errors += 1
                lr.last_error = f"{type(exc).__name__}: {exc}"
                errors.append({"rule_id": lr.cls.id, "error": lr.last_error})
            finally:
                lr.total_ms += (time.perf_counter() - r0) * 1000

        score = self.fuse(hits)
        hits.sort(key=lambda h: h.contribution, reverse=True)
        return Evaluation(score=score, level=self.level(score), flagged=score >= self.flag_threshold,
                          alert=score >= self.alert_threshold, hits=hits, rules_run=len(active),
                          errors=errors, latency_ms=round((time.perf_counter() - t0) * 1000, 3))

    @staticmethod
    def fuse(hits: List[Hit]) -> float:
        """Noisy-OR fusion: independent signals reinforce each other but never exceed 100.

        risk = 1 - prod(1 - contribution_i). One strong signal is enough to flag; several
        weak ones together also add up - which is exactly how human investigators think.
        """
        safe = 1.0
        for h in hits:
            safe *= (1.0 - h.contribution)
        return round((1.0 - safe) * 100, 2)

    def level(self, score: float) -> str:
        if score >= self.alert_threshold:
            return "critical"
        if score >= self.flag_threshold + (self.alert_threshold - self.flag_threshold) / 2:
            return "high"
        if score >= self.flag_threshold:
            return "medium"
        return "low"

    # ------------------------------------------------------------------ introspection
    def describe_rule(self, rule_id: str) -> dict:
        lr = self.rules[rule_id]
        c = lr.cls
        return {
            "id": c.id, "name": c.name, "description": c.description, "category": c.category,
            "file": lr.file, "enabled": lr.enabled, "weight": lr.weight, "default_weight": c.default_weight,
            "params": lr.instance.p, "default_params": dict(c.params), "param_help": dict(c.param_help),
            "stats": {"evaluations": lr.evaluations, "hits": lr.hits, "errors": lr.errors,
                      "avg_ms": round(lr.total_ms / lr.evaluations, 4) if lr.evaluations else 0.0,
                      "hit_rate": round(lr.hits / lr.evaluations, 4) if lr.evaluations else 0.0,
                      "last_error": lr.last_error},
            "loaded_at": lr.loaded_at,
            "source": inspect.getsource(c) if _source_ok(c) else "",
        }

    def describe(self) -> dict:
        with self._lock:
            return {"version": self.version, "rules": [self.describe_rule(r) for r in sorted(self.rules)],
                    "load_errors": self.load_errors, "rules_dir": _display_path(self.rules_dir),
                    "thresholds": {"flag": self.flag_threshold, "alert": self.alert_threshold}}


def _display_path(p: Path) -> str:
    """Show the rules folder relative to the project root when possible."""
    try:
        return str(Path(p).resolve().relative_to(Path(__file__).resolve().parents[3])) + "/"
    except ValueError:
        return str(p)


def _source_ok(cls) -> bool:
    try:
        inspect.getsource(cls)
        return True
    except (OSError, TypeError):
        return False


def _jsonable(v):
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_jsonable(x) for x in v]
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, (int, str, bool)) or v is None:
        return v
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)
