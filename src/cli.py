import json
from pathlib import Path

import click

from .pipeline import run_to_file


@click.command()
@click.option("--image", "image_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--out", "out_path", required=True, type=click.Path(dir_okay=False))
@click.option("--single-note", is_flag=True, default=False, help="Force single note mode")
@click.option("--trace", is_flag=True, default=False, help="Enable tracing if configured")
def main(image_path: str, out_path: str, single_note: bool, trace: bool):
    run_to_file(image_path, out_path, force_single=single_note)
    click.echo(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
