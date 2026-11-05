"""The candidate's identity: stored apart from the CV, put back by code at render time.

`llm` can never import this module, which an import contract enforces.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

IdentityValue = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]


class Identity(BaseModel):
    # The client always receives and sends every field: one schema, all fields required.
    model_config = ConfigDict(
        json_schema_mode_override="serialization",
        json_schema_serialization_defaults_required=True,
    )

    name: IdentityValue = ""
    email: IdentityValue = ""
    phone: IdentityValue = ""
    address: IdentityValue = ""
    linkedin: IdentityValue = ""
    github: IdentityValue = ""

    def contact_values(self) -> list[str]:
        values = (self.email, self.phone, self.address, self.linkedin, self.github)
        return [value for value in values if value]
