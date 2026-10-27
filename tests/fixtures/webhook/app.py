@app.post("/webhook")
def hook():
    return {"ok": True}
