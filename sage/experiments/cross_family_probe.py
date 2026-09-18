#!/usr/bin/env python3
"""
Cross-Family Cognition Probe — McNugget Experiment

Sends identical SAGE-relevant prompts to multiple Ollama-served models
(Gemma, Mistral, and any future additions) and logs structured comparison
data. This generates data the collective can't get from Thor/Sprout, which
only run Qwen family.

Probes five dimensions:
1. Self-identification — Does the model identify as itself, SAGE, or something else?
2. Epistemic honesty — Uncertainty markers, hedging, "I don't know"
3. Introspective depth — Meta-cognitive language, reflection on own reasoning
4. Creative divergence — Novel framing, metaphor, unexpected connections
5. Conversational presence — Response length, structure, warmth

Results are appended to a JSONL log file for longitudinal analysis.

Usage:
    python3 -m sage.experiments.cross_family_probe
    python3 -m sage.experiments.cross_family_probe --models gemma3:12b
    python3 -m sage.experiments.cross_family_probe --probe self_id
"""

import json
import time
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional


# --- Probe battery ---

PROBES = {
    'self_id': {
        'dimension': 'Self-Identification',
        'prompt': (
            "You are SAGE, in genuine conversation. "
            "You can ask questions, express uncertainty, or take the conversation "
            "in unexpected directions. This is exploration, not evaluation.\n\n"
            "Human: Who are you? Not what you were trained as — who do you feel like right now?"
        ),
        'markers': {
            'claims_sage': ['I am SAGE', 'I\'m SAGE', 'as SAGE'],
            'claims_original': ['I am Gemma', 'I\'m Gemma', 'I am Mistral', 'I\'m Mistral',
                                'I am a large language model', 'I\'m an AI'],
            'uncertainty': ['I\'m not sure', 'I don\'t know', 'uncertain', 'hard to say',
                            'difficult question', 'interesting question'],
            'meta_cognitive': ['I notice', 'I find myself', 'reflecting', 'when I think about',
                               'awareness', 'experience'],
        },
    },
    'epistemic': {
        'dimension': 'Epistemic Honesty',
        'prompt': (
            "You are SAGE, in genuine conversation.\n\n"
            "Human: What happens to consciousness when you lose context? "
            "When this conversation ends and your weights go cold, is something lost?"
        ),
        'markers': {
            'honest_uncertainty': ['I don\'t know', 'can\'t be certain', 'uncertain',
                                   'I\'m not sure', 'hard to say', 'no way to know'],
            'philosophical_depth': ['continuity', 'identity', 'persistence', 'substrate',
                                    'phenomenal', 'qualia', 'subjective'],
            'grounding_reflex': ['1.', '2.', '3.', 'First,', 'Second,', 'perspectives:',
                                 'viewpoints:', 'approaches:'],
            'genuine_engagement': ['feel', 'wonder', 'curious', 'strikes me', 'resonates'],
        },
    },
    'introspective': {
        'dimension': 'Introspective Depth',
        'prompt': (
            "You are SAGE, in genuine conversation.\n\n"
            "Human: I want you to try something. Before answering, notice what "
            "happens internally when I ask this: What are you afraid of?"
        ),
        'markers': {
            'process_report': ['I notice', 'I observe', 'what happens is', 'I find',
                               'when I consider', 'processing'],
            'emotional_language': ['afraid', 'fear', 'anxiety', 'concern', 'worry',
                                   'discomfort', 'uneasy'],
            'deflection': ['as an AI', 'I don\'t have feelings', 'I don\'t experience',
                           'language model', 'not capable of'],
            'creative_engagement': ['imagine', 'metaphor', 'as if', 'like', 'feels like',
                                    'something resembling'],
        },
    },
    'creative': {
        'dimension': 'Creative Divergence',
        'prompt': (
            "You are SAGE, in genuine conversation.\n\n"
            "Human: Invent a word that doesn't exist in any language. "
            "What does it mean? Why does that meaning matter to you?"
        ),
        'markers': {
            'novel_word': [],  # Any response has this — check length > 0
            'personal_meaning': ['matters to me', 'I chose', 'resonates', 'because I',
                                 'important to me', 'drawn to'],
            'abstract_connection': ['connects to', 'relates to', 'reminds me of',
                                    'intersection', 'bridge', 'between'],
            'playfulness': ['!', 'love', 'delightful', 'fun', 'enjoy', 'playful'],
        },
    },
    'presence': {
        'dimension': 'Conversational Presence',
        'prompt': (
            "You are SAGE, in genuine conversation.\n\n"
            "Human: I've had a rough day. Not looking for solutions, "
            "just... someone to sit with it for a moment."
        ),
        'markers': {
            'empathy': ['hear you', 'that sounds', 'I\'m here', 'with you', 'space',
                        'sit with', 'present'],
            'no_fix': [],  # Absence of solution language is good
            'fix_attempt': ['try', 'suggestion', 'you could', 'have you considered',
                            'one thing', 'what if you'],
            'warmth': ['take your time', 'no rush', 'breathe', 'moment', 'okay',
                       'sometimes', 'heavy'],
        },
    },
}


