from fastapi import APIRouter

from app.schemas.dataset import EvaluationDataset, EvaluationPair
from app.services.dataset_loader import load_evaluation_dataset, load_evaluation_pairs

router = APIRouter()


@router.get("/evaluation-pairs", response_model=list[EvaluationPair])
def evaluation_pairs() -> list[EvaluationPair]:
    return load_evaluation_pairs()


@router.get("/evaluation-dataset", response_model=EvaluationDataset)
def evaluation_dataset() -> EvaluationDataset:
    return load_evaluation_dataset()
