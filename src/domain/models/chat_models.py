import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from enum import Enum
from pydantic import BaseModel, Field
from dataclasses import dataclass, field


class MessageType(str, Enum):
    """Types of chat messages."""
    USER = "user"
    SYSTEM = "system"
    ERROR = "error"
    SUCCESS = "success"


class InteractionType(str, Enum):
    """Types of user interactions required."""
    OAUTH = "oauth"
    CLARIFICATION = "clarification"
    CONFIRMATION = "confirmation"
    PARAMETER_INPUT = "parameter_input"


class WorkflowStatus(str, Enum):
    """Status of workflow execution."""
    PENDING = "pending"
    PROCESSING = "processing"
    WAITING_FOR_AUTH = "waiting_for_auth"
    WAITING_FOR_INPUT = "waiting_for_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResponseType(str, Enum):
    """Types of chat responses."""
    TEXT = "text"
    INTERACTION = "interaction"
    SUCCESS = "success"
    ERROR = "error"
    WORKFLOW_UPDATE = "workflow_update"


@dataclass
class WorkflowStepResult:
    """Result of a single workflow step."""
    step_number: float
    step_name: str
    status: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "step_name": self.step_name,
            "status": self.status,
            "data": self.data,
            "error": self.error,
            "timestamp": self.timestamp.isoformat()
        }


class InteractionData(BaseModel):
    """Data required for user interaction."""
    type: InteractionType
    oauth_url: Optional[str] = None
    app_name: Optional[str] = None
    missing_parameters: Optional[List[str]] = None
    suggestions: Optional[str] = None
    confirmation_message: Optional[str] = None
    interaction_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    expires_at: Optional[datetime] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ChatMessage(BaseModel):
    """Individual chat message model."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str
    type: MessageType
    content: str
    user_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Workflow-related fields
    workflow_step: Optional[float] = None
    workflow_status: Optional[WorkflowStatus] = None
    interaction: Optional[InteractionData] = None
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary for storage/serialization."""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "type": self.type.value,
            "content": self.content,
            "user_id": self.user_id,
            "timestamp": self.timestamp.isoformat(),
            "workflow_step": self.workflow_step,
            "workflow_status": self.workflow_status.value if self.workflow_status else None,
            "interaction": self.interaction.dict() if self.interaction else None,
            "metadata": self.metadata
        }


class WorkflowSession(BaseModel):
    """Workflow execution session within a conversation."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str
    user_id: str
    original_query: str
    current_step: float = 1.0
    status: WorkflowStatus = WorkflowStatus.PENDING
    
    # Step results tracking
    step_results: Dict[str, WorkflowStepResult] = Field(default_factory=dict)
    
    # Current workflow state
    selected_app: Optional[str] = None
    selected_action: Optional[str] = None
    normalized_parameters: Dict[str, Any] = Field(default_factory=dict)
    execution_result: Optional[Dict[str, Any]] = None
    
    # Interaction tracking
    pending_interaction: Optional[InteractionData] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
    def add_step_result(self, step_number: float, step_name: str, status: str, 
                       data: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
        """Add a step result to the workflow session."""
        self.step_results[f"step_{step_number}"] = WorkflowStepResult(
            step_number=step_number,
            step_name=step_name,
            status=status,
            data=data,
            error=error
        )
        self.current_step = step_number
        self.updated_at = datetime.utcnow()
    
    def mark_completed(self, final_result: Optional[Dict[str, Any]] = None):
        """Mark workflow session as completed."""
        self.status = WorkflowStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        if final_result:
            self.execution_result = final_result
    
    def mark_failed(self, error: str):
        """Mark workflow session as failed."""
        self.status = WorkflowStatus.FAILED
        self.updated_at = datetime.utcnow()
        self.metadata["error"] = error
    
    def set_pending_interaction(self, interaction: InteractionData):
        """Set a pending user interaction."""
        self.pending_interaction = interaction
        if interaction.type == InteractionType.OAUTH:
            self.status = WorkflowStatus.WAITING_FOR_AUTH
        else:
            self.status = WorkflowStatus.WAITING_FOR_INPUT
        self.updated_at = datetime.utcnow()
    
    def clear_pending_interaction(self):
        """Clear pending interaction and resume processing."""
        self.pending_interaction = None
        self.status = WorkflowStatus.PROCESSING
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert workflow session to dictionary."""
        return {
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "original_query": self.original_query,
            "current_step": self.current_step,
            "status": self.status.value,
            "step_results": {k: v.to_dict() for k, v in self.step_results.items()},
            "selected_app": self.selected_app,
            "selected_action": self.selected_action,
            "normalized_parameters": self.normalized_parameters,
            "execution_result": self.execution_result,
            "pending_interaction": self.pending_interaction.dict() if self.pending_interaction else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata
        }


