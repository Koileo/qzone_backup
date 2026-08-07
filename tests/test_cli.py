import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from main import build_parser, interactive_args, interactive_loop, run, select_albums_interactively


class FakeCliApi:
    def __init__(self):
        self.message_targets = []
        self.album_targets = []
        self.photo_targets = []

    async def get_messages_list(self, target_qq, g_tk, cookies, pos=0, num=20):
        self.message_targets.append(target_qq)
        return {"status": "ok", "data": []}

    async def get_album_list(self, target_qq, g_tk, cookies, page=0, count=100, login_qq=None):
        self.album_targets.append(target_qq)
        return {
            "status": "ok",
            "data": [{"id": "a1", "name": "fixture", "photo_count": 0, "allow_access": 1}],
        }

    async def get_album_photos(
        self, target_qq, album_id, g_tk, cookies, start=0, count=100, login_qq=None
    ):
        self.photo_targets.append(target_qq)
        return {"status": "ok", "total": 0, "data": []}


class FakeFilteredCliApi(FakeCliApi):
    async def get_messages_list(self, target_qq, g_tk, cookies, pos=0, num=20):
        self.message_targets.append(target_qq)
        return {
            "status": "ok",
            "total_available": 2,
            "data": [
                {"cur_key": "original", "content": "自己发的", "repost": None},
                {
                    "cur_key": "repost",
                    "content": "转发语",
                    "repost": {"content": "原说说"},
                },
            ],
        }


async def fake_login(_path):
    return {"qq": "o999", "bkn": 123, "cookies": {"skey": "fixture"}}


