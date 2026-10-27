#!/usr/bin/env python3
"""Run: python3 scripts/test_interview_project.py (ffmpeg/ffprobe integration included)."""
import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import interview_project as project


class ProjectChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, content in (("final.mp4", b"video-v2"), ("source.mp4", b"source"),
                              ("captions.srt", b"Cathy Chang\nTwitter @cathychang00\n"),
                              ("frame.png", b"review-evidence")):
            (self.root / name).write_bytes(content)
        (self.root / "render.json").write_text(json.dumps({"watermark": {"text": "Twitter @CathyChang00"}}))
        video = self.ref("final.mp4")
        self.data = {
            "schema_version": 1, "project": "test", "active_version": "V2",
            "versions": {"V2": {"video": video, "duration_seconds": 20, "fps": 30}},
            "spans": [{"id": "hook", "utterance_id": "crypto", "version": "V2",
                       "video_sha256": video["sha256"], "source": self.ref("source.mp4"),
                       "source_range": [100, 106.5], "output_range": [0, 5], "rate": 1.3},
                      {"id": "body", "utterance_id": "crypto", "version": "V2",
                       "video_sha256": video["sha256"], "source": self.ref("source.mp4"),
                       "source_range": [100, 106.5], "output_range": [10, 15], "rate": 1.3}],
            "checks": [self.check("names", "text", artifact=self.ref("captions.srt"),
                                  contains=["Cathy Chang", "Twitter @cathychang00"], excludes=["Host", "Guest"])],
            "feedback": [], "materials": [], "semantic_reviews": [],
        }

    def ref(self, filename):
        return {"path": filename, "sha256": project.sha256(self.root / filename)}

    def check(self, identifier, kind, **kwargs):
        return {"id": identifier, "kind": kind, "version": "V2",
                "video_sha256": self.ref("final.mp4")["sha256"], "scope": "specified artifact only", **kwargs}

    def review(self):
        return {"video_sha256": self.ref("final.mp4")["sha256"],
                "reviewer": {"kind": "agent", "name": "test visual reviewer"},
                "observed_at": "2026-10-27", "method": "Synthetic fixture review record; no listening",
                "verdict": "accepted", "evidence": [self.ref("frame.png")]}

    def report(self, **kwargs):
        return project.check_state(self.data, self.root, **kwargs)

    def test_exact_mapping_and_all_reused_occurrences(self):
        result = project.locate(self.data, "V2", "00:02")
        self.assertAlmostEqual(result["matches"][0]["source_second"], 102.6)
        self.assertEqual({s["span_id"] for s in result["all_occurrences"]}, {"hook", "body"})
        self.assertEqual(project.locate(self.data, "V2", 5)["matches"], [])

    def test_wrong_watched_version_is_rejected(self):
        with self.assertRaises(ValueError):
            project.locate(self.data, "V1", 2)

    def test_mapping_rate_mismatch_fails(self):
        self.data["spans"][0]["rate"] = 1.2
        self.assertEqual(self.report()["status"], "fail")
        with self.assertRaises(ValueError):
            project.locate(self.data, "V2", 2)

    def test_locate_rejects_changed_source_and_outside_time(self):
        (self.root / "source.mp4").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            project.locate(self.data, "V2", 2, base=self.root)
        with self.assertRaises(ValueError):
            project.locate(self.data, "V2", 20)

    def test_nonfinite_rate_fails(self):
        self.data["spans"][0]["rate"] = float("nan")
        self.assertEqual(self.report()["status"], "fail")

    def test_source_identity_change_fails(self):
        (self.root / "source.mp4").write_bytes(b"changed")
        self.assertEqual(self.report()["status"], "fail")

    def test_stale_check_binding_fails(self):
        self.data["checks"][0]["video_sha256"] = "0" * 64
        self.assertEqual(self.report()["status"], "fail")

    def test_changed_video_identity_fails(self):
        (self.root / "final.mp4").write_bytes(b"changed")
        self.assertEqual(self.report()["status"], "fail")

    def test_text_exact_case_and_forbidden_labels(self):
        self.assertEqual(self.report()["status"], "checked")
        self.data["checks"][0]["contains"] = ["Twitter @CathyChang00"]
        self.assertEqual(self.report()["status"], "fail")
        self.data["checks"][0]["contains"] = ["Cathy Chang"]
        self.data["checks"][0]["excludes"] = ["Cathy Chang"]
        self.assertEqual(self.report()["status"], "fail")

    def test_configuration_check_has_specific_scope(self):
        self.data["checks"] = [self.check("watermark-config", "json_value", artifact=self.ref("render.json"),
                                          pointer="/watermark/text", equals="Twitter @CathyChang00")]
        report = self.report()
        self.assertEqual(report["status"], "checked")
        self.assertIn("do not prove burned-in pixels", report["boundary"])

    def test_empty_acceptance_is_not_pass(self):
        self.data["checks"] = []
        self.assertEqual(self.report()["status"], "pending")

    def test_visual_review_is_separate_from_text_check(self):
        self.data["checks"].append(self.check("pixels", "review", review={**self.review(), "verdict": "uncertain"}))
        self.assertEqual(self.report()["status"], "fail")
        self.data["checks"][-1]["review"]["verdict"] = "accepted"
        report = self.report()
        self.assertEqual(report["status"], "checked")
        self.assertEqual(report["checks"][-1]["status"], "review_recorded")

    def test_review_evidence_changed_fails(self):
        self.data["checks"] = [self.check("pixels", "review", review=self.review())]
        (self.root / "frame.png").write_bytes(b"new image")
        self.assertEqual(self.report()["status"], "fail")

    def test_feedback_cannot_be_verified_without_checks(self):
        self.data["feedback"] = [{"id": "F1", "observed_version": "V2", "at": 2,
                                   "request": "full name", "span_ids": ["hook"], "status": "verified",
                                   "resolved_version": "V2", "check_ids": []}]
        self.assertEqual(self.report()["status"], "fail")
        self.data["feedback"][0]["check_ids"] = ["names"]
        self.assertEqual(self.report()["status"], "fail")
        self.data["checks"].append(self.check("pixels", "review", review=self.review()))
        self.data["feedback"][0]["check_ids"].append("pixels")
        self.assertEqual(self.report()["status"], "checked")
        self.assertEqual(project.locate(self.data, None, feedback_id="F1")["output_second"], 2)

    def test_feedback_wrong_span_cannot_pass(self):
        self.data["feedback"] = [{"id": "F1", "observed_version": "V2", "at": 8,
                                   "request": "full name", "span_ids": ["hook"], "status": "located"}]
        self.assertEqual(self.report()["status"], "fail")

    def test_semantic_risk_needs_actual_review_record(self):
        self.data["spans"][0]["semantic_review_required"] = True
        self.assertEqual(self.report()["status"], "pending")
        self.data["semantic_reviews"] = [{
            "id": "S1", "version": "V2", "span_ids": ["hook"],
            "before": "Many marketers have crypto backgrounds.", "after": "Marketers have crypto backgrounds.",
            "dimensions": {d: {"verdict": "uncertain", "note": "needs original context"} for d in project.DIMENSIONS},
            "review": self.review(),
        }]
        result = self.report()
        self.assertEqual(result["status"], "fail")
        self.assertIn("many", result["risks"][0]["removed_sensitive_words"])
        item = self.data["semantic_reviews"][0]
        item["after"] = item["before"]
        item["dimensions"] = {d: {"verdict": "preserved", "note": "test fixture text remains identical"} for d in project.DIMENSIONS}
        self.assertEqual(self.report()["status"], "checked")
        item["review"]["video_sha256"] = "0" * 64
        self.assertEqual(self.report()["status"], "fail")

    def test_required_material_pending_at_delivery_only(self):
        self.data["materials"] = [{"id": "M1", "version": "V2", "topic": "specific collab",
                                    "purpose": "show announcement", "span_ids": ["body"],
                                    "required": True, "status": "planned"}]
        self.assertEqual(self.report(stage="plan")["status"], "checked")
        self.assertEqual(self.report()["status"], "pending")

    def test_views_from_another_post_fail(self):
        self.data["materials"] = [{"id": "M1", "version": "V2", "topic": "specific collab",
            "purpose": "show announcement", "span_ids": ["body"], "required": True, "status": "placed",
            "source_url": "https://example.test/post/A", "author": "Example", "observed_at": "2026-10-27",
            "semantic_limits": "this event only", "asset": self.ref("frame.png"),
            "source_evidence": self.ref("frame.png"), "output_range": [10, 13],
            "metric": {"kind": "views", "display_value": "1.6M", "source_url": "https://example.test/post/B",
                       "observed_at": "2026-10-27", "evidence": self.ref("frame.png")}}]
        self.assertEqual(self.report()["status"], "fail")

    def test_duplicate_ids_rejected(self):
        self.data["spans"].append(copy.deepcopy(self.data["spans"][0]))
        path = self.root / "state.json"
        project.write_json(path, self.data)
        with self.assertRaises(ValueError):
            project.load_state(path)

    def test_media_checks_are_pending_without_flag(self):
        self.data["checks"] = [self.check("duration", "media_duration", expected_seconds=20)]
        self.assertEqual(self.report()["status"], "pending")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg and ffprobe required")
