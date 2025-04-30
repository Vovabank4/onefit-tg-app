from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "OneFit backend работает!"}

# Здесь могут быть только FastAPI роуты, связанные с API, админкой, интеграциями и т.д.
# Весь код, связанный с aiogram, FSM, polling, обработчиками, напоминаниями и т.д. — удалён.
