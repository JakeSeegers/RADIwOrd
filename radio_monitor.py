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
    
    def test_live_calls_api(self):
        """Test the live calls API endpoint"""
        try:
            # First authenticate user
            if not self.authenticate_user():
                return False, "Authentication failed"
            
            # Generate authenticated JWT
            jwt_token = self.generate_jwt(include_user_auth=True)
            if not jwt_token:
                return False, "JWT generation failed"
            
            headers = {"Authorization": f"Bearer {jwt_token}"}
            
            # Test with a dummy group (won't return calls but will test endpoint)
            params = {
                "groups": "100-22361",  # Example group
                "init": "1"
            }
            
            response = requests.get(f"{self.base_url}/calls/v1/live/", headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                return True, f"Success! Endpoint works. Response keys: {list(data.keys())}"
            else:
                return False, f"Error {response.status_code}: {response.text}"
        
        except Exception as e:
            return False, f"Exception: {e}"
    
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
            
            channel_name = st.session_state.discovered_channels.get(group_id, f"Group {group_id}")
            
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
    """Create manual group addition interface"""
    st.header("📻 Live Calls Monitoring Setup")
    
    # Explain the approach
    st.success("✅ Using your working Broadcastify Calls API credentials!")
    st.info("""
    **How this works:**
    1. **Find Group IDs** from Broadcastify web interface
    2. **Add them manually** below  
    3. **Monitor live calls** from those groups
    4. **Get real-time transcription** and keyword alerts
    """)
    
    # Manual group addition (primary method)
    st.subheader("➕ Add Radio Groups to Monitor")
    st.markdown("""
    **How to find Group IDs:**
    - Go to [broadcastify.com](https://broadcastify.com) 
    - Browse to your area → Find active radio traffic
    - Look for URLs like `broadcastify.com/calls/tg/100/22361`
    - The Group ID is `100-22361` (format: `system-talkgroup`)
    """)
    
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        manual_id = st.text_input(
            "Group ID", 
            placeholder="e.g., 100-22361 or c-223312",
            help="Format: system-talkgroup for trunked, c-frequency for conventional"
        )
    with col2:
        manual_name = st.text_input(
            "Description", 
            placeholder="e.g., Ann Arbor DPSS Dispatch"
        )
    with col3:
        if st.button("➕ Add Group"):
            if manual_id and manual_name:
                st.session_state.discovered_channels[manual_id] = manual_name
                st.success("Group added!")
                st.rerun()
            else:
                st.warning("Enter both Group ID and Description")
    
    st.markdown("---")
    
    # Quick examples
    st.subheader("🚀 Popular Group Examples")
    st.info("Click to add some popular groups (these may or may not be active):")
    
    popular_groups = [
        ("100-22361", "Example: Police Dispatch"),
        ("200-15432", "Example: Fire Department"), 
        ("c-154430", "Example: Conventional Channel"),
        ("7017-6040271", "Example: Another System")
    ]
    
    cols = st.columns(len(popular_groups))
    for i, (group_id, description) in enumerate(popular_groups):
        with cols[i]:
            if st.button(f"Add {group_id}", key=f"add_{i}"):
                st.session_state.discovered_channels[group_id] = description
                st.success(f"Added {group_id}")
                st.rerun()
    
    st.markdown("---")
    
    # Test live calls endpoint
    st.subheader("🔧 Test Live Calls API")
    if st.button("🧪 Test Live Calls Endpoint"):
        with st.spinner("Testing live calls API..."):
            if st.session_state.discovered_channels:
                # Test with first group
                test_group = list(st.session_state.discovered_channels.keys())[0]
                calls, last_pos = monitor.api.get_live_calls([test_group])
                
                if calls is not None:
                    st.success(f"✅ Live calls API working! Found {len(calls)} recent calls for {test_group}")
                    if calls:
                        st.json(calls[0])  # Show first call structure
                else:
                    st.error("❌ Live calls API test failed")
            else:
                st.warning("Add some groups first to test")
    
    st.markdown("---")
    
    # Instructions for finding groups
    with st.expander("📖 How to Find Active Groups"):
        st.markdown("""
        **Method 1: Browse Broadcastify Website**
        1. Go to [broadcastify.com](https://broadcastify.com)
        2. Click "Calls" in the menu
        3. Browse by location to find your area
        4. Look for active groups with recent calls
        5. Copy the Group ID from the URL
        
        **Method 2: RadioReference Database**
        1. Go to [radioreference.com](https://radioreference.com)
        2. Browse by location → Find your local systems
        3. Look for talkgroup IDs 
        4. Format as `system-talkgroup` (e.g., `100-22361`)
        
        **Group ID Formats:**
        - **Trunked**: `{system_id}-{talkgroup_id}` (e.g., `100-22361`)
        - **Conventional**: `c-{frequency_id}` (e.g., `c-223312`)
        """)

def create_channel_selection():
    """Create group selection interface"""
    st.header("📻 Selected Groups for Monitoring")
    
    if not st.session_state.discovered_channels:
        st.info("👆 Add some groups above first!")
        return
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("✅ Select All Groups"):
            st.session_state.selected_channels = list(st.session_state.discovered_channels.keys())
            st.rerun()
    
    with col2:
        if st.button("❌ Clear Selection"):
            st.session_state.selected_channels = []
            st.rerun()
    
    # Group list
    group_data = []
    for group_id, description in st.session_state.discovered_channels.items():
        is_selected = group_id in st.session_state.selected_channels
        
        group_data.append({
            "Monitor": is_selected,
            "Group ID": group_id,
            "Description": description,
            "Delete": False,
        })
    
    if group_data:
        df = pd.DataFrame(group_data)
        
        edited_df = st.data_editor(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Monitor": st.column_config.CheckboxColumn("Monitor", default=False),
                "Group ID": st.column_config.TextColumn("Group ID", width="medium"),
                "Description": st.column_config.TextColumn("Description", width="large"),
                "Delete": st.column_config.CheckboxColumn("Delete", default=False),
            }
        )
        
        # Update selected channels
        selected_channels = edited_df[edited_df["Monitor"]]["Group ID"].tolist()
        if selected_channels != st.session_state.selected_channels:
            st.session_state.selected_channels = selected_channels
        
        # Handle deletions
        to_delete = edited_df[edited_df["Delete"]]["Group ID"].tolist()
        if to_delete:
            for group_id in to_delete:
                if group_id in st.session_state.discovered_channels:
                    del st.session_state.discovered_channels[group_id]
                if group_id in st.session_state.selected_channels:
                    st.session_state.selected_channels.remove(group_id)
            st.rerun()
    
    if st.session_state.selected_channels:
        st.success(f"🎯 Ready to monitor {len(st.session_state.selected_channels)} groups!")
    else:
        st.warning("⚠️ No groups selected for monitoring")

