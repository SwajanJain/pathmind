import argparse
import json

from pathmind_api.etl.runner import run_reactome_etl_sync, run_retention_purge, summary_to_dict


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PathMind ETL and privacy jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run-reactome-etl", help="Run Reactome target-pathway ETL")
    run_parser.add_argument("--mode", default="nightly", choices=["nightly", "incremental", "manual"])
    run_parser.add_argument("--max-targets", type=int, default=5000)
    run_parser.add_argument("--seed-uniprot", action="append", default=[])

    purge_parser = subparsers.add_parser("purge-api-logs", help="Purge api_event_logs older than retention")
    purge_parser.add_argument("--retention-days", type=int, default=90)

    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.command == "run-reactome-etl":
        summary = run_reactome_etl_sync(
            mode=args.mode,
            max_targets=args.max_targets,
            seed_uniprot_ids=args.seed_uniprot,
        )
        print(json.dumps(summary_to_dict(summary), indent=2))
        return
    if args.command == "purge-api-logs":
        result = run_retention_purge(retention_days=args.retention_days)
        print(json.dumps(result, indent=2))
        return
    raise SystemExit(1)


if __name__ == "__main__":
    main()
