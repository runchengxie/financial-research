"""Create a portable ZIP bundle of the repository's distributable assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT_NAME = "financial-research"
DEFAULT_OUTPUT_DIR = Path("/mnt/c/Users/gbyha/Downloads")
DEFAULT_PLATFORM_DATA_ROOT = Path(
    os.environ.get("FIN_RESEARCH_DATA_ROOT", "~/data/market-data-platform")
).expanduser()

INCLUDED_PATHS = (
    "AGENTS.md",
    "README.md",
    "docs",
    "data",
    "src",
    "scripts",
    "artifacts",
)
EXCLUDED_PARTS = {"__pycache__", ".git", ".DS_Store"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
PLATFORM_ASSET_PATHS = (
    "daily_basic/a_share_all_daily_basic_latest",
    "margin_detail/a_share_all_margin_detail_latest",
    "normalized_fundamentals/a_share_top800_union_20150227_20260529_income",
    "normalized_fundamentals/a_share_top800_union_20150227_20260529_cashflow",
    "normalized_fundamentals/a_share_top800_union_20150227_20260529_balancesheet",
)


def _included_files(repo_root: Path = REPO_ROOT) -> list[Path]:
    """Return stable, safe paths that belong in a portable bundle."""
    files: list[Path] = []
    for relative in INCLUDED_PATHS:
        candidate = repo_root / relative
        if candidate.is_file():
            files.append(candidate)
        elif candidate.is_dir():
            for path in candidate.rglob("*"):
                if not path.is_file():
                    continue
                rel_parts = path.relative_to(repo_root).parts
                if any(part in EXCLUDED_PARTS for part in rel_parts):
                    continue
                if path.suffix in EXCLUDED_SUFFIXES:
                    continue
                files.append(path)
    return sorted(files, key=lambda path: path.relative_to(repo_root).as_posix())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _project_entries(repo_root: Path = REPO_ROOT) -> list[tuple[Path, Path]]:
    return [
        (path, Path(PACKAGE_ROOT_NAME) / path.relative_to(repo_root))
        for path in _included_files(repo_root)
    ]


def _platform_asset_entries(data_root: Path) -> list[tuple[Path, Path]]:
    """Map the external assets used by enhanced screening into the ZIP.

    The source may use a ``*_latest`` symbolic link. The archive deliberately
    writes its resolved contents under that logical path so Windows recipients
    do not need symbolic-link support.
    """
    asset_root = data_root.expanduser().resolve() / "assets/tushare/a_share"
    entries: list[tuple[Path, Path]] = []
    for relative in PLATFORM_ASSET_PATHS:
        source = asset_root / relative
        if not source.exists():
            raise FileNotFoundError(f"缺少增强初筛所需资产：{source}")
        resolved = source.resolve()
        archive_root = (
            Path(PACKAGE_ROOT_NAME)
            / "platform-data/assets/tushare/a_share"
            / relative
        )
        if resolved.is_file():
            entries.append((resolved, archive_root))
            continue
        for path in resolved.rglob("*"):
            if path.is_file():
                entries.append((path, archive_root / path.relative_to(resolved)))
    return sorted(entries, key=lambda entry: entry[1].as_posix())


def _manifest(entries: list[tuple[Path, Path]], include_platform_assets: bool) -> dict[str, object]:
    entries = [
        {
            "path": archive_path.relative_to(PACKAGE_ROOT_NAME).as_posix(),
            "bytes": source_path.stat().st_size,
            "sha256": _sha256(source_path),
        }
        for source_path, archive_path in entries
    ]
    return {
        "format": "financial-research-bundle/v1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "included_paths": list(INCLUDED_PATHS),
        "file_count": len(entries),
        "total_bytes": sum(entry["bytes"] for entry in entries),
        "files": entries,
        "platform_assets_included": include_platform_assets,
        "external_assets_not_included": (
            [
                "market-data-platform 中持久化的 daily_basic、normalized_fundamentals、margin_detail 等资产",
                "需要 TuShare 或交易所披露才能刷新的一手与高频数据",
            ]
            if not include_platform_assets
            else [
                "ths_hot、limit_list_ths、moneyflow_ths 与 hsgt_top10 的完整平台原始资产；当前数据快照已通过 data/company-hotspot-data.csv 随包提供",
                "未被当前 enhanced_screen.py 使用的其他 market-data-platform 资产，以及打包后发生的上游新增数据",
            ]
        ),
        "run_note": (
            "若包含 platform-data，解压后将 FIN_RESEARCH_DATA_ROOT 指向 "
            "financial-research/platform-data，可在 market-data-platform 环境重跑增强初筛。"
            "它不包含用于刷新热点数据的全部上游平台资产。"
            if include_platform_assets
            else "该包可浏览文档、数据和仪表盘；重跑增强初筛需要另行提供 market-data-platform 资产。"
        ),
        "verification": "解压后可用 BUNDLE_MANIFEST.json 中的 SHA-256 校验每个文件。",
    }


def build_bundle(
    output_dir: Path,
    name: str = "financial-research.zip",
    *,
    include_platform_assets: bool = False,
    data_root: Path = DEFAULT_PLATFORM_DATA_ROOT,
) -> Path:
    """Write the portable project archive and return its path."""
    output_dir = output_dir.expanduser().resolve()
    if output_dir == REPO_ROOT or REPO_ROOT in output_dir.parents:
        raise ValueError("输出目录不能位于仓库内，否则压缩包可能递归包含自身。")
    if Path(name).name != name or not name.endswith(".zip"):
        raise ValueError("压缩包名称必须是单个以 .zip 结尾的文件名。")

    entries = _project_entries()
    if include_platform_assets:
        entries.extend(_platform_asset_entries(data_root))
    manifest = _manifest(entries, include_platform_assets)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / name

    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for source_path, member_path in entries:
            archive.write(source_path, member_path.as_posix())
        archive.writestr(
            f"{PACKAGE_ROOT_NAME}/BUNDLE_MANIFEST.json",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )
        archive.writestr(
            f"{PACKAGE_ROOT_NAME}/BUNDLE_README.md",
            "# 分发包说明\n\n"
            + manifest["run_note"]
            + "\n\n完整性校验请见 `BUNDLE_MANIFEST.json`。\n",
        )
    return archive_path


def bundle_summary(include_platform_assets: bool, data_root: Path) -> tuple[int, int]:
    """Return planned file count and uncompressed bytes without writing a ZIP."""
    entries = _project_entries()
    if include_platform_assets:
        entries.extend(_platform_asset_entries(data_root))
    return len(entries), sum(path.stat().st_size for path, _ in entries)


def main() -> None:
    parser = argparse.ArgumentParser(description="导出可分发的金融研报核验仓库 ZIP 包")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"输出目录，默认：{DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--name",
        default="financial-research.zip",
        help="压缩包名称，必须以 .zip 结尾",
    )
    parser.add_argument(
        "--include-platform-assets",
        action="store_true",
        help="额外打包增强初筛所需的 market-data-platform 持久化资产，文件可能较大",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_PLATFORM_DATA_ROOT,
        help=f"market-data-platform 数据根目录，默认：{DEFAULT_PLATFORM_DATA_ROOT}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只显示计划打包的文件数与未压缩大小，不写入压缩包",
    )
    args = parser.parse_args()

    file_count, total_bytes = bundle_summary(args.include_platform_assets, args.data_root)
    if args.dry_run:
        print(f"Planned files: {file_count}")
        print(f"Uncompressed size: {total_bytes / 1024 / 1024:.1f} MiB")
        print(f"Platform assets included: {args.include_platform_assets}")
        return

    archive_path = build_bundle(
        args.output_dir,
        args.name,
        include_platform_assets=args.include_platform_assets,
        data_root=args.data_root,
    )
    with ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read(f"{PACKAGE_ROOT_NAME}/BUNDLE_MANIFEST.json"))
    print(f"Bundle: {archive_path}")
    print(f"  Files: {manifest['file_count']}")
    print(f"  Size: {archive_path.stat().st_size / 1024:.1f} KiB")
    print(f"  Platform assets included: {manifest['platform_assets_included']}")
    if not manifest["platform_assets_included"]:
        print("  External market-data-platform assets are listed in BUNDLE_MANIFEST.json and are not included.")


if __name__ == "__main__":
    main()
