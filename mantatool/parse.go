package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/dotabuff/manta"
	"github.com/dotabuff/manta/dota"
)

var gameModes = map[int32]string{
	1: "All Pick", 2: "Captains Mode", 3: "Random Draft", 4: "Single Draft",
	5: "All Random", 11: "Mid Only", 12: "Least Played", 16: "Captains Draft",
	18: "Ability Draft", 20: "All Random Deathmatch", 21: "1v1 Mid", 22: "All Pick", 23: "Turbo",
}

func asUint64(v interface{}) (uint64, bool) {
	switch t := v.(type) {
	case uint64:
		return t, true
	case uint32:
		return uint64(t), true
	case int32:
		return uint64(uint32(t)), true
	case int64:
		return uint64(t), true
	case float64:
		return uint64(t), true
	}
	return 0, false
}

func asInt(v interface{}) int64 {
	switch t := v.(type) {
	case int32:
		return int64(t)
	case uint32:
		return int64(t)
	case int64:
		return t
	case uint64:
		return int64(t)
	case float32:
		return int64(t)
	case float64:
		return int64(t)
	}
	return 0
}

func asFloat(v interface{}) float64 {
	switch t := v.(type) {
	case float32:
		return float64(t)
	case float64:
		return t
	case int32:
		return float64(t)
	case uint32:
		return float64(t)
	case int64:
		return float64(t)
	case uint64:
		return float64(t)
	}
	return 0
}

func asString(v interface{}) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}

func snake(s string) string {
	var b strings.Builder
	for i, r := range s {
		if r >= 'A' && r <= 'Z' {
			if i > 0 && s[i-1] != '_' {
				b.WriteByte('_')
			}
			b.WriteRune(r + ('a' - 'A'))
		} else {
			b.WriteRune(r)
		}
	}
	return b.String()
}

func itemName(class string) string {
	n := strings.TrimPrefix(class, "CDOTA_Item_")
	if strings.HasPrefix(n, "Recipe_") {
		return ""
	}
	return snake(n)
}

