from fastapi import FastAPI

app = FastAPI(title="RubyBets API", version="0.1.0")


@app.get("/")
def read_root():
    return {"message": "RubyBets API is running"}


@app.get("/health")
def health_check():
    return {"status": "ok"}