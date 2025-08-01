from fastapi import FastAPI

app = FastAPI(
    title="Action Registry",
    summary="A lightweight clearing-house for callable actions.",
)


@app.get("/")
def read_root():
    """Returns a welcome message."""
    return {"message": "Welcome to the Action Registry!"}
