import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from pydantic import BaseModel, Field
from ..use_cases.composio_planner_agent import ComposioPlannerAgent
from ..infrastructure.composio_function_executor import ComposioFunctionExecutor
from ..infrastructure.composio_tool_discovery import ComposioToolDiscovery
from ..infrastructure.composio_auth_manager import ComposioAuthManager

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


# Pydantic models for request/response
class TaskExecutionRequest(BaseModel):
    query: str = Field(..., description="Natural language query to execute")
    conversation_id: Optional[str] = Field(None, description="Optional conversation ID for context")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context for execution")
    
    class Config:
        schema_extra = {
            "example": {
                "query": "Send an email to john@example.com with subject 'Meeting reminder' and body 'Don't forget our meeting tomorrow at 2 PM'",
                "conversation_id": "conv_user123_1234567890",
                "context": {"priority": "high"}
            }
        }


class TaskExecutionResponse(BaseModel):
    success: bool
    scenario: str
    intent: str
    execution_id: Optional[str] = None
    conversation_id: Optional[str] = None
    state: Optional[str] = None
    summary: Optional[str] = None
    message: Optional[str] = None
    key_results: Optional[List[str]] = None
    issues: Optional[List[str]] = None
    next_steps: Optional[List[str]] = None
    questions: Optional[List[Dict[str, Any]]] = None
    data: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any]


class ConversationContinueRequest(BaseModel):
    user_response: str = Field(..., description="User's response to clarification questions")
    
    class Config:
        schema_extra = {
            "example": {
                "user_response": "Tomorrow at 2 PM"
            }
        }


class ToolDiscoveryResponse(BaseModel):
    scenario: str
    available_tools: List[Dict[str, Any]]
    missing_tools: List[Dict[str, Any]]
    completeness: Dict[str, Any]
    apps_discovered: List[str]


class ExecutionStatusResponse(BaseModel):
    execution_id: str
    status: str
    user_id: str
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    steps: List[Dict[str, Any]]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ComposioTaskController:
    """
    FastAPI controller for task execution endpoints using Composio + Gemini.
    """
    
    def __init__(
        self,
        planner_agent: ComposioPlannerAgent,
        function_executor: ComposioFunctionExecutor,
        tool_discovery: ComposioToolDiscovery,
        auth_manager: ComposioAuthManager
    ):
        self.planner_agent = planner_agent
        self.function_executor = function_executor
        self.tool_discovery = tool_discovery
        self.auth_manager = auth_manager


# Dependency injection for controller
async def get_task_controller() -> ComposioTaskController:
    """Dependency injection for task controller."""
    # This will be injected by the main app
    pass


@router.post("/tasks/execute", response_model=TaskExecutionResponse)
async def execute_task(
    request: TaskExecutionRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(lambda: "user_demo"),  # Replace with proper auth
    controller: ComposioTaskController = Depends(get_task_controller)
) -> TaskExecutionResponse:
    """
    Execute a task based on natural language query.
    
    This endpoint processes user queries through the complete pipeline:
    1. Parse query using Gemini
    2. Discover required tools
    3. Check authentication
    4. Execute task tree
    5. Return results or clarification questions
    """
    try:
        logger.info(f"Executing task for user {user_id}: {request.query[:100]}...")
        
        # Process the query through planner agent
        result = await controller.planner_agent.process_user_query(
            user_id=user_id,
            query=request.query,
            conversation_id=request.conversation_id,
            context=request.context
        )
        
        # Convert result to response model
        response = TaskExecutionResponse(
            success=result['success'],
            scenario=result.get('scenario', 'unknown'),
            intent=result.get('intent', ''),
            execution_id=result.get('execution_id'),
            conversation_id=result.get('conversation_id'),
            state=result.get('state'),
            summary=result.get('summary'),
            message=result.get('message'),
            key_results=result.get('key_results'),
            issues=result.get('issues'),
            next_steps=result.get('next_steps'),
            questions=result.get('questions'),
            data=result.get('data'),
            error=result.get('error'),
            metadata=result.get('metadata', {})
        )
        
        # Add background task for cleanup if needed
        if result.get('execution_id'):
            background_tasks.add_task(
                log_execution_completion,
                result['execution_id'],
                user_id,
                result['success']
            )
        
        return response
        
    except Exception as e:
        logger.error(f"Error executing task: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Task execution failed: {str(e)}"
        )


