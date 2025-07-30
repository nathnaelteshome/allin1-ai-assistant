import logging
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from ..infrastructure.composio_auth_manager import ComposioAuthManager

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


# Pydantic models
class ConnectionInitiateRequest(BaseModel):
    app_name: str = Field(..., description="Name of the app to connect (gmail, twitter, etc.)")
    redirect_url: str = Field(..., description="OAuth callback URL")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    
    class Config:
        schema_extra = {
            "example": {
                "app_name": "gmail",
                "redirect_url": "http://localhost:5000/auth/callback",
                "metadata": {"scenario": "email"}
            }
        }


class ConnectionInitiateResponse(BaseModel):
    session_id: str
    auth_url: str
    connection_id: str
    app_name: str
    expires_in: int


class ConnectionCompleteRequest(BaseModel):
    auth_code: str = Field(..., description="Authorization code from OAuth callback")
    
    class Config:
        schema_extra = {
            "example": {
                "auth_code": "4/0AdQt8qjvKthisIsAFakeAuthCode"
            }
        }


class ConnectionCompleteResponse(BaseModel):
    success: bool
    account_id: str
    user_id: str
    app_name: str
    status: str
    connected_at: str


class ConnectedAccountResponse(BaseModel):
    id: str
    app_name: str
    status: str
    connected_at: str
    last_used_at: str
    is_healthy: bool
    metadata: Dict[str, Any]


class AuthController:
    """
    FastAPI controller for authentication and OAuth management.
    """
    
    def __init__(self, auth_manager: ComposioAuthManager):
        self.auth_manager = auth_manager


# Dependency injection - This will be overridden by FastAPI's dependency injection
def get_auth_controller():
    """Placeholder for dependency injection - overridden in main app."""
    raise NotImplementedError("Dependency injection not configured")


@router.post("/auth/connect", response_model=ConnectionInitiateResponse)
async def initiate_connection(
    request: ConnectionInitiateRequest,
    user_id: str = Depends(lambda: "user_demo"),  # Replace with proper auth
    controller: AuthController = Depends(get_auth_controller)
) -> ConnectionInitiateResponse:
    """
    Initiate OAuth connection for an external service.
    
    This endpoint starts the OAuth flow for connecting user accounts
    to external services like Gmail, Twitter, Google Calendar, etc.
    """
    try:
        logger.info(f"Initiating {request.app_name} connection for user {user_id}")
        
        # Initiate OAuth flow
        result = await controller.auth_manager.initiate_account_connection(
            user_id=user_id,
            app_name=request.app_name,
            redirect_url=request.redirect_url,
            metadata=request.metadata
        )
        
        response = ConnectionInitiateResponse(
            session_id=result['session_id'],
            auth_url=result['auth_url'],
            connection_id=result['connection_id'],
            app_name=request.app_name,
            expires_in=result['expires_in']
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error initiating connection: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initiate connection: {str(e)}"
        )


@router.post("/auth/connect/{session_id}/complete", response_model=ConnectionCompleteResponse)
async def complete_connection(
    session_id: str,
    request: ConnectionCompleteRequest,
    controller: AuthController = Depends(get_auth_controller)
) -> ConnectionCompleteResponse:
    """
    Complete OAuth connection with authorization code.
    
    This endpoint is called after the user completes the OAuth flow
    and returns with an authorization code.
    """
    try:
        logger.info(f"Completing OAuth connection for session {session_id}")
        
        # Complete OAuth flow
        result = await controller.auth_manager.complete_account_connection(
            session_id=session_id,
            auth_code=request.auth_code
        )
        
        response = ConnectionCompleteResponse(
            success=result['success'],
            account_id=result['account_id'],
            user_id=result['user_id'],
            app_name=result['app_name'],
            status=result['status'],
            connected_at=result['connected_at']
        )
        
        return response
        
    except ValueError as e:
        logger.error(f"OAuth completion error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error completing connection: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to complete connection: {str(e)}"
        )


