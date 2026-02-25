"""
Preventive Measures API endpoints
"""

from fastapi import APIRouter, HTTPException, status
from typing import List
from datetime import datetime

from backend.models.safety import PreventiveMeasure, MeasureCreate, MeasureUpdate
from backend.database import get_db_cursor

router = APIRouter(prefix="/api/safety/preventive-measures", tags=["Preventive Measures"])


@router.get("/category/{category_id}", response_model=List[PreventiveMeasure])
async def get_measures_by_category(category_id: int):  # ✅ Changed to int
    """Get all preventive measures for a category"""
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, category_id, number, title, description, 
                       order_num, is_active, created_at, updated_at
                FROM preventive_measures
                WHERE category_id = %s AND is_active = true
                ORDER BY order_num ASC
            """, (category_id,))
            
            measures = [dict(row) for row in cur.fetchall()]
            return [PreventiveMeasure(**m) for m in measures]
            
    except Exception as e: 
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching measures: {str(e)}"
        )


@router.post("/", response_model=PreventiveMeasure, status_code=status.HTTP_201_CREATED)
async def create_measure(measure_data: MeasureCreate):
    """Create a new preventive measure"""
    try: 
        with get_db_cursor() as cur:
            now = datetime.utcnow()
            
            # Auto-generate number based on existing count
            cur.execute("""
                SELECT COUNT(*) FROM preventive_measures 
                WHERE category_id = %s
            """, (measure_data. category_id,))
            count = cur.fetchone()[0]
            number = f"{count + 1:02d}"  # Format as "01", "02", etc.
            
            # ✅ Let SERIAL generate ID
            cur.execute("""
                INSERT INTO preventive_measures (
                    category_id, number, title, description, 
                    order_num, is_active, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, category_id, number, title, description,
                          order_num, is_active, created_at, updated_at
            """, (
                measure_data.category_id, number,
                measure_data.title, measure_data.description,
                measure_data.order_num or count + 1,
                measure_data.is_active, now, now
            ))
            
            new_measure = dict(cur.fetchone())
            return PreventiveMeasure(**new_measure)
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating measure: {str(e)}"
        )


@router.put("/{measure_id}", response_model=PreventiveMeasure)
async def update_measure(measure_id: int, measure_data: MeasureUpdate):  # ✅ Changed to int
    """Update a preventive measure"""
    try:
        with get_db_cursor() as cur:
            update_fields = []
            values = []
            
            if measure_data.title is not None:
                update_fields.append("title = %s")
                values.append(measure_data.title)
            
            if measure_data.description is not None:
                update_fields.append("description = %s")
                values.append(measure_data.description)
            
            if measure_data.order_num is not None:
                update_fields.append("order_num = %s")
                values.append(measure_data.order_num)
            
            if not update_fields:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No fields to update"
                )
            
            update_fields.append("updated_at = %s")
            values.append(datetime.utcnow())
            values.append(measure_id)
            
            cur.execute(f"""
                UPDATE preventive_measures
                SET {', '. join(update_fields)}
                WHERE id = %s
                RETURNING id, category_id, number, title, description,
                          order_num, is_active, created_at, updated_at
            """, values)
            
            updated = cur.fetchone()
            if not updated:
                raise HTTPException(status_code=404, detail="Measure not found")
            
            return PreventiveMeasure(**dict(updated))
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating measure: {str(e)}"
        )


@router.delete("/{measure_id}")
async def delete_measure(measure_id: int):  # ✅ Changed to int
    """Delete a preventive measure and renumber remaining ones"""
    try:
        with get_db_cursor() as cur:
            # Get category_id before deleting
            cur.execute("SELECT category_id FROM preventive_measures WHERE id = %s", (measure_id,))
            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Measure not found")
            
            category_id = result[0]
            
            # Delete the measure
            cur.execute("DELETE FROM preventive_measures WHERE id = %s", (measure_id,))
            
            # Renumber remaining measures
            cur. execute("""
                SELECT id FROM preventive_measures 
                WHERE category_id = %s 
                ORDER BY order_num ASC
            """, (category_id,))
            
            measures = cur.fetchall()
            for idx, (mid,) in enumerate(measures, 1):
                cur.execute("""
                    UPDATE preventive_measures 
                    SET number = %s, order_num = %s 
                    WHERE id = %s
                """, (f"{idx:02d}", idx, mid))
            
            return {"success": True, "message":  "Measure deleted successfully"}
            
    except HTTPException:
        raise
    except Exception as e: 
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting measure: {str(e)}"
        )