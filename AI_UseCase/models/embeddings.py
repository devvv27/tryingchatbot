from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterable, List

from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer


def _chunk_text(text: str, chunk_size: int = 700, overlap: int = 120) -> List[str]:
	clean = " ".join(text.split())
	if not clean:
		return []

	chunks: List[str] = []
	start = 0
	n = len(clean)
	while start < n:
		end = min(start + chunk_size, n)
		chunks.append(clean[start:end])
		if end == n:
			break
		start = max(end - overlap, start + 1)
	return chunks


@dataclass
class RetrievalResult:
	chunk: str
	score: float


class LightweightRAGStore:
	"""A simple in-memory vector store backed by TF-IDF embeddings."""

	def __init__(self) -> None:
		self._vectorizer = TfidfVectorizer(stop_words="english")
		self._chunks: List[str] = []
		self._matrix = None

	@property
	def is_ready(self) -> bool:
		return bool(self._chunks) and self._matrix is not None

	@property
	def chunk_count(self) -> int:
		return len(self._chunks)

	def build_from_pdf_files(self, uploaded_files: Iterable) -> int:
		chunks: List[str] = []

		for f in uploaded_files:
			file_bytes = f.getvalue()
			reader = PdfReader(BytesIO(file_bytes))
			for page in reader.pages:
				text = page.extract_text() or ""
				chunks.extend(_chunk_text(text))

		if not chunks:
			raise ValueError("No text could be extracted from the provided PDF files.")

		self._chunks = chunks
		self._matrix = self._vectorizer.fit_transform(chunks)
		return len(chunks)

	def retrieve(self, query: str, k: int = 4) -> List[RetrievalResult]:
		if not self.is_ready:
			return []

		query_vec = self._vectorizer.transform([query])
		scores = (self._matrix @ query_vec.T).toarray().ravel()

		if scores.size == 0:
			return []

		ranked_indices = scores.argsort()[::-1][:k]
		results: List[RetrievalResult] = []
		for idx in ranked_indices:
			score = float(scores[idx])
			if score > 0:
				results.append(RetrievalResult(chunk=self._chunks[idx], score=score))

		# Fallback for broad queries (e.g., "summarize the PDF") where sparse vectors can score zero.
		if not results:
			for idx in ranked_indices:
				results.append(RetrievalResult(chunk=self._chunks[idx], score=float(scores[idx])))

		return results
