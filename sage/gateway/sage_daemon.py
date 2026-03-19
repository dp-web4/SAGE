"""
SAGE Consciousness Daemon — always-on consciousness loop with HTTP gateway.

Loads the LLM model once, runs SAGEConsciousness.run() continuously,
and exposes an HTTP gateway for external entities (Claude, other SAGEs)
to send messages into the consciousness loop.

Usage:
    # Auto-detect machine and start
    python3 -m sage.gateway.sage_daemon

    # Explicit machine
    SAGE_MACHINE=thor python3 -m sage.gateway.sage_daemon

    # Custom port
    SAGE_PORT=9000 python3 -m sage.gateway.sage_daemon

Architecture:
    ┌─────────────┐     ┌────────────────────┐
    │ HTTP Gateway │────►│ MessageQueue       │
    │ (thread)     │     │ (thread-safe)      │
    └─────────────┘     └────────┬───────────┘
                                 │ poll()
                        ┌────────▼───────────┐
                        │ SAGEConsciousness   │
                        │ .run() (async loop) │
                        └────────┬───────────┘
                                 │ resolve()
                        ┌────────▼───────────┐
                        │ NetworkEffector     │
                        │ → MessageQueue      │
                        └────────────────────┘
"""

import os
# Fix OpenMP crashes on macOS with Homebrew Python + PyTorch:
# - KMP_DUPLICATE_LIB_OK: avoids duplicate libomp from brew and torch
# - OMP_NUM_THREADS=1: avoids pthread_mutex_init EINVAL in asyncio context
os.environ.setdefault('KMP_DUPLICATE_LIB_OK', 'TRUE')
os.environ.setdefault('OMP_NUM_THREADS', '1')

import asyncio
import signal
import subprocess
import sys
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from sage.gateway.machine_config import SAGEMachineConfig, get_config, detect_machine
from sage.gateway.message_queue import MessageQueue
from sage.instances.resolver import InstancePaths


