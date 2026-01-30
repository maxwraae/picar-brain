"""
Jarvis Memory Module
Entity-based persistent memory.
"""

import json
import os
import re
import tempfile
import shutil
from datetime import datetime

MEMORY_FILE = "memory.json"
MAX_OBSERVATIONS_PER_ENTITY = 20
MAX_OBSERVATIONS_IN_CONTEXT = 15

def load_memory() -> dict:
    """Load memory from file."""
    if not os.path.exists(MEMORY_FILE):
        print(f"[MEMORY] No memory file found, starting fresh")
        return {"entities": {}}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            entity_count = len(data.get("entities", {}))
            total_obs = sum(len(e.get("observations", [])) for e in data.get("entities", {}).values())
            print(f"[MEMORY] Loaded {entity_count} entities with {total_obs} total observations")
            return data
    except Exception as e:
        print(f"[MEMORY] Load error: {e}")
        return {"entities": {}}

def save_memory_file(memory: dict):
    """Atomic save - write to temp, then rename."""
    temp_fd, temp_path = tempfile.mkstemp(suffix='.json', dir=os.path.dirname(MEMORY_FILE) or '.')
    try:
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
        shutil.move(temp_path, MEMORY_FILE)
        print(f"[MEMORY] Saved to {MEMORY_FILE}")
    except Exception as e:
        print(f"[MEMORY] Save error: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)

def detect_entity(text: str) -> tuple[str, str]:
    """Auto-detect entity from text. Fallback for untagged MEMORY lines."""
    lower = text.lower().strip()

    # Leon references
    if lower.startswith("leon"):
        for prefix in ["leon's ", "leons ", "leon "]:
            if lower.startswith(prefix):
                return "Leon", text[len(prefix):].strip()
        return "Leon", text

    # Self references
    if lower.startswith("jag "):
        return "self", text[4:].strip()

    # Environment keywords
    env_keywords = ["hittade", "såg", "rummet", "under", "bakom", "golvet", "bordet"]
    if any(kw in lower for kw in env_keywords):
        return "environment", text

    return "general", text

def parse_memory_line(line: str) -> tuple[str, str] | None:
    """
    Parse MEMORY line with explicit or auto-detected entity.

    Formats:
      MEMORY[Leon]: gillar dinosaurier
      MEMORY: Leon gillar dinosaurier
    """
    line = line.strip()
    if not line.upper().startswith('MEMORY'):
        return None

    # Try explicit tag: MEMORY[entity]: observation
    match = re.match(r'MEMORY\[(\w+)\]:\s*(.+)', line, re.IGNORECASE)
    if match:
        entity = match.group(1).lower()
        observation = match.group(2).strip()

        # Normalize entity names
        if entity in ["leon"]:
            entity = "Leon"
        elif entity in ["env", "environment", "rummet", "rum"]:
            entity = "environment"
        elif entity in ["self", "jag", "själv", "mig"]:
            entity = "self"
        else:
            entity = entity.capitalize()

        return entity, observation

    # Fallback: MEMORY: text
    if ':' in line:
        text = line.split(':', 1)[1].strip()
        if text:
            return detect_entity(text)

    return None

def add_observation(entity: str, observation: str):
    """Add observation to entity."""
    if not observation or not observation.strip():
        print(f"[MEMORY] Skipping empty observation")
        return

    memory = load_memory()

    if entity not in memory["entities"]:
        print(f"[MEMORY] Creating new entity: {entity}")
        memory["entities"][entity] = {"observations": []}

    timestamp = datetime.now().isoformat()
    memory["entities"][entity]["observations"].append({
        "content": observation.strip(),
        "timestamp": timestamp
    })

    # Prune if too many
    obs = memory["entities"][entity]["observations"]
    if len(obs) > MAX_OBSERVATIONS_PER_ENTITY:
        pruned_count = len(obs) - MAX_OBSERVATIONS_PER_ENTITY
        memory["entities"][entity]["observations"] = obs[-MAX_OBSERVATIONS_PER_ENTITY:]
        print(f"[MEMORY] Pruned {pruned_count} old observations from {entity}")

    save_memory_file(memory)
    print(f"[MEMORY] Added: [{entity}] {observation}")

def format_memories_for_prompt() -> str:
    """Format memories for system prompt injection."""
    memory = load_memory()
    entities = memory.get("entities", {})

    if not entities:
        print(f"[MEMORY] No memories to format for prompt")
        return ""

    sections = []
    total = 0

    # Priority order
    for entity, header in [
        ("Leon", "Du minns om Leon:"),
        ("self", "Du minns om dig själv:"),
        ("environment", "Du minns om rummet:"),
        ("general", "Du minns:")
    ]:
        if entity not in entities:
            continue

        observations = entities[entity].get("observations", [])
        if not observations:
            continue

        # Take most recent
        recent = observations[-5:]

        lines = [header]
        for obs in recent:
            lines.append(f"- {obs['content']}")
            total += 1
            if total >= MAX_OBSERVATIONS_IN_CONTEXT:
                break

        sections.append("\n".join(lines))
        print(f"[MEMORY] Formatted {len(recent)} observations for {entity}")

        if total >= MAX_OBSERVATIONS_IN_CONTEXT:
            break

    print(f"[MEMORY] Total {total} observations included in prompt")
    return "\n\n".join(sections)
