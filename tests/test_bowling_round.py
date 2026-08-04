import unittest
from dataclasses import FrozenInstanceError

from throw_a_strike.domain import (
    BowlingRoundMachine, BowlingRoundSnapshot, BowlingThrowNumber, BowlingThrowResult,
    BowlingThrowResultKind, InvalidBowlingRoundValueError,
    expected_emulator_dart_index, is_expected_emulator_dart,
)

RACK=tuple(range(1,11))

def result(kind=BowlingThrowResultKind.MISS, before=RACK, knocked=(), after=None,
           dart=0, x=1, y=2):
    if after is None: after=tuple(pin for pin in before if pin not in knocked)
    if kind is BowlingThrowResultKind.FOUL: dart=x=y=None
    return BowlingThrowResult(kind,before,knocked,after,dart,x,y)

class RoundTests(unittest.TestCase):
    def test_snapshot_accepts_only_three_continuous_round_states(self):
        first=result(BowlingThrowResultKind.PIN_HIT,knocked=(1,))
        second=result(BowlingThrowResultKind.MISS,before=first.pins_after,
                      after=first.pins_after,dart=4)
        valid=(
            BowlingRoundSnapshot(BowlingThrowNumber.THROW_ONE,RACK,RACK,None,None,False),
            BowlingRoundSnapshot(BowlingThrowNumber.THROW_TWO,RACK,first.pins_after,first,None,False),
            BowlingRoundSnapshot(BowlingThrowNumber.THROW_TWO,RACK,second.pins_after,first,second,True),
        )
        self.assertEqual(len(valid),3)

    def test_snapshot_rejects_impossible_phase_and_result_combinations(self):
        first=result(); other=result(before=(1,2),after=(1,2),dart=4)
        invalid=(
            (BowlingThrowNumber.THROW_TWO,RACK,RACK,None,None,True),
            (BowlingThrowNumber.THROW_ONE,RACK,RACK,first,None,False),
            (BowlingThrowNumber.THROW_TWO,RACK,RACK,None,None,False),
            (BowlingThrowNumber.THROW_TWO,(1,2),(1,2),first,None,False),
            (BowlingThrowNumber.THROW_TWO,RACK,(1,2),first,other,True),
            (BowlingThrowNumber.THROW_ONE,(1,2),(1,3),None,None,False),
            (BowlingThrowNumber.THROW_TWO,RACK,(1,2),first,None,False),
        )
        for values in invalid:
            with self.subTest(values=values),self.assertRaises(InvalidBowlingRoundValueError):
                BowlingRoundSnapshot(*values)

    def test_initial_full_and_custom_racks(self):
        full=BowlingRoundMachine().snapshot
        self.assertEqual((full.throw_number,full.opening_rack,full.standing_pins,
                          full.first_result,full.second_result,full.complete),
                         (BowlingThrowNumber.THROW_ONE,RACK,RACK,None,None,False))
        self.assertEqual(BowlingRoundMachine((1,4,10)).snapshot.standing_pins,(1,4,10))

    def test_two_results_advance_and_complete_but_third_is_rejected(self):
        machine=BowlingRoundMachine(); first=result()
        snap=machine.record_throw(first)
        self.assertEqual((snap.throw_number,snap.first_result,snap.complete),
                         (BowlingThrowNumber.THROW_TWO,first,False))
        second=result(BowlingThrowResultKind.PIN_HIT,knocked=(2,7))
        snap=machine.record_throw(second)
        self.assertTrue(snap.complete); self.assertIs(snap.second_result,second)
        self.assertEqual(snap.standing_pins,(1,3,4,5,6,8,9,10))
        with self.assertRaises(InvalidBowlingRoundValueError): machine.record_throw(result())

    def test_zero_vocabulary_preserves_rack(self):
        for kind in (BowlingThrowResultKind.GUTTER,BowlingThrowResultKind.MISS,
                     BowlingThrowResultKind.FIELD_GOAL):
            with self.subTest(kind=kind): self.assertEqual(result(kind).pins_after,RACK)
        foul=result(BowlingThrowResultKind.FOUL)
        self.assertEqual(foul.pins_after,RACK); self.assertEqual((foul.dart_index,foul.aim_x,foul.aim_y),(None,None,None))

    def test_exact_vocabulary(self):
        self.assertEqual([kind.value for kind in BowlingThrowResultKind],
                         ["gutter","miss","field_goal","foul","pin_hit"])
        self.assertIsNot(BowlingThrowResultKind.GUTTER,BowlingThrowResultKind.MISS)

    def test_invalid_pin_and_result_relationships(self):
        bad=(RACK+(10,), (0,), (11,), (2,1))
        for pins in bad:
            with self.subTest(pins=pins),self.assertRaises(InvalidBowlingRoundValueError):
                result(before=pins,after=pins)
        with self.assertRaises(InvalidBowlingRoundValueError): result(BowlingThrowResultKind.PIN_HIT,knocked=(1,),after=RACK)
        with self.assertRaises(InvalidBowlingRoundValueError): result(BowlingThrowResultKind.PIN_HIT,before=(2,),knocked=(1,),after=(2,))
        with self.assertRaises(InvalidBowlingRoundValueError): result(BowlingThrowResultKind.PIN_HIT)
        with self.assertRaises(InvalidBowlingRoundValueError):
            BowlingThrowResult(BowlingThrowResultKind.FOUL,RACK,(),RACK,1,None,None)

    def test_values_are_frozen_and_exact_types_are_enforced(self):
        value=result()
        with self.assertRaises(FrozenInstanceError): value.aim_x=4
        for kwargs in ({"dart":True},{"x":True},{"y":False}):
            with self.subTest(kwargs=kwargs),self.assertRaises(InvalidBowlingRoundValueError): result(**kwargs)
        for rack in ([1],(True,)):
            with self.subTest(rack=rack),self.assertRaises(InvalidBowlingRoundValueError): BowlingRoundMachine(rack)
        with self.assertRaises(InvalidBowlingRoundValueError): BowlingRoundMachine().record_throw(object())

class DartPolicyTests(unittest.TestCase):
    def test_all_players_map_only_first_two_same_color_slots(self):
        for player in range(1,5):
            self.assertEqual(expected_emulator_dart_index(player,BowlingThrowNumber.THROW_ONE),player-1)
            self.assertEqual(expected_emulator_dart_index(player,BowlingThrowNumber.THROW_TWO),player+3)
            self.assertFalse(is_expected_emulator_dart(player,BowlingThrowNumber.THROW_TWO,player+7))

    def test_invalid_values_and_nonmutation(self):
        for player in (True,0,5,1.0):
            with self.assertRaises(InvalidBowlingRoundValueError): expected_emulator_dart_index(player,BowlingThrowNumber.THROW_ONE)
        for throw in (1,3,None):
            with self.assertRaises(InvalidBowlingRoundValueError): expected_emulator_dart_index(1,throw)
        marker=[8]
        self.assertFalse(is_expected_emulator_dart(1,BowlingThrowNumber.THROW_TWO,marker[0])); self.assertEqual(marker,[8])

if __name__ == "__main__": unittest.main()
