"""
User and Authentication API endpoints
"""

from fastapi import APIRouter, HTTPException, Query, status
from typing import List, Optional
from datetime import datetime
import uuid

from app.models.user import User, UserCreate, UserUpdate, CheckUserRequest, CheckUserResponse, LoginRequest, LoginResponse
from app.database import get_db_cursor
from app.utils.validators import normalize_phone_number

router = APIRouter(prefix="/api/users", tags=["Users & Authentication"])

@router.get("/phone/{phone_number}")
async def get_user_by_phone(phone_number: str):
    """Get user by phone number"""
    try:
        from app.utils.validators import normalize_phone_number
        phone_number = normalize_phone_number(phone_number)
        
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, first_name, last_name, middle_name, suffix,
                       phone_number, barangay, house_address,
                       role, is_verified, created_at
                FROM users
                WHERE phone_number IN (%s, %s, %s)
                LIMIT 1
            """, (
                phone_number,
                phone_number.lstrip('63'),
                '0' + phone_number.lstrip('63')
            ))
            
            user = cur.fetchone()
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            return dict(user)
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/check-user", response_model=CheckUserResponse)
async def check_user(request: CheckUserRequest):
    """Check if user exists by phone number"""
    try:
        phone_number = normalize_phone_number(request.phone_number)
        
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, first_name, middle_name, last_name, suffix,
                       house_address, barangay, phone_number, role,
                       is_verified, created_at, updated_at
                FROM users
                WHERE phone_number = %s
                LIMIT 1
            """, (phone_number,))
            
            user_data = cur.fetchone()
            
            if user_data:
                return CheckUserResponse(
                    success=True,
                    exists=True,
                    message="User found",
                    user=User(**user_data)
                )
            else:
                return CheckUserResponse(
                    success=True,
                    exists=False,
                    message="User not found",
                    user=None
                )
                
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking user: {str(e)}"
        )


