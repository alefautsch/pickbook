from __future__ import annotations

from pydantic import BaseModel, Field


class AdvisorModel(BaseModel):
    id: str
    label: str
    provider: str


class AdvisorPrompt(BaseModel):
    id: str
    label: str
    question: str


class AdvisorStatus(BaseModel):
    configured: bool
    default_model: str
    models: list[AdvisorModel] = Field(default_factory=list)
    prompts: list[AdvisorPrompt] = Field(default_factory=list)


class AdvisorMessage(BaseModel):
    role: str
    content: str


class AdvisorChatRequest(BaseModel):
    league_id: str
    question: str = ""
    prompt_id: str | None = None
    model_id: str = "claude-sonnet-4-6"
    messages: list[AdvisorMessage] = Field(default_factory=list)
