from fastapi import APIRouter, Query

from app.schemas.dataset import BatchExtractResponse, EvaluationDataset, EvaluationPair
from app.services.dataset_loader import load_evaluation_dataset, load_evaluation_pairs
from app.services.tag_extractor import batch_extract_dataset_tags

router = APIRouter()


@router.get("/evaluation-pairs", response_model=list[EvaluationPair])
def evaluation_pairs() -> list[EvaluationPair]:
    return load_evaluation_pairs()


@router.get("/evaluation-dataset", response_model=EvaluationDataset)
def evaluation_dataset() -> EvaluationDataset:
    return load_evaluation_dataset()


@router.post("/evaluation-dataset/batch-extract-tags", response_model=BatchExtractResponse)
def batch_extract_tags(limit: int | None = Query(default=None, ge=1)):
    return BatchExtractResponse(**batch_extract_dataset_tags(limit=limit))