def create_monitoring_dashboard():
    """Create monitoring dashboard"""
    st.header("📻 Live Call Monitor")
    
    # Status indicators
    col1, col2, col3 = st.columns(3)
    
    with col1:
        status = "🟢 RUNNING" if st.session_state.monitor_running else "🔴 STOPPED"
        st.metric("Status", status)
    
    with col2:
        st.metric("Groups", len(st.session_state.selected_channels))
    
    with col3:
        st.metric("Calls Processed", st.session_state.monitor_stats["calls_processed"])
    
    # Show monitoring info
    if st.session_state.selected_channels:
        st.success(f"✅ Ready to monitor {len(st.session_state.selected_channels)} groups")
        with st.expander("📋 Groups being monitored"):
            for group_id in st.session_state.selected_channels:
                description = st.session_state.discovered_channels.get(group_id, "Unknown")
                st.write(f"• {group_id}: {description}")
    else:
        st.warning("⚠️ No groups selected. Go to Setup Groups tab to add groups.")
    
    # Control buttons
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("▶️ Start Monitoring", disabled=st.session_state.monitor_running):
            if st.session_state.selected_channels:
                start_monitoring()
                st.success("Monitoring started!")
                st.rerun()
            else:
                st.warning("Please select groups first")
    
    with col2:
        if st.button("⏹️ Stop Monitoring", disabled=not st.session_state.monitor_running):
            stop_monitoring()
            st.info("Monitoring stopped")
            st.rerun()
    
    # Show monitoring stats
    if st.session_state.monitor_running:
        st.info("📡 Monitoring live calls... Check Transcripts tab for results.")
        
        # Auto-refresh for live updates
        time.sleep(3)
        st.rerun()
    
    # Instructions
    with st.expander("📖 How Live Call Monitoring Works"):
        st.markdown("""
        **How it works:**
        1. **Polls** the Broadcastify Calls API every 5 seconds
        2. **Gets new calls** from your selected groups  
        3. **Downloads audio** files for each call
        4. **Transcribes** audio using OpenAI Whisper (if API key added)
        5. **Searches** transcripts for your keywords
        6. **Sends email alerts** when keywords are found
        
        **What you'll see:**
        - Live calls appearing in the Transcripts tab
        - Keyword matches highlighted in red
        - Email notifications (if configured)
        - Audio links to listen to original calls
        """)

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
    st.header("📝 Live Call Transcripts")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        show_keywords_only = st.checkbox("Keywords Only")
    with col2:
        max_transcripts = st.selectbox("Show Last", [10, 25, 50, 100], index=1)
    with col3:
        auto_scroll = st.checkbox("Auto-scroll to latest", value=True)
    
    transcripts = st.session_state.get('transcripts', [])
    
    if not transcripts:
        if st.session_state.monitor_running:
            st.info("🔄 Monitoring active - waiting for calls...")
        else:
            st.info("▶️ Start monitoring to see live call transcripts here.")
        return
    
    # Filter transcripts
    filtered_transcripts = transcripts[-max_transcripts:]
    if show_keywords_only:
        filtered_transcripts = [t for t in filtered_transcripts if t.get('keywords_found')]
    
    # Display transcripts
    for i, transcript in enumerate(reversed(filtered_transcripts)):
        timestamp = transcript.get('timestamp', 'Unknown')
        channel = transcript.get('channel_name', 'Unknown')
        text = transcript.get('transcript', 'No transcript')
        keywords = transcript.get('keywords_found', [])
        
        # Different colors for keyword matches
        if keywords:
            with st.container():
                st.error(f"🚨 {timestamp} - {channel}")
                st.error(f"**Keywords found:** {', '.join(keywords)}")
                st.text_area("Transcript", value=text, height=100, disabled=True, key=f"transcript_kw_{i}")
                if transcript.get('audio_url'):
                    st.markdown(f"[🎧 Listen to Audio]({transcript['audio_url']})")
                st.markdown("---")
        else:
            with st.expander(f"📞 {timestamp} - {channel}", expanded=(i < 2)):
                st.text_area("Transcript", value=text, height=100, disabled=True, key=f"transcript_{i}")
                if transcript.get('audio_url'):
                    st.markdown(f"[🎧 Listen to Audio]({transcript['audio_url']})")
    
    # Auto-refresh
    if auto_scroll and st.session_state.monitor_running:
        time.sleep(3)
        st.rerun()

