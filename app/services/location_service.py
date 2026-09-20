"""地理位置服务 - 用户常用地点(选点保存)"""

import logging

from app.db import repositories

logger = logging.getLogger(__name__)


def create_location(user_id: int, req) -> int:
    return repositories.add_location(
        user_id, req.name, req.address, req.latitude, req.longitude, req.is_default
    )


def list_locations(user_id: int) -> list:
    return repositories.list_locations(user_id)


def delete_location(user_id: int, loc_id: int):
    repositories.delete_location(loc_id, user_id)


def set_default(user_id: int, loc_id: int):
    repositories.set_default_location(loc_id, user_id)
