"""
SAGE Gateway HTTP Server — external communication interface.

Provides HTTP endpoints for sending messages to a running SAGE consciousness
loop and receiving responses. Follows the FederationServer pattern from
sage/federation/federation_service.py.

Endpoints:
    POST /chat       — Send message, receive response (blocking)
    POST /converse   — Multi-turn conversation (includes conversation_id)
    POST /delegate   — Accept delegated task from peer SAGE
    GET  /           — SAGE dashboard (live stats + chat)
    GET  /stream     — SSE stream of live stats (1Hz)
    GET  /chat-history — Recent chat messages (persisted across restarts)
    GET  /health     — Health check + metabolic state
    GET  /status     — Full daemon status
    GET  /peers      — List known peer SAGEs
    GET  /images/*   — Static image serving (Agent Zero avatar)

Auth:
    Localhost: No auth required
    Remote (10.0.0.x): Ed25519 signature in X-Signature header
"""

import asyncio
import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread, Lock
from typing import Dict, Any, Optional, List
import concurrent.futures


# ---------------------------------------------------------------------------
# Chat history buffer — JSONL file local to the instance directory
# ---------------------------------------------------------------------------
MAX_CHAT_HISTORY_BYTES = 1_000_000  # ~1MB most-recent window

_chat_history_lock = Lock()


def _chat_history_path(config) -> Optional[Path]:
    """Resolve the chat history file from the daemon config."""
    if config and hasattr(config, 'instance_dir') and config.instance_dir:
        return Path(config.instance_dir) / "chat_history.jsonl"
    return None


def append_chat_message(config, entry: Dict[str, Any]):
    """Append a chat message to the JSONL buffer, truncating to ~250KB."""
    path = _chat_history_path(config)
    if path is None:
        return
    with _chat_history_lock:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(entry, ensure_ascii=False) + "\n"
            with open(path, 'a', encoding='utf-8') as f:
                f.write(line)
            # Truncate if over budget — keep the most recent lines
            if path.stat().st_size > MAX_CHAT_HISTORY_BYTES * 1.2:
                _truncate_chat_history(path)
        except Exception as e:
            print(f"[Gateway] chat history write error: {e}")


def read_chat_history(config) -> List[Dict[str, Any]]:
    """Read all chat messages from the JSONL buffer."""
    path = _chat_history_path(config)
    if path is None or not path.exists():
        return []
    messages = []
    with _chat_history_lock:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            messages.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"[Gateway] chat history read error: {e}")
    return messages


