from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

QuestionId = Annotated[
    str,
    Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$"),
]
OptionId = Annotated[str, Field(min_length=1, max_length=100)]


class QuestionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instructions: JsonValue | None = None


class NoulQuestion(QuestionBase):
    type: Literal["noul"]
    criteria: dict[Literal["true", "false"], JsonValue] | None = None


class ChoiceQuestion(QuestionBase):
    type: Literal["choice"]
    criteria: dict[OptionId, JsonValue] = Field(min_length=1, max_length=255)


class ScoreQuestion(QuestionBase):
    type: Literal["score"]
    criteria: list[JsonValue] = Field(min_length=1, max_length=10)


Question = Annotated[
    NoulQuestion | ChoiceQuestion | ScoreQuestion,
    Field(discriminator="type"),
]


class SystemOneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: Literal["clef-flash"]
    state: JsonValue
    questions: dict[QuestionId, Question] = Field(min_length=1, max_length=64)
