"""Parse video/audio via Whisper transcription."""

from __future__ import annotations

from pathlib import Path

from gathon.multimodal_graph.doc_parser import parse_doc
from gathon.schema import Confidence, FileType, UnifiedEdge, UnifiedNode


def parse_video(path: Path) -> tuple[list[UnifiedNode], list[UnifiedEdge]]:
    """Transcribe video/audio, parse transcript as document."""
    try:
        import faster_whisper
    except ImportError:
        return [], []

    model_name = "base"
    try:
        model = faster_whisper.WhisperModel(model_name)
    except Exception:
        return [], []

    try:
        segments, _ = model.transcribe(str(path))
        transcript = " ".join(seg.text for seg in segments)
    except Exception:
        return [], []

    if not transcript.strip():
        return [], []

    transcript_path = Path("gathon-out") / "transcripts" / f"{path.stem}.txt"
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(transcript, encoding="utf-8")

    nodes = []
    edges = []

    root = UnifiedNode(
        kind="Video",
        name=path.stem,
        qualified_name=f"{path}::root",
        file_path=str(path),
        label=path.stem,
        file_type=FileType.VIDEO,
        confidence=Confidence.INFERRED,
        confidence_score=0.8,
        pipeline="gathon_video",
    )
    nodes.append(root)

    trans_nodes, trans_edges = parse_doc(transcript_path)

    transcript_doc = UnifiedNode(
        kind="Document",
        name=f"{path.stem}_transcript",
        qualified_name=f"{path}::transcript",
        file_path=str(transcript_path),
        label=f"Transcript: {path.stem}",
        file_type=FileType.DOCUMENT,
        confidence=Confidence.INFERRED,
        confidence_score=0.8,
    )
    nodes.append(transcript_doc)

    edges.append(UnifiedEdge(
        kind="CONTAINS",
        source_qualified=root.qualified_name,
        target_qualified=transcript_doc.qualified_name,
        file_path=str(path),
        relation="contains",
        confidence=0.8,
    ))

    for tn in trans_nodes:
        tn.pipeline = "gathon_video"
        nodes.append(tn)

    for te in trans_edges:
        edges.append(te)

    return nodes, edges
