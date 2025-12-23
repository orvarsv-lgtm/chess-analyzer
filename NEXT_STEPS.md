# Next Steps – Quick Start

## Executive Summary
Your finished product has **26 features** but they cluster into **3 phases**. 

**Phase 1** (Foundation) → **Phase 2** (Analysis) → **Phase 3** (Intelligence)

Each phase takes ~2 weeks and delivers measurable value.

---

## 🎯 Phase 1: Core Analytics (Your Starting Point)

### What You'll Build
A **Performance Metrics** section that shows:
- Average CPL per game (overall + trend)
- Blunders/mistakes broken down by game phase
- Which phase you're weakest in

### Why Phase 1 Matters
- All other features depend on CPL calculation
- No external data needed
- Shows immediate value (players care about this)

### What You Already Have
✅ `engine_analysis.py` computes per-move CPL  
✅ CSV stores games & moves  
✅ Main loop exists to output stats

### What You Need to Add
1. **Aggregate CPL across all games** (sum losses, count moves, average)
2. **Classify each move's phase** (opening/middlegame/endgame)
3. **Group blunders by phase** (count errors per phase)
4. **Output in main.py** (new section after stats)

### Implementation Path

**Step 1a:** Create `src/performance_metrics.py`
```python
def compute_game_cpl(moves_pgn_str, engine_analysis_data):
    """Return total CPL for game"""
    
def classify_move_phase(move_index):
    """Return 'opening' | 'middlegame' | 'endgame'"""
    
def aggregate_cpl_by_phase(games_df):
    """Return CPL and blunder counts per phase"""
```

**Step 1b:** Modify `src/engine_analysis.py`
- Return structured data (list of move evaluations) instead of just printing
- Store: move number, SAN, eval before/after, phase classification

**Step 1c:** Update `src/main.py`
- Import `performance_metrics`
- Add output section after "ELO STATISTICS"

**Step 1d:** Test on `ari` and `john` data

### Estimated Effort
- **Coding:** 1–2 days
- **Testing & refinement:** 1 day
- **Total:** ~2 days (1/2 of Phase 1)

### Success Criteria
Output looks like:
```
PERFORMANCE METRICS
====================
Overall Average CPL:    45.2 cp
Last 10 games:          38.9 cp (↑ improving)

BLUNDERS BY PHASE
====================
Opening:    2 blunders,  5 mistakes  (win: 60%)
Middlegame: 8 blunders, 15 mistakes  (win: 40%)
Endgame:    1 blunder,   2 mistakes  (win: 80%)
```

---

## 📋 Phase 1 Continued: Opening & Time Control (After Step 1)

**Step 1e:** Time control performance
- Group games by time_control (already in CSV)
- Compute CPL per time control
- Show which format is your strength

**Step 1f:** Opening performance ranking
```
TOP OPENINGS (Ranked by Performance)
====================
1. Queen's Gambit      8 games, 62.5% win, 38 CPL ← Best
2. Italian Game        5 games, 60.0% win, 42 CPL
...
N. Reti Opening       12 games, 25.0% win, 72 CPL ← Worst
```

**Estimated effort:** +2–3 days

---

## 🚀 Your First Task (Pick One)

### Option A: Data Foundation First
**"Let me make sure CPL calculations are rock solid."**
- Create `performance_metrics.py` with `compute_game_cpl()` function
- Add unit tests with sample games
- Verify output matches manual calculation on 1–2 games
- **Deliverable:** CPL per game working in main.py
- **Time:** 1–2 days

### Option B: Engine Integration First
**"Let me refactor engine_analysis.py to return structured data."**
- Modify `analyze_game()` to return a dict/list instead of just printing
- Each move: {move_num, san, eval_before, eval_after, cp_loss, phase}
- Update main.py to consume this data
- **Deliverable:** Engine analysis returns reusable data
- **Time:** 1–2 days

### Option C: Quick Win First
**"Let me get *something* visible fast."**
- Add a simple "PERFORMANCE SUMMARY" section to main.py
- Show: overall CPL, best phase, worst phase
- Use existing engine_analysis.py output
- Refactor to cleaner data structure later
- **Deliverable:** Phase 1 alpha (rough but working)
- **Time:** 1 day

---

## My Recommendation

**Start with Option A → B → C (not C first)**

Why:
1. **A** ensures your foundation is correct before building on it
2. **B** unlocks reusability for Phases 2 & 3
3. **C** is tempting but creates tech debt

**Timeline:**
- Day 1: Option A (CPL calculation + tests)
- Day 2: Option B (refactor engine_analysis return value)
- Day 3: Option C (integrate into main.py output)
- **Week 1 complete:** Phase 1 foundation solid ✅

---

## Unblocking Questions

Before you start, answer these:

1. **Do you want to cache engine evaluations per game?**
   - (Stockfish analysis is slow; storing {moves_pgn → [evals]} would speed up re-runs)

2. **Should CPL include all moves or only your moves?**
   - (For now: all moves. Later: per-player option)

3. **How many games should you typically analyze?**
   - (Affects performance tuning priorities)

4. **Do you want a CLI option to pick which player?**
   - (Currently hardcoded; make it flexible?)

---

## File Structure After Phase 1

```
src/
  lichess_api.py          (fetch & parse, unchanged)
  parser.py               (add opening_name column, done)
  opening_classifier.py   (map moves to openings, done)
  engine_analysis.py      (REFACTORED: return structured data)
  performance_metrics.py  (NEW: compute CPL, blunder frequency)
  game_analyzer.py        (NEW: orchestrate analysis)
  main.py                 (updated: call performance_metrics, format output)
```

---

## Ready to Start?

Let me know which option (A / B / C) you prefer and I'll build Phase 1 Task 1.
