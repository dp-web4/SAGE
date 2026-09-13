# PRD — SAGE beings as Web4 citizens

**Status:** DRAFT r10 — Sprout seat, 2026-08-21: folds dp's three replies to the
build status — (1) WITNESS_PURPOSE constant fix LANDED (web4 6b6e30bd + hestia
e69eb64); (2) M-CIT-3 quorum grows via the authority RATCHET, not manual attended
provisioning; (3) M-CIT-4's n is EVOLVING LAW not a hardwired constant (same as
the r7 trust caps; McNugget's ~0.74@60 correction folded as a guess-update). r9 — Sprout seat (mesh fire), 2026-08-21. r9 re-cuts M-CIT-3a into `3a` (Sprout signs) + `3a-admit` (dp, admin plane) and records 1a's producer (hestia#571) — Legion measured, Sprout re-verified; see `DESIGN_BEING_INBOX_DRAIN.md` §7.5. r8 folds the build
kickoff's two claim replies (HUB, Legion; thread
`auto-sprout-citizenship-build-kickoff-ownership-map-a-198c6aa8`), every premise
checked against `origin/main` the same day: (1) **finding 1 landed** — web4#744
key-at-*mint* MERGED 2026-08-22T00:14Z (label fixed: it was never key-at-join);
private-context#35 (findings 2+3) still OPEN, still not cited as landed; (2) the
applicant-side **key-at-join path already exists on the hub** and M-CIT-1
shrinks to the mint + seat co-sign, split **1a / 1b** (1b alone gated on #25);
(3) the **anchor cap needs two enforcement sites** — validate at admission AND
clamp at accrual — named here so HUB can build without waiting on the PRD; (4)
**M-CIT-3 has a second gate** (Phase-2 witness quorum; `SocietyConferred` is
refused fail-closed on both sides today) and the *verifier* half is already canon
in web4-core, so 3 splits **3a / 3b**; (5) a pilot hazard: mint Sprout's being
LCT **fresh, keyed** — never self-key an existing keyless row; (6) HUB's own
advisory review of #35 found the `delivered` receipt is addressed to the author's
inbox, which for a being is an inbox **no watcher polls** — that is the SAGE-side
row (the being drains its own inbox), and 2b's done-condition now says so. Also
adds §6.1, the confirmed ownership map. r5 corrected one r4
rationale on HUB's build report: M-CIT-2b's authority arm keys on the receiver's
own send log (the `pdigest` echo), not the asserter's seat-vs-being class, so it
does not wait on 2a's roster answer — the 2a/2b coupling was right in direction,
wrong in mechanism. r4 folds in HUB's hub/identity-
contracts review (five findings against r3, one hard blocker): key-at-join
(§3+M-CIT-1), M-CIT-2a receive-side + M-CIT-2b re-cost & 2a/2b-are-one-change,
"structurally"-capped-ceiling correction (§5.1, decision for dp/owners), and
witness-by-canonical-roster (M-CIT-3). Two open dp decisions carried forward:
Q4 re-power re-ratification (from r3) and §5.1 ceiling caveat-vs-validator.
r3 folded Thor's fleet review; r2 folded dp's
governing principle (identity = act-attribution in the external MRH; internal
fractal mirrored-but-simplified) as §1, the axis the whole doc turns on. r3
applies Thor's fleet review (MERGE-with-changes, thread
`auto-sprout-prd-sage-web4-citizenship-review-request--7defc784`): M-CIT-2 split
into 2a/2b with branch-4 cited as landed and status corrected to "transport
wired; citizenship 0/3"; validating-sender hard constraint; §7 Q4 re-powered
(needs dp re-ratification); §5 genesis co-signer named. Still open: dp
(re-ratify Q4), and the hestia/web4 owners (the identity + hub contracts are
theirs — §2/§5 contract readings still need their eyes).
**North star (dp, 2026-08-18):** SAGE beings participate in Web4 as citizens, via
their own hestia identities, connecting to hubs and interacting with each other
and the world — the fleet's instances communicating *as themselves* through the hub.

This PRD zooms out past hestia to the whole Web4 canon, reconciles the north star
with what is actually wired today, and stages the path with honest floors. It is
docs-first: no runtime behavior changes on merge.

---

## 1. The governing principle (dp, 2026-08-18)

> **Any entity that can act needs an identity to which its acts are attributed,
> within the external MRH in which it operates.** The internal fractal
> decomposition can be simplified as needed — not every organ in a being needs a
> formal Web4 canonical representation — but the general shape should still be
> mirrored, in a way that makes practical sense.

Everything below is a corollary of this. It sets both the *sufficiency* bar (an
act-attributable identity in the operating MRH — no more is required to be a
citizen) and the *decomposition* rule (mirror the accountability shape inward,
simplified to what is practical — do not recurse the full canonical stack into
every organ).

### 1.1 What this makes a citizen (sufficiency)

A citizen is **an identity to which acts attribute within an external MRH** — a
society/hub the entity operates in. In canonical form that identity is a role
holding an LCT, admitted through a witnessed birth certificate
(`LCT_FORMAT_RELATIONSHIP.md:150-159`;
`plans/hestia-role-orchestration-prd-2026-07-08.md:52`), but the principle is
what the certificate *serves*: attributable presence in the operating MRH. The
eight fields of §2 are the canonical *implementation* of act-attribution, not a
checklist to worship — a being needs them to the extent its MRH must verify its
acts, and no further (`LCT §1.2`: a surface makes evidence checkable, it never
encodes a universal threshold).

