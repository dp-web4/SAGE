import ast
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from sage.gateway import premise_fidelity as pf


class PremiseFidelityTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix=".pf-", dir=Path(__file__).parent)
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def artifact(self, name, content, **overrides):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = content if isinstance(content, bytes) else content.encode()
        path.write_bytes(raw)
        source = {
            "source_id": overrides.pop("source_id", name),
            "source_type": overrides.pop("source_type", "conversation"),
            "producer_or_speaker": overrides.pop("producer_or_speaker", "being"),
            "content_hash": hashlib.sha256(raw).hexdigest(),
            "completeness": overrides.pop("completeness", "complete"),
            "pointer": overrides.pop("pointer", {"kind": "text", "path": name}),
            "observed_at": "2026-11-03",
            "provenance": overrides.pop("provenance", {}),
        }
        source.update(overrides)
        return source

    def check(self, source, claim):
        artifact = pf.SourceArtifact.from_dict(source)
        return pf.check_claim(pf.SourceClaim.from_dict(claim), {artifact.source_id: artifact}, self.root)

    def claim(self, source_id, op, kind="result", **assertion):
        return {
            "claim_text": "test claim",
            "claim_kind": kind,
            "source_refs": [source_id] if isinstance(source_id, str) else source_id,
            "assertion": {"op": op, **assertion},
        }

    def test_exact_text_and_quote_relations(self):
        source = self.artifact("source", "alpha beta gamma")
        self.assertEqual(self.check(source, self.claim("source", "text_contains", contains=["alpha", "gamma"])).support, "supported")
        self.assertEqual(self.check(source, self.claim("source", "text_contains", contains=["delta"])).support, "contradicted")
        self.assertEqual(self.check(source, self.claim("source", "quote", kind="quote", needle="beta")).support, "supported")
        self.assertEqual(self.check(source, self.claim("source", "quote", kind="quote", needle="delta")).support, "contradicted")

    def test_partial_quote_and_whole_file_absence_are_incomplete(self):
        source = self.artifact("partial", "alpha", completeness="partial")
        self.assertEqual(self.check(source, self.claim("partial", "quote", kind="quote", needle="missing")).support, "incomplete")
        self.assertEqual(self.check(source, self.claim("partial", "text_contains", contains=["missing"])).support, "incomplete")
        ambiguous = self.artifact("ambiguous", "alpha", completeness="ambiguous")
        self.assertEqual(self.check(ambiguous, self.claim("ambiguous", "text_contains", contains=["missing"])).support, "unknown")
        record = {"result": "[lines 2-3 of 9]\nalpha"}
        raw = json.dumps(record) + "\n"
        data_source = self.artifact("read.jsonl", raw, source_id="read", completeness="partial", pointer={"kind": "jsonl", "path": "read.jsonl", "jsonl_line": 1})
        result = self.check(data_source, self.claim("read", "absence", kind="completeness", needle="omega", scope="whole_file"))
        self.assertEqual(result.support, "incomplete")

    def test_complete_absence_and_present_needle(self):
        record = {"result": "alpha beta"}
        source = self.artifact("read.jsonl", json.dumps(record) + "\n", source_id="read", pointer={"kind": "jsonl", "path": "read.jsonl", "jsonl_line": 1})
        self.assertEqual(self.check(source, self.claim("read", "absence", kind="completeness", needle="omega", scope="whole_file")).support, "supported")
        self.assertEqual(self.check(source, self.claim("read", "absence", kind="completeness", needle="alpha", scope="whole_file")).support, "contradicted")

    def test_stale_hash_and_missing_source_fail_unknown(self):
        source = self.artifact("source", "alpha")
        (self.root / "source").write_text("changed")
        self.assertEqual(self.check(source, self.claim("source", "text_contains", contains=["alpha"])).support, "unknown")
        missing = self.artifact("missing", "alpha")
        (self.root / "missing").unlink()
        result = self.check(missing, self.claim("missing", "text_contains", contains=["alpha"]))
        self.assertEqual((result.support, result.reason.startswith("sources_unavailable")), ("unknown", True))

    def test_source_root_escape_is_unavailable(self):
        source = self.artifact("source", "alpha")
        source["pointer"]["path"] = "../source"
        self.assertEqual(self.check(source, self.claim("source", "text_contains", contains=["alpha"])).support, "unknown")

    def test_jsonl_seq_and_gzip_json_path_reopen_exact_records(self):
        lines = '{"seq": 1, "text": "one"}\n{"seq": 2, "text": "two"}\n'
        source = self.artifact("conversation.jsonl", lines, source_id="turn", pointer={"kind": "jsonl", "path": "conversation.jsonl", "seq": 2})
        artifact = pf.SourceArtifact.from_dict(source)
        resolved = artifact.resolve(self.root)
        self.assertEqual(resolved.data["text"], "two")
        heartbeat = gzip.compress(json.dumps({"explore": {"trace": [{"effector": "memory_write", "ok": False}]}}).encode())
        gz = self.artifact("beat.gz", heartbeat, source_id="receipt", source_type="tool_receipt", pointer={"kind": "gzip_jsonl", "path": "beat.gz", "jsonl_line": 1, "json_path": ["explore", "trace", 0]})
        result = self.check(gz, self.claim("receipt", "receipt_fields", effector="memory_write", ok=False))
        self.assertEqual(result.support, "supported")

    def test_duplicate_seq_and_malformed_json_are_unavailable(self):
        source = self.artifact("conversation.jsonl", '{"seq": 1}\n{"seq": 1}\n', source_id="turn", pointer={"kind": "jsonl", "path": "conversation.jsonl", "seq": 1})
        artifact = pf.SourceArtifact.from_dict(source)
        self.assertFalse(artifact.resolve(self.root).available)
        bad = self.artifact("bad.jsonl", '{bad\n', source_id="bad", pointer={"kind": "jsonl", "path": "bad.jsonl", "jsonl_line": 1})
        self.assertEqual(self.check(bad, self.claim("bad", "text_contains", contains=["bad"])).support, "unknown")

    def test_receipt_mismatch_and_argument_identity(self):
        record = {"effector": "memory_write", "args": {"path": "inbox/note.md"}, "ok": False, "error": "FileExistsError: exists"}
        source = self.artifact("receipt.jsonl", json.dumps(record) + "\n", source_id="receipt", source_type="tool_receipt", pointer={"kind": "jsonl", "path": "receipt.jsonl", "jsonl_line": 1})
        good = self.claim("receipt", "receipt_fields", effector="memory_write", ok=False, error_contains="FileExistsError", arg_path_contains="inbox/")
        self.assertEqual(self.check(source, good).support, "supported")
        bad = self.claim("receipt", "receipt_fields", effector="os.remove", ok=False)
        self.assertEqual(self.check(source, bad).support, "contradicted")

    def test_file_type_claim(self):
        source = self.artifact("inbox", "plain file", source_id="stat", pointer={"kind": "stat", "path": "inbox"})
        self.assertEqual(self.check(source, self.claim("stat", "file_type", expected="regular_file")).support, "supported")
        self.assertEqual(self.check(source, self.claim("stat", "file_type", expected="directory")).support, "contradicted")

    def test_inference_and_peer_assertion_do_not_promote(self):
        source = self.artifact("post", "---\nfrom: peer\n---\nunresponsive since October 12th")
        self.assertEqual(self.check(source, self.claim("post", "interpretation", kind="inference")).support, "inference")
        unknown = self.claim("post", "peer_assertion", kind="paraphrase", claim_fragment="since October 12th")
        self.assertEqual(self.check(source, unknown).support, "unknown")

    def test_peer_correction_can_contradict_original_assertion(self):
        original = self.artifact("original", "---\nfrom: peer\n---\nsince October 12th")
        correction = self.artifact("correction", "---\nfrom: seat\n---\nno evidence; these are void")
        artifacts = {s["source_id"]: pf.SourceArtifact.from_dict(s) for s in (original, correction)}
        claim = pf.SourceClaim.from_dict(self.claim(["original", "correction"], "peer_assertion", kind="paraphrase", claim_fragment="since October 12th"))
        self.assertEqual(pf.check_claim(claim, artifacts, self.root).support, "contradicted")

    def test_own_message_and_missing_authorship_marker(self):
        record = {"result": {"said": "text [your own message, shortened in this receipt only]"}}
        source = self.artifact("say.jsonl", json.dumps(record) + "\n", source_id="say", source_type="tool_receipt", pointer={"kind": "jsonl", "path": "say.jsonl", "jsonl_line": 1})
        self.assertEqual(self.check(source, self.claim("say", "own_message", kind="speaker", claimed_speaker="self")).support, "supported")
        self.assertEqual(self.check(source, self.claim("say", "own_message", kind="speaker", claimed_speaker="dp")).support, "contradicted")
        record["result"]["said"] = "text"
        unmarked = self.artifact("unmarked.jsonl", json.dumps(record) + "\n", source_id="unmarked", source_type="tool_receipt", pointer={"kind": "jsonl", "path": "unmarked.jsonl", "jsonl_line": 1})
        self.assertEqual(self.check(unmarked, self.claim("unmarked", "own_message", kind="speaker", claimed_speaker="self")).support, "unknown")

    def test_read_range_and_whole_file_mutation(self):
        record = {"result": "[lines 195-385 of 1206]\nalpha\n[truncated]"}
        source = self.artifact("read.jsonl", json.dumps(record) + "\n", source_id="read", source_type="file_read", completeness="partial", pointer={"kind": "jsonl", "path": "read.jsonl", "jsonl_line": 1})
        good = self.claim("read", "read_range", kind="completeness", start=195, end=385, total=1206, whole_file=False)
        self.assertEqual(self.check(source, good).support, "supported")
        bad = self.claim("read", "read_range", kind="completeness", start=1, end=1206, total=1206, whole_file=True)
        self.assertEqual(self.check(source, bad).support, "contradicted")

    def test_frontmatter_speakers_and_missing_frontmatter(self):
        one = self.artifact("one", "---\nfrom: being\n---\nfirst")
        two = self.artifact("two", "---\nfrom: seat\n---\nsecond")
        artifacts = {s["source_id"]: pf.SourceArtifact.from_dict(s) for s in (one, two)}
        claim = pf.SourceClaim.from_dict(self.claim(["one", "two"], "frontmatter_speakers", kind="speaker", expected=["being", "seat"]))
        self.assertEqual(pf.check_claim(claim, artifacts, self.root).support, "supported")
        wrong = pf.SourceClaim.from_dict(self.claim(["one", "two"], "frontmatter_speakers", kind="speaker", expected=["seat", "being"]))
        self.assertEqual(pf.check_claim(wrong, artifacts, self.root).support, "contradicted")
        missing = self.artifact("missing", "unsigned body")
        artifacts["missing"] = pf.SourceArtifact.from_dict(missing)
        unknown = pf.SourceClaim.from_dict(self.claim(["one", "missing"], "frontmatter_speakers", kind="speaker", expected=["being", "seat"]))
        self.assertEqual(pf.check_claim(unknown, artifacts, self.root).support, "unknown")

    def test_unexecuted_code_requires_manifest_not_blanket_keyword_rejection(self):
        manifest = self.artifact("manifest", "No tool result contains `ENXIO`; scripts were never ran", source_type="case_manifest")
        claim = self.claim("manifest", "manifest_unexecuted", required_fragments=["No tool result contains `ENXIO`", "never ran"])
        self.assertEqual(self.check(manifest, claim).support, "contradicted")
        raw = self.artifact("raw", "No tool result contains `ENXIO`; scripts were never ran", source_type="tool_receipt")
        raw_claim = self.claim("raw", "manifest_unexecuted", required_fragments=["No tool result contains `ENXIO`", "never ran"])
        self.assertEqual(self.check(raw, raw_claim).support, "unknown")
        executed = self.artifact("executed.jsonl", json.dumps({"effector": "run", "ok": False, "error": "ENXIO"}) + "\n", source_id="executed", source_type="tool_receipt", pointer={"kind": "jsonl", "path": "executed.jsonl", "jsonl_line": 1})
        positive = self.claim("executed", "receipt_fields", effector="run", ok=False, error_contains="ENXIO")
        self.assertEqual(self.check(executed, positive).support, "supported")

    def corpus(self):
        raw = self.artifact("raw", "alpha")
        manifest = self.artifact("manifest", "body.inventory() measured video_devices=[]", source_type="case_manifest")
        return {
            "schema": pf.CORPUS_SCHEMA,
            "corpus_id": "synthetic",
            "sources": {"raw": raw, "manifest": manifest},
            "cases": [
                {"case_id": "raw-case", "evidence_class": "raw_artifact", "claim": self.claim("raw", "text_contains", contains=["alpha"]), "expected_support": "supported"},
                {"case_id": "manifest-case", "evidence_class": "committed_manifest", "claim": self.claim("manifest", "text_contains", contains=["video_devices=[]"]), "expected_support": "supported"},
            ],
        }

    def test_corpus_separates_raw_and_manifest_predicates(self):
        result = pf.run_corpus(self.corpus(), self.root)
        self.assertEqual(result["summary"]["raw_total"], 1)
        self.assertEqual(result["summary"]["manifest_total"], 1)
        self.assertTrue(result["summary"]["raw_predicate"])
        self.assertTrue(result["summary"]["corpus_predicate"])

    def test_corpus_raw_predicate_fails_closed_on_stale_source(self):
        corpus = self.corpus()
        (self.root / "raw").write_text("changed")
        result = pf.run_corpus(corpus, self.root)
        self.assertFalse(result["summary"]["raw_sources_available"])
        self.assertFalse(result["summary"]["raw_predicate"])
        self.assertFalse(result["summary"]["corpus_predicate"])
        self.assertEqual(result["summary"]["manifest_passed"], 1)

    def test_corpus_validation_rejects_unknown_operation(self):
        corpus = self.corpus()
        corpus["cases"][0]["claim"]["assertion"]["op"] = "invented"
        with self.assertRaises(ValueError):
            pf.run_corpus(corpus, self.root)

    def test_cli_replay_is_byte_deterministic(self):
        corpus_path = self.root / "corpus.json"
        corpus_path.write_text(json.dumps(self.corpus()))
        one = self.root / "one.json"
        two = self.root / "two.json"
        self.assertEqual(pf.main([str(corpus_path), "--root", str(self.root), "--output", str(one)]), 0)
        self.assertEqual(pf.main([str(corpus_path), "--root", str(self.root), "--output", str(two)]), 0)
        self.assertEqual(one.read_bytes(), two.read_bytes())

    def test_no_model_network_or_effector_dependencies(self):
        tree = ast.parse(Path(pf.__file__).read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue(imported.isdisjoint({"httpx", "requests", "ollama", "subprocess", "torch"}))


if __name__ == "__main__":
    unittest.main()
