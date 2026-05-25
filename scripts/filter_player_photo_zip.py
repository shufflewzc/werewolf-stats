#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sqlite_store import load_repository_data

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}


def archive_photo_key(filename: str) -> str:
    name = PurePosixPath(filename).name.strip()
    if not name or name.startswith("."):
        return ""
    if PurePosixPath(name).suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        return ""
    return PurePosixPath(name).stem.strip()


def list_match_record_player_ids(
    data: dict[str, object],
    competition_name: str,
    season_name: str,
) -> set[str]:
    player_ids: set[str] = set()
    for match in data.get("matches", []):
        if (
            str(match.get("competition_name") or "").strip() != competition_name.strip()
            or str(match.get("season") or "").strip() != season_name.strip()
        ):
            continue
        for participant in match.get("players", []):
            if not isinstance(participant, dict):
                continue
            player_id = str(participant.get("player_id") or "").strip()
            if player_id:
                player_ids.add(player_id)
    return player_ids


def build_player_indexes(
    data: dict[str, object],
    player_ids: set[str],
) -> tuple[dict[str, dict[str, object]], dict[str, list[dict[str, object]]]]:
    player_by_id = {
        str(player.get("player_id") or "").strip(): player
        for player in data.get("players", [])
        if str(player.get("player_id") or "").strip() in player_ids
    }
    players_by_name: dict[str, list[dict[str, object]]] = {}
    for player in player_by_id.values():
        name = str(player.get("display_name") or "").strip()
        if name:
            players_by_name.setdefault(name, []).append(player)
    return player_by_id, players_by_name


def resolve_player_id(
    key: str,
    player_by_id: dict[str, dict[str, object]],
    players_by_name: dict[str, list[dict[str, object]]],
) -> tuple[str, str]:
    if key in player_by_id:
        return key, "player_id"
    name_matches = players_by_name.get(key, [])
    if len(name_matches) == 1:
        return str(name_matches[0].get("player_id") or ""), "display_name"
    if len(name_matches) > 1:
        return "", "ambiguous_name"
    return "", "unmatched"


def write_report(report_path: Path, rows: list[dict[str, str]]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["status", "source_file", "matched_player_id", "match_type", "reason"],
        )
        writer.writeheader()
        writer.writerows(rows)


def filter_zip(
    source_zip: Path,
    output_zip: Path,
    competition_name: str,
    season_name: str,
    report_path: Path,
) -> tuple[int, int, Path]:
    data = load_repository_data()
    match_player_ids = list_match_record_player_ids(data, competition_name, season_name)
    if not match_player_ids:
        raise ValueError("当前赛事赛季没有找到已存在比赛记录的队员。")

    player_by_id, players_by_name = build_player_indexes(data, match_player_ids)
    used_player_ids: set[str] = set()
    report_rows: list[dict[str, str]] = []
    written_count = 0

    try:
        with ZipFile(source_zip) as archive, ZipFile(output_zip, "w", compression=ZIP_DEFLATED) as output:
            for info in archive.infolist():
                if info.is_dir() or info.filename.startswith("__MACOSX/"):
                    continue
                key = archive_photo_key(info.filename)
                source_name = PurePosixPath(info.filename).name
                if not key:
                    report_rows.append(
                        {
                            "status": "ignored",
                            "source_file": info.filename,
                            "matched_player_id": "",
                            "match_type": "",
                            "reason": "不是支持的图片文件",
                        }
                    )
                    continue
                player_id, match_type = resolve_player_id(key, player_by_id, players_by_name)
                if not player_id:
                    report_rows.append(
                        {
                            "status": "skipped",
                            "source_file": info.filename,
                            "matched_player_id": "",
                            "match_type": match_type,
                            "reason": "未匹配到唯一的比赛记录队员",
                        }
                    )
                    continue
                if player_id in used_player_ids:
                    report_rows.append(
                        {
                            "status": "skipped",
                            "source_file": info.filename,
                            "matched_player_id": player_id,
                            "match_type": match_type,
                            "reason": "同一队员已有一张图片入选",
                        }
                    )
                    continue
                extension = PurePosixPath(source_name).suffix.lower()
                output.writestr(f"{player_id}{extension}", archive.read(info))
                used_player_ids.add(player_id)
                written_count += 1
                report_rows.append(
                    {
                        "status": "included",
                        "source_file": info.filename,
                        "matched_player_id": player_id,
                        "match_type": match_type,
                        "reason": "",
                    }
                )
    except BadZipFile as exc:
        raise ValueError("输入文件不是有效的 zip 压缩包。") from exc

    write_report(report_path, report_rows)
    return written_count, len(report_rows), report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="筛选赛季队员头像 zip，只保留已存在比赛记录的队员头像。")
    parser.add_argument("source_zip", help="原始头像 zip 文件路径")
    parser.add_argument("--competition", required=True, help="赛事名称，需与比赛记录中的 competition_name 一致")
    parser.add_argument("--season", required=True, help="赛季名称，需与比赛记录中的 season 一致")
    parser.add_argument("--output", help="输出的小 zip 路径，默认在原文件旁生成 matched-*.zip")
    parser.add_argument("--report", help="CSV 报告路径，默认在输出 zip 旁生成同名 .csv")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_zip = Path(args.source_zip).expanduser().resolve()
    if not source_zip.is_file():
        print(f"输入文件不存在：{source_zip}", file=sys.stderr)
        return 1
    output_zip = (
        Path(args.output).expanduser().resolve()
        if args.output
        else source_zip.with_name(f"matched-{source_zip.name}")
    )
    report_path = (
        Path(args.report).expanduser().resolve()
        if args.report
        else output_zip.with_suffix(".csv")
    )
    try:
        written_count, total_count, report_path = filter_zip(
            source_zip,
            output_zip,
            args.competition,
            args.season,
            report_path,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"已生成：{output_zip}")
    print(f"已写入可匹配头像：{written_count} 张")
    print(f"处理文件总数：{total_count} 个")
    print(f"匹配报告：{report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