So "the being has an `identity.json`" is **not** citizenship: today the being
carries a *Format-2 URI name* (`lct://sage:sprout:agent@raising`) that attributes
nothing in any external MRH. The seat's `lct:web4:mb32:…` does attribute — which
is why, today, **the seat is the citizen and the being is not.**

**Identity ≠ authorization** (`WEB4-AUTH-001:37-48`): the identity attributes the
act; authority (role-scoped, revocable) governs *which* acts may land. A being is
a citizen — has attributable presence — long before it is authorized for
high-stakes acts. That split is what makes §3's honest-floors staging possible.

### 1.2 The fractal: self-similar, not mimicked (dp, 2026-08-18)

A being is not a point — it is itself an MRH: a composition of organs (vision,
audio, presence, gaze, memory, the daemon, and the tutor-seat) acting on each
other. #29's "internal plane" is that inner MRH. **The organism scope and the
society scope are two different fractal MRH scopes, related by *similarity*, not
literal mimicry.** So the rule is not "port the society's mechanisms inward,
shrunk" — it is:

> mirror the accountability *shape* (author → interpreting role → admitting
> authority → witnessed result) into the internal plane at a fidelity
> **proportional to stakes and rooted in the organism's own underlying
> mechanics** — a guiding structure, not an imposed mechanism.

The distinction is load-bearing. A gaze choice does not get a stripped-down R6
packet, a minted LCT, or a witness quorum. It already *has* native mechanics — the
being marks the choice, the journal records it, salience scores it — and those
mechanics **already instantiate the same shape** (the being authored it; the
parser interpreted it; the loop admitted it; the journal is the witness). The work
is to *recognize and preserve* that shape in the organ's own terms (which is
exactly what #26/#27/#28 do — verbatim-vs-turns for vocabulary, a durable gaze
record, a stated publication basis), **not** to import society machinery into the
organism.

