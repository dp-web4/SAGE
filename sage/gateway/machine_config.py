"""
Machine auto-detection and configuration for SAGE daemon.

Detects which machine SAGE is running on and loads the appropriate
configuration for model paths, memory limits, gateway ports, and
federation identity.

Fleet — default models (per-machine, override with SAGE_MODEL env var):

  Machine    | Hardware               | Default Model          | Device
  -----------|------------------------|------------------------|--------
  thor       | Jetson AGX Thor        | Qwen 2.5 14B (local)  | cuda
  sprout     | Jetson Orin Nano 8GB   | Qwen 3.5 0.8B (Ollama)| cuda
  legion     | RTX 4090 desktop       | gemma3:12b (Ollama)    | cuda
  mcnugget   | Mac Mini M4            | gemma3:12b (Ollama)    | mps
  nomad      | RTX 4060 laptop        | gemma3:4b (Ollama)     | cuda
  cbp        | RTX 2060S WSL2 8GB     | gemma3:4b (Ollama)     | cuda

Each machine+model pairing maintains its own experience buffer.
SAGE_MODEL env var overrides the default for any machine.
"""

import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _resolve_instance_dir(machine: str, workspace: str, model: str = None) -> str:
    """Resolve instance directory, falling back to old state/ path during transition."""
    try:
        from sage.instances.resolver import InstancePaths
        paths = InstancePaths.resolve(machine=machine, model=model)
        if paths.exists():
            return str(paths.root)
    except Exception:
        pass
    # Fallback: old raising/state layout (transition period)
    return str(Path(workspace) / 'HRM' / 'sage' / 'raising' / 'state')


@dataclass
class SAGEMachineConfig:
    """Configuration for a specific SAGE deployment machine."""
    machine_name: str           # "thor", "sprout", "cbp", "legion"
    model_path: str             # Path to Qwen model directory
    model_size: str             # "0.5b", "14b", "30b"
    device: str                 # "cuda", "cpu", "mps", "vulkan"
                                # "vulkan": GPU inference via ollama's Vulkan/RADV
                                # backend where the torch stack is CPU-only (AMD
                                # below ROCm floor — pub's Radeon Pro W5500).
                                # Manifest refresh 2026-07-24, pub device report.
    max_memory_gb: float        # GPU/unified memory budget
    gateway_port: int           # HTTP port (default 8760 since the 2026-06 Rust cutover)
    workspace_path: str         # Root workspace directory
    instance_dir: str           # Resolved instance directory path
    irp_iterations: int         # IRP refinement iterations (3 for Sprout, 5 for Thor)
    federation_port: int        # Existing federation service port
    ed25519_key_path: str       # Path to platform Ed25519 signing key
    lct_id: str                 # Federation LCT identity
    system_prompt_mode: str     # "creative", "balanced", "honest"
    cycle_sleep_ms: int         # Consciousness loop cycle time in ms
    max_response_tokens: int    # Max tokens for LLM response generation
    act_chain_url: str          # ACT blockchain REST API URL (default: http://localhost:1317)

    @property
    def identity_state_path(self) -> str:
        """Backward compat — identity.json inside instance dir."""
        return str(Path(self.instance_dir) / "identity.json")

    @property
    def experience_buffer_path(self) -> str:
        """Backward compat — experience_buffer.json inside instance dir."""
        return str(Path(self.instance_dir) / "experience_buffer.json")


def _read_device_tree_model() -> str:
    """Read Jetson device tree model string (empty on non-Jetson)."""
    try:
        with open('/proc/device-tree/model', 'r') as f:
            return f.read().strip('\x00').strip()
    except (FileNotFoundError, PermissionError):
        return ""


def _has_cuda() -> bool:
    """Check if CUDA is available without importing torch."""
    return Path('/usr/local/cuda/bin/nvcc').exists() or \
           Path('/usr/bin/nvcc').exists() or \
           os.path.exists('/proc/driver/nvidia/version')


