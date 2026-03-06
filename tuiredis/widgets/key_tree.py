"""Key tree browser widget — organizes Redis keys in a tree hierarchy."""

from __future__ import annotations

from textual.message import Message
from textual.widgets import Tree
from textual.widgets._tree import TreeNode


class KeyTree(Tree):
    """A tree widget that displays Redis keys grouped by separator."""

    SEPARATOR = ":"

    class KeySelected(Message):
        """Emitted when a leaf key is selected."""

        def __init__(self, key: str) -> None:
            self.key = key
            super().__init__()

    class LoadMoreClicked(Message):
        """Emitted when the Load More node is selected."""

        pass

    class SelectionChanged(Message):
        """Emitted when the multi-selection set changes."""

        def __init__(self, selected_keys: set[str]) -> None:
            self.selected_keys = selected_keys
            super().__init__()

    # Type icons
    TYPE_ICONS = {
        "string": "📝",
        "list": "📋",
        "set": "🔵",
        "zset": "🏆",
        "hash": "📂",
        "unknown": "❓",
    }

    def __init__(self, **kwargs) -> None:
        super().__init__("🔑 Keys", **kwargs)
        self._keys: list[str] = []
        self._keys_set: set[str] = set()
        self._key_types: dict[str, str] = {}
        self._ttl_map: dict[str, int] = {}  # key → TTL (-1 no expiry, -2 missing)
        self._filter: str = ""
        self._next_cursor: int = 0
        self._selected_keys: set[str] = set()  # multi-select

    def load_keys(
        self,
        keys: list[str],
        key_types: dict[str, str] | None = None,
        next_cursor: int = 0,
        ttl_map: dict[str, int] | None = None,
    ) -> None:
        """Load a list of keys into the tree, grouped by separator."""
        self._keys = keys
        self._keys_set = set(keys)
        self._key_types = key_types or {}
        self._ttl_map = ttl_map or {}
        self._next_cursor = next_cursor
        self._selected_keys.clear()
        self._rebuild_tree()

    def update_ttls(self, ttl_map: dict[str, int]) -> None:
        """Update TTL data and rebuild the tree to show expiry indicators."""
        self._ttl_map = ttl_map
        self._rebuild_tree()

    def append_keys(
        self,
        keys: list[str],
        key_types: dict[str, str],
        next_cursor: int,
        ttl_map: dict[str, int] | None = None,
    ) -> None:
        """Append new keys (from pagination) and rebuild the tree."""
        self._keys.extend(keys)
        self._keys_set.update(keys)
        self._key_types.update(key_types)
        if ttl_map:
            self._ttl_map.update(ttl_map)
        self._next_cursor = next_cursor
        self._rebuild_tree()

    def filter_keys(self, pattern: str) -> None:
        """Filter the displayed keys by a substring match."""
        self._filter = pattern.lower()
        self._rebuild_tree()

    def bulk_delete_selected(self) -> set[str]:
        """Return and clear the current selection (caller does the actual delete)."""
        keys = set(self._selected_keys)
        self._selected_keys.clear()
        self._rebuild_tree()
        return keys

    def _rebuild_tree(self) -> None:
        """Rebuild the tree from the current key list and filter."""
        self.clear()
        self.root.expand()

        filtered = self._keys
        if self._filter:
            filtered = [k for k in self._keys if self._filter in k.lower()]

        self._filtered_set = set(filtered)

        # Build hierarchy with leaf-count tracking in a single pass.
        tree_data: dict = {}
        for key in filtered:
            parts = key.split(self.SEPARATOR)
            node = tree_data
            path_nodes = []
            for part in parts:
                if part not in node:
                    node[part] = [{}, 0]
                path_nodes.append(node[part])
                node = node[part][0]
            for ancestor in path_nodes:
                ancestor[1] += 1

        self._build_nodes(self.root, tree_data, prefix="")
        self.root.label = f"🔑 Keys ({len(filtered)})"

        if self._selected_keys:
            self.root.label = f"🔑 Keys ({len(filtered)})  ☑ {len(self._selected_keys)} selected"

        if self._next_cursor != 0:
            self.root.add_leaf(f"📂 Load More... [{self._next_cursor}]", data="_LOAD_MORE_")

    def _get_ttl_suffix(self, key: str) -> str:
        """Return a TTL indicator suffix for a key."""
        ttl = self._ttl_map.get(key, -1)
        if ttl == -1 or ttl == -2:
            return ""
        if ttl < 60:
            return f" 🔴{ttl}s"
        if ttl < 3600:
            return f" ⏱{ttl}s"
        return f" ⏱{ttl // 3600}h"

    def _build_nodes(self, parent: TreeNode, data: dict, prefix: str) -> None:
        """Recursively build tree nodes."""
        for name, (children, leaf_count) in sorted(data.items()):
            full_key = f"{prefix}{self.SEPARATOR}{name}" if prefix else name
            is_key = full_key in self._filtered_set

            if children:
                icon = self._get_icon(full_key) if is_key else "📁"
                node_data = full_key if is_key else None
                branch = parent.add(f"{icon} {name} ({leaf_count})", data=node_data)
                if not prefix:
                    branch.expand()
                self._build_nodes(branch, children, prefix=full_key)
            else:
                icon = self._get_icon(full_key)
                selected_prefix = "☑ " if full_key in self._selected_keys else ""
                ttl_suffix = self._get_ttl_suffix(full_key)
                parent.add_leaf(f"{selected_prefix}{icon} {name}{ttl_suffix}", data=full_key)

    def _get_icon(self, key: str) -> str:
        key_type = self._key_types.get(key, "unknown")
        return self.TYPE_ICONS.get(key_type, "❓")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle node selection — emit KeySelected for leaf nodes."""
        node = event.node
        if node.data == "_LOAD_MORE_":
            self.post_message(self.LoadMoreClicked())
        elif node.data is not None:
            self.post_message(self.KeySelected(node.data))

    def on_key(self, event) -> None:
        """Space bar toggles multi-selection on the focused leaf node."""
        if event.key != "space":
            return
        cursor_node = self.cursor_node
        if cursor_node is None:
            return
        key = cursor_node.data
        if key is None or key == "_LOAD_MORE_":
            return
        if key in self._selected_keys:
            self._selected_keys.discard(key)
        else:
            self._selected_keys.add(key)
        self._rebuild_tree()
        self.post_message(self.SelectionChanged(set(self._selected_keys)))
        event.stop()
