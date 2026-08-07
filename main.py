"""命令行抓取 QQ 空间说说并保存到本地。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from qzone_scraper import (
    build_snapshot,
    cookie_header,
    download_snapshot_media,
    normalise_qq,
    save_archive_html,
    save_snapshot,
    scrape_albums,
    scrape_messages,
)


def _read_session(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读取 session 失败：{exc}，将重新扫码登录。", file=sys.stderr)
        return None
    if not isinstance(data, dict) or not isinstance(data.get("cookies"), dict):
        print("session 文件缺少 cookies 字段，将重新扫码登录。", file=sys.stderr)
        return None
    if data.get("bkn") is None or data.get("qq") is None:
        print("session 文件缺少 qq/bkn 字段，将重新扫码登录。", file=sys.stderr)
        return None
    return data


async def login_with_cache(session_path: Path) -> Dict[str, Any]:
    """优先复用本地 session；缓存失效时走已有的扫码登录流程。"""

    # 延迟导入，让 `python3 main.py --help` 在未安装运行依赖时也可用。
    from qzone_api import QzoneApi, QzoneLogin

    cached = _read_session(session_path)
    if cached:
        try:
            qq = normalise_qq(cached["qq"])
            cookies = cookie_header(cached["cookies"])
            probe = await QzoneApi().get_messages_list(
                target_qq=qq, g_tk=int(cached["bkn"]), cookies=cookies, pos=0, num=1
            )
            if isinstance(probe, dict) and probe.get("status") != "error":
                print("已复用本地 session。")
                return cached
            print("本地 session 已失效，将重新扫码登录。", file=sys.stderr)
        except Exception as exc:
            print(f"验证本地 session 失败：{exc}，将重新扫码登录。", file=sys.stderr)

    result = await QzoneLogin().login()
    if result.get("code") != 0:
        raise RuntimeError(result.get("msg", "扫码登录失败"))
    session = {
        "qq": result["qq"],
        "cookies": result["cookies"],
        "skey": result.get("skey"),
        "bkn": result["bkn"],
    }
    session_path.parent.mkdir(parents=True, exist_ok=True)
    with session_path.open("w", encoding="utf-8") as handle:
        json.dump(session, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"扫码登录成功，session 已保存到 {session_path}")
    return session


def _add_output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", type=Path, default=Path("backups"), help="备份根目录")
    parser.add_argument("--output", type=Path, help="单目标 JSON 输出路径；HTML 使用同名 .html")
    parser.add_argument("--format", choices=("all", "json", "html"), default="all", help="导出格式")
    parser.add_argument("--session", type=Path, default=Path("qzone_session.json"), help="登录缓存路径")
    parser.add_argument("--delay", type=float, default=0.5, help="分页请求间隔秒数（默认 0.5）")
    parser.add_argument("--no-media", action="store_true", help="只保留图片 URL，不下载图片文件")
    parser.add_argument("--media-concurrency", type=int, default=6, help="图片并发下载数（默认 6）")


def _add_mood_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--page-size", type=int, default=20, help="每页说说条数（默认 20）")
    parser.add_argument("--max-pages", type=int, help="最多抓取多少页说说")


def _add_album_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--max-albums", type=int, help="最多备份多少个相册")
    parser.add_argument("--max-photo-pages", type=int, help="每个相册最多抓取多少页照片")
    parser.add_argument("--album", dest="album_names", action="append", help="只备份指定名称的相册，可重复")
    parser.set_defaults(interactive_select_albums=False)


def _add_backup_leaf(
    subparsers,
    name: str,
    help_text: str,
    *,
    scope: str,
    content: str,
) -> argparse.ArgumentParser:
    leaf = subparsers.add_parser(name, help=help_text, description=help_text)
    leaf.set_defaults(scope=scope, content=content, command="backup")
    if scope == "user":
        leaf.add_argument("targets", nargs="+", metavar="QQ", help="一个或多个目标 QQ，可用逗号分隔")
    _add_output_options(leaf)
    if content in ("moods", "all"):
        _add_mood_options(leaf)
    if content in ("albums", "all"):
        _add_album_options(leaf)
    return leaf


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qzone-archive",
        description="多功能 QQ 空间 CLI：分别备份自己/他人的说说与相册",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.5.3")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    commands.add_parser("menu", help="打开交互式选择菜单")

    self_parser = commands.add_parser("self", help="备份登录账号自己的空间")
    self_commands = self_parser.add_subparsers(dest="content", metavar="CONTENT", required=True)
    _add_backup_leaf(self_commands, "moods", "备份自己的说说", scope="self", content="moods")
    _add_backup_leaf(self_commands, "albums", "备份自己的相册", scope="self", content="albums")
    _add_backup_leaf(self_commands, "all", "备份自己的说说和相册", scope="self", content="all")

    user_parser = commands.add_parser("user", help="备份其他可访问的 QQ 空间")
    user_commands = user_parser.add_subparsers(dest="content", metavar="CONTENT", required=True)
    _add_backup_leaf(user_commands, "moods", "备份他人的说说", scope="user", content="moods")
    _add_backup_leaf(user_commands, "albums", "备份他人的相册", scope="user", content="albums")
    _add_backup_leaf(user_commands, "all", "备份他人的说说和相册", scope="user", content="all")

    legacy = commands.add_parser("backup", help="兼容入口：一键备份说说和相册")
    legacy.set_defaults(scope="legacy", content="all")
    legacy.add_argument("--target", action="append", help="目标 QQ；省略时使用登录账号")
    _add_output_options(legacy)
    _add_mood_options(legacy)
    _add_album_options(legacy)

    login_parser = commands.add_parser("login", help="扫码登录或验证已有 session")
    login_parser.add_argument("--session", type=Path, default=Path("qzone_session.json"))

    status_parser = commands.add_parser("status", help="查看本地 session 状态，不发起网络请求")
    status_parser.add_argument("--session", type=Path, default=Path("qzone_session.json"))

    render_parser = commands.add_parser("render", help="把已有 archive.json 重新渲染为 HTML")
    render_parser.add_argument("source", type=Path, help="已有 JSON 快照")
    render_parser.add_argument("--output", type=Path, help="HTML 输出路径")
    return parser


MENU_ACTIONS = {
    "1": ("self", "moods", "备份自己的说说"),
    "2": ("user", "moods", "备份别人的说说"),
    "3": ("self", "albums", "备份自己的相册"),
    "4": ("user", "albums", "备份别人的相册"),
    "5": ("self", "all", "备份自己的说说和相册"),
    "6": ("user", "all", "备份别人的说说和相册"),
}


def _ask(input_func, prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input_func(f"{prompt}{suffix}：").strip()
    return value or default


def _ask_choice(input_func, output_func, prompt: str, choices, default: str) -> str:
    while True:
        value = _ask(input_func, prompt, default)
        if value in choices:
            return value
        output_func(f"请输入：{' / '.join(choices)}")


def _ask_positive_int(input_func, output_func, prompt: str) -> Optional[str]:
    while True:
        value = _ask(input_func, prompt)
        if not value:
            return None
        if value.isdigit() and int(value) > 0:
            return value
        output_func("请输入大于 0 的整数，直接回车表示不限制。")


def _ask_targets(input_func, output_func) -> str:
    while True:
        value = _ask(input_func, "请输入目标 QQ；多个 QQ 用空格或逗号分隔")
        if not value:
            output_func("目标 QQ 不能为空。")
            continue
        parts = value.replace(",", " ").split()
        try:
            for part in parts:
                normalise_qq(part)
        except ValueError as exc:
            output_func(str(exc))
            continue
        return ",".join(parts)


def interactive_args(input_func=None, output_func=print) -> Optional[argparse.Namespace]:
    """通过中文交互向导构造与参数 CLI 相同的 Namespace。"""

    input_func = input if input_func is None else input_func
    output_func("\n" + "=" * 54)
    output_func(" Qzone Archive 0.5.3 · QQ 空间本地备份")
    output_func("=" * 54)
    output_func("  1. 备份自己的说说")
    output_func("  2. 备份别人的说说")
    output_func("  3. 备份自己的相册")
    output_func("  4. 备份别人的相册")
    output_func("  5. 备份自己的说说和相册")
    output_func("  6. 备份别人的说说和相册")
    output_func("  7. 扫码登录 / 验证登录")
    output_func("  8. 查看本地登录状态")
    output_func("  9. 从 JSON 重新生成 HTML")
    output_func("  0. 退出")

    choice = _ask_choice(input_func, output_func, "请选择功能", tuple("0123456789"), "1")
    if choice == "0":
        return None
    parser = build_parser()
    if choice == "7":
        return parser.parse_args(["login"])
    if choice == "8":
        return parser.parse_args(["status"])
    if choice == "9":
        source = _ask(input_func, "请输入 archive.json 路径")
        while not source:
            output_func("JSON 路径不能为空。")
            source = _ask(input_func, "请输入 archive.json 路径")
        output = _ask(input_func, "HTML 输出路径；直接回车使用同名 .html")
        arguments = ["render", source]
        if output:
            arguments.extend(["--output", output])
        return parser.parse_args(arguments)

    scope, content, label = MENU_ACTIONS[choice]
    output_func(f"\n已选择：{label}")
    arguments = [scope, content]
    if scope == "user":
        arguments.append(_ask_targets(input_func, output_func))

    output_dir = _ask(input_func, "备份保存目录", "backups")
    arguments.extend(["--output-dir", output_dir])

    if content == "albums":
        output_func(
            "接下来会显示相册列表，请选择要备份的相册。程序将下载原图/视频并生成 HTML，"
            "照片按拍摄时间自动分类（无时间信息的文件放入“未分类”）。"
        )
        arguments.extend(["--format", "html"])
        parsed = parser.parse_args(arguments)
        parsed.interactive_select_albums = True
        parsed._input_func = input_func
        parsed._output_func = output_func
        return parsed

    output_func("导出格式：1. JSON + HTML  2. 仅 HTML  3. 仅 JSON")
    format_choice = _ask_choice(input_func, output_func, "请选择导出格式", ("1", "2", "3"), "1")
    format_value = {"1": "all", "2": "html", "3": "json"}[format_choice]
    arguments.extend(["--format", format_value])

    media_choice = _ask_choice(input_func, output_func, "是否下载照片到本地？1. 是  2. 否", ("1", "2"), "1")
    if media_choice == "2":
        arguments.append("--no-media")

    if content in ("moods", "all"):
        max_pages = _ask_positive_int(input_func, output_func, "最多抓取多少页说说；回车表示全部")
        if max_pages:
            arguments.extend(["--max-pages", max_pages])
    if content in ("albums", "all"):
        select_choice = _ask_choice(
            input_func,
            output_func,
            "拉取列表后手动选择相册？1. 选择  2. 全部",
            ("1", "2"),
            "1",
        )
        max_albums = _ask_positive_int(input_func, output_func, "最多备份多少个相册；回车表示全部")
        if max_albums:
            arguments.extend(["--max-albums", max_albums])
        max_photo_pages = _ask_positive_int(
            input_func, output_func, "每个相册最多抓取多少页照片；回车表示全部"
        )
        if max_photo_pages:
            arguments.extend(["--max-photo-pages", max_photo_pages])
    parsed = parser.parse_args(arguments)
    if content in ("albums", "all"):
        parsed.interactive_select_albums = select_choice == "1"
        parsed._input_func = input_func
        parsed._output_func = output_func
    return parsed


def interactive_loop(input_func=None, output_func=print, runner=None) -> int:
    """持续显示菜单，完成一项操作后返回主菜单。"""

    input_func = input if input_func is None else input_func
    runner = run if runner is None else runner
    while True:
        try:
            args = interactive_args(input_func=input_func, output_func=output_func)
            if args is None:
                output_func("已退出。")
                return 0
            asyncio.run(runner(args))
            output_func("\n操作完成，已返回主菜单。")
        except (EOFError, KeyboardInterrupt):
            output_func("\n已退出。")
            return 130
        except Exception as exc:
            output_func(f"\n操作出错：{exc}")


def _target_list(values, owner_qq: int):
    if not values:
        return [owner_qq]
    targets = []
    seen = set()
    for value in values:
        for part in str(value).split(","):
            target = normalise_qq(part)
            if target not in seen:
                seen.add(target)
                targets.append(target)
    return targets


def select_albums_interactively(albums, input_func=None, output_func=print):
    """显示服务端相册列表，返回用户选中的相册 ID；空列表表示全部。"""

    input_func = input if input_func is None else input_func
    output_func("\n可备份的相册：")
    for index, album in enumerate(albums, 1):
        name = str(album.get("name") or "未命名相册")
        count = int(album.get("photo_count", 0) or 0)
        access = "可访问" if int(album.get("allow_access", 1) or 0) else "无权限"
        output_func(f"  {index:>3}. {name}（{count} 项，{access}）")
    output_func("输入编号选择，多个编号用逗号分隔；直接回车备份全部。")
    while True:
        raw = _ask(input_func, "相册编号")
        if not raw:
            return None
        values = raw.replace("，", ",").replace(" ", ",").split(",")
        try:
            indices = sorted({int(value) for value in values if value})
        except ValueError:
            output_func("请输入相册编号，例如：1,3,5")
            continue
        if not indices or any(index < 1 or index > len(albums) for index in indices):
            output_func(f"编号范围应为 1–{len(albums)}。")
            continue
        selected = [albums[index - 1] for index in indices]
        locked = [album for album in selected if not int(album.get("allow_access", 1) or 0)]
        if locked:
            output_func("已自动忽略无访问权限的相册。")
        return [str(album.get("id")) for album in selected if int(album.get("allow_access", 1) or 0)]


async def run(args: argparse.Namespace, *, login_func=login_with_cache, api_factory=None):
    if args.command == "status":
        session = _read_session(args.session)
        if not session:
            print(f"未找到可用的本地 session：{args.session}")
            return []
        print(f"本地 session：QQ {normalise_qq(session['qq'])}，路径 {args.session.resolve()}")
        return []

    if args.command == "render":
        with args.source.open("r", encoding="utf-8") as handle:
            snapshot = json.load(handle)
        output = args.output or args.source.with_suffix(".html")
        destination = save_archive_html(snapshot, output)
        print(f"HTML 已生成：{destination.resolve()}")
        return [destination]

    session = await login_func(args.session)
    owner_qq = normalise_qq(session["qq"])
    if args.command == "login":
        print(f"登录状态正常：QQ {owner_qq}")
        return []

    if args.scope == "self":
        targets = [owner_qq]
    elif args.scope == "user":
        targets = _target_list(args.targets, owner_qq)
    else:
        targets = _target_list(args.target, owner_qq)
    if args.output and len(targets) != 1:
        raise ValueError("--output 只适用于单个目标；多目标请使用 --output-dir")

    if api_factory is None:
        from qzone_api import QzoneApi

        api_factory = QzoneApi

    api = api_factory()
    cookies = cookie_header(session["cookies"])
    destinations = []
    include_moods = args.content in ("moods", "all")
    include_albums = args.content in ("albums", "all")
    for target_qq in targets:
        print(f"\n开始备份 QQ {target_qq}：{args.content}")

        def progress(page: int, position: int, count: int) -> None:
            print(f"  说说第 {page} 页（pos={position}）新增 {count} 条")

        feeds = []
        if include_moods:
            feeds = await scrape_messages(
                api,
                target_qq,
                int(session["bkn"]),
                cookies,
                page_size=args.page_size,
                max_pages=args.max_pages,
                delay=args.delay,
                on_page=progress,
            )
        albums = []
        album_error = None
        if include_albums:
            try:
                album_selector = None
                if getattr(args, "interactive_select_albums", False):
                    album_selector = lambda items: select_albums_interactively(
                        items,
                        input_func=getattr(args, "_input_func", None),
                        output_func=getattr(args, "_output_func", print),
                    )
                albums = await scrape_albums(
                    api,
                    target_qq,
                    int(session["bkn"]),
                    cookies,
                    login_qq=owner_qq,
                    max_albums=args.max_albums,
                    max_photo_pages=args.max_photo_pages,
                    album_names=args.album_names,
                    album_selector=album_selector,
                    delay=args.delay,
                    on_album=lambda index, total, name, count: print(
                        f"  相册 {index}/{total}《{name}》获取 {count} 张照片"
                    ),
                )
            except Exception as exc:
                album_error = str(exc)
                print(f"  相册备份未完成：{exc}", file=sys.stderr)

        included = []
        if include_moods:
            included.append("moods")
        if include_albums:
            included.append("albums")
        snapshot = build_snapshot(target_qq, feeds, albums, included=included)
        if album_error:
            snapshot["album_error"] = album_error

        if args.output:
            json_path = args.output
            html_path = args.output.with_suffix(".html")
            media_dir = args.output.parent / f"{args.output.stem}_media"
        else:
            target_dir = args.output_dir / str(target_qq) / args.content
            json_path = target_dir / "archive.json"
            html_path = target_dir / "index.html"
            media_dir = target_dir / "media"

        if not args.no_media:
            media_cookie_builder = getattr(api, "album_media_cookies", None)
            media_cookies = media_cookie_builder(cookies) if media_cookie_builder else cookies
            snapshot, media_report = await download_snapshot_media(
                snapshot,
                media_dir,
                cookies=media_cookies,
                concurrency=args.media_concurrency,
            )
            print(
                "  图片下载："
                f"新增 {media_report['downloaded']}，复用 {media_report['skipped']}，"
                f"失败 {media_report['failed']}"
            )
            snapshot["media_report"] = media_report

        if args.format in ("all", "json"):
            destinations.append(save_snapshot(snapshot, json_path))
        if args.format in ("all", "html"):
            destinations.append(save_archive_html(snapshot, html_path))
        print(f"QQ {target_qq} 备份完成：{len(feeds)} 条说说，{len(albums)} 个相册")
        for destination in destinations[-2:]:
            if destination in (json_path, html_path):
                print(f"  {destination.resolve()}")
    return destinations


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        return interactive_loop()
    args = build_parser().parse_args(arguments)
    if args.command == "menu":
        return interactive_loop()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"抓取失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
