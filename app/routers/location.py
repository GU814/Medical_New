"""地理位置路由 - 用户常用地点 CRUD"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.schemas import LocationAdd, LocationItem
from app.services import location_service

router = APIRouter(prefix="/api/location", tags=["地理位置"])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[LocationItem])
async def list_locations(user_id: int = Depends(get_current_user)):
    return location_service.list_locations(user_id)


@router.post("", response_model=LocationItem, status_code=status.HTTP_201_CREATED)
async def add_location(req: LocationAdd, user_id: int = Depends(get_current_user)):
    lid = location_service.create_location(user_id, req)
    return LocationItem(
        id=lid,
        name=req.name,
        address=req.address,
        latitude=req.latitude,
        longitude=req.longitude,
        is_default=req.is_default,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@router.delete("/{loc_id}")
async def delete_location(loc_id: int, user_id: int = Depends(get_current_user)):
    location_service.delete_location(user_id, loc_id)
    return {"ok": True}


@router.post("/{loc_id}/default")
async def set_default(loc_id: int, user_id: int = Depends(get_current_user)):
    location_service.set_default(user_id, loc_id)
    return {"ok": True}
