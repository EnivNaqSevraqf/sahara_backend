from datetime import datetime, timezone
from typing import List, Dict, Any
import re

def validate_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def get_utc_now() -> datetime:
    """Get current UTC datetime"""
    return datetime.now(timezone.utc)

def format_datetime(dt: datetime) -> str:
    """Format datetime to ISO format with timezone"""
    return dt.isoformat()

def paginate_results(items: List[Any], page: int = 1, page_size: int = 10) -> Dict[str, Any]:
    """
    Paginate a list of items
    
    Args:
        items: List of items to paginate
        page: Page number (1-based)
        page_size: Number of items per page
        
    Returns:
        Dict containing paginated results and metadata
    """
    start = (page - 1) * page_size
    end = start + page_size
    
    total_items = len(items)
    total_pages = (total_items + page_size - 1) // page_size
    
    return {
        "items": items[start:end],
        "pagination": {
            "current_page": page,
            "total_pages": total_pages,
            "page_size": page_size,
            "total_items": total_items
        }
    }

def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password strength
    
    Args:
        password: Password to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
        
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
        
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
        
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number"
        
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character"
        
    return True, ""

def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename by removing invalid characters
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Remove control characters
    filename = "".join(char for char in filename if ord(char) >= 32)
    return filename.strip()