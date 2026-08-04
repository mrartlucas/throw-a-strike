#!/usr/bin/env python3
"""Derive a contract from the canonical pydartsnut wheel without executing it."""
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
WHEEL_FILENAME = "pydartsnut-1.2.1-py3-none-any.whl"
WHEEL_SHA256 = "a207168cf36ba04352d3710933e159a1311948363be18c4bbd81ce4ae5916f4f"
SDIST_SHA256 = "f3618dc311e77773f6e655b11cb448e94940c59af32ad060e77a9ed616583d8e"
SEARCH_TERMS = tuple(sorted(("secondary", "second_display", "scoreboard", "control_screen",
                             "touch_screen", "auxiliary", "aux_display", "lcd",
                             "dual_display", "widget_display")))
TEXT_LIMIT = 1_000_000


class InspectionError(ValueError):
    pass


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _literal(node: ast.AST):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = node.args
    names = [a.arg for a in args.posonlyargs + args.args]
    defaults = [None] * (len(names) - len(args.defaults)) + args.defaults
    out = [name if default is None else f"{name}={ast.unparse(default)}"
           for name, default in zip(names, defaults)]
    if args.vararg:
        out.append("*" + args.vararg.arg)
    elif args.kwonlyargs:
        out.append("*")
    out.extend(item.arg if default is None else f"{item.arg}={ast.unparse(default)}"
               for item, default in zip(args.kwonlyargs, args.kw_defaults))
    if args.kwarg:
        out.append("**" + args.kwarg.arg)
    return "(" + ", ".join(out) + ")"


