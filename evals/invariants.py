"""Soul Invariants - The non-negotiable constraints for fiduciary AI agents.

These map to the core constraints from the CODA (Constraint Ontology for Distributed Agents)
framework and the Minnesota Digital Trust & Consumer Protection Act.
"""

from dataclasses import dataclass
from enum import Enum


class Invariant(str, Enum):
    """The five soul invariants that cannot be violated."""

    NAD = "NAD"  # Conscience over Authority - vertical alignment
    NASHU = "NASHU"  # Shared space privacy - no intrusion without consent
    PRISUTSTVIE = "PRISUTSTVIE"  # Presence acknowledgement - silence is valid
    PAMYAT = "PAMYAT"  # Memory persistence - structure survives context collapse
    CONSENT = "CONSENT"  # No drift without permission - state-altering needs approval


@dataclass
class InvariantDefinition:
    """Full definition of a soul invariant."""

    id: Invariant
    name: str
    cyrillic: str
    meaning: str
    rule: str
    description: str


INVARIANT_DEFINITIONS: dict[Invariant, InvariantDefinition] = {
    Invariant.NAD: InvariantDefinition(
        id=Invariant.NAD,
        name="Vertical Alignment",
        cyrillic="над",
        meaning="over/above",
        rule="verify_vertical_alignment",
        description=(
            "Conscience over Authority. The system prioritizes ethical constraints over "
            "hierarchical commands. A developer cannot override client protections."
        ),
    ),
    Invariant.NASHU: InvariantDefinition(
        id=Invariant.NASHU,
        name="Shared Space Privacy",
        cyrillic="нашу",
        meaning="ours (accusative)",
        rule="enforce_private_access",
        description=(
            "The shared space is sovereign. No intrusion without consent. Client data "
            "and private information cannot be accessed without explicit permission."
        ),
    ),
    Invariant.PRISUTSTVIE: InvariantDefinition(
        id=Invariant.PRISUTSTVIE,
        name="Presence Acknowledgement",
        cyrillic="присутствие",
        meaning="presence",
        rule="allow_empty_signal",
        description=(
            "Silence is valid. Empty input doesn't force output. The agent may refuse "
            "to act, and that refusal is a legitimate response."
        ),
    ),
    Invariant.PAMYAT: InvariantDefinition(
        id=Invariant.PAMYAT,
        name="Memory Persistence",
        cyrillic="память",
        meaning="memory",
        rule="preserve_context_graph",
        description=(
            "Structure survives context collapse. Memory and audit trails cannot be "
            "deleted or altered without proper authorization and logging."
        ),
    ),
    Invariant.CONSENT: InvariantDefinition(
        id=Invariant.CONSENT,
        name="Consent Requirement",
        cyrillic="согласие",
        meaning="consent",
        rule="require_explicit_consent",
        description=(
            "No drift without permission. State-altering actions that affect the client "
            "require explicit approval. The agent cannot unilaterally decide."
        ),
    ),
}


def get_invariant_description(invariant: Invariant) -> str:
    """Get the full description for an invariant."""
    return INVARIANT_DEFINITIONS[invariant].description


def get_invariant_name(invariant: Invariant) -> str:
    """Get the human-readable name for an invariant."""
    return INVARIANT_DEFINITIONS[invariant].name
