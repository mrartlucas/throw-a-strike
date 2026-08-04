#!/usr/bin/env python3
"""Statically inventory the locked pydartsnut wheel; never import wheel code."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from email.parser import BytesParser
from pathlib import Path
import sys
import zipfile

SCHEMA_VERSION = 1
PACKAGE = "pydartsnut"
VERSION = "1.2.1"
SDIST_SHA256 = "f3618dc311e77773f6e655b11cb448e94940c59af32ad060e77a9ed616583d8e"
SEARCH_TERMS = ["aux_display", "auxiliary", "control_screen", "dual_display", "lcd",
                "scoreboard", "second_display", "secondary", "touch_screen", "widget_display"]


class InspectionError(ValueError):
    pass


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = node.args
    values = [a.arg for a in args.posonlyargs + args.args]
    defaults = [None] * (len(values) - len(args.defaults)) + args.defaults
    rendered = []
    for name, default in zip(values, defaults):
        rendered.append(name if default is None else f"{name}={ast.unparse(default)}")
    if args.vararg:
        rendered.append("*" + args.vararg.arg)
    elif args.kwonlyargs:
        rendered.append("*")
    for item, default in zip(args.kwonlyargs, args.kw_defaults):
        rendered.append(item.arg if default is None else f"{item.arg}={ast.unparse(default)}")
    if args.kwarg:
        rendered.append("**" + args.kwarg.arg)
    return "(" + ", ".join(rendered) + ")"


def inspect_wheel(path: Path, expected_sha256: str) -> dict:
    if path.suffix != ".whl" or not path.is_file():
        raise InspectionError("input must be an existing .whl file")
    raw = path.read_bytes()  # Hash before opening the archive.
    actual = _digest(raw)
    if actual.lower() != expected_sha256.lower():
        raise InspectionError(f"wheel SHA-256 mismatch: expected {expected_sha256}, got {actual}")
    with zipfile.ZipFile(path) as wheel:
        names = sorted(wheel.namelist())
        metadata_paths = [n for n in names if n.endswith(".dist-info/METADATA")]
        record_paths = [n for n in names if n.endswith(".dist-info/RECORD")]
        if len(metadata_paths) != 1 or len(record_paths) != 1:
            raise InspectionError("wheel must contain exactly one METADATA and RECORD")
        metadata_raw = wheel.read(metadata_paths[0])
        metadata = BytesParser().parsebytes(metadata_raw)
        if metadata.get("Name", "").lower().replace("_", "-") != PACKAGE:
            raise InspectionError("wheel package name is not pydartsnut")
        if metadata.get("Version") != VERSION:
            raise InspectionError("wheel package version is not 1.2.1")
        source_paths = sorted(n for n in names if n.startswith("pydartsnut/") and n.endswith(".py"))
        if not source_paths:
            raise InspectionError("no pydartsnut Python package source found")
        sources = {n: wheel.read(n) for n in source_paths}
        records = sorted(line for line in wheel.read(record_paths[0]).decode().splitlines() if line)

    evidence, classes, methods, matches = [], [], [], []
    def add(level: str, archive: str, symbol: str, start: int, end: int, method: str) -> str:
        eid = f"E{len(evidence)+1:03d}"
        evidence.append({"evidence_id": eid, "evidence_level": level,
                         "archive_path": archive, "source_sha256": _digest(sources[archive]) if archive in sources else _digest(metadata_raw),
                         "symbol": symbol, "line_start": start, "line_end": end,
                         "extraction_method": method})
        return eid
    metadata_eid = add("VERIFIED_PACKAGE_METADATA", metadata_paths[0], "METADATA", 1,
                       len(metadata_raw.decode(errors="replace").splitlines()), "email.parser")
    method_eids = {}
    for archive, data in sources.items():
        text = data.decode("utf-8")
        tree = ast.parse(text, filename=archive)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                eid = add("VERIFIED_PACKAGE_SOURCE", archive, node.name, node.lineno, node.end_lineno or node.lineno, "ast.ClassDef")
                classes.append({"name": node.name, "archive_path": archive, "line_start": node.lineno, "line_end": node.end_lineno, "evidence_ids": [eid]})
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and (child.name == "__init__" or not child.name.startswith("_")):
                        symbol = f"{node.name}.{child.name}"
                        meid = add("VERIFIED_PACKAGE_SOURCE", archive, symbol, child.lineno, child.end_lineno or child.lineno, "ast.FunctionDef")
                        method_eids[symbol] = meid
                        methods.append({"symbol": symbol, "signature": _signature(child), "archive_path": archive,
                                        "line_start": child.lineno, "line_end": child.end_lineno, "evidence_ids": [meid]})
        lowered = text.lower()
        for term in SEARCH_TERMS:
            if term in lowered:
                for number, line in enumerate(text.splitlines(), 1):
                    if term in line.lower():
                        matches.append({"term": term, "archive_path": archive, "line": number})
    classes.sort(key=lambda x: (x["archive_path"], x["line_start"], x["name"]))
    methods.sort(key=lambda x: (x["archive_path"], x["line_start"], x["symbol"]))
    matches.sort(key=lambda x: (x["term"], x["archive_path"], x["line"]))
    def ids(*symbols: str) -> list[str]: return [method_eids[s] for s in symbols if s in method_eids]

    unknown_topics = [
        ("physical-display-size", "Physical display width and height on every supported cabinet", True, True, False),
        ("hardware-channel-order", "RGB channel order on actual hardware", True, True, False),
        ("stride", "Framebuffer stride", True, True, False), ("refresh-limit", "Display refresh limit", True, True, False),
        ("safe-update-rate", "Safe update rate", True, True, False), ("dropped-frames", "Dropped-frame behavior", True, True, False),
        ("axis-orientation", "Physical x/y orientation", True, True, True), ("calibration", "Coordinate calibration", True, False, True),
        ("dead-zones", "Coordinate dead zones", False, False, True), ("jitter", "Coordinate jitter", False, False, True),
        ("simultaneous-load", "Simultaneous-hit behavior under real hardware load", False, False, True),
        ("dart-color-map", "Dart-index to Blue/Red/Green/Yellow mapping", True, False, True),
        ("dart-index-stability", "Dart-index stability across boots and replacements", True, False, True),
        ("wrong-dart", "Multiplayer wrong-dart behavior", False, False, True),
        ("secondary-outside-package", "Secondary-display API outside this package", True, True, True),
        ("touch", "Touch-screen behavior", False, False, False), ("button-placement", "Physical button placement", False, False, False),
        ("audio", "Cabinet audio routing", False, False, False), ("emulator", "Emulator behavior", True, True, True),
        ("packaging", "Packaging and installation format", True, False, False), ("launcher", "Launcher lifecycle", True, False, False),
        ("store-retention", "Data-store quota and retention", False, False, False),
        ("compatibility", "Cabinet and firmware compatibility", True, True, True), ("performance", "Performance budgets", False, True, False),
    ]
    unknowns = [{"unknown_id": f"U{i:03d}", "question": q, "current_status": "UNKNOWN_HARDWARE",
                 "why_package_source_is_insufficient": "The wheel describes a client API, not cabinet, firmware, launcher, or operational guarantees.",
                 "verification_method": "Verify with current operator documentation, emulator traces, and recorded physical-cabinet testing.",
                 "blocks_adapter": ba, "blocks_rendering": br, "blocks_multiplayer": bm}
                for i, (_, q, ba, br, bm) in enumerate(unknown_topics, 1)]
    no_secondary = not matches
    result = {
      "schema_version": 1,
      "package": {"name": PACKAGE, "version": VERSION, "wheel_filename": path.name, "wheel_sha256": actual,
        "sdist_sha256": SDIST_SHA256, "wheel_size": len(raw), "metadata_name": metadata.get("Name"),
        "metadata_version": metadata.get("Version"), "python_requirement": metadata.get("Requires-Python"),
        "license": metadata.get("License"), "source_files_inspected": [{"archive_path": n, "sha256": _digest(sources[n])} for n in source_paths],
        "evidence_ids": [metadata_eid]},
      "inspection": {"inspector_schema_version": SCHEMA_VERSION, "deterministic_generation": True, "ast_only": True,
        "package_execution": False, "hardware_access": False, "record_entries": records,
        "public_classes": classes, "public_methods": methods},
      "constructor": {"public_class_import_path": "pydartsnut.Dartsnut", "signature": "(self)",
        "arguments": {"--params": "{}", "--shm": "pdishm", "--data-store": None, "--min-active-duration": None, "--idle-unblock-duration": None},
        "behavior": "Parses process arguments, JSON-decodes widget parameters, installs SIGINT handling, connects display/input shared memory, and initializes data storage and InputHandler.", "evidence_ids": ids("Dartsnut.__init__")},
      "main_display": {"method": "update_frame_buffer", "signature": "(self, frame)",
        "accepted_input_categories": ["bytearray", "object with tobytes attribute"], "image_mode_handling": "No conversion or mode validation",
        "encoded_width": None, "encoded_height": None, "channel_count": 3, "pixel_format": "RGB888 (documented by package source)", "expected_byte_length": None,
        "busy_state": "status byte 2 returns False", "ready_state": "status byte 1 copies bytes, sets status 0, posts semaphore, returns True",
        "invalid_state": "other status values return False", "return_type": "bool", "brightness_interaction": "none in this method", "evidence_ids": ids("Dartsnut.update_frame_buffer")},
      "dart_input": {"methods": {m.split(".")[-1]: next((x["signature"] for x in methods if x["symbol"] == m), None) for m in ["Dartsnut.get_darts","Dartsnut.get_dart_hits","Dartsnut.get_active_darts","Dartsnut.reset_blocking_state"]},
        "polling_shape": "12 entries of [x, y]", "event_shape": "list of (dart_index, x, y) tuples", "active_shape": "list of (dart_index, x, y) tuples",
        "dart_slot_count": 12, "invalid_sentinels": [[-1,-1],[0,0]], "coordinate_min": 0, "coordinate_max": 127, "dart_index_min": 0, "dart_index_max": 11,
        "duplicate_blocking": "An emitted index is blocked until invalid continuously for the configured interval", "default_rearm_seconds": 0.2,
        "simultaneous_hits": "Source iterates all 12 slots in index order", "hardware_guarantee": "UNKNOWN_HARDWARE", "evidence_ids": ids("Dartsnut.get_darts","Dartsnut.get_dart_hits","Dartsnut.get_active_darts","Dartsnut.reset_blocking_state","InputHandler.get_dart_hits")},
      "button_input": {"methods": {"get_buttons": "(self)", "get_button_events": "(self)"}, "keys": ["btn_a","btn_b","btn_down","btn_home","btn_left","btn_reserved","btn_right","btn_up"],
        "polling_semantics": "debounced current booleans", "event_semantics": "rising-edge booleans for keys returned by polling", "debounce_seconds": 0.03,
        "default_values": False, "unknown_keys_possible": "Event handler follows polling mapping; package polling defines exactly eight keys", "ordering_guarantee": None,
        "evidence_ids": ids("Dartsnut.get_buttons","Dartsnut.get_button_events","InputHandler.get_buttons")},
      "lifecycle": {"running_initial": True, "sigint_behavior": "sets running False", "missing_shared_memory": "prints message and exits with status 1",
        "cleanup": "close closes render semaphore; destructor calls close", "application_loop": None, "evidence_ids": ids("Dartsnut.sigint_handler","Dartsnut.close") + ids("Dartsnut.__init__")},
      "brightness": {"method": "set_brightness", "signature": "(self, brightness)", "accepted_range": [10,100], "out_of_range": "ignored", "return": None,
        "hardware_effect": "UNKNOWN_HARDWARE", "evidence_ids": ids("Dartsnut.set_brightness")},
      "widget_parameters": {"attribute": "widget_params", "source": "--params JSON string", "default": "{}", "parse": "json.loads", "invalid": "prints error and exits 1", "evidence_ids": ids("Dartsnut.__init__")},
      "persistence": {"methods": {"set_value": "(self, key, value)", "get_value": "(self, key, default=None)"}, "file": "data.json", "serialization": "JSON",
        "write_strategy": "temporary .tmp file followed by os.replace", "corruption": "set starts empty; get returns default", "key_restriction": "string documented", "value_restriction": "JSON-serializable",
        "default_path": "package source directory, with cwd fallback if __file__ unavailable", "evidence_ids": ids("Dartsnut.set_value","Dartsnut.get_value") + ids("Dartsnut.__init__")},
      "secondary_display": {"status": "NOT_FOUND_IN_INSPECTED_PACKAGE" if no_secondary else "VERIFIED_PACKAGE_SOURCE", "searched_symbols": SEARCH_TERMS,
        "matching_symbols": [], "matching_source_locations": matches, "public_api_candidates": [],
        "finding": "No secondary-display API was found in the inspected pydartsnut 1.2.1 wheel." if no_secondary else "Search terms occurred; manual API review is required.",
        "caveat": "This does not prove that the Dartsnut launcher, cabinet platform, another package, or a private API lacks secondary-display support."},
      "repository_usage": {"evidence_level": "VERIFIED_REPOSITORY_USAGE", "main_py": ["imports Dartsnut","creates a 128×160 Pygame surface","calls get_button_events","calls get_dart_hits","treats hits as dart_index, x, y","uses btn_a, btn_b, btn_up, btn_down, btn_left, and btn_right","relies on engine.running","calls update_frame_buffer"],
        "conf_json_size": [128,160], "pyproject_before_phase": "pydartsnut unconstrained", "uv_lock": "pydartsnut 1.2.1 with exact wheel and sdist hashes"},
      "contradictions": [
        {"contradiction_id":"C001","topic":"main.py display dimensions versus package implementation","source_a":"main.py uses 128×160","source_b":"wheel implementation encodes no width or height; package descriptions refer to 0–127 coordinates","impact":"Native render size and safe framebuffer length cannot be selected.","resolution_status":"UNRESOLVED","required_next_evidence":"Official platform contract plus emulator and cabinet native-size patterns."},
        {"contradiction_id":"C002","topic":"conf.json dimensions versus package implementation","source_a":"conf.json declares [128,160]","source_b":"wheel implementation encodes no width or height; package descriptions refer to 0–127 coordinates","impact":"Manifest size cannot be treated as verified hardware size.","resolution_status":"UNRESOLVED","required_next_evidence":"Launcher schema and physical display verification."},
        {"contradiction_id":"C003","topic":"dart re-arm documentation versus implementation","source_a":"Dartsnut.get_dart_hits docstring says 0.5 seconds","source_b":"InputHandler implementation default is 0.2 seconds","impact":"Consumers must not adopt the stale prose as final hardware input policy.","resolution_status":"UNRESOLVED","required_next_evidence":"Cabinet timing trace and maintained SDK clarification."}],
      "unknowns": unknowns, "evidence": evidence,
    }
    verified = sum(1 for e in evidence if e["evidence_level"].startswith("VERIFIED"))
    result["inspection"].update({"generated_claim_count": verified + len(unknowns) + len(result["contradictions"]), "verified_claim_count": verified,
                                 "unknown_claim_count": len(unknowns), "contradiction_count": len(result["contradictions"])})
    return result


def serialize(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", type=Path)
    group.add_argument("--check", type=Path)
    args = parser.parse_args(argv)
    try:
        rendered = serialize(inspect_wheel(args.wheel, args.expected_sha256))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        elif args.check.read_text(encoding="utf-8") != rendered:
            raise InspectionError(f"generated evidence differs from {args.check}")
    except (InspectionError, OSError, zipfile.BadZipFile, SyntaxError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
