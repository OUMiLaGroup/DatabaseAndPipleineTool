import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.segment import Segment,SegmentStatus 
from db.models.frame import Frame
logger = logging.getLogger(__name__)


class SegmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, route_id: str, segment_id: int) -> Segment | None:
        # get_by_id retrieves a Segment entity composite primary key of route_id and segment_id.
        return await self._session.get(Segment, {"route_id": route_id, "segment_id": segment_id})

    async def list_all(self) -> list[Segment]:
        stmt = select(Segment).order_by(Segment.created_at.desc())
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def get_by_status(self, status: SegmentStatus) -> list[Segment]:
        stmt = (
            select(Segment)
            .where(Segment.status == status)
            .order_by(Segment.created_at.desc()) # order by created_at desc to get the most recent.
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def get_by_route(self, route_id: str) -> list[Segment]:
        stmt = (
            select(Segment)
            .where(Segment.route_id == route_id)
            .order_by(Segment.segment_id.asc())
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def count_by_route_segment(self, route_id: str, segment_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(Frame)
            .where(Frame.route_id == route_id)
            .where(Frame.segment_id == segment_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_next_by_status(self, status: SegmentStatus) -> Segment | None:
        stmt = (
            select(Segment)
            .where(Segment.status == status)
            .order_by(Segment.created_at.asc())
            .limit(1)
        )
        result = await self._session.scalars(stmt)
        return result.first()

    async def create(
        self,
        route_id: str,
        segment_id: int,
        start_time,
        end_time,
        status: SegmentStatus,
    ) -> Segment: # creat new segmetn enity
        segment = Segment(
            route_id=route_id,
            segment_id=segment_id,
            start_time=start_time,
            end_time=end_time,
            status=status,
            segment_meta=None,
        )
        self._session.add(segment)
        await self._session.flush() # persist the new segment entity to the database
        return segment

    async def save(self, segment: Segment) -> Segment:
        self._session.add(segment)
        await self._session.flush()
        return segment

    async def delete(self, segment: Segment) -> None:
        await self._session.delete(segment)
        await self._session.flush()
