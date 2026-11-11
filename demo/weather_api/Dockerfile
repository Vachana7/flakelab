FROM python:3.12-slim
WORKDIR /srv
COPY server.py .
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["python", "-u", "server.py"]