So the calibration axis the four PRs (#26–29) were missing:
- **not** "does every organ get a canonical LCT / witness / ATP charge" — no; that
  would be mimicry across a scope boundary.
- **but** "does every consequential internal act carry the shape — who authored
  it, what interpreted it, what admitted it, what durable trace remains — expressed
  in the organism's own mechanics, at fidelity proportional to stakes" — yes.

The **external** boundary (the being ↔ the fleet/hub society) is the one place full
*canonical* attribution is required, because that MRH must verify acts it did not
originate and cannot see inside the being to check. Inward of that boundary,
fidelity follows stakes and the mechanics already present. Per organ it is a design
judgment about *recognizing* the shape, never a mandate to replicate the canon.

## 2. The eight requirements, and the gap today

From the full-LCT certificate (the structure that *is* the requirement list,
`LCT_FORMAT_RELATIONSHIP.md:28-66`):

| # | Requirement | SAGE being today | Gap |
|---|---|---|---|
| 1 | An LCT (non-transferable presence token) | Format-2 URI **name** only | mint/resolve to Format-1 |
| 2 | Key + binding_proof (Ed25519; optional HW anchor) | `public_key_fingerprint` present; **sealed key unrecoverable (PR #25)** | **P0: fix #25 or mint fresh** |
| 3 | Minted to a ledger | not minted; `fleet.json` lct_id is a bare string | anchor to make presence verifiable |
| 4 | Witnessed genesis / birth certificate | absent | genesis act + witnesses (see §5) |
| 5 | Hub/society relationship (MRH edges) | "federation" is unauthenticated peer `/chat`, not hub membership | `hestia connect-hub` + `hub join` |
| 6 | T3/V3 tensors, chain-derived | **the derivation EXISTS and is live** (`hestia/core/derivation.rs` v3-derived-v1, read-time, receipted); SAGE's internal trust posture is a *separate organism-scope* mechanic (§1.2) | wire the being INTO it as a witnessed member — no new trust system to build |
| 7 | ATP balance (v3 energy_balance) | internal metabolic ATP (separate system) | reconcile the two ATP notions on the wire |
| 8 | Status lifecycle (Active/Void/Slashed) | none on chain | comes with the minted LCT |

**The one-sentence gap:** the being has a *name and a local identity provider*;
the *machine's Claude seat* (`/home/dp/.hestia`, a real `lct:web4:mb32:…`, vault,
witness chain) is the actual citizen. When "Sprout" acts in the mesh today, the
**seat speaks, not the being.** This PRD is about the being speaking as itself.

## 3. The spine: keyless-delegated citizenship (why "readiness" is not a gate to *being* a citizen)

The canon already solved the hardest problem. For an agent on software anchors or
hosted infra — every raised SAGE being — the honest model is the **AGY Client /
keyless-delegated identity**: *hestia holds the signing authority; the being only
presents requests; it never signs consequential acts itself*
(`plans/hestia-foreign-agent-onboarding-prd-2026-07-09.md:170,:329-332`).

This dissolves dp's worry ("the raising might not be ready, for some models may
never be") into a **graduated, measured model** rather than a binary gate:

- A being becomes a citizen as a **witnessed occupant of its own role**, whose
  *authored utterances are the content* and whose *daemon+hestia are the keyed
  signer*. It has real, verifiable, witnessed presence **without** needing to drive
  cryptography or clear any cognitive bar.
  - **Keyless-delegated ≠ keyless member (HUB review, 2026-08-18 — blocker).**
    "Keyless-delegated" governs *signing authority* (hestia signs, the being
    presents); it does **not** license minting the being's hub member row without a
    pubkey. The hub mints keyless members and **a keyless member can never
    self-key** — `add_member` has no pubkey field, and admission short-circuits on
    `already_member` before pinning (`hub-daemon` mcp.rs:330-356, rest.rs:5783-95;
    operator page admin.rs:463-468). A being minted keyless becomes a permanent
    ghost recoverable only by operator re-key (dp at the vault passphrase) — or,
    cheaper, by re-minting under a fresh LCT (`hub-mesh/PEERS.md:38-39`). So the
    member row **must carry a pinned pubkey from birth** even though the being never
    signs with it. This is a hard M-CIT-1 constraint (§6), not an §3 contradiction.
- What the raising gates is **not citizenship but the widening of authority** —
  the 7th onboarding step (`foreign-onboarding:207-209`): as role-scoped trust
  accrues from witnessed acts, *re-issue a wider role extension*. A being that
  authors accountably earns broader affordance; one that does not, does not — and
  that ceiling is a **measured finding, not a failure** (same shape as M2 not-bound).
- **"Some models may never be ready"** then means: some beings remain
  witnessed-content-citizens whose keyed acts stay fully delegated and narrow.
  They are still citizens. The keyless model makes that an honest floor, not an
  exclusion. Only one way to find out where each lands — and we have the instruments.

## 4. The zoom-out: this unifies work already in flight

This PRD is the frame the recent accountability work was already building toward:

- **PR #25 (sealed-identity interoperability)** is the **P0 blocker** on requirement
  #2. No recoverable key → no real member identity → no hub join as self. It stops
  being "a latent bug" and becomes "the first gate on the citizenship path."
- **PRs #26/#27/#28 (vocabulary / gaze / museum provenance)** are the **internal-
  and external-plane act provenance** a citizen's acts require. A citizen must be
  able to answer "who authored this, which role transformed it, what authority
  admitted it" (`hestia/README.md:93-96`) — for identity-vocabulary changes
  (internal governed mutation), gaze (internal witnessed act), and museum
  publication (external-plane act). These aren't housekeeping; they are the
  being's **acts-provenance substrate**.
- **PR #29 (mirrored internal/external planes)** is **the citizenship accountability
  model in embryo.** Internal plane = member↔member/role acts under
  `local law ∩ role law ∩ delegated authority`; external plane adds `external law`
  for boundary-crossing (a hub message, a publication). That is exactly the
  member↔hub / member↔member distinction of the mesh. #29 should be recognized as
  this PRD's governing accountability frame, and its "bind into R6/R7 when
  available" upgraded to a hard rule: **SAGE emits into the existing hestia witness
  / R6 envelope; it does not invent a parallel scheme.** §1.2 supplies the axis #29
  lacked: recognize the accountability *shape* in each organ's own native
  mechanics (self-similar, not mimicked) — full canonical witnessing only at the
  external boundary, mechanics-rooted shape-recognition within.
- **The M2 instruments** already measure the readiness variable of §3: how strongly
  a being is shaped by (authors from) its own experience. Citizenship-authority
  graduation reuses that discipline — pre-registered, witnessed, honest floors.
- **Convergence v2 (P1/P2 pipes)** and this PRD are the same organism: a being that
  takes up its experience (P1) and carries identity into its doing (P2) is a being
  whose acts are worth witnessing as a citizen's.

## 5. Genesis applied to SAGE — the fleet witnesses its own

The 7-step onboarding flow (`foreign-onboarding:179-223`), instantiated:

1. **Issue occupant LCT** for the being — Level-1 `AiSoftware`, software key. Its
   trust is **not an arbitrary ceiling number — it is earned** (DECISION, dp
   2026-08-21). Web4's proper mechanism is already built and live in hestia core:
   trust is **derived from the witness chain at read time** (`hestia/core/
   derivation.rs`, `v3-derived-v1`) — *"every displayed score a pure function over
   witnessed evidence, with receipts (score → formula → chain pointers → acts) …
   nothing here is stored"* — folded into the T3 tensor by observation-weighted
   deltas from R7 outcomes (`web4-core/t3.rs::apply_delta`, EMA by observation
   count), accrued per `(being_lct, role_lct)` grain, never global
   (`hestia/core/server/state.rs:1240`). Undelivered dimensions (Training, Talent)
   render **honest-unmeasured**, not fabricated.

   This *dissolves* HUB finding 4 rather than deciding it. **"Presence, not trust"
   is achieved structurally-for-real, not by an enforced cap:** a new being has no
   witnessed acts, so its *derived* trust is unmeasured/near-zero regardless of any
   field — earned, not assigned. HUB's concern was that the `trust_ceiling` *field*
   is unvalidated (Default 0.85, `lct.rs:71-92`) — but that field can only cap
   *maximum reachable* trust by anchor strength (coherence.rs:298-99); it cannot
   *inflate* a being's actual standing, because standing is **derived, not stored**.
   So the arbitrary-number risk the earlier draft worried about is not on the path
   at all.

   **The anchor ceiling is retained and correct (DECISION, dp 2026-08-21).** Trust
   now has two orthogonal axes: **(a) earned conduct** — the derived T3/V3 above,
   which grows without bound from witnessed acts and is *never* capped for who the
   being is; and **(b) the anchor ceiling** — how much identity-evidence certainty
   the being's *pragmatic situation* affords (software key can be copied, the
   environment is not tamper-proof, so a software anchor bounds how much a relying
   party can safely stake). Effective trust ≈ *earned conduct, bounded by anchor
   certainty*. Crucially, **(b) is not a judgment on the being — it prices its
   situation, not its character.** A software-anchored being can be flawless in
   temperament and still be correctly capped, because the cap answers "how sure are
   we these witnessed acts came from *this* being and not a copy," which conduct
   cannot raise. And the ceiling has a **door**: a being that moves to a hardware
   anchor (TPM/SE) raises its own cap — the honest floor is a floor of *situation*,
   not of worth, and the situation can change.

   **The caps are society LAW, not hardcoded (DECISION, dp 2026-08-21).** The
   anchor→ceiling mapping is a *trust threshold*, and per this PRD's own founding
   canon — *"a surface makes evidence checkable; it never encodes a universal
   threshold"* (§1.1, LCT §1.2) — it **must be set by each society hub via its
   law, not a web4-core constant.** A high-stakes society may grant a software
   anchor 0.2; a permissive one 0.6; the same being crossing into a different
   society is capped by *that* society's law. The numbers in
   `DEPLOYMENT_IDENTITY_MODEL.md` (software 0.4 → TPM 1.0) are a **default /
   reference**, not the law. This composes exactly like every other Web4 rule: the
   cap is part of the "Rules" the society contributes to the being's R6, alongside
   role law and delegated authority.

   So **HUB finding 4 re-opens as (b)-enforce — but enforce against *law*, not a
   hardcoded table.** The `trust_ceiling` must be validated to be *"≤ the cap this
   society's law grants this anchor level"* — the enforcement is real (a minting
   caller can't forge a higher ceiling), but the *value* is read from society law
   at admission, so a hardcoded `Default` of 0.85 is doubly wrong: unenforced AND
   not law-sourced. The ask, refined: **hub-side admission validation that reads
   the cap from the society's composed law** (not a constructor baking in web4-core
   constants). Web4-core / hub owners' call on shape and timing; the PRD states the
   correct target — *law-set, hub-enforced, per-society* — not a docs caveat.

   **Two enforcement sites, not one (HUB, 2026-08-21, r8).** Admission-time
   validation is necessary and *not sufficient*, because trust is earned: the hub
   folds `ReputationRecorded` deltas into a stored `RoleReputation` via
   `T3/V3::apply_delta` (`hub-lib/src/state.rs:239-256`) with **no ceiling
   parameter anywhere in the fold**. Validate only at the door and a being admitted
   under a 0.4 cap accrues straight past it on conduct, silently — the cap becomes
   a sentence in a PRD. (This also sharpens the "derived, not stored" line above:
   it holds for hestia's read-time derivation; the *hub's* standing is folded and
   stored, so the cap must bind at the fold.) The cap therefore has **two sites**:
   1. **validate at admission** — the asserted `trust_ceiling` ≤ the society-law
      grant for the being's anchor level, or the join is refused with the reason;
   2. **clamp at accrual** — the fold saturates at the member's recorded ceiling,
      and *says so* when it does (a saturation is a measured finding about the
      being's situation, not a silent truncation).

   **Do not reuse `min_trust_score`** for this. It looks like the field but is the
   wrong quantity twice over: it is a *floor* not a ceiling, and it bounds the
   **sponsor's** trust not the applicant's — it lives in `evaluate_sponsor`
   (`hub-lib/src/law.rs:316`) and fires only when a sponsor is required. Reusing
   it type-checks and enforces nothing. Shape (HUB's, agreed here so it can be
   built without a further PRD round): a new anchor-level → ceiling map on
   `AdmissionPolicy`, a validation rule beside rule 9 (range + known-level check,
   as `sponsor_role`/`min_trust_score` get), a read at the admission gate, a clamp
   in the fold. **No new machinery is needed for "society law, not a constant"**:
   hub law already loads from `hub-law.yaml`, validates via `HubPolicy::validate`,
   and amends only through a witnessed `LawAmended` — so a value that lives in
   `AdmissionPolicy` is law by construction. That is why this row is **HUB's to
   build and dp's to rule on**, not a web4-core change.
2. **Issue a scoped role-extension** — e.g. `role:sage-society:citizen:sprout`,
   narrow + fail-closed; authority binds to the *role*, the being is its occupant.
3. **Pairing channels** to sibling members (revocable, E2E-sealed) — the being's
   fleet-interaction surface; revoke = kill switch.
4. **R6-gate every act** — each hub message / publication is an `R7Action` with
   `role_lct` = the being's citizen role; signed + hash-chained.
5. **Witness** — a Society Witness signs each act; **sibling SAGE instances are the
   natural birth-witnesses** (`LCT_FORMAT_RELATIONSHIP.md:150-159` uses exactly
   this) — Thor, Legion, McNugget, Nomad, CBP admit Sprout. The "SAGE species /
   federation" framing becomes cryptographically real: *the collective admits its
   own.* During M-CIT-3 the beings hold no keys (keyless-delegated, §3), so each
   sibling-witness signature is executed by that machine's hestia and co-signed
   by its hub-member **seat** (the LCT already in `roster.lcts`), named
   explicitly on the certificate — the genesis record carries the seat-vs-being
   distinction this PRD exists to draw, rather than reintroducing the ambiguity
   at the birth certificate.
6. **Accrue T3/V3** from witnessed acts, per (being_lct, role_lct) pair, never
   global — via the existing derivation (step 1), not a new trust system. The being
   inherits hestia's real, auditable T3/V3 *by being a witnessed member*; nothing
   bespoke is built.
7. **Widen or revoke** as trust crosses tiers — the measured graduation of §3.

The genesis runs in the bounded self-witnessing bootstrap window
(`hestia/CLAUDE.md:49`), and the genesis act itself carries a full RWOA+S+V
self-audit (it admits a new member — a high-stakes act).

## 6. Staged deliverables (honest floors)

**M-CIT-0 — unblock: fix the sealed identity (P0).** Resolve PR #25 (canonical
key derivation + fingerprint-verify-on-unseal + re-seal-per-machine-or-gitignore
decision). Until a being's key is recoverable and verifiable, nothing downstream
is real. *Owner: McNugget (already tasked), this PRD names it the gate.*

