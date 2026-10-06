import os
from pathlib import Path

import psycopg
import requests
import yaml
from bs4 import BeautifulSoup
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

DATABASE_URL = os.getenv(
    "MULEWATCH_DATABASE_URL",
    "postgresql://mulewatch:mulewatch_dev@localhost:5432/mulewatch",
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = PROJECT_ROOT / "rag" / "sources.yaml"

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384


def load_sources() -> list[dict]:
    """Load the typology source registry."""

    with SOURCES_FILE.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    return data["sources"]


def chunk_text(
    text: str,
    *,
    chunk_size: int = 400,
    overlap: int = 50,
) -> list[str]:
    """Split text into overlapping word-based chunks."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between 0 and chunk_size")

    words = text.split()

    if not words:
        return []

    chunks = []
    start = 0

    while start < len(words):
        end = min(start + chunk_size, len(words))

        chunk = " ".join(words[start:end])
        chunks.append(chunk)

        if end == len(words):
            break

        start = end - overlap

    return chunks


def build_chunks(
    text: str,
    source: dict,
    section: str,
    section_index: int = 0,
) -> list[dict]:
    """Create chunks while preserving citation metadata."""

    chunks = []

    for index, content in enumerate(chunk_text(text), start=1):
        chunks.append(
            {
                "chunk_id": f"{source['id']}:{section_index}:{index}",
                "content": content,
                "source": source["source"],
                "title": source["title"],
                "section": section,
                "url": source.get("url"),
                "date": source.get("date"),
            }
        )

    return chunks


def load_embedding_model() -> SentenceTransformer:
    """Load the local sentence-transformer embedding model."""

    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def embed_chunks(
    chunks: list[dict],
    model: SentenceTransformer,
) -> list[dict]:
    """Generate a local embedding for every chunk."""

    if not chunks:
        return chunks

    texts = [chunk["content"] for chunk in chunks]

    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
    )

    for chunk, embedding in zip(chunks, embeddings, strict=True):
        chunk["embedding"] = embedding.tolist()

    return chunks


def create_typology_chunks_table(conn: psycopg.Connection) -> None:
    """Create storage for typology chunks and their embeddings."""

    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS typology_chunks (
            chunk_id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            section TEXT NOT NULL,
            url TEXT,
            source_date DATE,
            embedding vector({EMBEDDING_DIMENSION}) NOT NULL
        )
        """
    )


def store_chunks(
    chunks: list[dict],
    conn: psycopg.Connection,
) -> None:
    """Insert or update typology chunks in PostgreSQL."""

    for chunk in chunks:
        conn.execute(
            """
            INSERT INTO typology_chunks (
                chunk_id,
                content,
                source,
                title,
                section,
                url,
                source_date,
                embedding
            )
            VALUES (
                %(chunk_id)s,
                %(content)s,
                %(source)s,
                %(title)s,
                %(section)s,
                %(url)s,
                %(date)s,
                %(embedding)s
            )
            ON CONFLICT (chunk_id)
            DO UPDATE SET
                content = EXCLUDED.content,
                source = EXCLUDED.source,
                title = EXCLUDED.title,
                section = EXCLUDED.section,
                url = EXCLUDED.url,
                source_date = EXCLUDED.source_date,
                embedding = EXCLUDED.embedding
            """,
            chunk,
        )


def fetch_web_sections(url: str) -> list[tuple[str, str]]:
    """Fetch a public web page and return heading-based text sections."""

    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "MuleWatch/1.0"},
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for element in soup(["script", "style", "nav", "footer"]):
        element.decompose()

    sections = []
    current_heading = "Introduction"
    current_text = []

    for element in soup.find_all(["h1", "h2", "h3", "p", "li"]):
        if element.name in {"h1", "h2", "h3"}:
            if current_text:
                sections.append(
                    (
                        current_heading,
                        " ".join(current_text),
                    )
                )

            current_heading = element.get_text(
                " ",
                strip=True,
            )
            current_text = []

        else:
            text = element.get_text(" ", strip=True)

            if text:
                current_text.append(text)

    if current_text:
        sections.append(
            (
                current_heading,
                " ".join(current_text),
            )
        )

    return sections


def build_web_source_chunks(source: dict) -> list[dict]:
    """Fetch one web source and convert its sections into meaningful chunks."""

    url = source.get("url")

    if not url:
        return []

    sections = fetch_web_sections(url)

    chunks = []
    pending_heading = None
    pending_text = []
    last_section_index = 0

    for section_index, (section, text) in enumerate(sections, start=1):
        last_section_index = section_index
        word_count = len(text.split())

        if word_count < 100:
            if pending_heading is None:
                pending_heading = section

            pending_text.append(text)
            continue

        if pending_text:
            text = " ".join(pending_text + [text])

            if pending_heading:
                section = f"{pending_heading} / {section}"

            pending_heading = None
            pending_text = []

        chunks.extend(
            build_chunks(
                text,
                source,
                section,
                section_index=section_index,
            )
        )

    if pending_text:
        chunks.extend(
            build_chunks(
                " ".join(pending_text),
                source,
                pending_heading or "Additional information",
                section_index=last_section_index + 1,
            )
        )

    return chunks


def build_local_source_chunks(source: dict) -> list[dict]:
    """Read a local Markdown source and convert its sections into chunks."""

    local_path = source.get("local_path")

    if not local_path:
        return []

    path = PROJECT_ROOT / local_path
    text = path.read_text(encoding="utf-8")

    sections = []
    current_heading = "Introduction"
    current_text = []

    for line in text.splitlines():
        stripped = line.strip()

        if stripped.startswith("#"):
            if current_text:
                sections.append(
                    (
                        current_heading,
                        " ".join(current_text),
                    )
                )

            current_heading = stripped.lstrip("#").strip()
            current_text = []

        elif stripped:
            current_text.append(stripped)

    if current_text:
        sections.append(
            (
                current_heading,
                " ".join(current_text),
            )
        )

    chunks = []

    for section_index, (section, section_text) in enumerate(
        sections,
        start=1,
    ):
        chunks.extend(
            build_chunks(
                section_text,
                source,
                section,
                section_index=section_index,
            )
        )

    return chunks


if __name__ == "__main__":
    sources = load_sources()
    model = load_embedding_model()

    total_chunks = 0

    with psycopg.connect(DATABASE_URL) as conn:
        register_vector(conn)
        create_typology_chunks_table(conn)

        for source in sources:
            if source.get("local_path"):
                print(f"\nIngesting local source: {source['title']}")

                chunks = build_local_source_chunks(source)

                if not chunks:
                    print("  No chunks extracted")
                    continue

                chunks = embed_chunks(chunks, model)
                store_chunks(chunks, conn)

                total_chunks += len(chunks)

                print(f"  Stored {len(chunks)} chunks")
                continue

            if not source.get("url"):
                print(f"\nSkipping source with no URL or local path: {source['title']}")
                continue

            print(f"\nIngesting: {source['title']}")

            try:
                chunks = build_web_source_chunks(source)

                if not chunks:
                    print("  No chunks extracted")
                    continue

                chunks = embed_chunks(chunks, model)
                store_chunks(chunks, conn)

                total_chunks += len(chunks)

                print(f"  Stored {len(chunks)} chunks")

            except requests.RequestException as exc:
                print(f"  Failed to fetch source: {exc}")

    print(f"\nTotal chunks stored: {total_chunks}")
