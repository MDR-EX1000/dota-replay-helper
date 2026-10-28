package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"math"
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

func hasNumber(v interface{}) bool {
	switch v.(type) {
	case int32, uint32, int64, uint64, float32, float64:
		f := asFloat(v)
		return !math.IsNaN(f) && !math.IsInf(f, 0) && f >= 0
	}
	return false
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

func heroToken(s string) string {
	s = strings.ToLower(strings.TrimSpace(s))
	s = strings.TrimPrefix(s, "npc_dota_hero_")
	s = strings.TrimPrefix(s, "cdota_unit_hero_")
	s = strings.ReplaceAll(s, "_", "")
	return s
}

func teamName(v int32) string {
	switch v {
	case 2:
		return "radiant"
	case 3:
		return "dire"
	}
	return ""
}

type damageTypes struct {
	Physical int64 `json:"physical"`
	Magical  int64 `json:"magical"`
	Pure     int64 `json:"pure"`
	Other    int64 `json:"other"`
}

type damageCategories struct {
	Attack int64 `json:"attack"`
	Spell  int64 `json:"spell"`
	Item   int64 `json:"item"`
	Other  int64 `json:"other"`
}

type damageInfo struct {
	Dealt    damageTypes      `json:"dealt"`
	Taken    damageTypes      `json:"taken"`
	DealtCat damageCategories `json:"dealt_category"`
	TakenCat damageCategories `json:"taken_category"`
}

type killInternal struct {
	T            float64
	Killer       string
	KillerSource string
	Victim       string
	KillerTeam   string
	VictimTeam   string
	AssistIDs    []int32
	Inflictor    string
	FirstBlood   bool
}

type objectiveInternal struct {
	T      float64
	Kind   string
	Team   string
	Target string
	Lane   string
	Tier   int
	Killer string
	Denied bool
}

type purchaseInternal struct {
	T      float64
	Hero   string
	ItemID int64
}

type econSample struct {
	NW      int64
	XP      int64
	NWValid bool
	XPValid bool
}

type econPoint struct {
	T  float64
	NW int64
}

func classifyObjective(target string) (kind, lane string, tier int) {
	t := strings.ToLower(target)
	if strings.Contains(t, "tower") {
		kind = "tower"
		if i := strings.Index(t, "tower"); i >= 0 && i+5 < len(t) {
			if t[i+5] >= '1' && t[i+5] <= '4' {
				tier = int(t[i+5] - '0')
			}
		}
	} else if strings.Contains(t, "_rax") {
		kind = "rax"
	} else if strings.Contains(t, "fort") {
		kind = "fort"
	} else if strings.Contains(t, "shrine") {
		kind = "shrine"
	} else if strings.Contains(t, "roshan") {
		kind = "roshan"
	} else if strings.Contains(t, "miniboss") || strings.Contains(t, "tormentor") {
		kind = "tormentor"
	} else {
		kind = "other"
	}
	switch {
	case strings.Contains(t, "_top"):
		lane = "top"
	case strings.Contains(t, "_mid"):
		lane = "mid"
	case strings.Contains(t, "_bot"):
		lane = "bot"
	}
	return
}

func objectiveTeam(target string) string {
	t := strings.ToLower(target)
	if strings.Contains(t, "badguys") {
		return "dire"
	}
	if strings.Contains(t, "goodguys") {
		return "radiant"
	}
	return ""
}

func parse(path, outDir string, writeRaw bool) error {
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
	abilityClass := map[int32]string{}
	abilityLevel := map[int32]int64{}

	var matchID uint64
	var gameMode, gameWinner, endTime int64

	damageTaken := map[string]int64{}
	dmg := map[string]*damageInfo{}
	kills := []killInternal{}
	objectives := []objectiveInternal{}
	purchases := []purchaseInternal{}
	lastObjective := map[string]float64{}
	firstBlood := false

	snapshots := map[uint64]map[int]econSample{}
	playerNW := map[string][]econPoint{}
	lastMinute := -1

	nameCache := map[uint32]string{}
	nameOf := func(idx uint32) string {
		if s, ok := nameCache[idx]; ok {
			return s
		}
		s, _ := p.LookupStringByIndex("CombatLogNames", int32(idx))
		nameCache[idx] = s
		return s
	}

	getDmg := func(token string) *damageInfo {
		if token == "" {
			return &damageInfo{}
		}
		if d, ok := dmg[token]; ok {
			return d
		}
		d := &damageInfo{}
		dmg[token] = d
		return d
	}

	addObjective := func(t float64, kind, target, killer string, attackerTeam int32) {
		if kind == "" || target == "" {
			return
		}
		if prev, ok := lastObjective[target]; ok && t-prev < 2.0 {
			return
		}
		lastObjective[target] = t
		targetTeam := objectiveTeam(target)
		destroyer := teamName(attackerTeam)
		if destroyer == "" {
			// building owner is opposite of destroyer
			if targetTeam == "dire" {
				destroyer = "radiant"
			} else if targetTeam == "radiant" {
				destroyer = "dire"
			}
		}
		_, lane, tier := classifyObjective(target)
		objectives = append(objectives, objectiveInternal{
			T: t, Kind: kind, Team: destroyer, Target: target,
			Lane: lane, Tier: tier, Killer: killer, Denied: targetTeam != "" && targetTeam == destroyer,
		})
	}

	sampleEconomy := func(t float64) {
		if t < 0 {
			return
		}
		minute := int(t / 60)
		if minute == lastMinute {
			return
		}
		lastMinute = minute
		for _, td := range teamData {
			for j := 0; j < 10; j++ {
				prefix := fmt.Sprintf("m_vecDataTeam.%04d.", j)
				sid, ok := asUint64(td[prefix+"m_iPlayerSteamID"])
				if !ok || sid == 0 {
					continue
				}
				nw := asInt(td[prefix+"m_iNetWorth"])
				xp := asInt(td[prefix+"m_iTotalEarnedXP"])
				if nw <= 0 {
					continue
				}
				if snapshots[sid] == nil {
					snapshots[sid] = map[int]econSample{}
				}
				snapshots[sid][minute] = econSample{NW: nw, XP: xp, NWValid: hasNumber(td[prefix+"m_iNetWorth"]), XPValid: hasNumber(td[prefix+"m_iTotalEarnedXP"])}
			}
		}
	}

	// HLTV combat log: kills, objectives, purchases, economy, damage breakdown.
	p.Callbacks.OnCMsgDOTACombatLogEntry(func(m *dota.CMsgDOTACombatLogEntry) error {
		t := float64(m.GetTimestamp())
		sampleEconomy(t)

		switch m.GetType() {
		case dota.DOTA_COMBATLOG_TYPES_DOTA_COMBATLOG_PLAYERSTATS:
			name := nameOf(m.GetTargetName())
			hero := heroToken(name)
			if hero == "" || strings.Contains(name, "modifier_") || strings.Contains(name, "fountain") || name == "dota_unknown" {
				return nil
			}
			nw := int64(m.GetNetworth())
			if nw <= 0 {
				return nil
			}
			playerNW[hero] = append(playerNW[hero], econPoint{T: t, NW: nw})

		case dota.DOTA_COMBATLOG_TYPES_DOTA_COMBATLOG_DAMAGE:
			if !m.GetIsTargetHero() || m.GetIsTargetIllusion() || !m.GetIsAttackerHero() {
				return nil
			}
			target := heroToken(nameOf(m.GetTargetName()))
			attacker := heroToken(nameOf(m.GetAttackerName()))
			if target == "" || attacker == "" {
				return nil
			}
			v := int64(m.GetValue())
			damageTaken[target] += v
			di := getDmg(target)
			dj := getDmg(attacker)
			switch m.GetDamageType() {
			case 1:
				dj.Dealt.Physical += v
				di.Taken.Physical += v
			case 2:
				dj.Dealt.Magical += v
				di.Taken.Magical += v
			case 4:
				dj.Dealt.Pure += v
				di.Taken.Pure += v
			default:
				dj.Dealt.Other += v
				di.Taken.Other += v
			}
			switch m.GetDamageCategory() {
			case 0:
				dj.DealtCat.Attack += v
				di.TakenCat.Attack += v
			case 1:
				dj.DealtCat.Spell += v
				di.TakenCat.Spell += v
			case 2, 3:
				dj.DealtCat.Item += v
				di.TakenCat.Item += v
			default:
				dj.DealtCat.Other += v
				di.TakenCat.Other += v
			}

		case dota.DOTA_COMBATLOG_TYPES_DOTA_COMBATLOG_DEATH:
			targetName := nameOf(m.GetTargetName())
			attackerName := nameOf(m.GetAttackerName())
			if m.GetIsTargetHero() && !m.GetIsTargetIllusion() {
				victim := heroToken(targetName)
				killer := ""
				if m.GetIsAttackerHero() {
					killer = heroToken(attackerName)
				}
				assists := []int32{}
				assists = append(assists, m.GetAssistPlayers()...)
				if len(assists) == 0 {
					for _, id := range []uint32{m.GetAssistPlayer0(), m.GetAssistPlayer1(), m.GetAssistPlayer2(), m.GetAssistPlayer3()} {
						if id > 0 {
							assists = append(assists, int32(id))
						}
					}
				}
				fb := false
				if !firstBlood {
					firstBlood = true
					fb = true
				}
				kills = append(kills, killInternal{
					T: t, Killer: killer, KillerSource: attackerName,
					Victim:     victim,
					KillerTeam: teamName(int32(m.GetAttackerTeam())),
					VictimTeam: teamName(int32(m.GetTargetTeam())),
					AssistIDs:  assists,
					Inflictor:  snake(strings.TrimPrefix(nameOf(m.GetInflictorName()), "item_")),
					FirstBlood: fb,
				})
				return nil
			}
			// non-hero deaths: Roshan, tormentor, shrine
			kind, _, _ := classifyObjective(targetName)
			if kind != "other" {
				addObjective(t, kind, targetName, heroToken(attackerName), int32(m.GetAttackerTeam()))
			}

		case dota.DOTA_COMBATLOG_TYPES_DOTA_COMBATLOG_TEAM_BUILDING_KILL:
			target := nameOf(m.GetTargetName())
			kind, _, _ := classifyObjective(target)
			addObjective(t, kind, target, heroToken(nameOf(m.GetAttackerName())), int32(m.GetAttackerTeam()))

		case dota.DOTA_COMBATLOG_TYPES_DOTA_COMBATLOG_PURCHASE:
			hero := heroToken(nameOf(m.GetTargetName()))
			if hero == "" {
				hero = heroToken(nameOf(m.GetAttackerName()))
			}
			if hero == "" {
				return nil
			}
			itemID := int64(m.GetValue())
			if itemID <= 0 {
				return nil
			}
			purchases = append(purchases, purchaseInternal{
				T: t, Hero: hero, ItemID: itemID,
			})

		case dota.DOTA_COMBATLOG_TYPES_DOTA_COMBATLOG_AEGIS_TAKEN:
			taker := heroToken(nameOf(m.GetTargetName()))
			addObjective(t, "aegis", "aegis", taker, int32(m.GetTargetTeam()))
		}
		return nil
	})

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
		case strings.HasPrefix(cn, "CDOTA_Ability_"):
			abilityClass[e.GetIndex()] = cn
			abilityLevel[e.GetIndex()] = asInt(e.Map()["m_iLevel"])
		}
		return nil
	})

	if err := p.Start(); err != nil {
		return err
	}

	fmt.Println("parsed", filepath.Base(path), "match_id", matchID,
		"heroes", len(heroes), "kills", len(kills), "objectives", len(objectives),
		"purchases", len(purchases))

	startClock := asFloat(gamerules["m_pGameRules.m_flGameStartTime"])
	endClock := asFloat(gamerules["m_pGameRules.m_flGameEndTime"])
	duration := endClock - startClock
	if duration <= 0 {
		duration = endClock
	}

	type teamStats struct {
		netWorth, earnedGold, earnedXP, lastHits, denies int64
		heroDamage, towerDamage, healing, stuns          float64
		wardsPlaced, wardsDestroyed                      int64
		obsPlaced, senPlaced                             int64
	}
	statsBySteam := map[uint64]teamStats{}
	statsSourceBySteam := map[uint64]map[string]interface{}{}
	for _, td := range teamData {
		for j := 0; j < 10; j++ {
			prefix := fmt.Sprintf("m_vecDataTeam.%04d.", j)
			sid, ok := asUint64(td[prefix+"m_iPlayerSteamID"])
			if !ok || sid == 0 {
				continue
			}
			source := map[string]interface{}{}
			for key, value := range td {
				if strings.HasPrefix(key, prefix) {
					source[strings.TrimPrefix(key, prefix)] = value
				}
			}
			statsSourceBySteam[sid] = source
			statsBySteam[sid] = teamStats{
				netWorth:       asInt(td[prefix+"m_iNetWorth"]),
				earnedGold:     asInt(td[prefix+"m_iTotalEarnedGold"]),
				earnedXP:       asInt(td[prefix+"m_iTotalEarnedXP"]),
				lastHits:       asInt(td[prefix+"m_iLastHitCount"]),
				denies:         asInt(td[prefix+"m_iDenyCount"]),
				heroDamage:     asFloat(td[prefix+"m_flHeroDamage"]),
				towerDamage:    asFloat(td[prefix+"m_flTowerDamage"]),
				healing:        asFloat(td[prefix+"m_fHealing"]),
				stuns:          asFloat(td[prefix+"m_fStuns"]),
				obsPlaced:      asInt(td[prefix+"m_iObserverWardsPlaced"]),
				senPlaced:      asInt(td[prefix+"m_iSentryWardsPlaced"]),
				wardsPlaced:    asInt(td[prefix+"m_iObserverWardsPlaced"]) + asInt(td[prefix+"m_iSentryWardsPlaced"]),
				wardsDestroyed: asInt(td[prefix+"m_iWardsDestroyed"]),
			}
		}
	}

	heroIdxByPlayer := map[int64][]int32{}
	for idx, h := range heroes {
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
	bestHero := func(pid int64) (map[string]interface{}, string, int32) {
		var bh map[string]interface{}
		bc := ""
		var bidx int32 = -1
		best := -1
		for _, idx := range heroIdxByPlayer[pid] {
			h := heroes[idx]
			score := countItems(h)*1000 + int(asInt(h["m_iCurrentLevel"]))
			if score > best {
				best = score
				bh = h
				bc = heroClass[idx]
				bidx = idx
			}
		}
		return bh, bc, bidx
	}

	finalMinute := int(duration / 60)
	for steam, st := range statsBySteam {
		if snapshots[steam] == nil {
			snapshots[steam] = map[int]econSample{}
		}
		snapshots[steam][finalMinute] = econSample{NW: st.netWorth, XP: st.earnedXP, NWValid: hasNumber(statsSourceBySteam[steam]["m_iNetWorth"]), XPValid: hasNumber(statsSourceBySteam[steam]["m_iTotalEarnedXP"])}
	}

	minutes := duration / 60.0
	players := make([]map[string]interface{}, 0, 10)
	heroByPID := map[int64]string{}
	pidByHero := map[string]int{}

	for i := 0; i < 10; i++ {
		pp := fmt.Sprintf("m_vecPlayerData.%04d.", i)
		tp := fmt.Sprintf("m_vecPlayerTeamData.%04d.", i)
		steam, _ := asUint64(pr[pp+"m_iPlayerSteamID"])
		team := asInt(pr[pp+"m_iPlayerTeam"])
		teamNameStr := "radiant"
		if team == 3 {
			teamNameStr = "dire"
		}
		st := statsBySteam[steam]

		heroName := ""
		heroTok := ""
		items := make([]string, 0, 6)
		abilities := []map[string]interface{}{}
		if h, cls, hidx := bestHero(int64(i)); h != nil {
			heroName = cls
			heroTok = heroToken(cls)
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
			for slot := 0; slot < 16; slot++ {
				hv := h[fmt.Sprintf("m_vecAbilities.%04d", slot)]
				handle, ok := asUint64(hv)
				if !ok {
					continue
				}
				idx := int32(handle & 0x3FFF)
				cls, ok := abilityClass[idx]
				if !ok {
					continue
				}
				lvl := abilityLevel[idx]
				if lvl <= 0 {
					continue
				}
				key := snake(strings.TrimPrefix(cls, "CDOTA_Ability_"))
				if strings.Contains(strings.ToLower(key), "special_bonus") {
					continue
				}
				abilities = append(abilities, map[string]interface{}{
					"name": key, "level": lvl,
				})
			}
			_ = hidx
		}

		gpm := 0.0
		xpm := 0.0
		if minutes > 0 {
			gpm = float64(st.earnedGold) / minutes
			xpm = float64(st.earnedXP) / minutes
		}

		slot := i
		if teamNameStr == "dire" {
			slot = 128 + (i - 5)
		}
		di := getDmg(heroTok)
		pl := map[string]interface{}{
			"player_id":             i,
			"player_slot":           slot,
			"steamid":               strconv.FormatUint(steam, 10),
			"name":                  asString(pr[pp+"m_iszPlayerName"]),
			"team":                  teamNameStr,
			"hero_id":               asInt(pr[tp+"m_nSelectedHeroID"]),
			"hero":                  heroTok,
			"level":                 asInt(pr[tp+"m_iLevel"]),
			"kills":                 asInt(pr[tp+"m_iKills"]),
			"deaths":                asInt(pr[tp+"m_iDeaths"]),
			"assists":               asInt(pr[tp+"m_iAssists"]),
			"net_worth":             st.netWorth,
			"total_earned_gold":     st.earnedGold,
			"total_earned_xp":       st.earnedXP,
			"gold_per_min":          int64(gpm + 0.5),
			"xp_per_min":            int64(xpm + 0.5),
			"last_hits":             st.lastHits,
			"denies":                st.denies,
			"hero_damage":           int64(st.heroDamage + 0.5),
			"hero_damage_taken":     damageTaken[heroTok],
			"tower_damage":          int64(st.towerDamage + 0.5),
			"hero_healing":          int64(st.healing + 0.5),
			"stuns":                 st.stuns,
			"observer_sentry_wards": st.wardsPlaced,
			"observer_wards_placed": st.obsPlaced,
			"sentry_wards_placed":   st.senPlaced,
			"wards_destroyed":       st.wardsDestroyed,
			"items":                 items,
			"abilities":             abilities,
			"damage": map[string]interface{}{
				"dealt":          di.Dealt,
				"taken":          di.Taken,
				"dealt_category": di.DealtCat,
				"taken_category": di.TakenCat,
			},
		}
		missing := []string{}
		source := statsSourceBySteam[steam]
		sourceFields := map[string][]string{
			"net_worth": {"m_iNetWorth"}, "total_earned_gold": {"m_iTotalEarnedGold"},
			"total_earned_xp": {"m_iTotalEarnedXP"}, "gold_per_min": {"m_iTotalEarnedGold"},
			"xp_per_min": {"m_iTotalEarnedXP"}, "last_hits": {"m_iLastHitCount"},
			"denies": {"m_iDenyCount"}, "hero_damage": {"m_flHeroDamage"},
			"tower_damage": {"m_flTowerDamage"}, "hero_healing": {"m_fHealing"},
			"stuns": {"m_fStuns"}, "observer_sentry_wards": {"m_iObserverWardsPlaced", "m_iSentryWardsPlaced"},
			"wards_destroyed": {"m_iWardsDestroyed"},
		}
		for field, sources := range sourceFields {
			valid := true
			for _, prop := range sources {
				if !hasNumber(source[prop]) {
					valid = false
				}
			}
			if (field == "gold_per_min" || field == "xp_per_min") && duration <= 0 {
				valid = false
			}
			if !valid {
				pl[field] = nil
				missing = append(missing, field)
			}
		}
		for field, prop := range map[string]string{"kills": "m_iKills", "deaths": "m_iDeaths", "assists": "m_iAssists", "level": "m_iLevel"} {
			if !hasNumber(pr[tp+prop]) {
				pl[field] = nil
				missing = append(missing, field)
			}
		}
		pl["data_quality"] = map[string]interface{}{"verified": true, "missing_fields": missing}
		if heroName != "" {
			pl["hero_name"] = heroName
		}
		heroByPID[int64(i)] = heroTok
		if heroTok != "" {
			pidByHero[heroTok] = i
		}
		players = append(players, pl)
	}

	// resolve assists and purchases to player ids
	resolveAssist := func(id int32) string {
		pid := int64(id)
		if pid > 9 && pid%2 == 0 {
			pid = pid / 2
		}
		if h, ok := heroByPID[pid]; ok {
			return h
		}
		return ""
	}
	killsOut := make([]map[string]interface{}, 0, len(kills))
	for _, k := range kills {
		assists := []string{}
		for _, id := range k.AssistIDs {
			if h := resolveAssist(id); h != "" {
				assists = append(assists, h)
			}
		}
		ev := map[string]interface{}{
			"t": k.T, "killer": k.Killer, "victim": k.Victim,
			"killer_team": k.KillerTeam, "victim_team": k.VictimTeam,
			"assists": assists,
		}
		if k.KillerSource != "" {
			ev["killer_source"] = k.KillerSource
		}
		if k.Inflictor != "" && k.Inflictor != "dota_unknown" {
			ev["inflictor"] = k.Inflictor
		}
		if k.FirstBlood {
			ev["first_blood"] = true
		}
		killsOut = append(killsOut, ev)
	}

	objectivesOut := make([]map[string]interface{}, 0, len(objectives))
	for _, o := range objectives {
		ev := map[string]interface{}{
			"t": o.T, "kind": o.Kind, "team": o.Team,
			"target": o.Target, "killer": o.Killer,
		}
		if o.Lane != "" {
			ev["lane"] = o.Lane
		}
		if o.Tier > 0 {
			ev["tier"] = o.Tier
		}
		if o.Denied {
			ev["denied"] = true
		}
		objectivesOut = append(objectivesOut, ev)
	}

	purchasesOut := make([]map[string]interface{}, 0, len(purchases))
	for _, pu := range purchases {
		pid, ok := pidByHero[pu.Hero]
		if !ok {
			continue
		}
		purchasesOut = append(purchasesOut, map[string]interface{}{
			"t": pu.T, "player_id": pid, "hero": pu.Hero,
			"item_id": pu.ItemID,
		})
	}

	// economy arrays by player id
	times := make([]int, 0, finalMinute+2)
	for m := 0; m <= finalMinute; m++ {
		times = append(times, m*60)
	}
	if int(duration) != finalMinute*60 {
		times = append(times, int(duration))
		times[len(times)-1] = int(duration)
	}
	netWorthSeries := make([][]interface{}, 10)
	xpSeries := make([][]interface{}, 10)
	for i := 0; i < 10; i++ {
		steam, _ := asUint64(pr[fmt.Sprintf("m_vecPlayerData.%04d.m_iPlayerSteamID", i)])
		samples := snapshots[steam]
		nw := make([]interface{}, len(times))
		xp := make([]interface{}, len(times))
		var cur econSample
		for idx, tm := range times {
			m := tm / 60
			if sm, ok := samples[m]; ok {
				cur = sm
			}
			if cur.NWValid {
				nw[idx] = cur.NW
			}
			if cur.XPValid {
				xp[idx] = cur.XP
			}
		}
		netWorthSeries[i] = nw
		xpSeries[i] = xp
	}

	economy := map[string]interface{}{
		"source":    "snapshot",
		"approx":    false,
		"times":     times,
		"net_worth": netWorthSeries,
		"xp":        xpSeries,
	}

	result := map[string]interface{}{
		"schema":         3,
		"match_id":       strconv.FormatUint(matchID, 10),
		"game_mode":      gameMode,
		"game_mode_name": gameModes[int32(gameMode)],
		"lobby_type":     asInt(gamerules["m_pGameRules.m_lobbyType"]),
		"game_state":     asInt(gamerules["m_pGameRules.m_nGameState"]),
		"game_winner":    gameWinner,
		"radiant_win":    gameWinner == 2,
		"end_time":       endTime,
		"start_time":     endTime - int64(duration),
		"duration":       int64(duration),
		"players":        players,
		"kills":          killsOut,
		"objectives":     objectivesOut,
		"purchases":      purchasesOut,
		"economy":        economy,
	}
	if gameWinner != 2 && gameWinner != 3 {
		result["radiant_win"] = nil
	}
	b, _ := json.MarshalIndent(result, "", "  ")
	out := filepath.Join(outDir, fmt.Sprintf("match_%d.json", matchID))
	if err := os.WriteFile(out, b, 0644); err != nil {
		return err
	}
	if !writeRaw {
		return nil
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
	outFlag := flag.String("out", "", "output directory")
	noRaw := flag.Bool("no-raw", false, "do not write _raw.json")
	flag.Parse()
	args := flag.Args()
	if len(args) == 0 {
		fmt.Println("usage: parse [--out DIR] [--no-raw] <demo...>")
		return
	}
	outDir := *outFlag
	if outDir == "" {
		exe, err := os.Executable()
		if err != nil {
			fmt.Println("cannot locate executable:", err)
			return
		}
		outDir = filepath.Join(filepath.Dir(exe), "..", "json")
	}
	os.MkdirAll(outDir, 0755)
	for _, path := range args {
		if err := parse(path, outDir, !*noRaw); err != nil {
			fmt.Println("ERROR", filepath.Base(path), err)
		}
	}
}
