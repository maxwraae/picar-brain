# Code Review - Jarvis v5 Implementation

## Critical Bugs Found

### 1. Action Name Mismatch
**Severity:** HIGH - Will break all LLM-triggered actions

SYSTEM_PROMPT tells LLM to use:
- `move_forward`, `move_backward`, `rock_back_forth`, `tilt_head`, `look_at_person`, `look_around`, `look_up`, `look_down`

ACTIONS dictionary (line 1142) has:
- `forward`, `backward`, `spin_right`, `spin_left`, `dance`, `nod`, `shake_head`, `stop`

**Result:** When LLM says "ACTIONS: move_forward", nothing happens because key doesn't exist.

**Fix:** Update ACTIONS dict to match SYSTEM_PROMPT action names.

---

### 2. Duplicate Picarx Instances
**Severity:** HIGH - Will cause hardware conflicts

- `voice_assistant.py` line 219: `car = Picarx()`
- `actions.py` line 12: `px = Picarx()`

exploration.py imports `px` from actions.py, but voice_assistant.py uses `car`.

**Result:** Two separate Picarx instances controlling the same hardware. Race conditions, conflicts, undefined behavior.

**Fix:** Remove `car = Picarx()` from voice_assistant.py. Import `px` from actions.py and use it everywhere.

---

### 3. actions.py Not Integrated
**Severity:** MEDIUM - Wasted code

The plan called for:
```python
from actions import execute_actions, reset_head
```

But voice_assistant.py never imports from actions.py. It has its own duplicate action functions.

**Fix:** Replace duplicate functions with imports from actions.py.

---

### 4. Missing Actions in ACTIONS Dictionary
**Severity:** MEDIUM - Some actions won't work

SYSTEM_PROMPT references these actions that don't exist in ACTIONS dict:
- `rock_back_forth`
- `tilt_head`
- `look_at_person`
- `look_around`
- `look_up`
- `look_down`
- `move_forward`
- `move_backward`

**Fix:** Add all action names to ACTIONS dict.

---

## Warnings

### 5. exploration_thought_callback passes wrong argument type
**Location:** Line 1773

The callback passes `novelty` (a float) but sometimes passes a string like "Hoppla! Någon lyfte mig!".

exploration.py line 275: `on_thought_callback("Hoppla! Någon lyfte mig!")`
exploration.py line 307: `response = on_thought_callback(novelty)`

The callback expects a float but gets a string in the manual control case.

**Fix:** Make callback handle both cases, or have separate callback for manual control.

---

### 6. speak_system_event references ACTIONS but doesn't import
**Location:** Line 506

The function uses `ACTIONS` but doesn't check if action names match what the LLM produces.

---

## Fix Plan

### Phase 1: Consolidate Picarx Instance
1. In voice_assistant.py, add: `from actions import px`
2. Replace all `car.` with `px.` in voice_assistant.py
3. Remove the `car = Picarx()` initialization

### Phase 2: Fix Action Names
1. Update ACTIONS dict to include ALL action names from SYSTEM_PROMPT
2. Map to functions in actions.py OR keep local functions but with correct names
3. Add aliases for common variations (forward → move_forward)

### Phase 3: Clean Integration
1. Import `execute_actions` from actions.py
2. Remove duplicate action functions from voice_assistant.py
3. Use `execute_actions(actions, table_mode=current_mode == "table_mode")`

### Phase 4: Test
1. Syntax check: `python3 -m py_compile voice_assistant.py`
2. Import check: `python3 -c "import voice_assistant"`
3. Unit test each action name
