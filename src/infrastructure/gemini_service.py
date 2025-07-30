import os
import json
import asyncio
from typing import Dict, List, Any, Optional, Union
import logging
from datetime import datetime
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

logger = logging.getLogger(__name__)


class GeminiService:
    """
    Gemini LLM integration service for natural language processing tasks.
    Handles query understanding, task decomposition, and parameter generation.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('GOOGLE_API_KEY')
        self.model_name = os.getenv('GEMINI_MODEL', 'gemini-pro')
        self.temperature = float(os.getenv('GEMINI_TEMPERATURE', '0.7'))
        
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is required for Gemini service")
        
        # Configure Gemini
        genai.configure(api_key=self.api_key)
        
        # Initialize model
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config=genai.types.GenerationConfig(
                temperature=self.temperature,
                top_p=0.8,
                top_k=40,
                max_output_tokens=4096,
            ),
            safety_settings={
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            }
        )
        
        logger.info(f"GeminiService initialized with model: {self.model_name}")

    async def parse_user_query(self, query: str) -> Dict[str, Any]:
        """
        Parse user query to extract intent, scenario, and parameters.
        
        Args:
            query: Natural language user query
            
        Returns:
            Parsed query information including scenario and parameters
        """
        try:
            system_prompt = """
You are an AI assistant that analyzes user queries to determine their intent and extract relevant parameters.

Analyze the user's query and respond with a JSON object containing:
1. scenario: One of [email, flight_booking, meeting_scheduling, trip_planning, food_ordering, x_posting]
2. intent: Brief description of what the user wants to do
3. confidence: Confidence score between 0.0 and 1.0
4. parameters: Extracted parameters relevant to the scenario
5. missing_parameters: List of required parameters that are missing
6. clarification_needed: Boolean indicating if clarification is needed

Available scenarios:
- email: Reading, sending, or managing emails
- flight_booking: Searching and booking flights
- meeting_scheduling: Creating calendar events and meetings
- trip_planning: Planning trips with flights, hotels, and activities
- food_ordering: Ordering food from restaurants
- x_posting: Posting content to X/Twitter

Example response:
{
    "scenario": "flight_booking",
    "intent": "Search for flights from New York to London",
    "confidence": 0.9,
    "parameters": {
        "origin": "New York",
        "destination": "London",
        "departure_date": null,
        "return_date": null
    },
    "missing_parameters": ["departure_date"],
    "clarification_needed": true
}

