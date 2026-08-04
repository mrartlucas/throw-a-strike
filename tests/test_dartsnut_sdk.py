import dataclasses
import sys
import unittest

import throw_a_strike.platform as platform
from throw_a_strike.platform import (
    DartsnutButtonId, DartsnutSdkFacade, DartsnutSdkOperation, DartsnutSdkOperationError,
    DartsnutSdkProtocol, FakeDartsnutSdk, InvalidDartsnutSdkResponseError,
    InvalidDartsnutSdkValueError, RawDartHit,
)


class RawSdk:
    def __init__(self):
        self.running = True; self.hits = []; self.buttons = {b.value: False for b in DartsnutButtonId}
        self.frame_result = True; self.none_result = None; self.received = []; self.counts = {}
    def _call(self, name): self.counts[name] = self.counts.get(name, 0) + 1
    def get_dart_hits(self): self._call("hits"); return self.hits
    def get_button_events(self): self._call("buttons"); return self.buttons
    def reset_blocking_state(self): self._call("reset"); return self.none_result
    def update_frame_buffer(self, frame): self._call("frame"); self.received.append(frame); return self.frame_result
    def set_brightness(self, brightness): self._call("brightness"); return self.none_result
    def close(self): self._call("close"); return self.none_result


class PublicTypeTests(unittest.TestCase):
    def test_button_enum_exact_and_ordered(self):
        self.assertEqual([(x.name, x.value) for x in DartsnutButtonId], [("A","btn_a"),("B","btn_b"),("UP","btn_up"),("RIGHT","btn_right"),("LEFT","btn_left"),("DOWN","btn_down"),("HOME","btn_home"),("RESERVED","btn_reserved")])
    def test_operation_enum_exact(self):
        self.assertEqual([x.value for x in DartsnutSdkOperation], ["running_state","dart_hits","button_events","reset_blocking_state","framebuffer_submission","brightness","close"])
    def test_hit_frozen_and_boundaries(self):
        for hit in (RawDartHit(0,0,0), RawDartHit(11,127,127)): self.assertIs(type(hit), RawDartHit)
        with self.assertRaises(dataclasses.FrozenInstanceError): RawDartHit(0,0,0).x = 1
    def test_hit_rejects_types(self):
        for values in ((False,0,0),(0,True,0),(0,0,False),(1.0,0,0),("1",0,0)):
            with self.subTest(values=values), self.assertRaises(InvalidDartsnutSdkValueError): RawDartHit(*values)
    def test_hit_rejects_ranges(self):
        for values in ((-1,0,0),(12,0,0),(0,-1,0),(0,128,0),(0,0,-1),(0,0,128)):
            with self.subTest(values=values), self.assertRaises(InvalidDartsnutSdkValueError): RawDartHit(*values)
    def test_exports_complete(self):
        expected = {"DartsnutButtonId","RawDartHit","DartsnutSdkOperation","DartsnutSdkProtocol","DartsnutSdkFacade","FakeDartsnutSdk","InvalidDartsnutSdkValueError","InvalidDartsnutSdkResponseError","DartsnutSdkOperationError"}
        self.assertEqual(set(platform.__all__), expected)


class ConstructionTests(unittest.TestCase):
    def test_constructs_without_calls_or_running_read(self):
        class S(RawSdk):
            @property
            def running(self): raise AssertionError("read")
            @running.setter
            def running(self, value): pass
        sdk=S(); DartsnutSdkFacade(sdk); self.assertEqual(sdk.counts,{})
    def test_rejects_none_and_classes(self):
        for value in (None, RawSdk):
            with self.assertRaises(InvalidDartsnutSdkValueError): DartsnutSdkFacade(value)
    def test_rejects_each_missing_or_noncallable_method(self):
        for name in ("get_dart_hits", "get_button_events", "reset_blocking_state", "update_frame_buffer", "set_brightness", "close"):
            sdk=RawSdk(); setattr(sdk,name,None)
            with self.subTest(name=name), self.assertRaises(InvalidDartsnutSdkValueError): DartsnutSdkFacade(sdk)
    def test_no_public_sdk_property_or_import(self):
        facade=DartsnutSdkFacade(RawSdk())
        self.assertFalse(hasattr(facade,"sdk")); self.assertNotIn("pydartsnut",sys.modules)


