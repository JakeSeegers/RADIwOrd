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

# Try to import AssemblyAI
try:
    import assemblyai as aai
    ASSEMBLYAI_AVAILABLE = True
except ImportError:
    ASSEMBLYAI_AVAILABLE = False

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
    'openai_api_key': '',
    'assemblyai_api_key': '2d7021a9d04f4c0cb952ecc892f3880c',
    'transcription_provider': 'assemblyai'
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
        'monitor_log': [],
        'last_activity': 'Never',
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
    
    def get_live_calls(self, group_ids, last_pos=None):
        """Get live calls for selected groups with detailed logging"""
        try:
            if not self.authenticate_user():
                return [], None
            
            jwt_token = self.generate_jwt(include_user_auth=True)
            headers = {"Authorization": f"Bearer {jwt_token}"}
            
            groups_param = ",".join(group_ids)
            
            params = {"groups": groups_param}
            if last_pos:
                params["pos"] = last_pos
            else:
                params["init"] = 1
            
            # Log the request details
            current_time = datetime.now().strftime('%H:%M:%S')
            log_entry = f"[{current_time}] API Request - Groups: {groups_param}, LastPos: {last_pos}"
            st.session_state.monitor_log.append(log_entry)
            
            response = requests.get(f"{self.base_url}/calls/v1/live/", headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                calls = data.get('calls', [])
                last_pos = data.get('lastPos', int(time.time()))
                
                # Log detailed response info
                log_entry = f"[{current_time}] API Response - Status: 200, Calls: {len(calls)}, LastPos: {last_pos}"
                st.session_state.monitor_log.append(log_entry)
                
                # Log details about each call
                for i, call in enumerate(calls):
                    group_id = call.get('groupId', 'Unknown')
                    call_id = call.get('ts', 'Unknown')
                    duration = call.get('duration', 'Unknown')
                    audio_url = call.get('url', 'No URL')
                    
                    log_entry = f"[{current_time}] Call {i+1}: Group={group_id}, ID={call_id}, Duration={duration}s, HasAudio={bool(audio_url)}"
                    st.session_state.monitor_log.append(log_entry)
                
                return calls, last_pos
            else:
                log_entry = f"[{current_time}] API Error: {response.status_code} - {response.text}"
                st.session_state.monitor_log.append(log_entry)
                st.error(f"Live calls error: {response.status_code}")
                return [], None
        
        except Exception as e:
            current_time = datetime.now().strftime('%H:%M:%S')
            log_entry = f"[{current_time}] Exception in get_live_calls: {e}"
            st.session_state.monitor_log.append(log_entry)
            st.error(f"Live calls error: {e}")
            return [], None

class MultiTranscriber:
    """Multi-provider transcription handler"""
    
    def __init__(self):
        self.providers = {}
        self.active_provider = None
        self.setup_providers()
    
    def setup_providers(self):
        """Initialize all available transcription providers"""
        provider_preference = st.session_state.get('transcription_provider', 'assemblyai')
        
        # Setup AssemblyAI
        if ASSEMBLYAI_AVAILABLE and st.session_state.get('assemblyai_api_key'):
            try:
                aai.settings.api_key = st.session_state.assemblyai_api_key
                self.providers['assemblyai'] = {
                    'name': 'AssemblyAI',
                    'status': '✅ Ready',
                    'cost': 'Low ($0.37/hour)',
                    'speed': 'Fast'
                }
            except Exception as e:
                pass
        
        # Setup OpenAI API
        if OPENAI_AVAILABLE and st.session_state.get('openai_api_key'):
            try:
                self.openai_client = OpenAI(api_key=st.session_state.openai_api_key)
                self.providers['openai'] = {
                    'name': 'OpenAI Whisper API',
                    'status': '✅ Ready',
                    'cost': 'Medium ($0.36/hour)',
                    'speed': 'Medium'
                }
            except Exception as e:
                pass
        
        # Set active provider based on preference and availability
        if provider_preference in self.providers:
            self.active_provider = provider_preference
        elif self.providers:
            self.active_provider = list(self.providers.keys())[0]
        else:
            self.active_provider = None
    
    def transcribe_call(self, audio_url):
        """Transcribe audio using the active provider"""
        if not self.active_provider:
            return "📞 Radio call captured - No transcription provider configured"
        
        provider = self.active_provider
        
        try:
            if provider == 'assemblyai':
                return self._transcribe_assemblyai(audio_url)
            elif provider == 'openai':
                return self._transcribe_openai_api(audio_url)
            else:
                return f"❌ Unknown provider: {provider}"
        except Exception as e:
            return f"❌ {self.providers.get(provider, {}).get('name', 'Unknown')} error: {e}"
    
    def _transcribe_assemblyai(self, audio_url):
        """Transcribe using AssemblyAI (direct URL support)"""
        config = aai.TranscriptionConfig(
            speech_model=aai.SpeechModel.best,
            auto_highlights=False
        )
        
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(audio_url)
        
        if transcript.status == "error":
            return f"❌ AssemblyAI error: {transcript.error}"
        
        text = transcript.text.strip() if transcript.text else ""
        return text if text else "🔇 [No speech detected]"
    
    def _transcribe_openai_api(self, audio_url):
        """Transcribe using OpenAI API"""
        import tempfile
        import os
        
        # Download audio file
        response = requests.get(audio_url, timeout=30)
        if response.status_code != 200:
            return f"❌ Failed to download audio: {response.status_code}"
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
            temp_file.write(response.content)
            temp_file_path = temp_file.name
        
        try:
            # Transcribe with OpenAI Whisper API
            with open(temp_file_path, 'rb') as audio_file:
                transcript = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
            
            return transcript.strip() if transcript.strip() else "🔇 [No speech detected]"
            
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_file_path)
            except:
                pass
    
    def get_status(self):
        """Get current transcription status"""
        if not self.active_provider:
            return "❌ No transcription provider available"
        
        provider_info = self.providers[self.active_provider]
        return f"✅ Using {provider_info['name']} - {provider_info['cost']} - {provider_info['speed']}"
    
    def get_available_providers(self):
        """Get list of available providers for UI"""
        return self.providers

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
        self.transcriber = MultiTranscriber()
        self.keyword_matcher = KeywordMatcher()
        self.last_pos = None
    
    def monitor_loop(self, stop_event):
        """Main monitoring loop with enhanced debugging"""
        while not stop_event.is_set():
            try:
                if not st.session_state.selected_channels:
                    time.sleep(5)
                    continue
                
                # Add to monitoring log
                current_time = datetime.now().strftime('%H:%M:%S')
                log_entry = f"[{current_time}] Starting poll for {len(st.session_state.selected_channels)} groups: {', '.join(st.session_state.selected_channels)}"
                
                st.session_state.monitor_log.append(log_entry)
                
                # Keep only last 50 log entries
                if len(st.session_state.monitor_log) > 50:
                    st.session_state.monitor_log = st.session_state.monitor_log[-50:]
                
                # Get live calls
                calls, self.last_pos = self.api.get_live_calls(st.session_state.selected_channels, self.last_pos)
                
                # Update last activity
                st.session_state.last_activity = current_time
                
                if calls:
                    log_entry = f"[{current_time}] 🎯 Processing {len(calls)} new calls..."
                    st.session_state.monitor_log.append(log_entry)
                    
                    # Process each call with detailed logging
                    for i, call in enumerate(calls):
                        if stop_event.is_set():
                            break
                        
                        try:
                            log_entry = f"[{current_time}] Processing call {i+1}/{len(calls)}: {call.get('ts', 'Unknown')}"
                            st.session_state.monitor_log.append(log_entry)
                            
                            self.process_call(call)
                            st.session_state.monitor_stats["calls_received"] += 1
                            
                            log_entry = f"[{current_time}] ✅ Successfully processed call {i+1}"
                            st.session_state.monitor_log.append(log_entry)
                            
                        except Exception as call_error:
                            log_entry = f"[{current_time}] ❌ Error processing call {i+1}: {call_error}"
                            st.session_state.monitor_log.append(log_entry)
                
                time.sleep(st.session_state.poll_interval)
            
            except Exception as e:
                error_log = f"[{datetime.now().strftime('%H:%M:%S')}] MONITOR ERROR: {e}"
                st.session_state.monitor_log.append(error_log)
                time.sleep(10)
    
    def process_call(self, call):
        """Process individual call with enhanced logging"""
        try:
            group_id = call.get('groupId')
            call_id = call.get('ts', 'Unknown')
            timestamp = datetime.fromtimestamp(call.get('ts', time.time())).strftime('%Y-%m-%d %H:%M:%S')
            audio_url = call.get('url')  # Fixed field name
            duration = call.get('duration', 0)
            
            # Log call processing with more details
            current_time = datetime.now().strftime('%H:%M:%S')
            log_entry = f"[{current_time}] 📞 Call Details: ID={call_id}, Group={group_id}, Duration={duration}s"
            st.session_state.monitor_log.append(log_entry)
            
            channel_name = st.session_state.discovered_channels.get(group_id, f"Group {group_id}")
            
            transcript_data = {
                'timestamp': timestamp,
                'channel_name': channel_name,
                'group_id': group_id,
                'call_id': call_id,
                'audio_url': audio_url,
                'duration': duration,
                'transcript': '',
                'keywords_found': [],
                'raw_call_data': call
            }
            
            if audio_url:
                log_entry = f"[{current_time}] 🎵 Transcribing audio: {audio_url[:50]}..."
                st.session_state.monitor_log.append(log_entry)
                
                transcript = self.transcriber.transcribe_call(audio_url)
                transcript_data['transcript'] = transcript
                
                keywords_found = self.keyword_matcher.find_keywords(transcript)
                transcript_data['keywords_found'] = keywords_found
                
                if keywords_found:
                    st.session_state.monitor_stats["keywords_found"] += 1
                    log_entry = f"[{current_time}] 🚨 KEYWORDS FOUND: {', '.join(keywords_found)}"
                    st.session_state.monitor_log.append(log_entry)
            else:
                log_entry = f"[{current_time}] ⚠️ No audio URL for call {call_id}"
                st.session_state.monitor_log.append(log_entry)
            
            # Add transcript to session state
            st.session_state.transcripts.append(transcript_data)
            
            # Keep only last 100 transcripts
            if len(st.session_state.transcripts) > 100:
                st.session_state.transcripts = st.session_state.transcripts[-100:]
            
            st.session_state.monitor_stats["calls_processed"] += 1
            
            log_entry = f"[{current_time}] ✅ Call {call_id} processed successfully"
            st.session_state.monitor_log.append(log_entry)
            
        except Exception as e:
            error_log = f"[{datetime.now().strftime('%H:%M:%S')}] Call processing error: {e}"
            st.session_state.monitor_log.append(error_log)

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
    1. Go to **[📻 Broadcastify Calls Coverage](https://www.broadcastify.com/calls/coverage/)** 
    2. **Navigate**: Find your area → Look for active systems
    3. **Click on a system** to see talkgroups/channels
    4. **Copy Group ID** from the system details
    5. **Format as** `system-talkgroup` (e.g., `4390-2797`)
    """)
    
    # Add direct link with corrected URL
    st.info("🔗 **[Click here to browse for active radio systems with calls](https://www.broadcastify.com/calls/coverage/)**")
    
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        manual_id = st.text_input(
            "Group ID", 
            placeholder="e.g., 4390-2797 or c-223312",
            help="Format: system-talkgroup for trunked, c-frequency for conventional"
        )
    with col2:
        manual_name = st.text_input(
            "Description", 
            placeholder="e.g., County Fire Dispatch"
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
    st.subheader("🚀 Example Group Format")
    st.info("Click to add an example group (may or may not be active):")
    
    popular_groups = [
        ("4390-2797", "Example: Anderson County Fire"),
        ("100-22361", "Example: Police Dispatch"), 
        ("c-154430", "Example: Conventional Channel"),
    ]
    
    cols = st.columns(len(popular_groups))
    for i, (group_id, description) in enumerate(popular_groups):
        with cols[i]:
            if st.button(f"Add {group_id}", key=f"add_{i}"):
                st.session_state.discovered_channels[group_id] = description
                st.success(f"Added {group_id}")
                st.rerun()

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
    """Create monitoring dashboard with enhanced debugging"""
    st.header("📻 Live Call Monitor")
    
    # Status indicators
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        status = "🟢 RUNNING" if st.session_state.monitor_running else "🔴 STOPPED"
        st.metric("Status", status)
    
    with col2:
        st.metric("Groups", len(st.session_state.selected_channels))
    
    with col3:
        st.metric("Calls Processed", st.session_state.monitor_stats["calls_processed"])
    
    with col4:
        last_activity = st.session_state.get('last_activity', 'Never')
        st.metric("Last Activity", last_activity)
    
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
    
    # Enhanced debugging section
    if st.session_state.monitor_running:
        st.markdown("---")
        st.subheader("🔍 Live Debugging & Monitoring Activity")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🧪 Test API Call Now"):
                with st.spinner("Testing live API call..."):
                    if st.session_state.selected_channels:
                        test_group = st.session_state.selected_channels[0]
                        calls, last_pos = monitor.api.get_live_calls([test_group])
                        
                        st.write(f"**Testing group:** {test_group}")
                        st.write(f"**API Response:** {len(calls) if calls else 0} calls")
                        st.write(f"**Last Position:** {last_pos}")
                        
                        if calls:
                            st.success(f"✅ Got {len(calls)} calls!")
                            with st.expander("Show Raw Call Data"):
                                for i, call in enumerate(calls):
                                    st.json({f"Call {i+1}": call})
                        else:
                            st.info("ℹ️ No new calls (this is normal if no recent activity)")
        
        with col2:
            # Show real-time stats
            st.write("**Real-time Stats:**")
            st.write(f"• Monitoring: {st.session_state.monitor_running}")
            st.write(f"• Groups: {len(st.session_state.selected_channels)}")
            st.write(f"• Poll interval: {st.session_state.poll_interval}s")
            st.write(f"• Total transcripts: {len(st.session_state.get('transcripts', []))}")
            
            # Add manual refresh
            if st.button("🔄 Refresh Stats"):
                st.rerun()
        
        # Show detailed monitoring activity log
        if st.session_state.monitor_log:
            st.subheader("📋 Recent Monitoring Activity (Detailed)")
            
            # Show last 20 log entries
            recent_logs = st.session_state.monitor_log[-20:]
            
            # Use a text area to show logs
            log_text = "\n".join(recent_logs)
            st.text_area("Activity Log", value=log_text, height=300, key="activity_log")
            
            # Clear logs button
            if st.button("🗑️ Clear Activity Log"):
                st.session_state.monitor_log = []
                st.rerun()
        
        st.info("📡 Monitoring active - polls API every 5 seconds. Check activity log above and Transcripts tab for results.")
        
        # Auto-refresh for live updates
        time.sleep(3)
        st.rerun()

def start_monitoring():
    """Start monitoring in background thread"""
    if not st.session_state.monitor_running:
        st.session_state.monitor_running = True
        st.session_state.stop_event = threading.Event()
        st.session_state.monitor_log = []
        
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
    """Create enhanced transcript viewer"""
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
            st.info("💡 If no calls appear, check the Activity Log in the Monitor tab")
        else:
            st.info("▶️ Start monitoring to see live call transcripts here.")
        return
    
    # Filter transcripts
    filtered_transcripts = transcripts[-max_transcripts:]
    if show_keywords_only:
        filtered_transcripts = [t for t in filtered_transcripts if t.get('keywords_found')]
    
    st.success(f"📊 Showing {len(filtered_transcripts)} transcripts (Total: {len(transcripts)})")
    
    # Display transcripts
    for i, transcript in enumerate(reversed(filtered_transcripts)):
        timestamp = transcript.get('timestamp', 'Unknown')
        channel = transcript.get('channel_name', 'Unknown')
        text = transcript.get('transcript', 'No transcript')
        keywords = transcript.get('keywords_found', [])
        duration = transcript.get('duration', 'Unknown')
        call_id = transcript.get('call_id', 'Unknown')
        
        # Different colors for keyword matches
        if keywords:
            with st.container():
                st.error(f"🚨 {timestamp} - {channel}")
                st.error(f"**Keywords found:** {', '.join(keywords)}")
                st.error(f"**Call ID:** {call_id} | **Duration:** {duration}s")
                st.text_area("Transcript", value=text, height=100, disabled=True, key=f"transcript_kw_{i}")
                if transcript.get('audio_url'):
                    st.markdown(f"[🎧 Listen to Audio]({transcript['audio_url']})")
                
                # Show raw call data for debugging
                if st.checkbox(f"Show raw data for call {call_id}", key=f"raw_{i}"):
                    st.json(transcript.get('raw_call_data', {}))
                st.markdown("---")
        else:
            with st.expander(f"📞 {timestamp} - {channel} (ID: {call_id}, {duration}s)", expanded=(i < 2)):
                st.text_area("Transcript", value=text, height=100, disabled=True, key=f"transcript_{i}")
                if transcript.get('audio_url'):
                    st.markdown(f"[🎧 Listen to Audio]({transcript['audio_url']})")
                
                # Show raw call data for debugging
                if st.checkbox(f"Show raw data", key=f"raw_normal_{i}"):
                    st.json(transcript.get('raw_call_data', {}))
    
    # Auto-refresh
    if auto_scroll and st.session_state.monitor_running:
        time.sleep(3)
        st.rerun()

def create_settings_page():
    """Create settings page"""
    st.header("⚙️ Settings & Configuration")
    
    st.subheader("Broadcastify API Configuration")
    
    st.session_state.api_key = st.text_input("API Key", type="password", value=st.session_state.api_key)
    st.session_state.api_key_id = st.text_input("API Key ID", value=st.session_state.api_key_id)
    st.session_state.app_id = st.text_input("App ID", value=st.session_state.app_id)
    st.session_state.username = st.text_input("Username", value=st.session_state.username)
    st.session_state.password = st.text_input("Password", type="password", value=st.session_state.password)
    
    st.markdown("---")
    st.subheader("🎤 Transcription Configuration")
    
    # Show current status
    status = monitor.transcriber.get_status()
    if "✅" in status:
        st.success(status)
    else:
        st.warning(status)
    
    # AssemblyAI Configuration
    with st.expander("🎯 AssemblyAI Configuration (Recommended)", expanded=True):
        st.markdown("""
        **AssemblyAI Benefits:**
        - ✅ **Direct URL processing** (no file downloads needed)
        - ✅ **Fast transcription** (~2-5 seconds per call)
        - ✅ **Good accuracy** for radio communications
        - ✅ **Affordable** at $0.37/hour of audio
        """)
        
        assemblyai_key = st.text_input(
            "AssemblyAI API Key",
            type="password",
            value=st.session_state.get('assemblyai_api_key', ''),
            help="Get your free API key from https://www.assemblyai.com/"
        )
        
        if st.button("💾 Save AssemblyAI Key"):
            st.session_state.assemblyai_api_key = assemblyai_key
            monitor.transcriber = MultiTranscriber()
            if assemblyai_key:
                st.success("✅ AssemblyAI API key saved!")
            else:
                st.info("AssemblyAI key cleared.")
            st.rerun()
    
    # OpenAI Configuration  
    with st.expander("🤖 OpenAI Configuration (Alternative)", expanded=False):
        openai_key = st.text_input(
            "OpenAI API Key",
            type="password", 
            value=st.session_state.get('openai_api_key', ''),
            help="Get your API key from https://platform.openai.com/api-keys"
        )
        
        if st.button("💾 Save OpenAI Key"):
            st.session_state.openai_api_key = openai_key
            monitor.transcriber = MultiTranscriber()
            if openai_key:
                st.success("✅ OpenAI API key saved!")
            else:
                st.info("OpenAI key cleared.")
            st.rerun()
    
    # Test transcription
    st.markdown("---")
    st.subheader("🧪 Test Transcription")
    
    if monitor.transcriber.get_available_providers():
        if st.button("Test Current Provider"):
            # Use one of the recent call URLs if available
            test_calls = st.session_state.get('transcripts', [])
            if test_calls and test_calls[-1].get('raw_call_data', {}).get('url'):
                test_url = test_calls[-1]['raw_call_data']['url']
                with st.spinner("Testing transcription..."):
                    result = monitor.transcriber.transcribe_call(test_url)
                    st.write("**Transcription Result:**")
                    st.text_area("Result", value=result, height=100, key="test_result")
            else:
                st.warning("No recent audio URLs available. Start monitoring first to get test audio.")
    else:
        st.info("Configure at least one transcription provider to test.")
    
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
        
        # Show active transcription provider
        if hasattr(monitor.transcriber, 'active_provider') and monitor.transcriber.active_provider:
            provider_name = {
                'assemblyai': 'AssemblyAI',
                'openai': 'OpenAI'
            }.get(monitor.transcriber.active_provider, 'Unknown')
            st.metric("Transcription", provider_name)
        else:
            st.metric("Transcription", "None")
        
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
