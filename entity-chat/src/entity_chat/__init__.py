from __future__ import annotations

import argparse
import hashlib
import json
import sys
import warnings
from pathlib import Path
from typing import NamedTuple

# glinker/gliner/torch raise deprecation warnings about their own internals
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

from pydantic_ai import Agent
from pydantic import BaseModel
from kreuzberg import extract_file_sync
from glinker.l1.processor import L1GlinerProcessor
from glinker.l1.models import L1GlinerConfig
from glinker.l1.component import L1GlinerComponent


GLINER_MODEL = "knowledgator/gliner-bi-edge-v2.0"
CHAT_MODEL = "anthropic:claude-haiku-4-5"
CACHE_DIR = Path(".")


class Entity(NamedTuple):
    name: str
    label: str
    count: int


class EntityInfo(BaseModel):
    name: str
    label: str
    count: int


class ChatResponse(BaseModel):
    reply: str
    entities: list[EntityInfo]


class AgentReply(BaseModel):
    reply: str


def cache_key(pdf_path: Path, labels: list[str]) -> str:
    digest = hashlib.sha256()
    digest.update(pdf_path.read_bytes())
    digest.update("|".join(sorted(labels)).encode())
    return digest.hexdigest()


def count_entities(spans: list[tuple[str, str]]) -> list[Entity]:
    counted: dict[tuple[str, str], Entity] = {}
    for text, label in spans:
        key = (text.casefold(), label.casefold())
        if key in counted:
            counted[key] = counted[key]._replace(count=counted[key].count + 1)
        else:
            counted[key] = Entity(text, label, 1)
    return list(counted.values())


def extract_entities(text: str, labels: list[str]) -> list[Entity]:
    config = L1GlinerConfig(model=GLINER_MODEL, labels=labels)
    component = L1GlinerComponent(config)
    processor = L1GlinerProcessor(config, component)
    spans = processor(texts=[text]).entities[0]

    return count_entities([(s.text, s.label) for s in spans if s.label is not None])


def load_or_extract_entities(pdf_path: Path, labels: list[str]) -> list[Entity]:
    cache_path = CACHE_DIR / f"{cache_key(pdf_path, labels)}.json"
    if cache_path.is_file():
        return [Entity(**row) for row in json.loads(cache_path.read_text())]

    extracted_text = extract_file_sync(pdf_path).content
    entities = extract_entities(extracted_text, labels)
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path.write_text(json.dumps([e._asdict()
                          for e in entities], indent=2))
    return entities


def build_agent(entities: list[Entity]) -> Agent[None, AgentReply]:
    listing = "\n".join(
        f"- {e.name} ({e.label}): {e.count} mention(s)" for e in entities)
    return Agent(
        CHAT_MODEL,
        output_type=AgentReply,
        system_prompt=(
            "You answer questions directly about named entities already extracted from a document. "
            "Use conversational style, no Markdown, no stying. "
            "Only use the entity list below - never invent entities or counts that aren't in it. "
            "Never assume access to the document's original text. "
            f"\n\n{listing}"
        ),
    )


def answer_question(entities: list[Entity], question: str) -> ChatResponse:
    # The model's only job is the natural-language reply - that's the one
    # part of ChatResponse it can actually produce. `entities` is already
    # fully known before the model runs, so it's attached here directly
    # instead of asking the model to transcribe it back to us.
    reply = build_agent(entities).run_sync(question).output.reply
    return ChatResponse(
        reply=reply,
        entities=[EntityInfo(name=e.name, label=e.label, count=e.count) for e in entities],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Answer questions about named entities detected in a PDF document."
    )
    parser.add_argument("document", type=Path, help="path to the PDF document")
    parser.add_argument(
        "question", help="natural language question about the document's entities")
    parser.add_argument(
        "--labels", required=True, help="comma-separated entity labels to detect, e.g. person,country"
    )
    args = parser.parse_args()

    if not args.document.is_file():
        print(f"error: file not found: {args.document}", file=sys.stderr)
        sys.exit(1)

    labels = [label.strip()
              for label in args.labels.split(",") if label.strip()]

    try:
        entities = load_or_extract_entities(args.document, labels)
        response = answer_question(entities, args.question)
    except Exception as exc:
        print(f"error: processing failed: {exc}", file=sys.stderr)
        sys.exit(2)

    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