class FacadeTests(unittest.TestCase):
    def setUp(self): self.sdk=RawSdk(); self.facade=DartsnutSdkFacade(self.sdk)
    def test_running_fresh_true_and_false(self):
        self.assertTrue(self.facade.is_running()); self.sdk.running=False; self.assertFalse(self.facade.is_running())
    def test_running_malformed(self):
        self.sdk.running=1
        with self.assertRaises(InvalidDartsnutSdkResponseError) as caught: self.facade.is_running()
        self.assertIs(caught.exception.operation,DartsnutSdkOperation.RUNNING_STATE)
    def test_running_exception_wrapped_and_chained_once(self):
        cause=LookupError("gone")
        class S(RawSdk):
            @property
            def running(self): self.counts["running"]=self.counts.get("running",0)+1; raise cause
            @running.setter
            def running(self,value): pass
        sdk=S()
        with self.assertRaises(DartsnutSdkOperationError) as caught: DartsnutSdkFacade(sdk).is_running()
        self.assertIs(caught.exception.cause,cause); self.assertIs(caught.exception.__cause__,cause); self.assertEqual(sdk.counts["running"],1)
    def test_darts_empty_and_order_preserved(self):
        self.assertEqual(self.facade.read_dart_hits(),())
        self.sdk.hits=[(11,127,0),(0,0,127),(11,127,0)]
        self.assertEqual(self.facade.read_dart_hits(),(RawDartHit(11,127,0),RawDartHit(0,0,127),RawDartHit(11,127,0)))
        self.assertEqual(self.sdk.counts["hits"],2)
    def test_dart_malformed_shapes_and_values(self):
        for value in ((), [{}], [(0,0)], [(False,0,0)], [(12,0,0)], [(0,128,0)]):
            self.sdk.hits=value
            with self.subTest(value=value), self.assertRaises(InvalidDartsnutSdkResponseError): self.facade.read_dart_hits()
    def test_dart_operational_error_once(self):
        cause=OSError("bad")
        def fail(): self.sdk._call("hits"); raise cause
        self.sdk.get_dart_hits=fail; facade=DartsnutSdkFacade(self.sdk)
        with self.assertRaises(DartsnutSdkOperationError) as caught: facade.read_dart_hits()
        self.assertIs(caught.exception.operation,DartsnutSdkOperation.DART_HITS); self.assertIs(caught.exception.__cause__,cause); self.assertEqual(self.sdk.counts["hits"],1)
    def test_buttons_order_and_all_values(self):
        self.assertEqual(self.facade.read_button_events(),())
        self.sdk.buttons={b.value: b in (DartsnutButtonId.RESERVED,DartsnutButtonId.A,DartsnutButtonId.HOME) for b in reversed(tuple(DartsnutButtonId))}
        self.assertEqual(self.facade.read_button_events(),(DartsnutButtonId.A,DartsnutButtonId.HOME,DartsnutButtonId.RESERVED))
        self.sdk.buttons={b.value:True for b in DartsnutButtonId}; self.assertEqual(self.facade.read_button_events(),tuple(DartsnutButtonId))
    def test_button_malformed(self):
        class D(dict): pass
        valid={b.value:False for b in DartsnutButtonId}
        cases=[D(valid),{},dict(valid,extra=False),{**valid,"btn_a":1},{**valid,1:False}]
        for value in cases:
            self.sdk.buttons=value
            with self.subTest(value=value), self.assertRaises(InvalidDartsnutSdkResponseError): self.facade.read_button_events()
    def test_button_error_wrapped_once(self):
        cause=RuntimeError("bad")
        def fail(): self.sdk._call("buttons"); raise cause
        self.sdk.get_button_events=fail; facade=DartsnutSdkFacade(self.sdk)
        with self.assertRaises(DartsnutSdkOperationError) as caught: facade.read_button_events()
        self.assertIs(caught.exception.operation,DartsnutSdkOperation.BUTTON_EVENTS); self.assertIs(caught.exception.__cause__,cause); self.assertEqual(self.sdk.counts["buttons"],1)
    def test_reset_explicit_and_return_validation(self):
        self.facade.read_dart_hits(); self.assertNotIn("reset",self.sdk.counts)
        self.assertIsNone(self.facade.reset_blocking_state()); self.facade.reset_blocking_state(); self.assertEqual(self.sdk.counts["reset"],2)
        self.sdk.none_result=False
        with self.assertRaises(InvalidDartsnutSdkResponseError): self.facade.reset_blocking_state()
    def test_framebuffer_copy_arbitrary_content_and_results(self):
        caller=bytearray(b"abc"); self.assertTrue(self.facade.submit_framebuffer(caller)); self.assertEqual(caller,b"abc")
        self.assertIsNot(self.sdk.received[0],caller); self.assertEqual(self.sdk.received[0],caller)
        self.sdk.frame_result=False; self.assertFalse(self.facade.submit_framebuffer(b"")); self.assertEqual(self.sdk.counts["frame"],2)
        self.assertTrue(self.sdk.received[0] is not self.sdk.received[1])
    def test_framebuffer_rejects_wrong_types_and_subclasses(self):
        class B(bytes): pass
        class BA(bytearray): pass
        for value in (B(),BA(),memoryview(b"x"),"x"):
            with self.subTest(value=value), self.assertRaises(InvalidDartsnutSdkValueError): self.facade.submit_framebuffer(value)
    def test_framebuffer_malformed_result(self):
        self.sdk.frame_result=1
        with self.assertRaises(InvalidDartsnutSdkResponseError): self.facade.submit_framebuffer(b"12345")
    def test_brightness_boundaries_middle_and_invalid(self):
        for value in (10,55,100): self.assertIsNone(self.facade.set_brightness(value))
        self.assertEqual(self.sdk.counts["brightness"],3)
        for value in (9,101,True,10.0,"10"):
            with self.assertRaises(InvalidDartsnutSdkValueError): self.facade.set_brightness(value)
        self.assertEqual(self.sdk.counts["brightness"],3)
    def test_close_repeats_and_validates(self):
        self.assertIsNone(self.facade.close()); self.facade.close(); self.assertEqual(self.sdk.counts["close"],2)
        self.sdk.none_result=True
        with self.assertRaises(InvalidDartsnutSdkResponseError): self.facade.close()
    def test_operation_failures_for_void_and_frame_methods(self):
        for method, operation, invoke in (("reset_blocking_state",DartsnutSdkOperation.RESET_BLOCKING_STATE,self.facade.reset_blocking_state),("update_frame_buffer",DartsnutSdkOperation.FRAMEBUFFER_SUBMISSION,lambda:self.facade.submit_framebuffer(b"x")),("set_brightness",DartsnutSdkOperation.BRIGHTNESS,lambda:self.facade.set_brightness(10)),("close",DartsnutSdkOperation.CLOSE,self.facade.close)):
            sdk=RawSdk(); cause=OSError(method)
            def fail(*args, _cause=cause): raise _cause
            setattr(sdk,method,fail); facade=DartsnutSdkFacade(sdk)
            action={"reset_blocking_state":facade.reset_blocking_state,"update_frame_buffer":lambda:facade.submit_framebuffer(b"x"),"set_brightness":lambda:facade.set_brightness(10),"close":facade.close}[method]
            with self.subTest(method=method), self.assertRaises(DartsnutSdkOperationError) as caught: action()
            self.assertIs(caught.exception.operation,operation); self.assertIs(caught.exception.__cause__,cause)


