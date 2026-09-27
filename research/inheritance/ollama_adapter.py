"""Stateless Ollama adapter for IH-01, matching the repository's /api/chat path.

No tools, prior messages, or returned context are replayed. Server defaults are
used deliberately: see llm_dispatch.py's documented Gemma/Apple options issue.
The harness seed is an ordering/pairing label, not an enforced sampling seed.
Pin the server model digest and sampling defaults in run metadata before use.
"""
import argparse
import json
import sys
import urllib.request


def payload(request, model):
    instruction = request['instruction'] + f" Keep handoff under {request['handoff_chars']} characters."
    data = {k: v for k, v in request.items() if k not in ('instruction', 'seed')}
    return {'model': model, 'stream': False, 'think': False,
            'messages': [{'role': 'system', 'content': instruction},
                         {'role': 'user', 'content': json.dumps(data)}]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default='http://127.0.0.1:11434')
    p.add_argument('--model', required=True)
    p.add_argument('--timeout', type=int, default=110)
    args = p.parse_args()
    request = json.load(sys.stdin)
    body = payload(request, args.model)
    req = urllib.request.Request(args.url.rstrip('/') + '/api/chat',
                                 data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=args.timeout) as r:
        reply = json.load(r)
    response = json.loads(reply['message']['content'])
    response['adapter_observation'] = {
        'backend': 'ollama', 'model_reported': reply.get('model'),
        'sampling_seed_enforced': False, 'sampling': 'server_defaults',
        'prompt_eval_count': reply.get('prompt_eval_count'),
        'eval_count': reply.get('eval_count'), 'done_reason': reply.get('done_reason')}
    print(json.dumps(response))


if __name__ == '__main__':
    main()
