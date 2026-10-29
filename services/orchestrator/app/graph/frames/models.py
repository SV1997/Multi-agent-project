"""What a query frame is.

Why this file exists: the examiner asked for "a Frame or a DAG structure for queries that can be used to
localize the search". A frame is the answer to "what kind of question is this?": a named type of question,
tied to the part of the policy documents that can answer it, and to the pieces of information that kind of
question needs before it can be answered properly.

Problem it solves: a plain search over a whole domain mixes rules from unrelated parts of the policy. A frame
names the categories to search, and lists the slots (facts such as the leave type) the answer depends on, so
the system can ask for a missing one instead of guessing.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Frame:
    frame_id: str                                   
    domain: str
    description: str                               
    categories: tuple[str, ...]                     
    required_slots: dict[str, str] = field(default_factory=dict)   
    optional_slots: tuple[str, ...] = ()           
    origin: str = "auto"                           

    @property
    def slot_names(self) -> tuple[str, ...]:
        return tuple(self.required_slots) + tuple(self.optional_slots)