Respond only with valid JSON.
"""
            
            prompt = f"{system_prompt}\n\nUser Query: {query}"
            
            response = await self._generate_response(prompt)
            
            # Parse JSON response
            try:
                logger.debug(f"Raw Gemini response: {response[:500]}...")  # Debug logging
                
                # Extract JSON from markdown code blocks if present
                response_clean = response.strip()
                if response_clean.startswith('```json'):
                    # Remove markdown code block markers
                    response_clean = response_clean[7:]  # Remove ```json
                    if response_clean.endswith('```'):
                        response_clean = response_clean[:-3]  # Remove trailing ```
                elif response_clean.startswith('```'):
                    # Remove generic code block markers
                    response_clean = response_clean[3:]
                    if response_clean.endswith('```'):
                        response_clean = response_clean[:-3]
                
                response_clean = response_clean.strip()
                parsed_result = json.loads(response_clean)
                
                # Validate required fields
                required_fields = ['scenario', 'intent', 'confidence', 'parameters']
                for field in required_fields:
                    if field not in parsed_result:
                        raise ValueError(f"Missing required field: {field}")
                
                # Add metadata
                parsed_result['parsed_at'] = datetime.utcnow().isoformat()
                parsed_result['original_query'] = query
                
                logger.info(f"Query parsed successfully: scenario={parsed_result['scenario']}, confidence={parsed_result['confidence']}")
                return parsed_result
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {str(e)}")
                raise ValueError(f"Invalid JSON response from Gemini: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error parsing user query: {str(e)}")
            raise

    async def build_task_tree(
        self, 
        scenario: str, 
        parameters: Dict[str, Any],
        available_tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Build a task tree for executing a scenario using available Composio tools.
        
        Args:
            scenario: Scenario name
            parameters: Extracted parameters
            available_tools: List of available Composio tools
            
        Returns:
            Task tree structure for execution
        """
        try:
            tools_info = "\n".join([
                f"- {tool['slug']}: {tool['description']} (App: {tool['app']})"
                for tool in available_tools
            ])
            
            system_prompt = f"""
You are an AI assistant that creates task execution trees for scenarios using Composio tools.

Create a task tree for the scenario "{scenario}" using the available tools and parameters.

Available Tools:
{tools_info}

The task tree should:
1. Use only the available tools listed above
2. Be executable in sequential or parallel order
3. Handle parameter dependencies between tools
4. Include error handling where appropriate

Respond with a JSON object containing:
1. task_tree: The execution tree structure
2. execution_order: Sequential list of tools to execute
3. dependencies: Map of tool dependencies
4. estimated_duration: Estimated execution time in seconds

Task tree structure should use:
- "sequential": Array of tasks to execute in order
- "parallel": Array of tasks to execute concurrently
- "tool": Tool slug to execute
- "parameters": Parameters for the tool
- "condition": Optional condition for conditional execution

Example task tree:
{{
    "task_tree": {{
        "sequential": [
            {{
                "tool": "GMAIL_FETCH_EMAILS",
                "parameters": {{
                    "query": "unread",
                    "max_results": 10
                }}
            }},
            {{
                "tool": "GMAIL_SEND_EMAIL",
                "parameters": {{
                    "to": "${{recipient}}",
                    "subject": "Response",
                    "body": "Auto-generated response"
                }}
            }}
        ]
    }},
    "execution_order": ["GMAIL_FETCH_EMAILS", "GMAIL_SEND_EMAIL"],
    "dependencies": {{"GMAIL_SEND_EMAIL": ["GMAIL_FETCH_EMAILS"]}},
    "estimated_duration": 30
}}

Respond only with valid JSON.
"""
            
            prompt = f"{system_prompt}\n\nScenario: {scenario}\nParameters: {json.dumps(parameters, indent=2)}"
            
            response = await self._generate_response(prompt)
            
            # Parse JSON response
            try:
                task_tree_result = json.loads(response)
                
                # Validate required fields
                required_fields = ['task_tree', 'execution_order']
                for field in required_fields:
                    if field not in task_tree_result:
                        raise ValueError(f"Missing required field: {field}")
                
                # Add metadata
                task_tree_result['created_at'] = datetime.utcnow().isoformat()
                task_tree_result['scenario'] = scenario
                task_tree_result['parameters'] = parameters
                
                logger.info(f"Task tree built for scenario {scenario} with {len(task_tree_result['execution_order'])} tools")
                return task_tree_result
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse task tree JSON: {str(e)}")
                raise ValueError(f"Invalid JSON response from Gemini: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error building task tree: {str(e)}")
            raise

    async def generate_clarification_questions(
        self, 
        scenario: str, 
        missing_parameters: List[str],
        tool_schemas: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate clarification questions for missing parameters.
        
        Args:
            scenario: Current scenario
            missing_parameters: List of missing parameter names
            tool_schemas: Schemas for tools that need the parameters
            context: Additional context for question generation
            
        Returns:
            List of clarification questions
        """
        try:
            schemas_info = json.dumps(tool_schemas, indent=2)
            context_info = json.dumps(context or {}, indent=2)
            
            system_prompt = f"""
You are an AI assistant that generates clarifying questions to collect missing information from users.

Generate natural, user-friendly questions to collect the missing parameters for the "{scenario}" scenario.

Tool Schemas:
{schemas_info}

Current Context:
{context_info}

For each missing parameter, create a question that:
1. Is natural and conversational
2. Provides context about why the information is needed
3. Includes examples or suggestions when helpful
4. Specifies the expected format if important

Respond with a JSON array of question objects:
[
    {{
        "parameter": "parameter_name",
        "question": "Natural language question",
        "type": "text|date|number|choice",
        "suggestions": ["option1", "option2"],
        "example": "Example answer",
        "required": true
    }}
]

Respond only with valid JSON array.
"""
            
            prompt = f"{system_prompt}\n\nMissing Parameters: {json.dumps(missing_parameters)}"
            
            response = await self._generate_response(prompt)
            
            # Parse JSON response
            try:
                questions = json.loads(response)
                
                if not isinstance(questions, list):
                    raise ValueError("Response should be a JSON array")
                
                # Validate question structure
                for question in questions:
                    required_fields = ['parameter', 'question']
                    for field in required_fields:
                        if field not in question:
                            raise ValueError(f"Missing required field in question: {field}")
                
                logger.info(f"Generated {len(questions)} clarification questions for scenario {scenario}")
                return questions
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse questions JSON: {str(e)}")
                raise ValueError(f"Invalid JSON response from Gemini: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error generating clarification questions: {str(e)}")
            raise

    async def generate_tool_parameters(
        self, 
        tool_slug: str, 
        tool_schema: Dict[str, Any],
        user_input: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate structured parameters for a tool based on natural language input.
        
        Args:
            tool_slug: Tool slug
            tool_schema: Tool parameter schema
            user_input: Natural language user input
            context: Additional context from previous executions
            
        Returns:
            Generated tool parameters
        """
        try:
            schema_info = json.dumps(tool_schema, indent=2)
            context_info = json.dumps(context or {}, indent=2)
            
            system_prompt = f"""
You are an AI assistant that converts natural language into structured tool parameters.

Convert the user input into parameters for the tool "{tool_slug}" based on its schema.

Tool Schema:
{schema_info}

Context from previous executions:
{context_info}

Extract and structure the parameters according to the schema:
1. Follow the exact parameter names and types from the schema
2. Use context information when available
3. Apply reasonable defaults for optional parameters
4. Ensure required parameters are provided or marked as missing

Respond with a JSON object containing:
{{
    "parameters": {{
        "param1": "value1",
        "param2": "value2"
    }},
    "missing_required": ["required_param_that_is_missing"],
    "confidence": 0.85,
    "assumptions": ["assumption1", "assumption2"]
}}

Respond only with valid JSON.
"""
            
            prompt = f"{system_prompt}\n\nUser Input: {user_input}"
            
            response = await self._generate_response(prompt)
            
            # Parse JSON response
            try:
                parameters_result = json.loads(response)
                
                # Validate structure
                if 'parameters' not in parameters_result:
                    raise ValueError("Missing 'parameters' field in response")
                
                # Add metadata
                parameters_result['generated_at'] = datetime.utcnow().isoformat()
                parameters_result['tool_slug'] = tool_slug
                parameters_result['user_input'] = user_input
                
                logger.info(f"Generated parameters for tool {tool_slug}")
                return parameters_result
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse parameters JSON: {str(e)}")
                raise ValueError(f"Invalid JSON response from Gemini: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error generating tool parameters: {str(e)}")
            raise

    async def analyze_execution_result(
        self, 
        execution_result: Dict[str, Any],
        original_query: str,
        scenario: str
    ) -> Dict[str, Any]:
        """
        Analyze execution result and generate user-friendly summary.
        
        Args:
            execution_result: Raw execution result
            original_query: Original user query
            scenario: Executed scenario
            
        Returns:
            Analysis with user-friendly summary
        """
        try:
            result_info = json.dumps(execution_result, indent=2)
            
            system_prompt = f"""
You are an AI assistant that analyzes task execution results and creates user-friendly summaries.

Analyze the execution result for the "{scenario}" scenario and create a summary for the user.

Original User Query: {original_query}

The summary should:
1. Explain what was accomplished in simple terms
2. Highlight key results or data
3. Mention any issues or limitations
4. Suggest next steps if appropriate

Respond with a JSON object containing:
{{
    "success": true/false,
    "summary": "User-friendly summary of what was accomplished",
    "key_results": ["result1", "result2"],
    "issues": ["issue1", "issue2"],
    "next_steps": ["suggestion1", "suggestion2"],
    "confidence": 0.9
}}

Respond only with valid JSON.
"""
            
            prompt = f"{system_prompt}\n\nExecution Result:\n{result_info}"
            
            response = await self._generate_response(prompt)
            
            # Parse JSON response
            try:
                analysis_result = json.loads(response)
                
                # Add metadata
                analysis_result['analyzed_at'] = datetime.utcnow().isoformat()
                analysis_result['scenario'] = scenario
                analysis_result['original_query'] = original_query
                
                logger.info(f"Analyzed execution result for scenario {scenario}")
                return analysis_result
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse analysis JSON: {str(e)}")
                raise ValueError(f"Invalid JSON response from Gemini: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error analyzing execution result: {str(e)}")
            raise

    async def optimize_task_sequence(
        self, 
        task_tree: Dict[str, Any],
        execution_constraints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Optimize task execution sequence for better performance.
        
        Args:
            task_tree: Original task tree
            execution_constraints: Performance constraints and preferences
            
        Returns:
            Optimized task tree
        """
        try:
            tree_info = json.dumps(task_tree, indent=2)
            constraints_info = json.dumps(execution_constraints or {}, indent=2)
            
            system_prompt = f"""
You are an AI assistant that optimizes task execution sequences for better performance.

Analyze the task tree and suggest optimizations based on:
1. Parallelization opportunities
2. Dependency management
3. Resource efficiency
4. Error handling

Current Task Tree:
{tree_info}

Execution Constraints:
{constraints_info}

Respond with a JSON object containing:
{{
    "optimized_tree": {{...}},
    "optimizations_applied": ["optimization1", "optimization2"],
    "estimated_improvement": "25% faster execution",
    "parallel_opportunities": 3,
    "risk_level": "low|medium|high"
}}

Respond only with valid JSON.
"""
            
            response = await self._generate_response(prompt)
            
            # Parse JSON response
            try:
                optimization_result = json.loads(response)
                
                # Add metadata
                optimization_result['optimized_at'] = datetime.utcnow().isoformat()
                optimization_result['original_tree'] = task_tree
                
                logger.info(f"Optimized task sequence with {len(optimization_result.get('optimizations_applied', []))} improvements")
                return optimization_result
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse optimization JSON: {str(e)}")
                raise ValueError(f"Invalid JSON response from Gemini: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error optimizing task sequence: {str(e)}")
            raise

    async def _generate_response(self, prompt: str, max_retries: int = 3) -> str:
        """
        Generate response from Gemini with retry logic.
        
        Args:
            prompt: Input prompt
            max_retries: Maximum number of retries
            
        Returns:
            Generated response text
        """
        for attempt in range(max_retries):
            try:
                response = await asyncio.to_thread(
                    self.model.generate_content,
                    prompt
                )
                
                # Enhanced response validation
                if hasattr(response, 'text') and response.text:
                    response_text = response.text.strip()
                    
                    # Debug logging
                    logger.debug(f"Gemini raw response (attempt {attempt + 1}): '{response_text[:200]}...'")
                    
                    # Check if response is not empty after stripping
                    if response_text:
                        return response_text
                    else:
                        logger.warning(f"Gemini returned empty response after stripping (attempt {attempt + 1})")
                        raise ValueError("Empty response from Gemini after stripping")
                else:
                    logger.warning(f"Gemini response has no text attribute or is None (attempt {attempt + 1})")
                    raise ValueError("No text in Gemini response")
                    
            except Exception as e:
                logger.warning(f"Gemini generation attempt {attempt + 1} failed: {str(e)}")
                
                if attempt == max_retries - 1:
                    raise ValueError(f"Failed to generate response after {max_retries} attempts: {str(e)}")
                
                # Wait before retry
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        raise ValueError("Unexpected error in response generation")

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check for Gemini service.
        
        Returns:
            Health status information
        """
        try:
            # Test with a simple prompt
            test_response = await self._generate_response("Respond with 'OK' if you can process this request.")
            
            health_status = {
                'status': 'healthy',
                'model': self.model_name,
                'temperature': self.temperature,
                'test_response': test_response[:100],  # First 100 chars
                'checked_at': datetime.utcnow().isoformat()
            }
            
            return health_status
            
        except Exception as e:
            logger.error(f"Gemini health check failed: {str(e)}")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'model': self.model_name,
                'checked_at': datetime.utcnow().isoformat()
            }

    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the current Gemini model configuration.
        
        Returns:
            Model configuration information
        """
        return {
            'model_name': self.model_name,
            'temperature': self.temperature,
            'api_configured': bool(self.api_key),
            'service_initialized': True
        }
    
    # Additional methods for test automation and Composio integration
    
    async def select_composio_tool(self, natural_query: str, available_tools: List[str]) -> Dict[str, Any]:
        """
        Use LLM to select the most appropriate Composio tool from available tools.
        
        Args:
            natural_query: Natural language user query
            available_tools: List of available Composio tool names
            
        Returns:
            Tool selection result with confidence and reasoning
        """
        try:
            tools_list = ', '.join(available_tools)
            
            system_prompt = f"""
You are an AI assistant that selects the most appropriate Composio tool for user queries.

Given this natural language query: "{natural_query}"

Available Composio tools: {tools_list}

Select the most appropriate tool to handle this query. Consider:
- Email-related tasks (send, receive, manage emails) -> GMAIL
- Code repositories, issues, pull requests -> GITHUB  
- Calendar, scheduling, meetings -> CALENDAR apps
- Social media posting -> X/TWITTER
- File operations -> FILE_MANAGER
- Communication -> SLACK, DISCORD

Respond with a JSON object:
{{
    "selected_tool": "TOOL_NAME",
    "confidence": 0.95,
    "reasoning": "Brief explanation of why this tool was selected",
    "alternative_tools": ["TOOL2", "TOOL3"]
}}

Respond only with valid JSON.
"""
            
            response = await self._generate_response(system_prompt)
            
            # Enhanced JSON parsing with better error handling
            try:
                # Clean up response to extract JSON
                response_clean = response.strip()
                logger.debug(f"Tool selection raw LLM response: '{response_clean[:300]}...'")
                
                # Remove markdown code blocks if present
                if response_clean.startswith('```json'):
                    response_clean = response_clean[7:]
                    if response_clean.endswith('```'):
                        response_clean = response_clean[:-3]
                elif response_clean.startswith('```'):
                    response_clean = response_clean[3:]
                    if response_clean.endswith('```'):
                        response_clean = response_clean[:-3]
                
                response_clean = response_clean.strip()
                
                # Check if we have content to parse
                if not response_clean:
                    logger.error("Empty response after cleaning for tool selection")
                    raise json.JSONDecodeError("Empty response", response_clean, 0)
                
                result = json.loads(response_clean)
                
                # Validate selection
                selected_tool = result.get('selected_tool', '').upper()
                if selected_tool not in [tool.upper() for tool in available_tools]:
                    logger.warning(f"LLM selected invalid tool: {selected_tool}")
                    # Default to first available tool
                    result['selected_tool'] = available_tools[0] if available_tools else None
                    result['confidence'] = 0.1
                    result['reasoning'] = f"Defaulted due to invalid selection: {selected_tool}"
                
                result['query'] = natural_query
                result['available_tools'] = available_tools
                result['selected_at'] = datetime.utcnow().isoformat()
                
                logger.info(f"Selected tool: {result['selected_tool']} (confidence: {result.get('confidence', 0)})")
                return result
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse tool selection JSON: {str(e)}")
                logger.error(f"Problematic response: '{response[:500]}...'")
                # Return default selection
                return {
                    'selected_tool': available_tools[0] if available_tools else None,
                    'confidence': 0.1,
                    'reasoning': f"JSON parse error: {str(e)}",
                    'query': natural_query,
                    'available_tools': available_tools,
                    'selected_at': datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error in tool selection: {str(e)}")
            return {
                'selected_tool': available_tools[0] if available_tools else None,
                'confidence': 0.1,
                'reasoning': f"Error: {str(e)}",
                'query': natural_query,
                'available_tools': available_tools,
                'selected_at': datetime.utcnow().isoformat()
            }
    
    async def select_composio_action(self, natural_query: str, tool_name: str, available_actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Use LLM to select the most appropriate action from a Composio tool.
        
        Args:
            natural_query: Natural language user query
            tool_name: Selected tool name (e.g., "GMAIL", "GITHUB")
            available_actions: List of available actions with descriptions
            
        Returns:
            Action selection result with confidence and reasoning
        """
        try:
            # Format actions for LLM prompt (limit to avoid token limits)
            action_descriptions = []
            for action_info in available_actions[:20]:  # Limit to first 20 actions
                action_name = action_info.get('name', 'Unknown')
                description = action_info.get('description', 'No description available')
                action_descriptions.append(f"• {action_name}: {description}")
            
            actions_text = '\n'.join(action_descriptions)
            if len(available_actions) > 20:
                actions_text += f"\n... and {len(available_actions) - 20} more actions"
            
            system_prompt = f"""
You are an AI assistant that selects the most appropriate Composio action for user queries.

Given this natural language query: "{natural_query}"
Tool: {tool_name}

Available {tool_name} actions:
{actions_text}

Select the single most appropriate action to handle this query. Consider:

For GMAIL:
- "send email" queries -> GMAIL_SEND_EMAIL
- "fetch/get/read emails" queries -> GMAIL_FETCH_EMAILS  
- "list emails" queries -> GMAIL_FETCH_EMAILS
- "create draft" queries -> GMAIL_CREATE_EMAIL_DRAFT

For GITHUB:
- "get my profile/info" queries -> GITHUB_GET_THE_AUTHENTICATED_USER
- "list my repositories" queries -> GITHUB_REPO_S_LIST_FOR_AUTHENTICATED_USER
- "create an issue" queries -> GITHUB_ISSUES_CREATE
- "search repositories" queries -> GITHUB_SEARCH_REPOSITORIES

Respond with a JSON object:
{{
    "selected_action": "ACTION_NAME",
    "confidence": 0.95,
    "reasoning": "Brief explanation of why this action was selected",
    "alternative_actions": ["ACTION2", "ACTION3"]
}}

Respond only with valid JSON.
"""
            
            response = await self._generate_response(system_prompt)
            
            # Enhanced JSON parsing with better error handling
            try:
                # Clean up response to extract JSON
                response_clean = response.strip()
                logger.debug(f"Action selection raw LLM response: '{response_clean[:300]}...'")
                
                # Remove markdown code blocks if present
                if response_clean.startswith('```json'):
                    response_clean = response_clean[7:]
                    if response_clean.endswith('```'):
                        response_clean = response_clean[:-3]
                elif response_clean.startswith('```'):
                    response_clean = response_clean[3:]
                    if response_clean.endswith('```'):
                        response_clean = response_clean[:-3]
                
                response_clean = response_clean.strip()
                
                # Check if we have content to parse
                if not response_clean:
                    logger.error("Empty response after cleaning for action selection")
                    raise json.JSONDecodeError("Empty response", response_clean, 0)
                
                result = json.loads(response_clean)
                
                # Validate selection
                selected_action = result.get('selected_action', '')
                action_names = [action.get('name', str(action)) if isinstance(action, dict) else str(action) for action in available_actions]
                
                if selected_action not in action_names:
                    logger.warning(f"LLM selected invalid action: {selected_action}")
                    # Default to first available action
                    result['selected_action'] = action_names[0] if action_names else None
                    result['confidence'] = 0.1
                    result['reasoning'] = f"Defaulted due to invalid selection: {selected_action}"
                
                result['query'] = natural_query
                result['tool_name'] = tool_name
                result['total_actions'] = len(available_actions)
                result['selected_at'] = datetime.utcnow().isoformat()
                
                logger.info(f"Selected action: {result['selected_action']} (confidence: {result.get('confidence', 0)})")
                return result
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse action selection JSON: {str(e)}")
                logger.error(f"Problematic response: '{response[:500]}...'")
                action_names = [action.get('name', str(action)) if isinstance(action, dict) else str(action) for action in available_actions]
                return {
                    'selected_action': action_names[0] if action_names else None,
                    'confidence': 0.1,
                    'reasoning': f"JSON parse error: {str(e)}",
                    'query': natural_query,
                    'tool_name': tool_name,
                    'total_actions': len(available_actions),
                    'selected_at': datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error in action selection: {str(e)}")
            action_names = [action.get('name', str(action)) if isinstance(action, dict) else str(action) for action in available_actions]
            return {
                'selected_action': action_names[0] if action_names else None,
                'confidence': 0.1,
                'reasoning': f"Error: {str(e)}",
                'query': natural_query,
                'tool_name': tool_name,
                'total_actions': len(available_actions),
                'selected_at': datetime.utcnow().isoformat()
            }
    
    async def normalize_action_parameters(self, 
                                        natural_query: str, 
                                        action_name: str, 
                                        action_schema: Dict[str, Any],
                                        context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Use LLM to normalize natural language query into structured action parameters.
        
        Args:
            natural_query: Natural language user query
            action_name: Selected action name
            action_schema: Action parameter schema from Composio
            context: Additional context for parameter generation
            
        Returns:
            Normalized parameters with metadata
        """
        try:
            schema_info = json.dumps(action_schema, indent=2)
            context_info = json.dumps(context or {}, indent=2)
            
            system_prompt = f"""
You are an AI assistant that converts natural language into structured action parameters.

Natural language query: "{natural_query}"
Action: {action_name}

Parameter schema:
{schema_info}

Additional context:
{context_info}

Based on the natural language query, extract appropriate values for each parameter.

Rules for common patterns:
- For email queries like "send email to john@example.com", extract recipient_email: "john@example.com"
- For "fetch recent emails", set max_results: 5, user_id: "me" 
- For GitHub queries like "create issue in my-repo", extract owner and repo from context
- For boolean parameters, use true/false
- For missing information, use reasonable defaults
- Always include required parameters
- Use current user context when appropriate (e.g., "me", authenticated user info)

Extract values that match the parameter types and descriptions in the schema.

Respond with a JSON object:
{{
    "parameters": {{
        "param1": "value1",
        "param2": "value2"
    }},
    "confidence": 0.95,
    "missing_required": ["required_param_that_could_not_be_extracted"],
    "assumptions": ["assumption1: used default value X", "assumption2: inferred Y from context"],
    "warnings": ["warning1", "warning2"]
}}

Respond only with valid JSON.
"""
            
            response = await self._generate_response(system_prompt)
            
            # Enhanced JSON parsing with better error handling
            try:
                # Clean up response to extract JSON
                response_clean = response.strip()
                logger.debug(f"Parameter normalization raw LLM response: '{response_clean[:300]}...'")
                
                # Remove markdown code blocks if present
                if response_clean.startswith('```json'):
                    response_clean = response_clean[7:]
                    if response_clean.endswith('```'):
                        response_clean = response_clean[:-3]
                elif response_clean.startswith('```'):
                    response_clean = response_clean[3:]
                    if response_clean.endswith('```'):
                        response_clean = response_clean[:-3]
                
                response_clean = response_clean.strip()
                
                # Check if we have content to parse
                if not response_clean:
                    logger.error("Empty response after cleaning for parameter normalization")
                    raise json.JSONDecodeError("Empty response", response_clean, 0)
                
                result = json.loads(response_clean)
                
                # Ensure required fields exist
                if 'parameters' not in result:
                    result['parameters'] = {}
                if 'confidence' not in result:
                    result['confidence'] = 0.5
                
                # Add metadata
                result['query'] = natural_query
                result['action_name'] = action_name
                result['normalized_at'] = datetime.utcnow().isoformat()
                result['schema'] = action_schema
                
                logger.info(f"Normalized parameters for {action_name}: {len(result['parameters'])} params, confidence: {result['confidence']}")
                return result
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse parameter normalization JSON: {str(e)}")
                logger.error(f"Problematic response: '{response[:500]}...'")
                return {
                    'parameters': {},
                    'confidence': 0.1,
                    'missing_required': [],
                    'assumptions': [],
                    'warnings': [f"JSON parse error: {str(e)}"],
                    'query': natural_query,
                    'action_name': action_name,
                    'normalized_at': datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error in parameter normalization: {str(e)}")
            return {
                'parameters': {},
                'confidence': 0.1,
                'missing_required': [],
                'assumptions': [],
                'warnings': [f"Error: {str(e)}"],
                'query': natural_query,
                'action_name': action_name,
                'normalized_at': datetime.utcnow().isoformat()
            }