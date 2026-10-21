"""Database models. Importing this package registers every table with SQLAlchemy."""

from app.models.corrective_action import ActionFollowUp, CorrectiveAction
from app.models.defect import DefectEntry
from app.models.disposition import DispositionRecord
from app.models.inspection import Inspection
from app.models.reference_data import DefectCategory, SeverityLevel

__all__ = [
    "ActionFollowUp",
    "CorrectiveAction",
    "DefectCategory",
    "DefectEntry",
    "DispositionRecord",
    "Inspection",
    "SeverityLevel",
]
