from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import (
    Medicine, MedicineInventory, MedicineBatch, Prescription, PrescriptionItem,
    StockTransaction, PrescriptionStatusEnum, User, RoleEnum
)
from api.dependencies import get_current_user, require_roles
from api.schemas.pharmacy import (
    DispenseRequest, MedicineResponse, MedicineCreateRequest, MedicineUpdateRequest,
    StockInRequest, StockOutRequest, BatchResponse, StockTransactionResponse,
    PharmacyDashboardStatsResponse, PrescriptionCreateRequest, PrescriptionResponse
)
from core.services.prescription_service import (
    create_prescription, get_prescription_detail, dispense_prescription as service_dispense_prescription,
    InvalidPrescriptionDataError, PrescriptionServiceError,
    PrescriptionNotFoundError, PrescriptionPermissionError
)
from core.services.pharmacy_service import (
    create_medicine, update_medicine, get_medicine, list_medicines as service_list_medicines,
    stock_in, stock_out, get_low_stock_medicines, get_expired_batches,
    get_expiring_soon_batches, get_pharmacy_dashboard_stats, list_stock_transactions,
    PharmacyServiceError, MedicineNotFoundError, BatchNotFoundError,
    InvalidInventoryDataError, InsufficientInventoryError
)

router = APIRouter(prefix="/pharmacy", tags=["Pharmacy"])


@router.get("/dashboard-stats", response_model=PharmacyDashboardStatsResponse)
def get_dashboard_stats_api(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.PHARMACIST, RoleEnum.ADMIN]))
):
    """Returns aggregated inventory health, risk alerts, valuation, and fulfillment statistics."""
    stats = get_pharmacy_dashboard_stats(db)
    return PharmacyDashboardStatsResponse(
        total_medicines=stats["total_medicines"],
        total_stock_units=stats["total_stock_units"],
        total_batches=stats["total_batches"],
        low_stock_count=stats["low_stock_count"],
        expired_batches_count=stats["expired_batches_count"],
        expired_units_count=stats["expired_units_count"],
        expiring_soon_batches_count=stats["expiring_soon_batches_count"],
        expiring_soon_units_count=stats["expiring_soon_units_count"],
        valuation_cost=stats["valuation_cost"],
        valuation_retail=stats["valuation_retail"],
        pending_prescriptions_count=stats["pending_prescriptions_count"],
        dispensed_prescriptions_count=stats["dispensed_prescriptions_count"],
        total_prescriptions_count=stats["total_prescriptions_count"]
    )


