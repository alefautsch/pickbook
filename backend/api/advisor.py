from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.schemas.advisor import AdvisorChatRequest, AdvisorStatus
from backend.services.advisor_service import advisor_status, stream_advisor_chat

router = APIRouter(prefix="/advisor", tags=["advisor"])


@router.get("/status", response_model=AdvisorStatus)
def read_advisor_status() -> AdvisorStatus:
    return AdvisorStatus(**advisor_status())


@router.post("/chat")
def advisor_chat(
    body: AdvisorChatRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    try:
        messages = (
            [{"role": m.role, "content": m.content} for m in body.messages]
            if body.messages
            else None
        )

        def event_stream() -> Iterator[str]:
            try:
                for chunk in stream_advisor_chat(
                    db,
                    league_id=body.league_id,
                    question=body.question,
                    prompt_id=body.prompt_id,
                    model_id=body.model_id,
                    messages=messages,
                ):
                    yield f"data: {json.dumps({'text': chunk})}\n\n"
                yield "data: [DONE]\n\n"
            except ValueError as exc:
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