func parse(path, outDir string) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()

	p, err := manta.NewStreamParser(f)
	if err != nil {
		return err
	}

	var pr map[string]interface{}
	var gamerules map[string]interface{}
	teamData := map[string]map[string]interface{}{}
	heroes := map[int32]map[string]interface{}{}
	heroClass := map[int32]string{}
	itemClass := map[int32]string{}

	var matchID uint64
	var gameMode, gameWinner, endTime int64

	p.Callbacks.OnCDemoFileInfo(func(m *dota.CDemoFileInfo) error {
		g := m.GetGameInfo().GetDota()
		matchID = g.GetMatchId()
		gameMode = int64(g.GetGameMode())
		gameWinner = int64(g.GetGameWinner())
		endTime = int64(g.GetEndTime())
		return nil
	})

	p.OnEntity(func(e *manta.Entity, op manta.EntityOp) error {
		cn := e.GetClassName()
		switch {
		case cn == "CDOTA_PlayerResource":
			pr = e.Map()
		case cn == "CDOTA_DataRadiant" || cn == "CDOTA_DataDire":
			teamData[cn] = e.Map()
		case cn == "CDOTAGamerulesProxy":
			gamerules = e.Map()
		case strings.HasPrefix(cn, "CDOTA_Unit_Hero"):
			heroes[e.GetIndex()] = e.Map()
			heroClass[e.GetIndex()] = cn
		case strings.HasPrefix(cn, "CDOTA_Item_"):
			itemClass[e.GetIndex()] = cn
		}
		return nil
	})

	if err := p.Start(); err != nil {
		return err
	}

	fmt.Println("parsed", filepath.Base(path), "match_id", matchID, "heroes", len(heroes), "items", len(itemClass))

	// game timing
	startClock := asFloat(gamerules["m_pGameRules.m_flGameStartTime"])
	endClock := asFloat(gamerules["m_pGameRules.m_flGameEndTime"])
	duration := endClock - startClock
	if duration <= 0 {
		duration = endClock
	}

	// index player data by steamid to pull per-player team stats
	type teamStats struct {
		netWorth, earnedGold, earnedXP, lastHits, denies int64
		heroDamage, towerDamage, healing, stuns          float64
		wardsPlaced, wardsDestroyed                      int64
	}
	statsBySteam := map[uint64]teamStats{}
	for _, td := range teamData {
		for j := 0; j < 10; j++ {
			prefix := fmt.Sprintf("m_vecDataTeam.%04d.", j)
			sid, ok := asUint64(td[prefix+"m_iPlayerSteamID"])
			if !ok || sid == 0 {
				continue
			}
			statsBySteam[sid] = teamStats{
				netWorth:      asInt(td[prefix+"m_iNetWorth"]),
				earnedGold:    asInt(td[prefix+"m_iTotalEarnedGold"]),
				earnedXP:      asInt(td[prefix+"m_iTotalEarnedXP"]),
				lastHits:      asInt(td[prefix+"m_iLastHitCount"]),
				denies:        asInt(td[prefix+"m_iDenyCount"]),
				heroDamage:    asFloat(td[prefix+"m_flHeroDamage"]),
				towerDamage:   asFloat(td[prefix+"m_flTowerDamage"]),
				healing:       asFloat(td[prefix+"m_fHealing"]),
				stuns:         asFloat(td[prefix+"m_fStuns"]),
				wardsPlaced:   asInt(td[prefix+"m_iObserverWardsPlaced"]) + asInt(td[prefix+"m_iSentryWardsPlaced"]),
				wardsDestroyed: asInt(td[prefix+"m_iWardsDestroyed"]),
			}
		}
	}

	// hero entities by player id; duplicates (clones/illusions) are ranked by
	// how many real inventory items they carry, then by final level.
	heroIdxByPlayer := map[int64][]int32{}
	for idx, h := range heroes {
		// current builds store player id doubled (radiant 0,2,4,6,8 / dire 10..18)
		pid := asInt(h["m_iPlayerID"]) / 2
		if pid >= 0 && pid < 10 {
			heroIdxByPlayer[pid] = append(heroIdxByPlayer[pid], idx)
		}
	}
	countItems := func(h map[string]interface{}) int {
		n := 0
		for slot := 0; slot < 6; slot++ {
			handle, ok := asUint64(h[fmt.Sprintf("m_hItems.%04d", slot)])
			if !ok {
				continue
			}
			if _, ok := itemClass[int32(handle&0x3FFF)]; ok {
				n++
			}
		}
		return n
	}
	bestHero := func(pid int64) (map[string]interface{}, string) {
		var bh map[string]interface{}
		bc := ""
		best := -1
		for _, idx := range heroIdxByPlayer[pid] {
			h := heroes[idx]
			score := countItems(h)*1000 + int(asInt(h["m_iCurrentLevel"]))
			if score > best {
				best = score
				bh = h
				bc = heroClass[idx]
			}
		}
		return bh, bc
	}

	minutes := duration / 60.0
	players := make([]map[string]interface{}, 0, 10)
	for i := 0; i < 10; i++ {
		pp := fmt.Sprintf("m_vecPlayerData.%04d.", i)
		tp := fmt.Sprintf("m_vecPlayerTeamData.%04d.", i)
		steam, _ := asUint64(pr[pp+"m_iPlayerSteamID"])
		team := asInt(pr[pp+"m_iPlayerTeam"])
		teamName := "radiant"
		if team == 3 {
			teamName = "dire"
		}
		st := statsBySteam[steam]

		heroName := ""
		items := make([]string, 0, 6)
		if h, cls := bestHero(int64(i)); h != nil {
			heroName = cls
			for slot := 0; slot < 6; slot++ {
				hv := h[fmt.Sprintf("m_hItems.%04d", slot)]
				handle, ok := asUint64(hv)
				if !ok {
					continue
				}
				idx := int32(handle & 0x3FFF)
				cls, ok := itemClass[idx]
				if !ok {
					continue
				}
				if name := itemName(cls); name != "" {
					items = append(items, name)
				}
			}
		}

		gpm := 0.0
		xpm := 0.0
		if minutes > 0 {
			gpm = float64(st.earnedGold) / minutes
			xpm = float64(st.earnedXP) / minutes
		}

		slot := i
		if teamName == "dire" {
			slot = 128 + (i - 5)
		}
		pl := map[string]interface{}{
			"player_id":                i,
			"player_slot":              slot,
			"steamid":                  strconv.FormatUint(steam, 10),
			"name":                     asString(pr[pp+"m_iszPlayerName"]),
			"team":                     teamName,
			"hero_id":                  asInt(pr[tp+"m_nSelectedHeroID"]),
			"level":                    asInt(pr[tp+"m_iLevel"]),
			"kills":                    asInt(pr[tp+"m_iKills"]),
			"deaths":                   asInt(pr[tp+"m_iDeaths"]),
			"assists":                  asInt(pr[tp+"m_iAssists"]),
			"net_worth":                st.netWorth,
			"total_earned_gold":        st.earnedGold,
			"total_earned_xp":          st.earnedXP,
			"gold_per_min":             int64(gpm + 0.5),
			"xp_per_min":               int64(xpm + 0.5),
			"last_hits":                st.lastHits,
			"denies":                   st.denies,
			"hero_damage":              int64(st.heroDamage + 0.5),
			"tower_damage":             int64(st.towerDamage + 0.5),
			"hero_healing":             int64(st.healing + 0.5),
			"stuns":                    st.stuns,
			"observer_sentry_wards":    st.wardsPlaced,
			"wards_destroyed":          st.wardsDestroyed,
			"items":                    items,
		}
		if heroName != "" {
			pl["hero_name"] = heroName
		}
		players = append(players, pl)
	}

	result := map[string]interface{}{
		"match_id":    strconv.FormatUint(matchID, 10),
		"game_mode":   gameMode,
		"game_mode_name": gameModes[int32(gameMode)],
		"lobby_type":  asInt(gamerules["m_pGameRules.m_lobbyType"]),
		"game_state":  asInt(gamerules["m_pGameRules.m_nGameState"]),
		"game_winner": gameWinner,
		"radiant_win": gameWinner == 2,
		"end_time":    endTime,
		"start_time":  endTime - int64(duration),
		"duration":    int64(duration),
		"players":     players,
	}
	b, _ := json.MarshalIndent(result, "", "  ")
	out := filepath.Join(outDir, fmt.Sprintf("match_%d.json", matchID))
	if err := os.WriteFile(out, b, 0644); err != nil {
		return err
	}

	raw := map[string]interface{}{
		"player_resource": pr,
		"team_data":       teamData,
		"gamerules":       gamerules,
		"heroes":          heroes,
	}
	b, _ = json.MarshalIndent(raw, "", "  ")
	rawOut := filepath.Join(outDir, fmt.Sprintf("match_%d_raw.json", matchID))
	return os.WriteFile(rawOut, b, 0644)
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("usage: parse <demo...>")
		return
	}
	exe, err := os.Executable()
	if err != nil {
		fmt.Println("cannot locate executable:", err)
		return
	}
	outDir := filepath.Join(filepath.Dir(exe), "..", "json")
	os.MkdirAll(outDir, 0755)
	for _, path := range os.Args[1:] {
		if err := parse(path, outDir); err != nil {
			fmt.Println("ERROR", filepath.Base(path), err)
		}
	}
}
