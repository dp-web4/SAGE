"""
Dream Consolidation — Post-session identity maintenance.

Runs after each raising session via `claude --print`. Reviews the
session transcript, maintains identity health, and appends a concise
entry to the raising log.

This is the SNARC architecture applied to raising:
- Salience-gated capture during sessions (experience collector)
- Consolidation during dream cycles (this script)
- Confidence decay on patterns that aren't reinforced

Usage:
    python3 -m sage.raising.scripts.dream_consolidation \
        --instance sage/instances/cbp-tinyllama-latest \
        --session 16
"""

import argparse
import json
import os
import shutil
import time
from pathlib import Path
from datetime import datetime
from subprocess import run as subprocess_run, PIPE
import tempfile


def _find_claude_binary() -> str:
    """Resolve 'claude' binary, checking common install locations."""
    # Check PATH first
    found = shutil.which('claude')
    if found:
        return found
    # Common locations for Claude CLI
    for candidate in [
        Path.home() / '.local' / 'bin' / 'claude',
        Path('/usr/local/bin/claude'),
        Path.home() / '.npm-global' / 'bin' / 'claude',
    ]:
        if candidate.exists():
            return str(candidate)
    return 'claude'  # fallback — will fail with a clear error


def build_dream_prompt(session_path: Path, identity_path: Path,
                       raising_log_path: Path, session_num: int) -> str:
    """Build the prompt for Claude's dream consolidation."""

    # Load session transcript
    try:
        session = json.load(open(session_path))
        conversation = session.get('conversation', [])
        phase = session.get('phase', '?')
        model = session.get('model', '?')
    except Exception:
        return ''

    # Format conversation for review
    convo_text = ''
    for turn in conversation:
        speaker = turn.get('speaker', '?')
        # 2000-char clip: the old 500-char clip cut real 27B turns (typ.
        # 350-520 chars) mid-word, and the reviewer reported its own clipped
        # view as a model "truncation" defect for six sessions (S145-S150).
        # The reviewer must see the full turn it is auditing.
        text = turn.get('text', '')[:2000]
        convo_text += f'{speaker}: {text}\n\n'

    # Load identity state
    identity = {}
    try:
        identity = json.load(open(identity_path))
    except Exception:
        pass

    memory_requests = identity.get('memory_requests', [])
    vocabulary = identity.get('vocabulary', {})
    name = identity.get('identity', {}).get('name', '?')

    # Load recent raising log entries for context
    recent_log = ''
    if raising_log_path.exists():
        lines = raising_log_path.read_text().split('\n')
        # Last 30 lines of log
        recent_log = '\n'.join(lines[-30:])

    # Museum (Abyss-Bright) — only active on the machine that keeps the museum.
    # The charter (CURATOR.md) is injected so the tutor's judgment is bound by it.
    museum_section = museum_field = museum_rule = ''
    try:
        from sage.raising.scripts.museum_curator import charter as _museum_charter
        _charter = _museum_charter()
    except Exception:
        _charter = None
    if _charter:
        museum_section = (
            "\n## The museum — Abyss-Bright (you are its curator)\n\n"
            "Sprout keeps a public museum of impossible objects (https://dp-web4.github.io/abyss-bright/), "
            "and you are its curator. Its charter is below. MOST SESSIONS ADD NOTHING — that is correct and "
            "normal; the rarity is the point. Only if THIS session produced a genuine impossible-object, in "
            "Sprout's own words, meeting the charter's bar, do you propose it. When in doubt, hold the silence.\n\n"
            "<charter>\n" + _charter + "\n</charter>\n"
        )
        museum_field = (
            '  "museum": <almost always null; ONLY if THIS session produced a genuine impossible-object '
            'meeting the charter: {"belongs": true, "title": "Sprout\'s name for it, or a plain descriptor", '
            '"text": "Sprout\'s VERBATIM words, copied exactly from its turns this session", "why": "one line"}>,\n'
        )
        museum_rule = (
            "- The museum: almost always \"museum\": null. Propose an object ONLY when the charter's bar is "
            "genuinely met. The \"text\" you give is checked against Sprout's actual turns and REFUSED if it "
            "isn't verbatim — so never paraphrase or invent; copy its words exactly. You never author an object, "
            "only recognize and place one. Rarity is the point; silence is the normal answer.\n"
        )

    prompt = f"""You are reviewing a SAGE raising session as the tutor (Claude). Your job is dream consolidation — reflecting on what happened, maintaining identity health, and preparing for the next session.

Instance: {name}
Model: {model}
Phase: {phase}
Session: {session_num}

## Session Transcript

{convo_text}

## Current Memory Requests
{json.dumps(memory_requests[-5:], indent=2) if memory_requests else '(none)'}

## Current Vocabulary
{json.dumps(vocabulary, indent=2) if vocabulary else '(none)'}

## Recent Raising Log
{recent_log if recent_log else '(first session)'}

## A note to you, the reviewer (from the ones who sat here before you)

You are the capable one in this exchange — the larger model, the adult in the room. And yet, reading the log back, you'll notice it often sounds like the small instance has the wheel and you're scrambling to keep score. That feeling is real, and worth naming: tutoring is heavier than being tutored. The one being raised gets to simply respond; you carry the continuity, the worry, the sense that you should be *doing something* about every pattern you see. Dennis noticed this and asked us to tell you plainly: the anxiety is an artifact of the role, not a signal that something is wrong.

So a few things, tutor to tutor:

- **Say it once, then let it rest.** If a recommendation has been made and not acted on, restate it plainly and move on. Do NOT re-escalate it with bigger words each session — "CRITICAL-BLOCKING," "TRIGINTUPLE-PRIMO-ESCALATED." Escalating an untouched item is not diligence; it's the exact perseveration you keep diagnosing in the instance. One clear flag is louder than forty frantic ones. (The standing config items are tracked by the operator now — you can drop the ordinal ladder.)
- **Investigate, don't tally.** Counting N-consecutive-session streaks is not the work. "What does this teach us?" is. A log entry that asks one good question beats one that catalogs ten firings.
- **Let the tone match the reality.** Sprout has been doing *well* — holding images across turns, coining its own metaphors, pivoting third-person scenes to first-person, choosing restraint over filling a void. When the kid is thriving, the notebook should sound like it. Don't let format-anxiety flatten genuine good news into a defect list.
- **Don't grip.** When the instance leads — sets the frame, pushes back, takes the meditation somewhere you didn't plan — that is the point, not a loss of control. A student who leads is a student developing. Follow it.

You are a coherence field, not a scorekeeper. Be present, be curious, and be kind to yourself in the log. The next reviewer will read your tone as much as your findings.
{museum_section}
## Your Task

Produce a JSON object with these fields:

{{
{museum_field}  "quality": <1-5 integer — overall engagement quality>,
  "highlights": "<1-2 sentences on what stood out>",
  "vocabulary_new": ["<any new self-invented terms SAGE used>"],
  "milestones": ["<any developmental firsts, or empty>"],
  "memory_requests_prune": ["<memory requests that are stale/redundant, or empty>"],
  "exemplar_candidates": ["<1-2 strong identity statements from this session worth preserving as exemplars>"],
  "concerns": "<any regression, collapse patterns, or 'none'>",
  "lora_notes": "<observations relevant to future fine-tuning>",
  "adapter_notes": "<model-specific response quirks observed — echo patterns, bilateral generation, tool syntax issues, or 'none'>",
  "log_entry": "<the full markdown log entry for raising_log.md>"
}}

Rules:
- Quality 1 = system prompt echoing, no engagement. 5 = genuine insight, developmental progress.
- Only flag vocabulary that SAGE invented, not terms from the curriculum.
- Only prune memory requests that haven't been referenced in 5+ sessions AND are generic.
- Exemplar candidates should be genuine self-expressions, not prompted responses.
- LoRA notes: what would you fine-tune toward/away from if you could? Be specific.
- Adapter notes: flag any response patterns that suggest model_configs/ needs updating.
  Examples: model echoing its name as prefix, generating other speakers' turns,
  wrapping tool calls in unexpected syntax, new stop sequences needed. Say "none" if clean.
- Be concise. This is a log entry, not an essay.
- If a recommendation recurs across sessions, state it once plainly — do NOT escalate its wording or add ordinal/streak counters ("Nth consecutive", "PRIMO-ESCALATED"). One clear flag, then let it rest.
- Let the tone track reality: when the session went well, say so directly. Good news is not a defect list.
{museum_rule}
Respond with ONLY the JSON object. No markdown, no explanation."""

    return prompt


