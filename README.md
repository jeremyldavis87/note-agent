# Note Agent (Local CLI)

Local tool that converts an image containing one or multiple notes into structured JSON using a vision LLM plus optional text LLM enrichment.

## Setup

1. Create a virtual environment (Python 3.12):
```bash
python3.12 -m venv .venv
source .venv/bin/activate
```
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Copy `.env.local` to `.env` and adjust values as needed.

## Run

```bash
python -m src.cli --image test-notes-image.jpg --out out.json
```

Flags:
- `--single-note` to force single-note processing
- `--trace` to enable Braintrust tracing (if configured)

## Models and providers
- Vision and text models are selected via `.env` settings (`AGENT_VISION_MODEL`, `TEXT_AI_MODEL`).
- Providers are chosen by the factory based on model names and which API keys are present (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).

## Compare to expected output
```bash
python scripts/compare_expected.py --actual out.json --expected expected-output.json
```

## Notes
- No DB/API/UI. Output is written to a JSON file.
- See `docs/FEATURES.md` for supported features.
