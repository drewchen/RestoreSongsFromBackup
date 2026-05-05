"""
copy_missing_music.py

Reads two file lists (CurrentWorkingFileList.txt and BackupFileList.txt),
determines which music files are missing from the current directory,
and copies them from the backup drive, recreating intermediate directories
as needed.

Directory structure:
  Current:  Y:\\Music\\<Artist>\\<Album>\\<Song>
  Backup:   H:\\iTunes\\iTunes\\iTunes Music\\Music\\<Artist>\\<Album>\\<Song>
         or H:\\iTunes\\iTunes\\iTunes Music\\<Artist>\\<Album>\\<Song>  (older iTunes layout)

Usage:
  python copy_missing_music.py [--current-root Y:\\\\Music] [--backup-root "H:\\\\iTunes\\\\iTunes\\\\iTunes Music"]

By default this is a DRY RUN (no files are copied). Pass --execute to actually copy.
"""

import os
import shutil
import argparse


# -- Configuration -------------------------------------------------------------

CURRENT_FILE_LIST = "CurrentWorkingFileList.txt"
BACKUP_FILE_LIST  = "BackupFileList.txt"

DEFAULT_CURRENT_ROOT = r"Y:\Music"
DEFAULT_BACKUP_ROOT  = r"H:\iTunes\iTunes\iTunes Music"

# The backup uses "Unknown Album" for untagged tracks; the current directory
# uses this placeholder instead.  Any destination path containing the backup
# string will have it replaced with the placeholder before copying.
UNKNOWN_ALBUM_BACKUP  = "Unknown Album"
UNKNOWN_ALBUM_CURRENT = "_                           _"


# -- Helpers -------------------------------------------------------------------

def load_paths(filepath: str) -> list[str]:
    """Load and clean a file list, stripping BOM, CR, and header lines."""
    with open(filepath, "rb") as f:
        content = f.read().decode("utf-8-sig")       # strips UTF-8 BOM
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
    Extract the artist/album/song portion from a full path.

    Current layout:  Y:/Music/<rel>
    Backup layout A: H:/iTunes/iTunes/iTunes Music/Music/<rel>
    Backup layout B: H:/iTunes/iTunes/iTunes Music/<rel>
    """
    marker_itunes_a = "\\iTunes Music\\Music\\"
    marker_itunes_b = "\\iTunes Music\\"
    marker_music    = "\\Music\\"

    if marker_itunes_a in path:
        return path[path.index(marker_itunes_a) + len(marker_itunes_a):]
    if marker_itunes_b in path:
        return path[path.index(marker_itunes_b) + len(marker_itunes_b):]
    if marker_music in path:
        return path[path.index(marker_music) + len(marker_music):]
    return None


def artist_and_filename(rel_path: str) -> str:
    """Return 'Artist/filename' ignoring the album directory."""
    parts = rel_path.split("\\")
    if len(parts) >= 2:
        return parts[0] + "\\" + parts[-1]
    return rel_path


# -- Main logic ----------------------------------------------------------------

def find_missing(current_list_path: str, backup_list_path: str):
    """
    Return (missing, detected) where:
      missing  -- list of (relative_path, backup_full_path) for files that
                  exist in the backup but are absent from current entirely.
      detected -- list of (backup_rel_path, current_full_path, backup_full_path)
                  for files present in both lists (exact or album-name mismatch).

    A file is considered present in current if the exact relative path
    (artist/album/song) matches, OR if the same artist+filename exists under
    a different album directory (re-tagged album name). The latter are NOT
    treated as missing.
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

    # Build a map of (artist, filename) -> current full path
    current_artist_song: dict[str, str] = {}
    for k, v in current_rel.items():
        current_artist_song[artist_and_filename(k)] = v

    missing:  list[tuple[str, str]]      = []  # (backup_rel, backup_full)
    detected: list[tuple[str, str, str]] = []  # (backup_rel, current_full, backup_full)

    for rel, backup_full in sorted(backup_rel.items()):
        if rel in current_rel:
            # Exact match
            detected.append((rel, current_rel[rel], backup_full))
        else:
            as_key = artist_and_filename(rel)
            if as_key in current_artist_song:
                # Present under a different album directory name
                detected.append((rel, current_artist_song[as_key], backup_full))
            else:
                missing.append((rel, backup_full))

    return missing, detected


def copy_missing(
    missing:  list[tuple[str, str]],
    detected: list[tuple[str, str, str]],
    current_root: str,
    backup_root: str,
    dry_run: bool = True,
) -> None:
    """Print detected files, then copy (or preview) each missing file."""

    print(f"  Backup root : {backup_root}")
    print(f"  Current root: {current_root}\n")

    # -- Detected (already present) --------------------------------------------
    print("=" * 72)
    print(f"  DETECTED -- {len(detected)} file(s) already present in current")
    print("=" * 72)
    for backup_rel, current_full, backup_full in detected:
        print(f"  [DETECTED] {backup_rel}")
        print(f"             from: {backup_full}")
        print(f"             at  : {current_full}")
    print()

    # -- Missing (to copy) -----------------------------------------------------
    print("=" * 72)
    print(f"  {'DRY RUN -- ' if dry_run else ''}COPYING -- {len(missing)} missing file(s)")
    print("=" * 72)

    skipped: list[tuple[str, str]] = []
    copied:  list[str]             = []
    errors:  list[tuple[str, str]] = []

    for rel_path, backup_full in missing:
        # Replace "Unknown Album" with the current directory's placeholder
        dest_rel = rel_path.replace(
            UNKNOWN_ALBUM_BACKUP + "\\",
            UNKNOWN_ALBUM_CURRENT + "\\",
        )
        dest_full = os.path.join(current_root, dest_rel)

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
                print(f"  [ERROR] {rel_path} -- {exc}")
                errors.append((rel_path, str(exc)))

    # -- Summary ---------------------------------------------------------------
    print()
    print("=" * 72)
    print("  Summary")
    print("=" * 72)
    print(f"  Detected (already present)       : {len(detected)}")
    print(f"  {'Would copy' if dry_run else 'Copied':<32} : {len(copied)}")
    print(f"  Skipped (source not on disk)     : {len(skipped)}")
    if not dry_run:
        print(f"  Errors                           : {len(errors)}")
    if dry_run:
        print()
        print("  *** This was a DRY RUN -- no files were copied. ***")
        print("  *** Re-run with --execute to perform the copy.  ***")


# -- Entry point ---------------------------------------------------------------

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

    missing, detected = find_missing(args.current_list, args.backup_list)
    print(f"Found {len(missing)} missing file(s) and {len(detected)} already-present file(s).\n")

    copy_missing(
        missing,
        detected,
        current_root=args.current_root,
        backup_root=args.backup_root,
        dry_run=not args.execute,
    )


if __name__ == "__main__":
    main()
