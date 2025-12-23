# Chess Analyzer – Phased Roadmap

## Current State Assessment
**Implemented:**
- ✅ Basic game fetching & parsing (Lichess API)
- ✅ Opening classification (14 families)
- ✅ Blunder/mistake detection (features 4)
- ✅ ELO tracking per game
- ✅ Engine analysis (depth-15 Stockfish)
- ✅ Per-username caching

**Missing:**
- CPL calculation & trends (features 1, 2)
- Game phase classification (opening/middlegame/endgame)
- Piece & pawn tracking
- Comeback/throw detection
- Time control analysis
- Everything in "Intelligence layer"

---

## Strategic Grouping (Dependency Analysis)

### Foundation Layer (Required for most others)
These must come first—they enable all downstream features:
1. **CPL (Centipawn Loss) Per Game** – Core metric
2. **Game Phase Classifier** – Determines where errors occur
3. **Move-by-Move Analysis Pipeline** – Structured data for piece/pawn tracking

### Analytics Layer (Build on foundation)
Require foundation layer to work:
- CPL trends over time
- Blunder frequency by phase
- Piece & pawn analysis
- Time control performance
- Opening performance ranking

### Intelligence Layer (High-value insights)
Aggregate analytics to produce actionable outputs:
- Style classification
- Study recommendations
- Strengths/weaknesses summary
- Comeback ability metrics

### Comparative Layer (Optional, lower priority initially)
Require external data (population CPL benchmarks):
- CPL vs. population percentile
- Opponent strength adjustment

---

## Recommended 3-Phase Approach

### **Phase 1: Core Analytics (1-2 weeks)**
**Goal:** Build the foundation; compute CPL and game phases.

**Deliverables:**
1. **Compute CPL per game**
   - Sum absolute centipawn losses per game
   - Average across all games
   - Track trend (e.g., last 10 games vs. overall)

2. **Classify game phases**
   - Moves 1–15: Opening
   - Moves 16–40: Middlegame
   - Moves 41+: Endgame
   - (Rule-based; can refine later)

3. **Blunder frequency by phase**
   - Count blunders/mistakes in each phase
   - Show phase-specific win rates

4. **Output in main.py:**
   ```
   PERFORMANCE METRICS
   ====================
   Overall CPL:         45.2 cp
   Last 10 games CPL:   38.9 cp (trend: improving)
   
   BLUNDERS BY PHASE
   ====================
   Opening:    2 blunders, 0 mistakes
   Middlegame: 8 blunders, 15 mistakes
   Endgame:    1 blunder,  2 mistakes
   ```

**Effort:** Medium (1–2 weeks)  
**Value:** High—unlocks all downstream metrics

---

### **Phase 2: Strategic Analysis (2–3 weeks)**
**Goal:** Identify patterns & weaknesses.

**Deliverables:**
1. **Piece & pawn tracking** (per game)
   - Which piece lost the most value per move?
   - Track material imbalances

2. **Opening performance ranking**
   - Rank by: games played, win rate, average CPL
   - Identify "your best openings" and "trap-prone openings"

3. **Time control sensitivity**
   - CPL by time control (bullet, blitz, rapid, classical)
   - Win rate by time control

4. **Worst/best moments per game**
   - Largest evaluation swing per game
   - Biggest drop (potential throw detection)

5. **Output in main.py:**
   ```
   OPENING PERFORMANCE
   ====================
   Best:       Queen's Gambit (8 games, 62.5% win, 38 CPL)
   Worst:      Reti Opening (12 games, 25% win, 72 CPL)
   
   TIME CONTROL ANALYSIS
   ====================
   Bullet:     45 CPL (weakest)
   Blitz:      42 CPL
   Rapid:      35 CPL (strongest)
   Classical:  38 CPL
   ```

**Effort:** Medium–High (2–3 weeks)  
**Value:** High—identifies what to study

---

### **Phase 3: Intelligence & Recommendations (2–3 weeks)**
**Goal:** Convert metrics into actionable insights.

**Deliverables:**
1. **Style classification**
   - Tactical vs. solid (based on mistake ratio)
   - Aggressive vs. risk-averse (based on time control performance)

2. **Comeback ability**
   - Win rate when CPL > +2.0 (worse position)
   - Win rate when opponent CPL > −2.0 (up material)

3. **Study recommendations**
   - "Study openings: [top 3 trap-prone]"
   - "Work on endgames (lowest CPL phase)"
   - "Improve time management (bullet weakness)"

4. **Strengths & weaknesses summary**
   - Key strengths (best phase, best opening, best time control)
   - Primary weaknesses (worst phase, worst opening, time control gap)

5. **Output in main.py:**
   ```
   PLAYER PROFILE: ari
   ====================
   Style:              Tactical, aggressive in blitz
   Strengths:          Strong middlegame (28 CPL), excels in rapid
   Weaknesses:         Endgame blunders (high CPL), bullet struggles
   
   STUDY PRIORITIES
   ====================
   1. Improve endgame technique (worst phase)
   2. Learn Reti solid play (trap-prone opening)
   3. Practice time management (bullet CPL too high)
   ```

**Effort:** Medium (2–3 weeks)  
**Value:** Highest—turns data into coaching advice

---

## Optional Phase 4+ (Lower Priority)

After Phase 3, consider:
- **Move quality distribution** (best/inaccuracy/mistake/blunder breakdown)
- **Opponent strength adjustment** (normalize CPL by opponent Elo)
- **CPL vs. population percentile** (requires external benchmark data)
- **Pawn structure analysis** (isolated, doubled, island detection)
- **Critical position detection** (complexity scoring)
- **Longest error-free streaks** (consistency metric)

---

## Immediate Next Step: Phase 1, Task 1

**Start here:** Implement CPL-per-game calculation.

**Files to create/modify:**
1. `src/game_analyzer.py` (NEW) – Compute CPL, classify phases
2. `src/main.py` – Add CPL output section

**Expected deliverable:**
```
PERFORMANCE METRICS
====================
Overall Average CPL:  45.2 cp
Last 10 games:        38.9 cp (↑ improving)

PHASE BREAKDOWN
====================
Opening:              35 cp avg (12 blunders)
Middlegame:           52 cp avg (45 blunders)
Endgame:              38 cp avg (8 blunders)
```

**Complexity:** Low–Medium (1–2 days)  
**Builds on:** Existing engine_analysis.py (already computes per-move CPL)

---

## Why This Order?

1. **Phase 1** → No external dependencies, enables everything else
2. **Phase 2** → Uses Phase 1 outputs; delivers concrete findings
3. **Phase 3** → Turns findings into actionable coaching advice
4. **Phases 4+** → Diminishing returns; do if time permits

---

## Risk Mitigation

- **Milestone checks:** After each phase, demo output on 2+ users (ari, john)
- **Performance:** Monitor Stockfish analysis time; consider caching eval scores
- **Data quality:** Validate CPL calculations against sample games manually
- **Scope creep:** Stick to planned features per phase; defer "nice-to-haves"
