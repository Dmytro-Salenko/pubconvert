FROM python:3.11-slim-bookworm

# Install LibreOffice (Draw for .pub import, Writer for PDF→DOCX)
# and libmspub for Microsoft Publisher format support
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libreoffice-draw \
        libreoffice-writer \
        libmspub-tools \
        fonts-liberation \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create tmp dir with correct ownership
RUN mkdir -p /tmp/pubconvert && chown appuser:appuser /tmp/pubconvert

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
