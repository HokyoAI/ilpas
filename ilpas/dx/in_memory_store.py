from typing import Dict, Iterable, Optional, Set
from uuid import uuid4

from ..core.models.errors import BadDataError
from ..core.models.types import Labels, LabelValue, ValueAndLabels, ValueDict
from ..core.store import Store


class InMemoryStore(Store):
    """
    In-memory implementation of the Store interface.
    """

    def __init__(self, default_namespace: str = "default"):
        """
        Initialize an in-memory store.

        Args:
            default_namespace: The default namespace to use when none is specified
        """
        super().__init__(default_namespace)

        # Store structure:
        # {
        #   namespace1: {
        #     primary_key1: {
        #       "value": value1,
        #       "labels": {label1: value1, ...},
        #       "guid": guid1
        #     },
        #     ...
        #   },
        #   ...
        # }
        self.store: Dict[
            str,
            Dict[
                str,
                ValueAndLabels,
            ],
        ] = {}

        # Label index for efficient lookup:
        # {
        #   namespace1: {
        #     label1: {
        #       value1: {primary_key1, primary_key2, ...},
        #       ...
        #     },
        #     ...
        #   },
        #   ...
        # }
        self.label_index: Dict[str, Dict[str, Dict[LabelValue, Set[str]]]] = {}

        # guid index for efficient lookup:
        # {
        #   namespace1: {
        #     guid: {
        #       value1: {primary_key1, primary_key2, ...},
        #       ...
        #     },
        #     ...
        #   },
        #   ...
        # }
        self.guid_index: Dict[str, Dict[str, Set[str]]] = {}

        self.instance_discovery_store: Dict[str, tuple[str, Optional[str]]] = {}

    async def _check_namespace(self, namespace):
        return namespace in self.store

    async def _create_namespace(self, namespace: str) -> None:
        """Create a namespace if it does not exist."""
        self.label_index[namespace] = {}
        self.guid_index[namespace] = {}
        self.store[namespace] = {}

    async def _find_primary_keys_by_labels(
        self, *, guid: Optional[str], namespace: str, labels: Labels
    ) -> Set[str]:
        """Find primary keys by labels. If no labels are provided, return all primary keys in given namespace.

        Args:
            namespace: The namespace to search in
            labels: The labels to search for

        Returns:
            A set of primary keys matching the labels
        """
        matching_primary_keys: Set[str] | None = None
        if not labels and guid is None:
            return set(self.store[namespace].keys())

        if guid is not None:
            if guid not in self.guid_index[namespace]:
                return set()
            else:
                matching_primary_keys = self.guid_index[namespace][guid]

        for label_key, label_value in labels.items():
            if label_key not in self.label_index[namespace]:
                continue

            if label_value not in self.label_index[namespace][label_key]:
                continue

            current_matching_keys = self.label_index[namespace][label_key][label_value]

            if matching_primary_keys is None:
                matching_primary_keys = current_matching_keys
            else:
                matching_primary_keys.intersection_update(current_matching_keys)

        if matching_primary_keys is None:
            return set()
        return matching_primary_keys

    async def _get_values_of_primary_keys(
        self, *, namespace: str, primary_keys: Iterable[str]
    ) -> Dict[str, ValueAndLabels]:
        """
        Retrieve the values of primary keys from the specified namespace.

        Args:
            namespace: The namespace to search in
            primary_keys: The primary keys to retrieve

        Returns:
            A dictionary mapping primary keys to their values and labels
        """
        result = {}
        for pkey in primary_keys:
            result[pkey] = self.store[namespace][pkey]
        return result

    async def _check_primary_keys(
        self, *, primary_keys: Iterable[str], namespace: str
    ) -> bool:
        """
        Check if the primary keys exists in the specified namespace.

        Returns:
            True if all primary keys exist, False otherwise
        """
        for pkey in primary_keys:
            if pkey not in self.store[namespace]:
                return False
        return True

    def _add_new_label(self, *, namespace: str, label_key: str, primary_key) -> None:
        """
        Add a new label key to the label index.
        For all existing records in the namespace, initialize their label values to None.
        """
        if label_key not in self.label_index[namespace]:
            self.label_index[namespace][label_key] = {}
            self.label_index[namespace][label_key][None] = set()

        for pkey in self.store[namespace]:
            if pkey != primary_key:
                self.label_index[namespace][label_key][None].add(pkey)
                self.store[namespace][pkey]["labels"][label_key] = None

    def _add_new_guid(self, *, namespace: str, guid: str, primary_key) -> None:
        """
        Add a new guid to the guid index.
        For all existing records in the namespace, initialize their guid values to None.
        """
        if guid not in self.guid_index[namespace]:
            self.guid_index[namespace][guid] = set()

    def _index_labels(
        self, *, namespace: str, primary_key: str, guid: str, labels: Labels
    ) -> None:
        """Index labels for efficient lookup."""
        if guid not in self.guid_index[namespace]:
            self._add_new_guid(namespace=namespace, guid=guid, primary_key=primary_key)
        self.guid_index[namespace][guid].add(primary_key)

        for label_key, label_value in labels.items():
            if label_key not in self.label_index[namespace]:
                self._add_new_label(
                    namespace=namespace, label_key=label_key, primary_key=primary_key
                )

            if label_value not in self.label_index[namespace][label_key]:
                self.label_index[namespace][label_key][label_value] = set()

            self.label_index[namespace][label_key][label_value].add(primary_key)

    def _deindex_labels(
        self, *, namespace: str, primary_key: str, guid: str, labels: Labels
    ) -> None:
        """Remove label indices for a record."""
        if guid in self.guid_index[namespace]:
            self.guid_index[namespace][guid].discard(primary_key)

            # Clean up empty sets
            if not self.guid_index[namespace][guid]:
                del self.guid_index[namespace][guid]

        for label_key, label_value in labels.items():
            if (
                label_key in self.label_index[namespace]
                and label_value in self.label_index[namespace][label_key]
            ):
                self.label_index[namespace][label_key][label_value].discard(primary_key)

                # Clean up empty sets
                if not self.label_index[namespace][label_key][label_value]:
                    del self.label_index[namespace][label_key][label_value]

                # Clean up empty indices
                if not self.label_index[namespace][label_key]:
                    del self.label_index[namespace][label_key]

    async def _delete(self, *, primary_key: str, namespace: str) -> None:
        """
        Delete a value by its primary key from the specified namespace.

        Args:
            primary_key: The primary key of the value to delete, guaranteed to exist
            namespace: The namespace to delete from

        """
        values_and_labels = self.store[namespace].pop(primary_key)
        self._deindex_labels(
            namespace=namespace,
            primary_key=primary_key,
            guid=values_and_labels["guid"],
            labels=values_and_labels["labels"],
        )

    async def _update_existing_pkey(
        self,
        *,
        namespace: str,
        primary_key: str,
        value: ValueDict,
        guid: str,
        labels: Labels,
    ) -> str:
        """Set the value and labels for an existing primary key in the specified namespace."""
        current_labels = self.store[namespace][primary_key]["labels"]
        current_guid = self.store[namespace][primary_key]["guid"]
        if current_guid != guid:
            raise BadDataError("GUID cannot be updated")
        self._deindex_labels(
            namespace=namespace,
            primary_key=primary_key,
            guid=guid,
            labels=current_labels,
        )
        self.store[namespace][primary_key] = {
            "value": value,
            "labels": labels,
            "guid": guid,
        }
        self._index_labels(
            namespace=namespace, primary_key=primary_key, guid=guid, labels=labels
        )
        return primary_key

    async def _insert_new_pkey(
        self, *, namespace: str, value: ValueDict, guid: str, labels: Labels
    ) -> str:
        """Set the value and labels for a new primary key in the specified namespace."""
        pkey = str(uuid4())
        if await self._check_primary_keys(primary_keys=[pkey], namespace=namespace):
            raise RuntimeError("UUID collision")
        self.store[namespace][pkey] = {
            "value": value,
            "labels": labels,
            "guid": guid,
        }
        self._index_labels(
            namespace=namespace, primary_key=pkey, guid=guid, labels=labels
        )
        return pkey

    async def _insert_given_pkey(
        self,
        *,
        namespace: str,
        primary_key: str,
        value: ValueDict,
        guid: str,
        labels: Labels,
    ) -> str:
        """Insert a new primary key with the given value and labels."""
        self.store[namespace][primary_key] = {
            "value": value,
            "labels": labels,
            "guid": guid,
        }
        self._index_labels(
            namespace=namespace, primary_key=primary_key, guid=guid, labels=labels
        )
        return primary_key

    async def put_instance_discovery(
        self, *, key: str, primary_key: str, namespace: Optional[str]
    ) -> None:
        """
        Store a public instance discovery key for a given primary key and namespace.
        The discovery key is stored in the default namespace.

        Args:
            key: The public instance discovery key
            primary_key: The primary key of the instance
            namespace: Optional namespace of the instance (default is used if not provided)
        """
        self.instance_discovery_store[key] = (primary_key, namespace)

    async def instance_discovery(
        self, *, key: str
    ) -> Optional[tuple[str, Optional[str]]]:
        """
        Retrieve the primary key and namespace of an instance by a public discovery key.

        Args:
            key: The public instance discovery key

        Returns:
            The primary key of the instance, and the namespace if available
        """
        return self.instance_discovery_store.get(key, None)

    async def delete_instance_discovery(self, *, key: str) -> None:
        """
        Delete a public instance discovery key.

        Args:
            key: The public instance discovery key
        """
        self.instance_discovery_store.pop(key, None)
