# Allin1 AI Assistant

A production-ready FastAPI-based conversational AI assistant that autonomously handles user queries through a chat interface. Uses advanced workflow orchestration with Composio integration to execute tasks across multiple external applications while providing seamless OAuth authentication and real-time interaction.

## Features

### Core Capabilities

- **Conversational AI Interface**: Natural language chat API for seamless user interaction
- **7-Step Workflow Orchestration**: Automated task execution with intelligent app selection
- **Composio Integration**: Connect to 200+ applications with standardized authentication
- **JWT Authentication System**: Secure user authentication with role-based access control
- **Real-time OAuth Flow**: Seamless authentication for external services
- **Interactive Parameter Collection**: Smart clarification requests for missing information

### Technical Features

- **FastAPI Architecture**: High-performance async API with automatic OpenAPI documentation
- **Clean Architecture**: SOLID principles with clear separation of concerns
- **Advanced Error Handling**: User-friendly error messages with recovery suggestions
- **Rate Limiting**: 60 requests/minute per user with middleware protection
- **Comprehensive Logging**: Structured logging with user context and correlation IDs
- **Background Task Management**: Automatic cleanup of expired sessions and workflows

## Supported Scenarios

The assistant can handle diverse tasks through 200+ Composio-integrated applications:

### Primary Use Cases

- **Email Management** - Send, draft, and manage emails across providers (Gmail, Outlook, etc.)
- **Calendar & Scheduling** - Create events, schedule meetings, manage availability
- **Communication** - Post to social media, send messages, manage notifications
- **File Management** - Upload, organize, and share files across cloud platforms
- **Task Management** - Create, assign, and track tasks in project management tools
- **Document Creation** - Generate and edit documents, presentations, and spreadsheets

### Workflow Intelligence

- **Automatic App Selection**: AI chooses the best application for each task
- **Context Awareness**: Maintains conversation context across multi-step workflows
- **Error Recovery**: Graceful handling of failures with user-friendly explanations
- **Parameter Optimization**: Smart parameter collection with validation and defaults

## Project Structure

```
src/
├── app.py                              # Main FastAPI application with lifespan management
├── controllers/
│   ├── chat_controller.py              # Chat API endpoints
│   ├── query_controller.py             # Legacy query handling
│   └── auth_controller.py              # Authentication endpoints
├── domain/
│   └── models/
│       ├── chat_models.py              # Chat conversation and workflow models
│       ├── llm_selection.py            # Task and response models
│       └── auth_models.py              # Authentication data models
├── infrastructure/
│   ├── chat_service.py                 # Core chat workflow orchestration
│   ├── jwt_auth_service.py             # JWT token management
│   ├── auth_middleware.py              # Authentication middleware
│   ├── chat_error_handler.py           # User-friendly error handling
│   ├── composio/                       # Composio integration services
│   └── llm/                           # LLM implementations
│       ├── llm_interface.py            # Base LLM interface
│       ├── chatgpt_llm.py              # ChatGPT implementation
│       ├── claude_llm.py               # Claude implementation
│       └── gemini_llm.py               # Gemini implementation
└── use_cases/
    └── route_query.py                  # Query routing logic
```

## Installation

1. Clone the repository:

```bash
git clone https://github.com/yourusername/allin1-ai-assistant.git
cd allin1-ai-assistant
```

2. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Set up environment variables:

```bash
cp .env.example .env
# Edit .env with your API keys and configuration
```

## Environment Variables

Create a `.env` file with the following variables:

```env
# FastAPI Configuration
SECRET_KEY=your-jwt-secret-key
DEBUG=True
PORT=8000

# JWT Authentication
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Composio Integration
COMPOSIO_API_KEY=your-composio-api-key

# LLM Configuration
GOOGLE_API_KEY=your-gemini-api-key
OPENAI_API_KEY=your-openai-api-key

# Firebase Configuration (Optional - for enhanced logging)
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_SERVICE_ACCOUNT_KEY_PATH=./firebase-service-account-key.json

# Application Settings
MAX_RETRIES=3
INITIAL_RETRY_DELAY=1
MAX_RETRY_DELAY=60
RATE_LIMIT_PER_MINUTE=60
```

**Security Note**: All external application authentication is handled securely through Composio's OAuth flow. No need to store individual service API keys in your environment.

## Usage

### Starting the Application

1. Run the FastAPI server:

```bash
python -m uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload
```

2. The API will be available at `http://localhost:8000`
3. Interactive API docs at `http://localhost:8000/docs`
4. Alternative docs at `http://localhost:8000/redoc`

