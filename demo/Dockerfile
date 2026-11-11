# ShopLite demo image: the project code plus its tests and pytest.
# FlakeLab starts a fresh container from this image for every experiment run.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEATHER_API_URL=http://weather-api:8000

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pytest.ini .
COPY shop ./shop
COPY tests ./tests

CMD ["python", "-m", "pytest", "-q"]