@router.get("/auth/accounts", response_model=List[ConnectedAccountResponse])
async def get_connected_accounts(
    app_name: Optional[str] = Query(None, description="Filter by app name"),
    user_id: str = Depends(lambda: "user_demo"),  # Replace with proper auth
    controller: AuthController = Depends(get_auth_controller)
) -> List[ConnectedAccountResponse]:
    """
    Get all connected accounts for the current user.
    
    Optionally filter by app name to get accounts for a specific service.
    """
    try:
        logger.info(f"Getting connected accounts for user {user_id}")
        
        # Get connected accounts
        accounts = await controller.auth_manager.get_user_connected_accounts(
            user_id=user_id,
            app_name=app_name
        )
        
        # Convert to response models
        response_accounts = []
        for account in accounts:
            response_account = ConnectedAccountResponse(
                id=account['id'],
                app_name=account['app_name'],
                status=account['status'],
                connected_at=account['connected_at'],
                last_used_at=account['last_used_at'],
                is_healthy=account.get('is_healthy', False),
                metadata=account.get('metadata', {})
            )
            response_accounts.append(response_account)
        
        return response_accounts
        
    except Exception as e:
        logger.error(f"Error getting connected accounts: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get connected accounts: {str(e)}"
        )


@router.delete("/auth/accounts/{account_id}")
async def disconnect_account(
    account_id: str,
    user_id: str = Depends(lambda: "user_demo"),  # Replace with proper auth
    controller: AuthController = Depends(get_auth_controller)
) -> Dict[str, Any]:
    """
    Disconnect a connected account.
    
    This removes the connection between the user and the external service.
    """
    try:
        logger.info(f"Disconnecting account {account_id} for user {user_id}")
        
        # Disconnect account
        result = await controller.auth_manager.disconnect_account(
            user_id=user_id,
            account_id=account_id
        )
        
        return result
        
    except ValueError as e:
        logger.error(f"Disconnect error: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error disconnecting account: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to disconnect account: {str(e)}"
        )


@router.post("/auth/accounts/{account_id}/refresh")
async def refresh_account_status(
    account_id: str,
    user_id: str = Depends(lambda: "user_demo"),  # Replace with proper auth
    controller: AuthController = Depends(get_auth_controller)
) -> Dict[str, Any]:
    """
    Refresh the status of a connected account.
    
    This checks if the account is still healthy and can be used for tool execution.
    """
    try:
        logger.info(f"Refreshing account {account_id} status for user {user_id}")
        
        # Refresh account status
        result = await controller.auth_manager.refresh_account_status(
            user_id=user_id,
            account_id=account_id
        )
        
        return result
        
    except ValueError as e:
        logger.error(f"Refresh error: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error refreshing account status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to refresh account status: {str(e)}"
        )


@router.get("/auth/sessions")
async def get_oauth_sessions(
    status: Optional[str] = Query(None, description="Filter by session status"),
    user_id: str = Depends(lambda: "user_demo"),  # Replace with proper auth
    controller: AuthController = Depends(get_auth_controller)
) -> Dict[str, Any]:
    """
    Get OAuth sessions for the current user.
    
    Useful for debugging OAuth flows and checking session status.
    """
    try:
        logger.info(f"Getting OAuth sessions for user {user_id}")
        
        # Get OAuth sessions
        sessions = await controller.auth_manager.get_user_oauth_sessions(
            user_id=user_id,
            status=status
        )
        
        return {
            'user_id': user_id,
            'sessions': sessions,
            'total_sessions': len(sessions)
        }
        
    except Exception as e:
        logger.error(f"Error getting OAuth sessions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get OAuth sessions: {str(e)}"
        )


@router.get("/auth/sessions/{session_id}")
async def get_oauth_session(
    session_id: str,
    controller: AuthController = Depends(get_auth_controller)
) -> Dict[str, Any]:
    """
    Get details of a specific OAuth session.
    """
    try:
        logger.info(f"Getting OAuth session {session_id}")
        
        # Get OAuth session
        session = await controller.auth_manager.get_oauth_session(session_id)
        
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"OAuth session {session_id} not found"
            )
        
        return session
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting OAuth session: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get OAuth session: {str(e)}"
        )


