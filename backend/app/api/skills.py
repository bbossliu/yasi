from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.models import SkillMastery, SkillNode, User
from app.schemas import ClearanceOut, ModuleTree, SkillNodeOut, TargetBandUpdate
from app.services.mastery_rules import evaluate_all, evaluate_node
from app.services.module_clearance import clearance_summary

router = APIRouter(prefix="/api")


def get_session(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


@router.get("/skills/tree", response_model=list[ModuleTree])
def skill_tree(session=Depends(get_session)):
    nodes = session.scalars(select(SkillNode).order_by(SkillNode.sort_order, SkillNode.id)).all()
    masteries = {m.node_id: m for m in session.scalars(select(SkillMastery)).all()}
    modules: dict[str, list[SkillNodeOut]] = {}
    for n in nodes:
        m = masteries.get(n.id)
        status = m.status if m else "unseen"
        can_verify = status != "verified" and evaluate_node(n, session, 1)
        modules.setdefault(n.module, []).append(SkillNodeOut(
            id=n.id, code=n.code, title=n.title, parent_id=n.parent_id,
            status=status, can_verify=can_verify, sort_order=n.sort_order))
    return [ModuleTree(module=mod, nodes=ns) for mod, ns in modules.items()]


@router.post("/skills/evaluate")
def evaluate(session=Depends(get_session)):
    return {"updated": evaluate_all(session, 1)}


@router.get("/skills/clearance", response_model=list[ClearanceOut])
def clearance(session=Depends(get_session)):
    return clearance_summary(session, 1)


@router.get("/skills/exam-eligibility")
def exam_eligibility(session=Depends(get_session)):
    nodes = session.scalars(select(SkillNode)).all()
    learned_ids = set(session.scalars(
        select(SkillMastery.node_id).where(SkillMastery.user_id == 1)).all())
    missing: dict[str, int] = {}
    for n in nodes:
        if n.id not in learned_ids:
            missing[n.module] = missing.get(n.module, 0) + 1
    return {"eligible": not missing, "missing": missing}


@router.get("/skills/target")
def get_target(session=Depends(get_session)):
    return {"target_band": session.get(User, 1).target_band}


@router.put("/skills/target")
def put_target(payload: TargetBandUpdate, session=Depends(get_session)):
    user = session.get(User, 1)
    user.target_band = payload.target_band
    session.commit()
    return {"target_band": user.target_band}
