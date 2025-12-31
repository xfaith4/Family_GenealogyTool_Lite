import argparse
import os
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app import create_app
from app.db import get_engine
from app.media_pipeline import MediaIngestService, MediaPaths, OCRService, legacy_link, run_watch_loop


def _paths_from_args(args):
    app = create_app({
        "DATABASE": args.db,
        "MEDIA_DIR": args.media_dir,
        "MEDIA_INGEST_DIR": args.ingest_dir,
        "TESTING": False,
    })
    engine = get_engine()
    session_factory = sessionmaker(bind=engine)
    return app, session_factory, MediaPaths(Path(app.config["MEDIA_DIR"]), Path(app.config["MEDIA_INGEST_DIR"]))


def cmd_scan(args) -> int:
    app, session_factory, paths = _paths_from_args(args)
    with app.app_context():
        session = session_factory()
        try:
            ingest = MediaIngestService(session, paths, verbose=args.verbose, dry_run=args.dry_run)
            count = ingest.scan_directory(Path(args.source))
            if not args.verbose:
                print(f"registered={count}")
            return 0
        finally:
            session.close()


def cmd_ingest(args) -> int:
    app, session_factory, paths = _paths_from_args(args)
    with app.app_context():
        session = session_factory()
        try:
            ingest = MediaIngestService(session, paths, verbose=args.verbose, dry_run=args.dry_run)
            count = ingest.scan_directory(Path(args.source))
            if args.ocr:
                ocr = OCRService(ingest, lang=args.lang, verbose=args.verbose, dry_run=args.dry_run)
                for file_path in Path(args.source).rglob("*"):
                    ocr.ocr_path(file_path, only_missing=True)
            if not args.verbose:
                print(f"registered={count}")
            return 0
        finally:
            session.close()


def cmd_ocr(args) -> int:
    app, session_factory, paths = _paths_from_args(args)
    with app.app_context():
        session = session_factory()
        try:
            ingest = MediaIngestService(session, paths, verbose=args.verbose, dry_run=args.dry_run)
            ocr = OCRService(ingest, lang=args.lang, verbose=args.verbose, dry_run=args.dry_run)
            processed = 0
            for file_path in Path(args.source).rglob("*"):
                asset = ocr.ocr_path(file_path, out_dir=Path(args.out) if args.out else None, only_missing=args.only_missing)
                if asset:
                    processed += 1
            if not args.verbose:
                print(f"ocr_processed={processed}")
            return 0
        finally:
            session.close()


def cmd_watch(args) -> int:
    app, session_factory, paths = _paths_from_args(args)
    with app.app_context():
        run_watch_loop(
            session_factory,
            paths,
            interval=args.interval,
            ocr=args.ocr,
            lang=args.lang,
            verbose=args.verbose,
            dry_run=args.dry_run,
        )
    return 0


def cmd_legacy(args) -> int:
    app, session_factory, paths = _paths_from_args(args)
    with app.app_context():
        session = session_factory()
        try:
            result = legacy_link(
                session=session,
                paths=paths,
                legacy_db=Path(args.legacy_db),
                report_path=Path(args.report),
                apply=args.apply,
                min_confidence=args.min_confidence,
                verbose=args.verbose,
                dry_run=args.dry_run,
            )
            if not args.verbose:
                print(f"applied={result['applied']} report={result['report']}")
            return 0
        finally:
            session.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Media ingest + OCR + legacy link tools")
    parser.add_argument("--db", default=os.environ.get("APP_DB_PATH") or "data/family_tree.sqlite")
    parser.add_argument("--media-dir", default=os.environ.get("APP_MEDIA_DIR") or "data/media")
    parser.add_argument("--ingest-dir", default=os.environ.get("APP_MEDIA_INGEST_DIR") or "data/media_ingest")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--dry-run", action="store_true")

    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Register existing files into media_assets")
    scan.add_argument("--source", default="data/media")
    scan.set_defaults(func=cmd_scan)

    ingest = sub.add_parser("ingest", help="Ingest new files from media_ingest")
    ingest.add_argument("--source", default="data/media_ingest")
    ingest.add_argument("--ocr", action="store_true")
    ingest.add_argument("--lang", default="eng")
    ingest.set_defaults(func=cmd_ingest)

    ocr = sub.add_parser("ocr", help="Run OCR on a folder")
    ocr.add_argument("--source", default="data/media_ingest")
    ocr.add_argument("--out", default=None)
    ocr.add_argument("--lang", default="eng")
    ocr.add_argument("--only-missing", action="store_true")
    ocr.set_defaults(func=cmd_ocr)

    watch = sub.add_parser("watch", help="Watch ingest folder and auto-ingest")
    watch.add_argument("--interval", type=float, default=5.0)
    watch.add_argument("--ocr", action="store_true")
    watch.add_argument("--lang", default="eng")
    watch.set_defaults(func=cmd_watch)

    legacy = sub.add_parser("legacy-link", help="Restore legacy media associations")
    legacy.add_argument("--legacy-db", required=True)
    legacy.add_argument("--report", default="data/reports/legacy_media_link_candidates.csv")
    legacy.add_argument("--apply", action="store_true")
    legacy.add_argument("--min-confidence", type=float, default=0.9)
    legacy.set_defaults(func=cmd_legacy)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