class ErrorTests(unittest.TestCase):
    def test_response_error_validation_and_read_only(self):
        error=InvalidDartsnutSdkResponseError(DartsnutSdkOperation.DART_HITS,"bad data")
        self.assertEqual(error.detail,"bad data"); self.assertIs(error.operation,DartsnutSdkOperation.DART_HITS)
        for operation,detail in (("dart_hits","x"),(DartsnutSdkOperation.DART_HITS,""),(DartsnutSdkOperation.DART_HITS," x"),(DartsnutSdkOperation.DART_HITS,1)):
            with self.assertRaises(InvalidDartsnutSdkValueError): InvalidDartsnutSdkResponseError(operation,detail)
        with self.assertRaises(AttributeError): error.detail="x"
    def test_operation_error_validation_and_identity(self):
        cause=ValueError("x"); error=DartsnutSdkOperationError(DartsnutSdkOperation.CLOSE,cause); self.assertIs(error.cause,cause)
        for operation,bad in (("close",cause),(DartsnutSdkOperation.CLOSE,BaseException()),(DartsnutSdkOperation.CLOSE,"x")):
            with self.assertRaises(InvalidDartsnutSdkValueError): DartsnutSdkOperationError(operation,bad)
        with self.assertRaises(AttributeError): error.cause=ValueError()


