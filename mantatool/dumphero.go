package main

import (
	"fmt"
	"os"
	"sort"
	"strings"

	"github.com/dotabuff/manta"
)

func main() {
	f, err := os.Open(os.Args[1])
	if err != nil {
		panic(err)
	}
	defer f.Close()

	p, err := manta.NewStreamParser(f)
	if err != nil {
		panic(err)
	}

	var hero map[string]interface{}
	p.OnEntity(func(e *manta.Entity, op manta.EntityOp) error {
		if hero == nil && strings.HasPrefix(e.GetClassName(), "CDOTA_Unit_Hero") {
			hero = e.Map()
			fmt.Println("CLASS:", e.GetClassName())
		}
		return nil
	})

	if err := p.Start(); err != nil {
		fmt.Println("parse err:", err)
	}

	if hero == nil {
		fmt.Println("NO HERO ENTITY")
		return
	}
	keys := make([]string, 0, len(hero))
	for k := range hero {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		fmt.Printf("%s = %v\n", k, hero[k])
	}
}