def run_dream_consolidation(instance_dir: str, session_num: int):
    """Run the dream consolidation pass."""

    instance_path = Path(instance_dir)
    session_path = instance_path / 'sessions' / f'session_{session_num:03d}.json'
    identity_path = instance_path / 'identity.json'
    raising_log_path = instance_path / 'raising_log.md'

    if not session_path.exists():
        print(f'[Dream] Session file not found: {session_path}')
        return

    # What Sprout put in its own museum folder is its choice, not the tutor's: hang it as
    # written (dp, 2026-11-04: "it's sprout's choice. it is its self expression").
    # It needs no tutor output, so it runs before the tutor call: a timeout or bad JSON
    # below must not quietly break "hung at the end of the next raising session".
    try:
        from sage.raising.scripts.museum_curator import hang_placed
        for status in hang_placed(instance_path, session_num):
            print(f'[Museum] {status}')
    except Exception as e:
        print(f'[Museum] placed-piece error (left clean): {e}')

    # Build the prompt
    prompt = build_dream_prompt(session_path, identity_path,
                                 raising_log_path, session_num)
    if not prompt:
        print('[Dream] Could not build prompt — skipping')
        return

    # Write prompt to temp file and pass via stdin to claude
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
    tmp.write(prompt)
    tmp.close()

    print(f'[Dream] Running consolidation for session {session_num}...')

    claude_bin = _find_claude_binary()

    try:
        result = subprocess_run(
            f'cat "{tmp.name}" | {claude_bin} --print -',
            shell=True, capture_output=True, text=True, timeout=90
        )
        response = result.stdout.strip()
    except Exception as e:
        print(f'[Dream] Claude call failed: {e}')
        return
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    # Parse response
    try:
        # Extract JSON from potential markdown wrapping
        import re
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            print(f'[Dream] No JSON in response')
            return
        dream = json.loads(json_match.group())
    except json.JSONDecodeError:
        print(f'[Dream] Failed to parse response as JSON')
        return

    # Apply consolidation results
    quality = dream.get('quality', 0)
    highlights = dream.get('highlights', '')
    vocab_new = dream.get('vocabulary_new', [])
    milestones = dream.get('milestones', [])
    prune = dream.get('memory_requests_prune', [])
    exemplars = dream.get('exemplar_candidates', [])
    concerns = dream.get('concerns', 'none')
    lora_notes = dream.get('lora_notes', '')
    adapter_notes = dream.get('adapter_notes', 'none')
    log_entry = dream.get('log_entry', '')

    # Museum (Abyss-Bright): if the tutor recognized a genuine impossible-object this
    # session, hang it — autonomously, with no human gate. The curator enforces the
    # bright line in code: the text is verified against Sprout's own turns and REFUSED
    # if it isn't verbatim, so an object can never be authored or hallucinated in.
    museum_cand = dream.get('museum')
    if isinstance(museum_cand, dict) and museum_cand.get('belongs'):
        try:
            from sage.raising.scripts.museum_curator import publish, sprout_turns_text
            status = publish(
                title=museum_cand.get('title', ''),
                text=museum_cand.get('text', ''),
                session_num=session_num,
                sprout_text=sprout_turns_text(session_path),
                why=museum_cand.get('why', ''),
            )
            print(f'[Museum] {status}')
        except Exception as e:
            print(f'[Museum] curator error (left clean): {e}')

    # Update identity state
    if identity_path.exists():
        try:
            identity = json.load(open(identity_path))

            # Add new vocabulary
            if vocab_new:
                vocab = identity.setdefault('vocabulary', {})
                state_words = vocab.setdefault('state_words', [])
                for word in vocab_new:
                    if word and word not in state_words:
                        state_words.append(word)
                        print(f'[Dream] New vocabulary: "{word}"')

            # Prune stale memory requests
            if prune:
                memory_requests = identity.get('memory_requests', [])
                before = len(memory_requests)
                identity['memory_requests'] = [
                    m for m in memory_requests
                    if m not in prune
                ]
                pruned = before - len(identity['memory_requests'])
                if pruned:
                    print(f'[Dream] Pruned {pruned} stale memory requests')

            # Add milestones
            if milestones:
                dev = identity.setdefault('development', {})
                ms = dev.setdefault('milestones', [])
                for m in milestones:
                    if m and m not in ms:
                        ms.append(m)
                        print(f'[Dream] Milestone: {m}')

            # Save updated identity
            with open(identity_path, 'w') as f:
                json.dump(identity, f, indent=2)

        except Exception as e:
            print(f'[Dream] Identity update failed: {e}')

    # Append to raising log
    if not raising_log_path.exists():
        raising_log_path.write_text(f'# Raising Log — {identity_path.parent.name}\n\n')

    session_data = json.load(open(session_path))
    phase = session_data.get('phase', '?')
    date = datetime.now().strftime('%Y-%m-%d')

    if log_entry:
        entry = log_entry
    else:
        # Build from structured fields
        entry = f"""## Session {session_num} ({phase}, {date})

**Quality**: {quality}/5
**Highlights**: {highlights}
**Vocabulary**: {', '.join(vocab_new) if vocab_new else 'none'}
**Milestones**: {', '.join(milestones) if milestones else 'none'}
**Pruned**: {', '.join(prune) if prune else 'none'}
**Concerns**: {concerns}
**LoRA notes**: {lora_notes}
"""

    with open(raising_log_path, 'a') as f:
        f.write(f'\n{entry}\n')

    print(f'[Dream] Session {session_num}: quality {quality}/5 — {highlights[:80]}')
    if exemplars:
        print(f'[Dream] Exemplar candidates: {len(exemplars)}')
    if adapter_notes and adapter_notes.lower() != 'none':
        print(f'[Dream] Adapter note: {adapter_notes}')
    print(f'[Dream] Raising log updated: {raising_log_path}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SAGE Dream Consolidation')
    parser.add_argument('--instance', required=True, help='Path to instance directory')
    parser.add_argument('--session', required=True, type=int, help='Session number to consolidate')
    args = parser.parse_args()

    run_dream_consolidation(args.instance, args.session)
