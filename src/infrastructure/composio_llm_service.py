"""
Composio LLM Service - Common LLM-driven operations for Composio integration.

This service provides centralized LLM-driven functionality for:
- Tool selection from available Composio apps
- Action selection from tool-specific actions  
- Parameter normalization from natural language
- End-to-end natural language query execution

Used by test scripts and production services to avoid code duplication.
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Union
from datetime import datetime

from composio import ComposioToolSet, Action, App
from .gemini_service import GeminiService

logger = logging.getLogger(__name__)


class ComposioLLMService:
    """Service for LLM-driven Composio operations with natural language processing."""
    
    def __init__(self, entity_id: str = "default"):
        """
        Initialize the Composio LLM Service.
        
        Args:
            entity_id: Composio entity ID for API operations
        """
        self.toolset = ComposioToolSet()
        self.entity_id = entity_id
        self.action_schemas = {}  # Cache for action schemas
        
        # Initialize Gemini service
        try:
            self.gemini_service = GeminiService()
            logger.info("ComposioLLMService initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize GeminiService: {e}")
            raise
    
    async def select_tool_with_llm(self, natural_query: str) -> str:
        """
        Use LLM to select the appropriate tool from available Composio tools.
        
        Args:
            natural_query: Natural language user query
            
        Returns:
            Selected tool name (e.g., "GMAIL", "GITHUB")
        """
        logger.info(f"Tool selection for query: '{natural_query}'")
        
        try:
            # Get all available apps from Composio
            raw_apps = self.toolset.get_apps()
            logger.debug(f"Found {len(raw_apps)} available apps")
            
            # Extract tool names properly from App objects
            all_apps = []
            for app in raw_apps:
                if hasattr(app, 'name'):
                    all_apps.append(app.name.upper())
                elif hasattr(app, 'key'):
                    all_apps.append(app.key.upper())
                else:
                    # Fallback to string representation
                    app_str = str(app)
                    logger.debug(f"App string representation: {app_str}")
                    all_apps.append(app_str.upper())
            
            logger.info(f"Available tools: {len(all_apps)} tools ({all_apps[:5]}...)")
            
            # Use Gemini service for tool selection
            result = await self.gemini_service.select_composio_tool(natural_query, all_apps)
            
            selected_tool = result.get('selected_tool', 'GMAIL')
            confidence = result.get('confidence', 0.0)
            reasoning = result.get('reasoning', 'No reasoning provided')
            
            logger.info(f"LLM selected tool: {selected_tool} (confidence: {confidence:.2f})")
            logger.debug(f"Selection reasoning: {reasoning}")
            
            return selected_tool
                
        except Exception as e:
            logger.error(f"Error in tool selection: {str(e)}")
            logger.info("Defaulting to GMAIL")
            return "GMAIL"
    
    async def select_action_with_llm(self, natural_query: str, tool_name: str) -> Optional[Any]:
        """
        Use LLM to select the most appropriate action from the selected tool.
        
        Args:
            natural_query: Natural language user query
            tool_name: Selected tool name (e.g., "GMAIL", "GITHUB")
            
        Returns:
            Selected Composio action object, or None if not found
        """
        logger.info(f"Action selection for tool: {tool_name}")
        
        try:
            # Get all actions for the selected tool
            logger.debug(f"Looking up actions for tool: '{tool_name}'")
            
            available_actions = None
            if tool_name.upper() == "GMAIL":
                available_actions = list(App.GMAIL.get_actions())
            elif tool_name.upper() == "GITHUB":
                available_actions = list(App.GITHUB.get_actions())
            else:
                logger.warning(f"Tool {tool_name} not implemented in ComposioLLMService")
                return None
            
            if not available_actions:
                logger.error(f"No actions found for tool: {tool_name}")
                return None
            
            # Prepare actions info for Gemini service
            actions_info = []
            for action in available_actions[:20]:  # Limit to avoid token limits
                try:
                    schema = self.toolset.get_action_schemas([action], check_connected_accounts=False)
                    desc = "No description"
                    if schema:
                        desc = getattr(schema[0], 'description', 'No description')
                    actions_info.append({
                        'name': str(action),
                        'description': desc
                    })
                except:
                    actions_info.append({
                        'name': str(action),
                        'description': 'Action available'
                    })
            
            logger.info(f"Analyzing {len(available_actions)} {tool_name} actions...")
            
            # Use Gemini service for action selection
            result = await self.gemini_service.select_composio_action(natural_query, tool_name, actions_info)
            
            selected_action_name = result.get('selected_action')
            confidence = result.get('confidence', 0.0)
            reasoning = result.get('reasoning', 'No reasoning provided')
            
            # Find the matching action object
            for action in available_actions:
                if str(action) == selected_action_name:
                    logger.info(f"LLM selected action: {selected_action_name} (confidence: {confidence:.2f})")
                    logger.debug(f"Selection reasoning: {reasoning}")
                    return action
            
            logger.warning(f"LLM selected invalid action: {selected_action_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error in action selection: {str(e)}")
            return None
    
    async def normalize_parameters_with_llm(self, natural_query: str, action: Any, action_schema: Any) -> Dict[str, Any]:
        """
        Use LLM to normalize natural language query into action parameters.
        
        Args:
            natural_query: Natural language user query
            action: Selected Composio action object
            action_schema: Action schema from Composio
            
        Returns:
            Dictionary of normalized parameters
        """
        logger.info(f"Parameter normalization for action: {action}")
        
        try:
            # Extract schema information
            parameters_model = getattr(action_schema, 'parameters', None)
            if not parameters_model or not hasattr(parameters_model, 'properties'):
                logger.warning("No parameters found in schema")
                return {}
            
            params = parameters_model.properties
            param_info = {}
            
            for param_name, param_details in params.items():

                param_type = param_details.get('type', 'unknown')
                param_desc = param_details.get('description', 'No description')
                param_info[param_name] = {"type": param_type, "description": param_desc}
            
            logger.debug(f"Schema parameters: {list(param_info.keys())}")
            
            # Use Gemini service for parameter normalization
            result = await self.gemini_service.normalize_action_parameters(
                natural_query, str(action), param_info
            )
            
            normalized_params = result.get('parameters', {})
            confidence = result.get('confidence', 0.0)
            assumptions = result.get('assumptions', [])
            warnings = result.get('warnings', [])
            
            logger.info(f"LLM normalized {len(normalized_params)} parameters (confidence: {confidence:.2f})")
            logger.debug(f"Parameters: {list(normalized_params.keys())}")
            
            if assumptions:
                logger.debug(f"Assumptions made: {len(assumptions)}")
            if warnings:
                logger.warning(f"Parameter warnings: {len(warnings)}")
            
            return normalized_params
                
        except Exception as e:
            logger.error(f"Error in parameter normalization: {str(e)}")
            return {}
    
    async def execute_natural_language_query(self, natural_query: str, 
                                           fallback_handlers: Optional[Dict[str, callable]] = None) -> Dict[str, Any]:
        """
        Execute a natural language query using LLM-driven tool and action selection.
        
        Args:
            natural_query: Natural language user query
            fallback_handlers: Dictionary mapping action names to fallback functions
                             (e.g., {"GMAIL_FETCH_EMAILS": fetch_emails_func})
            
        Returns:
            Dictionary with execution results and metadata
        """
        logger.info(f"Executing natural language query: '{natural_query}'")
        
        execution_result = {
            'query': natural_query,
            'success': False,
            'tool_selected': None,
            'action_selected': None,
            'parameters': {},
            'result': None,
            'error': None,
            'execution_time': None,
            'timestamp': datetime.now().isoformat()
        }
        
        start_time = datetime.now()
        
        try:
            # Step 1: Select appropriate tool
            selected_tool = await self.select_tool_with_llm(natural_query)
            execution_result['tool_selected'] = selected_tool
            
            # Step 2: Select appropriate action
            selected_action = await self.select_action_with_llm(natural_query, selected_tool)
            if not selected_action:
                execution_result['error'] = "Could not select appropriate action"
                return execution_result
            
            execution_result['action_selected'] = str(selected_action)
            
            # Step 3: Get action schema (with fallback handling)
            logger.debug(f"Getting schema for {selected_action}...")
            try:
                schema = self.toolset.get_action_schemas([selected_action], check_connected_accounts=False)
                if not schema:
                    raise Exception("Could not retrieve action schema")
                action_schema = schema[0]
                
                # Step 4: Normalize parameters using LLM
                normalized_params = await self.normalize_parameters_with_llm(natural_query, selected_action, action_schema)
                execution_result['parameters'] = normalized_params
                
                # Step 5: Execute the action
                logger.info(f"Executing {selected_action} with {len(normalized_params)} parameters")
                
                result = self.toolset.execute_action(
                    action=selected_action,
                    params=normalized_params,
                    entity_id=self.entity_id
                )
                
                execution_result['result'] = result
                execution_result['success'] = True
                logger.info("Action executed successfully via LLM pipeline")
                
            except Exception as schema_error:
                logger.warning(f"Schema retrieval failed (Composio API issue): {schema_error}")
                
                # Try to extract parameters using basic LLM approach even without schema
                basic_params = await self._extract_basic_parameters(natural_query, str(selected_action))
                execution_result['parameters'] = basic_params
                
                # Try fallback if provided
                if fallback_handlers:
                    action_str = str(selected_action)
                    logger.debug(f"Checking fallback handlers for action: '{action_str}'")
                    
                    for action_pattern, handler in fallback_handlers.items():
                        if action_pattern in action_str:
                            logger.info(f"Using fallback handler for {action_pattern}")
                            try:
                                # Pass parameters to fallback handler if it accepts them
                                import inspect
                                sig = inspect.signature(handler)
                                if len(sig.parameters) > 0:
                                    # Handler accepts parameters
                                    fallback_result = await handler(basic_params) if asyncio.iscoroutinefunction(handler) else handler(basic_params)
                                else:
                                    # Handler doesn't accept parameters (legacy)
                                    fallback_result = await handler() if asyncio.iscoroutinefunction(handler) else handler()
                                
                                execution_result['result'] = fallback_result
                                execution_result['success'] = True
                                execution_result['fallback_used'] = action_pattern
                                logger.info("Fallback handler executed successfully")
                                break
                            except Exception as fallback_error:
                                logger.error(f"Fallback handler failed: {fallback_error}")
                                execution_result['error'] = f"Fallback failed: {str(fallback_error)}"
                                break
                    else:
                        execution_result['error'] = f"No fallback available for action: {selected_action}"
                else:
                    execution_result['error'] = f"Schema retrieval failed: {str(schema_error)}"
            
        except Exception as e:
            logger.error(f"Error executing natural language query: {str(e)}")
            execution_result['error'] = str(e)
        
        finally:
            end_time = datetime.now()
            execution_result['execution_time'] = (end_time - start_time).total_seconds()
        
        return execution_result
    
    def get_action_schema_params(self, action: Any, use_defaults: bool = True) -> Dict[str, Any]:
        """
        Get schema parameters for a given action with optional default values.
        
        Args:
            action: The Composio action (e.g., Action.GMAIL_FETCH_EMAILS)
            use_defaults: Whether to include default values from schema
            
        Returns:
            Dictionary of parameters with values
        """
        try:
            # Get schema for the action
            schema = self.toolset.get_action_schemas(
                actions=[action],
                check_connected_accounts=False
            )
            
            if not schema:
                return {}
            
            action_schema = schema[0]
            self.action_schemas[str(action)] = action_schema  # Cache it
            
            # Extract parameters
            parameters_model = getattr(action_schema, 'parameters', None)
            if not parameters_model or not hasattr(parameters_model, 'properties'):
                return {}
            
            params = parameters_model.properties
            result_params = {}
            
            for param_name, param_info in params.items():
                # Get parameter details
                param_type = getattr(param_info, 'type', param_info.get('type', 'string') if hasattr(param_info, 'get') else 'string')
                param_default = getattr(param_info, 'default', param_info.get('default') if hasattr(param_info, 'get') else None)
                
                # Include parameter if it has a default value or if we want all params
                if use_defaults and param_default is not None:
                    result_params[param_name] = param_default
                elif not use_defaults:
                    # For non-default mode, we'll set reasonable values based on type
                    if param_type == 'boolean':
                        result_params[param_name] = False
                    elif param_type == 'integer':
                        result_params[param_name] = 1
                    elif param_type == 'array':
                        result_params[param_name] = []
                    else:  # string or other
                        result_params[param_name] = ""
            
            return result_params
            
        except Exception as e:
            logger.error(f"Error getting schema params for {action}: {str(e)}")
            return {}
    
    async def check_connection(self, app_name: str) -> Dict[str, Any]:
        """
        Check if a specific app is properly connected.
        
        Args:
            app_name: Name of the app to check (e.g., "gmail", "github")
            
        Returns:
            Dictionary with connection status and details
        """
        logger.info(f"Checking {app_name} connection")
        
        connection_info = {
            'app_name': app_name,
            'connected': False,
            'connection_id': None,
            'status': None,
            'error': None
        }
        
        try:
            from composio import Composio
            client = Composio()
            entity = client.get_entity(self.entity_id)
            connections = entity.get_connections()
            
            for conn in connections:
                # Check multiple attributes for app name
                conn_app_name = None
                if hasattr(conn, 'appName'):
                    conn_app_name = str(conn.appName).lower()
                elif hasattr(conn, 'app'):
                    conn_app_name = str(conn.app).lower()
                
                if conn_app_name and app_name.lower() in conn_app_name:
                    connection_info['connected'] = True
                    connection_info['connection_id'] = getattr(conn, 'id', 'unknown')
                    connection_info['status'] = getattr(conn, 'status', 'unknown')
                    logger.info(f"{app_name} connection found: {connection_info['connection_id']}")
                    break
            
            if not connection_info['connected']:
                logger.warning(f"No {app_name} connection found")
                connection_info['error'] = f"No {app_name} connection found"
            
        except Exception as e:
            logger.error(f"Error checking {app_name} connection: {str(e)}")
            connection_info['error'] = str(e)
        
        return connection_info
    
    async def _extract_basic_parameters(self, natural_query: str, action_name: str) -> Dict[str, Any]:
        """
        Extract parameters from natural language query using dynamic LLM intelligence.
        No hardcoding - analyzes action name to understand what parameters might be needed.
        
        Args:
            natural_query: Natural language user query
            action_name: Action name for context
            
        Returns:
            Dictionary of extracted parameters
        """
        try:
            logger.info(f"Dynamically extracting parameters for {action_name} from: '{natural_query}'")
            
            # Use LLM to dynamically understand what parameters this action might need
            dynamic_schema = await self._generate_dynamic_schema(action_name, natural_query)
            
            # Use Gemini service for parameter extraction with the dynamic schema
            result = await self.gemini_service.normalize_action_parameters(
                natural_query, action_name, dynamic_schema
            )
            
            extracted_params = result.get('parameters', {})
            logger.info(f"Extracted {len(extracted_params)} dynamic parameters: {list(extracted_params.keys())}")
            
            return extracted_params
            
        except Exception as e:
            logger.error(f"Error extracting basic parameters: {str(e)}")
            return {}
    
    async def _generate_dynamic_schema(self, action_name: str, natural_query: str) -> Dict[str, Any]:
        """
        Dynamically generate parameter schema by analyzing action name and query context.
        
        Args:
            action_name: The action name to analyze
            natural_query: User's natural language query for context
            
        Returns:
            Dictionary representing likely parameter schema
        """
        try:
            schema_prompt = f"""