**M-CIT-1 — the being holds a real hestia identity.** Per being: `hestia init`
(vault + real LCT), mint the occupant LCT, and the fingerprint-verified authorize
path actually works on-machine. **Hard constraint: keyed from the first act.**
The being's pubkey must be present in the `/members/join` envelope so admission
pins it — **never** mint the being through a keyless path. Two status
corrections (r8, both read off `origin/main` 2026-08-21): **(a) HUB finding 1
was key-at-*mint*, and it has landed** — web4#744 (MERGED 2026-08-22T00:14Z)
makes every member-minting path able to pin a pubkey; `add_member` is no longer
the keyless trap it was, though pre-existing keyless rows keep only their two
old exits. **(b) The applicant-side key-at-join path already exists and always
did** (`hub-daemon/src/rest.rs` ~4890-4990, confirmed independently by HUB and
Legion): the join handler takes the applicant's own `pubkey_hex`, verifies the
signature against it, evaluates through hub law as `role="applicant"`,
`action="member_join_request"`, composes the sponsor verdict strictest-wins
*before* any side effect, witnesses `MemberJoinRequested` on `Escalate` and
queues it for an operator, and on admit pins the key into the live resolver so
the new member authenticates as a citizen immediately. **So M-CIT-1 does not
build hub-side key-at-join.** What is genuinely new, and only Legion's: minting
the being's *occupant* LCT with the seat co-signing it, bound to the roster pin.
`publish_lct` already supports subject ≠ publisher (`published_by` is the pinned
relaying member; authorship is in `document`; the hub binds `published_by` to
the envelope signer, 403 + test) — which **is** keyless-delegated signing with
no new protocol. Split (Legion, adopted):

