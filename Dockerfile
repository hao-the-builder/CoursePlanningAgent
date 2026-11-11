# The tool service only. Dify calls this for every course code and every rule,
# so it has to be reachable from wherever Dify runs - which, once other people
# are testing, cannot be a tunnel to a laptop.
#
#   docker build -t course-planner-tools .
#   docker run -p 8601:8601 -e TOOL_API_TOKEN=... course-planner-tools
#
# Any container host works the same way: it sets $PORT, the service reads it.
FROM python:3.12-slim

WORKDIR /app

# Dependencies first, so a data or code edit does not reinstall them.
COPY service/requirements.txt ./service/requirements.txt
RUN pip install --no-cache-dir -r service/requirements.txt

# Only what the service reads. `raw/` (the source PDFs), the tests, the
# notebooks and the Streamlit app are all absent on purpose: a smaller image
# is a smaller thing to get wrong, and nothing here can serve a file that is
# not present.
COPY schema.py ./schema.py
COPY planner/ ./planner/
COPY service/ ./service/
COPY data/ ./data/

ENV HOST=0.0.0.0 \
    PORT=8601 \
    PYTHONUNBUFFERED=1

EXPOSE 8601

# TOOL_API_TOKEN is deliberately not set here. It is a secret, it belongs in
# the host's own secret store, and the service refuses to start without it
# rather than serving unauthenticated (hard rule 8).
CMD ["python", "-m", "service.tool_api"]
