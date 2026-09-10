"""Storage-only collection methods, composed into existing repositories."""
from contextlib import contextmanager
from uuid import UUID

from .collection_models import AssetCollection, CollectionItem


class MemoryCollectionStorage:
    @contextmanager
    def collection_lock(self, collection_id):
        # Shared repository lock also serializes position allocation.
        if not self._review_lock.acquire(blocking=False):
            raise ValueError("COLLECTION_BUSY")
        try:
            yield
        finally:
            self._review_lock.release()

    def save_collection(self, collection):
        self.collections[collection.collection_id] = collection.model_copy(deep=True)

    def get_collection(self, collection_id):
        value = self.collections.get(collection_id)
        return value.model_copy(deep=True) if value else None

    def save_collection_item(self, item):
        self.collection_items[item.id] = item.model_copy(deep=True)

    def list_collection_items(self, collection_id):
        return sorted([item.model_copy(deep=True) for item in self.collection_items.values()
                       if item.collection_id == collection_id], key=lambda item: item.position)


class PostgreSQLCollectionStorage:
    @contextmanager
    def collection_lock(self, collection_id: UUID):
        with self._connect() as connection:
            # Transaction advisory lock released on connection exit, including process death.
            locked = connection.execute("SELECT pg_try_advisory_xact_lock(%s)",
                                        (collection_id.int % (2**63),)).fetchone()[0]
            if not locked:
                raise ValueError("COLLECTION_BUSY")
            yield

    def save_collection(self, collection):
        from psycopg.types.json import Jsonb
        with self._connect() as connection:
            connection.execute("INSERT INTO asset_collections (id, data) VALUES (%s,%s) "
                               "ON CONFLICT (id) DO UPDATE SET data=EXCLUDED.data",
                               (collection.collection_id, Jsonb(collection.model_dump(mode="json"))))

    def get_collection(self, collection_id):
        with self._connect() as connection:
            row = connection.execute("SELECT data FROM asset_collections WHERE id=%s", (collection_id,)).fetchone()
        return AssetCollection.model_validate(row[0]) if row else None

    def save_collection_item(self, item):
        from psycopg.types.json import Jsonb
        with self._connect() as connection:
            connection.execute("INSERT INTO collection_items (id,collection_id,asset_id,position,data) "
                               "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET data=EXCLUDED.data",
                               (item.id, item.collection_id, item.asset_id, item.position,
                                Jsonb(item.model_dump(mode="json"))))

    def list_collection_items(self, collection_id):
        with self._connect() as connection:
            rows = connection.execute("SELECT data FROM collection_items WHERE collection_id=%s ORDER BY position",
                                      (collection_id,)).fetchall()
        return [CollectionItem.model_validate(row[0]) for row in rows]
