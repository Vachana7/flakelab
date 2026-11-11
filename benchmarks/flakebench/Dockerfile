# FlakeBench: known-cause flaky-test fixtures for evaluating FlakeLab.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 WEATHER_API_URL=http://weather-api:8000
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pytest.ini .
COPY bench ./bench
COPY tests ./tests
CMD ["python", "-m", "pytest", "-q"]
