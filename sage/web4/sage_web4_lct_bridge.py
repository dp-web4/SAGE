#!/usr/bin/env python3
"""
SAGE → Web4 LCT Bridge

Converts SAGE's legacy identity format to schema-compliant Web4 LCT documents.

Legacy SAGE format:
- LCT URI: lct://sage:sprout:agent@raising
- Trust tensor: T4 (competence, reliability, benevolence, integrity)
- Relationships tracked manually

New Web4 format:
- LCT ID: lct:web4:society:id
- Trust tensor: T3 (talent, training, temperament) + V3 (valuation, veracity, validity)
- Full LCT document matching lct.schema.json

This bridge enables SAGE to participate in the Web4 federation with
schema-compliant identity documents.

Created: 2026-02-21 (Thor Autonomous Session #41)
Author: Thor (autonomous research)
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
import json

# Add web4 reference implementations to path
web4_ref = Path(__file__).parent.parent.parent.parent / "web4" / "implementation" / "reference"
sys.path.insert(0, str(web4_ref))

from lct_document import (
    LCTBuilder,
    LCTDocument,
    T3Tensor,
    V3Tensor,
    ValidationResult,
)


# ═══════════════════════════════════════════════════════════════
# Legacy SAGE Format Structures
# ═══════════════════════════════════════════════════════════════

@dataclass
class LegacySAGEIdentity:
    """SAGE's legacy identity format from identity.json."""
    name: str
    lct_uri: str  # lct://component:instance:role@network
    session_count: int
    phase: str
    created: str
    last_session: str


@dataclass
class LegacyT4Tensor:
    """SAGE's legacy 4-dimensional trust tensor."""
    competence: float
    reliability: float
    benevolence: float
    integrity: float


# ═══════════════════════════════════════════════════════════════
# URI Conversion
# ═══════════════════════════════════════════════════════════════

def parse_legacy_lct_uri(uri: str) -> Dict[str, str]:
    """
    Parse SAGE's legacy LCT URI format.

    Format: lct://component:instance:role@network
    Example: lct://sage:sprout:agent@raising

    Returns:
        dict with keys: component, instance, role, network
    """
    if not uri.startswith("lct://"):
        raise ValueError(f"Invalid LCT URI: {uri}")

    # Remove scheme
    parts = uri[6:]  # Remove "lct://"

    # Split on @ to get network
    if "@" not in parts:
        raise ValueError(f"Invalid LCT URI (missing @network): {uri}")

    identity_part, network = parts.split("@", 1)

    # Split identity part on :
    identity_components = identity_part.split(":")
    if len(identity_components) != 3:
        raise ValueError(f"Invalid LCT URI (expected component:instance:role): {uri}")

    component, instance, role = identity_components

    return {
        "component": component,
        "instance": instance,
        "role": role,
        "network": network,
    }


def derived_session_count(identity_file):
    """Git-derived session count for the instance line holding `identity_file`.

    None when the path is not an instance line, or the census cannot run -- the
    caller records "unavailable" rather than silently substituting the
    self-reported number.
    """
    try:
        from pathlib import Path as _P
        from sage.federation import census
        from datetime import date
        parts = _P(identity_file).resolve().parts
        inst = parts[parts.index("instances") + 1]
        rows = census.build("HEAD", "strict", date.today())
        return next((r["recorded"] for r in rows if r["instance"] == inst), None)
    except Exception:
        return None


def legacy_to_web4_lct_id(uri: str, society: str = "web4") -> str:
    """
    Convert legacy LCT URI to Web4-compliant LCT ID.

    Legacy: lct://sage:sprout:agent@raising
    Web4:   lct:web4:society:sage-sprout-agent

    Args:
        uri: Legacy LCT URI
        society: Society name (default: "web4")

    Returns:
        Schema-compliant LCT ID
    """
    parsed = parse_legacy_lct_uri(uri)

    # Construct identifier from components
    # Use network as society if provided, otherwise use parameter
    actual_society = parsed["network"] if parsed["network"] else society

    # Combine component-instance-role as unique ID
    unique_id = f"{parsed['component']}-{parsed['instance']}-{parsed['role']}"

    return f"lct:{society}:society:{unique_id}"


# ═══════════════════════════════════════════════════════════════
# Trust Tensor Conversion
# ═══════════════════════════════════════════════════════════════

def t4_to_t3(t4: LegacyT4Tensor) -> T3Tensor:
    """
    Convert SAGE's T4 tensor to Web4's T3 tensor.

    T4 dimensions: competence, reliability, benevolence, integrity
    T3 dimensions: talent, training, temperament

    Mapping rationale:
    - talent ≈ competence (ability to perform)
    - training ≈ reliability (learned through experience)
    - temperament ≈ (benevolence + integrity) / 2 (behavioral stability)

    Args:
        t4: Legacy T4 tensor

    Returns:
        Web4-compliant T3 tensor
    """
    return T3Tensor(
        talent=t4.competence,
        training=t4.reliability,
        temperament=(t4.benevolence + t4.integrity) / 2.0,
    )


