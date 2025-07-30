"""
Authentication Service
Handles Composio app authentication and OAuth flows.
Follows Single Responsibility Principle - only responsible for authentication.
"""

import asyncio
import logging
from typing import Dict, Optional, List
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .workflow_config import WorkflowConfig

logger = logging.getLogger(__name__)


@dataclass
class AuthenticationResult:
    """Data class for authentication results."""
    is_authenticated: bool
    account_id: Optional[str] = None
    connection_status: Optional[str] = None
    error_message: Optional[str] = None
    oauth_url: Optional[str] = None
    connection_id: Optional[str] = None


class AuthenticationInterface(ABC):
    """Interface for authentication services following Interface Segregation Principle."""
    
    @abstractmethod
    async def check_authentication(self, app_name: str) -> AuthenticationResult:
        """Check if app is authenticated."""
        pass
    
    @abstractmethod
    async def initiate_oauth(self, app_name: str) -> AuthenticationResult:
        """Initiate OAuth flow for app."""
        pass
    
    @abstractmethod
    async def verify_authentication_after_oauth(self, app_name: str) -> AuthenticationResult:
        """Verify authentication after OAuth completion."""
        pass


class ComposioAuthenticationService(AuthenticationInterface):
    """Composio-specific authentication service."""
    
    def __init__(self, toolset, config: WorkflowConfig):
        self.toolset = toolset
        self.config = config
        logger.info("ComposioAuthenticationService initialized")
    
    async def check_authentication(self, app_name: str) -> AuthenticationResult:
        """Check if app is authenticated with Composio."""
        try:
            logger.info(f"Checking authentication for {app_name}")
            
            # Get connected accounts with timeout
            connected_accounts = await asyncio.wait_for(
                asyncio.to_thread(self.toolset.get_connected_accounts),
                timeout=self.config.timeouts.composio_auth_check
            )
            
            # Check if the selected app is connected
            auth_result = self._find_connected_app(connected_accounts, app_name)
            
            if auth_result.is_authenticated:
                logger.info(f"{app_name} is authenticated - Account ID: {auth_result.account_id}")
            else:
                logger.warning(f"{app_name} is not authenticated")
            
            return auth_result
            
        except asyncio.TimeoutError:
            logger.error(f"Authentication check timeout for {app_name}")
            return AuthenticationResult(
                is_authenticated=False,
                error_message="Authentication check timed out"
            )
        except Exception as e:
            logger.error(f"Authentication check failed for {app_name}: {str(e)}")
            return AuthenticationResult(
                is_authenticated=False,
                error_message=f"Authentication check failed: {str(e)}"
            )
    
    async def initiate_oauth(self, app_name: str) -> AuthenticationResult:
        """Initiate OAuth flow for the specified app."""
        try:
            logger.info(f"Initiating OAuth for {app_name}")
            
            # Get Composio App enum
            app_enum = self._get_app_enum(app_name)
            if not app_enum:
                return AuthenticationResult(
                    is_authenticated=False,
                    error_message=f"OAuth not supported for {app_name}"
                )
            
            # Generate OAuth URL with timeout
            oauth_request = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: self.toolset.initiate_connection(
                        app=app_enum,
                        entity_id=self.config.entity_id,
                        redirect_url=self.config.redirect_url
                    )
                ),
                timeout=self.config.timeouts.composio_oauth_init
            )
            
            if oauth_request and hasattr(oauth_request, 'redirectUrl'):
                oauth_url = oauth_request.redirectUrl
                connection_id = getattr(oauth_request, 'connectionId', 'unknown')
                
                logger.info(f"OAuth URL generated for {app_name}: {oauth_url}")
                
                return AuthenticationResult(
                    is_authenticated=False,  # Not yet authenticated, but OAuth initiated
                    oauth_url=oauth_url,
                    connection_id=connection_id
                )
            else:
                return AuthenticationResult(
                    is_authenticated=False,
                    error_message=f"Failed to generate OAuth URL for {app_name}"
                )
                
        except asyncio.TimeoutError:
            logger.error(f"OAuth initiation timeout for {app_name}")
            return AuthenticationResult(
                is_authenticated=False,
                error_message="OAuth initiation timed out"
            )
        except Exception as e:
            logger.error(f"OAuth initiation failed for {app_name}: {str(e)}")
            return AuthenticationResult(
                is_authenticated=False,
                error_message=f"OAuth initiation failed: {str(e)}"
            )
    
    async def verify_authentication_after_oauth(self, app_name: str) -> AuthenticationResult:
        """Verify authentication after OAuth completion."""
        try:
            logger.info(f"Verifying authentication after OAuth for {app_name}")
            
            # Give some time for the connection to be established
            await asyncio.sleep(2)
            
            # Re-check connected accounts
            return await self.check_authentication(app_name)
            
        except Exception as e:
            logger.error(f"Authentication verification failed for {app_name}: {str(e)}")
            return AuthenticationResult(
                is_authenticated=False,
                error_message=f"Authentication verification failed: {str(e)}"
            )
    
    def _find_connected_app(self, connected_accounts: List, app_name: str) -> AuthenticationResult:
        """Find if app is in connected accounts list."""
        if not connected_accounts:
            return AuthenticationResult(is_authenticated=False)
        
        app_name_upper = app_name.upper()
        
        for account in connected_accounts:
            # Check multiple possible attributes for app name
            account_app_name = None
            
            if hasattr(account, 'appName'):
                account_app_name = account.appName.upper()
            elif hasattr(account, 'app'):
                account_app_name = str(account.app).upper()
            elif hasattr(account, 'name'):
                account_app_name = account.name.upper()
            
            if account_app_name == app_name_upper:
                return AuthenticationResult(
                    is_authenticated=True,
                    account_id=getattr(account, 'id', 'N/A'),
                    connection_status=getattr(account, 'connectionStatus', 'Active')
                )
        
        return AuthenticationResult(is_authenticated=False)
    
    def _get_app_enum(self, app_name: str):
        """Get Composio App enum for the given app name."""
        try:
            from composio import App as ComposioApp
            
            enum_name = self.config.get_app_enum(app_name)
            if not enum_name:
                return None
            
            return getattr(ComposioApp, enum_name, None)
            
        except ImportError:
            logger.error("Composio library not available")
            return None
        except Exception as e:
            logger.error(f"Error getting app enum for {app_name}: {str(e)}")
            return None


