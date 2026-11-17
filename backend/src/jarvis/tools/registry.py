"""Tool registry. The production registry is built in one place and never includes test tools."""

from __future__ import annotations

from jarvis.tools.contract import AnyTool, Recovery, Risk


class ToolContractError(ValueError):
    pass


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AnyTool] = {}

    def register(self, tool: AnyTool) -> None:
        name = getattr(tool, "name", "")
        if not name:
            raise ToolContractError("tool has no name")
        if name in self._tools:
            raise ToolContractError(f"tool {name!r} already registered")
        if tool.side_effects and tool.recovery is None:
            raise ToolContractError(
                f"side-effecting tool {name!r} must declare a recovery strategy"
            )
        if tool.idempotent and tool.recovery not in (None, Recovery.IDEMPOTENT):
            raise ToolContractError(f"idempotent tool {name!r} must use IDEMPOTENT recovery")
        if tool.recovery is Recovery.IDEMPOTENT and not tool.idempotent:
            raise ToolContractError(
                f"tool {name!r} claims IDEMPOTENT recovery but is not idempotent"
            )
        if tool.risk is Risk.HIGHEST and tool.category is None:
            raise ToolContractError(f"highest-risk tool {name!r} needs an approval category")
        if tool.timeout_s <= 0:
            raise ToolContractError(f"tool {name!r} needs a positive timeout")
        self._tools[name] = tool

    def get(self, name: str) -> AnyTool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)


def build_production_registry() -> ToolRegistry:
    """Every tool available in a real build. Empty until the file tool lands in M5."""
    return ToolRegistry()
