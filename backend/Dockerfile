FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app/backend
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements-deploy.txt && pip check
COPY *.py ./
USER 10001:10001
EXPOSE 8000 8001
CMD ["python", "-m", "uvicorn", "deployment_main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log", "--no-proxy-headers", "--log-level", "critical", "--timeout-graceful-shutdown", "30"]
