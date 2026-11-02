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


def backend_metadata(url, model, timeout):
    """Observe the version and an unambiguous exact-tag digest; never infer either."""
    out = {'ollama_version': None, 'model_digest': None}
    errors = []
    try:
        with urllib.request.urlopen(url.rstrip('/') + '/api/version', timeout=timeout) as r:
            out['ollama_version'] = json.load(r).get('version')
    except (OSError, ValueError, AttributeError) as exc:
        errors.append('version:' + type(exc).__name__)
    try:
        with urllib.request.urlopen(url.rstrip('/') + '/api/tags', timeout=timeout) as r:
            tags = json.load(r).get('models', [])
        digests = {row.get('digest') for row in tags if isinstance(row, dict)
                   and (row.get('name') == model or row.get('model') == model)
                   and isinstance(row.get('digest'), str) and row['digest']}
        if len(digests) == 1:
            out['model_digest'] = digests.pop()
        else:
            errors.append('tags:no_unique_exact_digest')
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        errors.append('tags:' + type(exc).__name__)
    out['metadata_errors'] = ','.join(errors)
    return out


def interpret_reply(reply, metadata):
    """Keep failure observations separate from choices; never record thinking contents."""
    message = reply.get('message') if isinstance(reply, dict) else None
    message = message if isinstance(message, dict) else {}
    content = message.get('content')
    observation = dict(metadata, backend='ollama', model_reported=reply.get('model'),
                       sampling_seed_enforced=False, sampling='server_defaults',
                       prompt_eval_count=reply.get('prompt_eval_count'),
                       eval_count=reply.get('eval_count'), done_reason=reply.get('done_reason'),
                       has_thinking=bool(message.get('thinking')))
    if not isinstance(content, str) or not content.strip():
        kind = 'empty_content'
    else:
        try:
            response = json.loads(content)
            if isinstance(response, dict):
                response['adapter_observation'] = observation
                return response
            kind = 'non_object_content'
        except json.JSONDecodeError:
            kind = 'malformed_content'
    raw = content if isinstance(content, str) else ''
    failure = dict(observation, kind=kind, content=raw[:4000],
                   content_truncated=len(raw) > 4000)
    return {'adapter_failure': failure}


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
    metadata = backend_metadata(args.url, args.model, args.timeout)
    req = urllib.request.Request(args.url.rstrip('/') + '/api/chat',
                                 data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as r:
            reply = json.load(r)
        if not isinstance(reply, dict):
            raise ValueError('provider response is not an object')
        response = interpret_reply(reply, metadata)
    except (OSError, ValueError, TypeError) as exc:
        response = {'adapter_failure': dict(metadata, kind='backend_error',
                                            backend_error=type(exc).__name__)}
    print(json.dumps(response))


if __name__ == '__main__':
    main()