@router.get("/medicines", response_model=List[MedicineResponse])
def list_medicines_api(
    search: Optional[str] = Query(None, description="Search term"),
    category: Optional[str] = Query(None, description="Filter category"),
    stock_status: Optional[str] = Query(None, description="all, low_stock, out_of_stock, adequate"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves all pharmacy medicines with real-time stock levels."""
    return service_list_medicines(db_session=db, search=search, category=category, stock_status=stock_status)


@router.post("/medicines", response_model=MedicineResponse, status_code=status.HTTP_201_CREATED)
def create_medicine_api(
    payload: MedicineCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.PHARMACIST, RoleEnum.ADMIN]))
):
    """Adds a new drug SKU to the hospital formulary catalog."""
    try:
        med = create_medicine(
            db_session=db,
            name=payload.name,
            generic_name=payload.generic_name,
            category=payload.category,
            unit=payload.unit,
            unit_price=payload.unit_price,
            purchase_price=payload.purchase_price,
            reorder_level=payload.reorder_level,
            supplier=payload.supplier,
            manufacturer=payload.manufacturer,
            description=payload.description,
            actor_id=current_user.id
        )
        return med
    except InvalidInventoryDataError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PharmacyServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/medicines/{medicine_id}", response_model=MedicineResponse)
def update_medicine_api(
    medicine_id: int,
    payload: MedicineUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.PHARMACIST, RoleEnum.ADMIN]))
):
    """Updates an existing formulary drug SKU."""
    try:
        med = update_medicine(
            db_session=db,
            medicine_id=medicine_id,
            name=payload.name,
            generic_name=payload.generic_name,
            category=payload.category,
            unit=payload.unit,
            unit_price=payload.unit_price,
            purchase_price=payload.purchase_price,
            reorder_level=payload.reorder_level,
            supplier=payload.supplier,
            manufacturer=payload.manufacturer,
            description=payload.description,
            actor_id=current_user.id
        )
        return med
    except MedicineNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Medicine #{medicine_id} not found")
    except InvalidInventoryDataError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/stock-in")
def stock_in_api(
    payload: StockInRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.PHARMACIST, RoleEnum.ADMIN]))
):
    """Receives new batch inventory stock into the pharmacy."""
    try:
        res = stock_in(
            db_session=db,
            medicine_id=payload.medicine_id,
            batch_number=payload.batch_number,
            expiry_date=payload.expiry_date,
            quantity=payload.quantity,
            purchase_cost=payload.purchase_cost,
            selling_price=payload.selling_price,
            supplier=payload.supplier,
            performed_by_id=current_user.id,
            notes=payload.notes
        )
        return {"message": "Stock received successfully", "result": res}
    except (MedicineNotFoundError, BatchNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referenced medicine not found")
    except InvalidInventoryDataError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/stock-out")
def stock_out_api(
    payload: StockOutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.PHARMACIST, RoleEnum.ADMIN]))
):
    """Deducts stock from a specific batch for write-off, damage, expired discard, or adjustment."""
    try:
        res = stock_out(
            db_session=db,
            batch_id=payload.batch_id,
            quantity=payload.quantity,
            reason=payload.reason,
            performed_by_id=current_user.id,
            notes=payload.notes
        )
        return {"message": "Stock deducted successfully", "result": res}
    except BatchNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referenced batch not found")
    except InsufficientInventoryError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InvalidInventoryDataError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/batches", response_model=List[BatchResponse])
def list_batches_api(
    medicine_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, description="active, expiring_soon, expired, all"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.PHARMACIST, RoleEnum.ADMIN]))
):
    """Retrieves medicine batches with expiration tracking."""
    query = db.query(MedicineInventory)
    if medicine_id:
        query = query.filter(MedicineInventory.medicine_id == medicine_id)

    today = date.today()
    if status_filter == "expired":
        query = query.filter(MedicineInventory.expiry_date < today, MedicineInventory.quantity_in_stock > 0)
    elif status_filter == "expiring_soon":
        from datetime import timedelta
        query = query.filter(
            MedicineInventory.expiry_date >= today,
            MedicineInventory.expiry_date <= today + timedelta(days=30),
            MedicineInventory.quantity_in_stock > 0
        )
    elif status_filter == "active":
        query = query.filter(MedicineInventory.expiry_date >= today, MedicineInventory.quantity_in_stock > 0)

    return query.order_by(MedicineInventory.expiry_date.asc()).all()


@router.get("/transactions", response_model=List[StockTransactionResponse])
def list_transactions_api(
    medicine_id: Optional[int] = Query(None),
    transaction_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.PHARMACIST, RoleEnum.ADMIN]))
):
    """Returns chronological audit records of inventory movements."""
    return list_stock_transactions(db_session=db, medicine_id=medicine_id, transaction_type=transaction_type, limit=limit)


@router.get("/low-stock", response_model=List[MedicineResponse])
def get_low_stock_api(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.PHARMACIST, RoleEnum.ADMIN]))
):
    """Retrieves all medicines below reorder threshold."""
    return get_low_stock_medicines(db)


@router.get("/expired", response_model=List[BatchResponse])
def get_expired_batches_api(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.PHARMACIST, RoleEnum.ADMIN]))
):
    """Retrieves all expired batches containing on-hand inventory."""
    return get_expired_batches(db)


@router.get("/expiring-soon", response_model=List[BatchResponse])
def get_expiring_soon_batches_api(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.PHARMACIST, RoleEnum.ADMIN]))
):
    """Retrieves active batches expiring within specified days (default 30)."""
    return get_expiring_soon_batches(db, days=days)


@router.post("/dispense")
def dispense_prescription(
    payload: DispenseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.PHARMACIST, RoleEnum.ADMIN]))
):
    """
    Dispenses prescribed medications using First-Expiring, First-Out (FEFO)
    batch deduction logic and updates prescription fulfillment status.
    """
    try:
        result = service_dispense_prescription(
            db_session=db,
            prescription_id=payload.prescription_id,
            actor_id=current_user.id,
            item_dispensations=payload.items
        )
        return {
            "message": "Prescription successfully dispensed and inventory updated",
            "status": result["status"],
            "units_dispensed": result["units_dispensed"],
            "deducted_batches": result["deducted_batches"]
        }
    except PrescriptionNotFoundError:
        raise HTTPException(status_code=404, detail="Prescription not found")
    except PrescriptionServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/prescriptions", response_model=PrescriptionResponse, status_code=status.HTTP_201_CREATED)
def create_prescription_api(
    payload: PrescriptionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.DOCTOR, RoleEnum.ADMIN]))
):
    """
    Creates an electronic prescription containing one or more validated medicines.
    """
    items_data = [item.dict() for item in payload.items]
    try:
        rx = create_prescription(
            db_session=db,
            doctor_id=current_user.id,
            patient_id=payload.patient_id,
            items=items_data,
            medical_record_id=payload.medical_record_id,
            notes=payload.notes,
            actor_id=current_user.id
        )
        return rx
    except InvalidPrescriptionDataError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PrescriptionServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/prescriptions/{rx_id}", response_model=PrescriptionResponse)
def get_prescription_api(
    rx_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieves electronic prescription details with role-based confidentiality.
    """
    try:
        rx = get_prescription_detail(
            db_session=db,
            prescription_id=rx_id,
            requester_user_id=current_user.id,
            requester_role=current_user.role.value
        )
        return rx
    except PrescriptionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription not found")
    except PrescriptionPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