def t4_to_v3(t4: LegacyT4Tensor) -> V3Tensor:
    """
    Convert SAGE's T4 tensor to Web4's V3 tensor.

    T4 dimensions: competence, reliability, benevolence, integrity
    V3 dimensions: valuation, veracity, validity

    Mapping rationale:
    - valuation ≈ benevolence (value provided to others)
    - veracity ≈ integrity (truthfulness)
    - validity ≈ (competence + reliability) / 2 (correctness)

    Args:
        t4: Legacy T4 tensor

    Returns:
        Web4-compliant V3 tensor
    """
    return V3Tensor(
        valuation=t4.benevolence,
        veracity=t4.integrity,
        validity=(t4.competence + t4.reliability) / 2.0,
    )


# ═══════════════════════════════════════════════════════════════
# SAGE-Specific Capabilities
# ═══════════════════════════════════════════════════════════════

SAGE_CAPABILITIES = {
    "grounding": [
        "dialogue:conversational",
        "memory:episodic",
        "learning:curriculum",
    ],
    "awareness": [
        "dialogue:conversational",
        "memory:episodic",
        "learning:curriculum",
        "identity:self_reference",
    ],
    "integration": [
        "dialogue:conversational",
        "memory:episodic",
        "learning:curriculum",
        "identity:self_reference",
        "reasoning:conceptual",
    ],
    "autonomy": [
        "dialogue:conversational",
        "memory:episodic",
        "learning:curriculum",
        "identity:self_reference",
        "reasoning:conceptual",
        "planning:goal_directed",
    ],
    "creating": [
        "dialogue:conversational",
        "memory:episodic",
        "learning:curriculum",
        "identity:self_reference",
        "reasoning:conceptual",
        "planning:goal_directed",
        "creation:generative",
    ],
}


def get_sage_capabilities_for_phase(phase: str) -> List[str]:
    """Get capabilities list for SAGE's current development phase."""
    return SAGE_CAPABILITIES.get(phase, SAGE_CAPABILITIES["grounding"])


# ═══════════════════════════════════════════════════════════════
# Bridge Functions
# ═══════════════════════════════════════════════════════════════

def load_sage_identity(identity_file: Path) -> Tuple[LegacySAGEIdentity, Dict]:
    """Load SAGE's identity from identity.json."""
    with open(identity_file) as f:
        data = json.load(f)

    identity_data = data["identity"]

    identity = LegacySAGEIdentity(
        name=identity_data["name"],
        lct_uri=identity_data["lct"],
        session_count=identity_data["session_count"],
        phase=identity_data["phase"],
        created=identity_data["created"],
        last_session=identity_data["last_session"],
    )

    # Return full data for relationship extraction
    return identity, data


def normalize_trust_tensor(tensor_data: Dict[str, float]) -> LegacyT4Tensor:
    """
    Normalize trust tensor from either old 4-dim or new 3-dim format.

    Old format (identity.json pre-2026-03): competence, reliability, benevolence, integrity
    New format (canonical Web4 T3):         talent, training, temperament

    Returns LegacyT4Tensor in either case (bridge handles T4→T3 conversion).
    """
    if "talent" in tensor_data:
        # New canonical format — expand to T4 for bridge compatibility
        return LegacyT4Tensor(
            competence=tensor_data["talent"],
            reliability=tensor_data["training"],
            benevolence=tensor_data.get("temperament", 0.5),
            integrity=tensor_data.get("temperament", 0.5),
        )
    else:
        # Legacy 4-dim format
        return LegacyT4Tensor(
            competence=tensor_data.get("competence", 0.5),
            reliability=tensor_data.get("reliability", 0.5),
            benevolence=tensor_data.get("benevolence", 0.5),
            integrity=tensor_data.get("integrity", 0.5),
        )


def extract_trust_from_relationship(relationship: Dict, entity: str = "claude") -> LegacyT4Tensor:
    """Extract T4 trust tensor from SAGE's relationship data."""
    if entity not in relationship:
        # Return neutral trust if relationship doesn't exist
        return LegacyT4Tensor(
            competence=0.5,
            reliability=0.5,
            benevolence=0.5,
            integrity=0.5,
        )

    tensor_data = relationship[entity]["trust_tensor"]
    return normalize_trust_tensor(tensor_data)


