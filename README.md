# Run Locally

## 1. Install Python dependencies

```powershell
python -m pip install -r requirements.txt
```

## 2. Install frontend dependencies

```powershell
npm install
```

## 3. Start the backend

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

## 4. Start the frontend

Open a second terminal in the same project folder and run:

```powershell
npm run dev:frontend
```

## 5. Open the app

Open:

```text
http://127.0.0.1:5173
```

