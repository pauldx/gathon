# Gathon Image Vision Extraction Skill

## Overview

Images in Gathon are handled via **Claude Code subagents with vision capability**, not direct API calls. When images are encountered during extraction, they are flagged for semantic analysis by Claude subagents.

## Image Handling Pipeline

1. **Detection** → Router classifies `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.svg` as `Pipeline.GATHON_IMAGE`
2. **Placeholder creation** → `image_parser.py:parse_image()` creates minimal `IMAGE` root node with confidence=AMBIGUOUS
3. **Subagent dispatch** → Gathon CLI or Claude Code routes image to subagent for vision analysis
4. **Vision extraction** → Subagent reads image, extracts concepts, objects, text, relationships
5. **Graph linking** → Extracted concepts become nodes; relationships become edges, linked to root IMAGE node

## Subagent Instructions

When processing images, Claude subagents should:

**UI/Screenshot:**
- Identify layout patterns, design decisions, key UI elements
- Extract text labels, button names, form fields
- Model component hierarchy (header → nav → content → footer)
- Relationships: "contains", "precedes", "overlaps"

**Chart/Graph:**
- Extract metric name, axis labels, legend
- Identify trends: increasing, decreasing, constant, cyclical
- Note data source, time period
- Relationships: "shows", "measures", "trends_to"

**Diagram:**
- Identify components, nodes, symbols
- Extract connection types: directed/undirected, labeled/unlabeled
- Note sequence or hierarchy
- Relationships: "connects_to", "feeds_into", "contains"

**Research figure/equation:**
- Describe what phenomenon it demonstrates
- Extract key variables, parameters
- Note method or derivation
- Relationships: "demonstrates", "supports", "uses"

## JSON Output Format

Subagents should return extracted concepts as:

```json
{
  "nodes": [
    {
      "id": "entity_id",
      "label": "Human-readable label",
      "type": "concept|object|text|metric|component",
      "description": "Brief context"
    }
  ],
  "edges": [
    {
      "source": "id1",
      "target": "id2",
      "relation": "contains|depicts|shows|measures|connects_to|feeds_into|demonstrates",
      "confidence": "EXTRACTED|INFERRED|AMBIGUOUS"
    }
  ]
}
```

## No API Key Required

- Images are NOT parsed by Gathon's Python code
- Vision is handled entirely by Claude Code subagents
- No ANTHROPIC_API_KEY needed in extraction pipeline
- Subagents use Claude's built-in vision capability
- Fallback: If no subagent available, image remains as placeholder node

## Integration with Gathon Store

Root IMAGE node created by `parse_image()`:
- `kind="Image"`
- `qualified_name="{path}::root"`
- `file_type=FileType.IMAGE`
- `confidence=Confidence.AMBIGUOUS` (semantic content unknown until subagent runs)
- `source_location={path}` (pointer for subagent)

Subagent updates: Add concept nodes + edges, all linked to root via `CONTAINS` edges.

## Example

Input: `screenshot.png` (30x30 button "Click Me" on blue background)

After subagent vision:
- Nodes:
  - `screenshot.png::root` (IMAGE root)
  - `screenshot.png::button_click_me` (UI component, EXTRACTED)
  - `screenshot.png::blue_background` (design element, INFERRED)
- Edges:
  - `root` CONTAINS `button_click_me` (confidence: EXTRACTED)
  - `button_click_me` REFERENCES `blue_background` (confidence: INFERRED)
