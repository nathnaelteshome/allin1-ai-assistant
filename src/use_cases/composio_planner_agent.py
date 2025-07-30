import os
import json
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging
from ..infrastructure.gemini_service import GeminiService
from ..infrastructure.composio_service import ComposioService
from ..infrastructure.composio_auth_manager import ComposioAuthManager
from ..infrastructure.composio_tool_discovery import ComposioToolDiscovery
from ..infrastructure.composio_function_executor import ComposioFunctionExecutor

logger = logging.getLogger(__name__)


class ComposioPlannerAgent:
    """
    Enhanced Planner Agent that uses Gemini for natural language understanding
    and Composio for unified tool execution across all scenarios.
    """
    
    def __init__(
        self,
        gemini_service: GeminiService,
        composio_service: ComposioService,
        auth_manager: ComposioAuthManager,
        tool_discovery: ComposioToolDiscovery,
        function_executor: ComposioFunctionExecutor
    ):
        self.gemini_service = gemini_service
        self.composio_service = composio_service
        self.auth_manager = auth_manager
        self.tool_discovery = tool_discovery
        self.function_executor = function_executor
        
        # Planning state
        self._active_conversations: Dict[str, Dict[str, Any]] = {}
        self._conversation_history: List[Dict[str, Any]] = []
        
        logger.info("ComposioPlannerAgent initialized")

    async def process_user_query(
        self, 
        user_id: str, 
        query: str,
        conversation_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a user query through the complete pipeline: parse -> plan -> execute.
        
        Args:
            user_id: User identifier
            query: Natural language query
            conversation_id: Optional conversation context
            context: Additional context for processing
            
        Returns:
            Complete processing result including execution outcome
        """
        try:
            logger.info(f"Processing query for user {user_id}: {query[:100]}...")
            
            # Step 1: Parse the query using Gemini
            parsed_query = await self.gemini_service.parse_user_query(query)
            
            # Step 2: Check scenario completeness and tool availability
            scenario = parsed_query['scenario']
            scenario_tools = await self.tool_discovery.discover_scenario_tools(scenario)
            
            if not scenario_tools['completeness']['is_functional']:
                return await self._handle_incomplete_scenario(
                    user_id, parsed_query, scenario_tools
                )
            
            # Step 3: Check for missing parameters and required clarifications
            if parsed_query.get('clarification_needed') or parsed_query.get('missing_parameters'):
                return await self._handle_missing_parameters(
                    user_id, parsed_query, scenario_tools, conversation_id
                )
            
            # Step 4: Check user authentication for required apps
            auth_check = await self._check_user_authentication(
                user_id, scenario_tools['apps_discovered']
            )
            
            if not auth_check['all_authenticated']:
                return await self._handle_authentication_required(
                    user_id, auth_check, scenario
                )
            
            # Step 5: Build execution plan (task tree)
            task_tree_result = await self.gemini_service.build_task_tree(
                scenario=scenario,
                parameters=parsed_query['parameters'],
                available_tools=scenario_tools['available_tools']
            )
            
            # Step 6: Optimize task sequence if needed
            if len(task_tree_result['execution_order']) > 3:
                optimization_result = await self.gemini_service.optimize_task_sequence(
                    task_tree_result['task_tree']
                )
                task_tree_result['task_tree'] = optimization_result['optimized_tree']
            
            # Step 7: Execute the task tree
            execution_result = await self.function_executor.execute_task_tree(
                task_tree=task_tree_result['task_tree'],
                user_id=user_id,
                execution_context={
                    'scenario': scenario,
                    'original_query': query,
                    'conversation_id': conversation_id
                }
            )
            
            # Step 8: Analyze and summarize results
            analysis_result = await self.gemini_service.analyze_execution_result(
                execution_result=execution_result,
                original_query=query,
                scenario=scenario
            )
            
            # Step 9: Prepare final response
            final_response = {
                'success': execution_result['success'],
                'scenario': scenario,
                'intent': parsed_query['intent'],
                'execution_id': execution_result['execution_id'],
                'summary': analysis_result['summary'],
                'key_results': analysis_result.get('key_results', []),
                'issues': analysis_result.get('issues', []),
                'next_steps': analysis_result.get('next_steps', []),
                'data': execution_result.get('data'),
                'metadata': {
                    'user_id': user_id,
                    'query': query,
                    'processed_at': datetime.utcnow().isoformat(),
                    'confidence': parsed_query['confidence'],
                    'tools_used': task_tree_result['execution_order'],
                    'duration_ms': execution_result.get('metadata', {}).get('duration_ms')
                }
            }
            
            # Update conversation history
            if conversation_id:
                await self._update_conversation_history(
                    conversation_id, user_id, query, final_response
                )
            
            logger.info(f"Query processed successfully for user {user_id}")
            return final_response
            
        except Exception as e:
            logger.error(f"Error processing user query: {str(e)}")
            
            error_response = {
                'success': False,
                'error': str(e),
                'scenario': parsed_query.get('scenario') if 'parsed_query' in locals() else 'unknown',
                'query': query,
                'metadata': {
                    'user_id': user_id,
                    'processed_at': datetime.utcnow().isoformat(),
                    'error_type': 'processing_error'
                }
            }
            
            return error_response

    async def continue_conversation(
        self, 
        conversation_id: str, 
        user_id: str,
        user_response: str
    ) -> Dict[str, Any]:
        """
        Continue an existing conversation with additional user input.
        
        Args:
            conversation_id: Conversation identifier
            user_id: User identifier
            user_response: User's response to clarification questions
            
        Returns:
            Updated processing result
        """
        try:
            if conversation_id not in self._active_conversations:
                raise ValueError(f"Conversation {conversation_id} not found")
            
            conversation = self._active_conversations[conversation_id]
            
            if conversation['user_id'] != user_id:
                raise ValueError(f"Conversation {conversation_id} does not belong to user {user_id}")
            
            # Process user response based on conversation state
            if conversation['state'] == 'awaiting_parameters':
                return await self._process_parameter_response(
                    conversation_id, user_response, conversation
                )
            elif conversation['state'] == 'awaiting_authentication':
                return await self._process_authentication_response(
                    conversation_id, user_response, conversation
                )
            else:
                raise ValueError(f"Invalid conversation state: {conversation['state']}")
                
        except Exception as e:
            logger.error(f"Error continuing conversation {conversation_id}: {str(e)}")
            raise

    async def get_conversation_status(
        self, 
        conversation_id: str, 
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get the current status of a conversation.
        
        Args:
            conversation_id: Conversation identifier
            user_id: User identifier for authorization
            
        Returns:
            Conversation status or None if not found
        """
        if conversation_id not in self._active_conversations:
            return None
        
        conversation = self._active_conversations[conversation_id]
        
        if conversation['user_id'] != user_id:
            return None
        
        return {
            'conversation_id': conversation_id,
            'state': conversation['state'],
            'scenario': conversation.get('scenario'),
            'created_at': conversation['created_at'],
            'last_updated': conversation.get('last_updated'),
            'pending_questions': conversation.get('pending_questions', []),
            'collected_parameters': conversation.get('collected_parameters', {})
        }

    async def _handle_incomplete_scenario(
        self, 
        user_id: str, 
        parsed_query: Dict[str, Any],
        scenario_tools: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle scenarios where required tools are not available.
        
        Args:
            user_id: User identifier
            parsed_query: Parsed query information
            scenario_tools: Tool availability information
            
        Returns:
            Response indicating scenario incompleteness
        """
        missing_tools = scenario_tools['missing_tools']
        primary_missing = [tool for tool in missing_tools if tool['is_primary']]
        
        # Try to find alternatives for missing tools
        alternatives = {}
        for missing_tool in primary_missing:
            tool_alternatives = await self.tool_discovery.find_alternative_tools(
                missing_tool['slug'], parsed_query['scenario']
            )
            if tool_alternatives:
                alternatives[missing_tool['slug']] = tool_alternatives[:3]  # Top 3 alternatives
        
        response = {
            'success': False,
            'scenario': parsed_query['scenario'],
            'error_type': 'incomplete_scenario',
            'message': f"Sorry, the {parsed_query['scenario']} scenario is not fully available.",
            'details': {
                'completeness_percentage': scenario_tools['completeness']['percentage'],
                'missing_primary_tools': [tool['slug'] for tool in primary_missing],
                'available_alternatives': alternatives
            },
            'suggestions': [
                "Check back later as we add more integrations",
                "Try a different but related request",
                "Contact support for priority feature requests"
            ],
            'metadata': {
                'user_id': user_id,
                'processed_at': datetime.utcnow().isoformat()
            }
        }
        
        return response

    async def _handle_missing_parameters(
        self, 
        user_id: str, 
        parsed_query: Dict[str, Any],
        scenario_tools: Dict[str, Any],
        conversation_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Handle cases where parameters are missing and clarification is needed.
        
        Args:
            user_id: User identifier
            parsed_query: Parsed query information
            scenario_tools: Available tools information
            conversation_id: Optional conversation context
            
        Returns:
            Response with clarification questions
        """
        missing_params = parsed_query.get('missing_parameters', [])
        
        # Get tool schemas for parameter generation
        tool_schemas = {}
        for tool in scenario_tools['available_tools']:
            if tool['is_primary']:
                tool_schemas[tool['slug']] = tool['schema']
        
        # Generate clarification questions
        questions = await self.gemini_service.generate_clarification_questions(
            scenario=parsed_query['scenario'],
            missing_parameters=missing_params,
            tool_schemas=tool_schemas,
            context=parsed_query.get('parameters', {})
        )
        
        # Create or update conversation
        if not conversation_id:
            conversation_id = f"conv_{user_id}_{datetime.utcnow().timestamp()}"
        
        conversation_data = {
            'conversation_id': conversation_id,
            'user_id': user_id,
            'scenario': parsed_query['scenario'],
            'state': 'awaiting_parameters',
            'original_query': parsed_query.get('original_query', ''),
            'parsed_query': parsed_query,
            'scenario_tools': scenario_tools,
            'pending_questions': questions,
            'collected_parameters': parsed_query.get('parameters', {}),
            'created_at': datetime.utcnow().isoformat(),
            'last_updated': datetime.utcnow().isoformat()
        }
        
        self._active_conversations[conversation_id] = conversation_data
        
        response = {
            'success': False,
            'scenario': parsed_query['scenario'],
            'conversation_id': conversation_id,
            'state': 'awaiting_parameters',
            'message': "I need some additional information to help you with this request.",
            'questions': questions,
            'collected_parameters': parsed_query.get('parameters', {}),
            'metadata': {
                'user_id': user_id,
                'processed_at': datetime.utcnow().isoformat()
            }
        }
        
        return response

    async def _check_user_authentication(
        self, 
        user_id: str, 
        required_apps: List[str]
    ) -> Dict[str, Any]:
        """
        Check if user has authenticated with all required apps.
        
        Args:
            user_id: User identifier
            required_apps: List of app names that need authentication
            
        Returns:
            Authentication status information
        """
        auth_status = {
            'all_authenticated': True,
            'authenticated_apps': [],
            'missing_apps': [],
            'app_details': {}
        }
        
        for app in required_apps:
            connected_accounts = await self.auth_manager.get_user_connected_accounts(user_id, app)
            
            if connected_accounts:
                auth_status['authenticated_apps'].append(app)
                auth_status['app_details'][app] = {
                    'connected': True,
                    'accounts_count': len(connected_accounts),
                    'healthy_accounts': len([acc for acc in connected_accounts if acc.get('is_healthy', False)])
                }
            else:
                auth_status['missing_apps'].append(app)
                auth_status['app_details'][app] = {
                    'connected': False,
                    'accounts_count': 0,
                    'healthy_accounts': 0
                }
                auth_status['all_authenticated'] = False
        
        return auth_status

    async def _handle_authentication_required(
        self, 
        user_id: str, 
        auth_check: Dict[str, Any],
        scenario: str
    ) -> Dict[str, Any]:
        """
        Handle cases where user authentication is required.
        
        Args:
            user_id: User identifier
            auth_check: Authentication check results
            scenario: Current scenario
            
        Returns:
            Response with authentication instructions
        """
        missing_apps = auth_check['missing_apps']
        
        # Generate OAuth URLs for missing apps
        oauth_urls = {}
        for app in missing_apps:
            try:
                # This would typically use a configured redirect URL
                redirect_url = os.getenv('OAUTH_REDIRECT_URL', 'http://localhost:5000/auth/callback')
                
                oauth_result = await self.auth_manager.initiate_account_connection(
                    user_id=user_id,
                    app_name=app,
                    redirect_url=redirect_url,
                    metadata={'scenario': scenario}
                )
                
                oauth_urls[app] = {
                    'auth_url': oauth_result['auth_url'],
                    'session_id': oauth_result['session_id']
                }
                
            except Exception as e:
                logger.error(f"Failed to generate OAuth URL for {app}: {str(e)}")
                oauth_urls[app] = {
                    'error': str(e)
                }
        
        response = {
            'success': False,
            'scenario': scenario,
            'error_type': 'authentication_required',
            'message': f"Please connect your accounts to proceed with {scenario}.",
            'required_connections': missing_apps,
            'oauth_urls': oauth_urls,
            'already_connected': auth_check['authenticated_apps'],
            'instructions': [
                "Click on the authentication links above",
                "Complete the OAuth flow for each required service",
                "Return here to continue with your request"
            ],
            'metadata': {
                'user_id': user_id,
                'processed_at': datetime.utcnow().isoformat()
            }
        }
        
        return response

    async def _process_parameter_response(
        self, 
        conversation_id: str, 
        user_response: str,
        conversation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process user response to parameter collection questions.
        
        Args:
            conversation_id: Conversation identifier
            user_response: User's response
            conversation: Conversation data
            
        Returns:
            Updated processing result
        """
        try:
            # Extract parameters from user response using Gemini
            pending_questions = conversation['pending_questions']
            current_parameters = conversation['collected_parameters']
            
            # Generate parameters from natural language response
            # This is a simplified approach - in reality, you'd want more sophisticated parameter extraction
            for question in pending_questions:
                if question['parameter'] not in current_parameters:
                    # Use Gemini to extract the specific parameter value
                    # For now, using a simple approach
                    current_parameters[question['parameter']] = user_response
                    break  # Process one parameter at a time for clarity
            
            # Update conversation
            conversation['collected_parameters'] = current_parameters
            conversation['last_updated'] = datetime.utcnow().isoformat()
            
            # Check if we have all required parameters now
            parsed_query = conversation['parsed_query']
            missing_params = set(parsed_query.get('missing_parameters', []))
            collected_params = set(current_parameters.keys())
            
            still_missing = missing_params - collected_params
            
            if still_missing:
                # Still need more parameters
                remaining_questions = [q for q in pending_questions if q['parameter'] in still_missing]
                conversation['pending_questions'] = remaining_questions
                
                return {
                    'success': False,
                    'conversation_id': conversation_id,
                    'state': 'awaiting_parameters',
                    'message': "Thank you! I need just a bit more information.",
                    'questions': remaining_questions[:1],  # Ask one at a time
                    'collected_parameters': current_parameters,
                    'metadata': {
                        'user_id': conversation['user_id'],
                        'processed_at': datetime.utcnow().isoformat()
                    }
                }
            else:
                # All parameters collected, proceed with execution
                conversation['state'] = 'executing'
                
                # Update the parsed query with collected parameters
                updated_query = conversation['parsed_query']
                updated_query['parameters'].update(current_parameters)
                updated_query['clarification_needed'] = False
                updated_query['missing_parameters'] = []
                
                # Clean up conversation
                del self._active_conversations[conversation_id]
                
                # Process the complete query
                return await self.process_user_query(
                    user_id=conversation['user_id'],
                    query=conversation['original_query'],
                    conversation_id=conversation_id,
                    context={'collected_parameters': current_parameters}
                )
                
        except Exception as e:
            logger.error(f"Error processing parameter response: {str(e)}")
            raise

    async def _process_authentication_response(
        self, 
        conversation_id: str, 
        user_response: str,
        conversation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process user response to authentication requirements.
        
        Args:
            conversation_id: Conversation identifier
            user_response: User's response
            conversation: Conversation data
            
        Returns:
            Updated processing result
        """
        # This would handle OAuth callback processing
        # For now, return a placeholder response
        return {
            'success': False,
            'message': "OAuth callback processing not yet implemented",
            'conversation_id': conversation_id,
            'metadata': {
                'user_id': conversation['user_id'],
                'processed_at': datetime.utcnow().isoformat()
            }
        }

    async def _update_conversation_history(
        self, 
        conversation_id: str, 
        user_id: str,
        query: str, 
        response: Dict[str, Any]
    ):
        """
        Update conversation history for analytics and learning.
        
        Args:
            conversation_id: Conversation identifier
            user_id: User identifier
            query: User query
            response: System response
        """
        history_entry = {
            'conversation_id': conversation_id,
            'user_id': user_id,
            'timestamp': datetime.utcnow().isoformat(),
            'query': query,
            'response_summary': {
                'success': response['success'],
                'scenario': response.get('scenario'),
                'execution_id': response.get('execution_id')
            }
        }
        
        self._conversation_history.append(history_entry)
        
        # Keep only last 1000 entries to prevent memory issues
        if len(self._conversation_history) > 1000:
            self._conversation_history = self._conversation_history[-1000:]

    async def get_user_conversation_history(
        self, 
        user_id: str, 
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get conversation history for a user.
        
        Args:
            user_id: User identifier
            limit: Maximum number of conversations to return
            
        Returns:
            User's conversation history
        """
        user_conversations = [
            conv for conv in self._conversation_history 
            if conv['user_id'] == user_id
        ]
        
        # Sort by most recent first
        user_conversations.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return user_conversations[:limit]

    async def cleanup_expired_conversations(self, max_age_hours: int = 24):
        """
        Clean up expired conversations.
        
        Args:
            max_age_hours: Maximum age for conversations in hours
        """
        from datetime import timedelta
        
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        expired_conversations = []
        for conv_id, conv_data in self._active_conversations.items():
            created_at = datetime.fromisoformat(conv_data['created_at'])
            if created_at < cutoff_time:
                expired_conversations.append(conv_id)
        
        for conv_id in expired_conversations:
            del self._active_conversations[conv_id]
        
        logger.info(f"Cleaned up {len(expired_conversations)} expired conversations")

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check for the planner agent.
        
        Returns:
            Health status information
        """
        try:
            # Check all services
            gemini_health = await self.gemini_service.health_check()
            composio_health = await self.composio_service.health_check()
            
            health_status = {
                'status': 'healthy' if gemini_health['status'] == 'healthy' and composio_health['status'] == 'healthy' else 'unhealthy',
                'services': {
                    'gemini': gemini_health,
                    'composio': composio_health
                },
                'active_conversations': len(self._active_conversations),
                'conversation_history_size': len(self._conversation_history),
                'checked_at': datetime.utcnow().isoformat()
            }
            
            return health_status
            
        except Exception as e:
            logger.error(f"Planner agent health check failed: {str(e)}")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'checked_at': datetime.utcnow().isoformat()
            }