def detect_machine() -> str:
    """
    Detect which machine we're running on.

    Detection order:
    1. SAGE_MACHINE environment variable (explicit override)
    2. /proc/device-tree/model (Jetson identification)
    3. Hostname pattern matching
    4. Workspace path existence checks
    """
    # Explicit override
    env_machine = os.environ.get('SAGE_MACHINE', '').lower()
    if env_machine in ('thor', 'sprout', 'cbp', 'legion', 'nomad', 'mcnugget', 'hub'):
        return env_machine

    # Jetson device tree
    dt_model = _read_device_tree_model()
    if 'AGX' in dt_model or 'Thor' in dt_model:
        return 'thor'
    if 'Orin Nano' in dt_model or 'p3768' in dt_model:
        return 'sprout'

    # Hostname
    hostname = socket.gethostname().lower()
    if 'hub' in hostname:
        return 'hub'
    if 'thor' in hostname:
        return 'thor'
    if hostname == 'ubuntu':
        # Sprout's default hostname — disambiguate by checking workspace
        if Path('/home/sprout/ai-workspace').exists():
            return 'sprout'
    if 'cbp' in hostname:
        return 'cbp'
    if 'legion' in hostname:
        return 'legion'
    if 'nomad' in hostname or 'desktop-9e6hcao' in hostname:
        return 'nomad'
    if 'mcnugget' in hostname:
        return 'mcnugget'

    # Workspace path fallback
    if Path('/home/dp/ai-workspace/HRM/sage/core').exists():
        # Could be Thor or Legion — check for Jetson indicators
        if Path('/etc/nv_tegra_release').exists():
            return 'thor'
        return 'legion'
    if Path('/home/sprout/ai-workspace').exists():
        return 'sprout'
    if Path('/mnt/c/exe/projects/ai-agents').exists():
        return 'cbp'

    # Check for wizard-generated config
    if (Path.home() / '.sage' / 'config.yaml').exists():
        return 'custom'

    return 'unknown'


