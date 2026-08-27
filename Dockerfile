FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The database lives on a mounted volume, never inside the image.
ENV ABWAB_DB=/data/abwab.db
ENV ABWAB_ENV=production
VOLUME ["/data"]

EXPOSE 8000
CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:8000", \
     "--workers", "1", "--threads", "8", "--timeout", "60"]
