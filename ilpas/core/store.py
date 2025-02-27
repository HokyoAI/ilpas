from abc import ABC, abstractmethod
from typing import Dict, Iterable, List, Optional, Set

from .models.errors import ConflictException, NotFoundException
from .models.types import Labels, SearchResult, ValueAndLabels, ValueDict


class Store(ABC):
    """
    Abstract base class for a generic Key-Value store with namespacing and searchable labels.

    Features:
    1. Optional namespacing for higher security boundaries
    2. Multiple methods for accessing values (primary key or labels)
    3. Searchable labels for flexible querying
    """

    def __init__(self, default_namespace: str = "default") -> None:
        self.default_namespace = default_namespace

    @abstractmethod
    async def _create_namespace(self, namespace: str) -> None:
        """Create a namespace if it does not exist."""
        pass

    @abstractmethod
    async def _check_namespace(self, namespace: str) -> bool:
        """Check if a namespace exists."""
        pass

    @abstractmethod
    async def _find_primary_keys_by_labels(
        self, *, namespace: str, guid: Optional[str], labels: Labels
    ) -> Set[str]:
        """Find primary keys by labels. If no labels are provided, return all primary keys in given namespace.

        Args:
            namespace: The namespace to search in
            labels: The labels to search for

        Returns:
            A set of primary keys matching the labels
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def _check_primary_keys(
        self, *, primary_keys: Iterable[str], namespace: str
    ) -> bool:
        """
        Check if the primary keys exists in the specified namespace.

        Returns:
            True if all primary keys exist, False otherwise
        """
        pass

    @abstractmethod
    async def _delete(self, *, primary_key: str, namespace: str) -> None:
        """
        Delete a value by its primary key from the specified namespace.

        Args:
            primary_key: The primary key of the value to delete, guaranteed to exist
            namespace: The namespace to delete from

        """
        pass

    @abstractmethod
    async def _update_existing_pkey(
        self,
        *,
        namespace: str,
        guid: str,
        primary_key: str,
        value: ValueDict,
        labels: Labels,
    ) -> str:
        """Set the value and labels for an existing primary key in the specified namespace."""
        pass

    @abstractmethod
    async def _insert_new_pkey(
        self,
        *,
        namespace: str,
        guid: str,
        value: ValueDict,
        labels: Labels,
    ) -> str:
        """Set the value and labels for a new primary key in the specified namespace."""
        pass

    @abstractmethod
    async def _insert_given_pkey(
        self,
        *,
        namespace: str,
        guid: str,
        primary_key: str,
        value: ValueDict,
        labels: Labels,
    ) -> str:
        """
        Insert a new primary key with the given value and labels.
        If the primary key already exists, throw a ConflictException.
        """
        pass

    def _get_namespace_name(self, namespace: Optional[str]) -> str:
        """Helper to get the actual namespace or default."""
        return namespace if namespace is not None else self.default_namespace

    async def _get_namespace(self, namespace: Optional[str]) -> str:
        """
        Helper to get the actual namespace or default, and check if it exists.

        Args:
            namespace: The namespace to check

        Returns:
            Guaranteed to return a valid namespace

        Raises:
            NotFoundException: If the namespace does not exist
        """
        ns = self._get_namespace_name(namespace)
        exists = await self._check_namespace(ns)
        if exists:
            return ns
        else:
            raise NotFoundException(f"Namespace {ns} does not exist")

    async def _ensure_namespace_exists(self, namespace: Optional[str]) -> str:
        """Ensure namespace structures exists, creating if necessary.

        Args:
            namespace: The namespace to check

        Returns:
            Guaranteed to return a valid namespace
        """
        try:
            return await self._get_namespace(namespace)
        except NotFoundException:
            ns = self._get_namespace_name(namespace)
            await self._create_namespace(ns)
            return ns

    def _ensure_single_match(self, primary_keys: Set[str]) -> str:
        """Ensure there is exactly one match, raising an exception otherwise."""
        if len(primary_keys) > 1:
            raise ConflictException(
                f"Multiple records found matching the provided labels"
            )
        elif len(primary_keys) == 0:
            raise NotFoundException(f"No record found matching the provided labels")
        else:
            return primary_keys.pop()

    def _ensure_single_or_no_match(self, primary_keys: Set[str]) -> Optional[str]:
        """Ensure there is at most one match, raising an exception if there are multiple."""
        if len(primary_keys) > 1:
            raise ConflictException(
                f"Multiple records found matching the provided labels"
            )
        elif len(primary_keys) == 0:
            return None
        else:
            return primary_keys.pop()

    async def put_by_primary_key(
        self,
        *,
        value: ValueDict,
        guid: str,
        labels: Labels,
        primary_key: str,
        namespace: Optional[str] = None,
        throw_on_not_found: bool = False,
    ) -> str:
        """
        Store a value with a specified primary key in the specified namespace.

        Args:
            value: The value to store
            primary_key: The primary key to use
            namespace: Optional namespace (default is used if not provided)

        Raises:
            ConflictException: If a value with the same primary key already exists
        """
        namespace = await self._ensure_namespace_exists(namespace)

        if await self._check_primary_keys(
            primary_keys=[primary_key], namespace=namespace
        ):
            return await self._update_existing_pkey(
                namespace=namespace,
                primary_key=primary_key,
                value=value,
                guid=guid,
                labels=labels,
            )
        else:
            if throw_on_not_found:
                raise NotFoundException("primary key did not exist")
            else:
                return await self._insert_given_pkey(
                    namespace=namespace,
                    primary_key=primary_key,
                    value=value,
                    guid=guid,
                    labels=labels,
                )

    async def put_by_labels(
        self,
        *,
        value: ValueDict,
        guid: str,
        labels: Labels,
        namespace: Optional[str] = None,
    ) -> str:
        """
        Store a value with associated labels in the specified namespace.

        Args:
            value: The value to store
            labels: Searchable labels associated with the value
            namespace: Optional namespace (default is used if not provided)

        Returns:
            The primary key of the stored value

        Raises:
            ConflictException: If a conflict is detected (e.g., labels match existing entry, or multiple entries match)
        """
        namespace = await self._ensure_namespace_exists(namespace)

        existing_key = self._ensure_single_or_no_match(
            await self._find_primary_keys_by_labels(
                namespace=namespace, guid=guid, labels=labels
            )
        )
        if existing_key:
            return await self._update_existing_pkey(
                namespace=namespace,
                primary_key=existing_key,
                value=value,
                guid=guid,
                labels=labels,
            )
        else:
            return await self._insert_new_pkey(
                namespace=namespace, value=value, guid=guid, labels=labels
            )

    async def get_by_primary_key(
        self, *, primary_key: str, namespace: Optional[str] = None
    ) -> SearchResult:
        """
        Retrieve a value by its primary key from the specified namespace.

        Args:
            primary_key: The primary key of the value
            namespace: Optional namespace (default is used if not provided)

        Returns:
            The stored value

        Raises:
            NotFoundException: If the value is not found
        """
        namespace = await self._get_namespace(namespace)

        result = await self._get_values_of_primary_keys(
            namespace=namespace, primary_keys=[primary_key]
        )
        return {
            "primary_key": primary_key,
            **result[primary_key],
        }

    async def get_by_labels(
        self, *, guid: str, labels: Labels, namespace: Optional[str] = None
    ) -> SearchResult:
        """
        Retrieve a value by its labels from the specified namespace.

        Args:
            labels: The labels to search for
            namespace: Optional namespace (default is used if not provided)

        Returns:
            The stored value

        Raises:
            NotFoundException: If no value is found with the given labels
            ConflictException: If multiple values are found with the given labels
        """
        namespace = await self._get_namespace(namespace)

        primary_key = self._ensure_single_match(
            await self._find_primary_keys_by_labels(
                namespace=namespace, guid=guid, labels=labels
            )
        )

        result = await self._get_values_of_primary_keys(
            namespace=namespace, primary_keys=[primary_key]
        )
        return {
            "primary_key": primary_key,
            **result[primary_key],
        }

    async def search(
        self,
        *,
        guid: Optional[str],
        partial_labels: Labels,
        namespace: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Search for values that match the partial labels in the specified namespace.

        Args:
            partial_labels: Labels to match (partial matching)
            namespace: Optional namespace (default is used if not provided)

        Returns:
            List of dictionaries containing primary_key, value, and labels for each match
        """
        namespace = await self._get_namespace(namespace)

        primary_keys = await self._find_primary_keys_by_labels(
            namespace=namespace, guid=guid, labels=partial_labels
        )

        # do this check to guarantee that the primary keys exist for the _get_values_of_primary_keys call
        if not await self._check_primary_keys(
            primary_keys=primary_keys, namespace=namespace
        ):
            raise ConflictException("Something is messed up")

        values = await self._get_values_of_primary_keys(
            namespace=namespace, primary_keys=primary_keys
        )

        return [
            {
                "primary_key": pk,
                **values[pk],
            }
            for pk in primary_keys
        ]

    async def delete_by_primary_key(
        self, *, primary_key: str, namespace: Optional[str] = None
    ) -> None:
        """
        Delete a value by its primary key from the specified namespace.

        Args:
            primary_key: The primary key of the value to delete
            namespace: Optional namespace (default is used if not provided)

        Raises:
            NotFoundException: If the value is not found
        """
        namespace = await self._get_namespace(namespace)

        if not await self._check_primary_keys(
            primary_keys=[primary_key], namespace=namespace
        ):
            return None
        else:
            await self._delete(primary_key=primary_key, namespace=namespace)

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def delete_instance_discovery(self, *, key: str) -> None:
        """
        Delete a public instance discovery key.

        Args:
            key: The public instance discovery key
        """
        pass
