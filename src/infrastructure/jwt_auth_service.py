import os
import jwt
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from passlib.context import CryptContext

logger = logging.getLogger(__name__)


class JWTAuthService:
    """
    JWT Authentication service for secure user authentication and authorization.
    Follows SOLID principles with single responsibility for JWT operations.
    """
    
    def __init__(self):
        self.secret_key = os.getenv("SECRET_KEY", "your-secret-key-here")
        self.algorithm = "HS256"
        self.access_token_expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
        self.refresh_token_expire_days = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
        
        # Password hashing context
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        # Validate required configurations
        if self.secret_key == "your-secret-key-here":
            logger.warning("Using default secret key - this is insecure for production")
    
    def create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """
        Create a JWT access token with user data and expiration.
        
        Args:
            data: Dictionary containing user information (user_id, email, roles, etc.)
            expires_delta: Optional custom expiration time
        
        Returns:
            Encoded JWT token string
        """
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        
        to_encode.update({"exp": expire, "type": "access"})
        
        try:
            encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
            logger.info(f"Access token created for user: {data.get('user_id', 'unknown')}")
            return encoded_jwt
        except Exception as e:
            logger.error(f"Error creating access token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create access token"
            )
    
    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        """
        Create a JWT refresh token for long-term authentication.
        
        Args:
            data: Dictionary containing minimal user information
        
        Returns:
            Encoded JWT refresh token string
        """
        to_encode = {"user_id": data.get("user_id"), "type": "refresh"}
        expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)
        to_encode.update({"exp": expire})
        
        try:
            encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
            logger.info(f"Refresh token created for user: {data.get('user_id', 'unknown')}")
            return encoded_jwt
        except Exception as e:
            logger.error(f"Error creating refresh token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create refresh token"
            )
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify and decode a JWT token.
        
        Args:
            token: JWT token string
        
        Returns:
            Decoded token payload
        
        Raises:
            HTTPException: If token is invalid, expired, or malformed
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Check if token has expired
            exp = payload.get("exp")
            if exp and datetime.utcnow() > datetime.fromtimestamp(exp):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has expired",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # Ensure token has required fields
            if not payload.get("user_id"):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: missing user_id",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning(f"Expired token verification attempt")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"}
            )
        except jwt.JWTError as e:
            logger.warning(f"JWT verification failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"}
            )
        except Exception as e:
            logger.error(f"Unexpected error during token verification: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token verification failed"
            )
    
    def refresh_access_token(self, refresh_token: str) -> str:
        """
        Create a new access token using a valid refresh token.
        
        Args:
            refresh_token: Valid refresh token
        
        Returns:
            New access token
        """
        try:
            payload = self.verify_token(refresh_token)
            
            # Ensure this is a refresh token
            if payload.get("type") != "refresh":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type for refresh",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # Create new access token with minimal user data
            user_data = {"user_id": payload["user_id"]}
            return self.create_access_token(user_data)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error refreshing access token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to refresh token"
            )
    
    def hash_password(self, password: str) -> str:
        """Hash a password for secure storage."""
        return self.pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return self.pwd_context.verify(plain_password, hashed_password)
    
    def extract_user_id(self, token: str) -> str:
        """
        Extract user ID from token without full verification (for logging/tracking).
        
        Args:
            token: JWT token string
        
        Returns:
            User ID string or 'unknown' if extraction fails
        """
        try:
            # Decode without verification for quick user ID extraction
            payload = jwt.decode(token, options={"verify_signature": False})
            return payload.get("user_id", "unknown")
        except Exception:
            return "unknown"
    
    def create_user_tokens(self, user_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Create both access and refresh tokens for a user.
        
        Args:
            user_data: User information dictionary
        
        Returns:
            Dictionary containing both token types
        """
        access_token = self.create_access_token(user_data)
        refresh_token = self.create_refresh_token(user_data)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.access_token_expire_minutes * 60  # seconds
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Health check for JWT authentication service.
        
        Returns:
            Health status information
        """
        try:
            # Test token creation and verification
            test_data = {"user_id": "health_check", "test": True}
            test_token = self.create_access_token(test_data)
            decoded = self.verify_token(test_token)
            
            health_status = {
                "status": "healthy",
                "service": "jwt_auth",
                "token_algorithm": self.algorithm,
                "access_token_expire_minutes": self.access_token_expire_minutes,
                "test_passed": decoded.get("user_id") == "health_check",
                "checked_at": datetime.utcnow().isoformat()
            }
            
            return health_status
            
        except Exception as e:
            logger.error(f"JWT Auth service health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "service": "jwt_auth",
                "error": str(e),
                "checked_at": datetime.utcnow().isoformat()
            }