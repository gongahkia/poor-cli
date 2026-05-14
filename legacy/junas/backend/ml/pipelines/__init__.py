from abc import ABC, abstractmethod

from prefect import flow


class BasePipeline(ABC):
    @abstractmethod
    def discover(self) -> list[str]:
        """discover source files"""

    @abstractmethod
    def parse(self, path: str) -> list[dict]:
        """parse a single source file into records"""

    @abstractmethod
    def index(self, records: list[dict]) -> int:
        """index records into target store, return count"""

    @flow(name="ingest")
    def run(self) -> int:
        paths = self.discover()
        total = 0
        for path in paths:
            records = self.parse(path)
            total += self.index(records)
        return total