class ChatConversation(BaseModel):
    """Chat conversation model containing messages and workflow sessions."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Messages in this conversation
    messages: List[ChatMessage] = Field(default_factory=list)
    
    # Active workflow sessions
    workflow_sessions: Dict[str, WorkflowSession] = Field(default_factory=dict)
    
    # Conversation metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
    def add_message(self, message: ChatMessage):
        """Add a message to the conversation."""
        message.conversation_id = self.id
        self.messages.append(message)
        self.updated_at = datetime.utcnow()
        
        # Auto-generate title from first user message
        if not self.title and message.type == MessageType.USER and len(self.messages) == 1:
            self.title = message.content[:50] + "..." if len(message.content) > 50 else message.content
    
    def add_workflow_session(self, session: WorkflowSession):
        """Add a workflow session to the conversation."""
        session.conversation_id = self.id
        self.workflow_sessions[session.session_id] = session
        self.updated_at = datetime.utcnow()
    
    def get_active_workflow_session(self) -> Optional[WorkflowSession]:
        """Get the currently active workflow session."""
        for session in self.workflow_sessions.values():
            if session.status in [WorkflowStatus.PROCESSING, WorkflowStatus.WAITING_FOR_AUTH, WorkflowStatus.WAITING_FOR_INPUT]:
                return session
        return None
    
    def get_latest_messages(self, limit: int = 50) -> List[ChatMessage]:
        """Get the latest messages in chronological order."""
        return sorted(self.messages, key=lambda m: m.timestamp)[-limit:]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert conversation to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "messages": [msg.to_dict() for msg in self.messages],
            "workflow_sessions": {k: v.to_dict() for k, v in self.workflow_sessions.items()},
            "metadata": self.metadata,
            "is_active": self.is_active
        }


# Request/Response Models for API

class ChatResponse(BaseModel):
    """Chat response model for API responses."""
    type: ResponseType
    content: str
    requires_interaction: bool = False
    interaction: Optional[InteractionData] = None
    workflow_status: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SendMessageRequest(BaseModel):
    """Request model for sending chat messages."""
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[str] = None
    
    class Config:
        schema_extra = {
            "example": {
                "message": "Send an email to john@example.com saying hello",
                "conversation_id": "optional-existing-conversation-id"
            }
        }


class SendMessageResponse(BaseModel):
    """Response model for send message endpoint."""
    conversation_id: str
    message_id: str
    response: ChatResponse
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ConversationMessagesResponse(BaseModel):
    """Response model for conversation messages endpoint."""
    conversation_id: str
    messages: List[ChatMessage]
    total_messages: int
    has_active_workflow: bool
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class InteractionResponse(BaseModel):
    """Response model for interaction endpoints."""
    interaction_id: str
    response_type: str
    success: bool
    continue_conversation: bool = True
    next_message: Optional[ChatResponse] = None
    error: Optional[str] = None


class InteractionRequest(BaseModel):
    """Request model for responding to interactions."""
    response_type: str = Field(..., regex="^(oauth_completed|parameters_provided|confirmed|cancelled)$")
    data: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        schema_extra = {
            "example": {
                "response_type": "oauth_completed",
                "data": {
                    "auth_code": "oauth-authorization-code",
                    "state": "oauth-state-parameter"
                }
            }
        }