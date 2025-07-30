import os
import json
import asyncio
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
import logging
import uuid
from .composio_service import ComposioService
from .composio_auth_manager import ComposioAuthManager
from .composio_tool_discovery import ComposioToolDiscovery

logger = logging.getLogger(__name__)


class ComposioFunctionExecutor:
    """
    Composio-based function execution engine that replaces traditional API calls
    with unified tool execution through Composio SDK.
    """
    
    def __init__(
        self, 
        composio_service: ComposioService,
        auth_manager: ComposioAuthManager,
        tool_discovery: ComposioToolDiscovery
    ):
        self.composio_service = composio_service
        self.auth_manager = auth_manager
        self.tool_discovery = tool_discovery
        
        # Execution tracking
        self._active_executions: Dict[str, Dict[str, Any]] = {}
        self._execution_history: List[Dict[str, Any]] = []
        
        logger.info("ComposioFunctionExecutor initialized")
    
    async def execute_function(
        self, 
        user_id: str,
        app_name: str,
        function_name: str,
        parameters: Dict[str, Any],
        execution_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a function using Composio tools.
        
        Args:
            user_id: User identifier for authentication
            app_name: App name (gmail, twitter, etc.)
            function_name: Function/tool name to execute
            parameters: Function parameters
            execution_context: Additional execution context
            
        Returns:
            Execution result
        """
        try:
            logger.info(f"Executing {app_name}.{function_name} for user {user_id}")
            
            # Map function name to Composio tool slug
            tool_slug = f"{app_name.upper()}_{function_name.upper()}"
            
            # Try common tool naming patterns
            tool_variations = [
                tool_slug,
                f"{app_name.upper()}_LIST_EMAILS" if function_name == "list_emails" else None,
                f"{app_name.upper()}_SEND_EMAIL" if function_name == "send_email" else None,
                f"{app_name.upper()}_LIST_REPOSITORIES" if function_name == "list_repositories" else None,
                f"{app_name.upper()}_CREATE_ISSUE" if function_name == "create_issue" else None,
            ]
            
            # Remove None values
            tool_variations = [t for t in tool_variations if t is not None]
            
            # Try to execute with different tool variations
            last_error = None
            for tool_variation in tool_variations:
                try:
                    result = await self.composio_service.execute_tool(
                        tool_slug=tool_variation,
                        parameters=parameters,
                        user_id=user_id
                    )
                    
                    # If successful, return result
                    if result.get('success'):
                        logger.info(f"Successfully executed {tool_variation}")
                        return result
                    else:
                        last_error = result.get('error', 'Unknown error')
                        logger.warning(f"Tool {tool_variation} failed: {last_error}")
                        
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"Tool {tool_variation} error: {last_error}")
                    continue
            
            # If all variations failed, return error
            return {
                'success': False,
                'error': f"Function {function_name} not found for app {app_name}. Last error: {last_error}",
                'function_name': function_name,
                'app_name': app_name,
                'user_id': user_id
            }
            
        except Exception as e:
            logger.error(f"Error executing {app_name}.{function_name}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'function_name': function_name,
                'app_name': app_name,
                'user_id': user_id
            }

    async def execute_function_legacy(
        self, 
        function_name: str, 
        parameters: Dict[str, Any],
        user_id: str,
        execution_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a function using Composio tools.
        
        Args:
            function_name: Function/tool name to execute
            parameters: Function parameters
            user_id: User identifier for authentication
            execution_context: Additional context for execution
            
        Returns:
            Execution result with standardized format
        """
        execution_id = str(uuid.uuid4())
        
        try:
            logger.info(f"Starting function execution {execution_id}: {function_name}")
            
            # Map function name to tool slug
            tool_slug = self._map_function_to_tool_slug(function_name)
            if not tool_slug:
                raise ValueError(f"Unknown function: {function_name}")
            
            # Start execution tracking
            execution_record = {
                'execution_id': execution_id,
                'function_name': function_name,
                'tool_slug': tool_slug,
                'user_id': user_id,
                'parameters': parameters,
                'context': execution_context or {},
                'status': 'running',
                'started_at': datetime.utcnow().isoformat(),
                'steps': []
            }
            
            self._active_executions[execution_id] = execution_record
            
            # Validate tool availability
            tool_schema = await self.composio_service.get_tool_schema(tool_slug)
            
            # Validate parameters
            validation_result = await self.composio_service.validate_tool_parameters(tool_slug, parameters)
            if not validation_result['valid']:
                raise ValueError(f"Parameter validation failed: {validation_result['errors']}")
            
            # Get required app for authentication
            required_app = self._get_app_from_tool(tool_slug)
            
            # Get user's connected account for the required app
            connected_account = await self.auth_manager.get_account_for_tool_execution(user_id, required_app)
            if not connected_account:
                raise ValueError(f"No connected {required_app} account found for user {user_id}")
            
            # Execute the tool
            execution_result = await self.composio_service.execute_tool(
                tool_slug=tool_slug,
                parameters=parameters,
                user_id=user_id,
                connected_account_id=connected_account['composio_connection_id']
            )
            
            # Process and normalize result
            normalized_result = await self._normalize_execution_result(
                execution_result, 
                function_name, 
                tool_slug
            )
            
            # Update execution record
            execution_record.update({
                'status': 'completed' if normalized_result['success'] else 'failed',
                'completed_at': datetime.utcnow().isoformat(),
                'result': normalized_result,
                'duration_ms': self._calculate_duration(execution_record['started_at'])
            })
            
            # Move to history and clean up
            self._execution_history.append(execution_record)
            del self._active_executions[execution_id]
            
            logger.info(f"Function execution {execution_id} completed: {normalized_result['success']}")
            
            return {
                'execution_id': execution_id,
                'success': normalized_result['success'],
                'data': normalized_result['data'],
                'function_name': function_name,
                'tool_slug': tool_slug,
                'metadata': {
                    'user_id': user_id,
                    'duration_ms': execution_record['duration_ms'],
                    'executed_at': execution_record['completed_at']
                },
                'error': normalized_result.get('error')
            }
            
        except Exception as e:
            logger.error(f"Function execution {execution_id} failed: {str(e)}")
            
            # Update execution record with error
            if execution_id in self._active_executions:
                execution_record = self._active_executions[execution_id]
                execution_record.update({
                    'status': 'failed',
                    'completed_at': datetime.utcnow().isoformat(),
                    'error': str(e),
                    'duration_ms': self._calculate_duration(execution_record['started_at'])
                })
                
                self._execution_history.append(execution_record)
                del self._active_executions[execution_id]
            
            return {
                'execution_id': execution_id,
                'success': False,
                'data': None,
                'function_name': function_name,
                'error': str(e),
                'metadata': {
                    'user_id': user_id,
                    'executed_at': datetime.utcnow().isoformat()
                }
            }

    async def execute_task_tree(
        self, 
        task_tree: Dict[str, Any], 
        user_id: str,
        execution_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a complete task tree using Composio tools.
        
        Args:
            task_tree: Task tree structure
            user_id: User identifier
            execution_context: Additional execution context
            
        Returns:
            Complete task tree execution result
        """
        execution_id = str(uuid.uuid4())
        
        try:
            logger.info(f"Starting task tree execution {execution_id}")
            
            # Validate task tree tools
            task_tools = await self.tool_discovery.get_tools_for_task_tree(task_tree)
            if not task_tools['is_executable']:
                raise ValueError(f"Task tree not executable. Missing tools: {task_tools['missing_tools']}")
            
            # Start execution tracking
            execution_record = {
                'execution_id': execution_id,
                'type': 'task_tree',
                'user_id': user_id,
                'task_tree': task_tree,
                'context': execution_context or {},
                'status': 'running',
                'started_at': datetime.utcnow().isoformat(),
                'steps': [],
                'results': {}
            }
            
            self._active_executions[execution_id] = execution_record
            
            # Execute task tree recursively
            execution_result = await self._execute_task_node(
                task_tree, 
                user_id, 
                execution_id,
                {}  # Initial context
            )
            
            # Update execution record
            execution_record.update({
                'status': 'completed' if execution_result['success'] else 'failed',
                'completed_at': datetime.utcnow().isoformat(),
                'final_result': execution_result,
                'duration_ms': self._calculate_duration(execution_record['started_at'])
            })
            
            # Move to history
            self._execution_history.append(execution_record)
            del self._active_executions[execution_id]
            
            logger.info(f"Task tree execution {execution_id} completed: {execution_result['success']}")
            
            return {
                'execution_id': execution_id,
                'success': execution_result['success'],
                'data': execution_result['data'],
                'steps_executed': len(execution_record['steps']),
                'metadata': {
                    'user_id': user_id,
                    'duration_ms': execution_record['duration_ms'],
                    'executed_at': execution_record['completed_at']
                },
                'error': execution_result.get('error')
            }
            
        except Exception as e:
            logger.error(f"Task tree execution {execution_id} failed: {str(e)}")
            
            if execution_id in self._active_executions:
                execution_record = self._active_executions[execution_id]
                execution_record.update({
                    'status': 'failed',
                    'completed_at': datetime.utcnow().isoformat(),
                    'error': str(e),
                    'duration_ms': self._calculate_duration(execution_record['started_at'])
                })
                
                self._execution_history.append(execution_record)
                del self._active_executions[execution_id]
            
            return {
                'execution_id': execution_id,
                'success': False,
                'data': None,
                'error': str(e),
                'metadata': {
                    'user_id': user_id,
                    'executed_at': datetime.utcnow().isoformat()
                }
            }

    async def _execute_task_node(
        self, 
        node: Union[Dict, List, str], 
        user_id: str,
        execution_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Recursively execute a task tree node.
        
        Args:
            node: Task node to execute
            user_id: User identifier
            execution_id: Parent execution ID
            context: Current execution context
            
        Returns:
            Node execution result
        """
        try:
            if isinstance(node, dict):
                if 'function' in node or 'tool' in node:
                    # This is a leaf node with a function/tool to execute
                    function_name = node.get('function') or node.get('tool')
                    parameters = node.get('parameters', {})
                    
                    # Substitute context variables in parameters
                    resolved_parameters = self._resolve_context_variables(parameters, context)
                    
                    # Execute the function
                    result = await self.execute_function(
                        function_name=function_name,
                        parameters=resolved_parameters,
                        user_id=user_id,
                        execution_context={'parent_execution_id': execution_id}
                    )
                    
                    # Update context with result
                    if result['success'] and result['data']:
                        context[f"{function_name}_result"] = result['data']
                    
                    # Record step in parent execution
                    if execution_id in self._active_executions:
                        self._active_executions[execution_id]['steps'].append({
                            'step': len(self._active_executions[execution_id]['steps']) + 1,
                            'function': function_name,
                            'success': result['success'],
                            'executed_at': datetime.utcnow().isoformat()
                        })
                    
                    return result
                    
                elif 'parallel' in node:
                    # Execute tasks in parallel
                    tasks = node['parallel']
                    results = await asyncio.gather(*[
                        self._execute_task_node(task, user_id, execution_id, context.copy())
                        for task in tasks
                    ], return_exceptions=True)
                    
                    # Combine results
                    combined_result = {
                        'success': all(r['success'] for r in results if isinstance(r, dict)),
                        'data': [r['data'] for r in results if isinstance(r, dict)],
                        'parallel_results': results
                    }
                    
                    return combined_result
                    
                elif 'sequential' in node:
                    # Execute tasks sequentially
                    tasks = node['sequential']
                    results = []
                    
                    for task in tasks:
                        result = await self._execute_task_node(task, user_id, execution_id, context)
                        results.append(result)
                        
                        if not result['success']:
                            # Stop on first failure unless configured otherwise
                            break
                        
                        # Update context with each result
                        if result['data']:
                            context.update(result['data'])
                    
                    combined_result = {
                        'success': all(r['success'] for r in results),
                        'data': [r['data'] for r in results],
                        'sequential_results': results
                    }
                    
                    return combined_result
                
                else:
                    # Regular dict - process all key-value pairs
                    result_data = {}
                    success = True
                    
                    for key, value in node.items():
                        if isinstance(value, (dict, list)):
                            sub_result = await self._execute_task_node(value, user_id, execution_id, context)
                            result_data[key] = sub_result['data']
                            if not sub_result['success']:
                                success = False
                        else:
                            result_data[key] = value
                    
                    return {
                        'success': success,
                        'data': result_data
                    }
                    
            elif isinstance(node, list):
                # Execute all items in the list
                results = []
                for item in node:
                    result = await self._execute_task_node(item, user_id, execution_id, context)
                    results.append(result)
                
                return {
                    'success': all(r['success'] for r in results),
                    'data': [r['data'] for r in results],
                    'list_results': results
                }
                
            else:
                # Primitive value - return as is
                return {
                    'success': True,
                    'data': node
                }
                
        except Exception as e:
            logger.error(f"Error executing task node: {str(e)}")
            return {
                'success': False,
                'data': None,
                'error': str(e)
            }

    def _resolve_context_variables(self, parameters: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve context variables in parameters using template substitution.
        
        Args:
            parameters: Original parameters
            context: Current execution context
            
        Returns:
            Parameters with resolved variables
        """
        resolved = {}
        
        for key, value in parameters.items():
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                # Context variable substitution
                var_name = value[2:-1]  # Remove ${ and }
                resolved[key] = context.get(var_name, value)
            elif isinstance(value, dict):
                resolved[key] = self._resolve_context_variables(value, context)
            elif isinstance(value, list):
                resolved[key] = [
                    self._resolve_context_variables(item, context) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                resolved[key] = value
        
        return resolved

    def _map_function_to_tool_slug(self, function_name: str) -> Optional[str]:
        """
        Map function name to Composio tool slug.
        
        Args:
            function_name: Function name
            
        Returns:
            Corresponding tool slug
        """
        # Use tool discovery mapping
        return self.tool_discovery._map_function_to_tool(function_name)

    def _get_app_from_tool(self, tool_slug: str) -> str:
        """
        Extract app name from tool slug.
        
        Args:
            tool_slug: Tool slug
            
        Returns:
            App name
        """
        # Extract app from tool slug (e.g., GMAIL_SEND_EMAIL -> gmail)
        if '_' in tool_slug:
            return tool_slug.split('_')[0].lower()
        return tool_slug.lower()

    async def _normalize_execution_result(
        self, 
        raw_result: Dict[str, Any], 
        function_name: str,
        tool_slug: str
    ) -> Dict[str, Any]:
        """
        Normalize execution result to standard format.
        
        Args:
            raw_result: Raw result from Composio
            function_name: Original function name
            tool_slug: Tool slug used
            
        Returns:
            Normalized result
        """
        try:
            if raw_result['success']:
                # Apply function-specific normalization
                normalized_data = await self._apply_function_specific_normalization(
                    raw_result['data'], 
                    function_name
                )
                
                return {
                    'success': True,
                    'data': normalized_data,
                    'raw_data': raw_result['data'],
                    'tool_slug': tool_slug
                }
            else:
                return {
                    'success': False,
                    'data': None,
                    'error': raw_result.get('error', 'Unknown error'),
                    'tool_slug': tool_slug
                }
                
        except Exception as e:
            logger.error(f"Error normalizing result: {str(e)}")
            return {
                'success': False,
                'data': None,
                'error': f"Normalization error: {str(e)}",
                'tool_slug': tool_slug
            }

    async def _apply_function_specific_normalization(
        self, 
        data: Any, 
        function_name: str
    ) -> Any:
        """
        Apply function-specific data normalization.
        
        Args:
            data: Raw data
            function_name: Function name
            
        Returns:
            Normalized data
        """
        # Function-specific normalization rules
        normalizers = {
            'fetch_emails': self._normalize_email_data,
            'search_flights': self._normalize_flight_data,
            'search_restaurants': self._normalize_restaurant_data,
            'create_meeting': self._normalize_meeting_data
        }
        
        normalizer = normalizers.get(function_name)
        if normalizer:
            return await normalizer(data)
        
        return data

    async def _normalize_email_data(self, data: Any) -> Dict[str, Any]:
        """Normalize email data."""
        if isinstance(data, list):
            return {
                'emails': data,
                'count': len(data)
            }
        return data

    async def _normalize_flight_data(self, data: Any) -> Dict[str, Any]:
        """Normalize flight search data."""
        if isinstance(data, list):
            return {
                'flights': data,
                'count': len(data),
                'cheapest': min(data, key=lambda x: x.get('price', float('inf'))) if data else None
            }
        return data

    async def _normalize_restaurant_data(self, data: Any) -> Dict[str, Any]:
        """Normalize restaurant search data."""
        if isinstance(data, list):
            return {
                'restaurants': data,
                'count': len(data)
            }
        return data

    async def _normalize_meeting_data(self, data: Any) -> Dict[str, Any]:
        """Normalize meeting creation data."""
        if isinstance(data, dict):
            return {
                'meeting_id': data.get('id'),
                'join_url': data.get('join_url'),
                'meeting_details': data
            }
        return data

    def _calculate_duration(self, started_at: str) -> int:
        """
        Calculate execution duration in milliseconds.
        
        Args:
            started_at: Start time ISO string
            
        Returns:
            Duration in milliseconds
        """
        try:
            start_time = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds() * 1000
            return int(duration)
        except:
            return 0

    async def get_execution_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status of an execution.
        
        Args:
            execution_id: Execution ID
            
        Returns:
            Execution status or None if not found
        """
        # Check active executions
        if execution_id in self._active_executions:
            return self._active_executions[execution_id]
        
        # Check execution history
        for record in self._execution_history:
            if record['execution_id'] == execution_id:
                return record
        
        return None

    async def get_user_execution_history(
        self, 
        user_id: str, 
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get execution history for a user.
        
        Args:
            user_id: User identifier
            limit: Maximum number of records
            
        Returns:
            User's execution history
        """
        user_history = [
            record for record in self._execution_history 
            if record['user_id'] == user_id
        ]
        
        # Sort by most recent first
        user_history.sort(key=lambda x: x['started_at'], reverse=True)
        
        return user_history[:limit]

    async def cancel_execution(self, execution_id: str, user_id: str) -> Dict[str, Any]:
        """
        Cancel an active execution.
        
        Args:
            execution_id: Execution ID to cancel
            user_id: User identifier for authorization
            
        Returns:
            Cancellation result
        """
        if execution_id not in self._active_executions:
            return {
                'success': False,
                'error': 'Execution not found or already completed'
            }
        
        execution_record = self._active_executions[execution_id]
        
        if execution_record['user_id'] != user_id:
            return {
                'success': False,
                'error': 'Not authorized to cancel this execution'
            }
        
        # Mark as cancelled
        execution_record.update({
            'status': 'cancelled',
            'completed_at': datetime.utcnow().isoformat(),
            'cancelled_by': user_id,
            'duration_ms': self._calculate_duration(execution_record['started_at'])
        })
        
        # Move to history
        self._execution_history.append(execution_record)
        del self._active_executions[execution_id]
        
        logger.info(f"Execution {execution_id} cancelled by user {user_id}")
        
        return {
            'success': True,
            'execution_id': execution_id,
            'cancelled_at': execution_record['completed_at']
        }