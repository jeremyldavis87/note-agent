import json
import difflib
from pathlib import Path

import click


@click.command()
@click.option("--actual", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--expected", required=True, type=click.Path(exists=True, dir_okay=False))
def main(actual: str, expected: str):
    a = json.loads(Path(actual).read_text())
    e = json.loads(Path(expected).read_text())

    def normalize_text(x: str) -> str:
        return " ".join(x.split())

    # Strict on keys/structure, lenient on whitespace in text fields
    if set(a.keys()) != set(e.keys()):
        click.echo("Root keys differ")
        raise SystemExit(1)

    ad = json.dumps(a, indent=2, sort_keys=True)
    ed = json.dumps(e, indent=2, sort_keys=True)
    if ad == ed:
        click.echo("Match ✅")
        return

    # Show unified diff when not exact
    diff = difflib.unified_diff(ed.splitlines(), ad.splitlines(), fromfile="expected", tofile="actual")
    click.echo("\n".join(diff))
    raise SystemExit(2)


if __name__ == "__main__":
    main()