You are an expert at understanding API actions and their likely parameters.

Action: {action_name}
User Query: "{natural_query}"

Based on the action name and user query, predict what parameters this action likely needs.

Action Name Analysis:
- Break down the action name to understand its purpose
- Consider common patterns in API naming (CREATE, UPDATE, DELETE, FETCH, SEND, etc.)
- Consider the app/service (GMAIL, GITHUB, GOOGLEDOCS, SLACK, etc.)

Common Parameter Patterns:
- CREATE actions often need: title, content/body/text, target location
- SEND actions often need: recipient, subject, message/content
- FETCH actions often need: limit/count, query/filter, user_id
- UPDATE actions often need: id, title, content, target fields
- DELETE actions often need: id, confirmation fields

Respond with a JSON schema object representing the likely parameters:
{{
    "parameter_name": {{
        "type": "string|integer|boolean|array",
        "description": "Clear description of what this parameter does",
        "required": true|false
    }}
}}

Example for GMAIL_SEND_EMAIL:
{{
    "recipient_email": {{"type": "string", "description": "Email address of recipient", "required": true}},
    "subject": {{"type": "string", "description": "Email subject line", "required": true}},
    "body": {{"type": "string", "description": "Email body content", "required": true}}
}}

Respond only with valid JSON.
"""
            
            response = await self.gemini_service._generate_response(schema_prompt)
            
            try:
                dynamic_schema = json.loads(response)
                logger.info(f"Generated dynamic schema with {len(dynamic_schema)} parameters for {action_name}")
                return dynamic_schema
                
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse dynamic schema JSON: {e}")
                # Fallback to empty schema
                return {}
                
        except Exception as e:
            logger.error(f"Error generating dynamic schema: {str(e)}")
            return {}

    async def discover_app_actions(self, app_name: str) -> Dict[str, Any]:
        """
        Discover available actions for a specific app.
        
        Args:
            app_name: Name of the app (e.g., "GMAIL", "GITHUB")
            
        Returns:
            Dictionary with available actions and their schemas
        """
        logger.info(f"Discovering actions for {app_name}")
        
        discovery_result = {
            'app_name': app_name,
            'actions_found': 0,
            'actions': [],
            'schemas': {},
            'error': None
        }
        
        try:
            available_actions = []
            
            if app_name.upper() == "GMAIL":
                available_actions = list(App.GMAIL.get_actions())
            elif app_name.upper() == "GITHUB":
                available_actions = list(App.GITHUB.get_actions())
            else:
                discovery_result['error'] = f"App {app_name} not supported for discovery"
                return discovery_result
            
            discovery_result['actions_found'] = len(available_actions)
            
            # Get action details
            for action in available_actions[:10]:  # Limit for performance
                action_name = str(action)
                discovery_result['actions'].append(action_name)
                
                try:
                    schema = self.toolset.get_action_schemas([action], check_connected_accounts=False)
                    if schema:
                        discovery_result['schemas'][action_name] = {
                            'description': getattr(schema[0], 'description', 'No description'),
                            'parameters_count': len(getattr(schema[0].parameters, 'properties', {})) if hasattr(schema[0], 'parameters') else 0
                        }
                except:
                    discovery_result['schemas'][action_name] = {
                        'description': 'Schema unavailable',
                        'parameters_count': 0
                    }
            
            logger.info(f"Discovered {len(available_actions)} actions for {app_name}")
            
        except Exception as e:
            logger.error(f"Error discovering actions for {app_name}: {str(e)}")
            discovery_result['error'] = str(e)
        
        return discovery_result