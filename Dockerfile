FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir flask flask-socketio eventlet gunicorn Pillow qrcode requests reportlab playwright

RUN playwright install chromium

COPY . .

RUN mkdir -p /tmp/marathon_data

EXPOSE 5000

CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:5000", "--timeout", "120", "app:app"]