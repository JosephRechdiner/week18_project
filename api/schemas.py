from pydantic import BaseModel, Field
from typing import Literal

class Order(BaseModel):
    order_id: str = Field(..., description="Special order id")
    pizza_type: str = Field(..., description="The type of the pizza")
    size: Literal["Small", "Medium", "Large", "Family"] = Field(..., description="The size of the pizza")
    quantity: int = Field(..., gt=0, description="The quantity of the pizza in the order")
    is_delivery: bool = Field(..., description="Has the pizza delivered")
    special_instructions: str = Field("", description="Any special instructions")