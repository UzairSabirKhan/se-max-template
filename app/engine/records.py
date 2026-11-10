"""save_records, the pure part: compare this run's items with the stored records (A15, A24; FR-29, FR-30).

Labels every item new / changed / same / suspect, finds removed items, and decides the run's verdict
when the page itself was healthy: CHANGED, OK, SUSPECT, or BROKEN when too many items vanished.
No I/O here; app/db/records.py stores the result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.engine.extract import Item

MAX_REMOVED = 0.20          # 20% or more of the stored items vanishing means the page broke, not a sale
SMALL_LIST = 5
SUSPECT_MOVE_PCT = Decimal(50)


@dataclass
class Labelled:
    item: Item
    change: str                                   # new | changed | same | suspect
    previous: dict[str, Any] = field(default_factory=dict)
    pct_change: dict[str, float] = field(default_factory=dict)
    changed_fields: list[str] = field(default_factory=list)

    def as_report(self) -> dict[str, Any]:
        out = self.item.as_report()
        out["change"] = self.change
        if self.previous:
            out["previous"] = self.previous
        if self.pct_change:
            out["pct_change"] = self.pct_change
        return out


@dataclass
class Diff:
    labelled: list[Labelled]
    removed: list[str]                            # identity keys that vanished
    verdict: str                                  # CHANGED | OK | SUSPECT | BROKEN
    reason: str
    evidence: list[str] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "new": sum(1 for x in self.labelled if x.change == "new"),
            "changed": sum(1 for x in self.labelled if x.change == "changed"),
            "removed": len(self.removed),
        }


def _number(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def diff_records(items: list[Item], stored: dict[str, dict[str, Any]], tracked: list[str]) -> Diff:
    """`stored`: identity key -> data of the records currently stored (not removed)."""
    labelled: list[Labelled] = []
    seen: set[str] = set()
    for item in items:
        if item.key is None:
            continue
        seen.add(item.key)
        if item.error:  # its page failed this time (loop on_error=skip): keep it, don't judge it
            labelled.append(Labelled(item, "same"))
            continue
        old = stored.get(item.key)
        if old is None:
            labelled.append(Labelled(item, "new"))
            continue
        changed, previous, pct = [], {}, {}
        suspect = False
        for name in tracked:
            before, after = old.get(name), item.data.get(name)
            if before == after:
                continue
            changed.append(name)
            previous[name] = before
            b, a = _number(before), _number(after)
            if b is not None and a is not None and b != 0:
                move = (a - b) / b * 100
                pct[name] = float(round(move, 2))
                if abs(move) > SUSPECT_MOVE_PCT:
                    suspect = True
        labelled.append(Labelled(item, "suspect" if suspect else ("changed" if changed else "same"),
                                 previous, pct, changed))

    removed = [k for k in stored if k not in seen]
    first_run = not stored
    if stored:
        too_many = (len(removed) >= 2 or len(removed) == len(stored)) if len(stored) < SMALL_LIST \
            else len(removed) / len(stored) >= MAX_REMOVED
        if removed and too_many:
            return Diff(labelled, removed, "BROKEN",
                        f"{len(removed)} of {len(stored)} stored items vanished at once: the page likely broke",
                        [f"missing: {k}" for k in removed[:5]])

    suspects = [x for x in labelled if x.change == "suspect"]
    if suspects:
        names = ", ".join(str(x.item.data.get("title") or x.item.key) for x in suspects[:3])
        return Diff(labelled, removed, "SUSPECT",
                    f"{len(suspects)} value(s) moved more than 50%: held for you to confirm ({names})")
    counts = {c: sum(1 for x in labelled if x.change == c) for c in ("new", "changed")}
    if first_run:
        return Diff(labelled, removed, "CHANGED" if labelled else "OK",
                    f"First run: {len(labelled)} items saved as the starting point")
    if counts["new"] or counts["changed"] or removed:
        parts = [f"{counts['changed']} changed" if counts["changed"] else "",
                 f"{counts['new']} new" if counts["new"] else "", f"{len(removed)} removed" if removed else ""]
        return Diff(labelled, removed, "CHANGED", ", ".join(p for p in parts if p))
    return Diff(labelled, removed, "OK", "No changes since the last run")
