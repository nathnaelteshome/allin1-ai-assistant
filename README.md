# Allin1 AI Assistant

A web-based AI assistant that autonomously handles user queries by decomposing them into subtasks, executing via API functions, and aggregating results across six key scenarios: flight booking, email, meeting scheduling, trip planning, food ordering, and X (Twitter) posting.

## Features

- **Query Parsing**: Uses LLM to decompose natural language queries into executable subtasks
- **Pipedream-First Integration**: All external API calls go through Pipedream workflows for security and reliability
- **Task Execution**: Calls external APIs (Skyscanner, SendGrid, Google Calendar, etc.) via Pipedream workflows
- **Result Aggregation**: Combines API outputs to deliver comprehensive results
- **Retry Logic**: Exponential backoff retry strategy for failed API calls
- **Comprehensive Logging**: Firebase-based logging for monitoring and debugging
- **Gamification**: Award badges and points for task completion
- **Social Sharing**: Share task outcomes to X (Twitter) or email

## Supported Scenarios

All scenarios use **Pipedream workflows** for external API integration:

1. **Flight Booking** - Search and book flights via Skyscanner (through Pipedream)
2. **Email Sending** - Draft and send emails via SendGrid (through Pipedream)
3. **Meeting Scheduling** - Create calendar events via Google Calendar (through Pipedream)
4. **Trip Planning** - Plan complete trips with flights, hotels, and activities (through Pipedream)
5. **Food Ordering** - Order food via DoorDash (through Pipedream)
6. **X (Twitter) Posting** - Create and post content to X (through Pipedream)

## Project Structure

```
src/
├── app.py                          # Main Flask application
├── controllers/
│   └── query_controller.py         # Handles API requests
├── domain/
│   └── models/
│       └── llm_selection.py        # Task and response models
├── infrastructure/
│   ├── apis/                       # External API integrations
│   └── llm/                        # LLM implementations
│       ├── llm_interface.py        # Base LLM interface
│       ├── chatgpt_llm.py          # ChatGPT implementation
│       ├── claude_llm.py           # Claude implementation
│       ├── gemini_llm.py           # Gemini implementation
│       └── llm_list.py             # LLM selection logic
└── use_cases/
    └── route_query.py              # Query routing logic
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
# Edit .env with your API keys
```

## Environment Variables

Create a `.env` file with the following variables:

```env
# Flask Configuration
SECRET_KEY=your-secret-key
DEBUG=True
PORT=5000

# Firebase Configuration
FIREBASE_SERVICE_ACCOUNT_KEY_PATH=./firebase-service-account-key.json
FIREBASE_PROJECT_ID=allin1-ai-assistant-dev

# Pipedream Configuration (ALL external APIs go through Pipedream)
PIPEDREAM_API_KEY=your-pipedream-api-key
PIPEDREAM_FLIGHT_SEARCH_URL=https://your-flight-trigger-id.m.pipedream.net
PIPEDREAM_EMAIL_SEND_URL=https://your-email-trigger-id.m.pipedream.net
PIPEDREAM_EMAIL_DRAFT_URL=https://your-email-draft-trigger-id.m.pipedream.net

# Retry Configuration
MAX_RETRIES=3
INITIAL_RETRY_DELAY=1
MAX_RETRY_DELAY=60
```

**Important**: External API keys (Skyscanner, SendGrid, etc.) are stored securely in Pipedream workflows, not in your application environment. This ensures better security and centralized API management.

## Usage

1. Start the Flask application:
```bash
python src/app.py
```

2. The API will be available at `http://localhost:5000`

3. Send a POST request to `/tasks` with a query:
```bash
curl -X POST http://localhost:5000/tasks \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user123", "query": "Book a flight to New York City next week"}'
```


### Code Style
```bash
flake8 src/
black src/
```

## Architecture

The application follows a clean architecture pattern:

1. **Controllers** handle HTTP requests and responses
2. **Use Cases** contain business logic for query processing
3. **Domain Models** define data structures and business rules
4. **Infrastructure** handles external API calls and LLM integrations

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

