#!/usr/bin/env python3
"""
Interactive Composio Workflow Test - Complete LLM-driven pipeline demonstration.

This script demonstrates the full workflow:
1. Fetch Composio apps
2. LLM selects the app
3. Fetch Composio actions for selected app
4. LLM selects the action
5. Fetch Composio action schema
6. LLM normalizes parameters from natural language query
7. Execute the action with normalized parameters

Follows the structure and patterns from test_gmail_real_actions.py
"""

import asyncio
import logging
import sys
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

# Configure logging for debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

try:
    from composio import ComposioToolSet, App
except ImportError:
    print("❌ Composio not installed. Run: pip install composio-core")
    exit(1)

# Import the common services
sys.path.append('src')
try:
    from infrastructure.composio_llm_service import ComposioLLMService
except ImportError:
    print("❌ ComposioLLMService not found. Make sure src/infrastructure/composio_llm_service.py exists")
    exit(1)


class InteractiveComposioWorkflowTester:
    """Interactive test demonstrating complete LLM-driven Composio workflow."""
    
    def __init__(self):
        self.entity_id = "default"
        
        # Initialize toolset for direct Composio operations
        self.toolset = ComposioToolSet()
        
        # Initialize ComposioLLMService for LLM-driven operations
        try:
            self.composio_llm = ComposioLLMService(entity_id=self.entity_id)
            print("🔧 Composio LLM Service initialized")
            print("🤖 Natural language processing enabled")
        except Exception as e:
            print(f"❌ Failed to initialize ComposioLLMService: {e}")
            print("   Please set GOOGLE_API_KEY or GEMINI_API_KEY in your .env file")
            exit(1)
    
    def refresh_composio_client(self):
        """Refresh the Composio toolset to pick up new authentications."""
        try:
            print("🔄 Refreshing Composio toolset...")
            from composio import ComposioToolSet
            self.toolset = ComposioToolSet()
            print("✅ Composio toolset refreshed successfully")
            return True
        except Exception as e:
            print(f"❌ Failed to refresh Composio toolset: {str(e)}")
            return False
    
    async def step_1_fetch_composio_apps(self) -> List[str]:
        """Step 1: Fetch all available Composio apps."""
        print("\n" + "="*80)
        print("🔍 STEP 1: FETCHING COMPOSIO APPS")
        print("="*80)
        
        try:
            # Add timeout handling for Composio API
            print("🔄 Fetching apps from Composio (timeout: 30s)...")
            
            # Use asyncio.wait_for to add timeout
            raw_apps = await asyncio.wait_for(
                asyncio.to_thread(self.toolset.get_apps),
                timeout=30.0
            )
            print(f"📱 Found {len(raw_apps)} available apps from Composio")
            
            # Extract app names properly from App objects
            all_apps = []
            for app in raw_apps:
                if hasattr(app, 'name'):
                    all_apps.append(app.name.upper())
                elif hasattr(app, 'key'):
                    all_apps.append(app.key.upper())
                else:
                    # Fallback to string representation
                    app_str = str(app).upper()
                    all_apps.append(app_str)
            
            # Remove duplicates and sort
            unique_apps = sorted(list(set(all_apps)))
            
            print(f"\n📋 AVAILABLE APPS ({len(unique_apps)} unique apps):")
            print("-" * 50)
            
            # Display apps in columns for better readability
            for i, app in enumerate(unique_apps[:20], 1):  # Show first 20
                print(f"{i:2d}. {app}")
            
            if len(unique_apps) > 20:
                print(f"    ... and {len(unique_apps) - 20} more apps")
            
            print(f"\n✅ Step 1 Complete: {len(unique_apps)} apps available for LLM selection")
            return unique_apps
            
        except asyncio.TimeoutError:
            print("❌ Composio API timeout - using fallback app list")
            return self._get_fallback_apps()
        except Exception as e:
            print(f"❌ Error fetching Composio apps: {str(e)}")
            print("🔄 Using fallback app list for demonstration")
            return self._get_fallback_apps()
    
    def _get_fallback_apps(self) -> List[str]:
        """Provide a fallback list of common apps when Composio API is unavailable."""
        fallback_apps = [
            "GMAIL", "GITHUB", "SLACK", "CALENDAR", "DRIVE", "SHEETS", 
            "DOCS", "LINKEDIN", "TWITTER", "DROPBOX", "NOTION", "TRELLO",
            "ASANA", "JIRA", "DISCORD", "ZOOM", "FIGMA", "HUBSPOT"
        ]
        
        print(f"\n📋 FALLBACK APPS ({len(fallback_apps)} common apps):")
        print("-" * 50)
        print("⚠️ Using cached app list due to API unavailability")
        
        for i, app in enumerate(fallback_apps, 1):
            print(f"{i:2d}. {app}")
        
        print(f"\n✅ Step 1 Complete (Fallback): {len(fallback_apps)} apps available for LLM selection")
        return fallback_apps
    
    async def step_2_llm_selects_app(self, natural_query: str, available_apps: List[str]) -> str:
        """Step 2: Use LLM to select the most appropriate app."""
        print("\n" + "="*80)
        print("🤖 STEP 2: LLM SELECTS APP")
        print("="*80)
        print(f"Query: '{natural_query}'")
        print(f"Available apps: {len(available_apps)} options")
        
        try:
            # Use LLM service for app selection
            result = await self.composio_llm.select_tool_with_llm(natural_query)
            
            # Handle both dict and string returns
            if isinstance(result, dict):
                selected_app = result.get('selected_tool', 'GMAIL')
                confidence = result.get('confidence', 0.0)
                reasoning = result.get('reasoning', 'No reasoning provided')
            else:
                # Fallback if result is not a dict
                selected_app = str(result) if result else 'GMAIL'
                confidence = 0.5
                reasoning = 'LLM selection result format issue'
            
            print(f"\n🎯 LLM SELECTION RESULT:")
            print("-" * 30)
            print(f"   Selected App: {selected_app}")
            print(f"   Confidence: {confidence:.2f}")
            print(f"   Reasoning: {reasoning}")
            
            # Validate selection
            if selected_app not in [app.upper() for app in available_apps]:
                print(f"⚠️ LLM selected unavailable app: {selected_app}")
                print(f"   Defaulting to first available app: {available_apps[0]}")
                selected_app = available_apps[0]
            
            print(f"\n✅ Step 2 Complete: Selected app '{selected_app}' for execution")
            return selected_app
            
        except Exception as e:
            print(f"❌ Error in LLM app selection: {str(e)}")
            print(f"   Defaulting to GMAIL")
            return "GMAIL"
    
    async def step_2_5_check_and_authenticate_app(self, selected_app: str) -> bool:
        """Step 2.5: Check if app is authenticated and trigger OAuth if needed."""
        print("\n" + "="*80)
        print("🔐 STEP 2.5: AUTHENTICATION CHECK & OAUTH")
        print("="*80)
        print(f"Checking authentication for: {selected_app}")
        
        try:
            # Check if app is connected
            print("🔄 Checking connected accounts...")
            connected_accounts = await asyncio.wait_for(
                asyncio.to_thread(self.toolset.get_connected_accounts),
                timeout=10.0
            )
            
            # Check if the selected app is connected
            app_connected = False
            if connected_accounts:
                for account in connected_accounts:
                    if hasattr(account, 'appName') and account.appName.upper() == selected_app.upper():
                        app_connected = True
                        print(f"✅ {selected_app} is already connected!")
                        print(f"   Account ID: {getattr(account, 'id', 'N/A')}")
                        print(f"   Connection Status: {getattr(account, 'connectionStatus', 'Active')}")
                        break
                    elif hasattr(account, 'app') and str(account.app).upper() == selected_app.upper():
                        app_connected = True
                        print(f"✅ {selected_app} is already connected!")
                        break
            
            if app_connected:
                print(f"\n✅ Step 2.5 Complete: {selected_app} authentication verified")
                return True
            
            # App not connected - provide OAuth URL
            print(f"⚠️ {selected_app} is not connected to Composio")
            print("🚀 Initiating OAuth authentication flow...")
            
            # Get OAuth URL for the app dynamically
            try:
                from composio import App as ComposioApp
                
                # Get app enum dynamically
                app_enum = getattr(ComposioApp, selected_app.upper(), None)
                if not app_enum:
                    print(f"❌ App {selected_app} not found in Composio")
                    print(f"🌐 Try connecting at: https://app.composio.dev/apps")
                    return False
                
                print(f"🔗 Generating OAuth URL for {selected_app}...")
                
                # Generate OAuth URL
                oauth_request = await asyncio.wait_for(
                    asyncio.to_thread(
                        lambda: self.toolset.initiate_connection(
                            app=app_enum,
                            entity_id=self.entity_id,
                            redirect_url="http://localhost:8000/auth/callback"
                        )
                    ),
                    timeout=15.0
                )
                
                if oauth_request and hasattr(oauth_request, 'redirectUrl'):
                    oauth_url = oauth_request.redirectUrl
                    connection_id = getattr(oauth_request, 'connectionId', 'unknown')
                    
                    print(f"🎯 OAuth URL Generated Successfully!")
                    print("-" * 50)
                    print(f"🔗 Auth URL: {oauth_url}")
                    print(f"🆔 Connection ID: {connection_id}")
                    print("\n📋 AUTHENTICATION INSTRUCTIONS:")
                    print("1. Copy the OAuth URL above")
                    print("2. Open it in your browser")
                    print("3. Complete the authentication flow")
                    print("4. Return to continue the test")
                    
                    # Interactive prompt for user to complete OAuth
                    print(f"\n⏳ Please complete OAuth authentication for {selected_app}")
                    user_input = input("Press Enter after completing authentication (or 'skip' to continue without auth): ").strip()
                    
                    if user_input.lower() == 'skip':
                        print("⚠️ Skipping authentication - execution may fail")
                        return False
                    
                    # Verify connection after OAuth
                    print("🔄 Verifying authentication...")
                    await asyncio.sleep(2)  # Give some time for the connection to be established
                    
                    # IMPORTANT: Reinitialize the toolset to pick up new connections
                    print("🔄 Reinitializing Composio toolset to detect new authentication...")
                    try:
                        # Create a fresh toolset instance to pick up the new connection
                        from composio import ComposioToolSet
                        self.toolset = ComposioToolSet()
                        print("✅ Toolset reinitialized successfully")
                    except Exception as reinit_error:
                        print(f"⚠️ Toolset reinitialization warning: {str(reinit_error)}")
                    
                    # Re-check connected accounts with fresh toolset
                    updated_accounts = await asyncio.wait_for(
                        asyncio.to_thread(self.toolset.get_connected_accounts),
                        timeout=10.0
                    )
                    
                    auth_verified = False
                    if updated_accounts:
                        for account in updated_accounts:
                            if (hasattr(account, 'appName') and account.appName.upper() == selected_app.upper()) or \
                               (hasattr(account, 'app') and str(account.app).upper() == selected_app.upper()):
                                auth_verified = True
                                print(f"🎉 {selected_app} authentication successful!")
                                break
                    
                    if not auth_verified:
                        print(f"⚠️ Authentication verification failed for {selected_app}")
                        print("   Continuing with workflow - execution may fail")
                    
                    print(f"\n✅ Step 2.5 Complete: OAuth flow attempted for {selected_app}")
                    return auth_verified
                
                else:
                    print(f"❌ Failed to generate OAuth URL for {selected_app}")
                    return False
                
            except Exception as oauth_error:
                print(f"❌ OAuth initiation failed: {str(oauth_error)}")
                print("   Continuing without authentication - execution may fail")
                return False
            
        except asyncio.TimeoutError:
            print("❌ Authentication check timed out")
            return False
        except Exception as e:
            print(f"❌ Authentication check failed: {str(e)}")
            print("   Continuing without verification - execution may fail")
            return False
    
    async def step_3_fetch_composio_actions(self, selected_app: str) -> List[Dict[str, Any]]:
        """Step 3: Fetch all available actions for the selected app."""
        print("\n" + "="*80)
        print("🔧 STEP 3: FETCHING COMPOSIO ACTIONS")
        print("="*80)
        print(f"Selected app: {selected_app}")
        
        try:
            available_actions = []
            
            print("🔄 Fetching actions from Composio (timeout: 20s)...")
            
            # Get actions dynamically for any app
            raw_actions = None
            try:
                # Dynamically get the app from the App enum
                app_attr = getattr(App, selected_app.upper(), None)
                if app_attr:
                    raw_actions = await asyncio.wait_for(
                        asyncio.to_thread(lambda: list(app_attr.get_actions())),
                        timeout=20.0
                    )
                else:
                    print(f"⚠️ App {selected_app} not found in Composio App enum - using fallback actions")
                    return self._get_fallback_actions(selected_app)
            
            except asyncio.TimeoutError:
                print("❌ Composio actions API timeout - using fallback actions")
                return self._get_fallback_actions(selected_app)
            
            if not raw_actions:
                print(f"❌ No actions returned for {selected_app} - using fallback")
                return self._get_fallback_actions(selected_app)
            
            print(f"📋 Found {len(raw_actions)} actions for {selected_app}")
            
            # Prepare actions info for LLM WITHOUT fetching schemas (performance optimization)
            # The LLM will select based on action names, then we'll fetch schema for selected action only
            for action in raw_actions:
                available_actions.append({
                    'name': str(action),
                    'description': f'Action available for {selected_app}',  # Generic description
                    'action_object': action
                })
            
            print(f"\n📋 AVAILABLE ACTIONS ({len(available_actions)} actions ready for LLM selection):")
            print("-" * 60)
            print("🚀 Performance optimized: LLM will select action first, then fetch schema")
            
            # Display first 15 actions by name only (much faster)
            for i, action_info in enumerate(available_actions[:15], 1):
                name = action_info['name']
                print(f"{i:2d}. {name}")
            
            if len(available_actions) > 15:
                print(f"    ... and {len(available_actions) - 15} more actions")
            
            print(f"\n✅ Step 3 Complete: {len(available_actions)} actions ready for LLM selection")
            return available_actions
            
        except Exception as e:
            print(f"❌ Error fetching actions for {selected_app}: {str(e)}")
            print("🔄 Using fallback actions for demonstration")
            return self._get_fallback_actions(selected_app)
    
    def _get_fallback_actions(self, app_name: str) -> List[Dict[str, Any]]:
        """Provide fallback actions when Composio API is unavailable."""
        fallback_actions = {}
        
        # Define common actions for each app
        if app_name.upper() == "GMAIL":
            fallback_actions = {
                "GMAIL_FETCH_EMAILS": "Fetch emails from Gmail inbox with filtering options",
                "GMAIL_SEND_EMAIL": "Send an email via Gmail to specified recipients",
                "GMAIL_CREATE_DRAFT": "Create a draft email in Gmail",
                "GMAIL_DELETE_EMAIL": "Delete an email from Gmail",
                "GMAIL_MARK_READ": "Mark Gmail emails as read"
            }
        elif app_name.upper() == "GITHUB":
            fallback_actions = {
                "GITHUB_GET_THE_AUTHENTICATED_USER": "Get profile information for authenticated GitHub user",
                "GITHUB_REPO_S_LIST_FOR_AUTHENTICATED_USER": "List repositories for the authenticated user",
                "GITHUB_ISSUES_CREATE": "Create a new issue in a GitHub repository",
                "GITHUB_SEARCH_REPOSITORIES": "Search for repositories on GitHub",
                "GITHUB_CREATE_PULL_REQUEST": "Create a new pull request"
            }
        elif app_name.upper() == "SLACK":
            fallback_actions = {
                "SLACK_SEND_MESSAGE": "Send a message to a Slack channel or user",
                "SLACK_LIST_CHANNELS": "List all channels in Slack workspace",
                "SLACK_CREATE_CHANNEL": "Create a new Slack channel",
                "SLACK_GET_USER_INFO": "Get information about a Slack user",
                "SLACK_UPLOAD_FILE": "Upload a file to Slack"
            }
        else:
            # Generic fallback
            fallback_actions = {
                f"{app_name.upper()}_LIST": f"List items from {app_name}",
                f"{app_name.upper()}_CREATE": f"Create new item in {app_name}",
                f"{app_name.upper()}_GET": f"Get information from {app_name}",
                f"{app_name.upper()}_UPDATE": f"Update item in {app_name}",
                f"{app_name.upper()}_DELETE": f"Delete item from {app_name}"
            }
        
        actions_list = []
        for action_name, description in fallback_actions.items():
            actions_list.append({
                'name': action_name,
                'description': description,
                'action_object': action_name  # Use string as placeholder
            })
        
        print(f"\n📋 FALLBACK ACTIONS ({len(actions_list)} common actions):")
        print("-" * 60)
        print("⚠️ Using cached action list due to API unavailability")
        
        for i, action_info in enumerate(actions_list, 1):
            print(f"{i:2d}. {action_info['name']}")
            print(f"    {action_info['description']}")
        
        print(f"\n✅ Step 3 Complete (Fallback): {len(actions_list)} actions ready for LLM selection")
        return actions_list
    
    async def _display_detailed_results(self, data: Any, action_name: str):
        """Use LLM to intelligently format and explain Composio execution results."""
        print(f"\n📦 DETAILED RESULTS:")
        print("=" * 60)
        
        if not data:
            print("   📭 No data returned from API")
            print("   💡 This could mean:")
            print("      • No results found for the search query")
            print("      • API returned empty response")
            print("      • Authentication/permission issues")
            return
        
        try:
            # Use LLM to format the results intelligently
            print("🤖 AI-powered result formatting...")
            
            # Prepare data for LLM analysis
            data_str = str(data)
            if len(data_str) > 3000:  # Truncate very large responses
                data_str = data_str[:3000] + "... [truncated]"
            
            # Create prompt for LLM to format results
            format_prompt = f"""
You are helping format API execution results for the user. 

Action executed: {action_name}
Raw API response data: {data_str}

Please format this data in a clean, user-friendly way. Follow these guidelines:
1. Use emojis and clear headings to organize the information
2. Highlight the most important/relevant information first
3. If it's a list of items (like repositories, emails, etc.), show the first few with key details
4. Explain what the data means in simple terms
5. Keep the formatting concise but informative
6. Use proper indentation and bullets for readability

Format the response as if you're showing results to a user who just executed this action.
"""
            
            # Get formatted result from LLM
            formatted_result = await self.composio_llm.gemini_service._generate_response(format_prompt)
            
            if formatted_result:
                print("\n" + formatted_result)
            else:
                print("   ⚠️ LLM formatting failed, showing raw data:")
                self._display_raw_data(data)
                
        except Exception as e:
            print(f"   ⚠️ LLM formatting error: {str(e)}")
            print("   📄 Showing raw data instead:")
            self._display_raw_data(data)
    
    def _display_raw_data(self, data: Any):
        """Simple fallback display for raw data."""
        if isinstance(data, dict):
            print(f"   📊 Dictionary with {len(data)} keys: {list(data.keys())}")
            for key, value in list(data.items())[:5]:
                value_str = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                print(f"   • {key}: {value_str}")
            if len(data) > 5:
                print(f"   ... and {len(data) - 5} more keys")
        elif isinstance(data, list):
            print(f"   📊 List with {len(data)} items")
            for i, item in enumerate(data[:3]):
                item_str = str(item)[:100] + "..." if len(str(item)) > 100 else str(item)
                print(f"   [{i}]: {item_str}")
            if len(data) > 3:
                print(f"   ... and {len(data) - 3} more items")
        else:
            data_str = str(data)[:500] + "..." if len(str(data)) > 500 else str(data)
            print(f"   📄 {type(data).__name__}: {data_str}")
    
    async def step_4_llm_selects_action(self, natural_query: str, selected_app: str, available_actions: List[Dict[str, Any]]) -> Optional[Any]:
        """Step 4: Use LLM to select the most appropriate action."""
        print("\n" + "="*80)
        print("🤖 STEP 4: LLM SELECTS ACTION")
        print("="*80)
        print(f"Query: '{natural_query}'")
        print(f"App: {selected_app}")
        print(f"Available actions: {len(available_actions)} options")
        
        try:
            # Prepare action list for LLM (names only for performance)
            action_names = [action_info['name'] for action_info in available_actions]
            
            print(f"🤖 LLM analyzing {len(action_names)} action names...")
            
            # Use Gemini service directly for faster action selection
            actions_info = [{'name': name, 'description': f'Action for {selected_app}'} for name in action_names]
            
            result = await self.composio_llm.gemini_service.select_composio_action(
                natural_query, selected_app, actions_info
            )
            
            if not result:
                print("❌ LLM could not select an action")
                return None
            
            selected_action_name = result.get('selected_action')
            confidence = result.get('confidence', 0.0)
            reasoning = result.get('reasoning', 'No reasoning provided')
            
            # Find the matching action object
            selected_action_object = None
            for action_info in available_actions:
                if action_info['name'] == selected_action_name:
                    selected_action_object = action_info['action_object']
                    break
            
            if not selected_action_object:
                print(f"⚠️ Could not find action object for: {selected_action_name}")
                if available_actions:
                    selected_action_object = available_actions[0]['action_object']
                    selected_action_name = available_actions[0]['name']
                    print(f"   Using first available action: {selected_action_name}")
            
            print(f"\n🎯 LLM SELECTION RESULT:")
            print("-" * 30)
            print(f"   Selected Action: {selected_action_name}")
            print(f"   Confidence: {confidence:.2f}")
            print(f"   Reasoning: {reasoning}")
            
            print(f"\n✅ Step 4 Complete: Selected action '{selected_action_name}' for execution")
            return selected_action_object
            
        except Exception as e:
            print(f"❌ Error in LLM action selection: {str(e)}")
            return None
    
    async def step_5_fetch_action_schema(self, selected_action: Any) -> Optional[Any]:
        """Step 5: Fetch the schema for the selected action."""
        print("\n" + "="*80)
        print("📋 STEP 5: FETCHING ACTION SCHEMA")
        print("="*80)
        print(f"Selected action: {selected_action}")
        
        # Handle fallback actions (strings) vs real action objects
        if isinstance(selected_action, str):
            print("⚠️ Using fallback action - schema unavailable")
            print("   Will proceed with basic parameter extraction in next step")
            return None
        
        try:
            print("🔄 Fetching schema for selected action only (timeout: 15s)...")
            print("🚀 Performance: Only fetching schema for the LLM-selected action")
            
            # Get schema for the selected action with timeout
            # Debug the action object format first
            print(f"   Debug: Action type: {type(selected_action)}")
            print(f"   Debug: Action value: {selected_action}")
            
            # Fixed: Use actions= parameter explicitly to avoid KeyError('name')
            schema = None
            
            try:
                from composio import Action
                
                # Ensure we have a proper Action enum
                if isinstance(selected_action, Action):
                    action_to_use = selected_action
                    print(f"   Using existing Action enum: {action_to_use}")
                else:
                    # Convert to Action enum
                    action_name = str(selected_action).upper()
                    print(f"   Converting to Action enum: {action_name}")
                    action_to_use = Action(action_name)
                
                # FIXED: Use actions= parameter instead of positional argument
                # This prevents the KeyError('name') issue discovered in testing
                print(f"   🔧 Fetching schema using actions= parameter...")
                schema = await asyncio.wait_for(
                    asyncio.to_thread(
                        lambda: self.toolset.get_action_schemas(
                            actions=[action_to_use], 
                            check_connected_accounts=False
                        )
                    ),
                    timeout=15.0
                )
                
                if schema:
                    print(f"   ✅ Schema retrieved successfully! ({len(schema)} schemas)")
                else:
                    print(f"   ⚠️ No schema returned")
                
            except Exception as schema_error:
                print(f"   ❌ Schema fetch error: {str(schema_error)}")
                print(f"   ℹ️ Falling back to basic parameter extraction")
                return None
            
            if not schema:
                print("❌ Could not retrieve action schema from Composio")
                return None
            
            # Handle different schema response formats
            try:
                action_schema = schema[0] if isinstance(schema, list) and schema else schema
            except (IndexError, TypeError) as e:
                print(f"❌ Schema format issue: {str(e)}")
                return None
            
            print(f"\n📄 SCHEMA INFORMATION:")
            print("-" * 30)
            print(f"   Action: {selected_action}")
            
            # Safely extract description and parameters
            try:
                description = getattr(action_schema, 'description', 'No description available')
                print(f"   Description: {description}")
                
                # Extract and display parameters
                parameters_model = getattr(action_schema, 'parameters', None)
                if parameters_model:
                    if hasattr(parameters_model, 'properties'):
                        params = parameters_model.properties
                        print(f"   Parameters: {len(params)} found")
                        
                        print(f"\n🔧 PARAMETER DETAILS:")
                        print("-" * 40)
                        for param_name, param_details in list(params.items())[:10]:  # Show first 10
                            try:
                                # Fixed: Access dictionary keys instead of attributes
                                if isinstance(param_details, dict):
                                    param_type = param_details.get('type', 'unknown')
                                    param_desc = param_details.get('description', 'No description')
                                else:
                                    # Fallback for object-style access
                                    param_type = getattr(param_details, 'type', 'unknown')
                                    param_desc = getattr(param_details, 'description', 'No description')
                                
                                print(f"   • {param_name} ({param_type}): {param_desc[:80]}...")
                            except Exception as param_error:
                                print(f"   • {param_name}: Error reading parameter details - {str(param_error)}")
                        
                        if len(params) > 10:
                            print(f"   ... and {len(params) - 10} more parameters")
                    else:
                        print("   Parameters: Schema format not recognized")
                else:
                    print("   Parameters: None found")
                    
            except Exception as schema_error:
                print(f"   Schema parsing error: {str(schema_error)}")
                print("   Schema may be in unexpected format")
            
            print(f"\n✅ Step 5 Complete: Schema retrieved successfully")
            return action_schema
            
        except asyncio.TimeoutError:
            print("❌ Schema API timeout - will use basic parameter extraction")
            return None
        except Exception as e:
            print(f"❌ Error fetching action schema: {str(e)}")
            print("   This might be due to Composio API issues - will try basic parameter extraction")
            return None
    
    async def _validate_parameters_with_llm(self, natural_query: str, action_name: str, extracted_params: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to validate if parameters are sufficient for the action."""
        try:
            validation_prompt = f"""
Analyze if the following parameters are sufficient to execute the action successfully.

Action: {action_name}
User Query: "{natural_query}"
Extracted Parameters: {extracted_params}

Respond with a JSON object:
{{
    "sufficient": true/false,
    "missing_parameters": ["param1", "param2"],
    "suggestions": "What the user should provide",
    "can_proceed": true/false
}}

Guidelines:
- If basic parameters like "query", "max_results" are missing for search actions, suggest defaults
- If critical parameters like email addresses, recipients, file names are missing, mark as insufficient
- Be helpful and specific about what's missing
"""
            
            response = await self.composio_llm.gemini_service._generate_response(validation_prompt)
            
            if response:
                import json
                try:
                    validation_result = json.loads(response.strip())
                    return validation_result
                except json.JSONDecodeError:
                    # Fallback if LLM doesn't return valid JSON
                    return {"sufficient": True, "can_proceed": True, "missing_parameters": []}
            
        except Exception as e:
            print(f"   ⚠️ Parameter validation error: {str(e)}")
        
        # Default to allowing execution
        return {"sufficient": True, "can_proceed": True, "missing_parameters": []}

    async def step_6_llm_normalizes_parameters(self, natural_query: str, selected_action: Any, action_schema: Optional[Any]) -> Dict[str, Any]:
        """Step 6: Use LLM to normalize parameters from natural language query."""
        print("\n" + "="*80)
        print("🤖 STEP 6: LLM NORMALIZES PARAMETERS")
        print("="*80)
        print(f"Query: '{natural_query}'")
        print(f"Action: {selected_action}")
        
        try:
            normalized_params = {}
            
            if action_schema:
                # Use full schema for parameter normalization
                print("📋 Using full action schema for parameter normalization")
                normalized_params = await self.composio_llm.normalize_parameters_with_llm(
                    natural_query, selected_action, action_schema
                )
            else:
                # Use basic parameter extraction when schema is unavailable
                print("⚠️ Schema unavailable - using basic parameter extraction")
                normalized_params = await self.composio_llm._extract_basic_parameters(
                    natural_query, str(selected_action)
                )
            
            print(f"\n🎯 LLM NORMALIZATION RESULT:")
            print("-" * 40)
            
            if normalized_params:
                print(f"   Parameters extracted: {len(normalized_params)}")
                for key, value in normalized_params.items():
                    # Truncate long values for display
                    display_value = str(value)
                    if len(display_value) > 80:
                        display_value = display_value[:80] + "..."
                    print(f"   • {key}: {display_value}")
            else:
                print("   No parameters extracted")
            
            # Validate parameters with LLM
            print(f"\n🔍 VALIDATING PARAMETERS:")
            print("-" * 30)
            validation_result = await self._validate_parameters_with_llm(
                natural_query, str(selected_action), normalized_params
            )
            
            if not validation_result.get("sufficient", True):
                print("❌ INSUFFICIENT PARAMETERS DETECTED:")
                missing = validation_result.get("missing_parameters", [])
                suggestions = validation_result.get("suggestions", "")
                
                if missing:
                    print(f"   Missing: {', '.join(missing)}")
                if suggestions:
                    print(f"   💡 Suggestion: {suggestions}")
                
                print(f"\n⚠️ Cannot proceed with current parameters")
                print(f"   Please refine your query with more specific information")
                
                # Return special marker to indicate insufficient parameters
                return {"_insufficient_parameters": True, "missing": missing, "suggestions": suggestions}
            else:
                print("✅ Parameters are sufficient for execution")
            
            print(f"\n✅ Step 6 Complete: Parameters normalized from natural language")
            return normalized_params
            
        except Exception as e:
            print(f"❌ Error in LLM parameter normalization: {str(e)}")
            return {}
    
    async def step_7_execute_action(self, selected_action: Any, normalized_params: Dict[str, Any]) -> Dict[str, Any]:
        """Step 7: Execute the action with normalized parameters."""
        print("\n" + "="*80)
        print("🚀 STEP 7: EXECUTING ACTION")
        print("="*80)
        print(f"Action: {selected_action}")
        print(f"Parameters: {len(normalized_params)} provided")
        
        execution_result = {
            'success': False,
            'result': None,
            'error': None,
            'execution_time': None,
            'timestamp': datetime.now().isoformat()
        }
        
        start_time = datetime.now()
        
        try:
            print(f"\n📋 EXECUTION PARAMETERS:")
            print("-" * 30)
            for key, value in normalized_params.items():
                display_value = str(value)
                if len(display_value) > 60:
                    display_value = display_value[:60] + "..."
                print(f"   • {key}: {display_value}")
            
            # Pre-execution: Refresh toolset to ensure latest connections are available
            print(f"\n🔄 Pre-execution: Ensuring fresh Composio client state...")
            self.refresh_composio_client()
            
            # Handle fallback actions (strings) vs real action objects
            if isinstance(selected_action, str):
                print(f"\n⚠️ FALLBACK MODE: Cannot execute fallback action '{selected_action}'")
                print("   This demonstrates the workflow with simulated action")
                print("   In real scenario, would need proper Composio connection")
                
                execution_result['result'] = {
                    'simulated': True,
                    'action': selected_action,
                    'parameters': normalized_params,
                    'message': 'Fallback action demonstration - no actual execution'
                }
                execution_result['success'] = True
                
                print(f"\n🎭 SIMULATED EXECUTION COMPLETE")
                print("-" * 40)
                print("   This shows how the workflow would work with real Composio API")
                print("   Parameters were successfully extracted and would be used for execution")
                
            else:
                print(f"\n🔄 Executing real action with Composio...")
                
                # Execute the action using Composio with timeout
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        lambda: self.toolset.execute_action(
                            action=selected_action,
                            params=normalized_params,
                            entity_id=self.entity_id
                        )
                    ),
                    timeout=30.0
                )
                
                execution_result['result'] = result
                execution_result['success'] = True
                
                print(f"\n🎉 ACTION EXECUTED SUCCESSFULLY!")
                print("-" * 40)
            
            # Display results based on action type
            result = execution_result['result']
            if isinstance(result, dict):
                print(f"📊 Result type: Dictionary")
                print(f"📄 Response keys: {list(result.keys())}")
                
                # Debug: Show the actual result content
                print(f"🔍 DEBUG - Full result content:")
                for key, value in result.items():
                    if key == 'data' and not value:
                        print(f"   {key}: {value} (EMPTY - this might indicate a problem)")
                    else:
                        value_str = str(value)[:200] + "..." if len(str(value)) > 200 else str(value)
                        print(f"   {key}: {value_str}")
                
                # Check for success indicators (be more flexible)
                if result.get('successful') or result.get('successfull') or 'data' in result:
                    if 'data' in result and not result['data']:
                        print("⚠️ Composio reports success but returned empty data")
                        print("   This usually means the action failed silently")
                        print("   Common causes:")
                        print("   • Invalid parameters")
                        print("   • Permission issues") 
                        print("   • API quota exceeded")
                        print("   • Service temporarily unavailable")
                    else:
                        print("✅ Composio reports successful execution")
                    
                    # Display detailed data results
                    if 'data' in result and result['data']:
                        data = result['data']
                        print(f"   📊 Data type: {type(data).__name__}")
                        if isinstance(data, dict):
                            print(f"   🔑 Data keys: {list(data.keys())}")
                        elif isinstance(data, list):
                            print(f"   📋 Data list length: {len(data)}")
                        
                        await self._display_detailed_results(data, str(selected_action))
                    else:
                        print("   📄 No meaningful data returned")
                elif result.get('simulated'):
                    print("🎭 Simulated execution - workflow demonstration complete")
                else:
                    print("⚠️ Execution status unclear from response")
                    print(f"   Debug: Response contains: {list(result.keys())}")
                    # Still try to display data if it exists
                    if 'data' in result:
                        print("   📦 Found data field, attempting to display...")
                        await self._display_detailed_results(result['data'], str(selected_action))
            else:
                print(f"📊 Result type: {type(result).__name__}")
                print(f"📄 Result: {str(result)[:200]}...")
            
        except asyncio.TimeoutError:
            execution_result['error'] = "Execution timeout"
            print("❌ Action execution timed out (30s limit)")
            print("   This may indicate Composio API issues or slow response")
        except Exception as e:
            execution_result['error'] = str(e)
            print(f"❌ Action execution failed: {str(e)}")
            
            # Provide specific troubleshooting based on error type
            error_msg = str(e).lower()
            if 'no connected account' in error_msg:
                print("\n🔧 TROUBLESHOOTING:")
                print("   App account not connected to Composio.")
                print("   Solutions:")
                print("   1. Run: composio add <app_name>")
                print("   2. Complete OAuth flow in browser")
                print("   3. If recently authenticated, the client may need refreshing")
                print("   💡 Try running the workflow again - the client will auto-refresh")
            elif 'unauthorized' in error_msg or 'auth' in error_msg:
                print("\n🔐 AUTHENTICATION ISSUE:")
                print("   App permissions may need to be re-granted.")
                print("   Solutions:")
                print("   1. Try reconnecting the app account")
                print("   2. Refresh the Composio client")
                print("   3. Check if the app requires additional permissions")
        
        finally:
            end_time = datetime.now()
            execution_result['execution_time'] = (end_time - start_time).total_seconds()
            print(f"\n⏱️ Execution time: {execution_result['execution_time']:.2f} seconds")
        
        print(f"\n✅ Step 7 Complete: Action execution attempted")
        return execution_result
    
    async def run_complete_workflow(self, natural_query: str) -> Dict[str, Any]:
        """Run the complete 7-step LLM-driven Composio workflow."""
        print("\n" + "="*80)
        print("🎯 COMPLETE LLM-DRIVEN COMPOSIO WORKFLOW")
        print("="*80)
        print(f"Natural Language Query: '{natural_query}'")
        print(f"Timestamp: {datetime.now().isoformat()}")
        
        workflow_result = {
            'query': natural_query,
            'success': False,
            'steps_completed': 0,
            'selected_app': None,
            'selected_action': None,
            'normalized_parameters': {},
            'execution_result': None,
            'total_time': None,
            'timestamp': datetime.now().isoformat()
        }
        
        workflow_start = datetime.now()
        
        try:
            # Step 1: Fetch Composio apps
            available_apps = await self.step_1_fetch_composio_apps()
            if not available_apps:
                workflow_result['error'] = "Failed to fetch Composio apps"
                return workflow_result
            workflow_result['steps_completed'] = 1
            
            # Step 2: LLM selects app
            selected_app = await self.step_2_llm_selects_app(natural_query, available_apps)
            workflow_result['selected_app'] = selected_app
            workflow_result['steps_completed'] = 2
            
            # Step 2.5: Check authentication and initiate OAuth if needed
            auth_verified = await self.step_2_5_check_and_authenticate_app(selected_app)
            workflow_result['auth_verified'] = auth_verified
            workflow_result['steps_completed'] = 2.5
            
            # If authentication failed, return early for interactive handling
            if not auth_verified:
                workflow_result['error'] = f"Authentication required for {selected_app}"
                workflow_result['needs_auth'] = True
                return workflow_result
            
            # Step 3: Fetch Composio actions
            available_actions = await self.step_3_fetch_composio_actions(selected_app)
            if not available_actions:
                workflow_result['error'] = f"Failed to fetch actions for {selected_app}"
                return workflow_result
            workflow_result['steps_completed'] = 3
            
            # Step 4: LLM selects action
            selected_action = await self.step_4_llm_selects_action(natural_query, selected_app, available_actions)
            if not selected_action:
                workflow_result['error'] = "LLM failed to select an action"
                return workflow_result
            workflow_result['selected_action'] = str(selected_action)
            workflow_result['steps_completed'] = 4
            
            # Step 5: Fetch action schema
            action_schema = await self.step_5_fetch_action_schema(selected_action)
            workflow_result['steps_completed'] = 5
            
            # Step 6: LLM normalizes parameters
            normalized_params = await self.step_6_llm_normalizes_parameters(natural_query, selected_action, action_schema)
            workflow_result['normalized_parameters'] = normalized_params
            workflow_result['steps_completed'] = 6
            
            # Check if parameters are insufficient
            if normalized_params.get("_insufficient_parameters"):
                workflow_result['error'] = "Insufficient parameters provided"
                workflow_result['missing_params'] = normalized_params.get("missing", [])
                workflow_result['suggestions'] = normalized_params.get("suggestions", "")
                workflow_result['needs_more_info'] = True
                return workflow_result
            
            # Step 7: Execute action
            execution_result = await self.step_7_execute_action(selected_action, normalized_params)
            workflow_result['execution_result'] = execution_result
            workflow_result['steps_completed'] = 7
            
            # Mark as successful if we completed all steps
            workflow_result['success'] = True
            
        except Exception as e:
            workflow_result['error'] = str(e)
            print(f"❌ Workflow failed at step {workflow_result['steps_completed']}: {str(e)}")
        
        finally:
            workflow_end = datetime.now()
            workflow_result['total_time'] = (workflow_end - workflow_start).total_seconds()
        
        return workflow_result
    
    def display_workflow_summary(self, workflow_result: Dict[str, Any]):
        """Display a comprehensive summary of the workflow execution."""
        print("\n" + "="*80)
        print("📊 WORKFLOW EXECUTION SUMMARY")
        print("="*80)
        
        print(f"🎯 Query: '{workflow_result['query']}'")
        print(f"⏱️ Total Time: {workflow_result.get('total_time', 0):.2f} seconds")
        print(f"✅ Steps Completed: {workflow_result['steps_completed']}/7")
        print(f"🎉 Overall Success: {'YES' if workflow_result['success'] else 'NO'}")
        
        if workflow_result.get('error'):
            print(f"❌ Error: {workflow_result['error']}")
        
        print(f"\n🔍 WORKFLOW DETAILS:")
        print("-" * 30)
        print(f"   Selected App: {workflow_result.get('selected_app', 'N/A')}")
        print(f"   Authentication: {'✅ Verified' if workflow_result.get('auth_verified') else '⚠️ Not Verified'}")
        print(f"   Selected Action: {workflow_result.get('selected_action', 'N/A')}")
        print(f"   Parameters: {len(workflow_result.get('normalized_parameters', {}))}")
        
        execution_result = workflow_result.get('execution_result')
        if execution_result:
            print(f"   Execution Success: {'YES' if execution_result.get('success') else 'NO'}")
            print(f"   Execution Time: {execution_result.get('execution_time', 0):.2f}s")
        
        print(f"\n📋 STEP BREAKDOWN:")
        print("-" * 30)
        steps = [
            "1. Fetch Composio Apps",
            "2. LLM Selects App", 
            "2.5. Check Authentication & OAuth",
            "3. Fetch Composio Actions",
            "4. LLM Selects Action",
            "5. Fetch Action Schema",
            "6. LLM Normalizes Parameters",
            "7. Execute Action"
        ]
        
        step_numbers = [1, 2, 2.5, 3, 4, 5, 6, 7]
        for step_num, step in zip(step_numbers, steps):
            status = "✅" if step_num <= workflow_result['steps_completed'] else "⏸️"
            print(f"   {status} {step}")


async def main():
    """Main function with interactive mode for testing the complete workflow."""
    print("🚀 INTERACTIVE COMPOSIO WORKFLOW TESTER")
    print("=" * 80)
    print("This test demonstrates the complete LLM-driven Composio workflow:")
    print("1. Fetch Composio apps → 2. LLM selects app → 2.5. Check auth & OAuth →")
    print("3. Fetch actions → 4. LLM selects action → 5. Fetch schema → 6. LLM normalizes → 7. Execute")
    print()
    
    tester = InteractiveComposioWorkflowTester()
    
    # Pre-defined test queries for demonstration
    sample_queries = [
        "Send an email to test@example.com saying hello world",
        "Fetch my recent 5 emails from Gmail inbox", 
        "Get my GitHub profile information",
        "List my GitHub repositories",
        "Create an issue in my repository with title 'Test Issue'"
    ]
    
    print("📋 SAMPLE QUERIES:")
    print("-" * 30)
    for i, query in enumerate(sample_queries, 1):
        print(f"{i}. {query}")
    
    print(f"\n🤖 INTERACTIVE MODE")
    print("=" * 80)
    print("Enter your natural language queries to test the complete workflow!")
    print("Type 'exit' to quit, 'samples' to see sample queries again")
    
    while True:
        try:
            user_query = input("\n📝 Enter your query: ").strip()
            
            if user_query.lower() in ['exit', 'quit', 'q']:
                break
            elif user_query.lower() == 'samples':
                print("\n📋 SAMPLE QUERIES:")
                for i, query in enumerate(sample_queries, 1):
                    print(f"{i}. {query}")
                continue
            elif not user_query:
                continue
            
            print(f"\n🚀 Processing query: '{user_query}'")
            
            # Run the complete workflow
            workflow_result = await tester.run_complete_workflow(user_query)
            
            # Handle special cases before displaying summary
            if workflow_result.get('needs_auth'):
                print(f"\n🔐 AUTHENTICATION REQUIRED:")
                print("-" * 50)
                print(f"The app '{workflow_result['selected_app']}' needs to be connected.")
                print(f"📱 Please visit: https://app.composio.dev/apps")
                print(f"🔗 Or run: composio add {workflow_result['selected_app'].lower()}")
                print(f"\n💡 After connecting, try your query again!")
                continue
            
            if workflow_result.get('needs_more_info'):
                print(f"\n❌ MISSING INFORMATION:")
                print("-" * 50)
                missing = workflow_result.get('missing_params', [])
                suggestions = workflow_result.get('suggestions', '')
                
                if missing:
                    print(f"Missing parameters: {', '.join(missing)}")
                if suggestions:
                    print(f"💡 {suggestions}")
                    
                print(f"\n📝 Please provide a more detailed query and try again!")
                continue
            
            # Display comprehensive summary for successful/completed workflows
            tester.display_workflow_summary(workflow_result)
            
        except KeyboardInterrupt:
            break
        except EOFError:
            break
        except Exception as e:
            print(f"❌ Unexpected error: {str(e)}")
    
    print("\n👋 Workflow testing complete! Goodbye!")


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())