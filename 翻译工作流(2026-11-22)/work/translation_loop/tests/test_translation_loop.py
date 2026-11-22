from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "translation_loop.py"
spec = importlib.util.spec_from_file_location("translation_loop", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load {MODULE_PATH}")
tl = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = tl
spec.loader.exec_module(tl)

REQUIRED_SOURCES = (
    "c100001.txt",
    "c100001_2.txt",
    "c130901.txt",
    "c150051.txt",
    "c154413.txt",
)


def setUpModule():
    missing = [name for name in REQUIRED_SOURCES if not (tl.SOURCE_ROOT / name).is_file()]
    if missing:
        raise unittest.SkipTest(
            "source fixtures not included; place the original scene files under FlowerKnightGirl_原文/ "
            "and set FKG_GAME_SCENES")
    if not tl.DEFAULT_GAME_SCENES.is_dir():
        raise unittest.SkipTest(
            "game scenes not found; set FKG_GAME_SCENES to package.nw/scenes")


class BuildSceneTests(unittest.TestCase):
    def test_all_preflight_overrides_build_with_one_preserved_line(self) -> None:
        overrides = tl.load_overrides()
        self.assertEqual(set(overrides), {"c130901", "c131925_2", "c144403", "c147501_2", "c162701"})
        for scene_id, info in overrides.items():
            scene = tl.build_scene(scene_id)
            self.assertEqual(scene.total_lines, info["game_blocks"], scene_id)
            preserved = [u.line for u in scene.units if u.action == "preserve"]
            self.assertEqual(preserved, info["extra_game_lines_1based"], scene_id)
            self.assertEqual(scene.units[preserved[0] - 1].action, "preserve")
            self.assertEqual(sum(1 for u in scene.units if u.action == "translate"), info["source_blocks"], scene_id)

    def test_normal_scene_has_exact_game_line_count(self) -> None:
        scene = tl.build_scene("c100001")
        self.assertEqual(scene.total_lines, 88)
        self.assertEqual(len(scene.units), 88)
        self.assertTrue(all(u.action == "translate" for u in scene.units))


class WindowTests(unittest.TestCase):
    def test_history_pairs_and_lookahead_are_independent(self) -> None:
        scene = tl.build_scene("c100001")
        state = tl.new_state(scene, history_pairs=4, lookahead=0)
        self.assertEqual(tl.select_history(scene, state), [])
        self.assertEqual(tl.select_future(scene, state), [])
        self.assertEqual(tl.unit_by_line(scene)[1].line, 1)

        state["accepted"].append({
            "line": 1,
            "action": "translate",
            "speaker": "忍冬",
            "text": "测试译文1",
            "source_hash": "x",
            "accepted_at": "now",
        })
        state["next_line"] = 2
        history = tl.select_history(scene, state)
        self.assertEqual([u.line for u, _ in history], [1])
        state["history_pairs"] = 5
        state["lookahead"] = 2
        self.assertEqual([u.line for u in tl.select_future(scene, state)], [3, 4])

    def test_strict_mode_prompt_has_four_completed_pairs_plus_current(self) -> None:
        scene = tl.build_scene("c100001")
        state = tl.new_state(scene, history_pairs=4, lookahead=0)
        for line in range(1, 5):
            state["accepted"].append({
                "line": line,
                "action": "translate",
                "speaker": "忍冬" if line % 2 else "",
                "text": f"测试译文{line}",
                "source_hash": "x",
                "accepted_at": "now",
            })
        state["next_line"] = 5
        prompt, unit = tl.build_prompt(scene, state)
        self.assertEqual(unit.line, 5)
        self.assertIn("已定稿历史 pair: 4", prompt)
        self.assertIn("第 4 行 译文：", prompt)
        self.assertNotIn("第 0 行 译文：", prompt)
        self.assertNotIn("# 后文参考", prompt)

    def test_quality_mode_prompt_includes_future_reference(self) -> None:
        scene = tl.build_scene("c100001")
        state = tl.new_state(scene, history_pairs=5, lookahead=2)
        state["next_line"] = 1
        prompt, unit = tl.build_prompt(scene, state)
        self.assertEqual(unit.line, 1)
        self.assertIn("# 后文参考", prompt)
        self.assertIn("第 2 行：", prompt)
        self.assertIn("第 3 行：", prompt)
        self.assertNotIn("第 4 行：", prompt)

    def test_prompt_is_sectioned_and_marks_only_one_current_line(self) -> None:
        scene = tl.build_scene("c100001")
        state = tl.new_state(scene, history_pairs=4, lookahead=0)
        prompt, unit = tl.build_prompt(scene, state)
        self.assertEqual(unit.line, 1)
        for section in (
            "# 场景锚点",
            "# 人名与术语",
            "# 已定稿对话",
            "# 当前原文",
            "# 本次任务",
            "# 输出协议",
            "# 输出前自检",
        ):
            self.assertIn(section, prompt)
        self.assertIn(">> 第 1 行：", prompt)
        self.assertIn("只翻译第 1 行", prompt)
        self.assertIn("只输出一个 JSON 对象", prompt)

    def test_prompt_has_version_family_and_continuity_context(self) -> None:
        scene = tl.build_scene("c100001_2")
        state = tl.new_state(scene, history_pairs=5, lookahead=2)
        state["rolling_summary"] = "该角色在上一场景已与团长建立亲密关系。"
        prompt, unit = tl.build_prompt(scene, state)
        self.assertEqual(unit.line, 1)
        self.assertIn(f"prompt_version: `{tl.PROMPT_VERSION}`", prompt)
        self.assertIn("场景家族: `c100001`", prompt)
        self.assertIn("当前为 `_2` 变体", prompt)
        self.assertIn("# 角色与连续性", prompt)
        self.assertIn("上一场景已与团长", prompt)

    def test_prompt_contains_terms_and_character_address_policy(self) -> None:
        scene = tl.build_scene("c154413")
        state = tl.new_state(scene, history_pairs=5, lookahead=2)
        prompt, _ = tl.build_prompt(scene, state)
        self.assertIn("# 术语", prompt)
        self.assertIn("膣内", prompt)
        self.assertIn("小穴里", prompt)
        self.assertIn("# 角色称呼策略", prompt)
        self.assertIn("団長様 -> 团长大人", prompt)
        self.assertIn("terms_version:", prompt)
        self.assertIn("characters_version:", prompt)
        self.assertIn("style_version:", prompt)

    def test_prompt_includes_off_window_scene_names(self) -> None:
        # c150051 has アオ and シロ, plus composite name-plate variants.
        # At line 1 only 白 is the current speaker; the mapping must still
        # include 青 because the scene mentions/uses that name elsewhere.
        scene = tl.build_scene("c150051")
        state = tl.new_state(scene, history_pairs=5, lookahead=2)
        prompt, unit = tl.build_prompt(scene, state)
        self.assertEqual(unit.line, 1)
        self.assertIn("`シロ` -> `白`", prompt)
        self.assertIn("`アオ` -> `青`", prompt)


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scene = tl.build_scene("c100001")
        self.unit = self.scene.units[0]

    def test_valid_json_passes(self) -> None:
        raw = json.dumps({"line": self.unit.line, "speaker": self.unit.speaker_zh, "text": "测试译文"}, ensure_ascii=False)
        result = tl.validate_model_output(raw, self.unit)
        self.assertEqual(result["line"], 1)
        self.assertEqual(result["speaker"], "忍冬")

    def test_wrong_line_fails(self) -> None:
        raw = json.dumps({"line": 2, "speaker": self.unit.speaker_zh, "text": "测试译文"}, ensure_ascii=False)
        with self.assertRaises(tl.ValidationError):
            tl.validate_model_output(raw, self.unit)

    def test_wrong_speaker_fails(self) -> None:
        raw = json.dumps({"line": self.unit.line, "speaker": "错误名字", "text": "测试译文"}, ensure_ascii=False)
        with self.assertRaises(tl.ValidationError):
            tl.validate_model_output(raw, self.unit)

    def test_forbidden_tag_fails(self) -> None:
        raw = json.dumps({"line": self.unit.line, "speaker": self.unit.speaker_zh, "text": "<PAUSE>"}, ensure_ascii=False)
        with self.assertRaises(tl.ValidationError):
            tl.validate_model_output(raw, self.unit)

    def test_real_newline_fails(self) -> None:
        raw = json.dumps({"line": self.unit.line, "speaker": self.unit.speaker_zh, "text": "第一行\n第二行"}, ensure_ascii=False)
        with self.assertRaises(tl.ValidationError):
            tl.validate_model_output(raw, self.unit)

    def test_markdown_fence_fails(self) -> None:
        raw = "```json\n" + json.dumps({"line": self.unit.line, "speaker": self.unit.speaker_zh, "text": "测试译文"}, ensure_ascii=False) + "\n```"
        with self.assertRaises(tl.ValidationError):
            tl.validate_model_output(raw, self.unit)

    def test_repeated_speaker_prefix_fails(self) -> None:
        raw = json.dumps(
            {"line": self.unit.line, "speaker": self.unit.speaker_zh, "text": f"{self.unit.speaker_zh}: 重复名字"},
            ensure_ascii=False,
        )
        with self.assertRaises(tl.ValidationError):
            tl.validate_model_output(raw, self.unit)

    def test_japanese_only_term_is_normalized(self) -> None:
        raw = json.dumps(
            {"line": self.unit.line, "speaker": self.unit.speaker_zh, "text": "龟头埋进了膣内"},
            ensure_ascii=False,
        )
        result = tl.validate_model_output(raw, self.unit)
        self.assertIn("小穴里", result["text"])
        self.assertNotIn("膣", result["text"])

    def test_excessive_same_character_repetition_fails(self) -> None:
        raw = json.dumps(
            {"line": self.unit.line, "speaker": self.unit.speaker_zh, "text": "啊" * 40},
            ensure_ascii=False,
        )
        with self.assertRaises(tl.ValidationError):
            tl.validate_model_output(raw, self.unit)

    def test_raw_truncated_repetition_fails_before_json_parse(self) -> None:
        raw = '{"line": 1, "speaker": "忍冬", "text": "' + "了" * 40
        with self.assertRaises(tl.ValidationError):
            tl.validate_model_output(raw, self.unit)

    def test_source_quoted_speaker_gets_outer_quotes(self) -> None:
        raw = json.dumps(
            {"line": self.unit.line, "speaker": self.unit.speaker_zh, "text": "测试译文"},
            ensure_ascii=False,
        )
        result = tl.validate_model_output(raw, self.unit)
        self.assertEqual(result["text"], "「测试译文」")

    def test_unquoted_source_strips_outer_quotes(self) -> None:
        unit = tl.Unit(
            line=1,
            action="translate",
            speaker_ja="スイカズラ",
            speaker_zh="忍冬",
            source_text="テスト",
            source_hash="x",
        )
        raw = json.dumps(
            {"line": 1, "speaker": "忍冬", "text": "「测试译文」"},
            ensure_ascii=False,
        )
        result = tl.validate_model_output(raw, unit)
        self.assertEqual(result["text"], "测试译文")

    def test_narration_with_colon_in_sentence_passes(self) -> None:
        unit = tl.Unit(
            line=1,
            action="translate",
            speaker_ja="",
            speaker_zh="",
            source_text="彼女は口を開く。",
            source_hash="x",
        )
        raw = json.dumps(
            {"line": 1, "speaker": "", "text": "她开口道：果然如此。"},
            ensure_ascii=False,
        )
        result = tl.validate_model_output(raw, unit)
        self.assertEqual(result["text"], "她开口道，果然如此。")

    def test_narration_with_known_name_prefix_fails(self) -> None:
        unit = tl.Unit(
            line=1,
            action="translate",
            speaker_ja="",
            speaker_zh="",
            source_text="彼女は口を開く。",
            source_hash="x",
        )
        raw = json.dumps(
            {"line": 1, "speaker": "", "text": "忍冬: 她开口道。"},
            ensure_ascii=False,
        )
        with self.assertRaises(tl.ValidationError):
            tl.validate_model_output(raw, unit)


class FullRunTests(unittest.TestCase):
    def test_full_override_scene_runs_and_reviews_cleanly(self) -> None:
        scene = tl.build_scene("c130901")
        with tempfile.TemporaryDirectory(prefix="fkg-loop-test-") as tmp:
            run_root = Path(tmp)
            state = tl.new_state(scene, history_pairs=4, lookahead=0)
            tl.save_state(run_root, state)
            tl.write_draft(scene, state, run_root)
            translator = tl.MockTranslator()
            for _ in range(200):
                result = tl.step_scene(scene, state, run_root, translator)
                if result["status"] == "completed":
                    break
            else:
                self.fail("scene did not complete")
            report = tl.review_scene(scene, state, run_root)
            self.assertTrue(report["complete"])
            self.assertEqual(report["issues"], [])
            self.assertEqual(report["total_lines"], 74)
            self.assertEqual(report["translated_lines"], 73)
            self.assertEqual(report["preserved_lines"], 1)
            draft_lines = (run_root / "c130901" / "draft.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(draft_lines), 74)
            self.assertEqual(draft_lines[9], "")
            self.assertTrue(draft_lines[0].startswith("黄花九轮草: "))


class RetryTests(unittest.TestCase):
    class WrongThenRight:
        def __init__(self) -> None:
            self.calls = 0

        def translate(self, prompt: str, unit: tl.Unit) -> str:
            self.calls += 1
            line = unit.line + 1 if self.calls == 1 else unit.line
            return json.dumps({"line": line, "speaker": unit.speaker_zh, "text": "测试译文"}, ensure_ascii=False)

    def test_rejection_does_not_advance_and_next_attempt_can_accept(self) -> None:
        scene = tl.build_scene("c100001")
        with tempfile.TemporaryDirectory(prefix="fkg-loop-retry-") as tmp:
            run_root = Path(tmp)
            state = tl.new_state(scene, history_pairs=4, lookahead=0)
            tl.save_state(run_root, state)
            translator = self.WrongThenRight()
            first = tl.step_scene(scene, state, run_root, translator)
            self.assertEqual(first["status"], "rejected")
            self.assertEqual(state["next_line"], 1)
            self.assertEqual(state["retries"], 1)
            self.assertEqual(len(state["accepted"]), 0)
            second = tl.step_scene(scene, state, run_root, translator)
            self.assertEqual(second["status"], "running")
            self.assertEqual(state["next_line"], 2)
            self.assertEqual(len(state["accepted"]), 1)
            self.assertEqual(state["retries"], 0)
            self.assertIsNone(state["last_error"])


if __name__ == "__main__":
    unittest.main()
