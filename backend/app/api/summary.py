"""Summary router — GET /api/summary/{doc_id}"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document import Document
from app.models.schemas import SummaryResponse
from app.models.user import User
from app.services.summary_service import SummaryService

router = APIRouter()


@router.get("/{doc_id}", response_model=SummaryResponse)
async def get_summary(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.owner_id == current_user.id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.status != "done":
        raise HTTPException(
            status_code=202,
            detail=f"Document processing not complete (status: {doc.status})",
        )

    return await SummaryService().summarize(doc, db)