### Chat API Examples

**Send a Chat Message:**

```bash
curl -X POST http://localhost:8000/api/v1/chat/messages \
  -H "Authorization: Bearer <your-jwt-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Send an email to john@example.com saying hello",
    "conversation_id": "optional-existing-conversation-id"
  }'
```

**Get Conversation History:**

```bash
curl -X GET http://localhost:8000/api/v1/chat/conversations/{conversation_id}/messages \
  -H "Authorization: Bearer <your-jwt-token>"
```

**Handle OAuth Interactions:**

```bash
curl -X POST http://localhost:8000/api/v1/chat/interactions/{interaction_id}/respond \
  -H "Content-Type: application/json" \
  -d '{
    "response": "user_provided_value",
    "parameters": {"key": "value"}
  }'
```

### Frontend Integration Example

```javascript
// Send a message
const response = await fetch("/api/v1/chat/messages", {
  method: "POST",
  headers: {
    Authorization: "Bearer " + token,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    message: "Send an email to john@example.com saying hello",
  }),
});

const result = await response.json();

// Handle OAuth requirement
if (
  result.response.requires_interaction &&
  result.response.interaction.type === "oauth"
) {
  window.open(result.response.interaction.oauth_url);
}
```

### Development Commands

**Code Quality:**
```bash
flake8 src/          # Linting
black src/           # Code formatting
python -m uvicorn src.app:app --reload  # Development server
```

## Architecture

The application follows **Clean Architecture** principles with modern FastAPI patterns:

### 7-Step Workflow Process
1. **App Discovery**: Fetch available Composio applications (transparent to user)
2. **App Selection**: LLM selects the most appropriate application for the task
2.5. **Authentication Check**: Verify OAuth status → Initiate OAuth flow if needed
3. **Action Discovery**: Fetch available actions for the selected application
4. **Action Selection**: LLM chooses the best action for the user's intent
5. **Schema Validation**: Retrieve and validate action parameter schema
6. **Parameter Collection**: Gather required parameters → Ask user for clarification if needed
7. **Execution**: Execute the action and return results

### Component Architecture
- **Controllers**: Handle HTTP requests/responses with JWT authentication
- **Chat Service**: Orchestrates the 7-step workflow conversationally
- **Domain Models**: Define chat conversations, workflow sessions, and data structures
- **Infrastructure**: Composio integration, LLM services, and external API management
- **Middleware**: Authentication, rate limiting, and error handling

### Key Design Patterns
- **Dependency Injection**: Services are injected for testability and modularity
- **Event-Driven**: Workflow steps trigger based on user interactions and OAuth callbacks
- **State Management**: Conversation context maintains workflow state across interactions
- **Error Recovery**: Graceful degradation with user-friendly error messages

## API Documentation

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/chat/messages` | Send a chat message and receive AI response |
| `GET` | `/api/v1/chat/conversations/{id}/messages` | Get conversation message history |
| `POST` | `/api/v1/chat/interactions/{id}/respond` | Respond to interaction requests (OAuth, parameters) |
| `GET` | `/api/v1/auth/callback` | Handle OAuth callbacks from external services |
| `POST` | `/api/v1/auth/token` | Generate JWT access tokens |

### Authentication Flow
1. **User Registration**: Create account with username/password
2. **JWT Token**: Obtain access token for API authentication
3. **Chat Interaction**: Send messages with Authorization header
4. **OAuth Flow**: Automatic handling of external service authentication

## Performance & Security

### Security Features
- **JWT Authentication**: Access and refresh tokens with expiration
- **Rate Limiting**: 60 requests/minute per user
- **OAuth Integration**: Secure external service authentication
- **Input Validation**: Comprehensive request validation
- **Error Sanitization**: No sensitive data in error responses

### Performance Optimizations
- **Async Operations**: Non-blocking I/O throughout the application
- **Background Tasks**: Automatic cleanup of expired sessions
- **Caching**: Conversation state management
- **Connection Pooling**: Efficient external API communication

## Contributing

### Development Setup
1. Fork the repository
2. Create a feature branch
3. Set up development environment with all required API keys
4. Follow the coding standards (flake8, black)
5. Add comprehensive tests
6. Submit a pull request

### Code Standards
- Follow SOLID and DRY principles
- Use type hints throughout
- Implement comprehensive error handling
- Add docstrings for all public methods
- Write unit and integration tests

## License

This project is licensed under the MIT License - see the LICENSE file for details.
