FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY server.py ./
COPY docs ./static
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin wishly
USER wishly
EXPOSE 8765
CMD ["python", "-u", "server.py"]
