from __future__ import annotations

import anyio
from slimconfig import output_schema

from contract import TOOLS, Tool
from plugin.__main__ import IMPLEMENTATIONS, list_tools


def test_every_tool_is_implemented() -> None:
    assert set(IMPLEMENTATIONS) == set(Tool)


def test_the_server_offers_the_contract_schemas() -> None:
    served = {tool.name: tool for tool in anyio.run(list_tools)}
    assert set(served) == {tool.value for tool in Tool}
    for tool, (given, made) in TOOLS.items():
        assert served[tool.value].inputSchema == output_schema(given)
        assert served[tool.value].outputSchema == output_schema(made)