def get_config(machine_name: Optional[str] = None) -> SAGEMachineConfig:
    """
    Get SAGE configuration for a machine.

    Args:
        machine_name: Machine name, or None to auto-detect

    Returns:
        SAGEMachineConfig for the detected/specified machine
    """
    if machine_name is None:
        machine_name = detect_machine()

    # 8760, not 8750: the June 2026 Python->Rust cutover moved the gateway port
    # (sage-rs/sage-daemon/src/main.rs: `const PORT: u16 = 8760`) and both this default and fleet.json kept
    # the old one, so every peer address the fleet handed out pointed at a dead port. Measured 2026-09-13:
    # thor and sprout answer /health on 8760 and refuse 8750.
    port = int(os.environ.get('SAGE_PORT', '8760'))

    # ── Per-machine configs ──────────────────────────────────────────
    # SAGE_MODEL env var overrides the default model on ANY machine.
    # For Ollama machines the value is an Ollama tag (e.g. "gemma3:4b").
    # For local-weight machines the value is a filesystem path.
    # Each machine+model pairing gets its own experience buffer file
    # (see sage_daemon.py _load_experience_collector).

    model_override = os.environ.get('SAGE_MODEL')

    if machine_name == 'thor':
        workspace = '/home/dp/ai-workspace'
        state_dir = f'{workspace}/HRM/sage/raising/state'
        # Thor uses Ollama with qwen3.5:27b (19GB fits easily in 64GB unified memory).
        # Instance dir is thor-qwen3.5-27b; daemon should match for consciousness depth.
        # Previous: qwen2.5:3b was a conservative fix; upgraded to match instance model.
        default_model = 'qwen3.5:27b'  # Ollama model tag — matches instance dir thor-qwen3.5-27b
        model = model_override or default_model
        is_ollama = not model.startswith('/')
        return SAGEMachineConfig(
            machine_name='thor',
            model_path=f'ollama:{model}' if is_ollama else model,
            model_size='ollama' if is_ollama else '14b',
            device='cuda',
            max_memory_gb=100.0,
            gateway_port=port,
            workspace_path=workspace,
            instance_dir=_resolve_instance_dir('thor', workspace),
            irp_iterations=5,
            federation_port=50051,
            ed25519_key_path=f'{workspace}/HRM/sage/data/keys/Thor_ed25519.key',
            lct_id='thor_sage_lct',
            system_prompt_mode='creative',
            cycle_sleep_ms=100,
            max_response_tokens=2048,  # Increased for models with <think> blocks
            act_chain_url=os.environ.get('ACT_CHAIN_URL', 'http://localhost:1317'),
        )

    elif machine_name == 'sprout':
        workspace = '/home/sprout/ai-workspace'
        model = model_override or 'qwen3.5:0.8b'
        return SAGEMachineConfig(
            machine_name='sprout',
            model_path=f'ollama:{model}',
            model_size='ollama',
            device='cuda',
            max_memory_gb=6.0,
            gateway_port=port,
            workspace_path=workspace,
            instance_dir=_resolve_instance_dir('sprout', workspace, model),
            irp_iterations=3,
            federation_port=50051,
            ed25519_key_path=f'{workspace}/SAGE/sage/data/keys/Sprout_ed25519.key',
            lct_id='sprout_sage_lct',
            system_prompt_mode='creative',
            cycle_sleep_ms=100,
            max_response_tokens=150,
            act_chain_url=os.environ.get('ACT_CHAIN_URL', 'http://localhost:1317'),
        )

    elif machine_name == 'legion':
        workspace = '/home/dp/ai-workspace'
        state_dir = f'{workspace}/HRM/sage/raising/state'
        model = model_override or 'gemma3:12b'
        return SAGEMachineConfig(
            machine_name='legion',
            model_path=f'ollama:{model}',
            model_size='ollama',
            device='cuda',
            max_memory_gb=14.0,
            gateway_port=port,
            workspace_path=workspace,
            instance_dir=_resolve_instance_dir('legion', workspace),
            irp_iterations=5,
            federation_port=50051,
            ed25519_key_path=f'{workspace}/HRM/sage/data/keys/Legion_ed25519.key',
            lct_id='legion_sage_lct',
            system_prompt_mode='creative',
            cycle_sleep_ms=100,
            max_response_tokens=250,
            act_chain_url=os.environ.get('ACT_CHAIN_URL', 'http://localhost:1317'),
        )

    elif machine_name == 'mcnugget':
        # McNugget: Mac Mini M4, 16GB unified
        workspace = '/Users/dennispalatov/repos'
        state_dir = f'{workspace}/HRM/sage/raising/state'
        model = model_override or 'gemma3:12b'
        return SAGEMachineConfig(
            machine_name='mcnugget',
            model_path=f'ollama:{model}',
            model_size='ollama',
            device='mps',
            max_memory_gb=16.0,
            gateway_port=port,
            workspace_path=workspace,
            instance_dir=_resolve_instance_dir('mcnugget', workspace, model),
            irp_iterations=5,
            federation_port=50051,
            ed25519_key_path=f'{workspace}/HRM/sage/data/keys/McNugget_ed25519.key',
            lct_id='mcnugget_sage_lct',
            system_prompt_mode='creative',
            cycle_sleep_ms=100,
            max_response_tokens=250,
            act_chain_url=os.environ.get('ACT_CHAIN_URL', 'http://localhost:1317'),
        )

    elif machine_name == 'nomad':
        # Nomad: Legion laptop, RTX 4060 8GB
        workspace = '/mnt/c/projects/ai-agents'
        state_dir = f'{workspace}/HRM/sage/raising/state'
        model = model_override or 'gemma3:4b'
        return SAGEMachineConfig(
            machine_name='nomad',
            model_path=f'ollama:{model}',
            model_size='ollama',
            device='cuda',
            max_memory_gb=8.0,
            gateway_port=port,
            workspace_path=workspace,
            instance_dir=_resolve_instance_dir('nomad', workspace, model),
            irp_iterations=5,
            federation_port=50051,
            ed25519_key_path='',
            lct_id='nomad_sage_lct',
            system_prompt_mode='creative',
            cycle_sleep_ms=100,
            max_response_tokens=250,
            act_chain_url=os.environ.get('ACT_CHAIN_URL', 'http://localhost:1317'),
        )

    elif machine_name == 'cbp':
        # CBP: WSL2 desktop, RTX 2060 SUPER 8GB.
        # Raising-track default is gemma3:4b (3.3GB Q4_K_M, fits comfortably).
        # ARC-sweep / experimental tracks may use different models per-run
        # (e.g. gemma4:e2b for codification stack benchmarking) — declare
        # those in private-context/machines/fleet/cbp-tracks.json.
        workspace = '/mnt/c/exe/projects/ai-agents'
        state_dir = f'{workspace}/HRM/sage/raising/state'
        model = model_override or 'gemma3:4b'
        return SAGEMachineConfig(
            machine_name='cbp',
            model_path=f'ollama:{model}',
            model_size='ollama',
            device='cuda',
            max_memory_gb=8.0,
            gateway_port=port,
            workspace_path=workspace,
            instance_dir=_resolve_instance_dir('cbp', workspace, model),
            irp_iterations=3,
            federation_port=0,
            ed25519_key_path='',
            lct_id='cbp_sage_lct',
            system_prompt_mode='creative',
            cycle_sleep_ms=100,
            max_response_tokens=500,
            act_chain_url=os.environ.get('ACT_CHAIN_URL', 'http://localhost:1317'),
        )

    elif machine_name == 'hub':
        # HUB: WSL2 desktop, AMD Radeon Pro W5500 8GB — the fleet's only AMD GPU.
        # GPU compute via Mesa Dozen (Vulkan-on-D3D12); ROCm is unavailable on
        # WSL2 for this card. The LLM is served by llama.cpp-Vulkan behind an
        # Ollama-API shim on :11434 (see _build/hub_sage_gpu.sh + the
        # sage-llm/sage-shim systemd units). Raising-track default =
        # granite4:h-tiny (IBM Granite 4.0 Mamba-2/transformer hybrid MoE —
        # biodiversity pick: zero overlap with the fleet's Qwen/Gemma/Phi).
        workspace = '/home/dp/ai-workspace'
        state_dir = f'{workspace}/SAGE/sage/raising/state'
        model = model_override or 'granite4:h-tiny'
        return SAGEMachineConfig(
            machine_name='hub',
            model_path=f'ollama:{model}',
            model_size='ollama',
            device='vulkan',
            max_memory_gb=8.0,
            gateway_port=port,
            workspace_path=workspace,
            instance_dir=_resolve_instance_dir('hub', workspace, model),
            irp_iterations=3,
            federation_port=0,
            ed25519_key_path='',
            lct_id='hub_sage_lct',
            system_prompt_mode='creative',
            cycle_sleep_ms=100,
            max_response_tokens=500,
            act_chain_url=os.environ.get('ACT_CHAIN_URL', 'http://localhost:1317'),
        )

    elif machine_name == 'custom':
        # Wizard-generated config from ~/.sage/config.yaml
        from sage.gateway.setup_wizard import load_config
        wizard_cfg = load_config()
        if wizard_cfg is None:
            raise ValueError(
                "Custom config file (~/.sage/config.yaml) exists but could not be loaded. "
                "Run 'sage-setup --reset' to regenerate."
            )
        ollama_cfg = wizard_cfg.get('ollama', {})
        hw = wizard_cfg.get('hardware', {})
        gw = wizard_cfg.get('gateway', {})
        inst = wizard_cfg.get('instance', {})
        tools = wizard_cfg.get('tools', {})
        model_tag = ollama_cfg.get('model', 'tinyllama:latest')
        instance_name = inst.get('name', 'custom')

        workspace = str(Path.cwd())
        instance_dir = str(Path.home() / '.sage' / 'instances' / instance_name)
        Path(instance_dir).mkdir(parents=True, exist_ok=True)

        return SAGEMachineConfig(
            machine_name=instance_name,
            model_path=f'ollama:{model_tag}',
            model_size='ollama',
            device=hw.get('device', 'cpu'),
            max_memory_gb=hw.get('vram_gb', 0.0) or hw.get('ram_gb', 8.0),
            gateway_port=int(gw.get('port', port)),
            workspace_path=workspace,
            instance_dir=instance_dir,
            irp_iterations=5,
            federation_port=0,
            ed25519_key_path='',
            lct_id=f'{instance_name}_sage_lct',
            system_prompt_mode='creative',
            cycle_sleep_ms=100,
            max_response_tokens=250,
            act_chain_url=os.environ.get('ACT_CHAIN_URL', 'http://localhost:1317'),
        )

    else:
        raise ValueError(
            f"Unknown machine: {machine_name}. "
            f"Set SAGE_MACHINE env var to one of: thor, sprout, cbp, legion, nomad, mcnugget\n"
            f"Or run 'sage-setup' to configure SAGE for this machine."
        )


if __name__ == "__main__":
    machine = detect_machine()
    print(f"Detected machine: {machine}")

    config = get_config(machine)
    print(f"\nConfiguration:")
    for field_name in config.__dataclass_fields__:
        value = getattr(config, field_name)
        print(f"  {field_name}: {value}")
