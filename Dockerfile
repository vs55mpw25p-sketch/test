FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir Pillow==11.3.0
RUN useradd --create-home app
WORKDIR /app
COPY service.py ./
USER app
EXPOSE 8080
CMD ["python", "service.py"]
