"""
Marathon Production - Web Version for Railway
A web-based interface for Odoo production automation
"""

import os
import json
import logging
import time
import re
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from flask import Flask, render_template, request, jsonify, send_file, session
from flask_socketio import SocketIO, emit
import threading
import queue

# Browser automation (optional - disabled for Railway)
# Browser automation
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
PLAYWRIGHT_AVAILABLE = True

# QR Code generation
from PIL import Image, ImageDraw, ImageFont
import qrcode
import io
import base64

# API requests
import requests

# =============================================================================
# CONFIGURATION
# =============================================================================

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'marathon-production-secret-key-change-me')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# URLs
LOGIN_URL = "https://hexmodal.odoo.com/web/login"
STARTING_URL = "https://hexmodal.odoo.com/web#action=510&model=mrp.production&view_type=list&cids=1&menu_id=324"
HEXMODAL_URL = "https://dashboard.hexmodal.com"
HEXMODAL_API_URL = "https://dashboard.hexmodal.com/api/lights/dt/elights-list/"

# Data directory
DATA_DIR = Path(os.environ.get('DATA_DIR', '/tmp/marathon_data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
BATCH_HISTORY_FILE = DATA_DIR / "batch_history.json"
STATISTICS_FILE = DATA_DIR / "statistics.json"

# Browser profile directory
BROWSER_PROFILE_DIR = Path(os.environ.get('BROWSER_PROFILE', '/tmp/browser_profile'))
BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

# Device names for product selection
DEVICE_NAMES = [
    "BUTT-RedSquare", "CONN-Ext", "CR-7007GX", "CR-7007RX", "CR-7033A",
    "CR-7082", "CR-7108R", "DR-LT", "E-LightShell-NYC", "ExitSignShell-NYC",
    "FHUPS1-UNV-12L-SD", "FHUPS1-UNV-50L-SD", "HEX-A-1", "HEX-A-2", "HEX-A-R-1",
    "HEX-A-R-2", "HEX-C-2", "HEX-C-B-R", "HEX-C-G", "HEX-C-R", "HEX-D-P",
    "HEX-F", "HEX-F-Kit", "HEX-G", "HEX-L-S", "HEX-L-S-UNTESTED", "HEX-L-Z",
    "HEX-L-Z-UNTESTED", "HEX-M", "HEX-MOD-DHT", "HEX-MOD-DHT-UNCERT", 
    "HEX-MOD-LHT", "HEX-MOD-LHT-NOSERIAL", "HEX-MOD-LHT-UNCERT", "HEX-MOD-SDP", 
    "HEX-MOD-SDP-NOSERIAL", "HEX-MOD-SDP-UNCERT", "HEX-MOD-SHT", 
    "HEX-MOD-SHT-NOSERIAL", "HEX-MOD-SHT-UNCERT", "HEX-MOD-ULT", 
    "HEX-MOD-ULT-NOSERIAL", "HEX-MOD-ULT-UNCERT", "HEX-N", "HEX-P", 
    "HEX-P-UNCAL", "HEX-P-UNCERT", "HEX-R-R", "HEX-T-Base", "HEX-T-C", 
    "HEX-T-C-KIT", "HEX-T-C-UNCERT", "HEX-T-R", "HEX-T-R-UNCERT", "HEX-T-ULT", 
    "HEX-W", "HEX-W-4", "HEX-X-B-R", "HEX-X-G", "HEX-X-R", "HIS-HEX-A-C-1", 
    "HIS-HEX-C-G", "HIS-HEX-C-R", "HIS-HEX-L-S", "HIS-HEX-N", "HIS-HEX-P", 
    "HIS-HEX-R-R", "HIS-HEX-T-C", "HIS-HEX-W", "HIS-HEX-X-G", "HIS-HEX-X-R", 
    "Hex-A-C-1", "Hex-A-C-2", "Hex-A-G", "Hex-D-S", "LEDIndicator-01", 
    "LEDStrip-Green", "LEDStrip-NYC", "LEDStrip-Red"
]

# =============================================================================
# DATA CLASSES
# =============================================================================

class BatchHistory:
    """Manage batch history."""
    MAX_BATCHES = 50
    
    @staticmethod
    def load() -> List[Dict]:
        try:
            if BATCH_HISTORY_FILE.exists():
                with open(BATCH_HISTORY_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logging.warning(f"Could not load batch history: {e}")
        return []
    
    @staticmethod
    def save(history: List[Dict]):
        try:
            with open(BATCH_HISTORY_FILE, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            logging.error(f"Could not save batch history: {e}")
    
    @staticmethod
    def add(serials: List[str], product: str, success: bool):
        history = BatchHistory.load()
        batch = {
            'timestamp': datetime.now().isoformat(),
            'serials': serials,
            'count': len(serials),
            'product': product,
            'success': success
        }
        history.insert(0, batch)
        history = history[:BatchHistory.MAX_BATCHES]
        BatchHistory.save(history)


class Statistics:
    """Track production statistics."""
    
    @staticmethod
    def load() -> Dict:
        try:
            if STATISTICS_FILE.exists():
                with open(STATISTICS_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logging.warning(f"Could not load statistics: {e}")
        return {
            'daily': {},
            'products': {},
            'total_serials': 0,
            'total_batches': 0,
            'success_count': 0,
            'error_count': 0
        }
    
    @staticmethod
    def save(data: Dict):
        try:
            with open(STATISTICS_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logging.error(f"Could not save statistics: {e}")
    
    @staticmethod
    def record_batch(serial_count: int, product: str, success: bool):
        data = Statistics.load()
        today = datetime.now().strftime("%Y-%m-%d")
        
        if today not in data['daily']:
            data['daily'][today] = {'serials': 0, 'batches': 0, 'success': 0, 'errors': 0}
        
        data['daily'][today]['serials'] += serial_count
        data['daily'][today]['batches'] += 1
        if success:
            data['daily'][today]['success'] += 1
        else:
            data['daily'][today]['errors'] += 1
        
        if product not in data['products']:
            data['products'][product] = 0
        data['products'][product] += serial_count
        
        data['total_serials'] += serial_count
        data['total_batches'] += 1
        if success:
            data['success_count'] += 1
        else:
            data['error_count'] += 1
        
        Statistics.save(data)
    
    @staticmethod
    def get_today() -> Dict:
        data = Statistics.load()
        today = datetime.now().strftime("%Y-%m-%d")
        return data['daily'].get(today, {'serials': 0, 'batches': 0, 'success': 0, 'errors': 0})


# =============================================================================
# SERIAL VALIDATION
# =============================================================================

def clean_serials(raw_text: str) -> List[str]:
    """Extract serial numbers from raw input."""
    cleaned = []
    for line in raw_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        # Extract from URL if present
        match = re.search(r"[?&]s=([A-Za-z0-9._-]+)", line)
        serial = match.group(1) if match else line
        if serial and len(serial) >= 2:
            cleaned.append(serial)
    return cleaned


def validate_serials(serials: List[str]) -> Dict:
    """Validate serial numbers."""
    results = {'valid': [], 'duplicates': [], 'invalid': []}
    seen = set()
    
    for serial in serials:
        serial = serial.strip()
        if not serial:
            continue
        if serial in seen:
            results['duplicates'].append(serial)
            continue
        seen.add(serial)
        
        if len(serial) < 2:
            results['invalid'].append((serial, "Too short"))
        elif len(serial) > 50:
            results['invalid'].append((serial, "Too long"))
        elif not re.match(r'^[A-Za-z0-9._-]+$', serial):
            results['invalid'].append((serial, "Invalid characters"))
        else:
            results['valid'].append(serial)
    
    return results


def detect_product(serial: str) -> Optional[str]:
    """Detect product from serial number prefix."""
    serial_upper = serial.upper()
    
    patterns = [
        ("HEX-MOD-DHT", ["HEX-MOD-DHT", "HEXMODDHT"]),
        ("HEX-MOD-LHT", ["HEX-MOD-LHT", "HEXMODLHT"]),
        ("HEX-MOD-SHT", ["HEX-MOD-SHT", "HEXMODSHT"]),
        ("HEX-MOD-SDP", ["HEX-MOD-SDP", "HEXMODSDP"]),
        ("HEX-MOD-ULT", ["HEX-MOD-ULT", "HEXMODULT"]),
        ("HEX-T-C", ["HEX-T-C", "HEXTC"]),
        ("HEX-T-R", ["HEX-T-R", "HEXTR"]),
        ("HEX-P", ["HEX-P", "HEXP"]),
        ("HEX-N", ["HEX-N", "HEXN"]),
        ("HEX-W", ["HEX-W", "HEXW"]),
        ("HEX-G", ["HEX-G", "HEXG"]),
        ("HEX-L-S", ["HEX-L-S", "HEXLS"]),
        ("HEX-L-Z", ["HEX-L-Z", "HEXLZ"]),
    ]
    
    for product, prefixes in patterns:
        for prefix in prefixes:
            if serial_upper.startswith(prefix):
                return product
    
    return None


# =============================================================================
# QR CODE GENERATION
# =============================================================================

def generate_qr_label(serial: str) -> str:
    """Generate QR label as base64 PNG."""
    # Create QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(f"https://dashboard.hexmodal.com/lights/?s={serial}")
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    
    # Create label
    label_width, label_height = 400, 200
    label = Image.new('RGB', (label_width, label_height), 'white')
    draw = ImageDraw.Draw(label)
    
    # Resize and paste QR
    qr_size = 160
    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
    label.paste(qr_img, (20, 20))
    
    # Add text
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except:
        font = ImageFont.load_default()
        small_font = font
    
    draw.text((200, 50), serial, fill='black', font=font)
    draw.text((200, 85), "Scan for compliance", fill='gray', font=small_font)
    draw.text((200, 120), "dashboard.hexmodal.com", fill='#0066cc', font=small_font)
    
    # Convert to base64
    buffer = io.BytesIO()
    label.save(buffer, format='PNG')
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode()


def generate_labels_pdf(serials: List[str]) -> bytes:
    """Generate a PDF with all QR labels for printing."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.units import inch
    
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Label dimensions (2.25" x 1.25" like DYMO 30256)
    label_width = 2.25 * inch
    label_height = 1.25 * inch
    margin = 0.5 * inch
    
    # Calculate grid
    cols = int((width - 2 * margin) / label_width)
    rows = int((height - 2 * margin) / label_height)
    
    for i, serial in enumerate(serials):
        page_idx = i // (cols * rows)
        pos_on_page = i % (cols * rows)
        col = pos_on_page % cols
        row = pos_on_page // cols
        
        if pos_on_page == 0 and i > 0:
            c.showPage()
        
        x = margin + col * label_width
        y = height - margin - (row + 1) * label_height
        
        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=3, border=1)
        qr.add_data(f"https://dashboard.hexmodal.com/lights/?s={serial}")
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Save QR temporarily
        qr_buffer = io.BytesIO()
        qr_img.save(qr_buffer, format='PNG')
        qr_buffer.seek(0)
        
        from reportlab.lib.utils import ImageReader
        qr_reader = ImageReader(qr_buffer)
        
        # Draw QR
        qr_size = 0.8 * inch
        c.drawImage(qr_reader, x + 5, y + 10, width=qr_size, height=qr_size)
        
        # Draw text
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x + qr_size + 15, y + label_height - 25, serial)
        c.setFont("Helvetica", 8)
        c.drawString(x + qr_size + 15, y + label_height - 40, "Scan for compliance")
    
    c.save()
    buffer.seek(0)
    return buffer.read()


# =============================================================================
# BROWSER AUTOMATION (Headless)
# =============================================================================

class MarathonRobot:
    """Handles Odoo browser automation in headless mode."""
    
    def __init__(self, emit_status):
        self.emit_status = emit_status
        self.playwright = None
        self.browser = None
        self.is_running = False
    
    def emit(self, message: str, status: str = "info"):
        """Emit status to websocket."""
        self.emit_status(message, status)
        logging.info(f"[{status}] {message}")
    
    def ensure_browser(self):
        """Ensure browser is running."""
        if self.playwright is None:
            self.emit("Starting browser engine...")
            self.playwright = sync_playwright().start()
        
        if self.browser is None:
            self.emit("Launching headless browser...")
            self.browser = self.playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
    
    def cleanup(self):
        """Clean up resources."""
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except:
            pass
        finally:
            self.browser = None
            self.playwright = None
    
    def run_marathon(self, product: str, serials: List[str], odoo_email: str, odoo_password: str) -> bool:
        """Execute the Odoo production workflow."""
        if self.is_running:
            return False
        
        self.is_running = True
        success = False
        context = None
        page = None
        
        try:
            self.ensure_browser()
            
            # Create new context and page
            context = self.browser.new_context()
            page = context.new_page()
            
            quantity = len(serials)
            serials_text = "\n".join(serials)
            
            # Step 1: Login
            self.emit("📍 Step 1/10: Logging into Odoo...")
            page.goto(LOGIN_URL, timeout=30000)
            page.wait_for_timeout(2000)
            
            if "login" in page.url.lower():
                page.fill("input#login", odoo_email)
                page.fill("input#password", odoo_password)
                page.click("button[type='submit']")
                page.wait_for_timeout(3000)
                
                if "login" in page.url.lower():
                    self.emit("❌ Login failed - check credentials", "error")
                    return False
            
            self.emit("✓ Logged in successfully")
            
            # Step 2: Navigate to Manufacturing
            self.emit("📍 Step 2/10: Loading Manufacturing Orders...")
            page.goto(STARTING_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            
            # Step 3: Click New
            self.emit("📍 Step 3/10: Creating new production...")
            new_btn = page.locator("button.o_list_button_add").first
            new_btn.wait_for(state="attached", timeout=30000)
            new_btn.click(force=True)
            page.wait_for_timeout(1500)
            
            # Step 4: Set Product
            self.emit(f"📍 Step 4/10: Setting product to {product}...")
            product_input = page.locator("div[name='product_id'] input")
            product_input.wait_for(state="visible", timeout=10000)
            product_input.click()
            product_input.fill(product)
            page.wait_for_timeout(1000)
            product_input.press("Enter")
            page.wait_for_timeout(2000)
            
            # Step 5: Set Quantity
            self.emit(f"📍 Step 5/10: Setting quantity to {quantity}...")
            qty_input = page.locator("div[name='product_qty'] input").first
            qty_input.click()
            qty_input.fill(str(quantity))
            qty_input.press("Enter")
            page.wait_for_timeout(2000)
            
            # Step 6: Confirm
            self.emit("📍 Step 6/10: Confirming order...")
            confirm_btn = page.locator("button:has-text('Confirm')").first
            confirm_btn.click()
            page.wait_for_timeout(3000)
            
            # Step 7: Open Serial Assignment
            self.emit("📍 Step 7/10: Opening serial numbers...")
            try:
                serial_link = page.locator("button:has-text('Register Production'), button:has-text('Open')").first
                serial_link.wait_for(state="visible", timeout=10000)
                serial_link.click()
            except:
                page.locator("button:has-text('Open')").first.click()
            page.wait_for_timeout(2000)
            
            # Step 8: Enter Serials
            self.emit("📍 Step 8/10: Entering serial numbers...")
            serial_textarea = page.locator("textarea[name='lot_name'], textarea.o_input").first
            serial_textarea.wait_for(state="visible", timeout=10000)
            serial_textarea.click()
            serial_textarea.fill(serials_text)
            page.wait_for_timeout(1000)
            
            # Step 9: Generate
            self.emit("📍 Step 9/10: Generating serial numbers...")
            generate_btn = page.locator("button:has-text('Generate')").first
            generate_btn.click()
            page.wait_for_timeout(2000)
            
            # Step 10: Mark as Done
            self.emit("📍 Step 10/10: Marking as done...")
            try:
                done_btn = page.locator("button:has-text('Mark as Done'), button:has-text('Done')").first
                done_btn.wait_for(state="visible", timeout=10000)
                done_btn.click()
                page.wait_for_timeout(2000)
            except:
                pass
            
            # Handle confirmation dialogs
            try:
                apply_btn = page.locator("button:has-text('Apply'), button.btn-primary:has-text('OK')").first
                apply_btn.wait_for(state="visible", timeout=3000)
                apply_btn.click()
                page.wait_for_timeout(2000)
            except:
                pass
            
            success = True
            self.emit("✅ Marathon completed successfully!", "success")
            
        except Exception as e:
            self.emit(f"❌ Error: {str(e)}", "error")
            logging.error(f"Marathon error: {e}")
            
        finally:
            self.is_running = False
            try:
                if page:
                    page.close()
                if context:
                    context.close()
            except:
                pass
        
        return success


# =============================================================================
# HEXMODAL API VERIFICATION
# =============================================================================

def verify_serials_api(serials: List[str], session_cookie: str = None, csrf_token: str = None) -> Dict[str, str]:
    """Verify serials against Hexmodal API."""
    results = {}
    
    if not session_cookie or not csrf_token:
        # Return all as "NOT VERIFIED" if no credentials
        for serial in serials:
            results[serial] = "NOT VERIFIED - No credentials"
        return results
    
    headers = {
        'Cookie': f'sessionid={session_cookie}; csrftoken={csrf_token}',
        'X-Csrftoken': csrf_token,
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest',
    }
    
    for serial in serials:
        try:
            payload = {
                'draw': '1',
                'start': '0',
                'length': '12',
                'search[value]': serial,
                'search[regex]': 'false',
            }
            
            response = requests.post(HEXMODAL_API_URL, headers=headers, data=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('data'):
                    status = data['data'][0].get('composite_status_datatables_search', '')
                    if 'In Compliance' in status and 'Issue' not in status:
                        results[serial] = "PASS"
                    else:
                        results[serial] = status or "Unknown"
                else:
                    results[serial] = "NOT FOUND"
            else:
                results[serial] = f"API Error: {response.status_code}"
        except Exception as e:
            results[serial] = f"Error: {str(e)}"
    
    return results


# =============================================================================
# FLASK ROUTES
# =============================================================================

@app.route('/')
def index():
    """Main page."""
    stats = Statistics.get_today()
    return render_template('index.html', 
                         devices=DEVICE_NAMES, 
                         stats=stats)


@app.route('/api/detect-product', methods=['POST'])
def api_detect_product():
    """Detect product from serial."""
    data = request.json
    serial = data.get('serial', '')
    product = detect_product(serial)
    return jsonify({'product': product})


@app.route('/api/validate-serials', methods=['POST'])
def api_validate_serials():
    """Validate serials."""
    data = request.json
    raw_text = data.get('serials', '')
    serials = clean_serials(raw_text)
    validation = validate_serials(serials)
    return jsonify(validation)


@app.route('/api/generate-labels', methods=['POST'])
def api_generate_labels():
    """Generate QR labels as images."""
    data = request.json
    serials = data.get('serials', [])
    labels = []
    for serial in serials:
        labels.append({
            'serial': serial,
            'image': generate_qr_label(serial)
        })
    return jsonify({'labels': labels})


@app.route('/api/download-labels-pdf', methods=['POST'])
def api_download_labels_pdf():
    """Generate and download labels as PDF."""
    data = request.json
    serials = data.get('serials', [])
    
    if not serials:
        return jsonify({'error': 'No serials provided'}), 400
    
    try:
        pdf_bytes = generate_labels_pdf(serials)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'labels_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats')
def api_stats():
    """Get statistics."""
    return jsonify({
        'today': Statistics.get_today(),
        'all': Statistics.load()
    })


@app.route('/api/history')
def api_history():
    """Get batch history."""
    return jsonify(BatchHistory.load()[:20])


# =============================================================================
# WEBSOCKET HANDLERS
# =============================================================================

@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    emit('status', {'message': 'Connected to server', 'type': 'success'})


@socketio.on('run_marathon')
def handle_marathon(data):
    """Run the marathon process."""
    serials_text = data.get('serials', '')
    product = data.get('product', '')
    odoo_email = data.get('odoo_email', '')
    odoo_password = data.get('odoo_password', '')
    
    # Validate
    serials = clean_serials(serials_text)
    if not serials:
        emit('status', {'message': 'No valid serials provided', 'type': 'error'})
        emit('marathon_complete', {'success': False})
        return
    
    if not product:
        product = detect_product(serials[0])
        if not product:
            emit('status', {'message': 'Could not detect product - please select manually', 'type': 'error'})
            emit('marathon_complete', {'success': False})
            return
    
    if not odoo_email or not odoo_password:
        emit('status', {'message': 'Odoo credentials required', 'type': 'error'})
        emit('marathon_complete', {'success': False})
        return
    
    def emit_status(message, status_type="info"):
        socketio.emit('status', {'message': message, 'type': status_type})
    
    def run_task():
        robot = MarathonRobot(emit_status)
        try:
            success = robot.run_marathon(product, serials, odoo_email, odoo_password)
            
            # Record statistics
            BatchHistory.add(serials, product, success)
            Statistics.record_batch(len(serials), product, success)
            
            socketio.emit('marathon_complete', {
                'success': success,
                'count': len(serials),
                'product': product
            })
        finally:
            robot.cleanup()
    
    # Run in background thread
    thread = threading.Thread(target=run_task)
    thread.daemon = True
    thread.start()


@socketio.on('verify_serials')
def handle_verify(data):
    """Verify serials against Hexmodal."""
    serials_text = data.get('serials', '')
    session_cookie = data.get('session_cookie', '')
    csrf_token = data.get('csrf_token', '')
    
    serials = clean_serials(serials_text)
    if not serials:
        emit('verify_complete', {'results': {}, 'error': 'No serials'})
        return
    
    emit('status', {'message': f'Verifying {len(serials)} serials...', 'type': 'info'})
    
    results = verify_serials_api(serials, session_cookie, csrf_token)
    
    passed = sum(1 for v in results.values() if v == "PASS")
    emit('verify_complete', {
        'results': results,
        'summary': {
            'total': len(serials),
            'passed': passed,
            'failed': len(serials) - passed
        }
    })


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    
    print(f"Starting Marathon Production Web on port {port}")
    socketio.run(app, host='0.0.0.0', port=port, debug=debug)