@router.get("/auth/apps")
async def get_supported_apps(
    controller: AuthController = Depends(get_auth_controller)
) -> Dict[str, Any]:
    """
    Get list of supported apps for OAuth connections with dynamic configuration.
    """
    try:
        # Get supported apps from the auth manager
        supported_apps = controller.auth_manager.get_supported_apps()
        
        return {
            'supported_apps': supported_apps,
            'total_apps': len(supported_apps),
            'oauth_apps': [app for app, info in supported_apps.items() if info['auth_type'] == 'oauth2'],
            'api_key_apps': [app for app, info in supported_apps.items() if info['auth_type'] == 'api_key'],
            'categories': {
                category: [app for app, info in supported_apps.items() if info['category'] == category]
                for category in set(info['category'] for info in supported_apps.values())
            }
        }
    except Exception as e:
        logger.error(f"Error getting supported apps: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get supported apps: {str(e)}"
        )


@router.get("/auth/status")
async def get_user_auth_status(
    user_id: str = Depends(lambda: "user_demo"),  # Replace with proper auth
    controller: AuthController = Depends(get_auth_controller)
) -> Dict[str, Any]:
    """
    Get comprehensive authentication status for the current user.
    
    Shows which apps are connected and which scenarios are available.
    """
    try:
        logger.info(f"Getting auth status for user {user_id}")
        
        # Get all connected accounts
        all_accounts = await controller.auth_manager.get_user_connected_accounts(user_id)
        
        # Group by app
        connected_apps = {}
        for account in all_accounts:
            app_name = account['app_name']
            if app_name not in connected_apps:
                connected_apps[app_name] = []
            connected_apps[app_name].append(account)
        
        # Check scenario availability
        scenario_status = {}
        scenario_requirements = {
            'email': ['gmail'],
            'flight_booking': ['skyscanner', 'stripe'],
            'meeting_scheduling': ['google_calendar', 'zoom'],
            'trip_planning': ['skyscanner', 'booking', 'tripadvisor'],
            'food_ordering': ['doordash', 'stripe'],
            'x_posting': ['twitter']
        }
        
        for scenario, required_apps in scenario_requirements.items():
            connected_required = [app for app in required_apps if app in connected_apps]
            scenario_status[scenario] = {
                'available': len(connected_required) == len(required_apps),
                'required_apps': required_apps,
                'connected_apps': connected_required,
                'missing_apps': [app for app in required_apps if app not in connected_apps]
            }
        
        return {
            'user_id': user_id,
            'connected_apps': list(connected_apps.keys()),
            'total_accounts': len(all_accounts),
            'healthy_accounts': len([acc for acc in all_accounts if acc.get('is_healthy', False)]),
            'scenario_availability': scenario_status,
            'fully_available_scenarios': [
                scenario for scenario, status in scenario_status.items() 
                if status['available']
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting auth status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get auth status: {str(e)}"
        )


# New scenario-based endpoints for enhanced authentication management
@router.get("/auth/scenarios")
async def get_supported_scenarios(
    controller: AuthController = Depends(get_auth_controller)
) -> Dict[str, Any]:
    """
    Get all supported scenarios and their authentication requirements.
    """
    try:
        # Get scenario app mappings from auth manager
        scenario_apps = controller.auth_manager.SCENARIO_APPS
        supported_apps = controller.auth_manager.get_supported_apps()
        
        scenarios = {}
        for scenario, required_apps in scenario_apps.items():
            scenarios[scenario] = {
                'name': scenario.replace('_', ' ').title(),
                'required_apps': required_apps,
                'app_details': {
                    app: supported_apps.get(app, {})
                    for app in required_apps
                },
                'total_required': len(required_apps)
            }
        
        return {
            'scenarios': scenarios,
            'total_scenarios': len(scenarios)
        }
        
    except Exception as e:
        logger.error(f"Error getting supported scenarios: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get supported scenarios: {str(e)}"
        )


@router.get("/auth/scenarios/{scenario}/status")
async def get_scenario_auth_status(
    scenario: str,
    user_id: str = Depends(lambda: "user_demo"),
    controller: AuthController = Depends(get_auth_controller)
) -> Dict[str, Any]:
    """
    Get authentication status for a specific scenario.
    
    This shows which apps are connected and which are still needed
    for the scenario to be fully functional.
    """
    try:
        logger.info(f"Getting {scenario} auth status for user {user_id}")
        
        # Check scenario authentication
        result = await controller.auth_manager.check_scenario_authentication(
            user_id=user_id,
            scenario=scenario
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting scenario auth status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get scenario auth status: {str(e)}"
        )


@router.post("/auth/scenarios/{scenario}/connect")
async def connect_scenario_apps(
    scenario: str,
    user_id: str = Depends(lambda: "user_demo"),
    custom_redirect_url: Optional[str] = None,
    controller: AuthController = Depends(get_auth_controller)
) -> Dict[str, Any]:
    """
    Generate authentication URLs for all unauthenticated apps in a scenario.
    
    This is a convenient endpoint to get all OAuth URLs needed to
    enable a complete scenario workflow.
    """
    try:
        logger.info(f"Generating auth URLs for {scenario} scenario for user {user_id}")
        
        # Get authentication URLs for scenario
        result = await controller.auth_manager.get_authentication_urls_for_scenario(
            user_id=user_id,
            scenario=scenario
        )
        
        # Add redirect URL if provided
        if custom_redirect_url and 'authentication_urls' in result:
            for app_data in result['authentication_urls'].values():
                if 'auth_url' in app_data:
                    # Update redirect URL in the auth URL if needed
                    # This is a simplified approach - in practice you might want
                    # to regenerate the URLs with the custom redirect
                    app_data['custom_redirect'] = custom_redirect_url
        
        return result
        
    except Exception as e:
        logger.error(f"Error connecting scenario apps: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect scenario apps: {str(e)}"
        )


@router.post("/auth/bulk-check")
async def bulk_check_authentication(
    app_names: List[str],
    user_id: str = Depends(lambda: "user_demo"),
    controller: AuthController = Depends(get_auth_controller)
) -> Dict[str, Any]:
    """
    Check authentication status for multiple apps efficiently.
    
    This endpoint allows clients to check the authentication status
    for multiple apps in a single request.
    """
    try:
        logger.info(f"Bulk checking auth for {len(app_names)} apps for user {user_id}")
        
        # Bulk check authentication
        results = await controller.auth_manager.bulk_check_authentication(
            user_id=user_id,
            app_names=app_names
        )
        
        return {
            'user_id': user_id,
            'app_authentication_status': results,
            'total_apps_checked': len(app_names),
            'authenticated_apps': [app for app, status in results.items() if status],
            'unauthenticated_apps': [app for app, status in results.items() if not status],
            'authenticated_count': sum(results.values()),
            'authentication_percentage': (sum(results.values()) / len(app_names) * 100) if app_names else 0
        }
        
    except Exception as e:
        logger.error(f"Error in bulk authentication check: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check authentication status: {str(e)}"
        )


class ConnectAppRequest(BaseModel):
    app_name: str = Field(..., description="Name of the app to connect")
    custom_redirect_url: Optional[str] = Field(None, description="Custom OAuth callback URL")
    
    class Config:
        schema_extra = {
            "example": {
                "app_name": "gmail",
                "custom_redirect_url": "http://localhost:3000/auth/callback"
            }
        }


@router.get("/auth/callback")
async def oauth_callback(
    code: Optional[str] = Query(None, description="Authorization code"),
    state: Optional[str] = Query(None, description="OAuth state parameter"),
    app: Optional[str] = Query(None, description="App name"),
    error: Optional[str] = Query(None, description="OAuth error"),
    interaction_id: Optional[str] = Query(None, description="Chat interaction ID for workflow integration"),
    controller: AuthController = Depends(get_auth_controller)
) -> Dict[str, Any]:
    """
    Enhanced OAuth callback endpoint that handles redirects from external services.
    
    This endpoint is called by external services after the user completes
    the OAuth flow. It supports both traditional OAuth flows and chat workflow
    integration through interaction_id parameter.
    """
    try:
        if error:
            logger.error(f"OAuth error received: {error}")
            
            # If this is part of a chat workflow, we need to handle it gracefully
            if interaction_id:
                return {
                    "status": "oauth_failed",
                    "message": f"Authentication failed: {error}",
                    "interaction_id": interaction_id,
                    "redirect_type": "chat_error",
                    "redirect_url": f"/chat?error=oauth_failed&message={error}&interaction_id={interaction_id}"
                }
            
            raise HTTPException(
                status_code=400,
                detail=f"OAuth authorization failed: {error}"
            )
        
        if not code:
            error_msg = "Authorization code is required"
            logger.warning(error_msg)
            
            if interaction_id:
                return {
                    "status": "oauth_failed",
                    "message": error_msg,
                    "interaction_id": interaction_id,
                    "redirect_type": "chat_error",
                    "redirect_url": f"/chat?error=missing_code&interaction_id={interaction_id}"
                }
            
            raise HTTPException(
                status_code=400,
                detail=error_msg
            )
        
        logger.info(f"Processing OAuth callback for app: {app}, state: {state}, interaction_id: {interaction_id}")
        
        # Handle chat workflow integration
        if interaction_id:
            try:
                # Complete OAuth and continue chat workflow automatically
                # This assumes the chat service is available globally (will be injected in main app)
                
                # For now, return success info for chat interface to handle
                return {
                    "status": "oauth_completed",
                    "message": f"Successfully connected to {app}! Continuing with your request...",
                    "auth_code": code,
                    "app": app,
                    "state": state,
                    "interaction_id": interaction_id,
                    "redirect_type": "chat_success",
                    "redirect_url": f"/chat?oauth_success=true&app={app}&interaction_id={interaction_id}&auth_code={code}",
                    "auto_continue": True
                }
                
            except Exception as chat_error:
                logger.error(f"Error handling chat OAuth callback: {str(chat_error)}")
                return {
                    "status": "oauth_completed_with_error",
                    "message": f"Authentication successful but encountered an error continuing the workflow: {str(chat_error)}",
                    "auth_code": code,
                    "app": app,
                    "interaction_id": interaction_id,
                    "redirect_type": "chat_error",
                    "redirect_url": f"/chat?oauth_error=workflow_continuation&interaction_id={interaction_id}"
                }
        
        # Traditional OAuth flow (non-chat)
        return {
            "status": "callback_received",
            "message": "OAuth callback processed successfully",
            "auth_code": code,
            "app": app,
            "state": state,
            "redirect_type": "traditional",
            "next_step": "Use the auth_code with POST /auth/connect/{session_id}/complete to complete the connection"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing OAuth callback: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process OAuth callback: {str(e)}"
        )


@router.post("/auth/connect/{app_name}")
async def connect_app_enhanced(
    app_name: str,
    request: Optional[ConnectAppRequest] = None,
    user_id: str = Depends(lambda: "user_demo"),
    controller: AuthController = Depends(get_auth_controller)
) -> Dict[str, Any]:
    """
    Enhanced app connection endpoint with better error handling and app validation.
    
    This endpoint provides improved connection initiation with support for
    different authentication types (OAuth2, API keys) and better error messages.
    """
    try:
        logger.info(f"Enhanced connection request for {app_name} from user {user_id}")
        
        # Normalize app name
        normalized_app = controller.auth_manager._normalize_app_name(app_name)
        
        # Check if app is supported
        if not controller.auth_manager._is_app_supported(normalized_app):
            raise HTTPException(
                status_code=400,
                detail=f"App '{app_name}' is not supported. Use /auth/apps to see supported apps."
            )
        
        # Get app configuration
        app_config = controller.auth_manager.SUPPORTED_APPS[normalized_app]
        
        # Handle API key apps
        if app_config['auth_type'] == 'api_key':
            return {
                'app_name': app_name,
                'auth_method': 'api_key',
                'status': 'requires_api_key_configuration',
                'message': f'{app_config["name"]} requires API key configuration. Please configure the API key in your environment variables.',
                'config_required': True,
                'app_config': app_config
            }
        
        # Generate OAuth URL
        custom_redirect = request.custom_redirect_url if request else None
        auth_url = await controller.auth_manager.generate_oauth_url(
            user_id=user_id,
            app_name=normalized_app,
            custom_redirect_url=custom_redirect
        )
        
        return {
            'app_name': app_name,
            'normalized_app_name': normalized_app,
            'auth_method': 'oauth2',
            'auth_url': auth_url,
            'status': 'oauth_initiated',
            'message': f'Visit the auth_url to complete {app_config["name"]} authentication',
            'app_config': app_config,
            'expires_in': 1800  # 30 minutes
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in enhanced app connection: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initiate connection: {str(e)}"
        )