@router.post("/tasks/conversations/{conversation_id}/continue", response_model=TaskExecutionResponse)
async def continue_conversation(
    conversation_id: str,
    request: ConversationContinueRequest,
    user_id: str = Depends(lambda: "user_demo"),  # Replace with proper auth
    controller: ComposioTaskController = Depends(get_task_controller)
) -> TaskExecutionResponse:
    """
    Continue an existing conversation with additional user input.
    
    Used when the system needs clarification or additional parameters
    from the user to complete a task.
    """
    try:
        logger.info(f"Continuing conversation {conversation_id} for user {user_id}")
        
        # Continue the conversation
        result = await controller.planner_agent.continue_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            user_response=request.user_response
        )
        
        # Convert result to response model
        response = TaskExecutionResponse(
            success=result['success'],
            scenario=result.get('scenario', 'unknown'),
            intent=result.get('intent', ''),
            execution_id=result.get('execution_id'),
            conversation_id=conversation_id,
            state=result.get('state'),
            summary=result.get('summary'),
            message=result.get('message'),
            key_results=result.get('key_results'),
            issues=result.get('issues'),
            next_steps=result.get('next_steps'),
            questions=result.get('questions'),
            data=result.get('data'),
            error=result.get('error'),
            metadata=result.get('metadata', {})
        )
        
        return response
        
    except ValueError as e:
        logger.error(f"Conversation error: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error continuing conversation: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Conversation continuation failed: {str(e)}"
        )


@router.get("/tasks/conversations/{conversation_id}/status")
async def get_conversation_status(
    conversation_id: str,
    user_id: str = Depends(lambda: "user_demo"),  # Replace with proper auth
    controller: ComposioTaskController = Depends(get_task_controller)
) -> Dict[str, Any]:
    """
    Get the current status of a conversation.
    """
    try:
        status = await controller.planner_agent.get_conversation_status(
            conversation_id=conversation_id,
            user_id=user_id
        )
        
        if not status:
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {conversation_id} not found"
            )
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get conversation status: {str(e)}"
        )


@router.get("/tasks/executions/{execution_id}/status", response_model=ExecutionStatusResponse)
async def get_execution_status(
    execution_id: str,
    user_id: str = Depends(lambda: "user_demo"),  # Replace with proper auth
    controller: ComposioTaskController = Depends(get_task_controller)
) -> ExecutionStatusResponse:
    """
    Get the status of a task execution.
    """
    try:
        status = await controller.function_executor.get_execution_status(execution_id)
        
        if not status:
            raise HTTPException(
                status_code=404,
                detail=f"Execution {execution_id} not found"
            )
        
        # Verify user owns this execution
        if status['user_id'] != user_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to view this execution"
            )
        
        # Convert to response model
        response = ExecutionStatusResponse(
            execution_id=execution_id,
            status=status['status'],
            user_id=status['user_id'],
            started_at=status['started_at'],
            completed_at=status.get('completed_at'),
            duration_ms=status.get('duration_ms'),
            steps=status.get('steps', []),
            result=status.get('result'),
            error=status.get('error')
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get execution status: {str(e)}"
        )


@router.post("/tasks/executions/{execution_id}/cancel")
async def cancel_execution(
    execution_id: str,
    user_id: str = Depends(lambda: "user_demo"),  # Replace with proper auth
    controller: ComposioTaskController = Depends(get_task_controller)
) -> Dict[str, Any]:
    """
    Cancel an active task execution.
    """
    try:
        result = await controller.function_executor.cancel_execution(
            execution_id=execution_id,
            user_id=user_id
        )
        
        if not result['success']:
            raise HTTPException(
                status_code=400,
                detail=result['error']
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling execution: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel execution: {str(e)}"
        )


@router.get("/tools/discover")
async def discover_tools(
    scenario: Optional[str] = Query(None, description="Scenario to discover tools for"),
    app: Optional[str] = Query(None, description="Specific app to get tools for"),
    controller: ComposioTaskController = Depends(get_task_controller)
) -> Dict[str, Any]:
    """
    Discover available Composio tools, optionally filtered by scenario or app.
    """
    try:
        if scenario:
            # Get tools for specific scenario
            tools_info = await controller.tool_discovery.discover_scenario_tools(scenario)
            return tools_info
        elif app:
            # Get tools for specific app
            from ..infrastructure.composio_service import ComposioService
            tools = await controller.tool_discovery.composio_service.discover_tools(app)
            return {
                'app': app,
                'tools': tools,
                'count': len(tools)
            }
        else:
            # Get completeness report for all scenarios
            report = await controller.tool_discovery.get_scenario_completeness_report()
            return report
            
    except Exception as e:
        logger.error(f"Error discovering tools: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Tool discovery failed: {str(e)}"
        )