class FakeTests(unittest.TestCase):
    def test_protocol_and_running(self):
        fake=FakeDartsnutSdk(); self.assertIsInstance(fake,DartsnutSdkProtocol); self.assertTrue(fake.running); fake.set_running(False); self.assertFalse(fake.running); self.assertEqual(fake.calls, (DartsnutSdkOperation.RUNNING_STATE,) * 2)
    def test_fifo_darts_fresh_empty_lists_and_counts(self):
        fake=FakeDartsnutSdk(); a=(RawDartHit(0,1,2),); b=(RawDartHit(1,3,4),); fake.queue_dart_hits(a); fake.queue_dart_hits(b); self.assertEqual(fake.queued_dart_batch_count,2)
        self.assertEqual(fake.get_dart_hits(),[(0,1,2)]); self.assertEqual(fake.get_dart_hits(),[(1,3,4)]); x=fake.get_dart_hits(); y=fake.get_dart_hits(); self.assertEqual(x,[]); self.assertIsNot(x,y)
    def test_fifo_buttons_all_keys_duplicates_and_counts(self):
        fake=FakeDartsnutSdk(); fake.queue_button_events((DartsnutButtonId.HOME,DartsnutButtonId.A)); self.assertEqual(fake.queued_button_batch_count,1)
        result=fake.get_button_events(); self.assertEqual(list(result),[b.value for b in DartsnutButtonId]); self.assertTrue(result["btn_home"]); self.assertTrue(result["btn_a"])
        self.assertFalse(any(fake.get_button_events().values()))
        with self.assertRaises(InvalidDartsnutSdkValueError): fake.queue_button_events((DartsnutButtonId.A,DartsnutButtonId.A))
    def test_framebuffer_fifo_default_and_immutable_history(self):
        fake=FakeDartsnutSdk(); fake.queue_framebuffer_result(False); fake.queue_framebuffer_result(True); self.assertEqual(fake.queued_framebuffer_result_count,2)
        data=bytearray(b"a"); self.assertFalse(fake.update_frame_buffer(data)); data[0]=98; self.assertTrue(fake.update_frame_buffer(bytearray())); self.assertTrue(fake.update_frame_buffer(bytearray(b"c"))); self.assertEqual(fake.submitted_framebuffers,(b"a",b"",b"c"))
    def test_histories_counts_and_immutability(self):
        fake=FakeDartsnutSdk(); fake.reset_blocking_state(); fake.reset_blocking_state(); fake.set_brightness(25); fake.close()
        self.assertEqual(fake.reset_blocking_count,2); self.assertEqual(fake.close_count,1); self.assertEqual(fake.brightness_values,(25,)); self.assertIs(type(fake.calls),tuple)
    def test_setup_rejects_wrong_mutable_types(self):
        fake=FakeDartsnutSdk()
        for action in (lambda:FakeDartsnutSdk(1),lambda:fake.set_running(1),lambda:fake.queue_dart_hits([]),lambda:fake.queue_dart_hits((object(),)),lambda:fake.queue_button_events([]),lambda:fake.queue_button_events(("btn_a",)),lambda:fake.queue_framebuffer_result(1)):
            with self.assertRaises(InvalidDartsnutSdkValueError): action()


if __name__ == "__main__": unittest.main()
