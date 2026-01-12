# Marathon Production - Web Version

A web-based interface for Odoo production automation, deployable to Railway.

## Features

- **Run Marathon**: Automate Odoo production orders with serial numbers
- **Verify Serials**: Check compliance status against Hexmodal API
- **Generate Labels**: Create QR code labels for printing
- **Download PDF**: Export labels as printable PDF
- **Statistics**: Track daily/total production stats
- **History**: View recent batch history

## Deploy to Railway

### Option 1: One-Click Deploy

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/marathon-production)

### Option 2: Manual Deployment

1. **Create a GitHub repository** with these files

2. **Go to [Railway](https://railway.app)** and sign in

3. **Create New Project** → **Deploy from GitHub repo**

4. **Select your repository**

5. **Railway will automatically:**
   - Detect the Dockerfile
   - Build the container
   - Deploy the app

6. **Generate a domain:**
   - Go to Settings → Networking
   - Click "Generate Domain"
   - Your app will be at: `https://your-app.up.railway.app`

### Environment Variables (Optional)

Set these in Railway's Variables tab if needed:

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask secret key | Auto-generated |
| `PORT` | Server port | 5000 |
| `DEBUG` | Enable debug mode | false |

## Usage

### 1. Enter Odoo Credentials
- Your Odoo email and password
- Credentials are used only for the session (not stored)

### 2. Paste Serial Numbers
- One serial per line
- URLs are automatically parsed
- Product is auto-detected from prefix

### 3. Run Marathon
- Click "Run Marathon" to start automation
- Watch the activity log for progress
- Wait for completion message

### 4. Generate Labels (Optional)
- Click "Generate Labels" to preview QR codes
- Click "Download PDF" for printable labels

## File Structure

```
railway_app/
├── app.py              # Main Flask application
├── templates/
│   └── index.html      # Web interface
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container configuration
├── railway.json        # Railway configuration
└── README.md           # This file
```

## Local Development

```bash
# Clone the repository
git clone https://github.com/your-username/marathon-production.git
cd marathon-production

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Run the app
python app.py

# Open http://localhost:5000
```

## Security Notes

⚠️ **Important Security Considerations:**

1. **Credentials**: Odoo credentials are sent to the server for automation but are NOT stored. For production use, consider:
   - Using environment variables for shared credentials
   - Implementing OAuth if Odoo supports it
   - Adding user authentication to the web app

2. **Access Control**: This app is publicly accessible by default. Consider:
   - Adding basic authentication
   - Using Railway's private networking
   - Implementing user login

3. **HTTPS**: Railway provides HTTPS by default on generated domains.

## Troubleshooting

### "Browser launch failed"
- The Dockerfile installs Chromium. If you see this error, the container may need more memory.
- In Railway: Settings → Resource Limits → Increase memory

### "Login failed"
- Verify your Odoo credentials
- Check if Odoo requires 2FA (not supported)
- Ensure your IP isn't blocked by Odoo

### "Timeout errors"
- Odoo may be slow to respond
- Try reducing the number of serials per batch
- Check Railway logs for details

## License

MIT License - Use freely for your production needs.
