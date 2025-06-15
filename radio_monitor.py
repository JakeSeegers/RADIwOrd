import streamlit as st
import requests
import json
import hmac
import hashlib
import base64
import time
import threading
from datetime import datetime
import pandas as pd

# Page config
st.set_page_config(
    page_title="📻 Radio Monitor",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Try to import OpenAI safely
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Default configuration
DEFAULT_CONFIG = {
    'api_key': 'otL35tw40MzbfjbNRNApY8JggubKsqV1',
    'api_key_id': '79beb9f',
    'app_id': '6818aff92e1ce',
    'username': 'yotaxi1042',
    'password': 'yotaxi1042@avulos.com',
    'whisper_model': 'whisper-1',
    'min_duration': 2,
    'poll_interval': 5,
    'keywords': ['ice', 'immigration', 'federal', 'detain', 'dpss', 'gunshot', 'shots fired', 'officer down'],
    'openai_api_key': ''
}

# Initialize session state
def init_session_state():
    defaults = {
        'monitor_running': False,
        'discovered_channels': {},
        'selected_channels': [],
        'transcripts': [],
        'monitor_stats': {
            "calls_received": 0,
            "calls_processed": 0,
            "keywords_found": 0
        },
        'user_token': None,
        'user_id': None,
        'monitor_thread': None,
        'stop_event': None,
        **DEFAULT_CONFIG
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

class RadioMonitorAPI:
    """Handle Broadcastify API interactions"""
    
    def __init__(self):
        self.base_url = "https://api.bcfy.io"
    
    def generate_jwt(self, include_user_auth=False):
        """Generate JWT token for API authentication"""
        try:
            header = {
                "alg": "HS256",
                "typ": "JWT",
                "kid": st.session_state.api_key_id
            }
            
            current_time = int(time.time())
            payload = {
                "iss": st.session_state.app_id,
                "iat": current_time,
                "exp": current_time + 3600
            }
            
            if include_user_auth and st.session_state.user_token and st.session_state.user_id:
                payload["sub"] = int(st.session_state.user_id)
                payload["utk"] = st.session_state.user_token
            
            # Encode header and payload
            header_encoded = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
            payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
            
            # Create signature
            message = f"{header_encoded}.{payload_encoded}"
            signature = hmac.new(
                st.session_state.api_key.encode(),
                message.encode(),
                hashlib.sha256
            ).digest()
            signature_encoded = base64.urlsafe_b64encode(signature).decode().rstrip('=')
            
            return f"{message}.{signature_encoded}"
        
        except Exception as e:
            st.error(f"JWT generation error: {e}")
            return None
    
    def authenticate_user(self):
        """Authenticate user and get token"""
        try:
            jwt_token = self.generate_jwt()
            if not jwt_token:
                return False
            
            headers = {"Authorization": f"Bearer {jwt_token}"}
            data = {
                "username": st.session_state.username,
                "password": st.session_state.password
            }
            
            response = requests.post(f"{self.base_url}/common/v1/auth", headers=headers, data=data)
            
            if response.status_code == 200:
                auth_data = response.json()
                st.session_state.user_token = auth_data.get('token')
                st.session_state.user_id = auth_data.get('uid')
                return True
            else:
                st.error(f"Authentication failed: {response.status_code}")
                return False
        
        except Exception as e:
            st.error(f"Authentication error: {e}")
            return False
    
    def discover_county_channels(self, county_id):
        """Discover channels by county using AUTHENTICATED user JWT"""
        try:
            # FIRST: Authenticate user to get uid and token
            if not self.authenticate_user():
                st.error("❌ User authentication failed - required for county discovery")
                return {}
            
            # SECOND: Generate JWT with user authentication
            jwt_token = self.generate_jwt(include_user_auth=True)
            if not jwt_token:
                st.error("Failed to generate authenticated JWT token")
                return {}
            
            headers = {"Authorization": f"Bearer {jwt_token}"}
            
            # Use the CORRECT endpoint with AUTHENTICATED JWT
            url = f"{self.base_url}/calls/v1/groups_county/{county_id}"
            
            st.info(f"🔍 Trying with AUTHENTICATED JWT: {url}")
            st.info(f"📋 User ID: {st.session_state.user_id}")
            st.info(f"📋 Headers: Authorization: Bearer {jwt_token[:20]}...")
            
            response = requests.get(url, headers=headers)
            
            st.info(f"📊 Response Status: {response.status_code}")
            st.info(f"📄 Response Headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                data = response.json()
                st.success(f"✅ SUCCESS! County groups found:")
                st.json(data)
                
                discovered = {}
                
                # Handle groups response
                if isinstance(data, dict):
                    groups = data.get('groups', [])
                    if groups:
                        st.info(f"Found {len(groups)} groups in response")
                        for group in groups:
                            if isinstance(group, dict):
                                group_id = group.get('groupId') or group.get('id')
                                description = (group.get('description') or 
                                             group.get('descr') or 
                                             group.get('name') or 
                                             f"Group {group_id}")
                                if group_id:
                                    discovered[str(group_id)] = description
                    else:
                        st.info("Response has 'groups' key but it's empty")
                
                elif isinstance(data, list):
                    st.info(f"Direct list response with {len(data)} items")
                    for group in data:
                        if isinstance(group, dict):
                            group_id = group.get('groupId') or group.get('id')
                            description = (group.get('description') or 
                                         group.get('descr') or 
                                         group.get('name') or 
                                         f"Group {group_id}")
                            if group_id:
                                discovered[str(group_id)] = description
                
                if discovered:
                    st.success(f"🎉 Successfully discovered {len(discovered)} groups!")
                else:
                    st.warning("Got 200 response but no groups found in data structure")
                
                return discovered
            
            elif response.status_code == 401:
                st.error("❌ Authentication failed")
                st.info("Check your Broadcastify credentials in Settings")
                
            elif response.status_code == 404:
                st.warning(f"❌ County {county_id} not found")
                st.info("This could mean:")
                st.markdown("""
                - County ID doesn't exist in the database
                - No Broadcastify Calls coverage for this county
                - County has no active groups
                """)
                
            else:
                st.error(f"❌ Unexpected response: {response.status_code}")
                try:
                    error_data = response.json()
                    st.json(error_data)
                except:
                    st.text(response.text)
            
            return {}
        
        except Exception as e:
            st.error(f"Discovery error: {e}")
            return {}
    
    def test_all_endpoints(self):
        """Test what endpoints actually exist with AUTHENTICATED JWT"""
        # First authenticate user
        if not self.authenticate_user():
            st.error("❌ User authentication failed - required for most endpoints")
            return
        
        # Generate authenticated JWT
        jwt_token = self.generate_jwt(include_user_auth=True)
        if not jwt_token:
            st.error("Failed to generate authenticated JWT")
            return
        
        headers = {"Authorization": f"Bearer {jwt_token}"}
        
        # Test the endpoints from the documentation with AUTHENTICATED JWT
        test_endpoints = [
            ("/calls/v1/playlists_public", "Get all public playlists"),
            ("/calls/v1/groups_county/741", "Get groups for Indianapolis"),
            ("/calls/v1/groups_county/1307", "Get groups for your county"),
            ("/calls/v1/playlists_user", "Get your playlists (auth required)"),
        ]
        
        st.subheader("🔬 API Endpoint Testing (With User Authentication)")
        st.info(f"Testing with User ID: {st.session_state.user_id}")
        
        for endpoint, description in test_endpoints:
            try:
                url = f"{self.base_url}{endpoint}"
                response = requests.get(url, headers=headers)
                
                if response.status_code == 200:
                    st.success(f"✅ {endpoint} - Works!")
                    st.info(f"Description: {description}")
                    data = response.json()
                    if isinstance(data, list):
                        st.info(f"Returns list with {len(data)} items")
                        if len(data) > 0:
                            st.info(f"Sample item keys: {list(data[0].keys()) if isinstance(data[0], dict) else 'Not dict'}")
                    elif isinstance(data, dict):
                        st.info(f"Returns dict with keys: {list(data.keys())}")
                        
                elif response.status_code == 404:
                    st.warning(f"❌ {endpoint} - Not found")
                elif response.status_code == 401:
                    st.error(f"🔒 {endpoint} - Authentication failed")
                else:
                    st.info(f"⚠️ {endpoint} - Status {response.status_code}")
                    try:
                        error_data = response.json()
                        st.json(error_data)
                    except:
                        st.text(response.text[:200])
                    
            except Exception as e:
                st.error(f"❌ {endpoint} - Error: {e}")
        
        # Also try to get all public playlists to see what's available
        st.subheader("📋 Browse Available Public Playlists")
        try:
            url = f"{self.base_url}/calls/v1/playlists_public"
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                st.success(f"✅ Found {len(data) if isinstance(data, list) else 1} public playlists")
                
                if isinstance(data, list) and len(data) > 0:
                    # Show sample playlist structure
                    sample = data[0]
                    st.info("Sample playlist structure:")
                    st.json(sample)
                    
                    # Look for counties
                    counties_found = set()
                    for playlist in data[:10]:  # Check first 10
                        ctids = playlist.get('ctids', [])
                        counties_found.update(ctids)
                    
                    st.info(f"Sample counties with playlists: {sorted(list(counties_found))[:10]}")
                    
        except Exception as e:
            st.error(f"Error browsing public playlists: {e}")
        
        return
    
    def get_live_calls(self, group_ids, last_pos=None):
        """Get live calls for selected groups"""
        try:
            if not self.authenticate_user():
                return [], None
            
            jwt_token = self.generate_jwt(include_user_auth=True)
            headers = {"Authorization": f"Bearer {jwt_token}"}
            
            groups_param = ",".join(group_ids[:5])
            
            params = {"groups": groups_param}
            if last_pos:
                params["pos"] = last_pos
            else:
                params["init"] = 1
            
            response = requests.get(f"{self.base_url}/calls/v1/live/", headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                calls = data.get('calls', [])
                last_pos = data.get('lastPos', int(time.time()))
                return calls, last_pos
            else:
                st.error(f"Live calls error: {response.status_code}")
                return [], None
        
        except Exception as e:
            st.error(f"Live calls error: {e}")
            return [], None

class SimpleTranscriber:
    """Simple transcription handler"""
    
    def __init__(self):
        self.client = None
        if OPENAI_AVAILABLE and st.session_state.get('openai_api_key'):
            try:
                self.client = OpenAI(api_key=st.session_state.openai_api_key)
            except Exception as e:
                st.error(f"OpenAI client setup error: {e}")
    
    def transcribe_call(self, audio_url):
        """Simple transcription placeholder"""
        if not self.client:
            return "📞 Radio call captured - Add OpenAI API key for transcription"
        
        # For now, return a placeholder - real transcription would download and process audio
        return f"📞 Call captured from {audio_url[:30]}... - [Transcription with OpenAI coming soon]"

class KeywordMatcher:
    """Handle keyword detection"""
    
    def __init__(self):
        self.keywords = [kw.lower() for kw in st.session_state.keywords]
    
    def find_keywords(self, text):
        """Find keywords in text"""
        if not text:
            return []
        
        text_lower = text.lower()
        found = []
        
        for keyword in self.keywords:
            if keyword in text_lower:
                found.append(keyword)
        
        return found

class RadioMonitor:
    """Main monitoring class"""
    
    def __init__(self):
        self.api = RadioMonitorAPI()
        self.transcriber = SimpleTranscriber()
        self.keyword_matcher = KeywordMatcher()
        self.last_pos = None
    
    def monitor_loop(self, stop_event):
        """Main monitoring loop"""
        while not stop_event.is_set():
            try:
                if not st.session_state.selected_channels:
                    time.sleep(5)
                    continue
                
                calls, self.last_pos = self.api.get_live_calls(st.session_state.selected_channels, self.last_pos)
                
                for call in calls:
                    if stop_event.is_set():
                        break
                    
                    self.process_call(call)
                    st.session_state.monitor_stats["calls_received"] += 1
                
                time.sleep(st.session_state.poll_interval)
            
            except Exception as e:
                st.error(f"Monitor loop error: {e}")
                time.sleep(10)
    
    def process_call(self, call):
        """Process individual call"""
        try:
            group_id = call.get('groupId')
            timestamp = datetime.fromtimestamp(call.get('ts', time.time())).strftime('%Y-%m-%d %H:%M:%S')
            audio_url = call.get('audioUrl')
            
            channel_name = st.session_state.discovered_channels.get(group_id, f"Channel {group_id}")
            
            transcript_data = {
                'timestamp': timestamp,
                'channel_name': channel_name,
                'group_id': group_id,
                'audio_url': audio_url,
                'transcript': '',
                'keywords_found': []
            }
            
            if audio_url:
                transcript = self.transcriber.transcribe_call(audio_url)
                transcript_data['transcript'] = transcript
                
                keywords_found = self.keyword_matcher.find_keywords(transcript)
                transcript_data['keywords_found'] = keywords_found
                
                if keywords_found:
                    st.session_state.monitor_stats["keywords_found"] += 1
            
            st.session_state.transcripts.append(transcript_data)
            
            if len(st.session_state.transcripts) > 100:
                st.session_state.transcripts = st.session_state.transcripts[-100:]
            
            st.session_state.monitor_stats["calls_processed"] += 1
        
        except Exception as e:
            st.error(f"Call processing error: {e}")

# Initialize session state
init_session_state()

# Create monitor instance
monitor = RadioMonitor()

# ===================================================================
# UI FUNCTIONS
# ===================================================================

def create_discovery_interface():
    """Create channel discovery interface"""
    st.header("🔍 Discover Live Radio Channels")
    
    # Add debug section
    st.subheader("🔬 Debug County Discovery")
    st.info("This will show detailed debug info to figure out why discovery isn't working")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        county_id = st.text_input(
            "Enter County ID for Debug Test",
            placeholder="e.g., 741 for Indianapolis",
            help="This will show detailed API response info"
        )
    
    with col2:
        if st.button("🔍 Debug Discovery", type="primary"):
            if county_id:
                test_county_discovery(county_id, f"County {county_id}")
            else:
                st.warning("Please enter a County ID")
    
    st.markdown("---")
    
    # Add quick test buttons for known working counties
    st.subheader("🚀 Quick Test - Try Popular Counties")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("🏙️ Indianapolis (741)"):
            test_county_discovery("741", "Marion County, IN")
    
    with col2:
        if st.button("🍑 Atlanta (442)"):
            test_county_discovery("442", "Fulton County, GA")
    
    with col3:
        if st.button("🏫 Ann Arbor (2733)"):
            test_county_discovery("2733", "Washtenaw County, MI")
    
    with col4:
        if st.button("🌴 Orlando (1706)"):
            test_county_discovery("1706", "Orange County, FL")
    
    st.markdown("---")
    
    # Manual group addition
    st.subheader("➕ Manual Group Addition")
    st.info("If discovery doesn't work, manually add Group IDs from the web interface")
    
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        manual_id = st.text_input("Group ID", placeholder="e.g., 100-22361 or c-223312")
    with col2:
        manual_name = st.text_input("Channel Name", placeholder="e.g., Ann Arbor DPSS")
    with col3:
        if st.button("➕ Add"):
            if manual_id and manual_name:
                st.session_state.discovered_channels[manual_id] = manual_name
                st.success("Channel added!")
                st.rerun()

def test_county_discovery(county_id, county_name):
    """Test discovery for a specific county"""
    with st.spinner(f"Discovering channels in {county_name}..."):
        discovered = monitor.api.discover_county_channels(county_id)
        if discovered:
            st.session_state.discovered_channels.update(discovered)
            st.success(f"✅ Found {len(discovered)} channels in {county_name}!")
            st.rerun()
        else:
            st.error(f"❌ No channels found in {county_name}")

def create_channel_selection():
    """Create channel selection interface"""
    st.header("📻 Channel Selection")
    
    if not st.session_state.discovered_channels:
        st.info("🔍 No channels discovered yet. Use the Discovery section above to find channels.")
        return
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("✅ Select All"):
            st.session_state.selected_channels = list(st.session_state.discovered_channels.keys())
            st.rerun()
    
    with col2:
        if st.button("❌ Clear All"):
            st.session_state.selected_channels = []
            st.rerun()
    
    # Channel list
    channel_data = []
    for channel_id, description in st.session_state.discovered_channels.items():
        is_selected = channel_id in st.session_state.selected_channels
        
        channel_data.append({
            "Select": is_selected,
            "Channel ID": channel_id,
            "Description": description,
        })
    
    if channel_data:
        df = pd.DataFrame(channel_data)
        
        edited_df = st.data_editor(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Select": st.column_config.CheckboxColumn("Select", default=False),
                "Channel ID": st.column_config.TextColumn("Channel ID", width="medium"),
                "Description": st.column_config.TextColumn("Description", width="large"),
            }
        )
        
        selected_channels = edited_df[edited_df["Select"]]["Channel ID"].tolist()
        if selected_channels != st.session_state.selected_channels:
            st.session_state.selected_channels = selected_channels

def create_monitoring_dashboard():
    """Create monitoring dashboard"""
    st.header("📻 Live Radio Monitor")
    
    # Status indicators
    col1, col2, col3 = st.columns(3)
    
    with col1:
        status = "🟢 RUNNING" if st.session_state.monitor_running else "🔴 STOPPED"
        st.metric("Status", status)
    
    with col2:
        st.metric("Channels", len(st.session_state.selected_channels))
    
    with col3:
        st.metric("Calls Processed", st.session_state.monitor_stats["calls_processed"])
    
    # Control buttons
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("▶️ Start Monitoring", disabled=st.session_state.monitor_running):
            if st.session_state.selected_channels:
                start_monitoring()
                st.success("Monitoring started!")
                st.rerun()
            else:
                st.warning("Please select channels first")
    
    with col2:
        if st.button("⏹️ Stop Monitoring", disabled=not st.session_state.monitor_running):
            stop_monitoring()
            st.info("Monitoring stopped")
            st.rerun()
    
    # Auto-refresh for live updates
    if st.session_state.monitor_running:
        time.sleep(3)
        st.rerun()

def start_monitoring():
    """Start monitoring in background thread"""
    if not st.session_state.monitor_running:
        st.session_state.monitor_running = True
        st.session_state.stop_event = threading.Event()
        
        def monitor_worker():
            monitor.monitor_loop(st.session_state.stop_event)
        
        st.session_state.monitor_thread = threading.Thread(target=monitor_worker, daemon=True)
        st.session_state.monitor_thread.start()

def stop_monitoring():
    """Stop monitoring"""
    st.session_state.monitor_running = False
    if st.session_state.stop_event:
        st.session_state.stop_event.set()

def create_transcript_viewer():
    """Create transcript viewer"""
    st.header("📝 Live Transcripts")
    
    transcripts = st.session_state.get('transcripts', [])
    
    if not transcripts:
        st.info("No transcripts yet. Start monitoring to see live call activity.")
        return
    
    # Display recent transcripts
    for i, transcript in enumerate(reversed(transcripts[-25:])):
        timestamp = transcript.get('timestamp', 'Unknown')
        channel = transcript.get('channel_name', 'Unknown')
        text = transcript.get('transcript', 'No transcript')
        keywords = transcript.get('keywords_found', [])
        
        with st.expander(f"{timestamp} - {channel}", expanded=(i < 3)):
            if keywords:
                st.warning(f"🚨 Keywords found: {', '.join(keywords)}")
            
            st.text_area("Call Info", value=text, height=100, disabled=True, key=f"transcript_{i}")
            
            if transcript.get('audio_url'):
                st.markdown(f"[🎧 Listen to Audio]({transcript['audio_url']})")

def create_api_test():
    """Test API connectivity"""
    st.subheader("🔧 API Connection Test")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Test Basic Connection"):
            with st.spinner("Testing API connection..."):
                # Test basic JWT generation
                jwt_token = monitor.api.generate_jwt()
                if jwt_token:
                    st.success("✅ JWT generation successful")
                    
                    # Test authentication
                    if monitor.api.authenticate_user():
                        st.success("✅ User authentication successful")
                        st.success(f"User ID: {st.session_state.user_id}")
                        st.success(f"Token expires: {datetime.fromtimestamp(time.time() + 3600)}")
                    else:
                        st.error("❌ User authentication failed")
                else:
                    st.error("❌ JWT generation failed")
    
    with col2:
        if st.button("🔬 Test All Endpoints"):
            with st.spinner("Testing all API endpoints..."):
                monitor.api.test_all_endpoints()

def create_settings_page():
    """Create settings page"""
    st.header("⚙️ Settings & Configuration")
    
    st.subheader("Broadcastify API Configuration")
    
    st.session_state.api_key = st.text_input("API Key", type="password", value=st.session_state.api_key)
    st.session_state.api_key_id = st.text_input("API Key ID", value=st.session_state.api_key_id)
    st.session_state.app_id = st.text_input("App ID", value=st.session_state.app_id)
    st.session_state.username = st.text_input("Username", value=st.session_state.username)
    st.session_state.password = st.text_input("Password", type="password", value=st.session_state.password)
    
    # Add API testing
    create_api_test()
    
    st.markdown("---")
    st.subheader("Keywords")
    
    keywords_text = st.text_area(
        "Keywords (one per line)",
        value="\n".join(st.session_state.keywords),
        height=150
    )
    
    if st.button("💾 Save Keywords"):
        keyword_list = [kw.strip().lower() for kw in keywords_text.split('\n') if kw.strip()]
        st.session_state.keywords = keyword_list
        st.success(f"Saved {len(keyword_list)} keywords")
    
    st.markdown("---")
    st.subheader("OpenAI Transcription (Optional)")
    
    openai_key = st.text_input(
        "OpenAI API Key", 
        type="password",
        value=st.session_state.get('openai_api_key', ''),
        help="Get your API key from https://platform.openai.com/api-keys"
    )
    
    if st.button("💾 Save OpenAI Key"):
        st.session_state.openai_api_key = openai_key
        monitor.transcriber = SimpleTranscriber()
        if openai_key:
            st.success("✅ OpenAI API key saved!")
        else:
            st.info("OpenAI key cleared.")

# ===================================================================
# MAIN APPLICATION
# ===================================================================

def main():
    """Main Streamlit application"""
    
    with st.sidebar:
        st.title("📻 Radio Monitor")
        
        page = st.selectbox(
            "Navigation",
            ["🔍 Discovery", "📻 Monitor", "📝 Transcripts", "⚙️ Settings"]
        )
        
        if st.session_state.get('monitor_running', False):
            st.success("🟢 Monitoring Active")
        else:
            st.error("🔴 Monitoring Stopped")
        
        st.metric("Selected Channels", len(st.session_state.get('selected_channels', [])))
        st.metric("Keywords", len(st.session_state.get('keywords', [])))
    
    # Main content
    if page == "🔍 Discovery":
        create_discovery_interface()
        st.markdown("---")
        create_channel_selection()
    elif page == "📻 Monitor":
        create_monitoring_dashboard()
    elif page == "📝 Transcripts":
        create_transcript_viewer()
    elif page == "⚙️ Settings":
        create_settings_page()
    
    st.markdown("---")
    st.markdown("*Radio Monitor - Real-time radio monitoring*")

if __name__ == "__main__":
    main()
