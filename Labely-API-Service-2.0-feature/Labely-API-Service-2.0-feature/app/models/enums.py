import enum


class ProcessStatusEnum(str, enum.Enum):
    PENDING = "Pending"
    PROCESSING = "Processing"
    COMPLETED = "Completed"
    PARTIAL = "Partial"
    FAILED = "Failed"

class TrackingStatusEnum(str, enum.Enum):
    NOT_YET = "Not Yet"
    GENERATED = "Generated"
    NO_LABEL = "No Label"

class ShipmentStatusEnum(str, enum.Enum):
    PENDING = "Pending"
    PROCESSING = "Processing"
    COMPLETED = "Completed"
    FAILED = "Failed"

class BatchStatusEnum(str, enum.Enum):  # Add this new enum
    PENDING = "Pending"
    PROCESSING = "Processing"
    COMPLETED = "Completed"
    FAILED = "Failed"
