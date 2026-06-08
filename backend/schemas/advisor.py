from __future__ import annotations

from pydantic import BaseModel, Field


class AdvisorPageContext(BaseModel):
    page_type: str = "unknown"
    path: str | None = None
    roster_id: str | None = None
    player_id: str | None = None
    player_name: str | None = None
    summary: str | None = None


class AdvisorModel(BaseModel):
    id: str
    label: str
    provider: str
    available: bool = True
    supports_tools: bool = True


class AdvisorPrompt(BaseModel):
    id: str
    label: str
    question: str


class AdvisorStatus(BaseModel):
    configured: bool
    web_search_configured: bool = False
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
    focused_roster_id: str | None = None
    page_context: AdvisorPageContext | None = None
