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
    
    def discover_county_feeds(self, county_id):
        """Discover FEEDS by county using the CORRECT Broadcastify Feed API"""
        try:
            # Use the CORRECT API endpoint for FEEDS
            base_url = "https://api.broadcastify.com/audio/"
            
            # Simple API key authentication (not JWT!)
            params = {
                'a': 'county',
                'ctid': county_id,
                'type': 'json',
                'key': st.session_state.api_key
            }
            
            url = f"{base_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
            
            st.info(f"🔍 Trying CORRECT API: {url}")
            st.info(f"📋 Using API Key: {st.session_state.api_key[:10]}...")
            
            response = requests.get(base_url, params=params)
            
            st.info(f"📊 Response Status: {response.status_code}")
            st.info(f"📄 Response Headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                data = response.json()
                st.success(f"✅ SUCCESS! Found feeds for county {county_id}:")
                st.json(data)
                
                discovered = {}
                
                # Parse feed data
                if isinstance(data, list):
                    st.info(f"Found {len(data)} feeds")
                    for feed in data:
                        if isinstance(feed, dict):
                            feed_id = feed.get('feedId') or feed.get('id')
                            description = (feed.get('descr') or 
                                         feed.get('description') or 
                                         feed.get('name') or 
                                         f"Feed {feed_id}")
                            if feed_id:
                                discovered[str(feed_id)] = description
                
                elif isinstance(data, dict):
                    # Handle single feed or nested structure
                    feeds = data.get('feeds', [data])
                    for feed in feeds:
                        if isinstance(feed, dict):
                            feed_id = feed.get('feedId') or feed.get('id')
                            description = (feed.get('descr') or 
                                         feed.get('description') or 
                                         feed.get('name') or 
                                         f"Feed {feed_id}")
                            if feed_id:
                                discovered[str(feed_id)] = description
                
                if discovered:
                    st.success(f"🎉 Successfully discovered {len(discovered)} feeds!")
                else:
                    st.warning("Got 200 response but no feeds found in data structure")
                
                return discovered
            
            elif response.status_code == 401:
                st.error("❌ Authentication failed - check your API key")
                
            elif response.status_code == 404:
                st.warning(f"❌ County {county_id} not found in feed database")
                
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
    
    def discover_what_actually_works(self):
        """Brute force test to find what endpoints actually exist"""
        # First authenticate user
        if not self.authenticate_user():
            st.error("❌ User authentication failed")
            return
        
        # Generate authenticated JWT
        jwt_token = self.generate_jwt(include_user_auth=True)
        if not jwt_token:
            st.error("Failed to generate authenticated JWT")
            return
        
        headers = {"Authorization": f"Bearer {jwt_token}"}
        
        st.subheader("🕵️ Brute Force Endpoint Discovery")
        st.info("Testing every possible endpoint format to see what actually works...")
        
        # Test all possible endpoint variations
        test_variations = [
            # From documentation (but apparently don't work)
            "/calls/v1/groups_county/741",
            "/calls/v1/groups_county/1307", 
            
            # Try different formats
            "/calls/v1/county/741/groups",
            "/calls/v1/county_groups/741",
            "/calls/v1/counties/741/groups",
            
            # Try playlists (these might work)
            "/calls/v1/playlists_public",
            "/calls/v1/playlists_county/741",
            "/calls/v1/playlists_county/1307",
            "/calls/v1/county_playlists/741",
            
            # Try other documented endpoints
            "/calls/v1/playlists_user",
            
            # Maybe there's a browse/search endpoint?
            "/calls/v1/browse",
            "/calls/v1/search",
            "/calls/v1/groups",
            "/calls/v1/counties",
            
            # Maybe it's under a different path?
            "/common/v1/counties",
            "/feeds/v1/counties",
        ]
        
        working_endpoints = []
        
        for endpoint in test_variations:
            try:
                url = f"{self.base_url}{endpoint}"
                response = requests.get(url, headers=headers)
                
                if response.status_code == 200:
                    st.success(f"✅ {endpoint} - WORKS!")
                    working_endpoints.append(endpoint)
                    
                    try:
                        data = response.json()
                        if isinstance(data, list):
                            st.info(f"  Returns list with {len(data)} items")
                            if len(data) > 0 and isinstance(data[0], dict):
                                st.info(f"  Sample keys: {list(data[0].keys())}")
                        elif isinstance(data, dict):
                            st.info(f"  Returns dict with keys: {list(data.keys())}")
                    except:
                        st.info(f"  Non-JSON response")
                        
                elif response.status_code == 404:
                    st.text(f"❌ {endpoint} - Not found")
                elif response.status_code == 401:
                    st.warning(f"🔒 {endpoint} - Auth failed")
                elif response.status_code == 403:
                    st.warning(f"🚫 {endpoint} - Forbidden")
                else:
                    st.info(f"⚠️ {endpoint} - Status {response.status_code}")
                    
            except Exception as e:
                st.error(f"❌ {endpoint} - Error: {e}")
        
        st.subheader("🎯 Working Endpoints Summary")
        if working_endpoints:
            st.success(f"Found {len(working_endpoints)} working endpoints:")
            for endpoint in working_endpoints:
                st.write(f"✅ {endpoint}")
        else:
            st.error("No working endpoints found! Something is wrong with authentication or API access.")
        
        return working_endpoints
    
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
    st.header("🔍 Discover Live Radio Feeds")
    
    # Add success message about using correct API
    st.success("✅ Now using the CORRECT Broadcastify Feed API (not Calls API)!")
    st.info("This will find live audio feeds (what most people want) instead of individual call recordings.")
    
    # Add debug section
    st.subheader("🔬 Test Feed Discovery")
    st.info("Using the correct api.broadcastify.com/audio/ endpoint")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        county_id = st.text_input(
            "Enter County ID for Feed Discovery",
            placeholder="e.g., 741 for Indianapolis",
            help="This uses the correct Broadcastify Feed API"
        )
    
    with col2:
        if st.button("🔍 Discover Feeds", type="primary"):
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
    st.subheader("➕ Manual Feed Addition")
    st.info("Add Feed IDs manually if discovery doesn't find what you need")
    
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        manual_id = st.text_input("Feed ID", placeholder="e.g., 32602")
    with col2:
        manual_name = st.text_input("Feed Name", placeholder="e.g., Indianapolis Metro Police")
    with col3:
        if st.button("➕ Add"):
            if manual_id and manual_name:
                st.session_state.discovered_channels[manual_id] = manual_name
                st.success("Feed added!")
                st.rerun()
    
    st.markdown("---")
    
    # Add explanation of the difference
    st.info("""
    **📻 Feeds vs Calls:**
    - **Feeds** = Live audio streams (like traditional scanner apps)
    - **Calls** = Individual recorded transmissions with metadata
    
    Most users want **Feeds** for live monitoring, which is what this app now discovers!
    """)

def test_county_discovery(county_id, county_name):
    """Test discovery for a specific county using CORRECT API"""
    with st.spinner(f"Discovering feeds in {county_name}..."):
        discovered = monitor.api.discover_county_feeds(county_id)
        if discovered:
            st.session_state.discovered_channels.update(discovered)
            st.success(f"✅ Found {len(discovered)} feeds in {county_name}!")
            st.rerun()
        else:
            st.error(f"❌ No feeds found in {county_name}")

def create_channel_selection():
    """Create feed selection interface"""
    st.header("📻 Feed Selection")
    
    if not st.session_state.discovered_channels:
        st.info("🔍 No feeds discovered yet. Use the Discovery section above to find feeds.")
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
    
    # Feed list
    channel_data = []
    for feed_id, description in st.session_state.discovered_channels.items():
        is_selected = feed_id in st.session_state.selected_channels
        
        channel_data.append({
            "Select": is_selected,
            "Feed ID": feed_id,
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
                "Feed ID": st.column_config.TextColumn("Feed ID", width="medium"),
                "Description": st.column_config.TextColumn("Description", width="large"),
            }
        )
        
        selected_channels = edited_df[edited_df["Select"]]["Feed ID"].tolist()
        if selected_channels != st.session_state.selected_channels:
            st.session_state.selected_channels = selected_channels

def create_monitoring_dashboard():
    """Create monitoring dashboard"""
    st.header("📻 Live Feed Monitor")
    
    # Status indicators
    col1, col2, col3 = st.columns(3)
    
    with col1:
        status = "🟢 RUNNING" if st.session_state.monitor_running else "🔴 STOPPED"
        st.metric("Status", status)
    
    with col2:
        st.metric("Feeds", len(st.session_state.selected_channels))
    
    with col3:
        st.metric("Calls Processed", st.session_state.monitor_stats["calls_processed"])
    
    # Important note about feeds vs calls
    st.warning("🚧 **Note**: This monitor is designed for Calls API but we're now using Feed API. Feed monitoring needs different implementation. For now, this shows the concept.")
    
    # Control buttons
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("▶️ Start Monitoring", disabled=st.session_state.monitor_running):
            if st.session_state.selected_channels:
                st.warning("⚠️ Feed monitoring not fully implemented yet. This is designed for Calls API.")
                # start_monitoring()  # Disabled for now
                # st.success("Monitoring started!")
                # st.rerun()
            else:
                st.warning("Please select feeds first")
    
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
                # Test basic JWT generation (for old API)
                jwt_token = monitor.api.generate_jwt()
                if jwt_token:
                    st.success("✅ JWT generation successful (for Calls API)")
                    
                    # Test authentication (for old API)
                    if monitor.api.authenticate_user():
                        st.success("✅ User authentication successful (for Calls API)")
                        st.success(f"User ID: {st.session_state.user_id}")
                    else:
                        st.error("❌ User authentication failed")
                else:
                    st.error("❌ JWT generation failed")
    
    with col2:
        if st.button("🔍 Test Feed API"):
            with st.spinner("Testing CORRECT Feed API..."):
                # Test the correct Feed API
                discovered = monitor.api.discover_county_feeds("741")  # Test with Indianapolis
                if discovered:
                    st.success(f"✅ Feed API works! Found {len(discovered)} feeds for Indianapolis")
                    for feed_id, name in list(discovered.items())[:3]:  # Show first 3
                        st.info(f"Feed {feed_id}: {name}")
                else:
                    st.error("❌ Feed API test failed")

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
    st.markdown("*Radio Monitor - Now using correct Broadcastify Feed API*")

if __name__ == "__main__":
    main()