@router.get("/tools/scenarios/{scenario}", response_model=ToolDiscoveryResponse)
async def get_scenario_tools(
    scenario: str,
    force_refresh: bool = Query(False, description="Force refresh of cached data"),
    controller: ComposioTaskController = Depends(get_task_controller)
) -> ToolDiscoveryResponse:
    """
    Get available tools for a specific scenario.
    """
    try:
        tools_info = await controller.tool_discovery.discover_scenario_tools(
            scenario=scenario,
            force_refresh=force_refresh
        )
        
        response = ToolDiscoveryResponse(
            scenario=tools_info['scenario'],
            available_tools=tools_info['available_tools'],
            missing_tools=tools_info['missing_tools'],
            completeness=tools_info['completeness'],
            apps_discovered=tools_info['apps_discovered']
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting scenario tools: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get scenario tools: {str(e)}"
        )


@router.post("/tools/generate-input")
async def generate_tool_input(
    tool_slug: str,
    user_input: str,
    context: Optional[Dict[str, Any]] = None,
    controller: ComposioTaskController = Depends(get_task_controller)
) -> Dict[str, Any]:
    """
    Generate structured input parameters for a tool based on natural language.
    """
    try:
        # Get tool schema
        from ..infrastructure.composio_service import ComposioService
        tool_schema = await controller.tool_discovery.composio_service.get_tool_schema(tool_slug)
        
        # Generate parameters using Gemini
        from ..infrastructure.gemini_service import GeminiService
        # This would need access to gemini service - simplified for now
        
        return {
            "tool_slug": tool_slug,
            "user_input": user_input,
            "generated_parameters": {},  # Would be generated by Gemini
            "schema": tool_schema,
            "message": "Tool input generation not fully implemented yet"
        }
        
    except Exception as e:
        logger.error(f"Error generating tool input: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Tool input generation failed: {str(e)}"
        )


@router.get("/tasks/history")
async def get_user_task_history(
    limit: int = Query(20, description="Maximum number of tasks to return"),
    user_id: str = Depends(lambda: "user_demo"),  # Replace with proper auth
    controller: ComposioTaskController = Depends(get_task_controller)
) -> Dict[str, Any]:
    """
    Get task execution history for the current user.
    """
    try:
        # Get conversation history
        conversation_history = await controller.planner_agent.get_user_conversation_history(
            user_id=user_id,
            limit=limit
        )
        
        # Get execution history
        execution_history = await controller.function_executor.get_user_execution_history(
            user_id=user_id,
            limit=limit
        )
        
        return {
            'user_id': user_id,
            'conversation_history': conversation_history,
            'execution_history': execution_history,
            'total_conversations': len(conversation_history),
            'total_executions': len(execution_history)
        }
        
    except Exception as e:
        logger.error(f"Error getting user history: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get user history: {str(e)}"
        )


# Background task functions
async def log_execution_completion(execution_id: str, user_id: str, success: bool):
    """Background task to log execution completion."""
    try:
        logger.info(f"Execution {execution_id} completed for user {user_id}: {'success' if success else 'failed'}")
        # Could add analytics, notifications, etc. here
    except Exception as e:
        logger.error(f"Error in background task: {str(e)}")


# Natural Language Query Execution endpoint
class NLQueryRequest(BaseModel):
    query: str = Field(..., description="Natural language query to execute")
    user_id: Optional[str] = Field(None, description="User identifier")
    
    class Config:
        schema_extra = {
            "example": {
                "query": "Send an email to john@example.com saying hello",
                "user_id": "user_123"
            }
        }


class NLQueryResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None
    error: Optional[str] = None
    execution_details: Optional[Dict[str, Any]] = None