class RealMediaChecks(unittest.TestCase):
    def test_init_duration_and_audio_packet_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, copy_path = root / "source.mp4", root / "copy.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=30:d=1",
                            "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:v", "libx264", "-c:a", "aac",
                            "-shortest", str(source)], check=True)
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(source), "-c", "copy", "-metadata", "title=copy", str(copy_path)], check=True)
            state = root / "state.json"
            subprocess.run([sys_executable(), str(Path(project.__file__)), "init", "--video", str(copy_path),
                            "--version", "V1", "--project", "test", "--out", str(state)], check=True, capture_output=True)
            data = project.load_state(state)
            video_hash = data["versions"]["V1"]["video"]["sha256"]
            common = {"version": "V1", "video_sha256": video_hash, "scope": "actual media"}
            data["checks"] = [
                {**common, "id": "duration", "kind": "media_duration", "expected_seconds": 1.0},
                {**common, "id": "audio", "kind": "audio_identity", "baseline": {"path": str(source), "sha256": project.sha256(source)}},
            ]
            self.assertEqual(project.check_state(data, root, media=True)["status"], "checked")
            data["checks"][0]["expected_seconds"] = 2.0
            self.assertEqual(project.check_state(data, root, media=True)["status"], "fail")
            self.assertEqual(project.check_state(data, root, media=False)["status"], "pending")


def sys_executable():
    import sys
    return sys.executable


if __name__ == "__main__":
    unittest.main(verbosity=2)
