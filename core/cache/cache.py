from typing import Any, Protocol


class DocumentsCache(Protocol):
    def query_document(self, key: str) -> Any: ...

    def insert_document(self, key: str, document: Any): ...

    def clear(self): ...

    def __len__(self) -> int: ...

    def __contains__(self, key: str) -> bool: ...
