import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from fastapi.responses import JSONResponse
from ..domain.models.chat_models import (
    SendMessageRequest, SendMessageResponse, ConversationMessagesResponse,
    InteractionRequest, InteractionResponse, ChatMessage
)
from ..infrastructure.chat_service import ChatService
from ..infrastructure.auth_middleware import UserContext, get_current_user

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


class ChatController:
    """
    FastAPI controller for chat interface endpoints.
    Integrates the 7-step Composio workflow with conversational UI.
    """
    
    def __init__(self, chat_service: ChatService):
        self.chat_service = chat_service
        logger.info("ChatController initialized")


# Dependency injection for controller
async def get_chat_controller() -> ChatController:
    """Dependency injection for chat controller."""
    # This will be injected by the main app
    pass


@router.post("/chat/messages", response_model=SendMessageResponse)
async def send_message(
    request: SendMessageRequest,
    background_tasks: BackgroundTasks,
    user: UserContext = Depends(get_current_user),
    controller: ChatController = Depends(get_chat_controller)
) -> SendMessageResponse:
    """
    Send a chat message and execute workflow conversationally.
    
    This endpoint processes user messages through the complete 7-step pipeline:
    1. Parse query → 2. Select app → 2.5. Check auth → 3. Get actions → 
    4. Select action → 5. Get schema → 6. Normalize params → 7. Execute
    
    The workflow happens conversationally with natural chat responses.
    """
    try:
        logger.info(f"Processing chat message from user {user.user_id}: {request.message[:100]}...")
        
        # Process message through chat service
        result = await controller.chat_service.send_message(
            user_id=user.user_id,
            message=request.message,
            conversation_id=request.conversation_id
        )
        
        # Add background cleanup task
        background_tasks.add_task(
            controller.chat_service.cleanup_expired_sessions
        )
        
        # Convert to response model
        response = SendMessageResponse(
            conversation_id=result["conversation_id"],
            message_id=result["message_id"],
            response=result["response"]
        )
        
        logger.info(f"Chat message processed successfully for user {user.user_id}")
        return response
        
    except ValueError as e:
        logger.warning(f"Invalid request from user {user.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error processing chat message: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process your message. Please try again."
        )


@router.get("/chat/conversations/{conversation_id}/messages", response_model=ConversationMessagesResponse)
async def get_conversation_messages(
    conversation_id: str,
    limit: int = 50,
    user: UserContext = Depends(get_current_user),
    controller: ChatController = Depends(get_chat_controller)
) -> ConversationMessagesResponse:
    """
    Get messages from a conversation.
    
    Retrieves the chat history for a specific conversation, including
    user messages, system responses, and workflow status updates.
    """
    try:
        logger.info(f"Fetching messages for conversation {conversation_id} (user: {user.user_id})")
        
        # Validate limit parameter
        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Limit must be between 1 and 100"
            )
        
        # Get messages from chat service
        result = controller.chat_service.get_conversation_messages(
            user_id=user.user_id,
            conversation_id=conversation_id,
            limit=limit
        )
        
        # Convert to response model
        response = ConversationMessagesResponse(
            conversation_id=result["conversation_id"],
            messages=result["messages"],
            total_messages=result["total_messages"],
            has_active_workflow=result["has_active_workflow"]
        )
        
        logger.info(f"Retrieved {len(response.messages)} messages for conversation {conversation_id}")
        return response
        
    except ValueError as e:
        logger.warning(f"Invalid conversation request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error retrieving conversation messages: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversation messages"
        )


@router.post("/chat/interactions/{interaction_id}/respond", response_model=InteractionResponse)
async def respond_to_interaction(
    interaction_id: str,
    request: InteractionRequest,
    user: UserContext = Depends(get_current_user),
    controller: ChatController = Depends(get_chat_controller)
) -> InteractionResponse:
    """
    Respond to a system interaction (OAuth completion, parameter input, etc.).
    
    This endpoint handles user responses to system requests for:
    - OAuth authentication completion
    - Additional parameter clarification
    - Confirmation requests
    - Operation cancellation
    """
    try:
        logger.info(f"Processing interaction response {interaction_id} from user {user.user_id}")
        
        # Process interaction response through chat service
        result = await controller.chat_service.handle_interaction_response(
            interaction_id=interaction_id,
            response_type=request.response_type,
            response_data=request.data
        )
        
        if not result.get("success", False):
            error_msg = result.get("error", "Failed to process interaction response")
            logger.warning(f"Interaction response failed: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        
        # Convert to response model
        response = InteractionResponse(
            interaction_id=interaction_id,
            response_type=request.response_type,
            success=result["success"],
            continue_conversation=result.get("continue_conversation", True),
            next_message=result.get("next_message"),
            error=result.get("error")
        )
        
        logger.info(f"Interaction response processed successfully: {interaction_id}")
        return response
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid interaction response: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error processing interaction response: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process interaction response"
        )


