import os

# TestClient's host is trusted only in the test process, never in production defaults.
os.environ.setdefault("FLOWGATE_TRUSTED_HOSTS", "localhost,127.0.0.1,backend,testserver")
