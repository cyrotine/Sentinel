from __future__ import annotations

import logging
import os
from pathlib import Path

from pydantic import BaseModel, Field

from forge_repository_analysis.chunker import CodeChunker
from forge_repository_analysis.languages import LANGUAGE_MAP, SKIP_DIRS, SKIP_EXTENSIONS

logger = logging.getLogger(__name__)


class SymbolNode(BaseModel):
    name: str
    kind: str  # "function" | "class" | "method"
    start_line: int
    end_line: int


class FileNode(BaseModel):
    path: str
    language: str | None = None
    size: int = 0
    symbols: list[SymbolNode] = Field(default_factory=list)
    chunks: list[dict[str, object]] = Field(default_factory=list)


class RepositoryAnalysis(BaseModel):
    repository_id: str
    files: list[FileNode] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    total_files: int = 0
    total_size: int = 0


def _extract_symbols(content: str, language: str) -> list[SymbolNode]:
    try:
        from tree_sitter_languages import get_parser

        parser = get_parser(language)
        tree = parser.parse(content.encode())
        symbols: list[SymbolNode] = []

        def _walk(node) -> None:  # type: ignore[no-untyped-def]
            kind: str | None = None
            name_field: str | None = None
            if node.type in ("function_definition", "function_declaration"):
                kind = "function"
                name_field = "name"
            elif node.type in ("class_definition", "class_declaration"):
                kind = "class"
                name_field = "name"
            elif node.type == "method_definition":
                kind = "method"
                name_field = "name"

            if kind and name_field:
                name_node = node.child_by_field_name(name_field)
                if name_node:
                    symbols.append(
                        SymbolNode(
                            name=name_node.text.decode() if name_node.text else "unknown",
                            kind=kind,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                        )
                    )

            for child in node.children:
                _walk(child)

        _walk(tree.root_node)
        return symbols
    except Exception as exc:
        logger.debug("Symbol extraction failed for language %s: %s", language, exc)
        return []


class RepositoryAnalyzer:
    def __init__(self) -> None:
        self._chunker = CodeChunker()

    async def analyze(self, path: str, repository_id: str) -> RepositoryAnalysis:
        root = Path(path)
        files: list[FileNode] = []
        language_set: set[str] = set()
        total_size = 0

        for dirpath, dirnames, filenames in os.walk(root):
            # Prune skipped directories in-place
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

            for filename in filenames:
                file_path = Path(dirpath) / filename
                suffix = file_path.suffix.lower()

                if suffix in SKIP_EXTENSIONS:
                    continue

                # Skip minified files by naming convention
                if ".min." in filename:
                    continue

                try:
                    size = file_path.stat().st_size
                except OSError:
                    continue

                # Skip very large files (>500 KB)
                if size > 500_000:
                    continue

                relative_path = str(file_path.relative_to(root))
                language = LANGUAGE_MAP.get(suffix)

                symbols: list[SymbolNode] = []
                chunks: list[dict[str, object]] = []

                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    content = ""

                if content:
                    if language:
                        symbols = _extract_symbols(content, language)
                        language_set.add(language)
                    chunks = self._chunker.chunk(content, relative_path)

                files.append(
                    FileNode(
                        path=relative_path,
                        language=language,
                        size=size,
                        symbols=symbols,
                        chunks=chunks,
                    )
                )
                total_size += size

        return RepositoryAnalysis(
            repository_id=repository_id,
            files=files,
            languages=sorted(language_set),
            total_files=len(files),
            total_size=total_size,
        )
