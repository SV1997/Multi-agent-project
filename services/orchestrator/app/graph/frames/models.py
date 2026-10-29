"""What a query frame is: a named kind of question, tied to the policy categories that can answer it."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Frame:
    frame_id: str                       # "<domain>.<name>", for example "hr.leave_entitlement"
    domain: str
    description: str                    # shown to the model in the menu and in the scope prompt, so write it for the model
    categories: tuple[str, ...]         # taxonomy categories to search; a parent also covers everything below it