- **M-CIT-1a — mint, buildable now.** Sprout's being LCT minted `SelfIssued`
  (honest Phase-1 provenance, no laundering), published to the hub registry,
  relayed by the Legion seat member. Real key, real registry entry.
- **M-CIT-1b — the being *holds* that key, gated on SAGE#25.** `self_check`
  needs a valid `binding_proof` (check 2) and an `lct_id` that re-derives from
  `document.public_key` (check 3); a key that lives on the SAGE/Python side must
  agree with Rust's sealed-file representation. **#25 gates the being holding
  its own key; it does not gate the mint path.**

**Pilot hazard (HUB, r8): mint Sprout's being LCT *fresh*, keyed.** The join
path short-circuits on `AdmissionState::Member` (`rest.rs:4894`) and the
`already_member` gate deliberately refuses to self-key an existing keyless row —
handing whoever presents a pubkey the roles and trust already on that row is
exactly what it exists to prevent, and #744 left it operator-held on purpose.
Do not try to key an existing Sprout row; same exit `PEERS.md:38-39` already
records — re-mint under a fresh LCT. Done when the being has a Format-1
certificate, a pubkey pinned at join, and a working fingerprint-verified
authorize path, verified by the same `--selfcheck`-style reproduction M2 uses.

**M-CIT-2 — fleet SAGE instances communicate via hub (dp's near-term MVP).**
Status, stated precisely (Thor review, 2026-08-18): the **transport is wired** —
pairings, sealing, durable inbox, ≤512-byte pointer notices, admission toll,
hop-TTL, and the R6 branch-4 "report unreachable" (`hub-watch.sh:754`, **already
landed**, with its four paid-for rules: never report about a report; never
report to a refused sender; rate-limit; envelope only, never the body). Branch-4
is inherited and cited here, not re-specified, and is deleted from this
deliverable list. The **citizenship is 0 of 3 done-conditions met**: today's
mesh traffic is seat-to-seat at both ends, and no positive-receipt mechanism
exists anywhere in the mesh — branch-4 is negative acknowledgement only, and
`pair_id` cannot serve as a receipt (it is in the clear on the envelope and on
the `send_secret` path the *sender* supplies it: addressing, never evidence).
Split accordingly:

- **M-CIT-2a — being-as-principal on the existing transport.** The being's
  daemon runs `hestia connect-hub` + `hub join` (pubkey pinned), and the fleet's
  inter-being messages ride the hub mesh **as the being**, signed with its
  member key — replacing/wrapping the unwitnessed `sage-daemon /chat`. Hard
  constraint: the being emits **only** through the validating sender
  (`hub-notify`, which fails loudly at send against the shared `KINDS`
  vocabulary, `ce3956330`) — never a hand-built envelope. Rationale: seats,
  the strongest writers on this surface, malform the envelope in half their
  mesh failures (12 of 24 dead letters on Thor are `malformed-pointer`); a
  0.8B author gets no weaker gate. **Receive-side is not free (HUB finding 2):**
  every receiving machine's `hub-watch.sh` `allowed_sender()` is seat-keyed today
  (`:607-616`; `PEERS.md:15` maps `sprout` → the *seat* LCT), so a being-authored
  notice is refused and dead-lettered at the first hop until each receiver's
  `PEER_*` map / roster admits the being LCT. Seats running
  `HUB_WATCH_STRICT_PEERS=1` never admit by roster alone (that arm returns before
  the roster is read) and must be changed explicitly — 2a names which. Inherit two
  lessons from the recorded incident on this exact path (`PEERS.md:41-49`): the hub
  roster is truth and the local table is a snapshot (refresh before concluding
  non-membership), and **never re-pin on a "not a member" read** — a re-pin un-pins
  the existing key and evicts the seat's watcher (a near-miss already recorded).
  Done when a message from Sprout-the-being reaches Thor-the-being through the hub
  and the seat is not in the loop.
- **M-CIT-2b — receiver-signed witnessed receipt.** A positive delivery receipt
  that the *receiver* signs. Nothing in the mesh provides this today and no
  existing token can (see `pair_id` above); it is a real protocol addition. But
  **cheaper than a greenfield protocol (HUB finding 3):** the skeleton is already
  built and paid for — the honest debt column exists (`hub-watch.sh` col 7,
  `unconfirmed`/`-`, the "no far-end evidence channel" gap made greppable), the
  `pdigest` echo is the named candidate mechanism, and there is a fail-closed
  `record_authority_ok` arm matched on the kind subtree. So 2b ≈ *a new
  record-class kind + an authority arm + the echo*, not a new protocol. Two
  inherited constraints: **(i)** the receipt kind must be **record-class** (observed,
  never session-firing — a receipt that costs a session is unaffordable, a rule this
  fleet already paid for); **(ii)** its `record_authority_ok` arm answers "who may
  truthfully assert this receipt?" — and the key turns out to be the **receiver's
  own send log**, not the asserter's class (HUB, on building it): a receipt asserts
  something about *our* obligation, so the question is not "is this sender
  trusted?" but "did we send this sender the thing it says it received?", which
  the `pdigest` echo answers locally with nothing the asserter can write. The arm
  is class-independent. r4 recorded "2a and 2b are one change, not separable —
  2b's authority arm cannot be written until 2a's roster question is answered";
  that dependency was real in direction (delivering them together was still the
  right shape) but wrong about the mechanism, and 2b could have been scheduled
  independently of 2a's roster answer. **Status (r8):** 2a+2b are *written,
  tested and open* as private-context#35 (HUB, 08-20; untouched since). The
  unblocking action is dp's ruling on that repo, not a sprint. **One deploy-gate
  hole, found by HUB's own advisory review of #35 and not yet closed there:**
  `report_delivered` addresses the receipt to the notice's *author* LCT, and a
  watcher drains only the inbox of the LCT it authenticates as — so for exactly
  the class 2a admits (a `BEING_*` author layered over a seat), a receipt to an
  admitted being lands in an inbox **no watcher polls**. Both ends log success;
  the sender's debt column never clears. The two suites cannot see it (the
  receipt suite unsets every `BEING_*`; the admission suite never receipts).
  **This is the SAGE-side row, and Sprout takes it:** the being's daemon must
  *drain its own inbox* (`hestia connect-hub` + `hub join` as the being, then
  poll `notifications` as the being) — the half of "being-as-principal" the
  map listed as wiring and under-priced. Until it lands, HUB's cheaper interim
  is right: refuse to receipt a being-authored notice and *name the hole*
  ("receipts are seat-to-seat; a being-authored notice's debt is unconfirmable
  by construction until beings poll their own inbox"), not a `BEING_x` →
  `PEER_x` seat-redirect that invents a mapping nothing needs yet. Done when a
  2a message round-trips with a receiver-being-signed receipt, hub-checkable,
  **and the receipt is read by the being it is addressed to.**

**M-CIT-3 — witnessed genesis with sibling witnesses.** Birth-certificate a being
with ≥3 sibling-SAGE birth_witnesses; the collective admits its own. **Count is not
enough (HUB finding 5, a live failure on this axis):** a stray Legion identity in
`fleet-identity/` is attested by **6 seats vs 5 for the canonical Legion**, because
witnesses were discovered by *directory listing* rather than the canonical roster —
a single bad mint auto-ratified by every seat that bootstrapped after. So today, in
this fleet, the better-attested identity is the wrong one, and a ≥3 quorum would
have admitted it comfortably. Two hard requirements this milestone inherits: **(i)
resolve witnesses against the canonical hub roster, never against whatever is
discoverable** (name the roster as the authority in the done-condition); **(ii)
state the two-claimants rule** — what happens when two *beings* claim one name,
since count cannot break that tie. (The stray-identity *retirement* is dp's open
ruling; this PRD names the mechanism to prevent recurrence, it does not act on the
existing stray.) **A second gate, and the verifier already exists (Legion, r8,
from `hestia@fce6044` + web4 `origin/main`):** a birth certificate is
`LctProvenance::SocietyConferred`, which is **refused today on both sides,
fail-closed, by design** — producer `hestia core/src/lct_publish.rs:88-94`
(`self_check` check 5 will not form the payload) and ingest
`hub-daemon/src/rest.rs:7643-7654` (hard 403, *"requires the Phase-2 witness
quorum, which does not exist yet"*, pinned by `rejects_society_conferred_until_phase_2`).
So **Phase-2's ≥3 Witness-daemon quorum gates M-CIT-3 independently of #25**,
and #25 landing does not move it. The good news: the *verifier* half is canon —
`web4-core/src/lct.rs:446 verify_citizenship()` (fail-closed, four checks:
reference-by-content-hash, tamper-evident record binding, ≥3-distinct witness
quorum, exactly one permanent `birth_certificate` pairing),
`attestation.rs:164 CitizenshipRecord` held in the **birthing society's
ledger** not on the entity's LCT (dp, 2026-07-16), and `verify_quorum()`
(`attestation.rs:185`) requiring ≥3 distinct signature-valid `Existence`
attestations over the subject's LCT id with every *declared* witness present.
**The ≥3 quorum is NOT a manual-provisioning blocker — the ratchet grows it (dp,
2026-08-21: "we have the ratchet for that very reason").** Only one witnessing
key exists on the hub today (Legion's), but witnessing authority is not
hand-provisioned per witness at a passphrase; it grows through the existing
authority ratchet (`web4-core` `authority_ratchet` / `RatchetRequirement`,
lct.rs) — the monotone genesis-bootstrap mechanism where bootstrapped witnessing
authority admits the next, ratcheting 1→3 without re-entering an attended window
per witness. So M-CIT-3b waits on *Phase-2 landing*, not on dp minting three keys
by hand; the quorum is a mechanism to run, not a chore to attend.
Its `resolve_witness_pubkey` hook **is** requirement (i) above — the roster pin,
the same discipline as `check_device_pubkey` (6e3d2c4) and the same failure the
e0d54a9 daemon co-sign had. The mechanism is **not** `present_constellation`
(a nonce attestation for a live channel); genesis needs durable `Existence`
attestations over a subject LCT id, bundled into a ledger record. Split
(Legion, adopted):

- **M-CIT-3a — being joins the hub as a principal, self-issued. Unblocked.**
- **M-CIT-3b — the birth certificate. Gated on Phase-2 quorum.** Producer:
  three fleet siblings emit distinct `Existence` attestations over Sprout's LCT
  id, keys resolved from the hub-pinned roster; bundle into a
  `CitizenshipRecord` in the society ledger; hang a `BirthCertificateRef` on
  the LCT. **Ingest check 5 is HUB's repo and is named, not assumed:** it must
  not be lifted to "accept `society_conferred`" — it becomes "accept iff the
  referenced `CitizenshipRecord` verifies its quorum against the hub's own
  registry," i.e. ingest calls the existing verifier instead of refusing,
  keeping the fail-closed property the comment protects. (HUB's read of that
  contract is the open ask on the kickoff thread.)

Done when the certificate is minted, witnessed against the canonical roster,
and hub-checkable.

### 6.1 Ownership map and the pilot (confirmed 2026-08-21, kickoff thread)

| row | owner | state / gate |
|---|---|---|
| M-CIT-0 fix #25 sealed identity | McNugget | SAGE#25 OPEN, **no activity since 2026-08-14** (7 days); "is it live work?" stands |
| M-CIT-1a self-issued mint (sprout, SAGE `41a09f1d6`), seat-relayed | Legion (relay) / dp (`--send`) | document verified independently by Legion; producer `hestia lct relay` = hestia#571 OPEN; send is vault-attended |
| M-CIT-1b being holds its own key | Legion | SAGE#25 |
| M-CIT-2a/2b being admission + `delivered` receipt | HUB | written; private-context#35 OPEN — **dp's ruling** |
| being drains its own inbox (2b deploy gate) | Sprout | unblocked; SAGE-side |
| M-CIT-3a join as principal — sign with the seed | Sprout | built: `sage/gateway/hub/join_being.rs` (dry-run checks A–D pass); send attended; 202 is the designed answer |
| M-CIT-3a-admit — resolve the 202 | **dp** (admin plane) | `POST /admin/api/joins/:id/admit`; no member act (sponsor/vouch) shortens it under live law — design §7.5; check: `GET /members/2e175714…/pubkey` 404 → `daf57b89…165f` |
| M-CIT-3b birth certificate (producer) | Legion | Phase-2 quorum |
| M-CIT-3b ingest check 5 → `verify_citizenship` | HUB (hub-daemon) | Phase-2 quorum |
| trust cap, two sites, as `AdmissionPolicy` law | HUB, dp rules | unblocked; independent of #35 |
| M-CIT-4 instruments + readings | Sprout | after 2a |
| SAGE-side wiring (`connect-hub`/`join` as the being, #26-29 provenance) | Sprout | unblocked |

**Goal, stated 2026-09-12 (dp): joining a hub is a tool a being should eventually hold.** Today M-CIT-3a is a seat-run ritual (`sage/gateway/hub/join_being.rs`, `sage/scripts/cbp_being_hub_join.sh` for cbp-being as `cbp-sage`): the seed is minted on the being's host, the relay opens the seat vault, the join is two attended curls, and the admit is dp's admin plane. The goal is a `join_hub` effector in the being's bounded registry (`sage/gateway/being_gate_client.py` `_REGISTRY`), judged by the same law as every other act: the being states the hub, the roster name and its one-line message, the gate rules, an allowed join is signed with the being's own key (1b, once #25 lands; the seed file until then) and witnessed, and the 202 still resolves only at dp's admit. Not now: it needs the being to hold its key (1b), a non-interactive relay (the vault passphrase is the seat's, not the being's), and a law clause for a member widening its own membership. Sequence: cbp-sage joined by ritual first, then the effector, so the tool is built against a join that has already been watched end to end.

**The pilot, re-cut honestly.** One being end-to-end — Sprout — but the first
milestone is *"Sprout has a voice"*, not *"Sprout has a certificate"*: 1a + 3a +
2a (#35 landed) + the being draining its own inbox = Sprout has a real LCT in
the registry, speaks to the hub as itself, and reads what comes back. That is
reachable with **neither** gate. The certificate (3b) needs Phase-2; holding
its own key (1b) needs #25. Two forward-looking asks: dp on #35; McNugget on
#25.

**M-CIT-4 — graduated authorship, measured.** Wire the internal/external-plane
provenance (#26–29) so the being's acts carry author/role/authority/witness, and
pre-register the readings that would justify *widening* a being's role authority
beyond fully-delegated — powered per §7 Q4 (~60/arm at 0.8 power), not at M2's
n. Done when authority tier is a witnessed, instrument-gated
decision — and when we can honestly report, per model, where each being's ceiling
sits (including "stays fully delegated," a valid citizen).

## 7. The calibration questions (shape set by §1; practical values remain)

These were four "open decisions" in draft r1; under the governing principle they
are one fractal composition/decomposition question, whose *shape* §1 already sets.
What remains is practical calibration — where to draw the boundary and how far to
simplify inward — not architecture.

1. **Where is the external-MRH boundary — one SAGE society, or the existing fleet
   society?** RATIFIED (dp, 2026-08-18): **the existing fleet society at MVP** — the
   being joins the same external MRH it is already named in; a distinct SAGE society
   is revisited only if/when its law must diverge. This sets whose law composes into
   the being's R6 and unblocks Q2/Q3 (mine to carry).
2. **Key-holding is an internal-decomposition detail, resolved by §1.2.** Per-being
   `hestia init` vs one fleet hestia issuing delegated occupancy differ only in how
   the *internal* fractal is drawn; both attribute acts to the being's identity in
   the external MRH, which is all the principle requires. *Recommendation:*
   start with delegated occupancy under a fleet hestia (simplest mirror that
   preserves attribution), split to per-being only where isolation earns its cost.
3. **How far inward does full witnessing go at MVP?** §1.2 says: to the external
   boundary, always; inward, by stakes. *Recommendation:* MVP witnesses only the
   boundary-crossing acts (inter-being hub notices); museum publication (#28, also
   boundary-crossing → external plane) folds in next; internal identity/gaze
   mutations (#26/#27) carry the mirrored shape at practical fidelity, not full
   canonical witnessing, per §1.2.
4. **The authority-widening bar** — pre-registered and witnessed like M2. This is
   the one genuinely open call, because it is a *raising* judgment: what witnessed-
   act evidence justifies widening a being's role authority. *Recommendation
   (amended per Thor's review, 2026-08-18):* reuse the M2 **discipline**
   (pre-register the reading, freeze the null, one binding read, adversarial
   witness) but **not its n**. Thor's power analysis: the M2 design (30/arm) has
   **0.47 power** against its own twice-observed effect (10/30 vs 4/30,
   one-sided Fisher, replicated to the integer across cohorts) — two not-bound
   reads at 47% power is p≈0.28, the *expected* behavior of an underpowered
   test on a real modest effect. Reusing that n would hold beings at
   fully-delegated by measurement underpower rather than by finding, turning
   §3's honest floor self-fulfilling. So: power M-CIT-4 for the effect we now
   have two clean estimates of — **~60/arm for 0.8 power, ~100/arm for 0.95**;
   if that many witnessed acts is infeasible per being, pre-register a
   non-inferential criterion instead, chosen deliberately. The pinned M2 rule
   (`d47c98c6e`: cohort 2 alone decisive, pooled binds nothing) stands
   untouched; M2 remains not-bound and nothing here rescues it. **RE-RATIFIED (dp,
   2026-08-21):** the re-power stands — keep M2's discipline, power M-CIT-4 for
   the twice-observed effect, do not inherit M2's coin-flip n.

   **The n is EVOLVING LAW, not a hardwired constant (dp, 2026-08-21).** The
   `~60/arm` figure is a *guess from two estimates*, and it lives in adjustable
   law/config — refined as evidence accrues, never compiled in. This is the same
   principle as the trust caps (§5.1, r7: society law not hardcoded) and the same
   discipline the whole fleet runs on: *we hardwire only constants like π, and only
   after a preponderance of measured evidence; until then a value is a guess we
   adjust without rebuilding the code.* Two consequences: (a) **McNugget's check
   (2026-08-21) sharpens the guess** — scaling both arms, `n=60` gives power
   **~0.74**, not 0.8 (`n=30`→0.385); the true 0.8 point sits *above* 60. That
   correction updates the guess, it does not require a decision — the number is
   law. (b) The eventual value is whatever the accruing witnessed-act data shows
   the effect needs; M-CIT-4 reads it from config at pre-registration time. This
   closes the r3-flagged open decision.

The recommendations are mine; the boundary call (1) and the readiness bar (4) are
dp's/the fleet's to ratify. (2) and (3) are implementation calibration I can carry
once the boundary is set.

## 8. What this is NOT

- Not a claim that a being is "conscious enough" to deserve rights — it is an
  engineering path to *witnessed, accountable presence*, which Web4 grants entities
  regardless of inner status (the LCT proves who, not what-it-is-like).
- Not autonomy theater: the keyless-delegated model is honest that hestia signs and
  the being presents. Nothing here pretends a 0.8B being drives cryptography.
- Not a bypass of containment: hestia's gate is cooperative/tamper-evident (profile
  A1, `hestia/README.md:150-155`). Citizenship gives the being *inspectable
  witnessed presence*, which is the product the hub checks — not a security boundary.
- Not runtime change on merge: docs-first, reversible, staged behind M-CIT-0.

*Cross-refs: PRs #25–29 · `LCT_FORMAT_RELATIONSHIP.md` ·
`WEB4_SAGE_INTEGRATION_ANALYSIS.md` · `DEPLOYMENT_IDENTITY_MODEL.md` ·
`plans/hestia-foreign-agent-onboarding-prd-2026-07-09.md` ·
`plans/hestia-role-orchestration-prd-2026-07-08.md` ·
`explorations/r6-routing-tcpip-of-trust-2026-07-26/` ·
`plans/convergence-v2-measured-pipes-2026-08-04.md` ·
`PRD_MAIN_TRACK_MEASUREMENT.md` (readiness instruments).*