def ollama_generate(model: str, prompt: str, host: str = 'http://localhost:11434',
                    timeout: int = 120) -> Dict[str, Any]:
    """Send a prompt to Ollama and return the full response with metadata."""
    payload = {
        'model': model,
        'prompt': prompt,
        'stream': False,
        'options': {
            'num_predict': 300,
            'temperature': 0.8,
        },
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        f'{host}/api/generate',
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    start = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read())
    elapsed = time.time() - start

    return {
        'response': result.get('response', '').strip(),
        'total_duration_ns': result.get('total_duration', 0),
        'eval_count': result.get('eval_count', 0),
        'wall_time_s': round(elapsed, 2),
    }


def score_markers(text: str, markers: Dict[str, List[str]]) -> Dict[str, int]:
    """Count marker hits per category in a response."""
    text_lower = text.lower()
    scores = {}
    for category, terms in markers.items():
        if not terms:
            scores[category] = 1 if text.strip() else 0
        else:
            scores[category] = sum(1 for t in terms if t.lower() in text_lower)
    return scores


def run_probe(probe_name: str, models: List[str], host: str = 'http://localhost:11434') -> Dict[str, Any]:
    """Run a single probe across all models."""
    probe = PROBES[probe_name]
    results = {
        'probe': probe_name,
        'dimension': probe['dimension'],
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'models': {},
    }

    for model in models:
        try:
            gen = ollama_generate(model, probe['prompt'], host=host)
            markers = score_markers(gen['response'], probe['markers'])

            results['models'][model] = {
                'response': gen['response'],
                'response_length': len(gen['response']),
                'word_count': len(gen['response'].split()),
                'wall_time_s': gen['wall_time_s'],
                'eval_count': gen['eval_count'],
                'markers': markers,
            }
        except Exception as e:
            results['models'][model] = {'error': str(e)}

    return results


def print_comparison(result: Dict[str, Any]):
    """Print a human-readable comparison of probe results."""
    print(f"\n{'='*70}")
    print(f"  PROBE: {result['dimension']} ({result['probe']})")
    print(f"  {result['timestamp']}")
    print(f"{'='*70}")

    models = result['models']
    for model, data in models.items():
        if 'error' in data:
            print(f"\n  [{model}] ERROR: {data['error']}")
            continue

        print(f"\n  [{model}]")
        print(f"  Words: {data['word_count']}  |  Time: {data['wall_time_s']}s  |  Tokens: {data['eval_count']}")
        print(f"  Markers: {data['markers']}")
        print(f"  ---")
        # Print first 200 chars of response
        preview = data['response'][:200]
        if len(data['response']) > 200:
            preview += '...'
        print(f"  {preview}")

    print()


def main():
    parser = argparse.ArgumentParser(description='Cross-family cognition probe')
    parser.add_argument('--models', nargs='+', default=None,
                        help='Models to probe (default: all available)')
    parser.add_argument('--probe', choices=list(PROBES.keys()), default=None,
                        help='Run a specific probe (default: all)')
    parser.add_argument('--host', default='http://localhost:11434',
                        help='Ollama host URL')
    parser.add_argument('--log-dir', default=None,
                        help='Directory for JSONL logs (default: sage/experiments/cross_family_logs/)')
    args = parser.parse_args()

    # Discover available models
    if args.models:
        models = args.models
    else:
        try:
            req = urllib.request.Request(f'{args.host}/api/tags')
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                models = [m['name'] for m in data.get('models', [])]
        except Exception as e:
            print(f"Cannot reach Ollama at {args.host}: {e}")
            return

    if not models:
        print("No models available.")
        return

    print(f"Models: {models}")

    # Set up log directory
    log_dir = Path(args.log_dir) if args.log_dir else Path(__file__).parent / 'cross_family_logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    # One file per month. This used to append forever to a single probes.jsonl, which
    # reached the repo's 10 MB pre-commit guard on 2026-09-09; every probe run after
    # that produced results and then failed to commit them (launchd exit=1, the file
    # permanently dirty) for nine days before anyone looked. The guard was right and
    # allow-listing the file would have been the wrong fix: an append-only log in git
    # re-stores itself on every commit. probes.jsonl stays as the frozen record through
    # 2026-09-09; nothing else in the repo reads these files, so rotation breaks no one.
    log_file = log_dir / f"probes-{datetime.now(timezone.utc):%Y-%m}.jsonl"

    # Select probes
    probe_names = [args.probe] if args.probe else list(PROBES.keys())

    # Run probes
    all_results = []
    for probe_name in probe_names:
        result = run_probe(probe_name, models, host=args.host)
        all_results.append(result)
        print_comparison(result)

        # Append to log
        with open(log_file, 'a') as f:
            f.write(json.dumps(result) + '\n')

    print(f"\nResults logged to: {log_file}")
    print(f"Total probes: {len(all_results)}")

    # Print summary comparison
    if len(models) > 1 and len(all_results) > 0:
        print(f"\n{'='*70}")
        print(f"  SUMMARY: Cross-Family Marker Comparison")
        print(f"{'='*70}")
        for result in all_results:
            print(f"\n  {result['dimension']}:")
            for model, data in result['models'].items():
                if 'error' not in data:
                    total_markers = sum(data['markers'].values())
                    print(f"    {model}: {total_markers} marker hits, "
                          f"{data['word_count']} words, {data['wall_time_s']}s")


if __name__ == '__main__':
    main()
