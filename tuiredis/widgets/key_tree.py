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

    # Type icons
    TYPE_ICONS = {
        "string": "📝",
        "list": "📋",
        "set": "🔵",
        "zset": "🏆",
        "hash": "🗂️",
        "unknown": "❓",
    }

    def __init__(self, **kwargs) -> None:
        super().__init__("🔑 Keys", **kwargs)
        self._keys: list[str] = []
        self._keys_set: set[str] = set()
        self._key_types: dict[str, str] = {}
        self._filter: str = ""
        self._next_cursor: int = 0

    def load_keys(self, keys: list[str], key_types: dict[str, str] | None = None, next_cursor: int = 0):
        """Load a list of keys into the tree, grouped by separator."""
        self._keys = keys
        self._keys_set = set(keys)
        self._key_types = key_types or {}
        self._next_cursor = next_cursor
        self._rebuild_tree()

    def append_keys(self, keys: list[str], key_types: dict[str, str], next_cursor: int):
        """Append new keys (from pagination) and rebuild the tree."""
        self._keys.extend(keys)
        self._keys_set.update(keys)
        self._key_types.update(key_types)
        self._next_cursor = next_cursor
        self._rebuild_tree()

    def filter_keys(self, pattern: str):
        """Filter the displayed keys by a substring match."""
        self._filter = pattern.lower()
        self._rebuild_tree()

    def _rebuild_tree(self):
        """Rebuild the tree from the current key list and filter."""
        self.clear()
        self.root.expand()

        filtered = self._keys
        if self._filter:
            filtered = [k for k in self._keys if self._filter in k.lower()]

        self._filtered_set = set(filtered)

        # Build hierarchy
        tree_data: dict = {}
        for key in filtered:
            parts = key.split(self.SEPARATOR)
            node = tree_data
            for part in parts:
                if part not in node:
                    node[part] = {}
                node = node[part]

        self._build_nodes(self.root, tree_data, prefix="")
        self.root.label = f"🔑 Keys ({len(filtered)})"

        if self._next_cursor != 0:
            self.root.add_leaf(f"📂 Load More... [{self._next_cursor}]", data="_LOAD_MORE_")

    def _build_nodes(self, parent: TreeNode, data: dict, prefix: str):
        """Recursively build tree nodes."""
        for name, children in sorted(data.items()):
            full_key = f"{prefix}{self.SEPARATOR}{name}" if prefix else name
            is_key = full_key in self._filtered_set

            if children:
                # Branch
                # If this branch is itself a key, we allow selecting it by assigning data.
                icon = self._get_icon(full_key) if is_key else "📁"
                node_data = full_key if is_key else None
                branch = parent.add(f"{icon} {name} ({self._count_leaves(children)})", data=node_data)

                # Expand parent and first level children, avoid expanding everything
                if not prefix:
                    branch.expand()

                self._build_nodes(branch, children, prefix=full_key)
            else:
                # Leaf node – actual Redis key
                icon = self._get_icon(full_key)
                parent.add_leaf(f"{icon} {name}", data=full_key)

    def _count_leaves(self, data: dict) -> int:
        """Count total leaf nodes under a branch."""
        count = 0
        for children in data.values():
            if children:
                count += self._count_leaves(children)
            else:
                count += 1
        return count

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
