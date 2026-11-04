package main

import (
	"math"
	"testing"
)

func TestChooseHeroPrefersPlayerResourceSelectedHandle(t *testing.T) {
	selected := map[string]interface{}{"m_iPlayerID": int64(2), "m_iCurrentLevel": int64(17)}
	decoy := map[string]interface{}{
		"m_iPlayerID": int64(2), "m_iCurrentLevel": int64(25),
		"m_hItems.0000": uint64(42),
	}
	heroes := map[int32]map[string]interface{}{1377: selected, 2730: decoy}
	classes := map[int32]string{1377: "CDOTA_Unit_Hero_Shadow_Demon", 2730: "CDOTA_Unit_Hero_Pudge"}
	items := map[int32]string{42: "CDOTA_Item_Example"}

	h, cls, idx := chooseHero(1, 7554401, heroes, classes, items)
	if idx != 1377 || cls != "CDOTA_Unit_Hero_Shadow_Demon" || h["m_iCurrentLevel"] != int64(17) {
		t.Fatalf("selected hero handle ignored: idx=%d class=%s", idx, cls)
	}
}

func TestChooseHeroFallsBackWhenSelectedHandleIsInvalid(t *testing.T) {
	decoy := map[string]interface{}{
		"m_iPlayerID": int64(2), "m_iCurrentLevel": int64(25),
		"m_hItems.0000": uint64(42),
	}
	heroes := map[int32]map[string]interface{}{2730: decoy}
	classes := map[int32]string{2730: "CDOTA_Unit_Hero_Pudge"}
	items := map[int32]string{42: "CDOTA_Item_Example"}

	h, cls, idx := chooseHero(1, 0, heroes, classes, items)
	if idx != 2730 || cls != "CDOTA_Unit_Hero_Pudge" || h["m_iCurrentLevel"] != int64(25) {
		t.Fatalf("fallback hero selection failed: idx=%d class=%s", idx, cls)
	}
}

func TestHasNumberPreservesZeroAndRejectsAbsentOrInvalid(t *testing.T) {
	for _, value := range []interface{}{int32(0), uint64(5), float32(0), float64(12)} {
		if !hasNumber(value) {
			t.Fatalf("valid source value rejected: %v", value)
		}
	}
	for _, value := range []interface{}{nil, true, "0", int64(-1), math.NaN(), math.Inf(1)} {
		if hasNumber(value) {
			t.Fatalf("invalid source value accepted: %v", value)
		}
	}
}
