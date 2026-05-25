#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
DEFAULT_OUTPUT_ZIP = "matched-player-photos.zip"
DEFAULT_REPORT_CSV = "matched-player-photos-report.csv"


def photo_key(path: Path) -> str:
    if path.name.startswith(".") or path.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        return ""
    return path.stem.strip()


def find_roster_csv(folder: Path, explicit_path: str = "") -> Path:
    if explicit_path:
        roster_path = Path(explicit_path).expanduser()
        if not roster_path.is_absolute():
            roster_path = folder / roster_path
        if roster_path.is_file():
            return roster_path
        raise ValueError(f"队员名单 CSV 不存在：{roster_path}")

    candidates = [
        path
        for path in folder.glob("*.csv")
        if path.name not in {DEFAULT_REPORT_CSV}
        and not path.name.startswith("matched-player-photos-report")
    ]
    if not candidates:
        raise ValueError("当前文件夹没有找到队员名单 CSV。")
    if len(candidates) > 1:
        names = "、".join(path.name for path in candidates)
        raise ValueError(f"当前文件夹有多个 CSV，请用 --roster 指定队员名单：{names}")
    return candidates[0]


def read_roster(roster_path: Path) -> tuple[dict[str, list[dict[str, str]]], list[dict[str, str]]]:
    with roster_path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    players_by_name: dict[str, list[dict[str, str]]] = {}
    normalized_rows: list[dict[str, str]] = []
    for row in rows:
        player_id = str(row.get("player_id") or "").strip()
        display_name = str(row.get("display_name") or "").strip()
        if not player_id or not display_name:
            continue
        normalized = {
            "player_id": player_id,
            "display_name": display_name,
            "team_id": str(row.get("team_id") or "").strip(),
            "team_name": str(row.get("team_name") or "").strip(),
            "appearances": str(row.get("appearances") or "").strip(),
        }
        normalized_rows.append(normalized)
        players_by_name.setdefault(display_name, []).append(normalized)
    if not normalized_rows:
        raise ValueError("队员名单 CSV 里没有可用的 player_id / display_name。")
    return players_by_name, normalized_rows


def list_photo_files(folder: Path, output_zip: Path) -> list[Path]:
    ignored_names = {output_zip.name, DEFAULT_OUTPUT_ZIP, DEFAULT_REPORT_CSV}
    return sorted(
        [
            path
            for path in folder.iterdir()
            if path.is_file()
            and path.name not in ignored_names
            and path.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS
        ],
        key=lambda item: item.name,
    )


def write_report(report_path: Path, rows: list[dict[str, str]]) -> None:
    with report_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["status", "source_file", "matched_player_id", "display_name", "reason"],
        )
        writer.writeheader()
        writer.writerows(rows)


def filter_photos_by_roster(
    folder: Path,
    roster_path: Path,
    output_zip: Path,
    report_path: Path,
) -> tuple[int, int]:
    players_by_name, _rows = read_roster(roster_path)
    used_player_ids: set[str] = set()
    report_rows: list[dict[str, str]] = []
    written_count = 0

    photos = list_photo_files(folder, output_zip)
    with ZipFile(output_zip, "w", compression=ZIP_DEFLATED) as output:
        for photo_path in photos:
            key = photo_key(photo_path)
            candidates = players_by_name.get(key, [])
            if not candidates:
                report_rows.append(
                    {
                        "status": "skipped",
                        "source_file": photo_path.name,
                        "matched_player_id": "",
                        "display_name": key,
                        "reason": "文件名未匹配到已参赛队员姓名",
                    }
                )
                continue
            if len(candidates) > 1:
                report_rows.append(
                    {
                        "status": "skipped",
                        "source_file": photo_path.name,
                        "matched_player_id": "",
                        "display_name": key,
                        "reason": "队员名单中存在同名队员，请手动处理",
                    }
                )
                continue

            player = candidates[0]
            player_id = player["player_id"]
            if player_id in used_player_ids:
                report_rows.append(
                    {
                        "status": "skipped",
                        "source_file": photo_path.name,
                        "matched_player_id": player_id,
                        "display_name": key,
                        "reason": "同一队员已有一张图片入选",
                    }
                )
                continue

            output_name = f"{player_id}{photo_path.suffix.lower()}"
            output.write(photo_path, output_name)
            used_player_ids.add(player_id)
            written_count += 1
            report_rows.append(
                {
                    "status": "included",
                    "source_file": photo_path.name,
                    "matched_player_id": player_id,
                    "display_name": key,
                    "reason": "",
                }
            )

    write_report(report_path, report_rows)
    return written_count, len(report_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "按导出的本赛季队员名单筛选中文名头像。把脚本、队员名单 CSV 和 "
            "中文名.png 放在同一个文件夹后直接运行即可。"
        )
    )
    parser.add_argument(
        "--folder",
        default="",
        help="头像和队员名单所在文件夹；默认使用脚本所在文件夹。",
    )
    parser.add_argument(
        "--roster",
        default="",
        help="队员名单 CSV 文件名；默认自动查找同文件夹唯一 CSV。",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_ZIP,
        help=f"输出 zip 文件名；默认 {DEFAULT_OUTPUT_ZIP}。",
    )
    parser.add_argument(
        "--report",
        default=DEFAULT_REPORT_CSV,
        help=f"匹配报告 CSV 文件名；默认 {DEFAULT_REPORT_CSV}。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_folder = Path(__file__).resolve().parent
    folder = Path(args.folder).expanduser().resolve() if args.folder else script_folder
    if not folder.is_dir():
        print(f"文件夹不存在：{folder}", file=sys.stderr)
        return 1

    output_zip = Path(args.output).expanduser()
    if not output_zip.is_absolute():
        output_zip = folder / output_zip
    report_path = Path(args.report).expanduser()
    if not report_path.is_absolute():
        report_path = folder / report_path

    try:
        roster_path = find_roster_csv(folder, args.roster)
        written_count, total_count = filter_photos_by_roster(
            folder,
            roster_path,
            output_zip,
            report_path,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"队员名单：{roster_path}")
    print(f"已生成：{output_zip}")
    print(f"已筛选头像：{written_count} 张")
    print(f"扫描图片：{total_count} 张")
    print(f"匹配报告：{report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