@router.post("/query/execute", response_model=NLQueryResponse)
async def execute_nl_query(
    request: NLQueryRequest,
    controller: ComposioTaskController = Depends(get_task_controller)
) -> NLQueryResponse:
    """
    Direct natural language query execution endpoint.
    
    This endpoint processes natural language queries and executes them directly
    without the full conversation/planning pipeline. It's designed for simple,
    direct task execution.
    
    Examples:
    - "Send an email to john@example.com with subject 'Meeting' and body 'See you tomorrow'"
    - "Find flights from NYC to London next week"
    - "Post a tweet saying 'Hello world'"
    - "Schedule a meeting for tomorrow at 2 PM"
    """
    try:
        logger.info(f"Processing NL query: {request.query[:100]}...")
        
        user_id = request.user_id or "demo_user"
        
        # Use the planner agent to process the query directly
        result = await controller.planner_agent.process_user_query(
            user_id=user_id,
            query=request.query,
            conversation_id=None,  # No conversation tracking for direct queries
            context={"direct_execution": True}
        )
        
        # Format response based on result
        if result['success']:
            response = NLQueryResponse(
                success=True,
                message=result.get('summary', 'Query executed successfully'),
                data=result.get('data'),
                execution_details={
                    'scenario': result.get('scenario'),
                    'intent': result.get('intent'),
                    'execution_id': result.get('execution_id'),
                    'key_results': result.get('key_results'),
                    'steps_completed': len(result.get('key_results', []))
                }
            )
        else:
            # Check if this is an authentication error
            if result.get('error') and 'auth' in result.get('error', '').lower():
                response = NLQueryResponse(
                    success=False,
                    message="Authentication required. Please connect your account first.",
                    error=result.get('error'),
                    execution_details={
                        'scenario': result.get('scenario'),
                        'auth_required': True,
                        'required_apps': result.get('metadata', {}).get('required_apps', [])
                    }
                )
            else:
                response = NLQueryResponse(
                    success=False,
                    message=result.get('error', 'Query execution failed'),
                    error=result.get('error'),
                    execution_details={
                        'scenario': result.get('scenario'),
                        'issues': result.get('issues', [])
                    }
                )
        
        return response
        
    except Exception as e:
        logger.error(f"Error in natural language query execution: {str(e)}")
        return NLQueryResponse(
            success=False,
            message="Internal server error occurred",
            error=str(e)
        )


# Additional utility endpoints
@router.get("/tasks/scenarios")
async def list_supported_scenarios() -> Dict[str, Any]:
    """
    List all supported scenarios with their descriptions.
    """
    scenarios = {
        'email': {
            'name': 'Email Management',
            'description': 'Read, send, and manage emails',
            'primary_tools': ['GMAIL_FETCH_EMAILS', 'GMAIL_SEND_EMAIL'],
            'example_queries': [
                'Send an email to john@example.com',
                'Check my unread emails',
                'Reply to the latest email from Sarah'
            ]
        },
        'flight_booking': {
            'name': 'Flight Booking',
            'description': 'Search and book flights',
            'primary_tools': ['SKYSCANNER_SEARCH_FLIGHTS', 'SKYSCANNER_BOOK_FLIGHT'],
            'example_queries': [
                'Find flights from New York to London',
                'Book a flight to Paris next week',
                'Search for round-trip flights to Tokyo'
            ]
        },
        'meeting_scheduling': {
            'name': 'Meeting Scheduling',
            'description': 'Schedule meetings and calendar events',
            'primary_tools': ['GOOGLE_CALENDAR_CREATE_EVENT', 'ZOOM_CREATE_MEETING'],
            'example_queries': [
                'Schedule a meeting with the team tomorrow',
                'Create a Zoom meeting for Friday at 2 PM',
                'Book a conference room for next week'
            ]
        },
        'trip_planning': {
            'name': 'Trip Planning',
            'description': 'Plan complete trips with flights, hotels, and activities',
            'primary_tools': ['SKYSCANNER_SEARCH_FLIGHTS', 'BOOKING_SEARCH_HOTELS'],
            'example_queries': [
                'Plan a weekend trip to Barcelona',
                'Find hotels near the Eiffel Tower',
                'Plan a business trip to San Francisco'
            ]
        },
        'food_ordering': {
            'name': 'Food Ordering',
            'description': 'Order food from restaurants',
            'primary_tools': ['DOORDASH_SEARCH_RESTAURANTS', 'DOORDASH_PLACE_ORDER'],
            'example_queries': [
                'Order pizza for dinner',
                'Find Italian restaurants nearby',
                'Order lunch from my favorite restaurant'
            ]
        },
        'x_posting': {
            'name': 'X/Twitter Posting',
            'description': 'Post content to X/Twitter',
            'primary_tools': ['TWITTER_CREATION_OF_A_POST'],
            'example_queries': [
                'Post a tweet about my latest project',
                'Share this article on Twitter',
                'Tweet about the conference I attended'
            ]
        }
    }
    
    return {
        'supported_scenarios': scenarios,
        'total_scenarios': len(scenarios)
    }