### Note-processing agent features (LLM vision)

- Multi-note detection
  - Vision LLM detects layout (e.g., 3x3 Rocketbook), counts notes, estimates regions.
  - Fallbacks: QR-based positioning, OpenCV contour detection, 3x3 grid heuristic for Rocketbook.
- Single-note and multi-note flows
  - Single image can be processed as a single note or split into multiple notes, driven by user preference/flags.
- Vision-first text extraction (OCR via LLM)
  - High-accuracy extraction with formatting preservation: titles (##Title##), bullets, numbered lists, checkboxes, special characters, line breaks, tags (@tag), key:value tags (::key:value)
  - Confidence scoring based on content structure/length; LLM is ground truth.
- Structure recognition
  - Detects title, sections, bulleted/numbered lists, todos, simple tags (@tag), key-value tags (::key:value).
  - Produces structured section metadata with line spans.
- Intelligent post-processing
  - Normalizes formatting, fixes common OCR artifacts, generates clean, markdown-friendly text.
  - Tracks corrections and confidence.
- Visual and metadata enrichment
  - Image preprocessing (denoise, contrast, deskew) and quality metrics.
  - Color analysis (dominant/background), note type estimation (sticky/paper), size estimate.
  - QR code detection with rotation support; maps QR to categories and metadata.
  - EXIF extraction (capture time, camera, GPS when present).
- Comprehensive output schema
  - Per-note: spatial position, visual metadata, QR codes, text content (raw/formatted), structure, tags, entities, quality metrics, processing details.
  - Per-image: filename, dimensions, size, format, color space; summary stats and status.
- Error handling and graceful degradation
  - Partial results on agent failures; per-note error notes with diagnostics.
  - Fallbacks for region detection and single-note processing when multi-note fails.
- User- and org-level controls
  - Model selection via env/user preference; ocr_mode default “llm”.
  - Confidence thresholds, multi-note toggle, timeouts, retries, parallelism limits.
- Downstream AI enrichment (text LLM)
  - Optional summaries, entities, action items, and tags derived from extracted text.
- Graph integration hooks
  - Background task to extract triples from note content and insert into the knowledge graph.
- Observability
  - Metrics per stage (quality, confidence, timing, counts), structured logging.
  - Optional Braintrust tracing when enabled.
- Security and performance
  - Processes files from controlled upload dir, size limits, streaming-safe handling.
  - Parallelizable where independent; bounded concurrency; safe fallbacks.

- Upload API behavior
  - Images: vision pipeline runs; creates one or many notes; QR may remap category; comprehensive metadata stored on the parent note with child links.
  - Non-images: treated as text; directly creates a note with previews and optional AI enrichment.

- Configuration via environment
  - OPENAI_API_KEY, AGENT_VISION_MODEL, TEXT_AI_MODEL, OCR_MODE, thresholds/timeouts, graph service URLs.

- Logging and audit
  - Records model used, processing time, success rates, and warnings for operational insight.