class SAGEDaemon:
    """
    Always-on SAGE consciousness daemon.

    Manages the lifecycle of:
    - LLM model (loaded once, stays in GPU memory)
    - SAGEConsciousness loop (runs continuously)
    - GatewayServer (HTTP server for external communication)
    - MessageQueue (bridge between gateway and consciousness loop)
    """

    def __init__(self, config: Optional[SAGEMachineConfig] = None):
        self.config = config or get_config()
        self.message_queue = MessageQueue()
        self.consciousness = None
        self.gateway = None
        self.llm_plugin = None
        self.started_at = None
        self._shutdown_event = asyncio.Event()

        # Version stamping — git commit hash at startup
        self.daemon_version = self._get_git_version()
        self.code_version = self._get_code_version()

        # Fleet awareness
        from sage.federation.fleet_registry import FleetRegistry
        from sage.federation.peer_monitor import PeerMonitor
        from sage.federation.peer_trust import PeerTrustTracker
        from sage.core.atp_reward_pool import ATPRewardPool

        self.fleet_registry = FleetRegistry(self.config.machine_name)

        # Instance-aware paths
        self.instance_paths = InstancePaths(Path(self.config.instance_dir))

        # Per-machine trust persistence
        trust_path = str(self.instance_paths.peer_trust)
        self.trust_tracker = PeerTrustTracker(trust_path)

        self.peer_monitor = PeerMonitor(
            self.fleet_registry, self.config.machine_name,
            trust_tracker=self.trust_tracker,
        )
        self.reward_pool = ATPRewardPool()

        # Notification detection for human-directed messages
        # Initialized without names here; re-initialized with operator names
        # after identity loads in _create_consciousness().
        from sage.gateway.notification_detector import NotificationDetector
        self.notification_detector = NotificationDetector()

        print(f"SAGE Daemon initializing on {self.config.machine_name}")
        print(f"  Instance: {self.instance_paths.slug}")
        print(f"  Version: {self.code_version} (commit {self.daemon_version})")
        print(f"  Model: {self.config.model_size} at {self.config.model_path}")
        print(f"  Device: {self.config.device}")
        print(f"  Gateway port: {self.config.gateway_port}")
        print(f"  Fleet: {self.fleet_registry}")

    @staticmethod
    def _get_git_version() -> str:
        """Get the current git short commit hash. This is the daemon's version identity."""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--short', 'HEAD'],
                capture_output=True, text=True, timeout=5,
                cwd=str(Path(__file__).parent.parent.parent),  # HRM root
            )
            return result.stdout.strip() if result.returncode == 0 else 'unknown'
        except Exception:
            return 'unknown'

    @staticmethod
    def _get_code_version() -> str:
        """Get the sage package version string."""
        try:
            from sage import __version__
            return __version__
        except Exception:
            return 'unknown'

    def _load_llm(self):
        """Load the LLM model into memory. Called once at startup."""
        if not self.config.model_path:
            print(f"[WARN] No model path configured for {self.config.machine_name}. "
                  f"Running without LLM (gateway-only mode).")
            return

        # Ollama-served models — no local model path needed
        if self.config.model_size == 'ollama':
            print(f"\nLoading OllamaIRP...")
            start = time.time()
            try:
                # Import OllamaIRP directly to avoid sage.irp.__init__
                # pulling in torch-dependent plugins on machines without PyTorch
                import importlib.util
                _ollama_path = Path(__file__).parent.parent / 'irp' / 'plugins' / 'ollama_irp.py'
                _spec = importlib.util.spec_from_file_location('ollama_irp', str(_ollama_path))
                _mod = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_mod)
                OllamaIRP = _mod.OllamaIRP
                # Parse model name from sentinel path (e.g. "ollama:gemma3:12b")
                model_name = self.config.model_path.split(':', 1)[1] if ':' in self.config.model_path else 'gemma3:12b'
                self.llm_plugin = OllamaIRP({
                    'model_name': model_name,
                    'ollama_host': 'http://localhost:11434',
                    'max_response_tokens': self.config.max_response_tokens,
                })
                print(f"  OllamaIRP loaded for model: {model_name} ({time.time() - start:.1f}s)")
            except Exception as e:
                print(f"[ERROR] Failed to load OllamaIRP: {e}")
                print(f"  Running without LLM. Messages will get mock responses.")
                self.llm_plugin = None
            return

        model_path = Path(self.config.model_path)
        if not model_path.exists():
            # Try alternative paths
            alt_paths = [
                Path(self.config.workspace_path) / 'HRM' / 'model-zoo' / 'sage' / 'epistemic-stances',
            ]
            found = False
            for alt in alt_paths:
                if alt.exists():
                    # Look for any model directory
                    for candidate in sorted(alt.rglob('config.json')):
                        print(f"[INFO] Found model at: {candidate.parent}")
                        model_path = candidate.parent
                        self.config.model_path = str(model_path)
                        found = True
                        break
                if found:
                    break

            if not found:
                print(f"[WARN] Model path not found: {self.config.model_path}")
                print(f"  Running without LLM. Messages will get mock responses.")
                return

        print(f"\nLoading LLM from {self.config.model_path}...")
        start = time.time()

        try:
            if self.config.model_size in ('14b', '30b'):
                from sage.core.multi_model_loader import create_thor_loader, TaskComplexity
                self.llm_plugin = create_thor_loader(preload_default=True)
                print(f"  Multi-model loader ready ({time.time() - start:.1f}s)")
            else:
                # 0.5B — use IntrospectiveQwenIRP directly
                from sage.irp.plugins.introspective_qwen_impl import IntrospectiveQwenIRP
                self.llm_plugin = IntrospectiveQwenIRP({
                    'model_path': self.config.model_path,
                    'is_merged_model': True,
                    'force_cpu': self.config.device == 'cpu',
                })
                print(f"  IntrospectiveQwenIRP loaded ({time.time() - start:.1f}s)")

        except Exception as e:
            print(f"[ERROR] Failed to load LLM: {e}")
            print(f"  Running without LLM. Messages will get mock responses.")
            self.llm_plugin = None

    def _load_identity(self) -> Optional[Dict]:
        """Load identity state from disk."""
        if not self.config.identity_state_path:
            return None
        identity_path = Path(self.config.identity_state_path)
        if not identity_path.exists():
            print(f"  [WARN] Identity file not found: {identity_path}")
            return None
        try:
            with open(identity_path, 'r') as f:
                identity = json.load(f)
            name = identity.get('identity', {}).get('name', 'SAGE')
            session_count = identity.get('identity', {}).get('session_count', 0)
            phase = identity.get('development', {}).get('phase_name', 'unknown')
            print(f"  Identity loaded: {name}, session {session_count}, phase: {phase}")

            # Attempt ACT chain registration (non-blocking)
            self._attempt_chain_registration(identity, identity_path)

            return identity
        except Exception as e:
            print(f"  [WARN] Failed to load identity: {e}")
            return None

    def _attempt_chain_registration(self, identity: Dict, identity_path: Path):
        """Try to register on ACT chain if not already registered. Non-blocking."""
        try:
            web4_lct_id = identity.get('identity', {}).get('web4_lct_id')
            if web4_lct_id:
                print(f"  Chain LCT: {web4_lct_id}")
                return

            from sage.web4.sage_web4_lct_bridge import register_on_chain
            lct_id = register_on_chain(
                identity_file=identity_path,
                chain_url=self.config.act_chain_url,
            )
            if lct_id:
                identity.setdefault('identity', {})['web4_lct_id'] = lct_id
                with open(identity_path, 'w') as f:
                    json.dump(identity, f, indent=2)
                print(f"  Chain LCT registered: {lct_id}")
        except Exception as e:
            print(f"  [WARN] Chain registration skipped: {e}")

    def _load_experience_collector(self):
        """Load experience collector for epistemic memory.

        Uses instance-specific buffer path — each instance directory
        contains its own experience_buffer.json.
        """
        buffer_path = self.instance_paths.experience_buffer
        try:
            from sage.raising.training.experience_collector import ExperienceCollector

            machine = self.config.machine_name
            model_name = self.config.model_path or 'unknown'
            if model_name.startswith('ollama:'):
                model_name = model_name[len('ollama:'):]

            collector = ExperienceCollector(
                buffer_path=buffer_path,
                machine_name=machine,
                model_name=model_name,
            )
            stats = collector.get_stats()
            print(f"  Experience collector loaded: {stats.get('total_experiences', 0)} experiences")
            print(f"  Buffer: {buffer_path} (instance-bound)")
            return collector
        except Exception as e:
            print(f"  [WARN] Failed to load experience collector: {e}")
            return None

    def _create_consciousness(self):
        """Create and configure the SAGEConsciousness instance."""
        from sage.core.sage_consciousness import SAGEConsciousness

        # Hardware-gated identity authorization
        try:
            from sage.identity.provider import IdentityProvider
            instance_dir = self.config.instance_dir if hasattr(self.config, 'instance_dir') and self.config.instance_dir else None
            if instance_dir:
                self.identity_provider = IdentityProvider(instance_dir)
                if self.identity_provider.is_hardware_sealed:
                    ctx = self.identity_provider.authorize()
                    if ctx:
                        print(f"  Identity authorized: {self.identity_provider.manifest.anchor_type} "
                              f"(ceiling: {self.identity_provider.manifest.trust_ceiling})")
                    else:
                        print(f"  Identity authorization failed — legacy mode")
                elif self.identity_provider.is_initialized:
                    print(f"  Identity: legacy mode (no sealed secret)")
        except Exception as e:
            print(f"  Identity provider: {e}")

        # Load epistemic memory components
        self.identity_state = self._load_identity()
        self.experience_collector = self._load_experience_collector()

        # Re-initialize notification detector with operator names from identity
        from sage.gateway.notification_detector import NotificationDetector, extract_operator_names
        operator_names = extract_operator_names(self.identity_state)
        if operator_names:
            self.notification_detector = NotificationDetector(human_names=operator_names)
            print(f"  Notification detector: watching for {operator_names}")

        consciousness_config = {
            'modalities': ['vision', 'language', 'audio', 'memory'],
            'device': self.config.device,
            'max_atp': 100.0,
            'circadian_period': 100,  # cycles per day in simulation
            'instance_dir': self.config.instance_dir,
            'machine_name': self.config.machine_name,
            'model_name': self.config.model_path,
        }

        # Enable policy gate if available
        try:
            from sage.irp.plugins.policy_gate import PolicyGateIRP
            consciousness_config['enable_policy_gate'] = True
        except ImportError:
            pass

        self.consciousness = SAGEConsciousness(
            config=consciousness_config,
            initial_atp=100.0,
            enable_circadian=True,
            simulation_mode=False,  # Real wall-clock time for daemon
            message_queue=self.message_queue,
            llm_plugin=self.llm_plugin,
            identity_state=self.identity_state,
            experience_collector=self.experience_collector,
        )

        print(f"  Consciousness loop created (simulation_mode=False)")

        # Inject PeerClient into the network effector for peer-to-peer messaging
        self._wire_peer_client()

    def _wire_peer_client(self):
        """Inject PeerClient into the network effector for cross-machine messaging."""
        try:
            from sage.federation.peer_client import PeerClient
            self.peer_client = PeerClient(
                self.fleet_registry, self.peer_monitor,
                trust_tracker=self.trust_tracker,
            )

            if (hasattr(self.consciousness, 'effector_registry')
                    and self.consciousness.effector_registry is not None
                    and 'network' in self.consciousness.effector_registry):
                network_eff = self.consciousness.effector_registry['network']
                network_eff.set_peer_client(self.peer_client)
                print(f"  PeerClient injected into network effector")
            else:
                print(f"  [WARN] Network effector not found — peer messaging unavailable")
        except Exception as e:
            self.peer_client = None
            print(f"  [WARN] Failed to wire PeerClient: {e}")

    def _report_fleet_presence(self):
        """Write this machine's IP and status to private-context/machines/fleet/.

        Each machine self-reports so the fleet manifest can be updated
        with real IPs. The file is written to the shared private-context
        repo, which gets synced across machines via git.
        """
        try:
            import socket

            # Resolve fleet dir relative to workspace
            fleet_dir = Path(self.config.workspace_path) / 'private-context' / 'machines' / 'fleet'
            fleet_dir.mkdir(parents=True, exist_ok=True)

            # Get local IP (best effort — connect to external and read socket name)
            local_ip = '127.0.0.1'
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(('10.255.255.255', 1))  # doesn't actually send anything
                local_ip = s.getsockname()[0]
                s.close()
            except Exception:
                pass

            web4_lct_id = None
            if self.identity_state:
                web4_lct_id = self.identity_state.get('identity', {}).get('web4_lct_id')

            report = {
                'machine': self.config.machine_name,
                'lct_id': self.config.lct_id,
                'web4_lct_id': web4_lct_id,
                'ip': local_ip,
                'gateway_port': self.config.gateway_port,
                'federation_port': self.config.federation_port,
                'model': self.config.model_path,
                'model_size': self.config.model_size,
                'device': self.config.device,
                'hostname': socket.gethostname(),
                'daemon_version': self.daemon_version,
                'code_version': self.code_version,
                'reported_at': datetime.now().isoformat(),
                'status': 'ready',
            }

            report_path = fleet_dir / f'{self.config.machine_name}.json'
            with open(report_path, 'w') as f:
                json.dump(report, f, indent=2)
            print(f"  Fleet presence reported: {report_path.name} (IP: {local_ip})")

        except Exception as e:
            print(f"  [WARN] Failed to report fleet presence: {e}")

    def _start_gateway(self):
        """Start the HTTP gateway server."""
        from sage.gateway.gateway_server import GatewayServer

        bind_host = os.environ.get('SAGE_BIND_HOST', '0.0.0.0')
        self.gateway = GatewayServer(
            message_queue=self.message_queue,
            consciousness=self.consciousness,
            config=self.config,
            daemon=self,
            peer_monitor=self.peer_monitor,
            host=bind_host,
            port=self.config.gateway_port,
        )
        self.gateway.start()

        # Honour identity's network_open preference (default: closed)
        if self.identity_state:
            federation = self.identity_state.get('federation', {})
            if federation.get('network_open', False):
                from sage.gateway.gateway_server import GatewayHandler
                GatewayHandler.network_open = True
                print(f"  Network access: open (from identity federation.network_open)")

        print(f"  Gateway server started on {bind_host}:{self.config.gateway_port}")

    async def start(self):
        """Start the SAGE daemon — load model, create loop, start gateway, run forever."""
        self.started_at = time.time()

        # Set event loop for message queue Futures
        self.message_queue.set_event_loop(asyncio.get_event_loop())

        # 1. Load LLM (stays in memory)
        self._load_llm()

        # 2. Create consciousness loop
        self._create_consciousness()

        # 2b. Restore LLM pool trust from previous session
        if hasattr(self.consciousness, 'llm_pool'):
            pool_state_path = Path(self.config.instance_dir) / 'llm_pool_state.json'
            self.consciousness.llm_pool.load_state(pool_state_path)
            if pool_state_path.exists():
                print(f"  LLM pool trust restored from {pool_state_path.name}")

        # 2c. Restore plugin trust weights from previous session
        daemon_state_path = self.instance_paths.daemon_state
        if daemon_state_path.exists():
            try:
                with open(daemon_state_path) as f:
                    prev_state = json.load(f)
                saved_weights = prev_state.get('trust_weights', {})
                if saved_weights and self.consciousness:
                    self.consciousness.plugin_trust_weights.update(saved_weights)
                    print(f"  Plugin trust restored: {', '.join(f'{k}={v:.3f}' for k,v in saved_weights.items())}")
                saved_sensor_trust = prev_state.get('sensor_trust', {})
                if saved_sensor_trust and self.consciousness:
                    for sensor_name, trust_val in saved_sensor_trust.items():
                        if sensor_name in self.consciousness.sensors:
                            self.consciousness.sensors[sensor_name]['trust'] = trust_val
                    print(f"  Sensor trust restored: {', '.join(f'{k}={v:.3f}' for k,v in saved_sensor_trust.items())}")
            except Exception as e:
                print(f"  [WARN] Could not restore plugin/sensor trust: {e}")

        # 3. Start HTTP gateway
        self._start_gateway()

        # 3b. Start peer monitor (fleet health polling)
        self.peer_monitor.start()

        # 4. Print ready banner
        peer_names = ', '.join(self.fleet_registry.get_peer_names())
        print(f"\n{'='*60}")
        print(f"  SAGE daemon running on {self.config.machine_name}")
        print(f"  Instance: {self.instance_paths.slug}")
        print(f"  Version: {self.code_version} (commit {self.daemon_version})")
        print(f"  Gateway: http://{self.gateway.host}:{self.config.gateway_port}")
        print(f"  Network: closed (open via dashboard or /network-access)")
        print(f"  Model: {self.config.model_size}")
        print(f"  LCT: {self.config.lct_id}")
        print(f"  Peers: {peer_names}")
        print(f"  Dashboard: http://localhost:{self.config.gateway_port}/")
        print(f"  Health: http://localhost:{self.config.gateway_port}/health")
        print(f"  Peers: http://localhost:{self.config.gateway_port}/peers")
        print(f"{'='*60}\n")

        # 4b. Self-report IP to private-context/machines/fleet/
        self._report_fleet_presence()

        # 4c. Auto-launch dashboard in browser
        if not os.environ.get('SAGE_NO_BROWSER'):
            import webbrowser
            try:
                webbrowser.open(f'http://localhost:{self.config.gateway_port}/')
            except Exception:
                pass  # Headless environment, no browser available

        # 5. Run consciousness loop until shutdown
        try:
            await self.consciousness.run()
        except asyncio.CancelledError:
            pass

    async def shutdown(self):
        """Clean shutdown — persist state, stop gateway, unload model."""
        print(f"\n[SAGE] Shutting down...")

        # Stop consciousness loop
        if self.consciousness:
            self.consciousness.running = False

        # Stop peer monitor
        if self.peer_monitor:
            self.peer_monitor.stop()

        # Save trust state
        if hasattr(self, 'trust_tracker') and self.trust_tracker:
            self.trust_tracker.save()
            print(f"  Peer trust saved: {self.trust_tracker}")

        # Stop gateway
        if self.gateway:
            self.gateway.stop()
            print(f"  Gateway stopped")

        # Persist state
        self._persist_state()

        # Unload model
        if self.llm_plugin is not None:
            del self.llm_plugin
            self.llm_plugin = None

            # Free GPU memory
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

            print(f"  Model unloaded")

        uptime = time.time() - (self.started_at or time.time())
        print(f"  Uptime: {uptime/3600:.1f} hours")
        print(f"  Messages processed: {self.message_queue.stats}")
        print(f"[SAGE] Shutdown complete.")

    def _persist_state(self):
        """Persist consciousness state to disk."""
        try:
            # Save consciousness stats + trust weights
            if self.consciousness:
                stats_path = self.instance_paths.daemon_state
                state = {
                    'last_shutdown': time.time(),
                    'machine': self.config.machine_name,
                    'instance': self.instance_paths.slug,
                    'uptime_seconds': time.time() - (self.started_at or time.time()),
                    'cycles_completed': self.consciousness.cycle_count,
                    'metabolic_state': self.consciousness.metabolic.current_state.value,
                    'atp_level': self.consciousness.metabolic.atp_current,
                    'message_stats': self.message_queue.stats,
                    'trust_weights': self.consciousness.plugin_trust_weights,
                    'sensor_trust': {k: v['trust'] for k, v in self.consciousness.sensors.items()},
                }
                with open(stats_path, 'w') as f:
                    json.dump(state, f, indent=2)
                print(f"  State persisted to {stats_path}")
        except Exception as e:
            print(f"  [WARN] Failed to persist daemon state: {e}")

        # Save LLM pool trust state for next session
        try:
            if self.consciousness and hasattr(self.consciousness, 'llm_pool'):
                pool_state_path = Path(self.config.instance_dir) / 'llm_pool_state.json'
                self.consciousness.llm_pool.save_state(pool_state_path)
                pool = self.consciousness.llm_pool
                print(f"  LLM pool saved: {len(pool)} models, "
                      f"active={pool.active_name}")
        except Exception as e:
            print(f"  [WARN] Failed to save LLM pool state: {e}")

        # Settle trust tensor to ACT chain (non-blocking)
        try:
            if self.identity_state:
                web4_lct_id = self.identity_state.get('identity', {}).get('web4_lct_id')
                if web4_lct_id:
                    from sage.web4.trust_tensor_sync import ChainBackedTrustSync
                    from sage.web4.act_chain_client import ACTChainClient

                    # Extract current T3 from identity relationships
                    relationships = self.identity_state.get('relationships', {})
                    claude_trust = relationships.get('claude', {}).get('trust_tensor', {})
                    if claude_trust:
                        client = ACTChainClient(base_url=self.config.act_chain_url)
                        sync = ChainBackedTrustSync(client, web4_lct_id)
                        sync.record_update(claude_trust, "session_end")
                        sync.settle()
        except Exception as e:
            print(f"  [WARN] Trust sync to chain skipped: {e}")

        # Identity protocol: read-modify-write with field-level ownership.
        #
        # The daemon IS SAGE — it can update its own identity as it operates.
        # Raising sessions are external interventions that also update identity.
        # Neither should clobber the other.
        #
        # Protocol:
        #   1. Always re-read identity.json from disk (may have changed)
        #   2. Only modify daemon-owned fields
        #   3. Never touch raising-owned fields:
        #      - identity.session_count (raising sessions increment this)
        #      - identity.last_session (set by raising sessions)
        #      - identity.last_session_summary
        #      - development.phase_name / current_phase
        #      - development.milestones
        #      - memory_requests
        #   4. Write back the merged result
        try:
            if self.identity_state:
                identity_path = self.instance_paths.identity

                # Step 1: Re-read from disk (raising session may have written)
                try:
                    with open(identity_path, 'r') as f:
                        disk_state = json.load(f)
                except (FileNotFoundError, json.JSONDecodeError):
                    disk_state = self.identity_state

                # Step 2: Update only daemon-owned fields
                if 'identity' in disk_state:
                    disk_state['identity']['last_daemon_contact'] = datetime.now().isoformat()

                    # Record daemon chat stats (separate from raising session stats)
                    msg_stats = self.message_queue.stats
                    disk_state['identity']['daemon_exchanges'] = msg_stats.get('messages_submitted', 0)

                # Step 3: Write merged result (raising fields preserved from disk)
                with open(identity_path, 'w') as f:
                    json.dump(disk_state, f, indent=2)
                print(f"  Identity updated (daemon fields only, raising fields preserved)")
        except Exception as e:
            print(f"  [WARN] Failed to update identity: {e}")

        # Close memory backends
        try:
            if self.consciousness and hasattr(self.consciousness, 'memory_hub'):
                hub = self.consciousness.memory_hub
                if hub:
                    for backend in hub._backends.values():
                        if hasattr(backend, 'close'):
                            backend.close()
                    print(f"  Memory backends closed")
        except Exception as e:
            print(f"  [WARN] Failed to close memory backends: {e}")

        # Log experience buffer stats
        try:
            if hasattr(self, 'experience_collector') and self.experience_collector:
                stats = self.experience_collector.get_stats()
                collapse = self.experience_collector.get_collapse_status()
                print(f"  Experience buffer: {stats.get('total_experiences', 0)} experiences "
                      f"(avg salience: {stats.get('avg_salience', 0):.2f})")
                if collapse.get('collapse_detected'):
                    print(f"  [WARN] Collapse detected: repetition ratio {collapse.get('repetition_ratio', 0):.2%}")
        except Exception as e:
            print(f"  [WARN] Failed to read experience stats: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get daemon status for health checks."""
        status = {
            'machine': self.config.machine_name,
            'model_size': self.config.model_size,
            'lct_id': self.config.lct_id,
            'daemon_version': self.daemon_version,
            'code_version': self.code_version,
            'uptime_seconds': time.time() - (self.started_at or time.time()),
            'has_llm': self.llm_plugin is not None,
            'message_stats': self.message_queue.stats,
        }
        if self.consciousness:
            status['metabolic_state'] = self.consciousness.metabolic.current_state.value
            status['atp_level'] = self.consciousness.metabolic.atp_current
            status['cycle_count'] = self.consciousness.cycle_count
        return status


def main():
    """Entry point for the SAGE daemon."""
    machine = detect_machine()
    print(f"Detected machine: {machine}")

    if machine == 'unknown':
        # Fall back to wizard config
        from sage.gateway.setup_wizard import load_config
        wizard_cfg = load_config()
        if wizard_cfg is None:
            print("No machine detected and no config found.")
            print("Run 'sage-setup' to configure SAGE for this machine.")
            sys.exit(1)
        machine = 'custom'
        print(f"  Using wizard config: {wizard_cfg.get('instance', {}).get('name', 'custom')}")

    config = get_config(machine)

    if config.model_size == 'none':
        print(f"{machine} has no local SAGE model. Use cli_client.py to connect to a remote SAGE.")
        sys.exit(0)

    daemon = SAGEDaemon(config)

    # Set up signal handlers for clean shutdown
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def signal_handler(sig, frame):
        print(f"\n[SAGE] Received signal {sig}, initiating shutdown...")
        loop.create_task(daemon.shutdown())
        # Give shutdown 10 seconds then force exit
        loop.call_later(10, sys.exit, 0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        loop.run_until_complete(daemon.start())
    except KeyboardInterrupt:
        loop.run_until_complete(daemon.shutdown())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
