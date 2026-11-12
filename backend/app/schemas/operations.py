from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator


Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Quantity = Annotated[int, Field(ge=0, le=2_147_483_647)]


class MachineWrite(BaseModel):
    code: Code
    name: Name
    status: Literal["running", "idle", "maintenance", "offline"]


class StockWrite(BaseModel):
    sku: Code
    name: Name
    unit: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
    reorder_point: Quantity


class StockMovement(BaseModel):
    delta: int = Field(ge=-2_147_483_647, le=2_147_483_647)
    reason: Name

    @model_validator(mode="after")
    def validate_delta(self):
        if self.delta == 0:
            raise ValueError("Enter a positive or negative quantity")
        return self


class RunWrite(BaseModel):
    machine_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    job_id: int | None = Field(default=None, gt=0)
    production_date: date
    planned_minutes: int = Field(gt=0, le=1440)
    run_minutes: int = Field(ge=0, le=1440)
    ideal_cycle_seconds: int = Field(gt=0, le=86400)
    units_produced: Quantity
    units_rejected: Quantity

    @model_validator(mode="after")
    def validate_run(self):
        if self.run_minutes > self.planned_minutes:
            raise ValueError("Run time cannot exceed planned time")
        if self.units_rejected > self.units_produced:
            raise ValueError("Rejected units cannot exceed production")
        if self.units_produced * self.ideal_cycle_seconds > self.run_minutes * 60:
            raise ValueError("Output exceeds the capacity implied by the ideal cycle and run time")
        return self


class InspectionWrite(BaseModel):
    run_id: int = Field(gt=0)
    inspected: int = Field(gt=0, le=2_147_483_647)
    rejected: Quantity
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_counts(self):
        if self.rejected > self.inspected:
            raise ValueError("Rejected units cannot exceed inspected units")
        return self