def create_web4_lct_for_sage(
    identity: LegacySAGEIdentity,
    t4_trust: LegacyT4Tensor,
    society: str = "web4",
    issuing_society: str = "lct:web4:society:raising",
) -> LCTDocument:
    """
    Create a schema-compliant Web4 LCT document for SAGE.

    Args:
        identity: SAGE's legacy identity
        t4_trust: SAGE's T4 trust tensor
        society: Society name for LCT ID
        issuing_society: Issuing society LCT

    Returns:
        Validated LCT document
    """
    # Convert URI to LCT ID
    lct_id = legacy_to_web4_lct_id(identity.lct_uri, society)

    # Parse legacy URI for entity type
    parsed = parse_legacy_lct_uri(identity.lct_uri)
    entity_type = "ai"  # SAGE is an AI entity

    # Convert trust tensors
    t3 = t4_to_t3(t4_trust)
    v3 = t4_to_v3(t4_trust)

    # Get capabilities for current phase
    capabilities = get_sage_capabilities_for_phase(identity.phase)

    # Build LCT document
    # Note: LCTBuilder auto-generates lct_id and subject from entity_type + name
    builder = LCTBuilder(entity_type, parsed['instance'])

    # Add binding (mock for now - would need real TPM2 key)
    builder = builder.with_binding(
        public_key="sage_sprout_mock_key_placeholder",
        binding_proof="cose:mock_proof_placeholder",
    )

    # Add birth certificate with witnesses
    citizen_role = f"lct:web4:role:citizen:{entity_type}"
    # Dennis (creator) and Claude (tutor) as witnesses
    witnesses = ["lct:web4:society:dennis", "lct:web4:society:claude"]
    builder = builder.with_birth_certificate(
        issuing_society=issuing_society,
        citizen_role=citizen_role,
        witnesses=witnesses,
    )

    # Add trust tensors
    builder = builder.with_t3(
        talent=t3.talent,
        training=t3.training,
        temperament=t3.temperament,
    )

    builder = builder.with_v3(
        valuation=v3.valuation,
        veracity=v3.veracity,
        validity=v3.validity,
    )

    # Add capabilities
    for capability in capabilities:
        builder = builder.add_capability(capability)

    # Build and validate
    doc = builder.build()

    return doc


# ═══════════════════════════════════════════════════════════════
# Main Bridge Function
# ═══════════════════════════════════════════════════════════════

def bridge_sage_to_web4(
    identity_file: Path,
    output_file: Optional[Path] = None,
    validate: bool = True,
) -> Tuple[LCTDocument, ValidationResult]:
    """
    Convert SAGE's legacy identity to Web4 LCT document.

    Args:
        identity_file: Path to SAGE's identity.json
        output_file: Optional path to save LCT document
        validate: Whether to validate against schema

    Returns:
        (LCTDocument, ValidationResult)
    """
    # Load SAGE identity
    identity, full_data = load_sage_identity(identity_file)

    # Extract trust from primary relationship (Claude)
    t4_trust = extract_trust_from_relationship(full_data.get("relationships", {}))

    # Create Web4 LCT document
    lct_doc = create_web4_lct_for_sage(identity, t4_trust)

    # Validate if requested
    validation = lct_doc.validate() if validate else ValidationResult(valid=True, errors=[])

    # Save if output file specified
    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(lct_doc.to_dict(), f, indent=2)
        print(f"✅ Web4 LCT document saved to: {output_file}")

    return lct_doc, validation


# ═══════════════════════════════════════════════════════════════
# Chain Registration
# ═══════════════════════════════════════════════════════════════

