import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from ..domain.models.chat_models import ChatResponse, ResponseType

logger = logging.getLogger(__name__)


class ChatException(Exception):
    """Base exception for chat-related errors."""
    
    def __init__(self, message: str, error_code: str = "CHAT_ERROR", 
                 user_friendly_message: Optional[str] = None, suggestions: Optional[list] = None):
        self.message = message
        self.error_code = error_code
        self.user_friendly_message = user_friendly_message or message
        self.suggestions = suggestions or []
        super().__init__(self.message)


class WorkflowStepException(ChatException):
    """Exception for workflow step-specific errors."""
    
    def __init__(self, step: float, step_name: str, message: str, 
                 user_friendly_message: Optional[str] = None, suggestions: Optional[list] = None):
        self.step = step
        self.step_name = step_name
        super().__init__(
            message=message,
            error_code=f"WORKFLOW_STEP_{step}_ERROR",
            user_friendly_message=user_friendly_message,
            suggestions=suggestions
        )


class AuthenticationRequiredException(ChatException):
    """Exception when app authentication is required."""
    
    def __init__(self, app_name: str, oauth_url: Optional[str] = None):
        self.app_name = app_name
        self.oauth_url = oauth_url
        
        user_message = f"I need to connect to your {app_name} account to help you with this request."
        suggestions = [
            f"Click the authentication link to connect {app_name}",
            "After connecting, I'll automatically continue with your request"
        ]
        
        super().__init__(
            message=f"Authentication required for {app_name}",
            error_code="AUTH_REQUIRED",
            user_friendly_message=user_message,
            suggestions=suggestions
        )


class InsufficientParametersException(ChatException):
    """Exception when user query lacks sufficient parameters."""
    
    def __init__(self, missing_parameters: list, suggestions: str = ""):
        self.missing_parameters = missing_parameters
        
        user_message = "I need some additional information to complete your request."
        if suggestions:
            user_message += f" {suggestions}"
        
        suggestion_list = [
            "Please provide more specific details about what you want to do",
            "You can refine your request with additional information"
        ]
        
        if missing_parameters:
            suggestion_list.insert(0, f"Missing information: {', '.join(missing_parameters)}")
        
        super().__init__(
            message=f"Insufficient parameters: {missing_parameters}",
            error_code="INSUFFICIENT_PARAMS",
            user_friendly_message=user_message,
            suggestions=suggestion_list
        )


class WorkflowExecutionException(ChatException):
    """Exception during workflow execution."""
    
    def __init__(self, step: float, action: str, message: str):
        self.step = step
        self.action = action
        
        user_message = self._get_user_friendly_execution_error(action, message)
        suggestions = self._get_execution_error_suggestions(action, message)
        
        super().__init__(
            message=message,
            error_code="EXECUTION_FAILED",
            user_friendly_message=user_message,
            suggestions=suggestions
        )
    
    def _get_user_friendly_execution_error(self, action: str, error_msg: str) -> str:
        """Convert technical error to user-friendly message."""
        error_lower = error_msg.lower()
        
        if "authentication" in error_lower or "unauthorized" in error_lower:
            return "It looks like the app connection has expired or needs to be renewed."
        elif "rate limit" in error_lower or "quota" in error_lower:
            return "The service is temporarily busy. Please try again in a few minutes."
        elif "not found" in error_lower:
            return "I couldn't find the resource you're looking for. Please check the details and try again."
        elif "permission" in error_lower or "forbidden" in error_lower:
            return "You don't have permission to perform this action. Please check your account settings."
        elif "network" in error_lower or "timeout" in error_lower:
            return "I'm having trouble connecting to the service. Please try again."
        else:
            return f"I encountered an issue while trying to {self._get_action_description(action)}."
    
    def _get_execution_error_suggestions(self, action: str, error_msg: str) -> list:
        """Get helpful suggestions based on error type."""
        error_lower = error_msg.lower()
        
        if "authentication" in error_lower:
            return [
                "Try reconnecting your account",
                "Check if the app requires additional permissions",
                "Contact support if the issue persists"
            ]
        elif "rate limit" in error_lower:
            return [
                "Wait a few minutes and try again",
                "Consider breaking large requests into smaller parts",
                "Check the service's usage limits"
            ]
        elif "not found" in error_lower:
            return [
                "Double-check the details in your request",
                "Make sure the resource still exists",
                "Try a different approach or search method"
            ]
        else:
            return [
                "Try rephrasing your request",
                "Check your account permissions",
                "Contact support if the problem continues"
            ]
    
    def _get_action_description(self, action: str) -> str:
        """Get human-friendly action description."""
        action_descriptions = {
            "GMAIL_SEND": "send the email",
            "GMAIL_FETCH": "fetch your emails",
            "GITHUB_CREATE_ISSUE": "create the GitHub issue",
            "SLACK_SEND": "send the Slack message",
            "CALENDAR_CREATE": "schedule the meeting"
        }
        return action_descriptions.get(action, "complete your request")


