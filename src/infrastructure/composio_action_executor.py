import asyncio
import re
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
import logging
import uuid
from dataclasses import dataclass
from enum import Enum

from .composio_service import ComposioService
from .composio_auth_manager import ComposioAuthManager
from .composio_tool_discovery import ComposioToolDiscovery
from .composio_parameter_generator import ComposioParameterGenerator

logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    """Status of action execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class ExecutionPriority(Enum):
    """Priority levels for action execution."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class ActionRequest:
    """Represents a single action execution request."""
    id: str
    user_id: str
    app_name: str
    action_name: str
    natural_language_input: str
    parameters: Optional[Dict[str, Any]] = None
    priority: ExecutionPriority = ExecutionPriority.NORMAL
    retry_count: int = 0
    max_retries: int = 3
    timeout_seconds: int = 300
    dependencies: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    scheduled_at: Optional[datetime] = None


@dataclass
class ActionResult:
    """Represents the result of an action execution."""
    request_id: str
    status: ExecutionStatus
    data: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None
    retry_count: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class ComposioActionExecutor:
    """
    Advanced action executor that dynamically generates parameters and executes
    multi-app workflows with intelligent orchestration.
    """
    
    def __init__(
        self,
        composio_service: ComposioService,
        auth_manager: ComposioAuthManager,
        tool_discovery: ComposioToolDiscovery,
        parameter_generator: ComposioParameterGenerator
    ):
        self.composio_service = composio_service
        self.auth_manager = auth_manager
        self.tool_discovery = tool_discovery
        self.parameter_generator = parameter_generator
        
        # Execution management
        self._pending_requests: Dict[str, ActionRequest] = {}
        self._running_executions: Dict[str, ActionResult] = {}
        self._completed_executions: Dict[str, ActionResult] = {}
        
        # Execution queue by priority
        self._execution_queues: Dict[ExecutionPriority, List[str]] = {
            ExecutionPriority.URGENT: [],
            ExecutionPriority.HIGH: [],
            ExecutionPriority.NORMAL: [],
            ExecutionPriority.LOW: []
        }
        
        # Background task for processing queue
        self._queue_processor_task: Optional[asyncio.Task] = None
        self._processing_active = False
        
        # Performance and analytics
        self._execution_stats = {
            'total_executions': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'average_execution_time': 0,
            'app_performance': {}
        }
        
        logger.info("ComposioActionExecutor initialized")

    async def start_processing(self):
        """Start the background queue processor."""
        if not self._processing_active:
            self._processing_active = True
            self._queue_processor_task = asyncio.create_task(self._process_queue())
            logger.info("Action executor queue processing started")

    async def stop_processing(self):
        """Stop the background queue processor."""
        if self._processing_active:
            self._processing_active = False
            if self._queue_processor_task:
                self._queue_processor_task.cancel()
                try:
                    await self._queue_processor_task
                except asyncio.CancelledError:
                    pass
            logger.info("Action executor queue processing stopped")

    async def execute_action(
        self,
        user_id: str,
        app_name: str,
        action_name: str,
        natural_language_input: str,
        priority: ExecutionPriority = ExecutionPriority.NORMAL,
        parameters: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        execute_immediately: bool = True
    ) -> Union[ActionResult, str]:
        """
        Execute a single action with dynamic parameter generation.
        
        Args:
            user_id: User identifier
            app_name: Target application
            action_name: Action to perform
            natural_language_input: User's natural language description
            priority: Execution priority
            parameters: Optional pre-defined parameters
            metadata: Optional metadata
            execute_immediately: Whether to execute immediately or queue
            
        Returns:
            ActionResult if executed immediately, request_id if queued
        """
        try:
            # Create action request
            request = ActionRequest(
                id=str(uuid.uuid4()),
                user_id=user_id,
                app_name=app_name,
                action_name=action_name,
                natural_language_input=natural_language_input,
                parameters=parameters,
                priority=priority,
                metadata=metadata or {},
                created_at=datetime.utcnow()
            )
            
            logger.info(f"Creating action request {request.id} for {app_name}.{action_name}")
            
            if execute_immediately:
                return await self._execute_single_action(request)
            else:
                # Add to queue
                self._pending_requests[request.id] = request
                self._execution_queues[priority].append(request.id)
                logger.info(f"Action request {request.id} queued with priority {priority.value}")
                return request.id
                
        except Exception as e:
            logger.error(f"Error creating action request: {str(e)}")
            raise

    async def execute_workflow(
        self,
        user_id: str,
        workflow_description: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a complex workflow involving multiple actions across different apps.
        
        Args:
            user_id: User identifier
            workflow_description: Natural language description of the workflow
            context: Optional context for execution
            
        Returns:
            Workflow execution result
        """
        try:
            logger.info(f"Starting workflow execution for user {user_id}")
            workflow_id = str(uuid.uuid4())
            
            # Parse workflow into individual actions
            actions = await self._parse_workflow_actions(workflow_description, context)
            
            # Plan execution sequence
            execution_plan = await self._plan_workflow_execution(actions, user_id)
            
            # Execute actions according to plan
            workflow_result = await self._execute_workflow_plan(
                workflow_id, execution_plan, user_id, context
            )
            
            logger.info(f"Workflow {workflow_id} completed with status: {workflow_result['status']}")
            return workflow_result
            
        except Exception as e:
            logger.error(f"Error executing workflow: {str(e)}")
            return {
                'workflow_id': workflow_id if 'workflow_id' in locals() else 'unknown',
                'status': ExecutionStatus.FAILED.value,
                'error': str(e),
                'completed_at': datetime.utcnow().isoformat()
            }

    async def get_execution_status(self, request_id: str) -> Optional[ActionResult]:
        """Get the status of an action execution."""
        
        # Check running executions
        if request_id in self._running_executions:
            return self._running_executions[request_id]
        
        # Check completed executions
        if request_id in self._completed_executions:
            return self._completed_executions[request_id]
        
        # Check pending requests
        if request_id in self._pending_requests:
            return ActionResult(
                request_id=request_id,
                status=ExecutionStatus.PENDING,
                metadata={'queued_at': self._pending_requests[request_id].created_at.isoformat()}
            )
        
        return None

    async def cancel_execution(self, request_id: str, user_id: str) -> bool:
        """Cancel a pending or running execution."""
        
        try:
            # Check if user owns this request
            request = self._pending_requests.get(request_id)
            if request and request.user_id != user_id:
                raise PermissionError(f"User {user_id} cannot cancel request {request_id}")
            
            # Remove from pending queue
            if request_id in self._pending_requests:
                request = self._pending_requests.pop(request_id)
                
                # Remove from priority queue
                if request_id in self._execution_queues[request.priority]:
                    self._execution_queues[request.priority].remove(request_id)
                
                # Add to completed with cancelled status
                self._completed_executions[request_id] = ActionResult(
                    request_id=request_id,
                    status=ExecutionStatus.CANCELLED,
                    completed_at=datetime.utcnow(),
                    metadata={'cancelled_by': user_id}
                )
                
                logger.info(f"Request {request_id} cancelled by user {user_id}")
                return True
            
            # For running executions, we can't easily cancel them
            # but we mark them for cancellation
            if request_id in self._running_executions:
                result = self._running_executions[request_id]
                if result.metadata is None:
                    result.metadata = {}
                result.metadata['cancellation_requested'] = True
                result.metadata['cancelled_by'] = user_id
                logger.info(f"Cancellation requested for running execution {request_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error cancelling execution {request_id}: {str(e)}")
            return False

    async def get_user_execution_history(
        self,
        user_id: str,
        limit: int = 50,
        app_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get execution history for a user."""
        
        history = []
        
        # Combine completed and running executions
        all_executions = {**self._completed_executions, **self._running_executions}
        
        for request_id, result in all_executions.items():
            # Get original request details
            request = self._pending_requests.get(request_id)
            if not request:
                # Try to find in completed metadata
                continue
            
            if request.user_id != user_id:
                continue
            
            if app_filter and request.app_name != app_filter:
                continue
            
            history_item = {
                'request_id': request_id,
                'app_name': request.app_name,
                'action_name': request.action_name,
                'natural_input': request.natural_language_input[:100] + '...' if len(request.natural_language_input) > 100 else request.natural_language_input,
                'status': result.status.value,
                'created_at': request.created_at.isoformat() if request.created_at else None,
                'completed_at': result.completed_at.isoformat() if result.completed_at else None,
                'execution_time_ms': result.execution_time_ms,
                'success': result.status == ExecutionStatus.COMPLETED
            }
            
            history.append(history_item)
        
        # Sort by creation time, most recent first
        history.sort(key=lambda x: x['created_at'] or '', reverse=True)
        
        return history[:limit]

    async def _execute_single_action(self, request: ActionRequest) -> ActionResult:
        """Execute a single action request."""
        
        start_time = datetime.utcnow()
        result = ActionResult(
            request_id=request.id,
            status=ExecutionStatus.RUNNING,
            started_at=start_time
        )
        
        self._running_executions[request.id] = result
        
        try:
            logger.info(f"Executing action {request.app_name}.{request.action_name} for user {request.user_id}")
            
            # Step 1: Check user authentication for the app
            auth_status = await self._check_app_authentication(request.user_id, request.app_name)
            if not auth_status['authenticated']:
                raise Exception(f"User {request.user_id} not authenticated for {request.app_name}")
            
            # Step 2: Generate parameters if not provided
            if not request.parameters:
                logger.info("Generating parameters from natural language input")
                request.parameters = await self.parameter_generator.generate_parameters_from_text(
                    user_input=request.natural_language_input,
                    app_name=request.app_name,
                    action_name=request.action_name,
                    context=request.metadata
                )
                
                if not request.parameters:
                    raise Exception("Failed to generate parameters from natural language input")
                
                logger.info(f"Generated parameters: {list(request.parameters.keys())}")
            
            # Step 3: Validate and complete parameters
            validated_params = await self.parameter_generator.validate_and_complete_parameters(
                parameters=request.parameters,
                app_name=request.app_name,
                action_name=request.action_name,
                auto_complete=True
            )
            
            # Step 4: Execute the action using Composio service
            tool_slug = f"{request.app_name.upper()}_{request.action_name.upper()}"
            execution_result = await self.composio_service.execute_tool(
                tool_slug=tool_slug,
                parameters=validated_params,
                user_id=request.user_id
            )
            
            # Step 5: Process and normalize result
            if execution_result['success']:
                result.status = ExecutionStatus.COMPLETED
                result.data = execution_result['data']
                logger.info(f"Action {request.app_name}.{request.action_name} completed successfully")
            else:
                result.status = ExecutionStatus.FAILED
                result.error = execution_result.get('error', 'Unknown error')
                logger.error(f"Action {request.app_name}.{request.action_name} failed: {result.error}")
            
            # Update statistics
            await self._update_execution_stats(request, result)
            
        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.error = str(e)
            logger.error(f"Action execution failed: {str(e)}")
            
            # Consider retry if it's a transient error
            if request.retry_count < request.max_retries and self._is_retryable_error(str(e)):
                request.retry_count += 1
                result.status = ExecutionStatus.RETRYING
                result.retry_count = request.retry_count
                logger.info(f"Scheduling retry {request.retry_count}/{request.max_retries} for request {request.id}")
                
                # Schedule retry with exponential backoff
                retry_delay = min(300, 2 ** request.retry_count)  # Max 5 minutes
                await asyncio.sleep(retry_delay)
                
                return await self._execute_single_action(request)
        
        finally:
            # Calculate execution time
            end_time = datetime.utcnow()
            result.execution_time_ms = int((end_time - start_time).total_seconds() * 1000)
            result.completed_at = end_time
            
            # Move from running to completed
            if request.id in self._running_executions:
                del self._running_executions[request.id]
            self._completed_executions[request.id] = result
        
        return result

    async def _parse_workflow_actions(
        self,
        workflow_description: str,
        context: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Parse a workflow description into individual actions using enhanced NLP."""
        
        actions = []
        description_lower = workflow_description.lower()
        
        # Use available tools to determine possible actions
        try:
            available_tools = await self.tool_discovery.discover_tools()
            tool_map = {tool['app']: tool for tool in available_tools}
            
            logger.info(f"Available tools from {len(tool_map)} apps for workflow parsing")
        except Exception as e:
            logger.warning(f"Could not get available tools: {str(e)}")
            tool_map = {}
        
        # Enhanced pattern matching for complex workflows
        workflow_patterns = [
            # Email-to-social workflows
            {
                'pattern': r'(?:read|fetch|get).+(?:email|inbox).+(?:post|tweet|share|publish)',
                'actions': [
                    {'app': 'gmail', 'action': 'fetch_emails', 'desc': 'fetch recent emails'},
                    {'app': 'twitter', 'action': 'create_post', 'desc': 'post content from email'}
                ]
            },
            # Calendar-meeting workflows
            {
                'pattern': r'(?:schedule|create|setup).+(?:meeting|call|event)',
                'actions': [
                    {'app': 'google_calendar', 'action': 'create_event', 'desc': 'create meeting event'}
                ]
            },
            # Document creation workflows
            {
                'pattern': r'(?:create|write|generate).+(?:document|doc|note)',
                'actions': [
                    {'app': 'notion', 'action': 'create_page', 'desc': 'create new document'}
                ]
            },
            # Repository management
            {
                'pattern': r'(?:create|setup).+(?:repository|repo|project)',
                'actions': [
                    {'app': 'github', 'action': 'create_repository', 'desc': 'create new repository'}
                ]
            },
            # Issue tracking
            {
                'pattern': r'(?:create|report|add).+(?:issue|bug|ticket)',
                'actions': [
                    {'app': 'github', 'action': 'create_issue', 'desc': 'create new issue'}
                ]
            },
            # Communication workflows
            {
                'pattern': r'(?:send|share|notify).+(?:message|update|notification)',
                'actions': [
                    {'app': 'slack', 'action': 'send_message', 'desc': 'send team notification'}
                ]
            }
        ]
        
        # Try to match workflow patterns
        matched_pattern = None
        for pattern_info in workflow_patterns:
            if re.search(pattern_info['pattern'], description_lower):
                matched_pattern = pattern_info
                logger.info(f"Matched workflow pattern: {pattern_info['pattern']}")
                break
        
        if matched_pattern:
            # Use matched pattern actions
            for i, action_info in enumerate(matched_pattern['actions']):
                action = {
                    'app_name': action_info['app'],
                    'action_name': action_info['action'],
                    'description': action_info['desc'],
                    'depends_on': [],
                    'context_mapping': {}
                }
                
                # Add dependencies for sequential actions
                if i > 0:
                    prev_action = matched_pattern['actions'][i-1]
                    action['depends_on'] = [f"{prev_action['app']}.{prev_action['action']}"]
                    
                    # Add context mapping for data flow
                    if action_info['app'] == 'twitter' and prev_action['app'] == 'gmail':
                        action['context_mapping'] = {
                            'text': '${gmail.fetch_emails_result.latest_email.subject}'
                        }
                
                actions.append(action)
        else:
            # Fallback to single action detection
            app_keywords = {
                'gmail': ['email', 'mail', 'inbox', 'send', 'compose'],
                'twitter': ['tweet', 'post', 'x', 'social', 'publish'],
                'github': ['repository', 'repo', 'issue', 'code', 'commit'],
                'slack': ['message', 'slack', 'team', 'channel', 'notify'],
                'google_calendar': ['calendar', 'meeting', 'event', 'schedule', 'appointment'],
                'notion': ['note', 'document', 'page', 'write', 'notion']
            }
            
            action_keywords = {
                'create': ['create', 'new', 'make', 'add', 'setup'],
                'send': ['send', 'share', 'post', 'publish', 'notify'],
                'fetch': ['get', 'read', 'fetch', 'retrieve', 'find'],
                'update': ['update', 'modify', 'edit', 'change'],
                'delete': ['delete', 'remove', 'cancel', 'close']
            }
            
            # Detect app
            detected_app = None
            for app, keywords in app_keywords.items():
                if any(keyword in description_lower for keyword in keywords):
                    detected_app = app
                    break
            
            # Detect action type
            detected_action_type = None
            for action_type, keywords in action_keywords.items():
                if any(keyword in description_lower for keyword in keywords):
                    detected_action_type = action_type
                    break
            
            if detected_app and detected_action_type:
                # Map to specific action names
                action_mapping = {
                    'gmail': {
                        'send': 'send_email',
                        'fetch': 'fetch_emails',
                        'create': 'create_draft'
                    },
                    'twitter': {
                        'create': 'create_post',
                        'send': 'create_post',
                        'fetch': 'get_tweets'
                    },
                    'github': {
                        'create': 'create_repository' if 'repo' in description_lower else 'create_issue',
                        'fetch': 'list_repositories'
                    },
                    'slack': {
                        'send': 'send_message',
                        'create': 'create_channel'
                    },
                    'google_calendar': {
                        'create': 'create_event',
                        'fetch': 'list_events'
                    },
                    'notion': {
                        'create': 'create_page',
                        'update': 'update_page'
                    }
                }
                
                action_name = action_mapping.get(detected_app, {}).get(detected_action_type, 'generic_action')
                
                actions.append({
                    'app_name': detected_app,
                    'action_name': action_name,
                    'description': workflow_description,
                    'depends_on': [],
                    'context_mapping': {}
                })
        
        # If still no actions, create a generic one
        if not actions:
            actions.append({
                'app_name': 'unknown',
                'action_name': 'generic_action',
                'description': workflow_description,
                'depends_on': [],
                'context_mapping': {}
            })
        
        # Add metadata to each action
        for action in actions:
            action['workflow_id'] = str(uuid.uuid4())
            action['priority'] = ExecutionPriority.NORMAL
            action['estimated_duration'] = 30  # seconds
        
        logger.info(f"Parsed workflow into {len(actions)} actions with enhanced NLP")
        return actions

    async def _plan_workflow_execution(
        self,
        actions: List[Dict[str, Any]],
        user_id: str
    ) -> Dict[str, Any]:
        """Plan the execution sequence for workflow actions."""
        
        # Build dependency graph
        action_map = {f"{action['app_name']}.{action['action_name']}": action for action in actions}
        
        # Topological sort for execution order
        execution_order = []
        completed = set()
        
        def can_execute(action):
            return all(dep in completed for dep in action.get('depends_on', []))
        
        while len(execution_order) < len(actions):
            ready_actions = [
                action for action in actions 
                if f"{action['app_name']}.{action['action_name']}" not in completed and can_execute(action)
            ]
            
            if not ready_actions:
                # Circular dependency or unresolvable dependencies
                remaining = [a for a in actions if f"{a['app_name']}.{a['action_name']}" not in completed]
                logger.warning(f"Cannot resolve dependencies for actions: {[f'{a['app_name']}.{a['action_name']}' for a in remaining]}")
                # Add them anyway to avoid infinite loop
                ready_actions = remaining
            
            for action in ready_actions[:1]:  # Process one at a time for now
                action_key = f"{action['app_name']}.{action['action_name']}"
                execution_order.append(action_key)
                completed.add(action_key)
        
        # Check authentication for all required apps
        required_apps = list(set(action['app_name'] for action in actions if action['app_name'] != 'unknown'))
        auth_checks = {}
        
        for app in required_apps:
            auth_status = await self._check_app_authentication(user_id, app)
            auth_checks[app] = auth_status
        
        plan = {
            'execution_order': execution_order,
            'actions': action_map,
            'auth_checks': auth_checks,
            'estimated_duration': len(actions) * 30,  # 30 seconds per action estimate
            'parallel_groups': [],  # TODO: Identify actions that can run in parallel
            'created_at': datetime.utcnow().isoformat()
        }
        
        return plan

    async def _execute_workflow_plan(
        self,
        workflow_id: str,
        execution_plan: Dict[str, Any],
        user_id: str,
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Execute a planned workflow."""
        
        workflow_result = {
            'workflow_id': workflow_id,
            'status': ExecutionStatus.RUNNING.value,
            'actions_completed': 0,
            'actions_total': len(execution_plan['execution_order']),
            'results': {},
            'errors': [],
            'started_at': datetime.utcnow().isoformat()
        }
        
        try:
            # Check authentication first
            missing_auth = []
            for app, auth_status in execution_plan['auth_checks'].items():
                if not auth_status['authenticated']:
                    missing_auth.append(app)
            
            if missing_auth:
                workflow_result['status'] = ExecutionStatus.FAILED.value
                workflow_result['errors'].append(f"Missing authentication for apps: {missing_auth}")
                return workflow_result
            
            # Execute actions in order
            workflow_context = context or {}
            
            for action_key in execution_plan['execution_order']:
                action = execution_plan['actions'][action_key]
                
                if action['app_name'] == 'unknown':
                    logger.warning(f"Skipping unknown action: {action_key}")
                    continue
                
                try:
                    logger.info(f"Executing workflow action: {action_key}")
                    
                    # Apply context mapping if specified
                    action_input = action['description']
                    action_metadata = {'workflow_id': workflow_id, **workflow_context}
                    
                    if action.get('context_mapping'):
                        try:
                            action_input = await self._apply_context_mapping(
                                action['description'], 
                                action.get('context_mapping', {}), 
                                workflow_context
                            )
                            logger.info(f"Applied context mapping for {action_key}")
                        except Exception as e:
                            logger.warning(f"Context mapping failed for {action_key}: {str(e)}")
                    
                    # Execute the action
                    action_result = await self.execute_action(
                        user_id=user_id,
                        app_name=action['app_name'],
                        action_name=action['action_name'],
                        natural_language_input=action_input,
                        metadata=action_metadata,
                        execute_immediately=True
                    )
                    
                    workflow_result['results'][action_key] = {
                        'status': action_result.status.value,
                        'data': action_result.data,
                        'error': action_result.error,
                        'execution_time_ms': action_result.execution_time_ms,
                        'context_applied': bool(action.get('context_mapping'))
                    }
                    
                    if action_result.status == ExecutionStatus.COMPLETED:
                        workflow_result['actions_completed'] += 1
                        
                        # Add structured result to context for next actions
                        if action_result.data:
                            context_key = f"{action_key}_result"
                            workflow_context[context_key] = action_result.data
                            
                            # Extract commonly needed fields for easier access
                            if isinstance(action_result.data, dict):
                                # For email results
                                if action['app_name'] == 'gmail' and action['action_name'] == 'fetch_emails':
                                    if 'messages' in action_result.data and action_result.data['messages']:
                                        latest_email = action_result.data['messages'][0]
                                        workflow_context['latest_email'] = latest_email
                                        workflow_context['latest_email_subject'] = latest_email.get('subject', '')
                                        workflow_context['latest_email_body'] = latest_email.get('body', '')
                                
                                # For social posts
                                elif action['app_name'] == 'twitter' and action['action_name'] == 'create_post':
                                    workflow_context['last_post_id'] = action_result.data.get('id')
                                    workflow_context['last_post_url'] = action_result.data.get('url')
                                
                                # For GitHub actions
                                elif action['app_name'] == 'github':
                                    if 'create' in action['action_name']:
                                        workflow_context['created_resource_url'] = action_result.data.get('html_url')
                                        workflow_context['created_resource_id'] = action_result.data.get('id')
                            
                            logger.info(f"Added {context_key} to workflow context")
                    else:
                        workflow_result['errors'].append(f"Action {action_key} failed: {action_result.error}")
                        
                        # Enhanced error handling - decide whether to continue
                        if action_result.error:
                            error_lower = action_result.error.lower()
                            
                            # Stop on authentication errors
                            if 'authentication' in error_lower or 'unauthorized' in error_lower:
                                logger.error(f"Authentication error in {action_key}, stopping workflow")
                                break
                            
                            # Continue on rate limit errors (they might resolve)
                            elif 'rate limit' in error_lower or '429' in error_lower:
                                logger.warning(f"Rate limit error in {action_key}, continuing workflow")
                                continue
                            
                            # Stop on critical dependency failures
                            elif action.get('depends_on') and 'required' in str(action.get('metadata', {})):
                                logger.error(f"Critical dependency failure in {action_key}, stopping workflow")
                                break
                    
                except Exception as e:
                    error_msg = f"Error executing {action_key}: {str(e)}"
                    workflow_result['errors'].append(error_msg)
                    logger.error(error_msg)
                    
                    # Continue with next action
                    continue
            
            # Determine overall status
            if workflow_result['actions_completed'] == workflow_result['actions_total']:
                workflow_result['status'] = ExecutionStatus.COMPLETED.value
            elif workflow_result['actions_completed'] > 0:
                workflow_result['status'] = 'partially_completed'
            else:
                workflow_result['status'] = ExecutionStatus.FAILED.value
            
        except Exception as e:
            workflow_result['status'] = ExecutionStatus.FAILED.value
            workflow_result['errors'].append(f"Workflow execution error: {str(e)}")
            logger.error(f"Workflow {workflow_id} failed: {str(e)}")
        
        finally:
            workflow_result['completed_at'] = datetime.utcnow().isoformat()
            
            # Calculate total execution time
            start_time = datetime.fromisoformat(workflow_result['started_at'])
            end_time = datetime.utcnow()
            workflow_result['total_execution_time_ms'] = int((end_time - start_time).total_seconds() * 1000)
        
        return workflow_result

    async def _process_queue(self):
        """Background task to process the execution queue."""
        
        while self._processing_active:
            try:
                # Process queues by priority
                for priority in ExecutionPriority:
                    queue = self._execution_queues[priority]
                    
                    if queue:
                        request_id = queue.pop(0)
                        
                        if request_id in self._pending_requests:
                            request = self._pending_requests.pop(request_id)
                            
                            # Execute the request
                            asyncio.create_task(
                                self._execute_single_action(request)
                            )
                            
                            # Rate limiting - don't overwhelm the APIs
                            await asyncio.sleep(1)
                        
                        break  # Process one request at a time
                
                # Wait before checking queue again
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Error in queue processor: {str(e)}")
                await asyncio.sleep(10)

    async def _check_app_authentication(self, user_id: str, app_name: str) -> Dict[str, Any]:
        """Check if user is authenticated for a specific app."""
        
        try:
            connected_accounts = await self.auth_manager.get_user_connected_accounts(user_id, app_name)
            
            return {
                'authenticated': len(connected_accounts) > 0,
                'accounts_count': len(connected_accounts),
                'healthy_accounts': len([acc for acc in connected_accounts if acc.get('is_healthy', False)])
            }
            
        except Exception as e:
            logger.error(f"Error checking authentication for {app_name}: {str(e)}")
            return {
                'authenticated': False,
                'accounts_count': 0,
                'healthy_accounts': 0,
                'error': str(e)
            }

    def _is_retryable_error(self, error_message: str) -> bool:
        """Determine if an error is retryable."""
        
        retryable_indicators = [
            'timeout', 'connection', 'network', 'rate limit', 
            'temporary', 'service unavailable', '503', '429'
        ]
        
        error_lower = error_message.lower()
        return any(indicator in error_lower for indicator in retryable_indicators)

    async def _update_execution_stats(self, request: ActionRequest, result: ActionResult):
        """Update execution statistics."""
        
        self._execution_stats['total_executions'] += 1
        
        if result.status == ExecutionStatus.COMPLETED:
            self._execution_stats['successful_executions'] += 1
        else:
            self._execution_stats['failed_executions'] += 1
        
        # Update app-specific stats
        app_name = request.app_name
        if app_name not in self._execution_stats['app_performance']:
            self._execution_stats['app_performance'][app_name] = {
                'total': 0,
                'successful': 0,
                'average_time': 0
            }
        
        app_stats = self._execution_stats['app_performance'][app_name]
        app_stats['total'] += 1
        
        if result.status == ExecutionStatus.COMPLETED:
            app_stats['successful'] += 1
        
        if result.execution_time_ms:
            # Update rolling average
            current_avg = app_stats['average_time']
            new_avg = ((current_avg * (app_stats['total'] - 1)) + result.execution_time_ms) / app_stats['total']
            app_stats['average_time'] = int(new_avg)

    async def get_execution_analytics(self) -> Dict[str, Any]:
        """Get comprehensive execution analytics."""
        
        analytics = {
            'statistics': self._execution_stats.copy(),
            'queue_status': {
                'pending_total': sum(len(queue) for queue in self._execution_queues.values()),
                'running_count': len(self._running_executions),
                'completed_count': len(self._completed_executions),
                'queue_by_priority': {
                    priority.value: len(self._execution_queues[priority])
                    for priority in ExecutionPriority
                }
            },
            'success_rate': 0,
            'generated_at': datetime.utcnow().isoformat()
        }
        
        # Calculate overall success rate
        total = analytics['statistics']['total_executions']
        if total > 0:
            analytics['success_rate'] = analytics['statistics']['successful_executions'] / total
        
        return analytics

    async def cleanup_old_executions(self, max_age_hours: int = 24):
        """Clean up old completed executions."""
        
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        old_executions = []
        for request_id, result in self._completed_executions.items():
            if result.completed_at and result.completed_at < cutoff_time:
                old_executions.append(request_id)
        
        for request_id in old_executions:
            del self._completed_executions[request_id]
        
        logger.info(f"Cleaned up {len(old_executions)} old executions")

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check for the action executor."""
        
        try:
            health_status = {
                'status': 'healthy',
                'processing_active': self._processing_active,
                'queue_processor_running': self._queue_processor_task and not self._queue_processor_task.done(),
                'pending_requests': sum(len(queue) for queue in self._execution_queues.values()),
                'running_executions': len(self._running_executions),
                'completed_executions': len(self._completed_executions),
                'total_executions': self._execution_stats['total_executions'],
                'success_rate': self._execution_stats['successful_executions'] / max(1, self._execution_stats['total_executions']),
                'checked_at': datetime.utcnow().isoformat()
            }
            
            # Check if any critical issues
            if not self._processing_active:
                health_status['status'] = 'unhealthy'
                health_status['issues'] = ['Queue processing not active']
            
            return health_status
            
        except Exception as e:
            logger.error(f"Action executor health check failed: {str(e)}")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'checked_at': datetime.utcnow().isoformat()
            }

    async def _apply_context_mapping(
        self, 
        base_input: str, 
        context_mapping: Dict[str, str], 
        workflow_context: Dict[str, Any]
    ) -> str:
        """
        Apply context mapping to transform action input using workflow context.
        
        Args:
            base_input: Original action description
            context_mapping: Mapping of parameters to context values
            workflow_context: Current workflow execution context
            
        Returns:
            Modified action input with context applied
        """
        try:
            modified_input = base_input
            
            # Apply simple template substitutions
            for param_name, context_ref in context_mapping.items():
                if context_ref.startswith('${') and context_ref.endswith('}'):
                    # Extract context path (e.g., "${gmail.fetch_emails_result.latest_email.subject}")
                    context_path = context_ref[2:-1]  # Remove ${ and }
                    
                    # Navigate context path
                    context_value = workflow_context
                    path_parts = context_path.split('.')
                    
                    for part in path_parts:
                        if isinstance(context_value, dict) and part in context_value:
                            context_value = context_value[part]
                        else:
                            # Context path not found, use default or skip
                            logger.warning(f"Context path '{context_path}' not found in workflow context")
                            context_value = f"[missing: {context_path}]"
                            break
                    
                    # Apply the substitution
                    if isinstance(context_value, str):
                        # For text-based parameters, append or replace
                        if param_name == 'text' and context_value not in modified_input:
                            modified_input = f"{modified_input}: {context_value}"
                        elif param_name in ['subject', 'title', 'summary']:
                            modified_input = f"{param_name}: {context_value}"
                    elif context_value is not None:
                        # Convert non-string values to string
                        modified_input = f"{modified_input} ({param_name}: {str(context_value)})"
                
                else:
                    # Direct context reference
                    if context_ref in workflow_context:
                        context_value = workflow_context[context_ref]
                        if isinstance(context_value, str):
                            modified_input = f"{modified_input}: {context_value}"
            
            # Smart context inference for common cases
            if 'latest_email_subject' in workflow_context and 'post' in base_input.lower():
                email_subject = workflow_context['latest_email_subject']
                if email_subject and email_subject not in modified_input:
                    modified_input = f"Post about: {email_subject}"
            
            if 'latest_email_body' in workflow_context and 'summarize' in base_input.lower():
                email_body = workflow_context['latest_email_body']
                if email_body and len(email_body) > 50:
                    # Extract first sentence or first 100 chars
                    summary = email_body[:100] + "..." if len(email_body) > 100 else email_body
                    modified_input = f"Summarize: {summary}"
            
            logger.info(f"Context mapping applied: '{base_input}' -> '{modified_input}'")
            return modified_input
            
        except Exception as e:
            logger.error(f"Error applying context mapping: {str(e)}")
            return base_input  # Return original input on error