@router.get("/chat/conversations")
async def list_user_conversations(
    limit: int = 20,
    user: UserContext = Depends(get_current_user),
    controller: ChatController = Depends(get_chat_controller)
) -> Dict[str, Any]:
    """
    List user's chat conversations.
    
    Returns a list of conversations with basic metadata like title,
    last message timestamp, and active workflow status.
    """
    try:
        logger.info(f"Listing conversations for user {user.user_id}")
        
        # Validate limit parameter
        if limit < 1 or limit > 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Limit must be between 1 and 50"
            )
        
        # Get user conversations from chat service
        conversations = []
        for conversation in controller.chat_service.conversations.values():
            if conversation.user_id == user.user_id and conversation.is_active:
                conversations.append({
                    "id": conversation.id,
                    "title": conversation.title,
                    "created_at": conversation.created_at.isoformat(),
                    "updated_at": conversation.updated_at.isoformat(),
                    "message_count": len(conversation.messages),
                    "has_active_workflow": conversation.get_active_workflow_session() is not None
                })
        
        # Sort by updated time (most recent first) and limit
        conversations.sort(key=lambda x: x["updated_at"], reverse=True)
        conversations = conversations[:limit]
        
        return {
            "conversations": conversations,
            "total_conversations": len(conversations),
            "user_id": user.user_id
        }
        
    except Exception as e:
        logger.error(f"Error listing conversations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversations"
        )


@router.delete("/chat/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: UserContext = Depends(get_current_user),
    controller: ChatController = Depends(get_chat_controller)
) -> Dict[str, Any]:
    """
    Delete a chat conversation.
    
    Marks a conversation as inactive and cancels any active workflows.
    The conversation data is retained for audit purposes but hidden from the user.
    """
    try:
        logger.info(f"Deleting conversation {conversation_id} for user {user.user_id}")
        
        # Check if conversation exists and belongs to user
        if conversation_id not in controller.chat_service.conversations:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation {conversation_id} not found"
            )
        
        conversation = controller.chat_service.conversations[conversation_id]
        if conversation.user_id != user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this conversation"
            )
        
        # Mark conversation as inactive
        conversation.is_active = False
        conversation.updated_at = datetime.utcnow()
        
        # Cancel any active workflow sessions
        active_session = conversation.get_active_workflow_session()
        if active_session:
            active_session.status = WorkflowStatus.CANCELLED
            active_session.updated_at = datetime.utcnow()
            logger.info(f"Cancelled active workflow session: {active_session.session_id}")
        
        return {
            "success": True,
            "message": f"Conversation {conversation_id} deleted successfully",
            "conversation_id": conversation_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete conversation"
        )


@router.get("/chat/health")
async def chat_health_check(
    controller: ChatController = Depends(get_chat_controller)
) -> Dict[str, Any]:
    """
    Health check for chat service functionality.
    
    Returns status information about the chat service, including
    active conversations, workflow sessions, and service health.
    """
    try:
        health_info = await controller.chat_service.health_check()
        
        return {
            "service": "chat_controller",
            "status": health_info.get("status", "unknown"),
            "chat_service_health": health_info,
            "endpoints": {
                "send_message": "operational",
                "get_messages": "operational", 
                "handle_interactions": "operational",
                "list_conversations": "operational"
            },
            "checked_at": health_info.get("checked_at")
        }
        
    except Exception as e:
        logger.error(f"Chat health check failed: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "service": "chat_controller",
                "status": "unhealthy",
                "error": str(e),
                "checked_at": datetime.utcnow().isoformat()
            }
        )


# Additional utility endpoints

@router.get("/chat/scenarios")
async def get_supported_scenarios() -> Dict[str, Any]:
    """
    Get supported scenarios with sample chat queries.
    
    Returns information about what types of tasks the chat interface
    can handle, with example queries for each scenario.
    """
    scenarios = {
        "email": {
            "name": "Email Management",
            "description": "Send, read, and manage emails through Gmail",
            "sample_queries": [
                "Send an email to john@example.com with subject 'Meeting Tomorrow'",
                "Check my unread emails from last week",
                "Reply to the email from Sarah about the project"
            ],
            "required_auth": ["Gmail"]
        },
        "meetings": {
            "name": "Meeting Scheduling", 
            "description": "Schedule meetings and calendar events",
            "sample_queries": [
                "Schedule a team meeting for tomorrow at 2 PM",
                "Create a Zoom meeting for Friday afternoon",
                "Book a conference room for next Tuesday"
            ],
            "required_auth": ["Google Calendar", "Zoom"]
        },
        "code": {
            "name": "Code Management",
            "description": "Create issues, manage repositories on GitHub",
            "sample_queries": [
                "Create an issue in my project repo about the login bug",
                "List my recent GitHub repositories",
                "Get information about pull request #42"
            ],
            "required_auth": ["GitHub"]
        },
        "communication": {
            "name": "Team Communication",
            "description": "Send messages and manage team communication",
            "sample_queries": [
                "Send a message to the dev channel about the deployment",
                "Post an update about the project status",
                "Share this link with the marketing team"
            ],
            "required_auth": ["Slack", "Twitter"]
        }
    }
    
    return {
        "supported_scenarios": scenarios,
        "total_scenarios": len(scenarios),
        "getting_started": [
            "Just type what you want to do in natural language",
            "I'll guide you through any required authentication",
            "Ask for help or examples anytime with 'What can you help me with?'"
        ]
    }


# Import required dependencies for delete endpoint
from datetime import datetime
from ..domain.models.chat_models import WorkflowStatus