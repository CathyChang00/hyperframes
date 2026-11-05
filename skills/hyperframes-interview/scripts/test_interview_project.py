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

    def material(self, identifier="M1", window=None, mode="fullscreen", **kwargs):
        return {"id": identifier, "version": "V2", "topic": "specific source",
                "purpose": "show source during its discussion", "span_ids": ["body"],
                "required": False, "status": "placed", "source_url": "https://example.test/post/A",
                "author": "Example", "observed_at": "2026-11-04", "semantic_limits": "this source only",
                "asset": self.ref("frame.png"), "source_evidence": self.ref("frame.png"),
                "display_mode": mode, "output_range": window or [10, 14], **kwargs}

    def set_material_policy(self, limit=4, fps=30):
        self.data["versions"]["V2"].update(fps=fps, materials_policy={"fullscreen_max_seconds": limit})

    def set_typed_material_policy(self, static=4, video=15, fps="30000/1001"):
        self.data["versions"]["V2"].update(fps=fps, materials_policy={
            "static_fullscreen_max_seconds": static, "video_max_seconds": video})

    def test_fullscreen_119_frames_pass_but_120_fail_at_2997(self):
        self.set_material_policy(fps="30000/1001")
        for count, expected in ((119, "checked"), (120, "fail")):
            with self.subTest(frames=count):
                self.data["materials"] = [self.material(
                    window=[300 * 1001 / 30000, (300 + count) * 1001 / 30000],
                    output_frames=[300, 300 + count])]
                self.assertEqual(self.report(stage="plan")["status"], expected)

    def test_second_windows_are_quantized_to_project_frames(self):
        self.set_material_policy(fps=29.97)
        self.data["materials"] = [self.material(window=[10.01, 13.981])]
        self.assertEqual(self.report(stage="plan")["status"], "checked")
        self.data["materials"][0]["output_range"] = [10.01, 14.014]
        self.assertEqual(self.report(stage="plan")["status"], "fail")

    def test_overlay_is_not_subject_to_fullscreen_cap(self):
        self.set_material_policy()
        self.data["materials"] = [self.material(window=[10, 18], mode="overlay")]
        self.assertEqual(self.report(stage="plan")["status"], "checked")

    def test_other_project_can_explicitly_allow_five_seconds(self):
        self.set_material_policy(limit=5)
        self.data["materials"] = [self.material(window=[10, 15])]
        self.assertEqual(self.report(stage="plan")["status"], "checked")
        self.data["materials"][0]["output_range"] = [10, 15.1]
        self.assertEqual(self.report(stage="plan")["status"], "fail")

    def test_no_policy_does_not_invent_a_cathy_cap(self):
        self.data["materials"] = [self.material(window=[10, 18])]
        del self.data["materials"][0]["display_mode"]
        report = self.report(stage="plan")
        self.assertEqual(report["status"], "checked")
        self.assertTrue(any(r.get("materials_policy_missing") for r in report["risks"]))

    def test_typed_static_119_frames_pass_but_120_fail_at_2997(self):
        self.set_typed_material_policy()
        for count, expected in ((119, "checked"), (120, "fail")):
            with self.subTest(frames=count):
                self.data["materials"] = [self.material(asset_type="static",
                    window=[300 * 1001 / 30000, (300 + count) * 1001 / 30000],
                    output_frames=[300, 300 + count])]
                self.assertEqual(self.report(stage="plan")["status"], expected)

    def test_typed_video_449_frames_pass_but_450_fail_at_2997(self):
        self.set_typed_material_policy()
        for count, expected in ((449, "checked"), (450, "fail")):
            with self.subTest(frames=count):
                self.data["materials"] = [self.material(asset_type="video",
                    window=[0, count * 1001 / 30000], output_frames=[0, count])]
                self.assertEqual(self.report(stage="plan")["status"], expected)

    def test_typed_video_can_show_complete_nine_second_action(self):
        self.set_typed_material_policy()
        self.data["materials"] = [self.material(asset_type="video", window=[10, 19.4])]
        self.assertEqual(self.report(stage="plan")["status"], "checked")

    def test_typed_video_overlay_obeys_video_cap(self):
        self.set_typed_material_policy(fps=30)
        for duration, expected in ((9.4, "checked"), (15, "checked"), (15.1, "fail")):
            with self.subTest(duration=duration):
                self.data["materials"] = [self.material(asset_type="video", mode="overlay",
                    window=[0, duration], span_ids=["hook"])]
                self.assertEqual(self.report(stage="plan")["status"], expected)

    def test_typed_static_overlay_is_not_subject_to_fullscreen_cap(self):
        self.set_typed_material_policy()
        self.data["materials"] = [self.material(asset_type="static", mode="overlay", window=[0, 20])]
        self.assertEqual(self.report(stage="plan")["status"], "checked")

    def test_typed_policy_needs_valid_content_category_for_all_placed_items(self):
        self.set_typed_material_policy()
        for mode in ("fullscreen", "overlay"):
            for kind in (None, "", "animation", "image", "mp4", True):
                with self.subTest(mode=mode, kind=kind):
                    item = self.material(mode=mode)
                    if kind is not None:
                        item["asset_type"] = kind
                    self.data["materials"] = [item]
                    self.assertEqual(self.report(stage="plan")["status"], "fail")

    def test_scrolling_still_video_file_stays_under_static_cap(self):
        self.set_typed_material_policy()
        self.data["materials"] = [self.material(asset_type="static", window=[10, 15],
                                               asset=self.ref("source.mp4"))]
        self.assertEqual(self.report(stage="plan")["status"], "fail")

    def test_legacy_policy_still_caps_video_as_fullscreen_at_four_seconds(self):
        self.set_material_policy()
        self.data["materials"] = [self.material(asset_type="video", window=[10, 19.4])]
        original = copy.deepcopy(self.data)
        self.assertEqual(self.report(stage="plan")["status"], "fail")
        self.assertEqual(self.data, original)

    def test_typed_policy_rejects_missing_mixed_and_invalid_limits(self):
        policies = [{}, {"static_fullscreen_max_seconds": 4}, {"video_max_seconds": 15},
                    {"fullscreen_max_seconds": 4, "static_fullscreen_max_seconds": 4},
                    {"fullscreen_max_seconds": 4, "video_max_seconds": 15}]
        for key in ("static_fullscreen_max_seconds", "video_max_seconds"):
            for value in (0, -1, True, "invalid", None, float("nan"), float("inf"), 0.001):
                policies.append({"static_fullscreen_max_seconds": 4, "video_max_seconds": 15, key: value})
        for policy in policies:
            with self.subTest(policy=policy):
                self.data["versions"]["V2"]["materials_policy"] = policy
                self.assertEqual(self.report(stage="plan")["status"], "fail")

    def test_typed_continuous_video_cannot_reset_cap_by_id_or_display_mode(self):
        self.set_typed_material_policy(fps=30)
        self.data["materials"] = [
            self.material("M1", [0, 8], asset_type="video", span_ids=["hook"]),
            self.material("M2", [8, 16], asset_type="video", mode="overlay")]
        self.assertEqual(self.report(stage="plan")["status"], "fail")
        self.data["materials"][0]["continuity_id"] = "first-name"
        self.data["materials"][1]["continuity_id"] = "second-name"
        self.assertEqual(self.report(stage="plan")["status"], "fail")

    def test_typed_video_one_frame_seam_does_not_reset_cap(self):
        self.set_typed_material_policy(fps=30)
        self.data["materials"] = [
            self.material("M1", [0, 8], asset_type="video", span_ids=["hook"]),
            self.material("M2", [241 / 30, 481 / 30], asset_type="video")]
        self.assertEqual(self.report(stage="plan")["status"], "fail")

    def test_typed_static_split_still_uses_four_second_cap(self):
        self.set_typed_material_policy(fps=30)
        self.data["materials"] = [self.material("M1", [10, 12.5], asset_type="static"),
                                  self.material("M2", [12.5, 15], asset_type="static")]
        self.assertEqual(self.report(stage="plan")["status"], "fail")

    def test_typed_derived_assets_share_declared_continuity_cap(self):
        self.set_typed_material_policy(fps=30)
        self.data["materials"] = [
            self.material("M1", [0, 8], asset_type="video", span_ids=["hook"],
                          continuity_id="one-product-demonstration"),
            self.material("M2", [8, 16], asset_type="video", asset=self.ref("source.mp4"),
                          continuity_id="one-product-demonstration")]
        self.assertEqual(self.report(stage="plan")["status"], "fail")
        del self.data["materials"][1]["continuity_id"]
        self.assertEqual(self.report(stage="plan")["status"], "checked")

    def test_typed_same_asset_or_continuity_cannot_switch_category(self):
        self.set_typed_material_policy(fps=30)
        self.data["materials"] = [
            self.material("M1", [10, 12], asset_type="static"),
            self.material("M2", [12, 15], asset_type="video")]
        self.assertEqual(self.report(stage="plan")["status"], "fail")
        self.data["materials"][1]["asset"] = self.ref("source.mp4")
        for item in self.data["materials"]:
            item["continuity_id"] = "same-source-presentation"
        self.assertEqual(self.report(stage="plan")["status"], "fail")

    def test_typed_static_and_video_caps_apply_independently(self):
        self.set_typed_material_policy(fps=30)
        self.data["materials"] = [
            self.material("M1", [0, 4], asset_type="static", span_ids=["hook"]),
            self.material("M2", [4, 19], asset_type="video", asset=self.ref("source.mp4"))]
        self.assertEqual(self.report(stage="plan")["status"], "checked")

    def test_active_policy_requires_valid_display_mode(self):
        self.set_material_policy()
        for mode in (None, "full-screen", ""):
            with self.subTest(mode=mode):
                self.data["materials"] = [self.material(mode=mode)]
                self.assertEqual(self.report(stage="plan")["status"], "fail")

    def test_explicit_frames_must_match_seconds_and_be_integer(self):
        self.set_material_policy()
        for frames in ([300, 421], [True, 420], [420, 300], [300, 420.0]):
            with self.subTest(frames=frames):
                self.data["materials"] = [self.material(output_frames=frames)]
                self.assertEqual(self.report(stage="plan")["status"], "fail")
        self.data["materials"] = [self.material(output_frames=[300, 420])]
        self.assertEqual(self.report(stage="plan")["status"], "checked")

    def test_material_must_overlap_current_linked_speech(self):
        self.data["materials"] = [self.material(window=[0, 4])]
        self.assertEqual(self.report(stage="plan")["status"], "fail")
        self.data["materials"][0]["span_ids"] = ["hook"]
        self.assertEqual(self.report(stage="plan")["status"], "checked")
        self.data["materials"][0]["span_ids"] = ["unknown"]
        self.assertEqual(self.report(stage="plan")["status"], "fail")

    def test_intentional_material_lead_needs_reason_and_bounded_offset(self):
        self.data["materials"] = [self.material(window=[6, 9], timing_exception={
            "reason": "Introduce the source before the guest names it", "max_offset_seconds": 1})]
        self.assertEqual(self.report(stage="plan")["status"], "checked")
        for exception in ({"reason": "Intro", "max_offset_seconds": 0.5},
                          {"reason": "", "max_offset_seconds": 1},
                          {"reason": None, "max_offset_seconds": 1},
                          {"reason": "Intro", "max_offset_seconds": -1}):
            with self.subTest(exception=exception):
                self.data["materials"][0]["timing_exception"] = exception
                self.assertEqual(self.report(stage="plan")["status"], "fail")

    def test_touching_half_open_window_needs_explicit_timing_exception(self):
        self.data["materials"] = [self.material(window=[6, 10])]
        self.assertEqual(self.report(stage="plan")["status"], "fail")
        self.data["materials"][0]["timing_exception"] = {"reason": "Source pre-roll ends at answer start", "max_offset_seconds": 0}
        self.assertEqual(self.report(stage="plan")["status"], "checked")

    def test_splitting_same_image_does_not_reset_fullscreen_cap(self):
        self.set_material_policy()
        self.data["materials"] = [self.material("M1", [10, 12.5]), self.material("M2", [12.5, 15])]
        self.assertEqual(self.report(stage="plan")["status"], "fail")
        self.data["materials"][0]["continuity_id"] = "attempt-a"
        self.data["materials"][1]["continuity_id"] = "attempt-b"
        self.assertEqual(self.report(stage="plan")["status"], "fail")

    def test_one_frame_seam_does_not_reset_same_image_cap(self):
        self.set_material_policy()
        self.data["materials"] = [self.material("M1", [10, 12.5]), self.material("M2", [376 / 30, 451 / 30])]
        self.assertEqual(self.report(stage="plan")["status"], "fail")

    def test_distinct_images_get_separate_caps_unless_declared_continuation(self):
        self.set_material_policy()
        (self.root / "other.png").write_bytes(b"a distinct supporting image")
        self.data["materials"] = [self.material("M1", [10, 12.5]), self.material("M2", [12.5, 15], asset=self.ref("other.png"))]
        self.assertEqual(self.report(stage="plan")["status"], "checked")
        for item in self.data["materials"]:
            item["continuity_id"] = "same-long-post-different-crops"
        self.assertEqual(self.report(stage="plan")["status"], "fail")

    def test_nonadjacent_intentional_reuse_keeps_separate_caps(self):
        self.set_material_policy()
        self.data["materials"] = [self.material("M1", [0, 3], span_ids=["hook"]), self.material("M2", [10, 13])]
        self.assertEqual(self.report(stage="plan")["status"], "checked")

    def test_material_window_must_stay_in_final_video(self):
        self.data["materials"] = [self.material(window=[10, 21], mode="overlay")]
        self.assertEqual(self.report(stage="plan")["status"], "fail")

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
            self.assertNotIn("materials_policy", data["versions"]["V1"])
            self.assertNotIn("materials_policy_source", data["versions"]["V1"])
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

    def test_init_with_explicit_preset_imports_only_material_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, preset_path, state = root / "source.mp4", root / "preset.json", root / "state.json"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=30:d=1",
                            "-c:v", "libx264", str(source)], check=True)
            before = project.sha256(source)
            project.write_json(preset_path, {"id": "custom-five-second-project", "materials": {"fullscreen_max_seconds": 5},
                                            "playback": {"body_source_rate": 9}, "canvas": {"width": 9000}})
            subprocess.run([sys_executable(), str(Path(project.__file__)), "init", "--video", str(source),
                            "--version", "V1", "--project", "custom", "--out", str(state),
                            "--preset", str(preset_path)], check=True, capture_output=True)
            version = project.load_state(state)["versions"]["V1"]
            self.assertEqual(version["materials_policy"], {"fullscreen_max_seconds": 5})
            self.assertEqual(version["materials_policy_source"], {
                "preset_id": "custom-five-second-project",
                "preset": {"path": str(preset_path.resolve()), "sha256": project.sha256(preset_path)}})
            self.assertNotIn("playback", version)
            self.assertNotIn("canvas", version)
            self.assertEqual(project.sha256(source), before)

    def test_init_rejects_invalid_preset_caps_without_creating_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, preset_path = root / "source.mp4", root / "preset.json"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=30:d=1",
                            "-c:v", "libx264", str(source)], check=True)
            for i, cap in enumerate((0, -1, True, "invalid", 0.001)):
                with self.subTest(cap=cap):
                    state = root / f"state-{i}.json"
                    project.write_json(preset_path, {"id": "invalid-project", "materials": {"fullscreen_max_seconds": cap}})
                    result = subprocess.run([sys_executable(), str(Path(project.__file__)), "init", "--video", str(source),
                                             "--version", "V1", "--project", "invalid", "--out", str(state),
                                             "--preset", str(preset_path)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2)
                    self.assertFalse(state.exists())

    def test_init_typed_preset_keeps_rational_fps_and_never_overwrites_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, preset_path, state = root / "source.mp4", root / "preset.json", root / "state.json"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "color=c=black:s=64x64:r=30000/1001:d=1", "-c:v", "libx264", str(source)], check=True)
            source_hash = project.sha256(source)
            policy = {"static_fullscreen_max_seconds": 4, "video_max_seconds": 15}
            project.write_json(preset_path, {"id": "typed-cathy-project", "materials": {
                **policy, "cap_includes_fades": True, "motion": {"direction": "content_up"}},
                "playback": {"body_source_rate": 1.2}, "canvas": {"width": 1920}})
            command = [sys_executable(), str(Path(project.__file__)), "init", "--video", str(source),
                       "--version", "V1", "--project", "typed", "--out", str(state), "--preset", str(preset_path)]
            subprocess.run(command, check=True, capture_output=True)
            version = project.load_state(state)["versions"]["V1"]
            self.assertEqual(version["fps"], "30000/1001")
            self.assertEqual(version["materials_policy"], policy)
            self.assertEqual(version["materials_policy_source"], {
                "preset_id": "typed-cathy-project",
                "preset": {"path": str(preset_path.resolve()), "sha256": project.sha256(preset_path)}})
            self.assertNotIn("playback", version)
            self.assertNotIn("canvas", version)
            state_before = state.read_bytes()
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("State already exists", result.stderr)
            self.assertEqual(state.read_bytes(), state_before)
            self.assertEqual(project.sha256(source), source_hash)

    def test_init_rejects_mixed_or_partial_typed_preset_without_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, preset_path = root / "source.mp4", root / "preset.json"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=30:d=1",
                            "-c:v", "libx264", str(source)], check=True)
            for i, policy in enumerate(({"static_fullscreen_max_seconds": 4},
                                         {"video_max_seconds": 15},
                                         {"fullscreen_max_seconds": 4, "static_fullscreen_max_seconds": 4,
                                          "video_max_seconds": 15})):
                with self.subTest(policy=policy):
                    state = root / f"state-{i}.json"
                    project.write_json(preset_path, {"id": "invalid-typed-project", "materials": policy})
                    result = subprocess.run([sys_executable(), str(Path(project.__file__)), "init", "--video", str(source),
                                             "--version", "V1", "--project", "invalid", "--out", str(state),
                                             "--preset", str(preset_path)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2)
                    self.assertFalse(state.exists())


def sys_executable():
    import sys
    return sys.executable


if __name__ == "__main__":
    unittest.main(verbosity=2)
