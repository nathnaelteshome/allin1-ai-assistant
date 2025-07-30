import os
import json
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import logging
from firebase_admin import firestore
from .composio_service import ComposioService
from .firebase_service import FirebaseService

logger = logging.getLogger(__name__)


class ComposioAuthManager:
    """
    Manages OAuth authentication and connected accounts for Composio integrations.
    Handles user-specific account linking, token management, and authentication persistence.
    Supports all scenario-required apps: Gmail, Slack, GitHub, Skyscanner, Booking.com,
    TripAdvisor, Google Calendar, Zoom, DoorDash, Stripe, Twitter, and more.
    """
    
    # Comprehensive app configuration for all supported services
    SUPPORTED_APPS = {
        # Communication & Email
        'gmail': {
            'name': 'Gmail',
            'category': 'communication',
            'auth_type': 'oauth2',
            'scopes': ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.send'],
            'requires_approval': True
        },
        'slack': {
            'name': 'Slack',
            'category': 'communication', 
            'auth_type': 'oauth2',
            'scopes': ['channels:read', 'chat:write', 'users:read'],
            'requires_approval': True
        },
        
        # Development & Productivity
        'github': {
            'name': 'GitHub',
            'category': 'development',
            'auth_type': 'oauth2',
            'scopes': ['repo', 'user', 'issues'],
            'requires_approval': True
        },
        'notion': {
            'name': 'Notion',
            'category': 'productivity',
            'auth_type': 'oauth2',
            'scopes': ['read', 'write'],
            'requires_approval': True
        },
        
        # Travel & Booking
        'skyscanner': {
            'name': 'Skyscanner',
            'category': 'travel',
            'auth_type': 'api_key',
            'scopes': ['flight_search', 'flight_booking'],
            'requires_approval': False
        },
        'booking': {
            'name': 'Booking.com',
            'category': 'travel',
            'auth_type': 'oauth2',
            'scopes': ['read', 'booking'],
            'requires_approval': True
        },
        'tripadvisor': {
            'name': 'TripAdvisor',
            'category': 'travel',
            'auth_type': 'api_key',
            'scopes': ['read', 'search'],
            'requires_approval': False
        },
        
        # Business & Scheduling
        'google_calendar': {
            'name': 'Google Calendar',
            'category': 'scheduling',
            'auth_type': 'oauth2',
            'scopes': ['https://www.googleapis.com/auth/calendar'],
            'requires_approval': True
        },
        'zoom': {
            'name': 'Zoom',
            'category': 'scheduling',
            'auth_type': 'oauth2',
            'scopes': ['meeting:write', 'user:read'],
            'requires_approval': True
        },
        
        # Food & Delivery
        'doordash': {
            'name': 'DoorDash',
            'category': 'food',
            'auth_type': 'oauth2',
            'scopes': ['read', 'order'],
            'requires_approval': True
        },
        
        # Payment Processing
        'stripe': {
            'name': 'Stripe',
            'category': 'payment',
            'auth_type': 'api_key',
            'scopes': ['read', 'write'],
            'requires_approval': False
        },
        
        # Social Media
        'twitter': {
            'name': 'Twitter/X',
            'category': 'social',
            'auth_type': 'oauth2',
            'scopes': ['tweet.read', 'tweet.write', 'users.read'],
            'requires_approval': True
        },
        'x': {
            'name': 'X (Twitter)',
            'category': 'social',
            'auth_type': 'oauth2',
            'scopes': ['tweet.read', 'tweet.write', 'users.read'],
            'requires_approval': True
        }
    }
    
    # Scenario mappings - which apps are needed for each scenario
    SCENARIO_APPS = {
        'flight_booking': ['skyscanner', 'stripe', 'gmail'],
        'email_management': ['gmail', 'twitter'],
        'meeting_scheduling': ['google_calendar', 'zoom', 'gmail'],
        'trip_planning': ['skyscanner', 'booking', 'tripadvisor'],
        'food_ordering': ['doordash', 'stripe', 'twitter'],
        'social_posting': ['twitter', 'x']
    }
    
    def __init__(self, composio_service: ComposioService, firebase_service: FirebaseService):
        self.composio_service = composio_service
        self.firebase_service = firebase_service
        
        # Firestore collections
        self.connected_accounts_collection = 'composio_connected_accounts'
        self.oauth_sessions_collection = 'composio_oauth_sessions'
        
        logger.info(f"ComposioAuthManager initialized with support for {len(self.SUPPORTED_APPS)} apps")
    
    async def is_user_authenticated(self, user_id: str, app_name: str) -> bool:
        """
        Check if user has an authenticated connection for the given app.
        
        Args:
            user_id: User identifier
            app_name: App name to check (normalized to lowercase)
            
        Returns:
            True if user is authenticated for the app
        """
        try:
            # Normalize app name
            app_name = self._normalize_app_name(app_name)
            
            # Validate app is supported
            if not self._is_app_supported(app_name):
                logger.warning(f"App {app_name} is not supported")
                return False
                
            connected_accounts = await self.get_connected_accounts(user_id, app_name)
            
            # Check if any account is healthy
            healthy_accounts = [acc for acc in connected_accounts if acc.get('is_healthy', False)]
            return len(healthy_accounts) > 0
            
        except Exception as e:
            logger.error(f"Error checking authentication for {user_id}, {app_name}: {str(e)}")
            return False
    
    async def generate_oauth_url(self, user_id: str, app_name: str, custom_redirect_url: Optional[str] = None) -> str:
        """
        Generate OAuth URL for connecting an app with app-specific configuration.
        
        Args:
            user_id: User identifier
            app_name: App to connect (normalized internally)
            custom_redirect_url: Optional custom redirect URL
            
        Returns:
            OAuth URL for user to complete authentication
        """
        try:
            # Normalize and validate app name
            app_name = self._normalize_app_name(app_name)
            
            if not self._is_app_supported(app_name):
                raise ValueError(f"App {app_name} is not supported")
            
            app_config = self.SUPPORTED_APPS[app_name]
            
            # Determine redirect URL based on auth type and app
            if custom_redirect_url:
                redirect_url = custom_redirect_url
            else:
                base_redirect = os.getenv('OAUTH_REDIRECT_URL', 'http://localhost:5000/auth/callback')
                redirect_url = f"{base_redirect}?app={app_name}"
            
            # Check if already connected (for some apps we might want to allow multiple connections)
            if app_config.get('single_connection_only', True):
                is_connected = await self.is_user_authenticated(user_id, app_name)
                if is_connected:
                    logger.warning(f"User {user_id} already has a connected {app_name} account")
                    # For now, proceed with new connection - could be made configurable
            
            # Initiate account connection with app-specific metadata
            connection_result = await self.initiate_account_connection(
                user_id=user_id,
                app_name=app_name,
                redirect_url=redirect_url,
                metadata={
                    'app_config': app_config,
                    'requested_scopes': app_config.get('scopes', []),
                    'auth_type': app_config.get('auth_type', 'oauth2')
                }
            )
            
            return connection_result.get('auth_url', '')
            
        except Exception as e:
            logger.error(f"Error generating OAuth URL for {user_id}, {app_name}: {str(e)}")
            raise
    
    async def get_connected_accounts(self, user_id: str, app_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get connected accounts for a user, optionally filtered by app.
        
        Args:
            user_id: User identifier
            app_name: Optional app name filter
            
        Returns:
            List of connected accounts
        """
        try:
            # Get connected accounts from Composio
            connected_accounts = await self.composio_service.get_connected_accounts(user_id, app_name)
            
            # Also check our local storage for any additional metadata
            db = self.firebase_service.get_firestore_client()
            query = db.collection(self.connected_accounts_collection) \
                .where('user_id', '==', user_id) \
                .where('status', '==', 'connected')
            
            if app_name:
                query = query.where('app_name', '==', app_name.lower())
            
            docs = query.get()
            
            # Merge results
            local_accounts = []
            for doc in docs:
                data = doc.to_dict()
                local_accounts.append({
                    'id': doc.id,
                    'app': data.get('app_name'),
                    'status': data.get('status'),
                    'created_at': data.get('created_at'),
                    'metadata': data.get('metadata', {})
                })
            
            # Combine and deduplicate
            all_accounts = connected_accounts + local_accounts
            
            # Simple deduplication by app name
            seen_apps = set()
            unique_accounts = []
            for account in all_accounts:
                app = account.get('app', '').lower()
                if app and app not in seen_apps:
                    unique_accounts.append(account)
                    seen_apps.add(app)
            
            return unique_accounts
            
        except Exception as e:
            logger.error(f"Error getting connected accounts for user {user_id}: {str(e)}")
            # Return empty list instead of raising exception
            return []

    async def initiate_account_connection(
        self, 
        user_id: str, 
        app_name: str, 
        redirect_url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Initiate OAuth flow for connecting an external service account.
        
        Args:
            user_id: User identifier
            app_name: Service to connect (gmail, twitter, etc.)
            redirect_url: OAuth callback URL
            metadata: Additional metadata to store
            
        Returns:
            OAuth initiation data including auth URL
        """
        try:
            # Check if user already has a connected account for this app
            existing_accounts = await self.get_user_connected_accounts(user_id, app_name)
            
            if existing_accounts:
                logger.warning(f"User {user_id} already has connected {app_name} account")
                # Could either return existing or allow multiple accounts
                # For now, proceeding with new connection
            
            # Initiate OAuth flow with Composio
            oauth_result = await self.composio_service.initiate_oauth_flow(
                app_name=app_name,
                user_id=user_id,
                redirect_url=redirect_url
            )
            
            # Store OAuth session in Firebase
            session_data = {
                'user_id': user_id,
                'app_name': app_name.lower(),
                'connection_id': oauth_result['connection_id'],
                'auth_url': oauth_result['auth_url'],
                'redirect_url': redirect_url,
                'status': 'initiated',
                'created_at': firestore.SERVER_TIMESTAMP,
                'expires_at': datetime.utcnow() + timedelta(minutes=30),  # 30-minute expiry
                'metadata': metadata or {}
            }
            
            # Save session to Firestore
            session_ref = self.firebase_service.db.collection(self.oauth_sessions_collection).document()
            session_ref.set(session_data)
            
            result = {
                'session_id': session_ref.id,
                'auth_url': oauth_result['auth_url'],
                'connection_id': oauth_result['connection_id'],
                'app_name': app_name,
                'expires_in': 1800  # 30 minutes in seconds
            }
            
            logger.info(f"OAuth flow initiated for user {user_id}, app {app_name}, session {session_ref.id}")
            return result
            
        except Exception as e:
            logger.error(f"Error initiating account connection: {str(e)}")
            raise

    async def complete_account_connection(
        self, 
        session_id: str, 
        auth_code: str
    ) -> Dict[str, Any]:
        """
        Complete OAuth flow and store connected account information.
        
        Args:
            session_id: OAuth session ID
            auth_code: Authorization code from OAuth callback
            
        Returns:
            Connection completion result
        """
        try:
            # Retrieve OAuth session
            session_ref = self.firebase_service.db.collection(self.oauth_sessions_collection).document(session_id)
            session_doc = session_ref.get()
            
            if not session_doc.exists:
                raise ValueError(f"OAuth session {session_id} not found")
            
            session_data = session_doc.to_dict()
            
            # Check session expiry
            if datetime.utcnow() > session_data['expires_at']:
                raise ValueError(f"OAuth session {session_id} has expired")
            
            # Complete OAuth flow with Composio
            connection_result = await self.composio_service.complete_oauth_flow(
                connection_id=session_data['connection_id'],
                auth_code=auth_code
            )
            
            # Store connected account information
            account_data = {
                'user_id': session_data['user_id'],
                'app_name': session_data['app_name'],
                'composio_connection_id': connection_result['connection_id'],
                'status': connection_result['status'],
                'connected_at': firestore.SERVER_TIMESTAMP,
                'last_used_at': firestore.SERVER_TIMESTAMP,
                'metadata': session_data.get('metadata', {}),
                'connection_metadata': connection_result
            }
            
            # Save to connected accounts collection
            account_ref = self.firebase_service.db.collection(self.connected_accounts_collection).document()
            account_ref.set(account_data)
            
            # Update session status
            session_ref.update({
                'status': 'completed',
                'completed_at': firestore.SERVER_TIMESTAMP,
                'account_id': account_ref.id
            })
            
            result = {
                'success': True,
                'account_id': account_ref.id,
                'user_id': session_data['user_id'],
                'app_name': session_data['app_name'],
                'status': connection_result['status'],
                'connected_at': datetime.utcnow().isoformat()
            }
            
            logger.info(f"Account connection completed for user {session_data['user_id']}, app {session_data['app_name']}")
            return result
            
        except Exception as e:
            logger.error(f"Error completing account connection: {str(e)}")
            
            # Update session with error status
            try:
                session_ref = self.firebase_service.db.collection(self.oauth_sessions_collection).document(session_id)
                session_ref.update({
                    'status': 'failed',
                    'error': str(e),
                    'failed_at': firestore.SERVER_TIMESTAMP
                })
            except:
                pass  # Don't fail if we can't update session
            
            raise

    async def get_user_connected_accounts(
        self, 
        user_id: str, 
        app_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all connected accounts for a user, optionally filtered by app.
        
        Args:
            user_id: User identifier
            app_name: Optional app name filter
            
        Returns:
            List of connected accounts with metadata
        """
        try:
            query = self.firebase_service.db.collection(self.connected_accounts_collection)\
                .where('user_id', '==', user_id)\
                .where('status', '==', 'connected')
            
            if app_name:
                query = query.where('app_name', '==', app_name.lower())
            
            docs = query.get()
            
            accounts = []
            for doc in docs:
                account_data = doc.to_dict()
                account_data['id'] = doc.id
                
                # Add account health check
                account_data['is_healthy'] = await self._check_account_health(
                    account_data['composio_connection_id'],
                    account_data['app_name']
                )
                
                accounts.append(account_data)
            
            logger.info(f"Retrieved {len(accounts)} connected accounts for user {user_id}")
            return accounts
            
        except Exception as e:
            logger.error(f"Error getting connected accounts for user {user_id}: {str(e)}")
            return []

    async def get_account_for_tool_execution(
        self, 
        user_id: str, 
        app_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get the best connected account for tool execution.
        
        Args:
            user_id: User identifier
            app_name: App name for the tool
            
        Returns:
            Connected account data or None if no valid account
        """
        try:
            accounts = await self.get_user_connected_accounts(user_id, app_name)
            
            if not accounts:
                logger.warning(f"No connected {app_name} accounts found for user {user_id}")
                return None
            
            # Filter for healthy accounts
            healthy_accounts = [acc for acc in accounts if acc.get('is_healthy', False)]
            
            if not healthy_accounts:
                logger.warning(f"No healthy {app_name} accounts found for user {user_id}")
                return None
            
            # Return the most recently used healthy account
            best_account = max(healthy_accounts, key=lambda x: x.get('last_used_at', datetime.min))
            
            # Update last used timestamp
            await self._update_account_last_used(best_account['id'])
            
            return best_account
            
        except Exception as e:
            logger.error(f"Error getting account for tool execution: {str(e)}")
            return None

    async def disconnect_account(self, user_id: str, account_id: str) -> Dict[str, Any]:
        """
        Disconnect a connected account.
        
        Args:
            user_id: User identifier
            account_id: Account ID to disconnect
            
        Returns:
            Disconnection result
        """
        try:
            # Get account document
            account_ref = self.firebase_service.db.collection(self.connected_accounts_collection).document(account_id)
            account_doc = account_ref.get()
            
            if not account_doc.exists:
                raise ValueError(f"Account {account_id} not found")
            
            account_data = account_doc.to_dict()
            
            # Verify ownership
            if account_data['user_id'] != user_id:
                raise ValueError(f"Account {account_id} does not belong to user {user_id}")
            
            # Update account status
            account_ref.update({
                'status': 'disconnected',
                'disconnected_at': firestore.SERVER_TIMESTAMP
            })
            
            result = {
                'success': True,
                'account_id': account_id,
                'app_name': account_data['app_name'],
                'disconnected_at': datetime.utcnow().isoformat()
            }
            
            logger.info(f"Account {account_id} disconnected for user {user_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error disconnecting account {account_id}: {str(e)}")
            raise

    async def refresh_account_status(self, user_id: str, account_id: str) -> Dict[str, Any]:
        """
        Refresh the status of a connected account.
        
        Args:
            user_id: User identifier
            account_id: Account ID to refresh
            
        Returns:
            Updated account status
        """
        try:
            # Get account document
            account_ref = self.firebase_service.db.collection(self.connected_accounts_collection).document(account_id)
            account_doc = account_ref.get()
            
            if not account_doc.exists:
                raise ValueError(f"Account {account_id} not found")
            
            account_data = account_doc.to_dict()
            
            # Verify ownership
            if account_data['user_id'] != user_id:
                raise ValueError(f"Account {account_id} does not belong to user {user_id}")
            
            # Check account health with Composio
            is_healthy = await self._check_account_health(
                account_data['composio_connection_id'],
                account_data['app_name']
            )
            
            # Update health status
            account_ref.update({
                'is_healthy': is_healthy,
                'last_health_check': firestore.SERVER_TIMESTAMP
            })
            
            result = {
                'account_id': account_id,
                'app_name': account_data['app_name'],
                'is_healthy': is_healthy,
                'last_checked': datetime.utcnow().isoformat()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error refreshing account status: {str(e)}")
            raise

    async def _check_account_health(self, composio_connection_id: str, app_name: str) -> bool:
        """
        Check if a connected account is healthy and can be used for tool execution.
        
        Args:
            composio_connection_id: Composio connection ID
            app_name: App name
            
        Returns:
            True if account is healthy
        """
        try:
            # Try to get account info from Composio
            # This is a simplified health check - in reality, you might want to
            # try a simple read operation to verify the connection works
            accounts = await self.composio_service.get_connected_accounts("dummy_user", app_name)
            
            # Look for this specific connection in the results
            for account in accounts:
                if account.get('id') == composio_connection_id:
                    return account.get('status') == 'connected'
            
            return False
            
        except Exception as e:
            logger.error(f"Health check failed for connection {composio_connection_id}: {str(e)}")
            return False

    async def _update_account_last_used(self, account_id: str):
        """
        Update the last used timestamp for an account.
        
        Args:
            account_id: Account ID to update
        """
        try:
            account_ref = self.firebase_service.db.collection(self.connected_accounts_collection).document(account_id)
            account_ref.update({
                'last_used_at': firestore.SERVER_TIMESTAMP
            })
        except Exception as e:
            logger.error(f"Error updating last used timestamp for account {account_id}: {str(e)}")

    async def cleanup_expired_sessions(self):
        """
        Clean up expired OAuth sessions.
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=24)  # Clean up sessions older than 24 hours
            
            expired_sessions = self.firebase_service.db.collection(self.oauth_sessions_collection)\
                .where('expires_at', '<', cutoff_time)\
                .get()
            
            batch = self.firebase_service.db.batch()
            
            for doc in expired_sessions:
                batch.delete(doc.reference)
            
            batch.commit()
            
            logger.info(f"Cleaned up {len(expired_sessions)} expired OAuth sessions")
            
        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {str(e)}")

    async def get_oauth_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get OAuth session data by session ID.
        
        Args:
            session_id: Session ID
            
        Returns:
            Session data or None if not found
        """
        try:
            session_ref = self.firebase_service.db.collection(self.oauth_sessions_collection).document(session_id)
            session_doc = session_ref.get()
            
            if not session_doc.exists:
                return None
            
            session_data = session_doc.to_dict()
            session_data['id'] = session_doc.id
            
            return session_data
            
        except Exception as e:
            logger.error(f"Error getting OAuth session {session_id}: {str(e)}")
            return None

    async def get_user_oauth_sessions(self, user_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get OAuth sessions for a user.
        
        Args:
            user_id: User identifier
            status: Optional status filter
            
        Returns:
            List of OAuth sessions
        """
        try:
            query = self.firebase_service.db.collection(self.oauth_sessions_collection)\
                .where('user_id', '==', user_id)\
                .order_by('created_at', direction=firestore.Query.DESCENDING)
            
            if status:
                query = query.where('status', '==', status)
            
            docs = query.limit(20).get()  # Limit to recent 20 sessions
            
            sessions = []
            for doc in docs:
                session_data = doc.to_dict()
                session_data['id'] = doc.id
                sessions.append(session_data)
            
            return sessions
            
        except Exception as e:
            logger.error(f"Error getting OAuth sessions for user {user_id}: {str(e)}")
            return []
    
    def _normalize_app_name(self, app_name: str) -> str:
        """
        Normalize app name to standard format.
        
        Args:
            app_name: Raw app name
            
        Returns:
            Normalized app name
        """
        if not app_name:
            return ''
            
        # Convert to lowercase and handle common variations
        normalized = app_name.lower().strip()
        
        # Handle common app name variations
        app_name_mappings = {
            'google_calendar': 'google_calendar',
            'googlecalendar': 'google_calendar',
            'calendar': 'google_calendar',
            'booking.com': 'booking',
            'bookingcom': 'booking',
            'trip_advisor': 'tripadvisor',
            'door_dash': 'doordash',
            'x': 'twitter',  # X is treated as Twitter
            'twitterx': 'twitter'
        }
        
        return app_name_mappings.get(normalized, normalized)
    
    def _is_app_supported(self, app_name: str) -> bool:
        """
        Check if an app is supported.
        
        Args:
            app_name: Normalized app name
            
        Returns:
            True if app is supported
        """
        return app_name in self.SUPPORTED_APPS
    
    def get_supported_apps(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all supported apps and their configurations.
        
        Returns:
            Dictionary of supported apps and their configs
        """
        return self.SUPPORTED_APPS.copy()
    
    def get_apps_for_scenario(self, scenario: str) -> List[str]:
        """
        Get required apps for a specific scenario.
        
        Args:
            scenario: Scenario name
            
        Returns:
            List of required app names
        """
        return self.SCENARIO_APPS.get(scenario, [])
    
    async def check_scenario_authentication(self, user_id: str, scenario: str) -> Dict[str, Any]:
        """
        Check authentication status for all apps required by a scenario.
        
        Args:
            user_id: User identifier
            scenario: Scenario name
            
        Returns:
            Authentication status for scenario
        """
        try:
            required_apps = self.get_apps_for_scenario(scenario)
            
            if not required_apps:
                return {
                    'scenario': scenario,
                    'supported': False,
                    'error': f'Unknown scenario: {scenario}'
                }
            
            auth_status = {}
            all_authenticated = True
            
            for app_name in required_apps:
                is_auth = await self.is_user_authenticated(user_id, app_name)
                auth_status[app_name] = {
                    'authenticated': is_auth,
                    'required': True,
                    'app_config': self.SUPPORTED_APPS.get(app_name, {})
                }
                if not is_auth:
                    all_authenticated = False
            
            return {
                'scenario': scenario,
                'supported': True,
                'fully_authenticated': all_authenticated,
                'required_apps': required_apps,
                'app_status': auth_status,
                'authenticated_count': sum(1 for status in auth_status.values() if status['authenticated']),
                'total_required': len(required_apps)
            }
            
        except Exception as e:
            logger.error(f"Error checking scenario authentication for {scenario}: {str(e)}")
            return {
                'scenario': scenario,
                'supported': False,
                'error': str(e)
            }
    
    async def get_authentication_urls_for_scenario(self, user_id: str, scenario: str) -> Dict[str, Any]:
        """
        Generate authentication URLs for all unauthenticated apps in a scenario.
        
        Args:
            user_id: User identifier
            scenario: Scenario name
            
        Returns:
            Dictionary with authentication URLs for required apps
        """
        try:
            scenario_status = await self.check_scenario_authentication(user_id, scenario)
            
            if not scenario_status['supported']:
                return scenario_status
            
            auth_urls = {}
            
            for app_name, status in scenario_status['app_status'].items():
                if not status['authenticated']:
                    try:
                        auth_url = await self.generate_oauth_url(user_id, app_name)
                        auth_urls[app_name] = {
                            'auth_url': auth_url,
                            'app_name': app_name,
                            'display_name': self.SUPPORTED_APPS[app_name]['name'],
                            'category': self.SUPPORTED_APPS[app_name]['category'],
                            'auth_type': self.SUPPORTED_APPS[app_name]['auth_type']
                        }
                    except Exception as e:
                        auth_urls[app_name] = {
                            'error': str(e),
                            'app_name': app_name
                        }
            
            return {
                'scenario': scenario,
                'authentication_urls': auth_urls,
                'total_urls_generated': len([url for url in auth_urls.values() if 'auth_url' in url]),
                'errors': [app for app, data in auth_urls.items() if 'error' in data]
            }
            
        except Exception as e:
            logger.error(f"Error generating authentication URLs for scenario {scenario}: {str(e)}")
            return {
                'scenario': scenario,
                'error': str(e)
            }
    
    async def bulk_check_authentication(self, user_id: str, app_names: List[str]) -> Dict[str, bool]:
        """
        Check authentication status for multiple apps efficiently.
        
        Args:
            user_id: User identifier
            app_names: List of app names to check
            
        Returns:
            Dictionary mapping app names to authentication status
        """
        results = {}
        
        # Use asyncio.gather for concurrent checking
        try:
            auth_checks = [self.is_user_authenticated(user_id, app_name) for app_name in app_names]
            auth_results = await asyncio.gather(*auth_checks, return_exceptions=True)
            
            for i, app_name in enumerate(app_names):
                if isinstance(auth_results[i], Exception):
                    logger.error(f"Error checking auth for {app_name}: {auth_results[i]}")
                    results[app_name] = False
                else:
                    results[app_name] = auth_results[i]
                    
        except Exception as e:
            logger.error(f"Error in bulk authentication check: {str(e)}")
            # Fallback to individual checks
            for app_name in app_names:
                try:
                    results[app_name] = await self.is_user_authenticated(user_id, app_name)
                except Exception as app_error:
                    logger.error(f"Error checking {app_name}: {app_error}")
                    results[app_name] = False
        
        return results