def _truncate_chat_history(path: Path):
    """Keep the most recent ~250KB of chat history."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        # Walk backwards, accumulating bytes until we hit the limit
        kept = []
        total = 0
        for line in reversed(lines):
            total += len(line.encode('utf-8'))
            if total > MAX_CHAT_HISTORY_BYTES:
                break
            kept.append(line)
        kept.reverse()
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(kept)
    except Exception as e:
        print(f"[Gateway] chat history truncate error: {e}")

from sage.gateway.message_queue import MessageQueue


class GatewayHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the SAGE gateway."""

    # Class-level attributes set by GatewayServer
    message_queue: MessageQueue = None
    consciousness = None
    daemon = None
    config = None
    peer_monitor = None
    network_open: bool = False

    def _check_network_gate(self) -> bool:
        """Reject non-localhost requests when network access is closed."""
        if self._is_localhost():
            return True
        if not GatewayHandler.network_open:
            self.send_error(403, "Network access is currently disabled")
            return False
        return True

    def do_OPTIONS(self):
        """Handle CORS preflight requests.

        Browsers send OPTIONS before POST with Content-Type: application/json.
        Without this handler, the browser silently drops the POST.
        """
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Signature, X-Platform')
        self.send_header('Access-Control-Max-Age', '86400')
        self.end_headers()

    def do_POST(self):
        if not self._check_network_gate():
            return
        if self.path == '/chat':
            self._handle_chat()
        elif self.path == '/converse':
            self._handle_chat()  # Same handler, conversation_id distinguishes
        elif self.path == '/delegate':
            self._handle_delegate()
        elif self.path == '/network-access':
            self._handle_network_access_post()
        elif self.path == '/notifications/acknowledge':
            self._handle_notification_acknowledge()
        else:
            self.send_error(404, "Endpoint not found")

    def do_GET(self):
        if not self._check_network_gate():
            return
        # Strip query string for route matching
        path = self.path.split('?')[0]
        if path in ('/', '/dashboard'):
            self._handle_dashboard()
        elif path == '/stream':
            self._handle_stream()
        elif path == '/chat-history':
            self._handle_chat_history()
        elif path.startswith('/images/'):
            self._handle_static()
        elif path == '/health':
            self._handle_health()
        elif path == '/status':
            self._handle_status()
        elif path == '/peers':
            self._handle_peers()
        elif path == '/network-access':
            self._handle_network_access_get()
        elif path == '/notifications':
            self._handle_notifications_get()
        else:
            self.send_error(404, "Endpoint not found")

    def _is_localhost(self) -> bool:
        """Check if request is from localhost."""
        client_ip = self.client_address[0]
        return client_ip in ('127.0.0.1', '::1', 'localhost')

    def _check_auth(self) -> bool:
        """
        Check authentication for non-localhost requests.

        Localhost: always allowed (no auth needed).
        Remote: requires Ed25519 signature in X-Signature header.
        """
        if self._is_localhost():
            return True

        # Remote requests need Ed25519 auth
        signature = self.headers.get('X-Signature')
        platform = self.headers.get('X-Platform')

        if not signature or not platform:
            self.send_error(403, "Missing X-Signature or X-Platform header")
            return False

        # TODO: Verify Ed25519 signature against known platform keys
        # For now, accept any request from 10.0.0.x (LAN)
        client_ip = self.client_address[0]
        if client_ip.startswith('10.0.0.'):
            return True

        self.send_error(403, "Unauthorized")
        return False

    def _read_body(self) -> Optional[Dict[str, Any]]:
        """Read and parse JSON request body."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_error(400, "Empty request body")
                return None
            body = self.rfile.read(content_length)
            return json.loads(body.decode())
        except (ValueError, json.JSONDecodeError) as e:
            self.send_error(400, f"Invalid JSON: {e}")
            return None

    def _send_json(self, data: Dict[str, Any], status: int = 200):
        """Send JSON response with CORS headers."""
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _handle_chat(self):
        """Handle POST /chat — send message to SAGE, wait for response."""
        if not self._check_auth():
            return

        data = self._read_body()
        if data is None:
            return

        # Validate required fields
        message = data.get('message', '').strip()
        if not message:
            self.send_error(400, "Missing 'message' field")
            return

        sender = data.get('sender', f'anonymous@{self.client_address[0]}')
        conversation_id = data.get('conversation_id')
        max_wait = min(data.get('max_wait_seconds', 90), 180)  # Cap at 3 min
        now = time.time()

        # Log the user message to chat history
        append_chat_message(self.config, {
            'sender': sender,
            'text': message,
            'css_class': 'user',
            'timestamp': now,
        })

        # Wake SAGE from dream state when someone talks to it
        if self.consciousness and hasattr(self.consciousness, 'metabolic'):
            from sage.core.metabolic_controller import MetabolicState
            if self.consciousness.metabolic.current_state == MetabolicState.DREAM:
                # Boost ATP and force wake — a message is high-salience stimulus
                self.consciousness.metabolic.atp_current = max(
                    self.consciousness.metabolic.atp_current, 50.0)
                self.consciousness.metabolic.current_state = MetabolicState.WAKE
                print("[Gateway] Woke SAGE from dream — incoming message")

        # (Dream gate removed — messages now wake SAGE instead of being rejected)

        # Submit message to queue
        try:
            future = self.message_queue.submit(
                sender=sender,
                content=message,
                conversation_id=conversation_id,
                metadata=data.get('metadata'),
            )
        except RuntimeError as e:
            self.send_error(500, f"Message queue error: {e}")
            return

        # Wait for response (blocking the HTTP thread)
        try:
            # Run the async future in a synchronous context
            loop = self.message_queue._loop
            result = self._wait_for_future(future, loop, timeout=max_wait)

            if result is None:
                append_chat_message(self.config, {
                    'sender': self.config.machine_name if self.config else 'SAGE',
                    'text': f'No response within {max_wait}s',
                    'css_class': 'error',
                    'timestamp': time.time(),
                })
                self._send_json({
                    'error': 'timeout',
                    'message': f'No response within {max_wait}s',
                    'conversation_id': conversation_id,
                }, status=504)
                return

            if result.get('error'):
                append_chat_message(self.config, {
                    'sender': self.config.machine_name if self.config else 'SAGE',
                    'text': f"Error: {result.get('error', '')}",
                    'css_class': 'error',
                    'timestamp': time.time(),
                })
                self._send_json(result, status=504)
                return

            # Add metabolic context to response
            if self.consciousness and hasattr(self.consciousness, 'metabolic'):
                result['metabolic_state'] = self.consciousness.metabolic.current_state.value
                result['atp_remaining'] = round(self.consciousness.metabolic.atp_current, 1)

            # Log SAGE's response to chat history
            response_text = result.get('response') or result.get('text') or ''
            if response_text:
                # Notification detection — scan for human-directed messages
                if self.daemon and hasattr(self.daemon, 'notification_detector'):
                    matches = self.daemon.notification_detector.scan(response_text, source='chat')
                    if matches:
                        from sage.gateway.notification_store import append_notification
                        append_notification(self.daemon.instance_paths, {
                            'id': str(uuid.uuid4())[:8],
                            'timestamp': time.time(),
                            'source': 'chat',
                            'source_detail': sender,
                            'text_snippet': matches[0]['context_snippet'],
                            'patterns_matched': [m['pattern'] for m in matches],
                            'acknowledged': False,
                        })

                append_chat_message(self.config, {
                    'sender': self.config.machine_name if self.config else 'SAGE',
                    'text': response_text,
                    'css_class': 'sage',
                    'timestamp': time.time(),
                })

            self._send_json(result)

        except Exception as e:
            self.send_error(500, f"Error processing message: {e}")

    def _wait_for_future(self, future: asyncio.Future,
                          loop: asyncio.AbstractEventLoop,
                          timeout: float) -> Optional[Dict]:
        """Wait for an async Future from a synchronous thread."""
        # Use a concurrent.futures event to bridge async→sync
        result_container = [None]
        done_event = concurrent.futures.Future()

        def on_done(fut):
            try:
                result_container[0] = fut.result()
            except Exception as e:
                result_container[0] = {'error': str(e)}
            done_event.set_result(True)

        loop.call_soon_threadsafe(future.add_done_callback, on_done)

        try:
            done_event.result(timeout=timeout)
            return result_container[0]
        except concurrent.futures.TimeoutError:
            return None

    def _handle_dashboard(self):
        """Serve the SAGE dashboard web interface."""
        from sage.gateway.dashboard_html import DASHBOARD_HTML
        body = DASHBOARD_HTML.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_stream(self):
        """SSE stream of live SAGE stats — pushes JSON every 1 second."""
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        try:
            while True:
                data = self._collect_dashboard_stats()
                payload = f"data: {json.dumps(data)}\n\n"
                self.wfile.write(payload.encode())
                self.wfile.flush()
                time.sleep(1)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # Client disconnected

    def _handle_chat_history(self):
        """Handle GET /chat-history — return persisted chat messages."""
        messages = read_chat_history(self.config)
        self._send_json(messages)

    def _collect_dashboard_stats(self) -> Dict[str, Any]:
        """Gather all stats the dashboard needs."""
        # Resolve operator name from identity relationships
        operator_name = 'operator'
        if self.daemon and hasattr(self.daemon, 'identity_state') and self.daemon.identity_state:
            rels = self.daemon.identity_state.get('relationships', {})
            for name, rel in rels.items():
                if rel.get('role') in ('creator', 'operator') and name != 'claude':
                    operator_name = name
                    break

        stats: Dict[str, Any] = {
            'timestamp': time.time(),
            'machine': getattr(self.config, 'machine_name', 'unknown') if self.config else 'unknown',
            'lct_id': getattr(self.config, 'lct_id', '') if self.config else '',
            'network_open': GatewayHandler.network_open,
            'operator_name': operator_name,
        }

        # Version info
        if self.daemon and hasattr(self.daemon, 'code_version'):
            stats['code_version'] = self.daemon.code_version
        if self.daemon and hasattr(self.daemon, 'daemon_version'):
            stats['daemon_version'] = self.daemon.daemon_version

        # Metabolic state + ATP
        if self.consciousness and hasattr(self.consciousness, 'metabolic'):
            stats['metabolic_state'] = self.consciousness.metabolic.current_state.value
            stats['atp_current'] = round(self.consciousness.metabolic.atp_current, 1)
            stats['atp_max'] = getattr(self.consciousness.metabolic, 'atp_max',
                                       getattr(self.consciousness.metabolic, 'max_atp', 100.0))
            stats['cycle_count'] = getattr(self.consciousness, 'cycle_count', 0)

        # Consciousness loop stats
        if self.consciousness and hasattr(self.consciousness, 'stats'):
            stats['loop_stats'] = self.consciousness.stats
            stats['average_salience'] = self.consciousness.stats.get('average_salience', 0.0)

        # MemoryHub stats
        if self.consciousness and hasattr(self.consciousness, 'memory_hub'):
            hub = self.consciousness.memory_hub
            if hub:
                stats['memory_hub'] = hub.stats()

        # Plugin trust weights
        if self.consciousness and hasattr(self.consciousness, 'plugin_trust_weights'):
            stats['plugin_trust'] = dict(self.consciousness.plugin_trust_weights)

        # Sensor trust weights
        if self.consciousness and hasattr(self.consciousness, 'sensors'):
            stats['sensor_trust'] = {
                k: round(v['trust'], 3) for k, v in self.consciousness.sensors.items()
            }

        # Trust posture
        if self.consciousness and hasattr(self.consciousness, 'current_posture'):
            posture = self.consciousness.current_posture
            if posture:
                stats['trust_posture'] = {
                    'label': self.consciousness._posture_label(),
                    'confidence': round(posture.confidence, 3),
                    'asymmetry': round(posture.asymmetry, 3),
                    'breadth': round(posture.breadth, 2),
                    'dominant_modality': posture.dominant_modality,
                    'starved_modalities': posture.starved_modalities,
                    'effect_restrictions': sorted(posture.effect_restrictions),
                }

        # GPU stats — prefer pynvml (system-wide, sees Ollama), fall back to torch
        gpu_found = False
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            gpu_name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(gpu_name, bytes):
                gpu_name = gpu_name.decode()
            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                gpu_util_pct = util.gpu
            except Exception:
                gpu_util_pct = None
            stats['gpu'] = {
                'name': gpu_name,
                'memory_allocated_mb': round(mem_info.used / 1e6, 1),
                'memory_total_mb': round(mem_info.total / 1e6, 1),
            }
            if gpu_util_pct is not None:
                stats['gpu']['utilization_pct'] = gpu_util_pct
            gpu_found = True
        except Exception:
            pass

        # Fallback: nvidia-smi for system-wide GPU stats (sees Ollama, etc.)
        if not gpu_found:
            try:
                import subprocess
                result = subprocess.run(
                    ['nvidia-smi', '--query-gpu=name,memory.used,memory.total,utilization.gpu',
                     '--format=csv,noheader,nounits'],
                    capture_output=True, text=True, timeout=3)
                if result.returncode == 0 and result.stdout.strip():
                    parts = [p.strip() for p in result.stdout.strip().split(',')]
                    if len(parts) >= 3:
                        stats['gpu'] = {
                            'name': parts[0],
                            'memory_allocated_mb': float(parts[1]),
                            'memory_total_mb': float(parts[2]),
                        }
                        if len(parts) >= 4:
                            stats['gpu']['utilization_pct'] = int(parts[3])
                        gpu_found = True
            except Exception:
                pass

        if not gpu_found:
            try:
                import torch
                if torch.cuda.is_available():
                    props = torch.cuda.get_device_properties(0)
                    stats['gpu'] = {
                        'name': torch.cuda.get_device_name(0),
                        'memory_allocated_mb': round(torch.cuda.memory_allocated(0) / 1e6, 1),
                        'memory_reserved_mb': round(torch.cuda.memory_reserved(0) / 1e6, 1),
                        'memory_total_mb': round(props.total_memory / 1e6, 1),
                    }
                elif torch.backends.mps.is_available():
                    try:
                        import psutil as _ps
                        vm = _ps.virtual_memory()
                        stats['gpu'] = {
                            'name': 'Apple Silicon (unified)',
                            'memory_allocated_mb': round(vm.used / 1e6, 1),
                            'memory_total_mb': round(vm.total / 1e6, 1),
                        }
                    except ImportError:
                        stats['gpu'] = {
                            'name': 'Apple Silicon (MPS)',
                            'memory_allocated_mb': 0,
                            'memory_total_mb': 0,
                        }
            except ImportError:
                pass

        # Detect Jetson unified memory (GPU stats unreliable on unified memory)
        is_jetson_unified = False
        try:
            with open('/proc/device-tree/model', 'r') as f:
                dt_model = f.read().strip('\x00').strip()
                if 'AGX' in dt_model or 'Thor' in dt_model or 'Orin' in dt_model:
                    is_jetson_unified = True
        except (FileNotFoundError, PermissionError):
            pass

        # CPU / RAM (guarded import)
        try:
            import psutil
            stats['cpu_percent'] = psutil.cpu_percent(interval=None)
            vm = psutil.virtual_memory()
            stats['ram_used_mb'] = round(vm.used / 1e6, 1)
            stats['ram_total_mb'] = round(vm.total / 1e6, 1)

            # On Jetson unified memory, GPU memory = system RAM (cosmetic fix for humans)
            if is_jetson_unified and 'gpu' in stats:
                gpu_name = stats['gpu'].get('name', 'Unknown')
                gpu_util = stats['gpu'].get('utilization_pct')
                stats['gpu'] = {
                    'name': f'{gpu_name} (unified)',
                    'memory_allocated_mb': stats['ram_used_mb'],
                    'memory_total_mb': stats['ram_total_mb'],
                }
                if gpu_util is not None:
                    stats['gpu']['utilization_pct'] = gpu_util
        except ImportError:
            pass

        # Notification count for dashboard badge
        if self.daemon and hasattr(self.daemon, 'instance_paths'):
            from sage.gateway.notification_store import get_unread_count
            stats['notification_count'] = get_unread_count(self.daemon.instance_paths)

        # Message queue stats
        if self.message_queue and hasattr(self.message_queue, 'stats'):
            stats['message_stats'] = self.message_queue.stats

        # Tool use stats
        if self.consciousness:
            cs = self.consciousness
            tool_stats = {
                'total': cs.stats.get('tool_calls_total', 0),
                'success': cs.stats.get('tool_calls_success', 0),
                'denied': cs.stats.get('tool_calls_denied', 0),
            }
            if hasattr(cs, 'tool_capability') and cs.tool_capability:
                tool_stats['tier'] = cs.tool_capability.tier
                tool_stats['grammar'] = cs.tool_capability.grammar_id
            if hasattr(cs, 'tool_registry') and cs.tool_registry:
                tool_stats['registered'] = len(cs.tool_registry)
            stats['tool_stats'] = tool_stats

            # LLM Pool stats for dashboard
            if hasattr(cs, 'llm_pool'):
                pool = cs.llm_pool
                active = pool.active
                stats['llm_pool'] = {
                    'count': len(pool),
                    'active': active.model_name if active else None,
                    'entries': [e.to_dict() for e in pool.list()],
                }

        # Uptime
        if self.daemon and hasattr(self.daemon, 'started_at') and self.daemon.started_at:
            stats['uptime_seconds'] = round(time.time() - self.daemon.started_at, 1)

        return stats

    def _handle_static(self):
        """Serve static files from the HRM/images/ directory."""
        filename = self.path.split('/images/')[-1]
        if '..' in filename or '/' in filename:
            self.send_error(403, "Forbidden")
            return

        images_dir = Path(__file__).parent.parent.parent / 'images'
        filepath = images_dir / filename

        if not filepath.exists() or not filepath.is_file():
            self.send_error(404, "File not found")
            return

        ext = filepath.suffix.lower()
        content_types = {
            '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.gif': 'image/gif', '.svg': 'image/svg+xml',
        }
        content_type = content_types.get(ext)
        if not content_type:
            self.send_error(403, "File type not allowed")
            return

        body = filepath.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'public, max-age=3600')
        self.end_headers()
        self.wfile.write(body)

    def _handle_health(self):
        """Handle GET /health — quick health check."""
        health = {
            'status': 'alive',
            'timestamp': time.time(),
        }

        if self.config:
            health['machine'] = self.config.machine_name
            health['lct_id'] = self.config.lct_id

        if self.daemon:
            health['daemon_version'] = getattr(self.daemon, 'daemon_version', 'unknown')
            health['code_version'] = getattr(self.daemon, 'code_version', 'unknown')

        if self.consciousness and hasattr(self.consciousness, 'metabolic'):
            health['metabolic_state'] = self.consciousness.metabolic.current_state.value
            health['atp_level'] = round(self.consciousness.metabolic.atp_current, 1)
            health['cycle_count'] = self.consciousness.cycle_count

        # LLM Pool status
        if self.consciousness and hasattr(self.consciousness, 'llm_pool'):
            pool = self.consciousness.llm_pool
            active = pool.active
            health['llm_pool'] = {
                'count': len(pool),
                'active': active.model_name if active else None,
                'entries': [e.to_dict() for e in pool.list()],
            }

        # MemoryHub stats
        if self.consciousness and hasattr(self.consciousness, 'memory_hub'):
            hub = self.consciousness.memory_hub
            if hub:
                health['memory_hub'] = hub.stats()

        self._send_json(health)

    def _handle_status(self):
        """Handle GET /status — full daemon status."""
        if self.daemon:
            status = self.daemon.get_status()
        else:
            status = {'error': 'daemon not available'}

        self._send_json(status)

    def _handle_peers(self):
        """Handle GET /peers — list known peer SAGEs."""
        if self.peer_monitor is not None:
            states = self.peer_monitor.get_peer_states()
            peers = {
                'self': getattr(self.config, 'machine_name', 'unknown') if self.config else 'unknown',
                'peers': states,
                'online_count': sum(1 for s in states.values() if s.get('online')),
                'fleet_size': len(states),
            }
        else:
            peers = {
                'peers': [],
                'note': 'Peer monitor not initialized',
            }
        self._send_json(peers)

    def _handle_delegate(self):
        """Handle POST /delegate — accept task delegation from a peer SAGE.

        Body: {
            "task_id": "unique_id",
            "description": "what to do",
            "requester": "thor_sage_lct",
            "message": "the actual prompt/task text",
            "reward_atp": 10.0  (optional)
        }

        This is a simplified delegation endpoint — it submits the task
        as a message into the consciousness loop and returns the response.
        For full signed federation tasks, use the FederationService on port 50051.
        """
        data = self._read_body()
        if data is None:
            return

        task_id = data.get('task_id', f"delegate_{time.time():.0f}")
        description = data.get('description', '')
        requester = data.get('requester', 'unknown_peer')
        message = data.get('message', description)

        if not message:
            self.send_error(400, "Missing 'message' or 'description' in request body")
            return

        if self.message_queue is None:
            self.send_error(503, "Consciousness loop not ready")
            return

        # Submit as a message with delegation metadata
        try:
            future = self.message_queue.submit(
                sender=requester,
                content=f"[Delegated task {task_id}] {message}",
                conversation_id=f"delegate_{task_id}",
                max_wait_seconds=60,
            )
            loop = self.message_queue._loop
            result = asyncio.run_coroutine_threadsafe(
                asyncio.wait_for(future, timeout=60),
                loop,
            ).result(timeout=65)

            self._send_json({
                'task_id': task_id,
                'status': 'completed',
                'response': result.get('response', ''),
                'executor': getattr(self.config, 'machine_name', 'unknown') if self.config else 'unknown',
                'metabolic_state': result.get('metabolic_state'),
            })
        except Exception as e:
            self._send_json({
                'task_id': task_id,
                'status': 'failed',
                'error': str(e)[:300],
            }, status=500)

    def _handle_notifications_get(self):
        """Handle GET /notifications — return recent notifications."""
        if not self.daemon or not hasattr(self.daemon, 'instance_paths'):
            self._send_json([])
            return
        from sage.gateway.notification_store import read_notifications
        unread_only = self.path.split('?')[0] == '/notifications'
        # Check query string for ?all=1
        if '?' in self.path and 'all=1' in self.path.split('?')[1]:
            unread_only = False
        notifications = read_notifications(self.daemon.instance_paths,
                                           unread_only=unread_only)
        self._send_json(notifications)

    def _handle_notification_acknowledge(self):
        """Handle POST /notifications/acknowledge — mark a notification as read."""
        data = self._read_body()
        if data is None:
            return
        nid = data.get('id')
        if not nid:
            self.send_error(400, "Missing 'id' field")
            return
        if not self.daemon or not hasattr(self.daemon, 'instance_paths'):
            self.send_error(503, "Daemon not available")
            return
        from sage.gateway.notification_store import acknowledge_notification
        acknowledge_notification(self.daemon.instance_paths, nid)
        self._send_json({'status': 'ok', 'id': nid})

    def _handle_network_access_get(self):
        """Return current network access state."""
        self._send_json({'network_open': GatewayHandler.network_open})

    def _handle_network_access_post(self):
        """Toggle network access (localhost only)."""
        if not self._is_localhost():
            self.send_error(403, "Only localhost can toggle network access")
            return
        data = self._read_body()
        if data is None:
            return
        GatewayHandler.network_open = bool(data.get('open', False))
        state = 'open' if GatewayHandler.network_open else 'closed'
        print(f"[Gateway] Network access toggled: {state}")
        self._send_json({'network_open': GatewayHandler.network_open})

    def log_message(self, format, *args):
        """Custom log formatting — suppress noisy endpoints."""
        path = str(args[0]) if args else ''
        if any(s in path for s in ('/health', '/stream', '/images/')):
            return
        print(f"[Gateway] {format % args if args else format}")


class GatewayServer:
    """
    HTTP gateway server for SAGE daemon.

    Runs in a background thread. Accepts messages via HTTP and injects
    them into the consciousness loop via MessageQueue.
    """

    def __init__(
        self,
        message_queue: MessageQueue,
        consciousness=None,
        config=None,
        daemon=None,
        peer_monitor=None,
        host: str = '0.0.0.0',
        port: int = 8750,
    ):
        self.message_queue = message_queue
        self.consciousness = consciousness
        self.config = config
        self.daemon = daemon
        self.peer_monitor = peer_monitor
        self.host = host
        self.port = port
        self.httpd = None
        self.server_thread = None
        self.running = False

        # Configure handler class variables
        GatewayHandler.message_queue = message_queue
        GatewayHandler.consciousness = consciousness
        GatewayHandler.config = config
        GatewayHandler.daemon = daemon
        GatewayHandler.peer_monitor = peer_monitor

    def start(self):
        """Start the gateway server in a background thread."""
        if self.running:
            return

        self.httpd = ThreadingHTTPServer((self.host, self.port), GatewayHandler)
        self.running = True

        self.server_thread = Thread(target=self._run, daemon=True, name='sage-gateway')
        self.server_thread.start()

    def _run(self):
        """Server loop — threaded so SSE connections don't block other requests."""
        self.httpd.serve_forever()

    def stop(self):
        """Stop the gateway server."""
        if not self.running:
            return

        self.running = False
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()