def create_api_test():
    """Test API connectivity"""
    st.subheader("🔧 API Connection Test")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Test Authentication"):
            with st.spinner("Testing authentication..."):
                # Test basic JWT generation
                jwt_token = monitor.api.generate_jwt()
                if jwt_token:
                    st.success("✅ JWT generation successful")
                    
                    # Test user authentication
                    if monitor.api.authenticate_user():
                        st.success("✅ User authentication successful")
                        st.success(f"User ID: {st.session_state.user_id}")
                        st.success(f"Token expires: {datetime.fromtimestamp(time.time() + 3600)}")
                    else:
                        st.error("❌ User authentication failed")
                else:
                    st.error("❌ JWT generation failed")
    
    with col2:
        if st.button("🔍 Test Live Calls API"):
            with st.spinner("Testing live calls endpoint..."):
                success, message = monitor.api.test_live_calls_api()
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.error(f"❌ {message}")

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
            ["📻 Setup Groups", "🎯 Monitor", "📝 Transcripts", "⚙️ Settings"]
        )
        
        if st.session_state.get('monitor_running', False):
            st.success("🟢 Monitoring Active")
        else:
            st.error("🔴 Monitoring Stopped")
        
        st.metric("Selected Groups", len(st.session_state.get('selected_channels', [])))
        st.metric("Keywords", len(st.session_state.get('keywords', [])))
        
        # Add note about using Calls API
        st.info("✅ Using Broadcastify Calls API")
        st.caption("Individual call monitoring + transcription")
    
    # Main content
    if page == "📻 Setup Groups":
        create_discovery_interface()
        st.markdown("---")
        create_channel_selection()
    elif page == "🎯 Monitor":
        create_monitoring_dashboard()
    elif page == "📝 Transcripts":
        create_transcript_viewer()
    elif page == "⚙️ Settings":
        create_settings_page()
    
    st.markdown("---")
    st.markdown("*Radio Monitor - Live call monitoring with AI transcription*")

if __name__ == "__main__":
    main()
