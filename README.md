# Allin1 AI Assistant

A web-based AI assistant that autonomously handles user queries by decomposing them into subtasks, executing via API functions, and aggregating results across six key scenarios: flight booking, email, meeting scheduling, trip planning, food ordering, and X (Twitter) posting.

## Features

- **Query Parsing**: Uses LLM to decompose natural language queries into executable subtasks
- **Task Execution**: Calls external APIs (Skyscanner, SendGrid, Google Calendar, etc.) with specific payloads
- **Result Aggregation**: Combines API outputs to deliver comprehensive results
- **Gamification**: Award badges and points for task completion
- **Social Sharing**: Share task outcomes to X (Twitter) or email
- **Multi-LLM Support**: Supports ChatGPT, Claude, and Gemini for query processing

## Supported Scenarios

1. **Flight Booking** - Search and book flights via Skyscanner
2. **Email Sending** - Draft and send emails via SendGrid
3. **Meeting Scheduling** - Create calendar events via Google Calendar
4. **Trip Planning** - Plan complete trips with flights, hotels, and activities
5. **Food Ordering** - Order food via DoorDash
6. **X (Twitter) Posting** - Create and post content to X

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

# LLM API Keys
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
GOOGLE_API_KEY=your-google-key


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

