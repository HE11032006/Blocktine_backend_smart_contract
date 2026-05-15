from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.user import User
from app.models.group import Group
from app.models.member import Member
from app.models.round import Round
from app.schemas.group import GroupCreate, GroupOut, GroupJoin, GroupListOut
from app.schemas.payment import RoundOut
from app.utils.auth import get_current_user
from app.utils.helpers import generate_invite_code
from app.services.blockchain_service import BlockchainService
from app.config import settings
from datetime import datetime, timedelta

router = APIRouter()


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: GroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invite_code = generate_invite_code()
    group = Group(
        name=payload.name,
        amount_fcfa=payload.amount_fcfa,
        frequency_days=payload.frequency_days,
        max_members=payload.max_members,
        is_public=payload.is_public,
        invite_code=invite_code,
        creator_id=current_user.id,
    )
    db.add(group)
    db.flush()

    # Le créateur devient automatiquement membre
    member = Member(group_id=group.id, user_id=current_user.id, reception_rank=1)
    db.add(member)
    db.commit()
    db.refresh(group)
    return group


@router.get("", response_model=GroupListOut)
def list_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    memberships = db.query(Member).filter(
        Member.user_id == current_user.id,
        Member.is_active == True,
    ).all()
    group_ids = [m.group_id for m in memberships]
    groups = db.query(Group).filter(Group.id.in_(group_ids)).all()
    
    for g in groups:
        g.member_count = db.query(Member).filter(Member.group_id == g.id, Member.is_active == True).count()
        
    return GroupListOut(groups=groups, total=len(groups))


@router.post("/{group_id}/join", response_model=GroupOut)
def join_group(
    group_id: str,
    payload: GroupJoin,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Groupe introuvable")

    if group.invite_code != payload.invite_code:
        raise HTTPException(status_code=403, detail="Code d'invitation invalide")

    active_members = db.query(Member).filter(
        Member.group_id == group_id,
        Member.is_active == True,
    ).count()

    if active_members >= group.max_members:
        raise HTTPException(status_code=409, detail="Groupe complet")

    already_member = db.query(Member).filter(
        Member.group_id == group_id,
        Member.user_id == current_user.id,
    ).first()
    if already_member:
        raise HTTPException(status_code=409, detail="Vous êtes déjà membre de ce groupe")

    member = Member(
        group_id=group.id,
        user_id=current_user.id,
        reception_rank=active_members + 1,
    )
    db.add(member)
    db.commit()
    db.refresh(group)
    return group


@router.get("/{group_id}/rounds", response_model=List[RoundOut])
def get_rounds(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Vérifier que l'utilisateur est membre
    member = db.query(Member).filter(
        Member.group_id == group_id,
        Member.user_id == current_user.id,
        Member.is_active == True,
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="Accès refusé")

    rounds = db.query(Round).filter(Round.group_id == group_id).order_by(Round.round_number).all()
    return rounds


@router.post("/{group_id}/start", response_model=GroupOut)
def start_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Groupe introuvable")

    if group.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Seul le créateur peut démarrer la tontine")

    if group.contract_group_id is not None:
        raise HTTPException(status_code=400, detail="Tontine déjà démarrée sur la blockchain")

    # Récupérer tous les membres actifs
    members = db.query(Member).filter(Member.group_id == group_id, Member.is_active == True).all()
    if len(members) < 2:
        raise HTTPException(status_code=400, detail="Il faut au moins 2 membres pour démarrer")

    # Adresses wallet des membres
    member_addresses = []
    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        if not user or not user.wallet_address:
             raise HTTPException(status_code=400, detail=f"Membre {user.phone_number if user else 'Inconnu'} n'a pas de wallet")
        member_addresses.append(user.wallet_address)

    # Appel Blockchain
    blockchain = BlockchainService()
    try:
        # Conversion FCFA -> Wei USDC (Mock)
        # On assume 1 USDC = 655 FCFA pour le calcul on-chain si besoin
        # Mais ici on passe juste le montant configuré
        amount_usdc = group.amount_fcfa / 655.0
        amount_wei = int(amount_usdc * 10**6) # USDC a souvent 6 décimales

        # Fréquence en secondes
        frequency_sec = group.frequency_days * 24 * 3600

        # Conversion de l'UUID du groupe en uint256 pour la blockchain
        group_id_uint = int(group.id.hex, 16)
        
        # Deadline du premier tour : maintenant + fréquence
        first_deadline = int((datetime.utcnow() + timedelta(days=group.frequency_days)).timestamp())

        tx_hash = blockchain.create_group_on_chain(
            group_id_uint=group_id_uint,
            amount_usdc_wei=amount_wei,
            interval_seconds=frequency_sec,
            member_addresses=member_addresses,
            first_deadline=first_deadline
        )

        # On stocke l'ID utilisé sur la blockchain
        group.contract_group_id = group_id_uint
        db.commit()
        db.refresh(group)
        return group
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur Blockchain : {str(e)}")
@router.get("/by-code/{code}", response_model=GroupOut)
def get_group_by_code(
    code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.invite_code == code).first()
    if not group:
        raise HTTPException(status_code=404, detail="Code de tontine invalide")
    return group

@router.get("/{group_id}/members")
def get_group_members(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    members = db.query(Member).filter(Member.group_id == group_id).all()
    result = []
    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        result.append({
            "id": str(m.user_id),
            "name": "Vous" if str(user.id) == str(current_user.id) else (user.full_name if user else "Inconnu"),
            "wallet": user.wallet_address if user else "0x...",
            "status": "paid" if m.is_active else "pending", 
            "rank": m.reception_rank
        })
    return result

@router.delete("/{group_id}/leave")
def leave_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    member = db.query(Member).filter(
        Member.group_id == group_id,
        Member.user_id == current_user.id,
        Member.is_active == True
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Vous n'êtes pas membre de ce groupe")

    member.is_active = False
    
    # Trace du départ dans l'historique
    leave_tx = Payment(
        user_id=current_user.id,
        group_id=group_id,
        amount_fcfa=0,
        status="failed", # On utilise failed ou un autre statut pour marquer le départ
        kotani_ref=f"QUIT-{uuid.uuid4().hex[:8].upper()}"
    )
    db.add(leave_tx)
    db.commit()
    return {"status": "success", "message": "Vous avez quitté le groupe"}