class ConversationNotFoundException(ChatException):
    """Exception when conversation is not found."""
    
    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        
        super().__init__(
            message=f"Conversation {conversation_id} not found",
            error_code="CONVERSATION_NOT_FOUND",
            user_friendly_message="I couldn't find that conversation. It may have been deleted or you may not have access to it.",
            suggestions=[
                "Check the conversation ID",
                "Start a new conversation",
                "Contact support if you believe this is an error"
            ]
        )


class InteractionExpiredException(ChatException):
    """Exception when interaction has expired."""
    
    def __init__(self, interaction_id: str):
        self.interaction_id = interaction_id
        
        super().__init__(
            message=f"Interaction {interaction_id} has expired",
            error_code="INTERACTION_EXPIRED",
            user_friendly_message="This interaction has expired. Please start a new request.",
            suggestions=[
                "Try making your request again",
                "Authentication links expire after 30 minutes for security",
                "I'll guide you through the process again"
            ]
        )


class ChatErrorHandler:
    """
    Enhanced error handler for chat interface.
    Provides user-friendly error messages and recovery suggestions.
    """
    
    @staticmethod
    def create_error_response(error: Exception, conversation_id: Optional[str] = None) -> ChatResponse:
        """
        Create a user-friendly chat error response.
        
        Args:
            error: The exception that occurred
            conversation_id: Optional conversation ID for context
        
        Returns:
            ChatResponse with user-friendly error message
        """
        try:
            if isinstance(error, ChatException):
                return ChatResponse(
                    type=ResponseType.ERROR,
                    content=error.user_friendly_message,
                    requires_interaction=False,
                    metadata={
                        "error_code": error.error_code,
                        "suggestions": error.suggestions,
                        "conversation_id": conversation_id
                    }
                )
            
            elif isinstance(error, HTTPException):
                return ChatErrorHandler._handle_http_exception(error, conversation_id)
            
            else:
                # Generic error handling
                logger.error(f"Unhandled error in chat: {str(error)}")
                return ChatResponse(
                    type=ResponseType.ERROR,
                    content="I encountered an unexpected issue. Please try again or contact support if the problem persists.",
                    requires_interaction=False,
                    metadata={
                        "error_code": "INTERNAL_ERROR",
                        "suggestions": [
                            "Try rephrasing your request",
                            "Wait a moment and try again",
                            "Contact support if the issue continues"
                        ],
                        "conversation_id": conversation_id
                    }
                )
                
        except Exception as handler_error:
            logger.error(f"Error in chat error handler: {str(handler_error)}")
            # Fallback error response
            return ChatResponse(
                type=ResponseType.ERROR,
                content="I'm experiencing technical difficulties. Please try again.",
                requires_interaction=False
            )
    
    @staticmethod
    def _handle_http_exception(error: HTTPException, conversation_id: Optional[str] = None) -> ChatResponse:
        """Handle HTTP exceptions with user-friendly messages."""
        status_code = error.status_code
        
        if status_code == 400:
            content = "There was an issue with your request. Please check the details and try again."
            suggestions = ["Double-check your input", "Try rephrasing your request"]
        elif status_code == 401:
            content = "Authentication is required. Please connect your account and try again."
            suggestions = ["Complete the authentication process", "Check your account connection"]
        elif status_code == 403:
            content = "You don't have permission to perform this action."
            suggestions = ["Check your account permissions", "Contact support for assistance"]
        elif status_code == 404:
            content = "I couldn't find what you're looking for."
            suggestions = ["Check the details in your request", "Try a different approach"]
        elif status_code == 429:
            content = "Too many requests. Please wait a moment and try again."
            suggestions = ["Wait a few minutes before trying again", "Try breaking large requests into smaller parts"]
        elif status_code >= 500:
            content = "I'm experiencing technical difficulties. Please try again in a moment."
            suggestions = ["Wait a moment and retry", "Contact support if the issue persists"]
        else:
            content = "I encountered an issue processing your request."
            suggestions = ["Try again", "Contact support if the problem continues"]
        
        return ChatResponse(
            type=ResponseType.ERROR,
            content=content,
            requires_interaction=False,
            metadata={
                "error_code": f"HTTP_{status_code}",
                "suggestions": suggestions,
                "conversation_id": conversation_id
            }
        )
    
    @staticmethod
    async def global_chat_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        Global exception handler for chat-related requests.
        
        This handler intercepts chat exceptions and returns user-friendly responses
        while logging technical details for debugging.
        """
        try:
            # Log the technical error
            logger.error(f"Chat exception in {request.url.path}: {str(exc)}", exc_info=True)
            
            # Extract conversation ID from request if available
            conversation_id = None
            if hasattr(request.state, "conversation_id"):
                conversation_id = request.state.conversation_id
            
            # Create user-friendly response
            error_response = ChatErrorHandler.create_error_response(exc, conversation_id)
            
            # Determine appropriate HTTP status code
            if isinstance(exc, ChatException):
                if exc.error_code == "AUTH_REQUIRED":
                    status_code = status.HTTP_401_UNAUTHORIZED
                elif exc.error_code == "INSUFFICIENT_PARAMS":
                    status_code = status.HTTP_400_BAD_REQUEST
                elif exc.error_code in ["CONVERSATION_NOT_FOUND", "INTERACTION_EXPIRED"]:
                    status_code = status.HTTP_404_NOT_FOUND
                else:
                    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            elif isinstance(exc, HTTPException):
                status_code = exc.status_code
            else:
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            
            return JSONResponse(
                status_code=status_code,
                content={
                    "response": error_response.dict(),
                    "conversation_id": conversation_id,
                    "timestamp": "2024-01-01T00:00:00Z"  # Would use actual timestamp
                }
            )
            
        except Exception as handler_error:
            logger.critical(f"Error in global chat exception handler: {str(handler_error)}")
            
            # Final fallback response
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "response": {
                        "type": "error",
                        "content": "I'm experiencing technical difficulties. Please try again.",
                        "requires_interaction": False
                    },
                    "error_code": "HANDLER_ERROR"
                }
            )
    
    @staticmethod
    def log_workflow_error(step: float, step_name: str, error: Exception, 
                          user_id: str, conversation_id: str):
        """
        Log workflow errors with structured information for debugging.
        
        Args:
            step: Workflow step number
            step_name: Name of the workflow step
            error: The exception that occurred
            user_id: ID of the user
            conversation_id: ID of the conversation
        """
        logger.error(
            f"Workflow error at step {step} ({step_name})",
            extra={
                "workflow_step": step,
                "step_name": step_name,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "user_id": user_id,
                "conversation_id": conversation_id
            },
            exc_info=True
        )
    
    @staticmethod
    def get_recovery_suggestions(error_code: str) -> list:
        """
        Get recovery suggestions based on error code.
        
        Args:
            error_code: The error code
        
        Returns:
            List of recovery suggestions
        """
        recovery_suggestions = {
            "AUTH_REQUIRED": [
                "Complete the authentication process",
                "Make sure you're signed in to the required service",
                "Check if additional permissions are needed"
            ],
            "INSUFFICIENT_PARAMS": [
                "Provide more specific details in your request",
                "Include all required information",
                "Try breaking complex requests into steps"
            ],
            "EXECUTION_FAILED": [
                "Try your request again",
                "Check your account permissions",
                "Verify the information in your request"
            ],
            "CONVERSATION_NOT_FOUND": [
                "Start a new conversation",
                "Check the conversation link",
                "Contact support if needed"
            ],
            "INTERACTION_EXPIRED": [
                "Start a new request",
                "Authentication links expire for security",
                "Try the process again from the beginning"
            ]
        }
        
        return recovery_suggestions.get(error_code, [
            "Try again in a moment",
            "Contact support if the issue persists",
            "Check our help documentation"
        ])