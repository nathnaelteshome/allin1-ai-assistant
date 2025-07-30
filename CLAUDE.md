# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Allin1 AI Assistant is a FastAPI-based web application that autonomously handles user queries by decomposing them into subtasks, executing via API functions, and aggregating results across six key scenarios: flight booking, email sending, meeting scheduling, trip planning, food ordering, and X (Twitter) posting.

## Architecture

The project follows **Clean Architecture** principles with clear separation of concerns:

- **Controllers** (`src/controllers/`) - Handle HTTP requests and responses
- **Use Cases** (`src/use_cases/`) - Business logic for query processing
- **Domain Models** (`src/domain/models/`) - Data structures and business rules
- **Infrastructure** (`src/infrastructure/`) - External API calls and LLM integrations

## Key Components

### LLM Integration
- **Multi-LLM Support**: ChatGPT, Claude, and Gemini implementations
- **Base Interface**: `src/infrastructure/llm/llm_interface.py` defines the contract
- **Query Processing**: LLMs parse natural language queries and build task trees

### Task Execution Flow
1. User query → LLM parses → Task tree creation
2. Task tree → API function mapping → External API calls
3. API results → Result aggregation → User response

### Supported Scenarios
Each scenario has predefined task trees with specific API integrations:
- Flight Booking (Skyscanner + Stripe)
- Email Sending (SendGrid)
- Meeting Scheduling (Google Calendar + Zoom)
- Trip Planning (Skyscanner + Booking.com + TripAdvisor)
- Food Ordering (DoorDash + Stripe)
- X Posting (Twitter API)

## Development Commands

### Environment Setup
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac: venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Running the Application
```bash
python -m uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload
# Application runs on http://localhost:8000
```

### Code Quality
```bash
flake8 src/          # Linting
black src/           # Code formatting
```

### Project Scaffolding
```bash
python templates.py  # Regenerate project structure (use with caution)
```


## Environment Variables

Required environment variables for full functionality:
```env
SECRET_KEY=your-secret-key
DEBUG=True
PORT=5000

# Firebase Configuration
FIREBASE_SERVICE_ACCOUNT_KEY_PATH=./firebase-service-account-key.json
FIREBASE_PROJECT_ID=allin1-ai-assistant-dev

# External API Configuration
# Add your external API keys here (e.g., SendGrid, Skyscanner, etc.)

# Retry Configuration
MAX_RETRIES=3
INITIAL_RETRY_DELAY=1
MAX_RETRY_DELAY=60
```

## Current Implementation Status

**Note**: This project is in early development phase. Most implementation files are empty scaffolding created by `templates.py`. Key areas requiring implementation:

1. **FastAPI Application** (`src/app.py`) - Main application setup
2. **Query Controller** (`src/controllers/query_controller.py`) - Request handling
3. **LLM Implementations** (`src/infrastructure/llm/`) - Actual LLM integrations
4. **API Clients** (`src/infrastructure/apis/`) - External service integrations
5. **Domain Models** (`src/domain/models/`) - Data structures
6. **Use Cases** (`src/use_cases/`) - Business logic

## Development Guidelines

### External API Integration
Make direct API calls to external services. Store API keys securely in environment variables.

```python
# ✅ Correct - Direct API calls
import sendgrid
client = sendgrid.SendGridAPIClient(api_key=os.getenv('SENDGRID_API_KEY'))
response = client.mail.send.post(request_body=mail.get())
```

### Adding New Scenarios
1. Obtain API credentials for the external service
2. Add API keys to environment variables
3. Update LLM implementations to recognize new task types
4. Define task tree structure for the scenario
5. Implement function class in `src/infrastructure/functions/`
6. Add function mappings in query router

### LLM Implementation Pattern
Each LLM implementation should provide:
- `parse_query()` - Extract task type and parameters
- `build_task_tree()` - Create execution plan
- `generate_questions()` - Handle missing parameters
- `validate_response()` - Ensure response format

### Error Handling
- External API failures should be gracefully handled
- LLM timeouts should have fallback mechanisms
- User-facing errors should be informative but not expose internal details

## Testing Strategy

While no tests exist yet, the architecture supports:
- Unit tests for business logic in use cases
- Integration tests for API clients
- End-to-end tests for complete query processing flows
- Mock external APIs for consistent testing

## Interaction Guidelines

### Claude Interaction Principles
- After a request is made, if the requirements aren't clear, ask clarifying questions before guessing anything

## Development Workflow

### Daily Reporting
- Everyday create a daily report markdown file and update it as we work on things day by day

## Integration Guidelines

### External API Integration
- Follow each API's official documentation for integration
- IMPORTANT: When integrating, always:
  * Read the official API documentation thoroughly
  * Use official SDKs when available
  * Handle rate limiting and error responses appropriately

## Project Insights

- The project is about creating AI agents to do user tasks
- We use Composio for app integration and executing actions

## Composio Integration Notes

- When integrating Composio, detailed research is required
- Follow the guide at docs/Programmatic Integration of Composio with FastAPI for Email-to-X Workflow.md

## Testing Guidelines

- When you test something dont use mock api or url use the real url and api serach the web for it

## Code Quality Guidelines

- Always follow best code principles in this project including the SOLID and DRY principles
- Prioritize writing clean, maintainable, and well-structured code