@router.post("/get-user", response_model=LoginResponse)
async def get_user(request: LoginRequest):
    """Get user details by phone number (after OTP verification)"""
    try:
        phone_number = normalize_phone_number(request.phone_number)
        
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, first_name, middle_name, last_name, suffix,
                       house_address, barangay, phone_number, role,
                       is_verified, created_at, updated_at
                FROM users
                WHERE phone_number = %s
                LIMIT 1
            """, (phone_number,))
            
            user_data = cur.fetchone()
            
            if not user_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            # Mark user as verified
            if not user_data['is_verified']:
                cur.execute("""
                    UPDATE users
                    SET is_verified = TRUE, updated_at = %s
                    WHERE phone_number = %s
                """, (datetime.utcnow(), phone_number))
                user_data['is_verified'] = True
            
            return LoginResponse(
                success=True,
                message="User retrieved successfully",
                user=User(**user_data)
            )
                
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving user: {str(e)}"
        )


# ✅ FIX: Handle both "/" and "" (with and without trailing slash)
@router.post("/", response_model=User, status_code=status.HTTP_201_CREATED)
@router.post("", response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user(user_data: UserCreate):
    """Create a new user"""
    try:
        phone_number = normalize_phone_number(user_data.phone_number)
        
        with get_db_cursor() as cur:
            # Check if user exists
            cur.execute("SELECT id FROM users WHERE phone_number = %s", (phone_number,))
            if cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User with this phone number already exists"
                )
            
            # Create new user
            user_id = str(uuid.uuid4())
            now = datetime.utcnow()
            
            cur.execute("""
                INSERT INTO users (
                    id, first_name, middle_name, last_name, suffix,
                    house_address, barangay, phone_number, role,
                    is_verified, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, first_name, middle_name, last_name, suffix,
                          house_address, barangay, phone_number, role,
                          is_verified, created_at, updated_at
            """, (
                user_id,
                user_data.first_name.strip(),
                user_data.middle_name.strip() if user_data.middle_name else None,
                user_data.last_name.strip(),
                user_data.suffix.strip() if user_data.suffix else None,
                user_data.house_address.strip(),
                user_data.barangay.strip(),
                phone_number,
                user_data.role.strip(),
                False,  # is_verified starts as False
                now,
                now
            ))
            
            new_user = cur.fetchone()
            
            # ✅ Add success logging
            print(f"✅ User created successfully: {user_id} | {phone_number}")
            
            return User(**new_user)
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error creating user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating user: {str(e)}"
        )


# ✅ FIX: Handle both "/" and "" (with and without trailing slash)
@router.get("/")
@router.get("")
async def get_users(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(25, ge=1, le=200, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by name, phone, or barangay"),
    role: Optional[str] = Query(None, description="Filter by role"),
    is_verified: Optional[bool] = Query(None, description="Filter by verification status"),
    barangay: Optional[str] = Query(None, description="Filter by barangay"),
):
    """Get users with pagination, search, and filters"""
    with get_db_cursor() as cur:
        where_parts: list[str] = []
        params: list = []

        if search:
            where_parts.append(
                "(first_name ILIKE %s OR last_name ILIKE %s OR phone_number ILIKE %s OR barangay ILIKE %s)"
            )
            like = f"%{search}%"
            params.extend([like, like, like, like])

        if role:
            where_parts.append("role = %s")
            params.append(role)

        if is_verified is not None:
            where_parts.append("is_verified = %s")
            params.append(is_verified)

        if barangay:
            where_parts.append("barangay ILIKE %s")
            params.append(f"%{barangay}%")

        where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        # Total count
        cur.execute(f"SELECT COUNT(*) AS cnt FROM users {where_clause}", params)
        total = cur.fetchone()["cnt"]

        # Paginated result
        offset = (page - 1) * limit
        cur.execute(
            f"""
            SELECT id, first_name, middle_name, last_name, suffix,
                   house_address, barangay, phone_number, role,
                   is_verified, created_at, updated_at
            FROM users
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        users = cur.fetchall()

        return {
            "items": [User(**u) for u in users],
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit if total else 0,
        }


@router.get("/{user_id}", response_model=User)
async def get_user_by_id(user_id: str):
    """Get user by ID"""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT id, first_name, middle_name, last_name, suffix,
                   house_address, barangay, phone_number, role,
                   is_verified, created_at, updated_at
            FROM users
            WHERE id = %s
        """, (user_id,))
        
        user_data = cur.fetchone()
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        return User(**user_data)


@router.put("/{user_id}", response_model=User)
async def update_user(user_id: str, user_data: UserUpdate):
    """Update user"""
    try:
        phone_number = normalize_phone_number(user_data.phone_number)
        
        with get_db_cursor() as cur:
            cur.execute("""
                UPDATE users
                SET first_name = %s, middle_name = %s, last_name = %s, suffix = %s,
                    house_address = %s, barangay = %s, phone_number = %s, role = %s,
                    is_verified = %s, updated_at = %s
                WHERE id = %s
                RETURNING id, first_name, middle_name, last_name, suffix,
                          house_address, barangay, phone_number, role,
                          is_verified, created_at, updated_at
            """, (
                user_data.first_name.strip(),
                user_data.middle_name.strip() if user_data.middle_name else None,
                user_data.last_name.strip(),
                user_data.suffix.strip() if user_data.suffix else None,
                user_data.house_address.strip(),
                user_data.barangay.strip(),
                phone_number,
                user_data.role.strip(),
                user_data.is_verified if user_data.is_verified is not None else False,
                datetime.utcnow(),
                user_id
            ))
            
            updated_user = cur.fetchone()
            if not updated_user:
                raise HTTPException(status_code=404, detail="User not found")
            
            return User(**updated_user)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating user: {str(e)}"
        )


@router.delete("/{user_id}")
async def delete_user(user_id: str):
    """Delete user"""
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM users WHERE id = %s RETURNING id", (user_id,))
        deleted = cur.fetchone()
        
        if not deleted:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {"success": True, "message": "User deleted successfully"}