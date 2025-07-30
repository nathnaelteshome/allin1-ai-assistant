import logging
from typing import Optional, Dict, Any
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .jwt_auth_service import JWTAuthService

logger = logging.getLogger(__name__)

# Security scheme for Bearer token
security = HTTPBearer()

# Global JWT service instance
jwt_auth_service = JWTAuthService()


class UserContext:
    """
    User context model containing authenticated user information.
    Follows SOLID principles with clear data structure.
    """
    
    def __init__(self, user_id: str, email: Optional[str] = None, 
                 roles: Optional[list] = None, metadata: Optional[Dict[str, Any]] = None):
        self.user_id = user_id
        self.email = email
        self.roles = roles or []
        self.metadata = metadata or {}
        self.is_authenticated = True
    
    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        return role in self.roles
    
    def has_any_role(self, roles: list) -> bool:
        """Check if user has any of the specified roles."""
        return any(role in self.roles for role in roles)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert user context to dictionary."""
        return {
            "user_id": self.user_id,
            "email": self.email,
            "roles": self.roles,
            "metadata": self.metadata,
            "is_authenticated": self.is_authenticated
        }


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserContext:
    """
    Authentication dependency that extracts and validates user from JWT token.
    
    This replaces the dummy authentication system with proper JWT-based auth.
    
    Args:
        credentials: HTTP Bearer token credentials
    
    Returns:
        UserContext: Authenticated user information
    
    Raises:
        HTTPException: If authentication fails
    """
    try:
        # Extract token from credentials
        token = credentials.credentials
        
        # Verify and decode token
        payload = jwt_auth_service.verify_token(token)
        
        # Extract user information from token payload
        user_id = payload.get("user_id")
        email = payload.get("email")
        roles = payload.get("roles", [])
        metadata = payload.get("metadata", {})
        
        # Create user context
        user_context = UserContext(
            user_id=user_id,
            email=email,
            roles=roles,
            metadata=metadata
        )
        
        logger.debug(f"User authenticated successfully: {user_id}")
        return user_context
        
    except HTTPException:
        # Re-raise HTTP exceptions from JWT service
        raise
    except Exception as e:
        logger.error(f"Unexpected error in authentication: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication processing failed"
        )


async def get_optional_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))) -> Optional[UserContext]:
    """
    Optional authentication dependency for endpoints that work with or without auth.
    
    Args:
        credentials: Optional HTTP Bearer token credentials
    
    Returns:
        UserContext or None if no valid authentication provided
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        # Return None for optional auth instead of raising exception
        return None


async def require_roles(required_roles: list):
    """
    Dependency factory for role-based authorization.
    
    Args:
        required_roles: List of roles required for access
    
    Returns:
        Dependency function that checks user roles
    """
    async def role_checker(user: UserContext = Depends(get_current_user)) -> UserContext:
        if not user.has_any_role(required_roles):
            logger.warning(f"User {user.user_id} lacks required roles: {required_roles}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {required_roles}"
            )
        return user
    
    return role_checker


async def require_admin(user: UserContext = Depends(get_current_user)) -> UserContext:
    """
    Dependency that requires admin role.
    
    Args:
        user: Authenticated user context
    
    Returns:
        UserContext if user is admin
    
    Raises:
        HTTPException: If user is not admin
    """
    if not user.has_role("admin"):
        logger.warning(f"Non-admin user {user.user_id} attempted admin action")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return user


class RateLimitingMiddleware:
    """
    Simple rate limiting middleware for API protection.
    Follows SOLID principles with single responsibility for rate limiting.
    """
    
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.user_requests = {}  # In production, use Redis or similar
    
    async def check_rate_limit(self, user: UserContext = Depends(get_current_user)) -> UserContext:
        """
        Check if user has exceeded rate limit.
        
        Args:
            user: Authenticated user context
        
        Returns:
            UserContext if within rate limit
        
        Raises:
            HTTPException: If rate limit exceeded
        """
        import time
        
        current_time = time.time()
        user_id = user.user_id
        
        # Initialize user request tracking
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []
        
        # Clean old requests (older than 1 minute)
        self.user_requests[user_id] = [
            req_time for req_time in self.user_requests[user_id]
            if current_time - req_time < 60
        ]
        
        # Check if rate limit exceeded
        if len(self.user_requests[user_id]) >= self.requests_per_minute:
            logger.warning(f"Rate limit exceeded for user {user_id}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {self.requests_per_minute} requests per minute."
            )
        
        # Record current request
        self.user_requests[user_id].append(current_time)
        
        return user


# Global rate limiting instance
rate_limiter = RateLimitingMiddleware()


async def get_user_with_rate_limit(user: UserContext = Depends(get_current_user)) -> UserContext:
    """
    Combined dependency for authentication and rate limiting.
    
    Args:
        user: Authenticated user context
    
    Returns:
        UserContext if authenticated and within rate limit
    """
    return await rate_limiter.check_rate_limit(user)


def create_demo_token(user_id: str = "demo_user", email: str = "demo@example.com") -> str:
    """
    Create a demo token for testing purposes.
    
    Args:
        user_id: Demo user ID
        email: Demo user email
    
    Returns:
        JWT token for demo user
    """
    user_data = {
        "user_id": user_id,
        "email": email,
        "roles": ["user"],
        "metadata": {"demo": True}
    }
    
    return jwt_auth_service.create_access_token(user_data)


async def get_jwt_service() -> JWTAuthService:
    """Dependency to get JWT service instance."""
    return jwt_auth_service