"""
Composio Workflow Service
Orchestrates the complete Composio workflow following SOLID principles.
Each method has a single responsibility and dependencies are injected.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass

from .workflow_config import WorkflowConfig
from .authentication_service import AuthenticationInterface, AuthenticationResult
from .result_formatter_service import ResultFormatterInterface

logger = logging.getLogger(__name__)


@dataclass
class WorkflowStep:
    """Data class for workflow step results."""
    step_number: float
    step_name: str
    success: bool
    data: Any = None
    error_message: Optional[str] = None
    execution_time: Optional[float] = None


@dataclass
class WorkflowResult:
    """Data class for complete workflow results."""
    query: str
    success: bool
    steps_completed: float
    selected_app: Optional[str] = None
    auth_verified: bool = False
    selected_action: Optional[str] = None
    normalized_parameters: Dict[str, Any] = None
    execution_result: Dict[str, Any] = None
    total_time: Optional[float] = None
    timestamp: str = None
    error: Optional[str] = None
    steps: List[WorkflowStep] = None
    
    def __post_init__(self):
        if self.normalized_parameters is None:
            self.normalized_parameters = {}
        if self.execution_result is None:
            self.execution_result = {}
        if self.steps is None:
            self.steps = []
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class ComposioWorkflowService:
    """
    Main workflow orchestration service.
    Follows Single Responsibility Principle - orchestrates workflow steps.
    """
    
    def __init__(
        self,
        toolset,
        llm_service,
        auth_service: AuthenticationInterface,
        result_formatter: ResultFormatterInterface,
        config: WorkflowConfig
    ):
        self.toolset = toolset
        self.llm_service = llm_service
        self.auth_service = auth_service
        self.result_formatter = result_formatter
        self.config = config
        logger.info("ComposioWorkflowService initialized")
    
    async def execute_workflow(self, natural_query: str) -> WorkflowResult:
        """Execute the complete LLM-driven Composio workflow."""
        logger.info(f"Starting workflow for query: '{natural_query}'")
        
        workflow_result = WorkflowResult(
            query=natural_query,
            success=False,
            steps_completed=0
        )
        
        workflow_start = datetime.now()
        
        try:
            # Step 1: Fetch Composio apps
            step1 = await self._step_1_fetch_apps()
            workflow_result.steps.append(step1)
            
            if not step1.success:
                workflow_result.error = "Failed to fetch Composio apps"
                return workflow_result
            
            workflow_result.steps_completed = 1
            available_apps = step1.data
            
            # Step 2: LLM selects app
            step2 = await self._step_2_select_app(natural_query, available_apps)
            workflow_result.steps.append(step2)
            workflow_result.selected_app = step2.data
            workflow_result.steps_completed = 2
            
            # Step 2.5: Authentication check and OAuth
            step2_5 = await self._step_2_5_authenticate_app(step2.data)
            workflow_result.steps.append(step2_5)
            workflow_result.auth_verified = step2_5.success
            workflow_result.steps_completed = 2.5
            
            # Step 3: Fetch actions
            step3 = await self._step_3_fetch_actions(step2.data)
            workflow_result.steps.append(step3)
            
            if not step3.success:
                workflow_result.error = f"Failed to fetch actions for {step2.data}"
                return workflow_result
            
            workflow_result.steps_completed = 3
            available_actions = step3.data
            
            # Step 4: LLM selects action
            step4 = await self._step_4_select_action(natural_query, step2.data, available_actions)
            workflow_result.steps.append(step4)
            
            if not step4.success:
                workflow_result.error = "LLM failed to select an action"
                return workflow_result
            
            workflow_result.selected_action = str(step4.data)
            workflow_result.steps_completed = 4
            
            # Step 5: Fetch action schema
            step5 = await self._step_5_fetch_schema(step4.data)
            workflow_result.steps.append(step5)
            workflow_result.steps_completed = 5
            
            # Step 6: Normalize parameters
            step6 = await self._step_6_normalize_parameters(natural_query, step4.data, step5.data)
            workflow_result.steps.append(step6)
            workflow_result.normalized_parameters = step6.data
            workflow_result.steps_completed = 6
            
            # Step 7: Execute action
            step7 = await self._step_7_execute_action(step4.data, step6.data, step2.data)
            workflow_result.steps.append(step7)
            workflow_result.execution_result = step7.data
            workflow_result.steps_completed = 7
            
            # Mark as successful if we completed all steps
            workflow_result.success = True
            
        except Exception as e:
            logger.error(f"Workflow failed at step {workflow_result.steps_completed}: {str(e)}")
            workflow_result.error = str(e)
        
        finally:
            workflow_end = datetime.now()
            workflow_result.total_time = (workflow_end - workflow_start).total_seconds()
        
        return workflow_result
    
    async def _step_1_fetch_apps(self) -> WorkflowStep:
        """Step 1: Fetch all available Composio apps."""
        step_start = datetime.now()
        
        try:
            logger.info("Fetching apps from Composio")
            
            raw_apps = await asyncio.wait_for(
                asyncio.to_thread(self.toolset.get_apps),
                timeout=self.config.timeouts.composio_apps_fetch
            )
            
            # Extract app names
            unique_apps = self._extract_app_names(raw_apps)
            
            logger.info(f"Found {len(unique_apps)} unique apps")
            
            step_time = (datetime.now() - step_start).total_seconds()
            
            return WorkflowStep(
                step_number=1,
                step_name="Fetch Composio Apps",
                success=True,
                data=unique_apps,
                execution_time=step_time
            )
            
        except asyncio.TimeoutError:
            logger.warning("Composio API timeout - using fallback apps")
            return WorkflowStep(
                step_number=1,
                step_name="Fetch Composio Apps",
                success=True,
                data=self.config.app.fallback_apps,
                execution_time=(datetime.now() - step_start).total_seconds(),
                error_message="API timeout - using fallback"
            )
        except Exception as e:
            logger.error(f"Error fetching apps: {str(e)}")
            return WorkflowStep(
                step_number=1,
                step_name="Fetch Composio Apps",
                success=False,
                error_message=str(e),
                execution_time=(datetime.now() - step_start).total_seconds()
            )
    
    async def _step_2_select_app(self, query: str, available_apps: List[str]) -> WorkflowStep:
        """Step 2: Use LLM to select the most appropriate app."""
        step_start = datetime.now()
        
        try:
            logger.info(f"LLM selecting app for query: '{query}'")
            
            result = await self.llm_service.select_tool_with_llm(query)
            
            # Handle both dict and string returns
            if isinstance(result, dict):
                selected_app = result.get('selected_tool', 'GMAIL')
            else:
                selected_app = str(result) if result else 'GMAIL'
            
            # Validate selection
            if selected_app not in [app.upper() for app in available_apps]:
                logger.warning(f"LLM selected unavailable app: {selected_app}, using first available")
                selected_app = available_apps[0]
            
            step_time = (datetime.now() - step_start).total_seconds()
            
            return WorkflowStep(
                step_number=2,
                step_name="LLM Selects App",
                success=True,
                data=selected_app,
                execution_time=step_time
            )
            
        except Exception as e:
            logger.error(f"Error in LLM app selection: {str(e)}")
            return WorkflowStep(
                step_number=2,
                step_name="LLM Selects App",
                success=True,  # Continue with fallback
                data="GMAIL",
                execution_time=(datetime.now() - step_start).total_seconds(),
                error_message=f"LLM selection failed, using GMAIL: {str(e)}"
            )
    
    async def _step_2_5_authenticate_app(self, app_name: str) -> WorkflowStep:
        """Step 2.5: Check authentication and handle OAuth if needed."""
        step_start = datetime.now()
        
        try:
            logger.info(f"Checking authentication for {app_name}")
            
            auth_result = await self.auth_service.ensure_authentication(app_name, interactive=False)
            
            step_time = (datetime.now() - step_start).total_seconds()
            
            return WorkflowStep(
                step_number=2.5,
                step_name="Check Authentication & OAuth",
                success=auth_result.is_authenticated,
                data=auth_result,
                execution_time=step_time,
                error_message=auth_result.error_message if not auth_result.is_authenticated else None
            )
            
        except Exception as e:
            logger.error(f"Authentication check failed for {app_name}: {str(e)}")
            return WorkflowStep(
                step_number=2.5,
                step_name="Check Authentication & OAuth",
                success=False,
                execution_time=(datetime.now() - step_start).total_seconds(),
                error_message=str(e)
            )
    
    async def _step_3_fetch_actions(self, app_name: str) -> WorkflowStep:
        """Step 3: Fetch all available actions for the selected app."""
        step_start = datetime.now()
        
        try:
            logger.info(f"Fetching actions for {app_name}")
            
            raw_actions = await self._get_app_actions(app_name)
            
            if not raw_actions:
                # Use fallback actions
                actions = self._get_fallback_actions(app_name)
            else:
                actions = [{'name': str(action), 'action_object': action} for action in raw_actions]
            
            step_time = (datetime.now() - step_start).total_seconds()
            
            return WorkflowStep(
                step_number=3,
                step_name="Fetch Composio Actions",
                success=True,
                data=actions,
                execution_time=step_time
            )
            
        except Exception as e:
            logger.error(f"Error fetching actions for {app_name}: {str(e)}")
            # Return fallback actions even on error
            return WorkflowStep(
                step_number=3,
                step_name="Fetch Composio Actions",
                success=True,
                data=self._get_fallback_actions(app_name),
                execution_time=(datetime.now() - step_start).total_seconds(),
                error_message=f"API error, using fallback: {str(e)}"
            )
    
    async def _step_4_select_action(self, query: str, app_name: str, available_actions: List[Dict]) -> WorkflowStep:
        """Step 4: Use LLM to select the most appropriate action."""
        step_start = datetime.now()
        
        try:
            logger.info(f"LLM selecting action for {app_name}")
            
            action_names = [action['name'] for action in available_actions]
            actions_info = [{'name': name, 'description': f'Action for {app_name}'} for name in action_names]
            
            result = await self.llm_service.gemini_service.select_composio_action(
                query, app_name, actions_info
            )
            
            if not result:
                raise Exception("LLM returned no action selection")
            
            selected_action_name = result.get('selected_action')
            
            # Find the matching action object
            selected_action_object = None
            for action_info in available_actions:
                if action_info['name'] == selected_action_name:
                    selected_action_object = action_info['action_object']
                    break
            
            if not selected_action_object:
                # Use first available action as fallback
                selected_action_object = available_actions[0]['action_object']
            
            step_time = (datetime.now() - step_start).total_seconds()
            
            return WorkflowStep(
                step_number=4,
                step_name="LLM Selects Action",
                success=True,
                data=selected_action_object,
                execution_time=step_time
            )
            
        except Exception as e:
            logger.error(f"Error in LLM action selection: {str(e)}")
            return WorkflowStep(
                step_number=4,
                step_name="LLM Selects Action",
                success=False,
                execution_time=(datetime.now() - step_start).total_seconds(),
                error_message=str(e)
            )
    
    async def _step_5_fetch_schema(self, selected_action) -> WorkflowStep:
        """Step 5: Fetch the schema for the selected action."""
        step_start = datetime.now()
        
        try:
            logger.info("Fetching action schema")
            
            if isinstance(selected_action, str):
                # Fallback action, no schema available
                return WorkflowStep(
                    step_number=5,
                    step_name="Fetch Action Schema",
                    success=True,
                    data=None,
                    execution_time=(datetime.now() - step_start).total_seconds(),
                    error_message="Using fallback action - schema unavailable"
                )
            
            schema = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: self.toolset.get_action_schemas([selected_action], check_connected_accounts=False)
                ),
                timeout=self.config.timeouts.composio_schema_fetch
            )
            
            action_schema = schema[0] if schema else None
            
            step_time = (datetime.now() - step_start).total_seconds()
            
            return WorkflowStep(
                step_number=5,
                step_name="Fetch Action Schema",
                success=True,
                data=action_schema,
                execution_time=step_time
            )
            
        except Exception as e:
            logger.warning(f"Schema fetch failed: {str(e)}")
            return WorkflowStep(
                step_number=5,
                step_name="Fetch Action Schema",
                success=True,  # Continue without schema
                data=None,
                execution_time=(datetime.now() - step_start).total_seconds(),
                error_message=f"Schema unavailable: {str(e)}"
            )
    
    async def _step_6_normalize_parameters(self, query: str, selected_action, action_schema) -> WorkflowStep:
        """Step 6: Use LLM to normalize parameters from natural language query."""
        step_start = datetime.now()
        
        try:
            logger.info("Normalizing parameters with LLM")
            
            if action_schema:
                logger.info("Using full schema for parameter normalization")
                normalized_params = await self.llm_service.normalize_parameters_with_llm(
                    query, selected_action, action_schema
                )
            else:
                logger.info("Schema unavailable - using dynamic parameter extraction")
                normalized_params = await self.llm_service._extract_basic_parameters(
                    query, str(selected_action)
                )
            
            # Enhanced debugging for parameter extraction
            logger.info(f"Parameter extraction results:")
            logger.info(f"  Action: {selected_action}")
            logger.info(f"  Query: '{query}'")
            logger.info(f"  Extracted params: {normalized_params}")
            logger.info(f"  Parameter count: {len(normalized_params)}")
            
            # Validate that we have meaningful parameters
            if not normalized_params:
                logger.warning("No parameters extracted - this may cause execution issues")
            
            step_time = (datetime.now() - step_start).total_seconds()
            
            return WorkflowStep(
                step_number=6,
                step_name="LLM Normalizes Parameters",
                success=True,
                data=normalized_params,
                execution_time=step_time
            )
            
        except Exception as e:
            logger.error(f"Parameter normalization failed: {str(e)}")
            return WorkflowStep(
                step_number=6,
                step_name="LLM Normalizes Parameters",
                success=True,  # Continue with empty params
                data={},
                execution_time=(datetime.now() - step_start).total_seconds(),
                error_message=str(e)
            )
    
    async def _step_7_execute_action(self, selected_action, normalized_params: Dict, app_name: str) -> WorkflowStep:
        """Step 7: Execute the action with normalized parameters."""
        step_start = datetime.now()
        
        try:
            logger.info(f"Executing action: {selected_action}")
            logger.info(f"Parameters being sent: {normalized_params}")
            
            if isinstance(selected_action, str):
                # Fallback/simulated execution
                result = {
                    'simulated': True,
                    'action': selected_action,
                    'parameters': normalized_params,
                    'message': 'Fallback action demonstration - no actual execution'
                }
                success = True
            else:
                # Real execution with enhanced error capture
                try:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(
                            lambda: self.toolset.execute_action(
                                action=selected_action,
                                params=normalized_params,
                                entity_id=self.config.entity_id
                            )
                        ),
                        timeout=self.config.timeouts.action_execution
                    )
                    
                    # Check for execution errors in the result
                    if isinstance(result, dict) and 'error' in result:
                        logger.error(f"Composio execution error: {result['error']}")
                        # Still consider it "successful" for workflow continuation, but log the error
                        logger.warning("Action executed but returned an error - check parameters")
                    
                    success = True
                    logger.info(f"Action execution completed. Result type: {type(result)}")
                    
                except Exception as exec_error:
                    logger.error(f"Direct execution failed: {str(exec_error)}")
                    # Create error result for debugging
                    result = {
                        'execution_error': True,
                        'error': str(exec_error),
                        'action': str(selected_action),
                        'parameters': normalized_params,
                        'message': f'Execution failed: {str(exec_error)}'
                    }
                    success = False
            
            step_time = (datetime.now() - step_start).total_seconds()
            
            # Format results with LLM
            if result and not result.get('simulated') and not result.get('execution_error'):
                data_to_format = result.get('data', result)
                formatted_result = await self.result_formatter.format_result(
                    data_to_format, str(selected_action), app_name
                )
                result['formatted_output'] = formatted_result
            
            return WorkflowStep(
                step_number=7,
                step_name="Execute Action",
                success=success,
                data={
                    'result': result,
                    'success': success,
                    'execution_time': step_time
                },
                execution_time=step_time
            )
            
        except Exception as e:
            logger.error(f"Action execution failed: {str(e)}")
            return WorkflowStep(
                step_number=7,
                step_name="Execute Action",
                success=False,
                execution_time=(datetime.now() - step_start).total_seconds(),
                error_message=str(e)
            )
    
    def _extract_app_names(self, raw_apps) -> List[str]:
        """Extract app names from raw Composio apps."""
        all_apps = []
        for app in raw_apps:
            if hasattr(app, 'name'):
                all_apps.append(app.name.upper())
            elif hasattr(app, 'key'):
                all_apps.append(app.key.upper())
            else:
                app_str = str(app).upper()
                all_apps.append(app_str)
        
        return sorted(list(set(all_apps)))
    
    async def _get_app_actions(self, app_name: str):
        """Get actions for specific app."""
        try:
            from composio import App
            
            app_actions = None
            if app_name.upper() == "GMAIL":
                app_actions = await asyncio.wait_for(
                    asyncio.to_thread(lambda: list(App.GMAIL.get_actions())),
                    timeout=self.config.timeouts.composio_actions_fetch
                )
            elif app_name.upper() == "GITHUB":
                app_actions = await asyncio.wait_for(
                    asyncio.to_thread(lambda: list(App.GITHUB.get_actions())),
                    timeout=self.config.timeouts.composio_actions_fetch
                )
            elif app_name.upper() in ["SLACK"]:
                app_actions = await asyncio.wait_for(
                    asyncio.to_thread(lambda: list(App.SLACK.get_actions())),
                    timeout=self.config.timeouts.composio_actions_fetch
                )
            elif app_name.upper() in ["CALENDAR", "GOOGLECALENDAR"]:
                app_actions = await asyncio.wait_for(
                    asyncio.to_thread(lambda: list(App.GOOGLECALENDAR.get_actions())),
                    timeout=self.config.timeouts.composio_actions_fetch
                )
            
            return app_actions
            
        except Exception as e:
            logger.warning(f"Failed to get actions for {app_name}: {str(e)}")
            return None
    
    def _get_fallback_actions(self, app_name: str) -> List[Dict]:
        """Get fallback actions when API is unavailable."""
        fallback_map = {
            "GMAIL": [
                {"name": "GMAIL_FETCH_EMAILS", "action_object": "GMAIL_FETCH_EMAILS"},
                {"name": "GMAIL_SEND_EMAIL", "action_object": "GMAIL_SEND_EMAIL"},
                {"name": "GMAIL_CREATE_DRAFT", "action_object": "GMAIL_CREATE_DRAFT"}
            ],
            "GITHUB": [
                {"name": "GITHUB_GET_THE_AUTHENTICATED_USER", "action_object": "GITHUB_GET_THE_AUTHENTICATED_USER"},
                {"name": "GITHUB_REPOS_LIST_FOR_AUTHENTICATED_USER", "action_object": "GITHUB_REPOS_LIST_FOR_AUTHENTICATED_USER"},
                {"name": "GITHUB_ISSUES_CREATE", "action_object": "GITHUB_ISSUES_CREATE"}
            ]
        }
        
        return fallback_map.get(app_name.upper(), [
            {"name": f"{app_name.upper()}_GENERIC_ACTION", "action_object": f"{app_name.upper()}_GENERIC_ACTION"}
        ])