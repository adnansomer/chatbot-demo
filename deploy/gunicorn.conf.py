"""Gunicorn configuration for the Huawei Cloud ECS deployment."""

bind = "127.0.0.1:8000"
# Conversation state lives in memory in FlowEngine.sessions, which is not
# shared across processes. Gunicorn does not offer sticky routing between
# workers on one node, so a single worker is required to keep sessions
# consistent; use threads for concurrency instead. Move FlowEngine.sessions
# to Redis before ever raising this above 1 or scaling to multiple nodes.
workers = 1
threads = 4
worker_class = "gthread"
timeout = 60
keepalive = 5

accesslog = "/var/log/telkom-chatbot/access.log"
errorlog = "/var/log/telkom-chatbot/error.log"
loglevel = "info"
