"""
copy_missing_music.py

Reads two file lists (CurrentWorkingFileList.txt and BackupFileList.txt),
determines which music files are missing from the current directory,
and copies them from the backup drive, recreating intermediate directories
as needed.

Directory structure:
  Current:  Y:\Music\<Artist>\<Album>\<Song>
  Backup:   H:\iTunes\iTunes\iTunes Music\Music\<Artist>\<Album>\<Song>
         or H:\iTunes\iTunes\iTunes Music\<Artist>\<Album>\<Song>  (older iTunes layout)

Usage:
  python copy_missing_music.py [--dry-run] [--current-root Y:\\Music] [--backup-root "H:\\iTunes\\iTunes\\iTunes Music"]

By default this is a DRY RUN (no files are copied). Pass --execute to actually copy.
"""

import os
import shutil
import argparse


# ── Configuration ────────────────────────────────────────────────────────────

CURRENT_FILE_LIST = "CurrentWorkingFileList.txt"
BACKUP_FILE_LIST  = "BackupFileList.txt"

DEFAULT_CURRENT_ROOT = r"Y:\Music"
DEFAULT_BACKUP_ROOT  = r"H:\iTunes\iTunes\iTunes Music"


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_paths(filepath: str) -> list[str]:
    """Load and clean a file list, stripping BOM, CR, and header lines."""
    with open(filepath, "rb") as f:
        content = f.read().decode("utf-8-sig")          # strips UTF-8 BOM
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    paths = []
    for line in lines:
        line = line.strip()
        if (line
                and line != "FullName"
                and not line.startswith("---")
                and "FileList" not in line):
            paths.append(line)
    return paths


def relative_music_path(path: str) -> str | None:
    """
    Extract the artist\\album\\song portion from a full path.

    Current layout:  Y:\\Music\\<rel>
    Backup layout A: H:\\iTunes\\iTunes\\iTunes Music\\Music\\<rel>
    Backup layout B: H:\\iTunes\\iTunes\\iTunes Music\\<rel>
    """
    marker_music    = "\\Music\\"          # current  (and backup layout A)
    marker_itunes_a = "\\iTunes Music\\Music\\"
    marker_itunes_b = "\\iTunes Music\\"

    if marker_itunes_a in path:
        return path[path.index(marker_itunes_a) + len(marker_itunes_a):]
    if marker_itunes_b in path:
        return path[path.index(marker_itunes_b) + len(marker_itunes_b):]
    if marker_music in path:
        return path[path.index(marker_music) + len(marker_music):]
    return None


def artist_and_filename(rel_path: str) -> str:
    """Return '<Artist>\\<filename>' ignoring the album directory."""
    parts = rel_path.split("\\")
    if len(parts) >= 2:
        return parts[0] + "\\" + parts[-1]
    return rel_path


# ── Main logic ────────────────────────────────────────────────────────────────

def find_missing(current_list_path: str, backup_list_path: str):
    """
    Return a list of (relative_path, backup_full_path) tuples for files that
    exist in the backup but not in the current directory.

    A file is considered 'present' in current if the exact relative path
    (artist\\album\\song) matches, OR if the same artist+filename exists
    under a different album directory.  The latter case represents songs
    that were re-tagged (album name changed) and are NOT treated as missing.
    """
    current_paths = load_paths(current_list_path)
    backup_paths  = load_paths(backup_list_path)

    # Build lookup tables
    current_rel: dict[str, str] = {}     # relative -> full current path
    for p in current_paths:
        rel = relative_music_path(p)
        if rel:
            current_rel[rel] = p

    backup_rel: dict[str, str] = {}      # relative -> full backup path
    for p in backup_paths:
        rel = relative_music_path(p)
        if rel:
            backup_rel[rel] = p

    # Build a set of (artist, filename) pairs already in current
    current_artist_song = {artist_and_filename(k) for k in current_rel}

    missing = []  # list of (relative_path, backup_full_path)
    for rel, backup_full in sorted(backup_rel.items()):
        if rel not in current_rel:
            # Only truly missing if artist+filename is also absent
            if artist_and_filename(rel) not in current_artist_song:
                missing.append((rel, backup_full))

    return missing


def copy_missing(
    missing: list[tuple[str, str]],
    current_root: str,
    backup_root: str,
    dry_run: bool = True,
) -> None:
    """Copy each missing file from the backup drive to the current drive."""

    print(f"\n{'DRY RUN — ' if dry_run else ''}Copying {len(missing)} missing file(s)\n")
    print(f"  Backup root : {backup_root}")
    print(f"  Current root: {current_root}\n")
    print("-" * 72)

    skipped  = []
    copied   = []
    errors   = []

    for rel_path, backup_full in missing:
        # Build the destination path
        dest_full = os.path.join(current_root, rel_path)

        # Verify the source file actually exists on disk
        if not os.path.exists(backup_full):
            skipped.append((rel_path, f"Source not found: {backup_full}"))
            print(f"  [SKIP ] {rel_path}")
            print(f"          source not found: {backup_full}")
            continue

        if dry_run:
            print(f"  [WOULD COPY] {rel_path}")
            print(f"               from: {backup_full}")
            print(f"               to  : {dest_full}")
            copied.append(rel_path)
        else:
            try:
                os.makedirs(os.path.dirname(dest_full), exist_ok=True)
                shutil.copy2(backup_full, dest_full)
                print(f"  [OK   ] {rel_path}")
                copied.append(rel_path)
            except Exception as exc:
                print(f"  [ERROR] {rel_path} — {exc}")
                errors.append((rel_path, str(exc)))

    print("-" * 72)
    print(f"\nSummary:")
    print(f"  {'Would copy' if dry_run else 'Copied'} : {len(copied)}")
    print(f"  Skipped (source missing) : {len(skipped)}")
    if not dry_run:
        print(f"  Errors                   : {len(errors)}")
    if dry_run:
        print("\n  *** This was a DRY RUN — no files were copied. ***")
        print("  *** Re-run with --execute to perform the copy.  ***")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Copy music files missing from the current directory from the backup."
    )
    parser.add_argument(
        "--current-list",
        default=CURRENT_FILE_LIST,
        help=f"Path to the current file list  (default: {CURRENT_FILE_LIST})",
    )
    parser.add_argument(
        "--backup-list",
        default=BACKUP_FILE_LIST,
        help=f"Path to the backup file list   (default: {BACKUP_FILE_LIST})",
    )
    parser.add_argument(
        "--current-root",
        default=DEFAULT_CURRENT_ROOT,
        help=f"Root of the current music directory (default: {DEFAULT_CURRENT_ROOT})",
    )
    parser.add_argument(
        "--backup-root",
        default=DEFAULT_BACKUP_ROOT,
        help=f"Root of the backup iTunes directory (default: {DEFAULT_BACKUP_ROOT})",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually copy files (default is dry-run only)",
    )
    args = parser.parse_args()

    missing = find_missing(args.current_list, args.backup_list)
    print(f"Found {len(missing)} file(s) missing from current directory.")

    copy_missing(
        missing,
        current_root=args.current_root,
        backup_root=args.backup_root,
        dry_run=not args.execute,
    )


if __name__ == "__main__":
    main()
