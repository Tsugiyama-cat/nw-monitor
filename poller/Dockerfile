FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir requests pyyaml
COPY poller.py .
CMD ["python", "-u", "poller.py"]