class AuthenticationOrchestrator:
    """Orchestrates the complete authentication flow."""
    
    def __init__(self, auth_service: AuthenticationInterface, config: WorkflowConfig):
        self.auth_service = auth_service
        self.config = config
        logger.info("AuthenticationOrchestrator initialized")
    
    async def ensure_authentication(self, app_name: str, interactive: bool = True) -> AuthenticationResult:
        """Ensure app is authenticated, handle OAuth if needed."""
        try:
            # Step 1: Check current authentication status
            auth_result = await self.auth_service.check_authentication(app_name)
            
            if auth_result.is_authenticated:
                return auth_result
            
            if not interactive:
                return auth_result  # Don't initiate OAuth in non-interactive mode
            
            # Step 2: App not authenticated - initiate OAuth
            logger.info(f"{app_name} not authenticated, initiating OAuth flow")
            oauth_result = await self.auth_service.initiate_oauth(app_name)
            
            if not oauth_result.oauth_url:
                return oauth_result
            
            # Step 3: Present OAuth URL to user (in real implementation)
            self._present_oauth_instructions(app_name, oauth_result)
            
            # Step 4: Wait for user to complete OAuth (simplified for demo)
            user_completed_oauth = self._wait_for_user_oauth_completion(app_name)
            
            if not user_completed_oauth:
                return AuthenticationResult(
                    is_authenticated=False,
                    error_message="User skipped OAuth authentication"
                )
            
            # Step 5: Verify authentication after OAuth
            return await self.auth_service.verify_authentication_after_oauth(app_name)
            
        except Exception as e:
            logger.error(f"Authentication orchestration failed for {app_name}: {str(e)}")
            return AuthenticationResult(
                is_authenticated=False,
                error_message=f"Authentication orchestration failed: {str(e)}"
            )
    
    def _present_oauth_instructions(self, app_name: str, oauth_result: AuthenticationResult):
        """Present OAuth instructions to user."""
        print(f"🎯 OAuth URL Generated Successfully!")
        print("-" * 50)
        print(f"🔗 Auth URL: {oauth_result.oauth_url}")
        print(f"🆔 Connection ID: {oauth_result.connection_id}")
        print(f"\n📋 AUTHENTICATION INSTRUCTIONS:")
        print("1. Copy the OAuth URL above")
        print("2. Open it in your browser")
        print("3. Complete the authentication flow")
        print("4. Return to continue the test")
    
    def _wait_for_user_oauth_completion(self, app_name: str) -> bool:
        """Wait for user to complete OAuth (interactive)."""
        print(f"\n⏳ Please complete OAuth authentication for {app_name}")
        user_input = input("Press Enter after completing authentication (or 'skip' to continue without auth): ").strip()
        
        if user_input.lower() == 'skip':
            print("⚠️ Skipping authentication - execution may fail")
            return False
        
        return True


class MockAuthenticationService(AuthenticationInterface):
    """Mock authentication service for testing."""
    
    def __init__(self, config: WorkflowConfig):
        self.config = config
        self.authenticated_apps = set()
        logger.info("MockAuthenticationService initialized")
    
    async def check_authentication(self, app_name: str) -> AuthenticationResult:
        """Mock authentication check."""
        is_auth = app_name.upper() in self.authenticated_apps
        return AuthenticationResult(
            is_authenticated=is_auth,
            account_id=f"mock-{app_name.lower()}-id" if is_auth else None,
            connection_status="Active" if is_auth else None
        )
    
    async def initiate_oauth(self, app_name: str) -> AuthenticationResult:
        """Mock OAuth initiation."""
        return AuthenticationResult(
            is_authenticated=False,
            oauth_url=f"https://mock-oauth.example.com/{app_name.lower()}",
            connection_id=f"mock-connection-{app_name.lower()}"
        )
    
    async def verify_authentication_after_oauth(self, app_name: str) -> AuthenticationResult:
        """Mock OAuth verification."""
        self.authenticated_apps.add(app_name.upper())
        return AuthenticationResult(
            is_authenticated=True,
            account_id=f"mock-{app_name.lower()}-id",
            connection_status="Active"
        )