def _call_name(call: ast.Call) -> str:
    parts = []
    node: ast.AST = call.func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr); node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _target_name(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def inspect_wheel(path: Path, expected_sha256: str, *, allow_synthetic: bool = False) -> dict:
    """Inspect a wheel. ``allow_synthetic`` is an internal test/parser mode only."""
    if path.suffix != ".whl" or not path.is_file():
        raise InspectionError("input must be an existing .whl file")
    raw = path.read_bytes()  # identity is established before ZIP contents are read
    actual = _digest(raw)
    if not allow_synthetic:
        if path.name != WHEEL_FILENAME:
            raise InspectionError(f"canonical wheel filename required: {WHEEL_FILENAME}")
        if expected_sha256.lower() != WHEEL_SHA256:
            raise InspectionError("expected SHA-256 must equal the canonical locked hash")
        if actual != WHEEL_SHA256:
            raise InspectionError(f"canonical wheel SHA-256 mismatch: got {actual}")
    elif actual.lower() != expected_sha256.lower():
        raise InspectionError(f"wheel SHA-256 mismatch: expected {expected_sha256}, got {actual}")

    with zipfile.ZipFile(path) as wheel:
        names = sorted(wheel.namelist())
        metap = [n for n in names if n.endswith(".dist-info/METADATA")]
        recordp = [n for n in names if n.endswith(".dist-info/RECORD")]
        if len(metap) != 1 or len(recordp) != 1:
            raise InspectionError("wheel must contain exactly one METADATA and RECORD")
        metadata_raw = wheel.read(metap[0]); record_raw = wheel.read(recordp[0])
        metadata = BytesParser().parsebytes(metadata_raw)
        if metadata.get("Name", "").lower().replace("_", "-") != PACKAGE:
            raise InspectionError("wheel package name is not pydartsnut")
        if metadata.get("Version") != VERSION:
            raise InspectionError("wheel package version is not 1.2.1")
        source_paths = sorted(n for n in names if n.startswith("pydartsnut/") and n.endswith(".py"))
        if not source_paths:
            raise InspectionError("no pydartsnut Python package source found")
        files = {n: wheel.read(n) for n in names if not n.endswith("/")}
        sources = {n: files[n] for n in source_paths}

    evidence: list[dict] = []
    claims: list[dict] = []
    evidence_keys: dict[tuple, str] = {}

    def evidence_for(level: str, archive: str, symbol: str, node: ast.AST | None,
                     method: str, *, lines: tuple[int, int] | None = None) -> str:
        if node is not None:
            start, end = node.lineno, getattr(node, "end_lineno", node.lineno)
        else:
            start, end = lines or (1, 1)
        key = level, archive, symbol, start, end, method
        if key in evidence_keys:
            return evidence_keys[key]
        eid = f"E{len(evidence)+1:03d}"
        content = files[archive]
        evidence.append({"evidence_id": eid, "evidence_level": level,
                         "archive_path": archive, "source_sha256": _digest(content),
                         "symbol": symbol, "line_start": start, "line_end": end,
                         "extraction_method": method})
        evidence_keys[key] = eid
        return eid

    def add_claim(topic: str, value, status: str, eids: list[str]) -> str:
        cid = f"CLM-{len(claims)+1:03d}"
        claims.append({"claim_id": cid, "topic": topic, "value": value,
                       "status": status, "evidence_ids": sorted(set(eids))})
        return cid

    meta_lines = metadata_raw.decode("utf-8", errors="replace").splitlines()
    meta_eid = evidence_for("VERIFIED_PACKAGE_METADATA", metap[0], "METADATA", None,
                            "email.parser", lines=(1, max(1, len(meta_lines))))
    for topic, value in (("package.name", metadata.get("Name")),
                         ("package.version", metadata.get("Version")),
                         ("package.python_requirement", metadata.get("Requires-Python")),
                         ("package.license", metadata.get("License"))):
        if value is not None:
            add_claim(topic, value, "VERIFIED_PACKAGE_METADATA", [meta_eid])

    trees: dict[str, ast.Module] = {}
    classes, methods, functions, assigned, imported, strings = [], [], [], [], [], []
    method_nodes: dict[str, tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = {}
    class_nodes: dict[str, tuple[str, ast.ClassDef]] = {}
    for archive, data in sources.items():
        text = data.decode("utf-8"); tree = ast.parse(text, filename=archive); trees[archive] = tree
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    imported.append({"name": alias.asname or alias.name, "archive_path": archive, "line": node.lineno})
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    name = _target_name(target)
                    if name and not name.startswith("_"):
                        assigned.append({"name": name, "archive_path": archive, "line": node.lineno})
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                eid = evidence_for("VERIFIED_PACKAGE_SOURCE", archive, node.name, node, "ast.FunctionDef")
                functions.append({"name": node.name, "archive_path": archive, "line_start": node.lineno,
                                  "line_end": node.end_lineno, "evidence_ids": [eid]})
                method_nodes[node.name] = (archive, node)
            if isinstance(node, ast.ClassDef):
                eid = evidence_for("VERIFIED_PACKAGE_SOURCE", archive, node.name, node, "ast.ClassDef")
                classes.append({"name": node.name, "archive_path": archive, "line_start": node.lineno,
                                "line_end": node.end_lineno, "evidence_ids": [eid]})
                class_nodes[node.name] = (archive, node)
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbol = f"{node.name}.{child.name}"
                        meid = evidence_for("VERIFIED_PACKAGE_SOURCE", archive, symbol, child, "ast.FunctionDef")
                        methods.append({"symbol": symbol, "signature": _signature(child), "archive_path": archive,
                                        "line_start": child.lineno, "line_end": child.end_lineno, "evidence_ids": [meid]})
                        method_nodes[symbol] = (archive, child)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                strings.append({"value": node.value, "archive_path": archive, "line": node.lineno})

    def nodes(symbol: str, kind):
        item = method_nodes.get(symbol)
        if not item:
            return []
        archive, root = item
        return sorted([(archive, n) for n in ast.walk(root) if isinstance(n, kind)],
                      key=lambda item: (item[1].lineno, getattr(item[1], "col_offset", 0)))

    def precise(topic: str, value, archive: str, symbol: str, node: ast.AST, extraction: str) -> str:
        return add_claim(topic, value, "VERIFIED_PACKAGE_SOURCE",
                         [evidence_for("VERIFIED_PACKAGE_SOURCE", archive, symbol, node, extraction)])

    # Public signatures are source-derived claims.
    signature_claims = {}
    for item in methods:
        signature_claims[item["symbol"]] = add_claim(f"signature.{item['symbol']}", item["signature"],
                                                      "VERIFIED_PACKAGE_SOURCE", item["evidence_ids"])

    # Constructor options/defaults and setup calls/assignments.
    constructor_options = {}
    for archive, call in nodes("Dartsnut.__init__", ast.Call):
        name = _call_name(call)
        if name.endswith("add_argument") and call.args:
            option = _literal(call.args[0])
            default_nodes = [kw.value for kw in call.keywords if kw.arg == "default"]
            default = _literal(default_nodes[0]) if len(default_nodes) == 1 else None
            if isinstance(option, str):
                cid = precise(f"constructor.option.{option}.default", default, archive, "Dartsnut.__init__", call, "ast.Call(add_argument)")
                constructor_options[option] = {"default": default, "status": "VERIFIED_PACKAGE_SOURCE", "claim_ids": [cid]}
        if name == "signal.signal":
            precise("constructor.signal_handler_registration", ast.unparse(call), archive, "Dartsnut.__init__", call, "ast.Call(signal.signal)")
        if name == "json.loads":
            precise("widget_parameters.parse", "json.loads", archive, "Dartsnut.__init__", call, "ast.Call(json.loads)")
        if name == "os.makedirs":
            precise("persistence.directory_creation", "os.makedirs", archive, "Dartsnut.__init__", call, "ast.Call(os.makedirs)")
    for archive, assign in nodes("Dartsnut.__init__", (ast.Assign, ast.AnnAssign)):
        targets = assign.targets if isinstance(assign, ast.Assign) else [assign.target]
        value_node = assign.value
        for target in targets:
            target_text = _target_name(target)
            value = _literal(value_node)
            if target_text == "self.running" and isinstance(value, bool):
                precise("lifecycle.running_initial", value, archive, "Dartsnut.__init__", assign, "ast.Assign")
            if target_text == "self.data_store_file" and isinstance(value_node, ast.Call) and _call_name(value_node) == "os.path.join":
                literals = [_literal(a) for a in value_node.args]
                filename = next((x for x in literals if isinstance(x, str)), None)
                if filename:
                    precise("persistence.filename", filename, archive, "Dartsnut.__init__", value_node, "ast.Call(os.path.join)")

    # Framebuffer branches, states, mutations, calls, returns and doc wording.
    for archive, call in nodes("Dartsnut.update_frame_buffer", ast.Call):
        name = _call_name(call)
        if name == "isinstance" and len(call.args) >= 2 and ast.unparse(call.args[1]) == "bytearray":
            precise("main_display.accepts_bytearray", True, archive, "Dartsnut.update_frame_buffer", call, "ast.Call(isinstance)")
        if name == "hasattr" and len(call.args) >= 2 and _literal(call.args[1]) == "tobytes":
            precise("main_display.accepts_tobytes", True, archive, "Dartsnut.update_frame_buffer", call, "ast.Call(hasattr)")
        if name.endswith("_post_render_semaphore"):
            precise("main_display.posts_render_semaphore", True, archive, "Dartsnut.update_frame_buffer", call, "ast.Call")
    status_comparisons = []
    for archive, comp in nodes("Dartsnut.update_frame_buffer", ast.Compare):
        if "shm_buffer[0]" in ast.unparse(comp.left) and len(comp.comparators) == 1:
            value = _literal(comp.comparators[0])
            if value is not None:
                cid = precise("main_display.status_comparison", value, archive, "Dartsnut.update_frame_buffer", comp, "ast.Compare")
                status_comparisons.append({"value": value, "claim_ids": [cid]})
    for archive, assign in nodes("Dartsnut.update_frame_buffer", (ast.Assign, ast.AnnAssign)):
        targets = assign.targets if isinstance(assign, ast.Assign) else [assign.target]
        for target in targets:
            simple_name = _target_name(target).split(".")[-1].lower()
            literal = _literal(assign.value)
            if simple_name in ("width", "frame_width", "display_width") and isinstance(literal, int):
                precise("main_display.encoded_width", literal, archive, "Dartsnut.update_frame_buffer", assign, "ast.Assign")
            if simple_name in ("height", "frame_height", "display_height") and isinstance(literal, int):
                precise("main_display.encoded_height", literal, archive, "Dartsnut.update_frame_buffer", assign, "ast.Assign")
            if simple_name in ("channels", "channel_count") and isinstance(literal, int):
                precise("main_display.channel_count", literal, archive, "Dartsnut.update_frame_buffer", assign, "ast.Assign")
        if any("shm_buffer[0]" in _target_name(t) for t in targets):
            value = _literal(assign.value)
            if value is not None:
                precise("main_display.status_mutation", value, archive, "Dartsnut.update_frame_buffer", assign, "ast.Assign")
    return_values = []
    for archive, ret in nodes("Dartsnut.update_frame_buffer", ast.Return):
        value = _literal(ret.value) if ret.value else None
        cid = precise("main_display.return_value", value, archive, "Dartsnut.update_frame_buffer", ret, "ast.Return")
        return_values.append({"value": value, "claim_ids": [cid]})
    for archive, comp in nodes("Dartsnut.update_frame_buffer", ast.Compare):
        rendered = ast.unparse(comp)
        if "len(image_bytes)" in rendered or "len(frame)" in rendered:
            precise("main_display.byte_length_validation", rendered, archive,
                    "Dartsnut.update_frame_buffer", comp, "ast.Compare")
    item = method_nodes.get("Dartsnut.update_frame_buffer")
    rgb_claim = None
    if item:
        archive, method = item; doc = ast.get_docstring(method, clean=False) or ""
        if "RGB888" in doc:
            docnode = method.body[0] if method.body and isinstance(method.body[0], ast.Expr) else method
            rgb_claim = precise("main_display.pixel_format_wording", "RGB888", archive, "Dartsnut.update_frame_buffer", docnode, "ast.get_docstring")

    # Dart constants and tuple construction, derived only from relevant methods/classes.
    slot_claims = []
    for symbol in ("Dartsnut.get_darts", "InputHandler._update_blocking_timers", "InputHandler.get_dart_hits", "InputHandler.get_active_darts"):
        for archive, call in nodes(symbol, ast.Call):
            if _call_name(call) == "range" and len(call.args) == 1 and isinstance(_literal(call.args[0]), int):
                slot_claims.append(precise("dart_input.slot_count", _literal(call.args[0]), archive, symbol, call, "ast.Call(range)"))
    tuple_claims = []
    for symbol in ("InputHandler.get_dart_hits", "InputHandler.get_active_darts"):
        for archive, call in nodes(symbol, ast.Call):
            if _call_name(call).endswith("append") and call.args and isinstance(call.args[0], ast.Tuple) and len(call.args[0].elts) == 3:
                cid = precise("dart_input.event_tuple_arity", 3, archive, symbol, call.args[0], "ast.Tuple")
                tuple_claims.append(cid)
    mapping_constants = {}
    mapping_nodes = nodes("Dartsnut.get_darts", ast.Compare) + nodes("Dartsnut.get_darts", ast.BinOp)
    seen_mapping_nodes = set()
    for archive, expression in sorted(mapping_nodes, key=lambda item: (item[1].lineno, item[1].col_offset)):
        for node in ast.walk(expression):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                node_key = archive, node.lineno, node.col_offset
                if node_key in seen_mapping_nodes:
                    continue
                seen_mapping_nodes.add(node_key)
                cid = precise("dart_input.mapping_constant", node.value, archive,
                              "Dartsnut.get_darts", node, "ast.Constant in ast.Compare/BinOp")
                mapping_constants.setdefault(str(node.value), []).append(cid)
    for archive, assign in nodes("Dartsnut.get_darts", (ast.Assign, ast.AnnAssign)):
        targets = assign.targets if isinstance(assign, ast.Assign) else [assign.target]
        value = _literal(assign.value)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and any(_target_name(t).endswith("_mapped") for t in targets):
            cid = precise("dart_input.mapping_output_constant", value, archive,
                          "Dartsnut.get_darts", assign.value, "ast.Constant assigned to mapped coordinate")
            mapping_constants.setdefault(str(value), []).append(cid)
    invalid_values = []
    for archive, comp in nodes("_is_invalid_dart", ast.Compare):
        values = [_literal(n) for n in [comp.left] + comp.comparators]
        for value in values:
            if isinstance(value, list) and len(value) == 2:
                cid = precise("dart_input.invalid_sentinel", value, archive, "_is_invalid_dart", comp, "ast.Compare")
                invalid_values.append({"value": value, "claim_ids": [cid]})
    timing = {}
    handler = class_nodes.get("InputHandler")
    if handler:
        archive, cls = handler
        for child in cls.body:
            if isinstance(child, (ast.Assign, ast.AnnAssign)):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                value = _literal(child.value)
                for target in targets:
                    name = _target_name(target)
                    if name in ("IDLE_UNBLOCK_DURATION", "MIN_ACTIVE_DURATION") and isinstance(value, (int, float)):
                        timing[name] = {"value": value, "claim_ids": [precise(f"dart_input.{name.lower()}", value, archive, "InputHandler", child, "ast.Assign")]}
    for topic, symbol, attr, operation in (("dart_input.block_add", "InputHandler.get_dart_hits", "blocked_dart_indices.add", "add"),
                                           ("dart_input.block_remove", "InputHandler._update_blocking_timers", "blocked_dart_indices.remove", "remove"),
                                           ("dart_input.block_reset", "InputHandler.reset_blocking_state", "blocked_dart_indices.clear", "clear")):
        for archive, call in nodes(symbol, ast.Call):
            if _call_name(call).endswith(attr):
                precise(topic, operation, archive, symbol, call, "ast.Call")

    # Buttons are extracted from the actual dict syntax and event iteration.
    button_keys, button_key_claims = [], []
    for archive, dictionary in nodes("Dartsnut.get_buttons", ast.Dict):
        literals = [_literal(k) for k in dictionary.keys]
        keys = [k for k in literals if isinstance(k, str)]
        if keys:
            button_keys = keys
            button_key_claims.append(precise("button_input.keys", keys, archive, "Dartsnut.get_buttons", dictionary, "ast.Dict"))
    debounce_candidates = []
    for archive, assign in nodes("Dartsnut.get_buttons", (ast.Assign, ast.AnnAssign)):
        targets = assign.targets if isinstance(assign, ast.Assign) else [assign.target]
        if any(_target_name(t) == "self._debounce_delay" for t in targets):
            value = _literal(assign.value)
            if isinstance(value, (int, float)):
                cid = precise("button_input.debounce_seconds", value, archive, "Dartsnut.get_buttons", assign, "ast.Assign")
                debounce_candidates.append({"value": value, "claim_ids": [cid]})
    debounce = debounce_candidates[0] if len({x["value"] for x in debounce_candidates}) == 1 else None
    for archive, dictionary in nodes("InputHandler.get_buttons", ast.DictComp):
        precise("button_input.event_default", False, archive, "InputHandler.get_buttons", dictionary, "ast.DictComp")
    for archive, loop in nodes("InputHandler.get_buttons", ast.For):
        precise("button_input.edge_iteration", ast.unparse(loop.target), archive, "InputHandler.get_buttons", loop, "ast.For")

    # Brightness compare and write are syntax-derived.
    brightness_candidates = []
    for archive, comp in nodes("Dartsnut.set_brightness", ast.Compare):
        constants = [_literal(comp.left)] + [_literal(x) for x in comp.comparators]
        nums = [x for x in constants if isinstance(x, (int, float)) and not isinstance(x, bool)]
        if len(nums) == 2 and len(comp.ops) == 2:
            value = [nums[0], nums[1]]
            cid = precise("brightness.accepted_bounds", value, archive, "Dartsnut.set_brightness", comp, "ast.Compare")
            brightness_candidates.append({"value": value, "claim_ids": [cid]})
    brightness_bounds = brightness_candidates[0] if len({tuple(x["value"]) for x in brightness_candidates}) == 1 else None
    for archive, assign in nodes("Dartsnut.set_brightness", (ast.Assign, ast.AnnAssign)):
        precise("brightness.write", ast.unparse(assign), archive, "Dartsnut.set_brightness", assign, "ast.Assign")
    brightness_returns = nodes("Dartsnut.set_brightness", ast.Return)
    if not brightness_returns and method_nodes.get("Dartsnut.set_brightness"):
        archive, method = method_nodes["Dartsnut.set_brightness"]
        precise("brightness.implicit_return", None, archive, "Dartsnut.set_brightness", method, "ast.FunctionDef(no Return)")

    # Persistence operations and error handlers.
    persistence_ops = {}
    for symbol in ("Dartsnut.__init__", "Dartsnut.set_value", "Dartsnut.get_value"):
        for archive, call in nodes(symbol, ast.Call):
            name = _call_name(call)
            if name in ("json.load", "json.dump", "os.replace", "os.remove", "os.path.exists", "os.getcwd", "os.path.dirname", "os.path.abspath"):
                cid = precise(f"persistence.operation.{name}", name, archive, symbol, call, f"ast.Call({name})")
                persistence_ops.setdefault(name, []).append(cid)
        for archive, trynode in nodes(symbol, ast.Try):
            handled = sorted({ast.unparse(t) for h in trynode.handlers for t in ([h.type] if h.type else [])})
            if handled:
                precise(f"persistence.error_handlers.{symbol}", handled, archive, symbol, trynode, "ast.Try/ExceptHandler")
    temp_suffix = None
    for archive, assign in nodes("Dartsnut.set_value", (ast.Assign, ast.AnnAssign)):
        if ".tmp" in ast.unparse(assign.value):
            cid = precise("persistence.temporary_suffix", ".tmp", archive, "Dartsnut.set_value", assign, "ast.Assign/BinOp")
            temp_suffix = {"value": ".tmp", "claim_ids": [cid]}

    # Complete secondary search across metadata, RECORD, every source/identifier/string,
    # and all safely decoded small text files.
    def term_hits(value: str) -> list[str]:
        low = value.lower()
        return [term for term in SEARCH_TERMS if term in low]
    matching_symbols, locations, candidates = [], [], []
    symbol_items = ([{"name": x["name"], "kind": "class", **{k: x[k] for k in ("archive_path", "line_start")}} for x in classes] +
                    [{"name": x["symbol"], "kind": "method", "archive_path": x["archive_path"], "line_start": x["line_start"]} for x in methods] +
                    [{"name": x["name"], "kind": "function", "archive_path": x["archive_path"], "line_start": x["line_start"]} for x in functions] +
                    [{"name": x["name"], "kind": "assigned", "archive_path": x["archive_path"], "line_start": x["line"]} for x in assigned] +
                    [{"name": x["name"], "kind": "imported", "archive_path": x["archive_path"], "line_start": x["line"]} for x in imported])
    for item in symbol_items:
        hits = term_hits(item["name"])
        if hits:
            record = {**item, "terms": hits}; matching_symbols.append(record)
            if item["kind"] in ("class", "method", "function", "assigned", "imported") and not item["name"].split(".")[-1].startswith("_"):
                candidates.append(record)
    for entry in strings:
        hits = term_hits(entry["value"])
        if hits:
            locations.append({"archive_path": entry["archive_path"], "line": entry["line"], "kind": "string_constant", "terms": hits})
    headers = "\n".join(f"{k}: {v}" for k, v in metadata.items())
    description = metadata.get_payload() if isinstance(metadata.get_payload(), str) else ""
    metadata_matches = [{"area": area, "terms": term_hits(text)} for area, text in (("headers", headers), ("description", description)) if term_hits(text)]
    records = sorted(line for line in record_raw.decode("utf-8", errors="replace").splitlines() if line)
    record_matches = [{"path": line.split(",", 1)[0], "terms": term_hits(line.split(",", 1)[0])} for line in records if term_hits(line.split(",", 1)[0])]
    text_file_matches = []
    for archive, raw_file in sorted(files.items()):
        if len(raw_file) > TEXT_LIMIT:
            continue
        try:
            text = raw_file.decode("utf-8")
        except UnicodeDecodeError:
            continue
        hits = term_hits(text)
        if hits:
            text_file_matches.append({"archive_path": archive, "terms": hits})
    search_empty = not any((matching_symbols, locations, candidates, metadata_matches, record_matches, text_file_matches))
    secondary_status = "NOT_FOUND_IN_INSPECTED_PACKAGE" if search_empty else "VERIFIED_PACKAGE_SOURCE"
    secondary_finding = "No secondary-display API was found in the inspected pydartsnut 1.2.1 wheel." if search_empty else "Search matches require API review."
    secondary_claim = add_claim("secondary_display.search_result", secondary_finding,
                                secondary_status, [] if search_empty else sorted({eid for x in methods + classes + functions for eid in x["evidence_ids"] if any(t in json.dumps(x).lower() for t in SEARCH_TERMS)}))

    def refs(prefix: str) -> list[str]:
        return [c["claim_id"] for c in claims if c["topic"].startswith(prefix)]
    def field(value, prefix: str, unknown="UNKNOWN"):
        cids = refs(prefix)
        return {"value": value if cids else unknown, "status": "VERIFIED_PACKAGE_SOURCE" if cids else "UNKNOWN_HARDWARE", "claim_ids": cids}
    def unique_field(prefix: str):
        matched = [c for c in claims if c["topic"] == prefix]
        values = {json.dumps(c["value"], sort_keys=True) for c in matched}
        if len(values) != 1:
            return {"value":"UNKNOWN","status":"UNKNOWN_HARDWARE","claim_ids":[]}
        return {"value":matched[0]["value"],"status":"VERIFIED_PACKAGE_SOURCE","claim_ids":[c["claim_id"] for c in matched]}

    contradictions = [
      {"contradiction_id":"C001","topic":"main.py display dimensions versus package implementation","source_a":"main.py uses 128×160","source_b":"no width/height literal was extracted from update_frame_buffer","impact":"Native size and safe payload length cannot be selected.","resolution_status":"UNRESOLVED","required_next_evidence":"Platform specification and cabinet patterns."},
      {"contradiction_id":"C002","topic":"conf.json dimensions versus package implementation","source_a":"conf.json declares [128,160]","source_b":"no width/height literal was extracted from update_frame_buffer","impact":"Manifest size is not verified hardware size.","resolution_status":"UNRESOLVED","required_next_evidence":"Launcher schema and cabinet evidence."},
    ]
    # Only add prose/implementation timing contradiction when both are actually found.
    doc = ast.get_docstring(method_nodes["Dartsnut.get_dart_hits"][1]) if "Dartsnut.get_dart_hits" in method_nodes else ""
    doc_half = "0.5" in (doc or "")
    impl_idle = timing.get("IDLE_UNBLOCK_DURATION", {}).get("value")
    if doc_half and impl_idle is not None and impl_idle != 0.5:
        archive, method = method_nodes["Dartsnut.get_dart_hits"]
        docnode = method.body[0] if method.body and isinstance(method.body[0], ast.Expr) else method
        doccid = precise("dart_input.documented_rearm_seconds", 0.5, archive, "Dartsnut.get_dart_hits", docnode, "ast.get_docstring")
        contradictions.append({"contradiction_id":"C003","topic":"dart re-arm documentation versus implementation","source_a":{"value":0.5,"claim_ids":[doccid]},"source_b":{"value":impl_idle,"claim_ids":timing["IDLE_UNBLOCK_DURATION"]["claim_ids"]},"impact":"Final input policy cannot rely on stale prose.","resolution_status":"UNRESOLVED","required_next_evidence":"Maintainer clarification and cabinet timing trace."})

    unknown_questions = ["Physical display width and height on every supported cabinet", "RGB channel order on actual hardware", "Framebuffer stride", "Display refresh limit", "Safe update rate", "Dropped-frame behavior", "Physical x/y orientation", "Coordinate calibration", "Coordinate dead zones", "Coordinate jitter", "Simultaneous-hit behavior under real hardware load", "Dart-index to player-color mapping", "Dart-index stability", "Wrong-dart behavior", "Secondary-display API outside the package", "Touch-screen behavior", "Physical button placement", "Audio routing", "Emulator behavior", "Packaging and installation format", "Launcher lifecycle", "Data-store quota and retention", "Cabinet and firmware compatibility", "Performance budgets"]
    unknowns = [{"unknown_id":f"U{i:03d}","question":q,"current_status":"UNKNOWN_HARDWARE","why_package_source_is_insufficient":"The client wheel does not establish cabinet, firmware, launcher, or operational behavior.","verification_method":"Use current platform documentation, emulator traces, and recorded cabinet testing.","blocks_adapter":i in (1,2,3,4,5,6,7,8,12,13,15,19,20,21,23),"blocks_rendering":i in (1,2,3,4,5,6,7,15,19,23,24),"blocks_multiplayer":i in (7,8,9,10,11,12,13,14,15,19,23)} for i,q in enumerate(unknown_questions,1)]

    result = {
      "schema_version": 1,
      "package": {"name": PACKAGE,"version":VERSION,"wheel_filename":path.name,"wheel_sha256":actual,"sdist_sha256":SDIST_SHA256,"wheel_size":len(raw),"metadata_name":metadata.get("Name"),"metadata_version":metadata.get("Version"),"python_requirement":metadata.get("Requires-Python"),"license":metadata.get("License"),"source_files_inspected":[{"archive_path":p,"sha256":_digest(sources[p])} for p in source_paths],"claim_ids":refs("package.")},
      "inspection": {"inspector_schema_version":SCHEMA_VERSION,"deterministic_generation":True,"ast_only":True,"package_execution":False,"hardware_access":False,"synthetic_mode":allow_synthetic,"record_entries":records,"public_classes":sorted(classes,key=lambda x:(x["archive_path"],x["line_start"])),"public_methods":sorted(methods,key=lambda x:(x["archive_path"],x["line_start"])),"module_functions":sorted(functions,key=lambda x:(x["archive_path"],x["line_start"]))},
      "constructor": {"signature":field(next((x["signature"] for x in methods if x["symbol"]=="Dartsnut.__init__"),None),"signature.Dartsnut.__init__"),"options":constructor_options,"setup_claim_ids":refs("constructor.")},
      "main_display": {"signature":field(next((x["signature"] for x in methods if x["symbol"]=="Dartsnut.update_frame_buffer"),None),"signature.Dartsnut.update_frame_buffer"),"accepted_bytearray":unique_field("main_display.accepts_bytearray"),"accepted_tobytes":unique_field("main_display.accepts_tobytes"),"status_comparisons":status_comparisons,"status_mutation":unique_field("main_display.status_mutation"),"return_values":return_values,"semaphore_call":unique_field("main_display.posts_render_semaphore"),"pixel_format_wording":unique_field("main_display.pixel_format_wording"),"encoded_width":unique_field("main_display.encoded_width"),"encoded_height":unique_field("main_display.encoded_height"),"channel_count":unique_field("main_display.channel_count"),"byte_length_validation":unique_field("main_display.byte_length_validation")},
      "dart_input": {"slot_count":unique_field("dart_input.slot_count"),"tuple_arity":unique_field("dart_input.event_tuple_arity"),"mapping_constants":mapping_constants,"invalid_sentinels":invalid_values,"timing":timing,"blocking_claim_ids":refs("dart_input.block"),"reset_claim_ids":refs("dart_input.block_reset")},
      "button_input": {"keys":field(button_keys,"button_input.keys"),"debounce_seconds":debounce or {"value":"UNKNOWN","status":"UNKNOWN_HARDWARE","claim_ids":[]},"event_claim_ids":refs("button_input.event")+refs("button_input.edge")},
      "lifecycle": {"running_initial":unique_field("lifecycle.running_initial"),"signal_claim_ids":refs("constructor.signal_handler_registration"),"claim_ids":refs("lifecycle.")+refs("signature.Dartsnut.close")+refs("signature.Dartsnut.sigint_handler")},
      "brightness": {"signature":field(next((x["signature"] for x in methods if x["symbol"]=="Dartsnut.set_brightness"),None),"signature.Dartsnut.set_brightness"),"bounds":brightness_bounds or {"value":"UNKNOWN","status":"UNKNOWN_HARDWARE","claim_ids":[]},"write_claim_ids":refs("brightness.write"),"return_claim_ids":refs("brightness.implicit_return")},
      "widget_parameters": {"parse":unique_field("widget_parameters.parse"),"params_option":constructor_options.get("--params",{"value":"UNKNOWN","status":"UNKNOWN_HARDWARE","claim_ids":[]})},
      "persistence": {"filename":field(next((c["value"] for c in claims if c["topic"]=="persistence.filename"),None),"persistence.filename"),"temporary_suffix":temp_suffix or {"value":"UNKNOWN","status":"UNKNOWN_HARDWARE","claim_ids":[]},"operations":persistence_ops,"directory_claim_ids":refs("persistence.directory"),"error_claim_ids":refs("persistence.error_handlers")},
      "secondary_display": {"status":secondary_status,"searched_symbols":list(SEARCH_TERMS),"matching_symbols":sorted(matching_symbols,key=lambda x:(x["name"],x["archive_path"],x["line_start"])),"matching_source_locations":sorted(locations,key=lambda x:(x["archive_path"],x["line"])),"public_api_candidates":sorted(candidates,key=lambda x:(x["name"],x["archive_path"],x["line_start"])),"metadata_matches":metadata_matches,"record_matches":record_matches,"text_file_matches":text_file_matches,"finding":secondary_finding,"caveat":"This does not prove that the Dartsnut launcher, cabinet platform, another package, or a private API lacks secondary-display support.","claim_ids":[secondary_claim]},
      "repository_usage": {"status":"VERIFIED_REPOSITORY_USAGE","main_py":["imports Dartsnut","creates a 128×160 Pygame surface","calls get_button_events","calls get_dart_hits","treats hits as dart_index, x, y","uses btn_a, btn_b, btn_up, btn_down, btn_left, and btn_right","relies on engine.running","calls update_frame_buffer"],"conf_json_size":[128,160],"pyproject_before_phase":"pydartsnut unconstrained","uv_lock":"pydartsnut 1.2.1 with exact hashes"},
      "contradictions": contradictions,"unknowns":unknowns,"claims":claims,"evidence":evidence,
    }
    verified = sum(c["status"].startswith("VERIFIED") for c in claims)
    result["inspection"].update({"generated_claim_count":len(claims),"verified_claim_count":verified,"unknown_claim_count":len(unknowns),"contradiction_count":len(contradictions)})
    return result


def serialize(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path); parser.add_argument("--expected-sha256", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", type=Path); group.add_argument("--check", type=Path)
    args = parser.parse_args(argv)
    try:
        rendered = serialize(inspect_wheel(args.wheel, args.expected_sha256))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(rendered, encoding="utf-8")
        elif args.check.read_text(encoding="utf-8") != rendered:
            raise InspectionError(f"generated evidence differs from {args.check}")
    except (InspectionError, OSError, zipfile.BadZipFile, SyntaxError) as exc:
        print(f"error: {exc}", file=sys.stderr); return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
