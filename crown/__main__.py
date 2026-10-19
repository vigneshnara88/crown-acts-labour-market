"""Command-line interface for aggregation and estimation."""

import argparse
import json
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from . import __version__
from .aggregate import OUTCOMES, aggregate_people
from .estimate import estimate_models, load_cells
from .policy import TREATMENTS, attach_exposure, load_policy


def parser() -> argparse.ArgumentParser:
    main = argparse.ArgumentParser(description="ACS cell aggregation and CROWN policy comparisons.")
    commands = main.add_subparsers(dest="command", required=True)
    aggregate = commands.add_parser("aggregate", help="Build weighted cells from harmonized records.")
    aggregate.add_argument("--people", type=Path, required=True)
    aggregate.add_argument("--output", type=Path, required=True)
    aggregate.add_argument("--start-year", type=int, default=2015)
    aggregate.add_argument("--end-year", type=int, default=2024)
    aggregate.add_argument("--chunksize", type=int, default=250_000)
    estimate = commands.add_parser("estimate", help="Estimate the saturated state-group-year model.")
    estimate.add_argument("--cells", type=Path, required=True)
    estimate.add_argument("--policy", type=Path, required=True)
    estimate.add_argument("--output", type=Path, required=True)
    estimate.add_argument("--treatment", choices=TREATMENTS, required=True)
    estimate.add_argument("--pairwise", action="store_true", help="Also fit BW/BM and BW/WW comparisons.")
    estimate.add_argument("--outcomes", choices=OUTCOMES, nargs="+")
    estimate.add_argument("--alpha", type=float, default=0.05)
    estimate.add_argument("--require-balanced", action="store_true")
    for command in [aggregate, estimate]:
        command.add_argument("--overwrite", action="store_true", help="Replace existing output files.")
    return main


def main() -> None:
    command_parser = parser()
    args = command_parser.parse_args()
    try:
        output = args.output.resolve()
        if output.suffix.lower() != ".csv":
            raise ValueError("--output must name a .csv file.")
        metadata_path = output.with_suffix(".metadata.json")
        inputs = [args.people] if args.command == "aggregate" else [args.cells, args.policy]
        if output in [path.resolve() for path in inputs]:
            raise ValueError("The output path must differ from every input path.")
        if not args.overwrite and (output.exists() or metadata_path.exists()):
            raise ValueError("An output already exists; choose another path or pass --overwrite.")
        if args.command == "aggregate":
            frame, metadata = aggregate_people(
                args.people, start_year=args.start_year, end_year=args.end_year,
                chunksize=args.chunksize,
            )
        else:
            cells = load_cells(args.cells)
            policy = load_policy(args.policy, last_year=int(cells["year"].max()))
            panel = attach_exposure(cells, policy, args.treatment)
            frame, metadata = estimate_models(
                panel, treatment=args.treatment, pairwise=args.pairwise,
                outcomes=args.outcomes, alpha=args.alpha, require_balanced=args.require_balanced,
            )
            metadata["policy_records"] = json.loads(policy.to_json(orient="records", date_format="iso"))
        metadata.update({
            "command": args.command,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "package_version": __version__,
            "dependencies": {name: version(name) for name in ["numpy", "pandas", "scipy"]},
            "inputs": [str(path.resolve()) for path in inputs],
            "output": str(output),
        })
        metadata_text = json.dumps(metadata, indent=2, allow_nan=False) + "\n"
        output.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(output, index=False)
        metadata_path.write_text(metadata_text, encoding="utf-8")
        print(f"Wrote {len(frame)} rows to {output}")
        print(f"Wrote metadata to {metadata_path}")
    except (ValueError, OSError) as error:
        command_parser.error(str(error))


if __name__ == "__main__":
    main()
