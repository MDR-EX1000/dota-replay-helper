package main

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"

	"github.com/dotabuff/manta"
	"github.com/dotabuff/manta/dota"
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
	p.OnEntity(func(e *manta.Entity, op manta.EntityOp) error {
		if e.GetClassName() == "CDOTA_PlayerResource" {
			pr = e.Map()
		}
		return nil
	})

	p.Callbacks.OnCDemoFileInfo(func(m *dota.CDemoFileInfo) error {
		g := m.GetGameInfo().GetDota()
		fmt.Println("FILEINFO match_id:", g.GetMatchId())
		fmt.Println("FILEINFO game_mode:", g.GetGameMode())
		fmt.Println("FILEINFO game_winner:", g.GetGameWinner())
		fmt.Println("FILEINFO end_time:", g.GetEndTime())
		for _, pi := range g.GetPlayerInfo() {
			fmt.Printf("PLAYERINFO hero=%q name=%q steamid=%d game_team=%d\n",
				pi.GetHeroName(), pi.GetPlayerName(), pi.GetSteamid(), pi.GetGameTeam())
		}
		return nil
	})

	if err := p.Start(); err != nil {
		fmt.Println("parse err:", err)
	}

	if pr == nil {
		fmt.Println("NO PLAYER RESOURCE")
		return
	}
	keys := make([]string, 0, len(pr))
	for k := range pr {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		fmt.Printf("%s = %v\n", k, pr[k])
	}

	b, _ := json.MarshalIndent(pr, "", "  ")
	os.WriteFile("playerresource.json", b, 0644)
}
