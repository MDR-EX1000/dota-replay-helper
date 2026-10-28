package main

import (
	"math"
	"testing"
)

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
