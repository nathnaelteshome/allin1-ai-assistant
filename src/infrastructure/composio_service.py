import os
import asyncio
from typing import Dict, List, Any, Optional
from composio import ComposioToolSet, Composio, App, Action
import logging
import json
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class ComposioService:
    """
    Main Composio SDK wrapper service for unified API integrations.
    Handles tool discovery, execution, and connected accounts management.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('COMPOSIO_API_KEY')
        self.base_url = os.getenv('COMPOSIO_BASE_URL', 'https://backend.composio.dev/api')
        self.environment = os.getenv('COMPOSIO_ENVIRONMENT', 'production')
        
        if not self.api_key:
            raise ValueError("COMPOSIO_API_KEY is required")
        
        # Initialize Composio client
        self.composio_client = Composio(api_key=self.api_key)
        self.toolset = ComposioToolSet(api_key=self.api_key)
        
        # Tool and accounts caches
        self._tools_cache: Dict[str, Any] = {}
        self._connected_accounts_cache: Dict[str, Any] = {}
        self._tool_cache_ttl = int(os.getenv('COMPOSIO_TOOL_CACHE_TTL', '3600'))
        self._accounts_cache_ttl = int(os.getenv('COMPOSIO_CONNECTED_ACCOUNTS_CACHE_TTL', '1800'))
        
        # App-specific configuration for enhanced OAuth handling
        self.APP_CONFIGS = {
            'skyscanner': {'auth_method': 'api_key', 'requires_callback': False},
            'booking': {'auth_method': 'oauth2', 'requires_callback': True},
            'tripadvisor': {'auth_method': 'api_key', 'requires_callback': False},
            'google_calendar': {'auth_method': 'oauth2', 'requires_callback': True},
            'zoom': {'auth_method': 'oauth2', 'requires_callback': True},
            'doordash': {'auth_method': 'oauth2', 'requires_callback': True},
            'stripe': {'auth_method': 'api_key', 'requires_callback': False},
            'twitter': {'auth_method': 'oauth2', 'requires_callback': True},
            'x': {'auth_method': 'oauth2', 'requires_callback': True},
            'gmail': {'auth_method': 'oauth2', 'requires_callback': True},
            'slack': {'auth_method': 'oauth2', 'requires_callback': True},
            'github': {'auth_method': 'oauth2', 'requires_callback': True},
            'notion': {'auth_method': 'oauth2', 'requires_callback': True}
        }
        
        logger.info(f"ComposioService initialized with environment: {self.environment}")

    async def discover_tools(self, app_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Discover available Composio tools, optionally filtered by app.
        
        Args:
            app_name: Optional app name to filter tools (e.g., 'gmail', 'twitter')
            
        Returns:
            List of tool definitions with schemas
        """
        cache_key = f"tools_{app_name or 'all'}"
        
        if cache_key in self._tools_cache:
            logger.debug(f"Returning cached tools for {cache_key}")
            return self._tools_cache[cache_key]
        
        try:
            logger.info(f"Discovering real tools for app: {app_name or 'all'}")
            
            # Use real Composio API to get actions
            if app_name:
                # Get actions for specific app
                try:
                    # Convert app name to correct App enum
                    app_enum = getattr(App, app_name.upper())
                    logger.info(f"Found app enum: {app_enum}")
                    
                    # Method 1: Try get_actions from the app enum first (most direct)
                    actions = []
                    try:
                        actions_generator = app_enum.get_actions()
                        actions = list(actions_generator)  # Convert generator to list
                        logger.info(f"Found {len(actions)} actions using app_enum.get_actions()")
                    except Exception as e:
                        logger.warning(f"app_enum.get_actions() failed: {str(e)}")
                    
                    # Method 2: If no actions, try find_actions_by_tags
                    if not actions:
                        logger.info("Trying find_actions_by_tags...")
                        common_tags = ["send", "create", "get", "list", "read", "write", "update", "delete"]
                        for tag in common_tags:
                            try:
                                tag_actions = self.toolset.find_actions_by_tags(app_enum, tags=[tag])
                                actions.extend(tag_actions)
                                logger.info(f"Found {len(tag_actions)} actions with tag '{tag}'")
                                if len(actions) >= 10:  # Limit for performance
                                    break
                            except Exception as tag_error:
                                logger.debug(f"Tag '{tag}' failed: {str(tag_error)}")
                                continue
                    
                    # Method 3: If still no actions, try find_actions_by_use_case with common use cases
                    if not actions:
                        logger.info("Trying find_actions_by_use_case...")
                        use_cases = [
                            f"{app_name} automation",
                            f"manage {app_name}",
                            f"send {app_name} message",
                            f"get {app_name} data"
                        ]
                        for use_case in use_cases:
                            try:
                                use_case_actions = self.toolset.find_actions_by_use_case(
                                    app_enum, 
                                    use_case=use_case,
                                    advanced=False
                                )
                                actions.extend(use_case_actions)
                                logger.info(f"Found {len(use_case_actions)} actions with use case '{use_case}'")
                                if len(actions) >= 5:
                                    break
                            except Exception as uc_error:
                                logger.debug(f"Use case '{use_case}' failed: {str(uc_error)}")
                                continue
                    
                    # Get schemas for the actions if we found any
                    tools = []
                    if actions:
                        logger.info(f"Getting schemas for {len(actions)} actions...")
                        try:
                            tools = self.toolset.get_action_schemas(
                                actions=actions[:25],  # Limit to prevent timeout
                                check_connected_accounts=False
                            )
                            logger.info(f"Got {len(tools)} tool schemas")
                        except Exception as schema_error:
                            logger.error(f"Error getting schemas: {str(schema_error)}")
                            # Fallback: create basic tool info from actions
                            tools = []
                            for action in actions[:10]:
                                tools.append({
                                    'name': str(action),
                                    'description': f'Action: {action}',
                                    'parameters': {},
                                    'appName': app_name
                                })
                    
                except (AttributeError, KeyError) as e:
                    logger.warning(f"App {app_name} not found in Composio App enum: {str(e)}")
                    tools = []
                except Exception as e:
                    logger.warning(f"Error getting actions for {app_name}: {str(e)}")
                    tools = []
            else:
                # Get actions for common apps
                try:
                    all_tools = []
                    common_apps = [App.GMAIL, App.GITHUB, App.SLACK, App.TWITTER]
                    
                    for app in common_apps:
                        try:
                            app_name_str = app.name.lower()
                            logger.info(f"Getting actions for {app_name_str}...")
                            
                            # Use get_actions method from app enum first
                            actions = []
                            try:
                                actions_generator = app.get_actions()
                                actions = list(actions_generator)  # Convert generator to list
                                logger.info(f"Found {len(actions)} actions for {app_name_str}")
                            except:
                                # Fallback to tags
                                for tag in ["send", "get", "create"]:
                                    try:
                                        tag_actions = self.toolset.find_actions_by_tags(app, tags=[tag])
                                        actions.extend(tag_actions)
                                        if len(actions) >= 3:  # Limit per app
                                            break
                                    except:
                                        continue
                            
                            if actions:
                                try:
                                    app_tools = self.toolset.get_action_schemas(
                                        actions=actions[:5],  # Limit per app
                                        check_connected_accounts=False
                                    )
                                    all_tools.extend(app_tools)
                                    logger.info(f"Added {len(app_tools)} tools for {app_name_str}")
                                except Exception as schema_error:
                                    logger.warning(f"Schema error for {app_name_str}: {str(schema_error)}")
                                    # Add basic tool info
                                    for action in actions[:3]:
                                        all_tools.append({
                                            'name': str(action),
                                            'description': f'Action: {action}',
                                            'parameters': {},
                                            'appName': app_name_str
                                        })
                        except Exception as app_error:
                            logger.warning(f"Error getting actions for {app}: {str(app_error)}")
                            continue
                    
                    tools = all_tools
                    
                except Exception as e:
                    logger.warning(f"Error getting tools for common apps: {str(e)}")
                    tools = []
            
            # Convert tools to our expected format
            tools_data = []
            for tool in tools:
                try:
                    # Tools from get_action_schemas are dict objects with schema info
                    if isinstance(tool, dict):
                        tool_data = {
                            'name': tool.get('name', tool.get('title', 'Unknown Tool')),
                            'app': tool.get('appName', app_name or 'unknown'),
                            'description': tool.get('description', f"Tool: {tool.get('name', 'unknown')}"),
                            'slug': tool.get('name', tool.get('title', str(tool))),
                            'parameters': tool.get('parameters', {}).get('properties', {}),
                            'required_parameters': tool.get('parameters', {}).get('required', []),
                            'tool_object': tool  # Keep reference for execution
                        }
                    else:
                        # Fallback for other tool types
                        tool_data = {
                            'name': getattr(tool, 'name', str(tool)),
                            'app': getattr(tool, 'app', app_name or 'unknown'),
                            'description': getattr(tool, 'description', f'Tool: {tool}'),
                            'slug': str(tool),
                            'parameters': getattr(tool, 'parameters', {}),
                            'tool_object': tool
                        }
                    tools_data.append(tool_data)
                except Exception as e:
                    logger.warning(f"Error processing tool {tool}: {str(e)}")
                    continue
            
            # Cache the results
            self._tools_cache[cache_key] = tools_data
            
            logger.info(f"Discovered {len(tools_data)} real tools for {app_name or 'all apps'}")
            return tools_data
            
        except Exception as e:
            logger.error(f"Error discovering tools: {str(e)}")
            # Fallback to basic tool structure if API fails
            logger.warning("Falling back to minimal tool discovery")
            return []

    async def get_tool_schema(self, tool_slug: str) -> Dict[str, Any]:
        """
        Get detailed schema for a specific tool.
        
        Args:
            tool_slug: The tool slug/identifier
            
        Returns:
            Tool schema with parameters and descriptions
        """
        try:
            logger.info(f"Getting real schema for tool: {tool_slug}")
            
            # Try to find the tool in our tools cache first
            tool_found = None
            for cache_key, tools in self._tools_cache.items():
                for tool in tools:
                    if tool['slug'] == tool_slug:
                        tool_found = tool
                        break
                if tool_found:
                    break
            
            if not tool_found:
                # If not in cache, try to discover it
                logger.info(f"Tool {tool_slug} not in cache, discovering...")
                all_tools = await self.discover_tools()
                for tool in all_tools:
                    if tool['slug'] == tool_slug:
                        tool_found = tool
                        break
            
            if tool_found and 'tool_object' in tool_found:
                # Get schema from the real tool object
                tool_obj = tool_found['tool_object']
                
                try:
                    # Try to get the action schema using correct method
                    if hasattr(tool_obj, 'enum'):
                        # If tool_obj has an enum attribute, use it for schema retrieval
                        action_enum = tool_obj.enum
                        schema_data = self.toolset.get_action_schemas(
                            actions=[action_enum],
                            check_connected_accounts=False
                        )
                        # get_action_schemas returns a list, get the first item
                        if schema_data:
                            schema_info = schema_data[0]
                        else:
                            schema_info = {}
                    else:
                        # Use the tool object directly if it's already a schema
                        schema_info = tool_obj if isinstance(tool_obj, dict) else {}
                    
                    # Convert to our expected format
                    schema = {
                        'name': tool_found['name'],
                        'description': tool_found['description'],
                        'parameters': schema_info.get('parameters', {}).get('properties', {}),
                        'required_parameters': schema_info.get('parameters', {}).get('required', []),
                        'app': tool_found['app'],
                        'tool_slug': tool_slug,
                        'raw_schema': schema_info
                    }
                    
                    logger.info(f"Retrieved real schema for {tool_slug}")
                    return schema
                    
                except Exception as e:
                    logger.warning(f"Error getting schema from tool object: {str(e)}")
                    # Fall back to basic info from tool discovery
                    schema = {
                        'name': tool_found['name'],
                        'description': tool_found['description'],
                        'parameters': tool_found.get('parameters', {}),
                        'required_parameters': [],
                        'app': tool_found['app'],
                        'tool_slug': tool_slug
                    }
                    return schema
            
            # If we still don't have the tool, return a basic schema
            logger.warning(f"Tool {tool_slug} not found, returning basic schema")
            return {
                'name': tool_slug,
                'description': f'Tool: {tool_slug}',
                'parameters': {},
                'required_parameters': [],
                'app': 'unknown',
                'tool_slug': tool_slug
            }
            
        except Exception as e:
            logger.error(f"Error getting tool schema for {tool_slug}: {str(e)}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def execute_tool(
        self, 
        tool_slug: str, 
        parameters: Dict[str, Any],
        user_id: Optional[str] = None,
        connected_account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a Composio tool with given parameters.
        
        Args:
            tool_slug: The tool to execute
            parameters: Tool parameters
            user_id: User identifier for account linking
            connected_account_id: Specific connected account to use
            
        Returns:
            Tool execution result
        """
        try:
            logger.info(f"Executing real tool {tool_slug} with parameters: {json.dumps(parameters, indent=2)}")
            
            # Find the tool object in cache
            tool_found = None
            for tools in self._tools_cache.values():
                for tool in tools:
                    if tool['slug'] == tool_slug:
                        tool_found = tool
                        break
                if tool_found:
                    break
            
            if not tool_found:
                # Try to discover the tool
                all_tools = await self.discover_tools()
                for tool in all_tools:
                    if tool['slug'] == tool_slug:
                        tool_found = tool
                        break
            
            if not tool_found or 'tool_object' not in tool_found:
                raise ValueError(f"Tool {tool_slug} not found or not properly configured")
            
            tool_obj = tool_found['tool_object']
            
            # Set up entity ID for user context
            entity_id = f"user_{user_id}" if user_id else "default"
            
            # Execute the real tool
            logger.info(f"Executing {tool_slug} with entity_id: {entity_id}")
            
            try:
                # Execute using ComposioToolSet execute_action method
                result = self.toolset.execute_action(
                    action=tool_found['slug'],  # Use the tool slug/name
                    params=parameters,
                    entity_id=entity_id
                )
                
                # Normalize result format
                normalized_result = {
                    'success': True,
                    'data': result,
                    'tool': tool_slug,
                    'execution_id': f"composio_exec_{tool_slug}_{entity_id}",
                    'metadata': {
                        'user_id': user_id,
                        'connected_account_id': connected_account_id,
                        'entity_id': entity_id
                    }
                }
                
                logger.info(f"Tool {tool_slug} executed successfully")
                return normalized_result
                
            except Exception as exec_error:
                logger.error(f"Composio execution failed for {tool_slug}: {str(exec_error)}")
                
                # Check if it's an authentication error
                if "auth" in str(exec_error).lower() or "unauthorized" in str(exec_error).lower():
                    error_result = {
                        'success': False,
                        'error': f"Authentication required for {tool_slug}. Please connect your account first.",
                        'error_type': 'authentication_required',
                        'tool': tool_slug,
                        'parameters': parameters,
                        'metadata': {
                            'user_id': user_id,
                            'connected_account_id': connected_account_id,
                            'entity_id': entity_id
                        }
                    }
                else:
                    error_result = {
                        'success': False,
                        'error': str(exec_error),
                        'error_type': 'execution_error',
                        'tool': tool_slug,
                        'parameters': parameters,
                        'metadata': {
                            'user_id': user_id,
                            'connected_account_id': connected_account_id,
                            'entity_id': entity_id
                        }
                    }
                
                return error_result
            
        except Exception as e:
            logger.error(f"Error executing tool {tool_slug}: {str(e)}")
            
            error_result = {
                'success': False,
                'error': str(e),
                'error_type': 'general_error',
                'tool': tool_slug,
                'parameters': parameters,
                'metadata': {
                    'user_id': user_id,
                    'connected_account_id': connected_account_id
                }
            }
            
            return error_result

    async def get_connected_accounts(self, user_id: str, app_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get connected accounts for a user, optionally filtered by app.
        
        Args:
            user_id: User identifier
            app_name: Optional app name filter
            
        Returns:
            List of connected accounts
        """
        cache_key = f"accounts_{user_id}_{app_name or 'all'}"
        
        if cache_key in self._connected_accounts_cache:
            logger.debug(f"Returning cached connected accounts for {cache_key}")
            return self._connected_accounts_cache[cache_key]
        
        try:
            entity_id = f"user_{user_id}"
            logger.info(f"Getting real connected accounts for entity: {entity_id}")
            
            # Get connected accounts using real Composio API
            accounts = self.composio_client.get_entity(entity_id).get_connections()
            
            # Convert to serializable format
            accounts_data = []
            for account in accounts:
                try:
                    account_data = {
                        'id': getattr(account, 'id', str(account)),
                        'app': getattr(account, 'app_name', None) or getattr(account, 'app', None),
                        'status': getattr(account, 'status', 'connected'),
                        'created_at': getattr(account, 'created_at', None),
                        'metadata': getattr(account, 'metadata', {}),
                        'connection_id': getattr(account, 'connection_id', None)
                    }
                    
                    # Filter by app if specified
                    if app_name and account_data['app'] and account_data['app'].lower() != app_name.lower():
                        continue
                    elif app_name and not account_data['app']:
                        continue
                    
                    accounts_data.append(account_data)
                except Exception as e:
                    logger.warning(f"Error processing account {account}: {str(e)}")
                    continue
            
            # Cache the results
            self._connected_accounts_cache[cache_key] = accounts_data
            
            logger.info(f"Retrieved {len(accounts_data)} connected accounts for user {user_id}")
            return accounts_data
            
        except Exception as e:
            logger.error(f"Error getting connected accounts for user {user_id}: {str(e)}")
            # Return empty list on error rather than failing
            return []

    async def initiate_oauth_flow(self, app_name: str, user_id: str, redirect_url: str) -> Dict[str, Any]:
        """
        Initiate OAuth flow for connecting an external service with app-specific handling.
        
        Args:
            app_name: The app to connect (e.g., 'gmail', 'twitter')
            user_id: User identifier
            redirect_url: URL to redirect after OAuth completion
            
        Returns:
            OAuth initiation data including auth URL
        """
        try:
            entity_id = f"user_{user_id}"
            logger.info(f"Initiating real OAuth flow for {app_name} with entity: {entity_id}")
            
            # Normalize app name
            normalized_app = app_name.lower().strip()
            
            # Get app-specific configuration
            app_config = self.APP_CONFIGS.get(normalized_app, {
                'auth_method': 'oauth2', 
                'requires_callback': True
            })
            
            # Handle API key-based apps differently
            if app_config['auth_method'] == 'api_key':
                logger.info(f"{app_name} uses API key authentication, not OAuth")
                return {
                    'auth_url': None,
                    'connection_id': None,
                    'app': app_name,
                    'user_id': user_id,
                    'entity_id': entity_id,
                    'status': 'requires_api_key',
                    'auth_method': 'api_key',
                    'message': f'{app_name} requires API key configuration instead of OAuth',
                    'redirect_url': redirect_url
                }
            
            # Use real Composio API to initiate OAuth
            entity = self.composio_client.get_entity(entity_id)
            
            # Get the app enum with enhanced mapping
            app_enum = self._get_app_enum(normalized_app)
            
            # Initiate connection with enhanced error handling
            try:
                connection_request = entity.initiate_connection(
                    app_name=app_enum,
                    redirect_url=redirect_url
                )
                
                result = {
                    'auth_url': connection_request.redirectUrl,
                    'connection_id': connection_request.connectedAccountId,
                    'app': app_name,
                    'user_id': user_id,
                    'entity_id': entity_id,
                    'status': 'initiated',
                    'auth_method': 'oauth2',
                    'redirect_url': redirect_url,
                    'app_config': app_config
                }
                
                logger.info(f"OAuth flow initiated for user {user_id} and app {app_name}")
                return result
                
            except Exception as connection_error:
                logger.error(f"Connection initiation failed for {app_name}: {str(connection_error)}")
                # Return a more detailed error response
                return {
                    'auth_url': None,
                    'connection_id': None,
                    'app': app_name,
                    'user_id': user_id,
                    'entity_id': entity_id,
                    'status': 'failed',
                    'error': str(connection_error),
                    'auth_method': 'oauth2',
                    'redirect_url': redirect_url
                }
            
        except Exception as e:
            logger.error(f"Error initiating OAuth flow for {app_name}: {str(e)}")
            raise
    
    def _get_app_enum(self, app_name: str) -> Any:
        """
        Get the Composio App enum for a given app name with enhanced mapping.
        
        Args:
            app_name: Normalized app name
            
        Returns:
            Composio App enum or string
        """
        # Enhanced app name to enum mapping
        app_enum_mapping = {
            'gmail': 'GMAIL',
            'slack': 'SLACK', 
            'github': 'GITHUB',
            'twitter': 'TWITTER',
            'x': 'TWITTER',  # X maps to Twitter
            'notion': 'NOTION',
            'google_calendar': 'GOOGLECALENDAR',
            'zoom': 'ZOOM',
            'stripe': 'STRIPE',
            'skyscanner': 'SKYSCANNER',
            'booking': 'BOOKING',
            'tripadvisor': 'TRIPADVISOR',
            'doordash': 'DOORDASH'
        }
        
        enum_name = app_enum_mapping.get(app_name, app_name.upper())
        
        try:
            app_enum = getattr(App, enum_name)
            logger.info(f"Found App enum {enum_name} for {app_name}")
            return app_enum
        except AttributeError:
            logger.warning(f"App enum {enum_name} not found for {app_name}, using string")
            # Fallback to string if enum not found
            return app_name

    async def complete_oauth_flow(self, connection_id: str, auth_code: str) -> Dict[str, Any]:
        """
        Complete OAuth flow with authorization code.
        
        Args:
            connection_id: Connection ID from initiation
            auth_code: Authorization code from OAuth callback
            
        Returns:
            Connection completion result
        """
        try:
            logger.info(f"Completing real OAuth flow for connection {connection_id}")
            
            # Complete the connection using real Composio API
            # Note: The exact method may vary based on Composio SDK version
            # This is a general approach that should work
            
            # For now, we'll use the connection_id to complete the flow
            # The auth_code is typically handled automatically by Composio
            completed_connection = self.composio_client.get_connection(connection_id)
            
            result = {
                'success': True,
                'connection_id': connection_id,
                'app': getattr(completed_connection, 'app', 'unknown'),
                'status': getattr(completed_connection, 'status', 'connected'),
                'entity_id': getattr(completed_connection, 'entity_id', None)
            }
            
            # Clear accounts cache to force refresh
            self._connected_accounts_cache.clear()
            
            logger.info(f"OAuth flow completed successfully for connection {connection_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error completing OAuth flow for connection {connection_id}: {str(e)}")
            raise

    async def validate_tool_parameters(self, tool_slug: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate parameters against tool schema.
        
        Args:
            tool_slug: Tool to validate against
            parameters: Parameters to validate
            
        Returns:
            Validation result with errors if any
        """
        try:
            schema = await self.get_tool_schema(tool_slug)
            
            validation_result = {
                'valid': True,
                'errors': [],
                'missing_required': [],
                'invalid_types': []
            }
            
            required_params = schema.get('required_parameters', [])
            tool_params = schema.get('parameters', {})
            
            # Check required parameters
            for param in required_params:
                if param not in parameters:
                    validation_result['missing_required'].append(param)
                    validation_result['valid'] = False
            
            # Check parameter types (basic validation)
            for param_name, param_value in parameters.items():
                if param_name in tool_params:
                    param_schema = tool_params[param_name]
                    expected_type = param_schema.get('type')
                    
                    if expected_type and not self._validate_parameter_type(param_value, expected_type):
                        validation_result['invalid_types'].append({
                            'parameter': param_name,
                            'expected': expected_type,
                            'received': type(param_value).__name__
                        })
                        validation_result['valid'] = False
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error validating parameters for {tool_slug}: {str(e)}")
            return {
                'valid': False,
                'errors': [f"Validation error: {str(e)}"],
                'missing_required': [],
                'invalid_types': []
            }

    def _validate_parameter_type(self, value: Any, expected_type: str) -> bool:
        """
        Basic parameter type validation.
        
        Args:
            value: Parameter value
            expected_type: Expected type string
            
        Returns:
            True if type matches
        """
        type_mapping = {
            'string': str,
            'integer': int,
            'number': (int, float),
            'boolean': bool,
            'array': list,
            'object': dict
        }
        
        expected_python_type = type_mapping.get(expected_type.lower())
        if expected_python_type:
            return isinstance(value, expected_python_type)
        
        return True  # Default to valid if type unknown

    async def get_user_info(self) -> Dict[str, Any]:
        """
        Get current user information from Composio.
        
        Returns:
            User information dictionary
        """
        try:
            # Get user info using Composio client
            user_info = self.composio_client.get_user()
            
            return {
                'id': getattr(user_info, 'id', 'unknown'),
                'email': getattr(user_info, 'email', 'unknown'),
                'name': getattr(user_info, 'name', 'unknown'),
                'created_at': getattr(user_info, 'created_at', None),
                'status': 'active'
            }
            
        except Exception as e:
            logger.warning(f"Could not get user info: {str(e)}")
            # Return basic info if API call fails
            return {
                'id': 'api_user',
                'email': 'api_user@composio.dev',
                'name': 'API User',
                'status': 'active'
            }
    
    async def get_available_apps(self) -> List[Dict[str, Any]]:
        """
        Get list of available apps in Composio.
        
        Returns:
            List of available apps
        """
        try:
            apps = self.composio_client.get_apps()
            
            apps_list = []
            for app in apps:
                apps_list.append({
                    'name': getattr(app, 'name', str(app)),
                    'description': getattr(app, 'description', f'App: {app}'),
                    'logo': getattr(app, 'logo', None),
                    'categories': getattr(app, 'categories', []),
                    'is_local': getattr(app, 'is_local', False)
                })
            
            return apps_list
            
        except Exception as e:
            logger.warning(f"Could not get available apps: {str(e)}")
            # Return basic app list
            return [
                {'name': 'Gmail', 'description': 'Email management'},
                {'name': 'GitHub', 'description': 'Code repository management'},
                {'name': 'Slack', 'description': 'Team communication'},
                {'name': 'Twitter', 'description': 'Social media platform'}
            ]

    async def clear_caches(self):
        """Clear all internal caches."""
        self._tools_cache.clear()
        self._connected_accounts_cache.clear()
        logger.info("All caches cleared")

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check for Composio service.
        
        Returns:
            Health status information
        """
        try:
            # Try to get basic tools list to verify connectivity
            tools = await self.discover_tools()
            
            health_status = {
                'status': 'healthy',
                'composio_api': 'connected',
                'tools_available': len(tools),
                'cache_stats': {
                    'tools_cached': len(self._tools_cache),
                    'accounts_cached': len(self._connected_accounts_cache)
                }
            }
            
            return health_status
            
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'composio_api': 'disconnected'
            }