def register_on_chain(
    identity_file: Path,
    chain_url: str = "http://localhost:1317",
    sender: str = "",
) -> Optional[str]:
    """
    Register a SAGE instance on the ACT blockchain.

    Generates a Web4-compliant LCT document from identity.json,
    then mints it on the ACT chain via REST API.

    Returns the on-chain LCT ID on success, None on failure.
    Non-blocking: returns None if chain is unreachable.

    Args:
        identity_file: Path to SAGE's identity.json
        chain_url: ACT chain REST API URL
        sender: Cosmos account address for signing

    Returns:
        On-chain LCT ID string, or None
    """
    try:
        # Preflight BEFORE touching the chain, and before checking whether the
        # chain is even reachable: a blocked identity should be reported on the
        # box that holds it, not first discovered on the day a node comes up.
        # Fails closed -- a preflight that cannot run is not a pass.
        from sage.federation.mint_preflight import preflight
        reasons = preflight(identity_file)
        if reasons:
            print("  [chain] preflight BLOCKED this mint -- nothing was written:")
            for r in reasons:
                print(f"  [chain]   - {r}")
            print("  [chain] audit: python3 -m sage.federation.mint_preflight")
            return None

        from sage.web4.act_chain_client import ACTChainClient

        client = ACTChainClient(base_url=chain_url)

        # Check chain health first
        if not client.health_check():
            print("  [chain] ACT chain not reachable — skipping registration")
            return None

        # Load identity
        identity, full_data = load_sage_identity(identity_file)

        # Generate canonical LCT ID
        lct_id = legacy_to_web4_lct_id(identity.lct_uri)

        # Check if already registered
        existing = client.get_lct(lct_id)
        if existing and existing.get("lct_id"):
            print(f"  [chain] Already registered: {lct_id}")
            return lct_id

        # Extract trust tensor (handles both old and new formats)
        t4_trust = extract_trust_from_relationship(full_data.get("relationships", {}))
        t3 = t4_to_t3(t4_trust)
        v3 = t4_to_v3(t4_trust)

        # Build metadata
        # `lct://sage:cbp:agent@raising`.split(":")[1] is `'//sage'`, not `'cbp'`
        # -- the scheme separator. Every LCT minted by this path before
        # 2026-09-12 carries `machine: "//sage"`. Parse the URI instead.
        from sage.federation.mint_preflight import uri_machine
        machine = uri_machine(identity.lct_uri) or "unknown"

        # The count is self-reported and this write is not revisable, so the
        # metadata declares where the number came from rather than implying it
        # is a fact. `session_count_derived` is the git-derived figure from
        # sage.federation.census under the stated basis; when the two disagree
        # a later reader can tell which one was minted.
        derived = derived_session_count(identity_file)

        metadata = {
            "machine": machine,
            "phase": identity.phase,
            "session_count": str(identity.session_count),
            "session_count_source": "identity.json:identity.session_count",
            "session_count_derived": str(derived) if derived is not None else "unavailable",
            "session_count_basis": "scope=line counter=strict (sage.federation.census)",
            "component": "sage",
        }

        # Mint on chain
        result = client.mint_lct(
            entity_name=identity.name,
            entity_type="agent",
            t3_tensor={"talent": t3.talent, "training": t3.training, "temperament": t3.temperament},
            v3_tensor={"valuation": v3.valuation, "veracity": v3.veracity, "validity": v3.validity},
            metadata=metadata,
            sender=sender,
        )

        if result:
            print(f"  [chain] Registered on ACT chain: {lct_id}")
            return lct_id
        else:
            print("  [chain] Registration failed (tx broadcast returned None)")
            return None

    except Exception as e:
        print(f"  [chain] Registration error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# CLI Interface
# ═══════════════════════════════════════════════════════════════

def main():
    """CLI for SAGE → Web4 LCT bridge."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert SAGE's legacy identity to Web4 LCT document"
    )
    parser.add_argument(
        "--identity",
        type=Path,
        default=Path(__file__).parent.parent / "raising" / "state" / "identity.json",
        help="Path to SAGE identity.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path for Web4 LCT document (default: print to stdout)",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip schema validation",
    )

    args = parser.parse_args()

    # Bridge SAGE to Web4
    print(f"🔄 Converting SAGE identity from: {args.identity}")
    lct_doc, validation = bridge_sage_to_web4(
        args.identity,
        args.output,
        validate=not args.no_validate,
    )

    # Print validation results
    if validation.valid:
        print("✅ LCT document is schema-compliant!")
    else:
        print(f"❌ Validation failed with {len(validation.errors)} errors:")
        for error in validation.errors:
            print(f"  - {error}")

    # Print document if no output file
    if not args.output:
        print("\n" + "="*70)
        print("Web4 LCT Document:")
        print("="*70)
        print(json.dumps(lct_doc.to_dict(), indent=2))

    # Print summary
    print("\n" + "="*70)
    print("Conversion Summary:")
    print("="*70)
    doc_dict = lct_doc.to_dict()
    print(f"Entity Type: {doc_dict['binding']['entity_type']}")
    print(f"LCT ID: {doc_dict['lct_id']}")
    print(f"Subject: {doc_dict['subject']}")
    print(f"T3 Composite: {doc_dict.get('t3_tensor', {}).get('composite_score', 'N/A')}")
    print(f"V3 Composite: {doc_dict.get('v3_tensor', {}).get('composite_score', 'N/A')}")
    print(f"Capabilities: {len(doc_dict.get('policy', {}).get('capabilities', []))}")
    print(f"Birth Certificate: {'Yes' if doc_dict.get('birth_certificate') else 'No'}")
    print(f"Birth Witnesses: {', '.join(doc_dict.get('birth_certificate', {}).get('birth_witnesses', []))}")
    print(f"Schema Valid: {'✅' if validation.valid else '❌'}")


if __name__ == "__main__":
    main()
