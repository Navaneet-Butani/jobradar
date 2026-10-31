"""Base repository with common database operations."""

import logging
from typing import Dict, List, Optional, Any, Union, TypeVar, Generic, Type
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, delete, update, func, and_, or_, desc, asc
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..core.database import db
from ..core.exceptions import ValidationError, NotFoundError
from ..models.base import ProcessingStats

T = TypeVar('T')
logger = logging.getLogger(__name__)


class BaseRepository(Generic[T]):
    """Base repository class with common CRUD operations."""
    
    def __init__(self, model: Type[T]):
        """Initialize repository with SQLAlchemy model."""
        self.model = model
        
    def _fit_lengths(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Truncate strings to their VARCHAR(n) limit. Sources send oversized
        values (e.g. a location listing 100 countries) and one long field
        should not drop the whole record."""
        columns = self.model.__table__.columns
        out = dict(data)
        for key, value in data.items():
            col = columns.get(key)
            limit = getattr(getattr(col, "type", None), "length", None)
            if isinstance(value, str) and limit and len(value) > limit:
                out[key] = value[:limit]
        return out

    async def create(self, data: Dict[str, Any], session: Optional[AsyncSession] = None) -> T:
        """Create a new record."""
        if session is None:
            session = db.session
            
        try:
            instance = self.model(**self._fit_lengths(data))
            session.add(instance)
            await session.commit()
            await session.refresh(instance)
            return instance
        except IntegrityError as e:
            await session.rollback()
            # Usually two concurrent jobs creating the same company/posting in one
            # batch; callers treat it as "already exists". One line, not a SQL dump.
            reason = str(getattr(e, "orig", e)).splitlines()[0]
            logger.info(f"Integrity conflict creating {self.model.__name__}: {reason}")
            raise ValidationError(f"Data validation failed: {str(e)}")
        except Exception as e:
            await session.rollback()
            logger.error(f"Error creating {self.model.__name__}: {e}")
            raise
            
    async def get_by_id(self, id: int, session: Optional[AsyncSession] = None) -> Optional[T]:
        """Get record by ID."""
        if session is None:
            session = db.session
            
        try:
            result = await session.execute(select(self.model).where(self.model.id == id))
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching {self.model.__name__} by ID {id}: {e}")
            raise
            
    async def get_by_uuid(self, uuid: str, session: Optional[AsyncSession] = None) -> Optional[T]:
        """Get record by UUID (if model has uuid field)."""
        if session is None:
            session = db.session
            
        if not hasattr(self.model, 'uuid'):
            raise ValueError(f"Model {self.model.__name__} does not have uuid field")
            
        try:
            result = await session.execute(select(self.model).where(self.model.uuid == uuid))
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching {self.model.__name__} by UUID {uuid}: {e}")
            raise
            
    async def get_by_field(self, field_name: str, value: Any, session: Optional[AsyncSession] = None) -> Optional[T]:
        """Get record by any field."""
        if session is None:
            session = db.session
            
        if not hasattr(self.model, field_name):
            raise ValueError(f"Model {self.model.__name__} does not have field {field_name}")
            
        try:
            field = getattr(self.model, field_name)
            result = await session.execute(select(self.model).where(field == value))
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching {self.model.__name__} by {field_name}={value}: {e}")
            raise
            
    async def get_many(
        self, 
        filters: Optional[Dict[str, Any]] = None,
        offset: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = False,
        load_relations: Optional[List[str]] = None,
        session: Optional[AsyncSession] = None
    ) -> List[T]:
        """Get multiple records with filtering, pagination, and ordering."""
        if session is None:
            session = db.session
            
        try:
            query = select(self.model)
            
            # Apply filters
            if filters:
                filter_conditions = []
                for field_name, value in filters.items():
                    if hasattr(self.model, field_name):
                        field = getattr(self.model, field_name)
                        if isinstance(value, list):
                            filter_conditions.append(field.in_(value))
                        else:
                            filter_conditions.append(field == value)
                if filter_conditions:
                    query = query.where(and_(*filter_conditions))
                    
            # Apply ordering
            if order_by and hasattr(self.model, order_by):
                field = getattr(self.model, order_by)
                if order_desc:
                    query = query.order_by(desc(field))
                else:
                    query = query.order_by(asc(field))
                    
            # Apply eager loading
            if load_relations:
                for relation in load_relations:
                    if hasattr(self.model, relation):
                        query = query.options(selectinload(getattr(self.model, relation)))
                        
            # Apply pagination
            query = query.offset(offset).limit(limit)
            
            result = await session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error fetching multiple {self.model.__name__}: {e}")
            raise
            
    async def count(
        self, 
        filters: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None
    ) -> int:
        """Count records with optional filtering."""
        if session is None:
            session = db.session
            
        try:
            query = select(func.count(self.model.id))
            
            if filters:
                filter_conditions = []
                for field_name, value in filters.items():
                    if hasattr(self.model, field_name):
                        field = getattr(self.model, field_name)
                        if isinstance(value, list):
                            filter_conditions.append(field.in_(value))
                        else:
                            filter_conditions.append(field == value)
                if filter_conditions:
                    query = query.where(and_(*filter_conditions))
                    
            result = await session.execute(query)
            return result.scalar()
        except Exception as e:
            logger.error(f"Error counting {self.model.__name__}: {e}")
            raise
            
    async def update(
        self, 
        id: int, 
        data: Dict[str, Any], 
        session: Optional[AsyncSession] = None
    ) -> Optional[T]:
        """Update record by ID."""
        if session is None:
            session = db.session
            
        try:
            # Remove None values to avoid overwriting with null
            update_data = {k: v for k, v in data.items() if v is not None}
            
            if not update_data:
                return await self.get_by_id(id, session)
                
            await session.execute(
                update(self.model).where(self.model.id == id).values(**update_data)
            )
            await session.commit()
            
            return await self.get_by_id(id, session)
        except IntegrityError as e:
            await session.rollback()
            logger.error(f"Integrity error updating {self.model.__name__} {id}: {e}")
            raise ValidationError(f"Data validation failed: {str(e)}")
        except Exception as e:
            await session.rollback()
            logger.error(f"Error updating {self.model.__name__} {id}: {e}")
            raise
            
    async def delete(self, id: int, session: Optional[AsyncSession] = None) -> bool:
        """Delete record by ID."""
        if session is None:
            session = db.session
            
        try:
            result = await session.execute(delete(self.model).where(self.model.id == id))
            await session.commit()
            return result.rowcount > 0
        except Exception as e:
            await session.rollback()
            logger.error(f"Error deleting {self.model.__name__} {id}: {e}")
            raise
            
    async def batch_create(
        self, 
        records: List[Dict[str, Any]], 
        session: Optional[AsyncSession] = None,
        batch_size: int = 1000
    ) -> ProcessingStats:
        """Create multiple records in batches."""
        if session is None:
            session = db.session
            
        stats = ProcessingStats(
            total_processed=len(records),
            successful=0,
            failed=0,
            duplicates_found=0,
            processing_time_ms=0,
            errors=[]
        )
        
        start_time = func.extract('epoch', func.now()) * 1000
        
        try:
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                batch_instances = []
                
                for record_data in batch:
                    try:
                        instance = self.model(**record_data)
                        batch_instances.append(instance)
                        stats.successful += 1
                    except Exception as e:
                        stats.failed += 1
                        stats.errors.append(f"Record {i}: {str(e)}")
                        logger.warning(f"Failed to create {self.model.__name__} record: {e}")
                        
                if batch_instances:
                    session.add_all(batch_instances)
                    
                try:
                    await session.commit()
                except IntegrityError as e:
                    await session.rollback()
                    stats.failed += len(batch_instances)
                    stats.successful -= len(batch_instances)
                    stats.errors.append(f"Batch integrity error: {str(e)}")
                    logger.error(f"Batch integrity error for {self.model.__name__}: {e}")
                    
        except Exception as e:
            await session.rollback()
            logger.error(f"Error in batch create for {self.model.__name__}: {e}")
            raise
        finally:
            end_time = func.extract('epoch', func.now()) * 1000
            stats.processing_time_ms = int(end_time - start_time)
            
        return stats
        
    async def batch_update(
        self, 
        updates: List[Dict[str, Any]], 
        id_field: str = 'id',
        session: Optional[AsyncSession] = None
    ) -> int:
        """Update multiple records by ID field."""
        if session is None:
            session = db.session
            
        if not updates:
            return 0
            
        try:
            updated_count = 0
            for update_data in updates:
                if id_field not in update_data:
                    continue
                    
                id_value = update_data.pop(id_field)
                if update_data:  # Only update if there's data
                    result = await session.execute(
                        update(self.model)
                        .where(getattr(self.model, id_field) == id_value)
                        .values(**update_data)
                    )
                    updated_count += result.rowcount
                    
            await session.commit()
            return updated_count
        except Exception as e:
            await session.rollback()
            logger.error(f"Error in batch update for {self.model.__name__}: {e}")
            raise
            
    async def exists(
        self, 
        filters: Dict[str, Any], 
        session: Optional[AsyncSession] = None
    ) -> bool:
        """Check if record exists with given filters."""
        if session is None:
            session = db.session
            
        try:
            query = select(func.count(self.model.id))
            
            filter_conditions = []
            for field_name, value in filters.items():
                if hasattr(self.model, field_name):
                    field = getattr(self.model, field_name)
                    filter_conditions.append(field == value)
                    
            if filter_conditions:
                query = query.where(and_(*filter_conditions))
                
            result = await session.execute(query)
            count = result.scalar()
            return count > 0
        except Exception as e:
            logger.error(f"Error checking existence in {self.model.__name__}: {e}")
            raise
            
    async def find_duplicates(
        self, 
        fields: List[str], 
        session: Optional[AsyncSession] = None
    ) -> List[Dict[str, Any]]:
        """Find duplicate records based on specified fields."""
        if session is None:
            session = db.session
            
        try:
            # Build group by clause
            group_fields = []
            for field_name in fields:
                if hasattr(self.model, field_name):
                    group_fields.append(getattr(self.model, field_name))
                    
            if not group_fields:
                return []
                
            # Query for duplicates
            query = (
                select(*group_fields, func.count().label('count'))
                .group_by(*group_fields)
                .having(func.count() > 1)
            )
            
            result = await session.execute(query)
            duplicates = []
            
            for row in result.all():
                duplicate_info = {}
                for i, field_name in enumerate(fields):
                    duplicate_info[field_name] = row[i]
                duplicate_info['count'] = row.count
                duplicates.append(duplicate_info)
                
            return duplicates
        except Exception as e:
            logger.error(f"Error finding duplicates in {self.model.__name__}: {e}")
            raise


class CacheableRepositoryMixin:
    """Mixin for repositories that support caching."""
    
    def __init__(self, *args, cache_ttl: int = 300, **kwargs):
        """Initialize with cache settings."""
        super().__init__(*args, **kwargs)
        self.cache_ttl = cache_ttl  # 5 minutes default
        
    def _get_cache_key(self, prefix: str, *args) -> str:
        """Generate cache key."""
        key_parts = [prefix] + [str(arg) for arg in args]
        return ":".join(key_parts)
        
    async def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """Get value from Redis cache."""
        try:
            from ..core.redis import get_redis_client
            redis_client = get_redis_client()
            if redis_client is None:
                return None
            cached_value = await redis_client.get(cache_key)
            if cached_value:
                import json
                return json.loads(cached_value)
        except Exception as e:
            logger.warning(f"Cache get error for key {cache_key}: {e}")
        return None
        
    async def _set_cache(self, cache_key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in Redis cache."""
        try:
            from ..core.redis import get_redis_client
            redis_client = get_redis_client()
            if redis_client is None:
                return
            import json
            cache_ttl = ttl or self.cache_ttl
            await redis_client.setex(cache_key, cache_ttl, json.dumps(value, default=str))
        except Exception as e:
            logger.warning(f"Cache set error for key {cache_key}: {e}")
            
    async def _invalidate_cache(self, pattern: str) -> None:
        """Invalidate cache entries matching pattern."""
        try:
            from ..core.redis import get_redis_client
            redis_client = get_redis_client()
            if redis_client is None:
                return
            keys = await redis_client.keys(pattern)
            if keys:
                await redis_client.delete(*keys)
        except Exception as e:
            logger.warning(f"Cache invalidation error for pattern {pattern}: {e}")