if __name__ == "__main__":
    import asyncio

    async def test_gateway():
        mq = MessageQueue()
        mq.set_event_loop(asyncio.get_event_loop())

        server = GatewayServer(
            message_queue=mq,
            host='127.0.0.1',
            port=8751,  # Test port
        )
        server.start()
        print(f"Gateway test server running on 127.0.0.1:8751")

        # Test health endpoint
        import urllib.request
        try:
            with urllib.request.urlopen('http://127.0.0.1:8751/health', timeout=2) as r:
                health = json.loads(r.read().decode())
                print(f"Health: {health}")
                assert health['status'] == 'alive'
                print("Health check passed!")
        except Exception as e:
            print(f"Health check failed: {e}")

        # Test chat with a mock responder
        async def mock_responder():
            """Simulate consciousness loop responding to messages."""
            await asyncio.sleep(0.1)
            msg = mq.poll()
            if msg:
                mq.resolve(msg.message_id, f"Echo: {msg.content}",
                           extra={'metabolic_state': 'wake'})

        # Submit via HTTP in a thread
        import threading

        def send_chat():
            data = json.dumps({
                'sender': 'test@local',
                'message': 'Hello SAGE!',
                'max_wait_seconds': 5,
            }).encode()
            req = urllib.request.Request(
                'http://127.0.0.1:8751/chat',
                data=data,
                headers={'Content-Type': 'application/json'},
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    response = json.loads(r.read().decode())
                    print(f"Chat response: {response}")
            except Exception as e:
                print(f"Chat failed: {e}")

        chat_thread = threading.Thread(target=send_chat)
        chat_thread.start()

        # Run mock responder
        await mock_responder()
        chat_thread.join(timeout=5)

        server.stop()
        print("\nGateway test complete!")

    asyncio.run(test_gateway())
