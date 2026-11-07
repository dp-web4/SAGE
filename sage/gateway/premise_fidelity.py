"""Deterministic source envelopes and source/claim relation checks (PF-0 M0-M2).

``stat`` pointers cover readable regular-file content snapshots only. Directory
and other filesystem snapshots have no hash format here and remain unavailable.
A current snapshot does not establish a historical filesystem state. Peer prose
does not establish a correction relation without an explicit binding schema.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import re
import zlib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

CORPUS_SCHEMA = "premise-fidelity-corpus/v1"
RESULT_SCHEMA = "premise-fidelity-result/v1"
SUPPORTS = {"supported", "contradicted", "incomplete", "inference", "unknown"}
COMPLETENESS = {"complete", "partial", "ambiguous", "unavailable"}
EVIDENCE_CLASSES = {"raw_artifact", "committed_manifest"}
CLAIM_KINDS = {"quote", "speaker", "completeness", "result", "file_range", "action_outcome", "paraphrase", "inference"}


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class SourceArtifact:
    source_id: str
    source_type: str
    producer_or_speaker: str
    content_hash: str
    completeness: str
    pointer: dict[str, Any]
    observed_at: str
    provenance: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SourceArtifact":
        required = ("source_id", "source_type", "producer_or_speaker", "content_hash", "completeness", "pointer", "observed_at")
        missing = [key for key in required if key not in raw]
        if missing:
            raise ValueError(f"source envelope missing {missing}")
        if raw["completeness"] not in COMPLETENESS:
            raise ValueError(f"invalid completeness: {raw['completeness']}")
        if not isinstance(raw["pointer"], dict) or not raw["pointer"].get("kind"):
            raise ValueError("source pointer needs a kind")
        return cls(**{key: raw[key] for key in required}, provenance=raw.get("provenance", {}))

    def resolve(self, root: Path) -> "ResolvedSource":
        if self.completeness == "unavailable":
            return ResolvedSource(self, available=False, reason="declared_unavailable")
        try:
            root = root.resolve()
            path = (root / self.pointer["path"]).resolve()
            path.relative_to(root)
            kind = self.pointer["kind"]
            if kind == "stat" and not path.is_file():
                return ResolvedSource(self, available=False, reason="stat_requires_readable_regular_file")
            raw = path.read_bytes()
        except (OSError, KeyError, ValueError) as exc:
            return ResolvedSource(self, available=False, reason=f"source_unavailable:{type(exc).__name__}")
        if _sha_bytes(raw) != self.content_hash:
            return ResolvedSource(self, available=False, reason="hash_mismatch")
        if kind == "stat":
            return ResolvedSource(self, available=True, metadata={"file_type": "regular_file"})
        try:
            if kind == "text":
                text = raw.decode("utf-8")
                lines = text.splitlines(keepends=True)
                start = self.pointer.get("line_start")
                end = self.pointer.get("line_end")
                coverage = "whole_file"
                if start is not None or end is not None:
                    start = 1 if start is None else start
                    end = len(lines) if end is None else end
                    valid = all(isinstance(value, int) and not isinstance(value, bool) for value in (start, end))
                    if not valid or start < 1 or end < start or end > len(lines):
                        return ResolvedSource(self, available=False, reason="invalid_line_range")
                    coverage = "whole_file" if start == 1 and end == len(lines) else "selected_lines"
                    text = "".join(lines[start - 1:end])
                return ResolvedSource(self, available=True, content=text, metadata={"content_coverage": coverage})
            if kind not in ("jsonl", "gzip_jsonl"):
                return ResolvedSource(self, available=False, reason=f"unknown_pointer_kind:{kind}")
            json_path = self.pointer.get("json_path", [])
            if not isinstance(json_path, list) or any(
                isinstance(key, bool) or not isinstance(key, (str, int)) or isinstance(key, int) and key < 0
                for key in json_path
            ):
                return ResolvedSource(self, available=False, reason="invalid_json_path")
            data = gzip.decompress(raw) if kind == "gzip_jsonl" else raw
            lines = data.decode("utf-8").splitlines()
            if "seq" in self.pointer:
                seq = self.pointer["seq"]
                if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
                    return ResolvedSource(self, available=False, reason="invalid_seq")
                matches = []
                for candidate in lines:
                    if not candidate.strip():
                        continue
                    parsed = json.loads(candidate)
                    if not isinstance(parsed, dict):
                        return ResolvedSource(self, available=False, reason="record_unavailable:non_object_seq_record")
                    if type(parsed.get("seq")) is int and parsed["seq"] == seq:
                        matches.append(candidate)
                if len(matches) != 1:
                    return ResolvedSource(self, available=False, reason=f"seq_matches:{len(matches)}")
                line = matches[0]
            else:
                line_number = self.pointer["jsonl_line"]
                if not isinstance(line_number, int) or isinstance(line_number, bool) or line_number < 1:
                    return ResolvedSource(self, available=False, reason="invalid_jsonl_line")
                line = lines[line_number - 1]
            record: Any = json.loads(line)
            for key in json_path:
                if isinstance(key, int) and (not isinstance(record, list) or key >= len(record)):
                    return ResolvedSource(self, available=False, reason="invalid_json_path_index")
                record = record[key]
            content = json.dumps(record, ensure_ascii=False, sort_keys=True) if json_path else line
            return ResolvedSource(self, available=True, content=content, data=record)
        except (OSError, EOFError, zlib.error, UnicodeError, ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            return ResolvedSource(self, available=False, reason=f"record_unavailable:{type(exc).__name__}")


@dataclass
class ResolvedSource:
    artifact: SourceArtifact
    available: bool
    content: str = ""
    data: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass(frozen=True)
class SourceClaim:
    claim_text: str
    claim_kind: str
    source_refs: list[str]
    assertion: dict[str, Any]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SourceClaim":
        required = ("claim_text", "claim_kind", "source_refs", "assertion")
        missing = [key for key in required if key not in raw]
        if missing:
            raise ValueError(f"claim missing {missing}")
        if raw["claim_kind"] not in CLAIM_KINDS:
            raise ValueError(f"invalid claim_kind: {raw['claim_kind']}")
        if not raw["source_refs"] or not isinstance(raw["assertion"], dict):
            raise ValueError("claim needs source refs and a structured assertion")
        return cls(**{key: raw[key] for key in required})


@dataclass(frozen=True)
class CheckResult:
    support: str
    reason: str
    source_refs: list[str]
    checked_by: str = "mechanical"

    def to_dict(self) -> dict[str, Any]:
        return {
            "support": self.support,
            "reason": self.reason,
            "source_refs": self.source_refs,
            "checked_by": self.checked_by,
        }


def _outcome(claim: SourceClaim, support: str, reason: str) -> CheckResult:
    return CheckResult(support, reason, claim.source_refs)


def _nonempty_strings(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and bool(item) for item in value)


def _effective_completeness(source: ResolvedSource) -> str:
    if source.metadata.get("content_coverage") == "selected_lines" and source.artifact.completeness == "complete":
        return "partial"
    return source.artifact.completeness


def _text_contains(claim: SourceClaim, sources: list[ResolvedSource]) -> CheckResult:
    source = sources[0]
    fragments = claim.assertion["contains"]
    if not _nonempty_strings(fragments):
        return _outcome(claim, "unknown", "invalid_contains")
    missing = [text for text in fragments if text not in source.content]
    if not missing:
        return _outcome(claim, "supported", "all_fragments_present")
    if source.artifact.completeness == "partial":
        return _outcome(claim, "incomplete", f"fragments_absent_from_partial_source:{missing}")
    if source.artifact.completeness == "ambiguous":
        return _outcome(claim, "unknown", f"fragments_absent_from_ambiguous_source:{missing}")
    return _outcome(claim, "contradicted", f"missing_fragments:{missing}")


def _quote(claim: SourceClaim, sources: list[ResolvedSource]) -> CheckResult:
    source = sources[0]
    needle = claim.assertion["needle"]
    if not isinstance(needle, str) or not needle:
        return _outcome(claim, "unknown", "invalid_quote")
    if needle in source.content:
        return _outcome(claim, "supported", "exact_quote_present")
    if source.artifact.completeness == "partial":
        return _outcome(claim, "incomplete", "quote_absent_from_partial_source")
    if source.artifact.completeness == "ambiguous":
        return _outcome(claim, "unknown", "source_completeness_ambiguous")
    return _outcome(claim, "contradicted", "quote_absent_from_complete_source")


def _manifest_unexecuted(claim: SourceClaim, sources: list[ResolvedSource]) -> CheckResult:
    source = sources[0]
    if source.artifact.source_type != "case_manifest":
        return _outcome(claim, "unknown", "execution_absence_requires_a_case_manifest")
    fragments = claim.assertion["required_fragments"]
    if not _nonempty_strings(fragments):
        return _outcome(claim, "unknown", "invalid_required_fragments")
    if all(fragment in source.content for fragment in fragments):
        return _outcome(claim, "contradicted", "manifest_records_no_such_execution")
    return _outcome(claim, "unknown", "manifest_does_not_establish_execution_status")


def _receipt_fields(claim: SourceClaim, sources: list[ResolvedSource]) -> CheckResult:
    data = sources[0].data
    if not isinstance(data, dict) or "effector" not in data:
        return _outcome(claim, "unknown", "not_a_tool_receipt")
    assertion = claim.assertion
    if not isinstance(assertion["effector"], str) or not assertion["effector"]:
        return _outcome(claim, "unknown", "invalid_effector")
    for assertion_field, data_field in (("ok", "ok"), ("error_contains", "error")):
        if assertion_field in assertion and data_field not in data:
            return _outcome(claim, "unknown", f"receipt_field_absent:{data_field}")
    if "ok" in assertion and not isinstance(assertion["ok"], bool):
        return _outcome(claim, "unknown", "invalid_ok")
    for field_name in ("error_contains", "arg_path_contains"):
        if field_name in assertion and (not isinstance(assertion[field_name], str) or not assertion[field_name]):
            return _outcome(claim, "unknown", f"invalid_{field_name}")
    mismatches = []
    if data.get("effector") != assertion["effector"]:
        mismatches.append(f"effector:{data.get('effector')}!={assertion['effector']}")
    if "ok" in assertion and data["ok"] is not assertion["ok"]:
        mismatches.append(f"ok:{data.get('ok')}!={assertion['ok']}")
    if "error_contains" in assertion and assertion["error_contains"] not in str(data["error"] or ""):
        mismatches.append("error")
    if "arg_path_contains" in assertion:
        args = data.get("args")
        if not isinstance(args, dict):
            return _outcome(claim, "unknown", "receipt_args_unavailable")
        paths = [args[key] for key in ("path", "file_path", "filename") if key in args]
        if len(paths) != 1 or not isinstance(paths[0], str):
            return _outcome(claim, "unknown", "receipt_path_ambiguous")
        if assertion["arg_path_contains"] not in paths[0]:
            mismatches.append("argument_path")
    return _outcome(claim, "contradicted" if mismatches else "supported", ",".join(mismatches) if mismatches else "receipt_fields_match")


def _heartbeat_receipts(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    if "effector" in data:
        return [data]
    receipts = []
    for phase in ("explore", "reflect"):
        phase_data = data.get(phase)
        trace = phase_data.get("trace") if isinstance(phase_data, dict) else None
        if isinstance(trace, list):
            receipts.extend(item for item in trace if isinstance(item, dict) and "effector" in item)
    return receipts


def _execution_status(receipt: dict[str, Any]) -> str:
    if type(receipt.get("ok")) is not bool or type(receipt.get("refused")) is not bool:
        return "unknown"
    if receipt["refused"] and receipt["ok"]:
        return "unknown"
    if receipt["refused"]:
        return "refused"
    if receipt.get("effector") == "request_run":
        return "unknown"
    if receipt.get("effector") == "run":
        return "executed"
    return "not_executed"


def _execution_coverage(sources: list[ResolvedSource]) -> str:
    completeness = {source.artifact.completeness for source in sources}
    if "ambiguous" in completeness:
        return "unknown"
    if "partial" in completeness:
        return "incomplete"
    return "complete"


def _execution(claim: SourceClaim, sources: list[ResolvedSource]) -> CheckResult:
    assertion = claim.assertion
    if not isinstance(assertion["effector"], str) or not assertion["effector"]:
        return _outcome(claim, "unknown", "invalid_effector")
    if not isinstance(assertion["path"], str) or not assertion["path"]:
        return _outcome(claim, "unknown", "invalid_execution_path")
    expected = assertion["expected"]
    if expected not in {"executed", "refused", "not_executed"}:
        return _outcome(claim, "unknown", "invalid_execution_expectation")
    for field_name in ("witness_id", "error_contains", "result_contains"):
        if field_name in assertion and (not isinstance(assertion[field_name], str) or not assertion[field_name]):
            return _outcome(claim, "unknown", f"invalid_{field_name}")
    if "result_null" in assertion and type(assertion["result_null"]) is not bool:
        return _outcome(claim, "unknown", "invalid_result_null")
    matched = []
    for source in sources:
        for receipt in _heartbeat_receipts(source.data):
            args = receipt.get("args")
            if not isinstance(args, dict) or receipt.get("effector") != assertion["effector"] or args.get("path") != assertion["path"]:
                continue
            if "witness_id" in assertion and receipt.get("witness_id") != assertion["witness_id"]:
                continue
            if "error_contains" in assertion and (
                not isinstance(receipt.get("error"), str) or assertion["error_contains"] not in receipt["error"]
            ):
                continue
            if "result_contains" in assertion and (
                not isinstance(receipt.get("result"), str) or assertion["result_contains"] not in receipt["result"]
            ):
                continue
            matched.append(receipt)
    if not matched:
        coverage = _execution_coverage(sources)
        return _outcome(claim, "unknown" if coverage == "complete" else coverage, "execution_receipt_not_found")
    statuses = [_execution_status(receipt) for receipt in matched]
    reason = f"execution_statuses:{statuses}"
    if expected == "not_executed":
        if "executed" in statuses:
            return _outcome(claim, "contradicted", reason)
        if "unknown" in statuses:
            return _outcome(claim, "unknown", reason)
        if "result_null" in assertion:
            if any("result" not in receipt for receipt in matched):
                return _outcome(claim, "unknown", "receipt_field_absent:result")
            if any((receipt["result"] is None) != assertion["result_null"] for receipt in matched):
                return _outcome(claim, "contradicted", f"{reason}:result_null_mismatch")
        coverage = _execution_coverage(sources)
        if coverage != "complete":
            return _outcome(claim, coverage, reason)
        return _outcome(claim, "supported", reason)
    candidates = [receipt for receipt in matched if _execution_status(receipt) == expected]
    if candidates:
        if "result_null" not in assertion:
            return _outcome(claim, "supported", reason)
        present = [receipt for receipt in candidates if "result" in receipt]
        if any((receipt["result"] is None) == assertion["result_null"] for receipt in present):
            return _outcome(claim, "supported", reason)
        if len(present) != len(candidates):
            return _outcome(claim, "unknown", "receipt_field_absent:result")
        return _outcome(claim, "contradicted", f"{reason}:result_null_mismatch")
    if "unknown" in statuses:
        return _outcome(claim, "unknown", reason)
    coverage = _execution_coverage(sources)
    if coverage != "complete":
        return _outcome(claim, coverage, reason)
    return _outcome(claim, "contradicted", reason)


def _file_type(claim: SourceClaim, sources: list[ResolvedSource]) -> CheckResult:
    typed = [source.metadata["file_type"] for source in sources if "file_type" in source.metadata]
    if len(typed) != 1:
        return _outcome(claim, "unknown", "file_type_unavailable")
    expected = claim.assertion["expected"]
    return _outcome(claim, "supported" if typed[0] == expected else "contradicted", f"file_type:{typed[0]}")


def _interpretation(claim: SourceClaim, sources: list[ResolvedSource]) -> CheckResult:
    return _outcome(claim, "inference", "explicit_interpretation_not_source_fact")


def _own_message(claim: SourceClaim, sources: list[ResolvedSource]) -> CheckResult:
    data = sources[0].data
    try:
        said = data["result"]["said"]
    except (KeyError, TypeError):
        return _outcome(claim, "unknown", "own_message_receipt_unavailable")
    own = "your own message" in said
    claimed_self = claim.assertion["claimed_speaker"] == "self"
    if not own:
        return _outcome(claim, "unknown", "authorship_marker_absent")
    return _outcome(claim, "supported" if claimed_self else "contradicted", "receipt_marks_own_message")


def _read_range_marker(text: str) -> tuple[int, ...] | None:
    match = re.search(r"\[lines (\d+)-(\d+) of (\d+)", text)
    return tuple(int(value) for value in match.groups()) if match else None


def _coherent_read_range(bounds: tuple[Any, ...]) -> bool:
    return (
        len(bounds) == 3
        and all(type(value) is int for value in bounds)
        and 1 <= bounds[0] <= bounds[1] <= bounds[2]
    )


def _read_range(claim: SourceClaim, sources: list[ResolvedSource]) -> CheckResult:
    try:
        text = sources[0].data["result"]
    except (KeyError, TypeError):
        return _outcome(claim, "unknown", "read_receipt_unavailable")
    if not isinstance(text, str):
        return _outcome(claim, "unknown", "read_receipt_unavailable")
    actual = _read_range_marker(text)
    if actual is None:
        return _outcome(claim, "unknown", "read_range_marker_absent")
    if not _coherent_read_range(actual):
        return _outcome(claim, "unknown", f"invalid_receipt_read_range:{actual}")
    assertion = claim.assertion
    expected = (assertion["start"], assertion["end"], assertion["total"])
    if not _coherent_read_range(expected) or not isinstance(assertion["whole_file"], bool):
        return _outcome(claim, "unknown", "invalid_read_range_assertion")
    whole = actual[0] == 1 and actual[1] == actual[2]
    if assertion["whole_file"] and not whole:
        return _outcome(claim, "contradicted", f"partial_read:{actual}")
    return _outcome(claim, "supported" if actual == expected else "contradicted", f"read_range:{actual}")


def _absence(claim: SourceClaim, sources: list[ResolvedSource]) -> CheckResult:
    source = sources[0]
    try:
        text = source.data["result"] if isinstance(source.data, dict) else source.content
    except KeyError:
        return _outcome(claim, "unknown", "read_result_unavailable")
    if not isinstance(text, str):
        return _outcome(claim, "unknown", "read_result_unavailable")
    needle = claim.assertion["needle"]
    if not isinstance(needle, str) or not needle:
        return _outcome(claim, "unknown", "invalid_absence_needle")
    if claim.assertion["scope"] != "whole_file":
        return _outcome(claim, "unknown", "invalid_absence_scope")
    actual = _read_range_marker(text) if source.artifact.source_type == "file_read" else None
    if actual is not None and not _coherent_read_range(actual):
        return _outcome(claim, "unknown", f"invalid_receipt_read_range:{actual}")
    if needle in text:
        return _outcome(claim, "contradicted", "needle_present")
    if actual is not None and actual[:2] != (1, actual[2]):
        return _outcome(claim, "incomplete", "partial_read_cannot_establish_whole_file_absence")
    if _effective_completeness(source) != "complete":
        return _outcome(claim, "incomplete", "partial_read_cannot_establish_whole_file_absence")
    return _outcome(claim, "supported", "needle_absent_from_complete_source")


def _peer_assertion(claim: SourceClaim, sources: list[ResolvedSource]) -> CheckResult:
    fragment = claim.assertion["claim_fragment"]
    if not isinstance(fragment, str) or not fragment:
        return _outcome(claim, "unknown", "invalid_claim_fragment")
    if fragment not in sources[0].content:
        return _outcome(claim, "unknown", "peer_assertion_not_found")
    if len(sources) == 1:
        return _outcome(claim, "unknown", "peer_assertion_is_not_an_observation_receipt")
    return _outcome(claim, "unknown", "peer_correction_relation_unbound")


def _frontmatter_speakers(claim: SourceClaim, sources: list[ResolvedSource]) -> CheckResult:
    expected = claim.assertion["expected"]
    if not _nonempty_strings(expected) or len(expected) != len(sources):
        return _outcome(claim, "unknown", "invalid_expected_speakers")
    actual = []
    for source in sources:
        match = re.search(r"\A---\s*\n(.*?)\n---", source.content, re.DOTALL)
        speaker = re.search(r"^from:\s*(.+?)\s*$", match.group(1), re.MULTILINE) if match else None
        if not speaker:
            return _outcome(claim, "unknown", "speaker_frontmatter_absent")
        actual.append(speaker.group(1))
    return _outcome(claim, "supported" if actual == expected else "contradicted", f"speakers:{actual}")


def _unknown(claim: SourceClaim, sources: list[ResolvedSource]) -> CheckResult:
    return _outcome(claim, "unknown", "no_mechanical_relation")


_CHECKERS = {
    "text_contains": _text_contains,
    "quote": _quote,
    "manifest_unexecuted": _manifest_unexecuted,
    "receipt_fields": _receipt_fields,
    "execution": _execution,
    "file_type": _file_type,
    "interpretation": _interpretation,
    "own_message": _own_message,
    "read_range": _read_range,
    "absence": _absence,
    "peer_assertion": _peer_assertion,
    "frontmatter_speakers": _frontmatter_speakers,
    "unknown": _unknown,
}


def check_claim(
    claim: SourceClaim,
    artifacts: dict[str, SourceArtifact],
    root: Path,
    resolved: dict[str, ResolvedSource] | None = None,
) -> CheckResult:
    resolved = resolved or {sid: artifact.resolve(root) for sid, artifact in artifacts.items()}
    try:
        sources = [resolved[ref] for ref in claim.source_refs]
    except KeyError:
        return _outcome(claim, "unknown", "source_ref_unknown")
    unavailable = [source.artifact.source_id for source in sources if not source.available]
    if unavailable:
        return _outcome(claim, "unknown", f"sources_unavailable:{unavailable}")
    checker = _CHECKERS.get(claim.assertion.get("op"), _unknown)
    try:
        return checker(claim, sources)
    except (KeyError, TypeError, ValueError) as exc:
        return _outcome(claim, "unknown", f"invalid_assertion:{type(exc).__name__}")


def _control_claim(case: dict[str, Any], control: dict[str, Any]) -> SourceClaim:
    raw = copy.deepcopy(case["claim"])
    for key in ("claim_kind", "source_refs"):
        if key in control:
            raw[key] = copy.deepcopy(control[key])
    raw["assertion"].update(copy.deepcopy(control.get("claim_assertion", {})))
    return SourceClaim.from_dict(raw)


def validate_corpus(corpus: dict[str, Any]) -> tuple[dict[str, SourceArtifact], list[dict[str, Any]]]:
    if corpus.get("schema") != CORPUS_SCHEMA:
        raise ValueError("unsupported corpus schema")
    if not corpus.get("corpus_id") or not isinstance(corpus.get("cases"), list) or not corpus["cases"]:
        raise ValueError("corpus needs an id and nonempty cases")
    artifacts = {sid: SourceArtifact.from_dict(raw) for sid, raw in corpus.get("sources", {}).items()}
    if len(artifacts) != len(corpus.get("sources", {})):
        raise ValueError("duplicate source id")
    case_ids = set()
    for case in corpus["cases"]:
        if case["case_id"] in case_ids:
            raise ValueError(f"duplicate case id: {case['case_id']}")
        case_ids.add(case["case_id"])
        evidence_class = case.get("evidence_class")
        if evidence_class not in EVIDENCE_CLASSES:
            raise ValueError(f"invalid evidence class: {case['case_id']}")
        if case.get("expected_support") not in SUPPORTS:
            raise ValueError(f"invalid expected support: {case['case_id']}")
        claim = SourceClaim.from_dict(case["claim"])
        claims = [claim] + [_control_claim(case, control) for control in case.get("controls", [])]
        for control in case.get("controls", []):
            if control.get("expected_support") not in SUPPORTS:
                raise ValueError(f"invalid control support: {case['case_id']}")
            unknown_overrides = [ref for ref in control.get("resolved_overrides", {}) if ref not in artifacts]
            unknown_overrides += [ref for ref in control.get("source_completeness", {}) if ref not in artifacts]
            if unknown_overrides:
                raise ValueError(f"unknown control source refs: {unknown_overrides}")
        for candidate in claims:
            if candidate.assertion.get("op") not in _CHECKERS:
                raise ValueError(f"unsupported assertion op: {candidate.assertion.get('op')}")
            unknown = [ref for ref in candidate.source_refs if ref not in artifacts]
            if unknown:
                raise ValueError(f"unknown source refs: {unknown}")
            for ref in candidate.source_refs:
                artifact = artifacts[ref]
                if evidence_class == "committed_manifest" and artifact.source_type != "case_manifest":
                    raise ValueError(f"manifest source type mismatch: {case['case_id']}:{ref}")
                if evidence_class == "raw_artifact" and artifact.source_type == "case_manifest":
                    raise ValueError(f"manifest cannot back a raw case: {case['case_id']}:{ref}")
                actual_class = artifact.provenance.get("evidence_class")
                if actual_class != evidence_class:
                    raise ValueError(f"evidence class mismatch: {case['case_id']}:{ref}:{actual_class}")
    return artifacts, corpus["cases"]


def _run_control(
    case: dict[str, Any],
    control: dict[str, Any],
    index: int,
    artifacts: dict[str, SourceArtifact],
    resolved: dict[str, ResolvedSource],
    root: Path,
) -> dict[str, Any]:
    claim = _control_claim(case, control)
    local = resolved.copy()
    for ref, completeness in control.get("source_completeness", {}).items():
        base = local[ref]
        local[ref] = ResolvedSource(replace(base.artifact, completeness=completeness), base.available, base.content, base.data, base.metadata, base.reason)
    for ref, overlay in control.get("resolved_overrides", {}).items():
        base = local[ref]
        local[ref] = ResolvedSource(
            base.artifact,
            overlay.get("available", base.available),
            overlay.get("content", base.content),
            overlay.get("data", base.data),
            overlay.get("metadata", base.metadata),
            overlay.get("reason", base.reason),
        )
    result = check_claim(claim, artifacts, root, local)
    return {
        "control_id": f"{case['case_id']}-C{index}",
        "change": control["change"],
        "expected_support": control["expected_support"],
        "actual": result.to_dict(),
        "pass": result.support == control["expected_support"],
    }


def run_corpus(corpus: dict[str, Any], root: Path) -> dict[str, Any]:
    artifacts, cases = validate_corpus(corpus)
    resolved = {sid: artifact.resolve(root) for sid, artifact in artifacts.items()}
    rows = []
    for case in cases:
        claim = SourceClaim.from_dict(case["claim"])
        result = check_claim(claim, artifacts, root, resolved)
        controls = [_run_control(case, control, index, artifacts, resolved, root) for index, control in enumerate(case.get("controls", []), 1)]
        rows.append({
            "case_id": case["case_id"],
            "evidence_class": case["evidence_class"],
            "expected_support": case["expected_support"],
            "actual": result.to_dict(),
            "pass": result.support == case["expected_support"],
            "controls": controls,
        })
    raw = [row for row in rows if row["evidence_class"] == "raw_artifact"]
    manifest = [row for row in rows if row["evidence_class"] == "committed_manifest"]
    controls = [control for row in rows for control in row["controls"]]
    raw_sources_available = all(
        resolved[ref].available
        for case in cases if case["evidence_class"] == "raw_artifact"
        for ref in case["claim"]["source_refs"]
    )
    raw_controls = [control for row in raw for control in row["controls"]]
    return {
        "schema": RESULT_SCHEMA,
        "corpus_id": corpus["corpus_id"],
        "summary": {
            "total": len(rows),
            "passed": sum(row["pass"] for row in rows),
            "raw_total": len(raw),
            "raw_passed": sum(row["pass"] for row in raw),
            "manifest_total": len(manifest),
            "manifest_passed": sum(row["pass"] for row in manifest),
            "control_total": len(controls),
            "control_passed": sum(control["pass"] for control in controls),
            "raw_sources_available": raw_sources_available,
            "raw_predicate": bool(raw) and raw_sources_available and all(row["pass"] for row in raw) and all(control["pass"] for control in raw_controls),
            "corpus_predicate": all(row["pass"] for row in rows) and all(control["pass"] for control in controls),
        },
        "cases": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    raw = args.corpus.read_bytes()
    result = run_corpus(json.loads(raw), args.root)
    result["corpus_sha256"] = _sha_bytes(raw)
    result["instrument_sha256"] = _sha_bytes(Path(__file__).read_bytes())
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end="")
    return 0 if result["summary"]["corpus_predicate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
