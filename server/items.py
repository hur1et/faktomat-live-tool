"""
Item-Loader und -Validator – Faktomat Live.

Lädt die Itemliste (items.json) beim Serverstart und prüft sie gegen das
in UEBERGABE Abschnitt 5 festgelegte Schema. Verstöße führen zum sofortigen
Startabbruch mit klarer Fehlermeldung (fail-loud) – ein Live-Event darf nicht
mit stillschweigend falschen Items starten.

Design-Constraints (Ground Truth = items.json, Codebook Interventionsstudie):
  - genau 24 Items,
  - 12 je Task ("left" / "right")  -> b′ = z(right/12) − z(left/12) hängt daran,
  - jede Task enthält beide truth_values (sonst ist d′/b′ nicht berechenbar),
  - jedes Item: id, text, truth_value(bool), task(left|right), domain(str).

Hinweis: Das Übergabedokument sprach ursprünglich von 6/6-Balance je Zelle
(task × truth_value). Die reale Itemliste ist 14 wahr / 10 falsch – das ist die
akzeptierte Ground Truth. Der Validator erzwingt daher NICHT mehr 6/6, sondern
nur die für das Scoring notwendigen Bedingungen (12/Task, beide truth_values je
Task). Das Scoring selbst zählt die Zellen ohnehin dynamisch, nicht hart auf 12.

Keine Rohdaten im Repo: die echte items.json wird separat abgelegt und ist
via .gitignore ausgeschlossen, bis die Lizenzfrage geklärt ist (UEBERGABE 2, A).
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Task = Literal["left", "right"]

# Erwartete Struktur (Ground Truth): 24 Items, 12/Task.
# KEINE feste Zellbalance mehr – die reale Liste ist 14 wahr / 10 falsch.
EXPECTED_TOTAL = 24
EXPECTED_PER_TASK = 12


class ItemValidationError(Exception):
    """Ausgelöst, wenn die Itemliste das Schema verletzt. Bricht den Start ab."""


@dataclass(frozen=True)
class Item:
    """Ein IBE-Item. truth_value und task sind für das Scoring maßgeblich."""

    id: str
    text: str
    truth_value: bool
    task: Task
    domain: str


@dataclass(frozen=True)
class ItemSet:
    """Validierte, unveränderliche Itemliste plus Metadaten."""

    version: str
    source: str
    items: tuple[Item, ...]


def _require(condition: bool, message: str) -> None:
    """Wirft ItemValidationError mit klarer Meldung, wenn condition falsch ist."""
    if not condition:
        raise ItemValidationError(message)


def _parse_item(raw: dict, index: int) -> Item:
    """Prüft ein einzelnes Roh-Item und gibt ein typisiertes Item zurück."""
    where = f"Item #{index}"
    for field in ("id", "text", "truth_value", "task", "domain"):
        _require(field in raw, f"{where}: Feld '{field}' fehlt.")

    _require(isinstance(raw["id"], str) and raw["id"].strip() != "",
             f"{where}: 'id' muss ein nicht-leerer String sein.")
    _require(isinstance(raw["text"], str) and raw["text"].strip() != "",
             f"{where} ({raw['id']}): 'text' muss ein nicht-leerer String sein.")
    _require(isinstance(raw["truth_value"], bool),
             f"{where} ({raw['id']}): 'truth_value' muss true/false sein.")
    _require(raw["task"] in ("left", "right"),
             f"{where} ({raw['id']}): 'task' muss 'left' oder 'right' sein, war {raw['task']!r}.")
    _require(isinstance(raw["domain"], str) and raw["domain"].strip() != "",
             f"{where} ({raw['id']}): 'domain' muss ein nicht-leerer String sein.")

    return Item(
        id=raw["id"],
        text=raw["text"],
        truth_value=raw["truth_value"],
        task=raw["task"],
        domain=raw["domain"],
    )


def validate_items(items: list[Item]) -> None:
    """
    Prüft die für das Scoring notwendigen Constraints gegen die Ground Truth.

    Erzwungen: 24 Items, eindeutige IDs, 12 je Task, und je Task beide
    truth_values vorhanden. NICHT erzwungen: 6/6-Zellbalance (die reale Liste
    ist 14 wahr / 10 falsch – akzeptierte Ground Truth).

    Wirft ItemValidationError bei jedem Verstoß.
    """
    _require(len(items) == EXPECTED_TOTAL,
             f"Erwarte {EXPECTED_TOTAL} Items, gefunden {len(items)}.")

    ids = [it.id for it in items]
    duplicates = [i for i, c in Counter(ids).items() if c > 1]
    _require(not duplicates, f"Doppelte Item-IDs: {duplicates}.")

    per_task = Counter(it.task for it in items)
    _require(per_task["left"] == EXPECTED_PER_TASK and per_task["right"] == EXPECTED_PER_TASK,
             f"Erwarte je {EXPECTED_PER_TASK} Items pro Task, "
             f"gefunden left={per_task['left']}, right={per_task['right']}.")

    # Jede Task muss beide truth_values enthalten, sonst ist d′/b′ nicht
    # berechenbar (z einer Rate von 0 oder 1 ist auch mit Hautus wackelig,
    # eine leere Zelle wäre inhaltlich sinnlos).
    per_cell = Counter((it.task, it.truth_value) for it in items)
    for task in ("left", "right"):
        for truth in (True, False):
            _require(per_cell[(task, truth)] >= 1,
                     f"Zelle task={task}, truth_value={truth} ist leer – "
                     f"d′/b′ nicht berechenbar.")


def load_items(path: str | Path) -> ItemSet:
    """
    Lädt und validiert items.json. Wirft ItemValidationError bei jedem Verstoß
    (Datei fehlt, kein JSON, Schema- oder Balance-Verletzung).
    """
    p = Path(path)
    _require(p.is_file(), f"Itemdatei nicht gefunden: {p}")

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ItemValidationError(f"items.json ist kein gültiges JSON: {exc}") from exc

    _require(isinstance(raw, dict), "items.json muss ein JSON-Objekt sein.")
    _require("items" in raw and isinstance(raw["items"], list),
             "items.json braucht ein 'items'-Array.")

    items = [_parse_item(entry, i) for i, entry in enumerate(raw["items"])]
    validate_items(items)

    return ItemSet(
        version=str(raw.get("version", "unknown")),
        source=str(raw.get("source", "unknown")),
        items=tuple(items),
    )
