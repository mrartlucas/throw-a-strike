"""Integrity tests for the static pydartsnut wheel contract."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.inspect_pydartsnut_wheel import (InspectionError, SDIST_SHA256,
    WHEEL_FILENAME, WHEEL_SHA256, inspect_wheel, main, serialize)

ROOT = Path(__file__).parents[1]
CONTRACT = ROOT / "docs/platform/evidence/pydartsnut-1.2.1-contract.json"
DOC = ROOT / "docs/platform/DARTSNUT_PLATFORM_CONTRACT.md"

BASE_SOURCE = '''import argparse, json, os, signal
class Dartsnut:
 def __init__(self):
  self.running = True
  signal.signal(signal.SIGINT, self.stop)
  p=argparse.ArgumentParser()
  p.add_argument("--params", default="{}")
  p.add_argument("--shm", default="pdishm")
  p.add_argument("--data-store", default=None)
  self.widget_params=json.loads("{}")
  os.makedirs("store", exist_ok=True)
  self.data_store_file=os.path.join("store", "data.json")
 def stop(self, *args): self.running=False
 def update_frame_buffer(self, frame):
  """Bytes must be RGB888."""
  if isinstance(frame, bytearray): data=frame
  elif hasattr(frame, "tobytes"): data=frame.tobytes()
  if self.shm_buffer[0] == 2: return False
  if self.shm_buffer[0] == 1:
   self.shm_buffer[0] = 0
   self._post_render_semaphore()
   return True
  return False
 def get_darts(self):
  for i in range(12):
   if i <= 1800: x=0
   elif i >= 39800: x=127
   else: x=(i-1800)//299
 def get_buttons(self):
  buttons={"btn_a":False,"btn_b":False,"btn_up":False,"btn_right":False,"btn_left":False,"btn_down":False,"btn_home":False,"btn_reserved":False}
  self._debounce_delay=0.03
  return buttons
 def set_brightness(self, brightness):
  if 10 <= brightness <= 100: self.buf[49]=brightness
 def set_value(self,key,value):
  data=json.load(open(self.data_store_file))
  temp_file=self.data_store_file+".tmp"
  json.dump(data,open(temp_file,"w")); os.replace(temp_file,self.data_store_file)
 def get_value(self,key,default=None):
  try: return json.load(open(self.data_store_file)).get(key,default)
  except (json.JSONDecodeError, IOError): return default
 def get_dart_hits(self):
  """Unblocked after 0.5 seconds."""
 def get_active_darts(self): pass
 def reset_blocking_state(self): pass
 def get_button_events(self): pass
class InputHandler:
 IDLE_UNBLOCK_DURATION=0.2
 MIN_ACTIVE_DURATION=0.0
 def _update_blocking_timers(self, states):
  for i in range(12): self.blocked_dart_indices.remove(i)
 def get_dart_hits(self):
  for index in range(12): self.hits.append((index, 1, 2)); self.blocked_dart_indices.add(index)
 def get_active_darts(self):
  for i in range(12): self.active.append((i,1,2))
 def get_buttons(self):
  result={btn:False for btn in self.engine.get_buttons()}
  for name, pressed in result.items(): pass
 def reset_blocking_state(self): self.blocked_dart_indices.clear()
def _is_invalid_dart(pos): return pos == [-1,-1] or pos == [0,0]
'''


def wheel(directory: Path, source=BASE_SOURCE, *, filename=WHEEL_FILENAME,
          name="pydartsnut", version="1.2.1", description="Description", extra=None):
    path=directory/filename; dist=f"{name}-{version}.dist-info"
    metadata=f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\nRequires-Python: >=3.11\n\n{description}\n"
    with zipfile.ZipFile(path,"w") as z:
        z.writestr("pydartsnut/__init__.py",source)
        z.writestr(f"{dist}/METADATA",metadata)
        extra_records="".join(f"{key},,\n" for key in sorted(extra or {}))
        z.writestr(f"{dist}/RECORD",f"pydartsnut/__init__.py,,\n{dist}/METADATA,,\n{extra_records}")
        for key,value in (extra or {}).items(): z.writestr(key,value)
    return path


def synthetic(path):
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    return inspect_wheel(path,digest,allow_synthetic=True)


class CanonicalIdentityTests(unittest.TestCase):
    def test_production_rejects_arbitrary_matching_hash(self):
        with tempfile.TemporaryDirectory() as td:
            p=wheel(Path(td)); own=hashlib.sha256(p.read_bytes()).hexdigest()
            self.assertNotEqual(own,WHEEL_SHA256)
            with self.assertRaisesRegex(InspectionError,"expected SHA-256|canonical wheel SHA"):
                inspect_wheel(p,own)
            self.assertEqual(main([str(p),"--expected-sha256",own,"--output",str(Path(td)/"x")]),1)

    def test_production_requires_canonical_filename(self):
        with tempfile.TemporaryDirectory() as td:
            p=wheel(Path(td),filename="renamed.whl")
            with self.assertRaisesRegex(InspectionError,"filename"):
                inspect_wheel(p,WHEEL_SHA256)

    def test_identity_name_version_and_nonwheel_rejections(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); bad=root/"x.txt"; bad.write_text("x")
            with self.assertRaises(InspectionError): inspect_wheel(bad,WHEEL_SHA256)
            for kwargs, text in (({"name":"other"},"name"),({"version":"9"},"version")):
                p=wheel(root,**kwargs)
                with self.assertRaisesRegex(InspectionError,text): synthetic(p)


class LiteralExtractionTests(unittest.TestCase):
    def inspect(self, source=BASE_SOURCE, **kwargs):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        return synthetic(wheel(Path(temp.name),source,**kwargs))

    def claim(self,data,topic): return [c for c in data["claims"] if c["topic"]==topic]

    def test_missing_values_and_methods_are_not_hardcoded(self):
        data=self.inspect("class Dartsnut:\n def __init__(self): pass\n")
        self.assertFalse(self.claim(data,"button_input.keys"))
        self.assertEqual(data["button_input"]["keys"]["status"],"UNKNOWN_HARDWARE")
        self.assertEqual(data["main_display"]["accepted_bytearray"]["status"],"UNKNOWN_HARDWARE")
        self.assertEqual(data["dart_input"]["slot_count"]["status"],"UNKNOWN_HARDWARE")

    def test_changed_slot_literal_changes_claim(self):
        first=self.inspect(); second=self.inspect(BASE_SOURCE.replace("range(12)","range(9)"))
        self.assertEqual(first["dart_input"]["slot_count"]["value"],12)
        self.assertEqual(second["dart_input"]["slot_count"]["value"],9)

    def test_ambiguous_slot_and_debounce_are_unknown(self):
        source=BASE_SOURCE.replace("for i in range(12):\n   if", "for i in range(12):\n   for j in range(9): pass\n   if").replace("self._debounce_delay=0.03", "self._debounce_delay=0.03\n  self._debounce_delay=0.07")
        data=self.inspect(source)
        self.assertEqual(data["dart_input"]["slot_count"]["status"],"UNKNOWN_HARDWARE")
        self.assertEqual(data["button_input"]["debounce_seconds"]["status"],"UNKNOWN_HARDWARE")

    def test_frame_states_returns_and_branches_are_ast_derived(self):
        data=self.inspect()
        self.assertEqual([x["value"] for x in data["main_display"]["status_comparisons"]],[2,1])
        self.assertEqual([x["value"] for x in data["main_display"]["return_values"]],[False,True,False])
        self.assertEqual(data["main_display"]["status_mutation"]["value"],0)
        self.assertTrue(data["main_display"]["accepted_bytearray"]["value"])
        self.assertTrue(data["main_display"]["accepted_tobytes"]["value"])

    def test_optional_dimensions_channels_and_length_check_are_source_derived(self):
        insertion='  width=64\n  height=32\n  channels=4\n  if len(frame) != 8192: return False\n'
        data=self.inspect(BASE_SOURCE.replace('  """Bytes must be RGB888."""\n', '  """Bytes must be RGB888."""\n'+insertion))
        self.assertEqual(data["main_display"]["encoded_width"]["value"],64)
        self.assertEqual(data["main_display"]["encoded_height"]["value"],32)
        self.assertEqual(data["main_display"]["channel_count"]["value"],4)
        self.assertIn("len(frame)",data["main_display"]["byte_length_validation"]["value"])

    def test_slot_tuple_sentinels_and_timing_are_extracted(self):
        data=self.inspect()
        self.assertEqual(data["dart_input"]["tuple_arity"]["value"],3)
        self.assertEqual([x["value"] for x in data["dart_input"]["invalid_sentinels"]],[[-1,-1],[0,0]])
        self.assertEqual(data["dart_input"]["timing"]["IDLE_UNBLOCK_DURATION"]["value"],0.2)
        changed=self.inspect(BASE_SOURCE.replace("IDLE_UNBLOCK_DURATION=0.2","IDLE_UNBLOCK_DURATION=0.4"))
        self.assertEqual(changed["dart_input"]["timing"]["IDLE_UNBLOCK_DURATION"]["value"],0.4)

    def test_button_keys_and_debounce_are_extracted(self):
        data=self.inspect(); keys=data["button_input"]["keys"]["value"]
        self.assertEqual(keys,["btn_a","btn_b","btn_up","btn_right","btn_left","btn_down","btn_home","btn_reserved"])
        self.assertEqual(data["button_input"]["debounce_seconds"]["value"],0.03)
        changed=self.inspect(BASE_SOURCE.replace('"btn_reserved":False','"btn_extra":False'))
        self.assertIn("btn_extra",changed["button_input"]["keys"]["value"])
        self.assertNotIn("btn_reserved",changed["button_input"]["keys"]["value"])

    def test_button_event_default_is_literal_derived_and_ambiguity_is_unknown(self):
        false_data=self.inspect()
        self.assertIs(false_data["button_input"]["event_default"]["value"],False)
        event_claim=next(c for c in false_data["claims"] if c["topic"]=="button_input.event_default")
        event_evidence=next(e for e in false_data["evidence"] if e["evidence_id"] in event_claim["evidence_ids"])
        self.assertEqual(event_evidence["extraction_method"],"ast.literal_eval(DictComp.value)")
        self.assertEqual(event_evidence["line_start"],event_evidence["line_end"])
        true_data=self.inspect(BASE_SOURCE.replace("{btn:False for btn", "{btn:True for btn"))
        self.assertIs(true_data["button_input"]["event_default"]["value"],True)
        nonliteral=self.inspect(BASE_SOURCE.replace("{btn:False for btn", "{btn:self.default for btn"))
        self.assertEqual(nonliteral["button_input"]["event_default"]["status"],"UNKNOWN_HARDWARE")
        conflicting=self.inspect(BASE_SOURCE.replace(
            "result={btn:False for btn in self.engine.get_buttons()}",
            "result={btn:False for btn in self.engine.get_buttons()}\n  other={btn:True for btn in self.engine.get_buttons()}"))
        self.assertEqual(conflicting["button_input"]["event_default"]["status"],"UNKNOWN_HARDWARE")

    def test_conflicting_button_dictionaries_are_unknown(self):
        marker='  buttons={"btn_a":False,"btn_b":False,"btn_up":False,"btn_right":False,"btn_left":False,"btn_down":False,"btn_home":False,"btn_reserved":False}'
        identical=self.inspect(BASE_SOURCE.replace(marker,marker+'\n  same={"btn_a":True,"btn_b":True,"btn_up":True,"btn_right":True,"btn_left":True,"btn_down":True,"btn_home":True,"btn_reserved":True}'))
        self.assertEqual(identical["button_input"]["keys"]["status"],"VERIFIED_PACKAGE_SOURCE")
        conflicting=self.inspect(BASE_SOURCE.replace(marker,marker+'\n  other={"btn_x":False}'))
        self.assertEqual(conflicting["button_input"]["keys"]["status"],"UNKNOWN_HARDWARE")

    def test_brightness_bounds_and_persistence_operations_are_extracted(self):
        data=self.inspect()
        self.assertEqual(data["brightness"]["bounds"]["value"],[10,100])
        changed=self.inspect(BASE_SOURCE.replace("10 <= brightness <= 100","20 <= brightness <= 80"))
        self.assertEqual(changed["brightness"]["bounds"]["value"],[20,80])
        operations=data["persistence"]["operations"]
        for name in ("json.load","json.dump","os.replace"): self.assertIn(name,operations)
        self.assertEqual(data["persistence"]["temporary_suffix"]["value"],".tmp")
        removed=self.inspect(BASE_SOURCE.replace("; os.replace(temp_file,self.data_store_file)",""))
        self.assertNotIn("os.replace",removed["persistence"]["operations"])

    def test_temporary_suffix_is_literal_derived_and_ambiguity_is_unknown(self):
        data=self.inspect(); self.assertEqual(data["persistence"]["temporary_suffix"]["value"],".tmp")
        suffix_claim=next(c for c in data["claims"] if c["topic"]=="persistence.temporary_suffix")
        suffix_evidence=next(e for e in data["evidence"] if e["evidence_id"] in suffix_claim["evidence_ids"])
        self.assertEqual(suffix_evidence["extraction_method"],"ast.Constant temporary-path suffix")
        self.assertEqual(suffix_evidence["line_start"],suffix_evidence["line_end"])
        backup=self.inspect(BASE_SOURCE.replace('self.data_store_file+".tmp"','self.data_store_file+".tmp-backup"'))
        self.assertEqual(backup["persistence"]["temporary_suffix"]["value"],".tmp-backup")
        nonliteral=self.inspect(BASE_SOURCE.replace('self.data_store_file+".tmp"','self.data_store_file+suffix'))
        self.assertEqual(nonliteral["persistence"]["temporary_suffix"]["status"],"UNKNOWN_HARDWARE")
        conflicting=self.inspect(BASE_SOURCE.replace(
            'temp_file=self.data_store_file+".tmp"',
            'temp_file=self.data_store_file+".tmp"\n  temp_backup=self.data_store_file+".bak"'))
        self.assertEqual(conflicting["persistence"]["temporary_suffix"]["status"],"UNKNOWN_HARDWARE")

    def test_constructor_options_are_extracted_and_change(self):
        data=self.inspect(); self.assertEqual(data["constructor"]["options"]["--shm"]["default"],"pdishm")
        changed=self.inspect(BASE_SOURCE.replace('default="pdishm"','default="other"'))
        self.assertEqual(changed["constructor"]["options"]["--shm"]["default"],"other")

    def test_duplicate_constructor_options_identical_or_unknown(self):
        anchor='  p.add_argument("--shm", default="pdishm")'
        identical=self.inspect(BASE_SOURCE.replace(anchor,anchor+'\n'+anchor))
        option=identical["constructor"]["options"]["--shm"]
        self.assertEqual(option["status"],"VERIFIED_PACKAGE_SOURCE")
        claim=next(c for c in identical["claims"] if c["claim_id"]==option["claim_ids"][0])
        self.assertEqual(len(claim["evidence_ids"]),2)
        conflicting=self.inspect(BASE_SOURCE.replace(anchor,anchor+'\n  p.add_argument("--shm", default="other")'))
        self.assertEqual(conflicting["constructor"]["options"]["--shm"]["status"],"UNKNOWN_HARDWARE")
        implicit=self.inspect(BASE_SOURCE.replace(anchor,anchor+'\n  p.add_argument("--shm")'))
        self.assertEqual(implicit["constructor"]["options"]["--shm"]["status"],"UNKNOWN_HARDWARE")

    def test_claim_and_evidence_integrity_and_precise_lines(self):
        data=self.inspect(); evidence={e["evidence_id"]:e for e in data["evidence"]}
        ids=[c["claim_id"] for c in data["claims"]]; self.assertEqual(len(ids),len(set(ids)))
        source=BASE_SOURCE.splitlines()
        for claim in data["claims"]:
            if claim["status"].startswith("VERIFIED"):
                self.assertTrue(claim["evidence_ids"])
                for eid in claim["evidence_ids"]:
                    self.assertIn(eid,evidence)
                    e=evidence[eid]
                    if e["archive_path"].endswith(".py"):
                        snippet="\n".join(source[e["line_start"]-1:e["line_end"]])
                        self.assertTrue(snippet.strip())
                        self.assertIn("ast.",e["extraction_method"])

    def test_determinism_sorting_newline_and_check_helper(self):
        with tempfile.TemporaryDirectory() as td:
            p=wheel(Path(td)); data=synthetic(p); rendered=serialize(data)
            self.assertEqual(data,synthetic(p)); self.assertTrue(rendered.endswith("\n")); self.assertFalse(rendered.endswith("\n\n"))
            self.assertLess(rendered.index('"claims"'),rendered.index('"constructor"'))


class SecondarySearchTests(unittest.TestCase):
    def inspect(self, source=BASE_SOURCE, **kwargs):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        return synthetic(wheel(Path(temp.name),source,**kwargs))

    def test_complete_empty_search_reports_scoped_absence(self):
        section=self.inspect()["secondary_display"]
        self.assertEqual(section["status"],"NOT_FOUND_IN_INSPECTED_PACKAGE")
        for key in ("matching_symbols","matching_source_locations","public_api_candidates","metadata_matches","record_matches","text_file_matches"):
            self.assertEqual(section[key],[])
        self.assertIn("No secondary-display API",section["finding"])

    def test_metadata_only_match_is_unknown_hardware(self):
        data=self.inspect(description="A scoreboard description",extra={"notes.txt":"auxiliary output"})
        section=data["secondary_display"]
        self.assertTrue(section["metadata_matches"]); self.assertTrue(section["text_file_matches"])
        self.assertEqual(section["status"],"UNKNOWN_HARDWARE")

    def test_module_function_string_symbol_and_candidates_are_generated(self):
        source=BASE_SOURCE+'\ndef secondary_screen():\n text="widget_display mode"\n return text\n'
        section=self.inspect(source)["secondary_display"]
        names={x["name"] for x in section["matching_symbols"]}
        candidates={x["name"] for x in section["public_api_candidates"]}
        self.assertIn("secondary_screen",names); self.assertIn("secondary_screen",candidates)
        self.assertEqual(section["status"],"VERIFIED_PACKAGE_SOURCE")
        self.assertTrue(any(x["kind"]=="string_constant" for x in section["matching_source_locations"]))
        self.assertNotIn("No secondary-display API",section["finding"])

    def test_record_paths_are_searched(self):
        data=self.inspect(extra={"scoreboard.txt":"plain"})
        self.assertTrue(data["secondary_display"]["record_matches"] or data["secondary_display"]["text_file_matches"])


class CommittedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.data=json.loads(CONTRACT.read_text()); cls.doc=DOC.read_text()

    def test_schema_identity_hashes_and_counts(self):
        p=self.data["package"]
        self.assertEqual(self.data["schema_version"],1); self.assertEqual(p["name"],"pydartsnut"); self.assertEqual(p["version"],"1.2.1")
        self.assertEqual(p["wheel_filename"],WHEEL_FILENAME); self.assertEqual(p["wheel_sha256"],WHEEL_SHA256); self.assertEqual(p["sdist_sha256"],SDIST_SHA256)
        self.assertEqual(self.data["inspection"]["generated_claim_count"],len(self.data["claims"]))

    def test_every_verified_claim_has_existing_precise_evidence(self):
        evidence={e["evidence_id"]:e for e in self.data["evidence"]}
        for claim in self.data["claims"]:
            if claim["status"].startswith("VERIFIED"):
                self.assertTrue(claim["evidence_ids"],claim["claim_id"])
                for eid in claim["evidence_ids"]:
                    self.assertIn(eid,evidence); e=evidence[eid]
                    self.assertGreaterEqual(e["line_end"],e["line_start"]); self.assertTrue(e["archive_path"]); self.assertRegex(e["source_sha256"],r"^[0-9a-f]{64}$")

    def test_all_section_claim_references_exist(self):
        claims={c["claim_id"] for c in self.data["claims"]}
        def visit(value):
            if isinstance(value,dict):
                for k,v in value.items():
                    if k=="claim_ids": self.assertLessEqual(set(v),claims)
                    else: visit(v)
            elif isinstance(value,list):
                for x in value: visit(x)
        for section in ("constructor","main_display","dart_input","button_input","lifecycle","brightness","widget_parameters","persistence","secondary_display"): visit(self.data[section])

    def test_document_claim_references_valid_and_search_description_accurate(self):
        import re
        claim_ids={c["claim_id"] for c in self.data["claims"]}; evidence_ids={e["evidence_id"] for e in self.data["evidence"]}
        self.assertLessEqual(set(re.findall(r"CLM-\d{3}",self.doc)),claim_ids)
        self.assertLessEqual(set(re.findall(r"\bE\d{3}\b",self.doc)),evidence_ids)
        for phrase in ("METADATA headers","description body","RECORD paths","small UTF-8 text files","module-level functions","string constants"):
            self.assertIn(phrase,self.doc)

    def test_no_color_mapping_or_physical_orientation_is_asserted(self):
        self.assertIn("No player-color mapping is asserted",self.doc)
        self.assertIn("No physical coordinate orientation is asserted",self.doc)

    def test_dependency_lock_and_scope_guards(self):
        self.assertIn('"pydartsnut==1.2.1"',(ROOT/"pyproject.toml").read_text())
        lock=(ROOT/"uv.lock").read_text(); self.assertIn("specifier = \"==1.2.1\"",lock); self.assertIn(WHEEL_SHA256,lock); self.assertIn(SDIST_SHA256,lock)
        tracked=[p.as_posix() for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]
        self.assertFalse(any(p.endswith((".whl",".zip",".tar.gz")) for p in tracked if ".contract_tmp" not in p))


if __name__ == "__main__": unittest.main()
