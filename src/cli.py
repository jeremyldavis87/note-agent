import click

from .pipeline import run_to_file, process_multiple_images


@click.command()
@click.option("--image", "image_paths", required=True, multiple=True, type=click.Path(exists=True, dir_okay=False), help="Image file(s) to process (can specify multiple times)")
@click.option("--out", "out_path", required=True, type=click.Path(dir_okay=False))
@click.option("--single-note", is_flag=True, default=False, help="Force single note mode")
@click.option("--trace", is_flag=True, default=False, help="Enable tracing if configured")
def main(image_paths: tuple, out_path: str, single_note: bool, trace: bool):
    if len(image_paths) == 1:
        # Single image: use existing function
        run_to_file(image_paths[0], out_path, force_single=single_note)
    else:
        # Multiple images: use aggregation function
        process_multiple_images(list(image_paths), out_path, force_single=single_note)
    click.echo(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