class CliMatrixTests(unittest.TestCase):
    def _run_command(self, command, expected_dir):
        with tempfile.TemporaryDirectory() as directory:
            parser = build_parser()
            args = parser.parse_args(
                command
                + [
                    "--output-dir",
                    directory,
                    "--format",
                    "json",
                    "--no-media",
                    "--delay",
                    "0",
                ]
            )
            api = FakeCliApi()
            destinations = asyncio.run(
                run(args, login_func=fake_login, api_factory=lambda: api)
            )
            output = Path(directory) / expected_dir / "archive.json"
            self.assertEqual(destinations, [output])
            self.assertTrue(output.is_file())
            saved = json.loads(output.read_text(encoding="utf-8"))
            return api, saved

    def test_self_moods_only_calls_mood_api(self):
        api, saved = self._run_command(["self", "moods"], "999/moods")
        self.assertEqual(api.message_targets, [999])
        self.assertEqual(api.album_targets, [])
        self.assertEqual(saved["included"], ["moods"])

    def test_user_moods_uses_requested_target(self):
        api, saved = self._run_command(["user", "moods", "123"], "123/moods")
        self.assertEqual(api.message_targets, [123])
        self.assertEqual(api.album_targets, [])
        self.assertEqual(saved["target_qq"], "123")

    def test_mood_type_filters_exported_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            args = build_parser().parse_args(
                [
                    "self",
                    "moods",
                    "--mood-type",
                    "repost",
                    "--output-dir",
                    directory,
                    "--format",
                    "json",
                    "--no-media",
                    "--delay",
                    "0",
                ]
            )
            destinations = asyncio.run(
                run(args, login_func=fake_login, api_factory=FakeFilteredCliApi)
            )
            saved = json.loads(destinations[0].read_text(encoding="utf-8"))
            self.assertEqual(saved["total"], 1)
            self.assertEqual(saved["data"][0]["cur_key"], "repost")

    def test_self_albums_only_calls_album_api(self):
        api, saved = self._run_command(["self", "albums"], "999/albums")
        self.assertEqual(api.message_targets, [])
        self.assertEqual(api.album_targets, [999])
        self.assertEqual(api.photo_targets, [999])
        self.assertEqual(saved["included"], ["albums"])

    def test_user_albums_uses_requested_target(self):
        api, saved = self._run_command(["user", "albums", "456"], "456/albums")
        self.assertEqual(api.message_targets, [])
        self.assertEqual(api.album_targets, [456])
        self.assertEqual(api.photo_targets, [456])
        self.assertEqual(saved["target_qq"], "456")

    def test_user_all_supports_multiple_comma_separated_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            args = build_parser().parse_args(
                [
                    "user",
                    "all",
                    "123,456",
                    "--output-dir",
                    directory,
                    "--format",
                    "json",
                    "--no-media",
                    "--delay",
                    "0",
                    "--max-pages",
                    "1",
                    "--max-photo-pages",
                    "1",
                ]
            )
            api = FakeCliApi()
            destinations = asyncio.run(
                run(args, login_func=fake_login, api_factory=lambda: api)
            )
            self.assertEqual(api.message_targets, [123, 456])
            self.assertEqual(api.album_targets, [123, 456])
            self.assertEqual(len(destinations), 2)
            self.assertTrue((Path(directory) / "123/all/archive.json").is_file())
            self.assertTrue((Path(directory) / "456/all/archive.json").is_file())

    def test_render_command_needs_no_login(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "archive.json"
            source.write_text(
                json.dumps(
                    {
                        "target_qq": "123",
                        "fetched_at": "fixture",
                        "total": 0,
                        "data": [],
                        "album_total": 0,
                        "albums": [],
                        "included": ["moods"],
                    }
                ),
                encoding="utf-8",
            )
            args = build_parser().parse_args(["render", str(source)])

            async def forbidden_login(_path):
                raise AssertionError("render 不应登录")

            destinations = asyncio.run(run(args, login_func=forbidden_login))
            self.assertEqual(destinations, [source.with_suffix(".html")])
            html = source.with_suffix(".html").read_text(encoding="utf-8")
            self.assertIn("说说时间线", html)
            self.assertNotIn("相册底片册", html)


class InteractiveMenuTests(unittest.TestCase):
    @staticmethod
    def _inputs(values):
        iterator = iter(values)
        return lambda _prompt: next(iterator)

    def test_user_moods_wizard_collects_target_and_options(self):
        messages = []
        args = interactive_args(
            input_func=self._inputs(["2", "123 456", "", "1", "2", "2", "3"]),
            output_func=messages.append,
        )
        self.assertEqual(args.scope, "user")
        self.assertEqual(args.content, "moods")
        self.assertEqual(args.targets, ["123,456"])
        self.assertEqual(args.output_dir, Path("backups"))
        self.assertEqual(args.format, "html")
        self.assertTrue(args.no_media)
        self.assertEqual(args.max_pages, 3)
        self.assertEqual(args.mood_type, "original")

    def test_self_albums_wizard_selects_albums_and_exports_html(self):
        args = interactive_args(
            input_func=self._inputs(["3", "my-backup"]),
            output_func=lambda _message: None,
        )
        self.assertEqual(args.scope, "self")
        self.assertEqual(args.content, "albums")
        self.assertEqual(args.output_dir, Path("my-backup"))
        self.assertEqual(args.format, "html")
        self.assertFalse(args.no_media)
        self.assertIsNone(args.album_names)
        self.assertTrue(args.interactive_select_albums)
        self.assertIsNotNone(args._input_func)
        self.assertIsNotNone(args._output_func)
        self.assertIsNone(args.max_albums)
        self.assertIsNone(args.max_photo_pages)

    def test_invalid_target_is_reprompted(self):
        messages = []
        args = interactive_args(
            input_func=self._inputs(["4", "abc", "789", ""]),
            output_func=messages.append,
        )
        self.assertEqual(args.targets, ["789"])
        self.assertTrue(any("QQ 号必须" in message for message in messages))

    def test_album_wizard_lists_selection_and_writes_html_without_json(self):
        with tempfile.TemporaryDirectory() as directory:
            messages = []
            args = interactive_args(
                input_func=self._inputs(["3", directory, "1"]),
                output_func=messages.append,
            )
            destinations = asyncio.run(
                run(args, login_func=fake_login, api_factory=FakeCliApi)
            )
            target_dir = Path(directory) / "999/albums"
            self.assertEqual(destinations, [target_dir / "index.html"])
            self.assertTrue((target_dir / "index.html").is_file())
            self.assertFalse((target_dir / "archive.json").exists())
            self.assertTrue(any("fixture" in message for message in messages))

    def test_album_selector_lists_and_selects_accessible_ids(self):
        messages = []
        selected = select_albums_interactively(
            [
                {"id": "a", "name": "旅行", "photo_count": 12, "allow_access": 1},
                {"id": "b", "name": "私密", "photo_count": 8, "allow_access": 0},
                {"id": "c", "name": "日常", "photo_count": 5, "allow_access": 1},
            ],
            input_func=self._inputs(["x", "1,2,3"]),
            output_func=messages.append,
        )
        self.assertEqual(selected, ["a", "c"])
        self.assertTrue(any("旅行" in message for message in messages))
        self.assertTrue(any("忽略无访问权限" in message for message in messages))

    def test_zero_exits_menu(self):
        self.assertIsNone(
            interactive_args(
                input_func=self._inputs(["0"]),
                output_func=lambda _message: None,
            )
        )

    def test_interactive_loop_returns_to_menu(self):
        commands = []

        async def fake_runner(args):
            commands.append(args.command)
            return []

        code = interactive_loop(
            input_func=self._inputs(["8", "0"]),
            output_func=lambda _message: None,
            runner=fake_runner,
        )
        self.assertEqual(code, 0)
        self.assertEqual(commands, ["status"])


if __name__ == "__main__":
    unittest.main()
