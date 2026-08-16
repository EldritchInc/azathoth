"""Deterministic matching of tool definitions against requirements."""

from azathoth.tools.definition import ToolDefinition
from azathoth.tools.requirements import (
    ToolRequirement,
    ToolRequirementMatch,
    ToolRequirements,
)


class ToolMatcher:
    """Match tool definitions against deterministic requirements."""

    @staticmethod
    def matches(
        definition: ToolDefinition,
        requirement: ToolRequirement,
    ) -> bool:
        """Return whether a tool definition satisfies one requirement."""

        if definition.name != requirement.name:
            return False

        return requirement.version is None or definition.version == requirement.version

    def match(
        self,
        definitions: tuple[ToolDefinition, ...],
        requirements: ToolRequirements,
    ) -> tuple[ToolRequirementMatch, ...]:
        """Match requirements against available tool definitions."""

        return tuple(
            ToolRequirementMatch(
                requirement=requirement,
                matched=any(
                    self.matches(
                        definition,
                        requirement,
                    )
                    for definition in definitions
                ),
            )
            for requirement in requirements.requirements
        )
