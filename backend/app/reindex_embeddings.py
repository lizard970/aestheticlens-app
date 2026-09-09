from .embeddings import configured_embedding_adapter
from .knowledge import SemanticSearchService
from .repositories import repository_from_env


def main() -> None:
    repository = repository_from_env()
    adapter = configured_embedding_adapter()
    if adapter is None:
        raise RuntimeError("Configure AESTHETICLENS_EMBEDDING_PROVIDER and credentials first")
    service = SemanticSearchService(repository, adapter)
    results = repository.list_results()
    for result in results:
        service.refresh(result.id)
    print(f"Re-evaluated {len(results)} stored analysis results.")


if __name__ == "__main__":
    main()
