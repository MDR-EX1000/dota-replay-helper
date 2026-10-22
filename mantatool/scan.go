package main

import (
	"encoding/json"
	"fmt"
	"os"
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

	var pr map[string]interface{}
	teamData := map[string]map[string]interface{}{}
	var gamerules map[string]interface{}
	heroes := map[int32]map[string]interface{}{}
	classes := map[string]bool{}

	p.OnEntity(func(e *manta.Entity, op manta.EntityOp) error {
		cn := e.GetClassName()
		classes[cn] = true
		if cn == "CDOTA_PlayerResource" {
			pr = e.Map()
		}
		if cn == "CDOTA_DataRadiant" || cn == "CDOTA_DataDire" {
			teamData[cn] = e.Map()
		}
		if cn == "CDOTAGamerulesProxy" {
			gamerules = e.Map()
		}
		if strings.HasPrefix(cn, "CDOTA_Unit_Hero") {
			heroes[e.GetIndex()] = e.Map()
		}
		return nil
	})

	if err := p.Start(); err != nil {
		fmt.Println("parse err:", err)
	}

	b, _ := json.MarshalIndent(pr, "", "  ")
	os.WriteFile("pr_final.json", b, 0644)
	hj := map[string]map[string]interface{}{}
	for idx, h := range heroes {
		hj[fmt.Sprint(idx)] = h
	}
	b, _ = json.MarshalIndent(hj, "", "  ")
	os.WriteFile("heroes_final.json", b, 0644)
	b, _ = json.MarshalIndent(teamData, "", "  ")
	os.WriteFile("teamdata_final.json", b, 0644)
	b, _ = json.MarshalIndent(gamerules, "", "  ")
	os.WriteFile("gamerules_final.json", b, 0644)

	var sb strings.Builder
	for c := range classes {
		sb.WriteString(c + "\n")
	}
	os.WriteFile("classes.txt", []byte(sb.String()), 0644)
	fmt.Println("heroes:", len(heroes), "classes:", len(classes))
}
