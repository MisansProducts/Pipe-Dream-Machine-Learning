import pandas as pd
import io
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from sklearn.preprocessing import MinMaxScaler
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client[os.getenv("DB_NAME")]
collection = db["historical_exports"]

os.makedirs("models", exist_ok=True)

docs = list(collection.find(
    {},
    {"city": 1, "csv_content": 1, "created_at": 1}
).sort("created_at", -1))

seen_cities = set()
df = {}
for doc in docs:
    city = doc["city"]
    if city in seen_cities:
        continue
    seen_cities.add(city)
    csv_text = doc["csv_content"].replace("\\n", "\n")
    df[city] = pd.read_csv(io.StringIO(csv_text))


class LSTMModel(nn.Module):
    def __init__(self, input_size=5, hidden_size=64, num_layers=2):
        super(LSTMModel, self).__init__()
        
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True
        )
        
        self.fc = nn.Linear(hidden_size, 1)
        
    def forward(self, x):
        out, _ = self.lstm(x)
        out = out[:, -1, :]
        out = self.fc(out)
        return out


for city_name, city_data in df.items():
    print(f"\n{'='*50}")
    print(f"Processing city: {city_name}")
    print(f"{'='*50}")

    data = city_data.copy()

    data['timestamp'] = pd.to_datetime(data['timestamp'], format='mixed', utc=True)
    data = data.sort_values('timestamp')
    data = data.set_index('timestamp')
    data = data[['tempC']]

    data = data.resample('1min').mean()
    data = data.interpolate()

    data['hour'] = data.index.hour
    data['dayofyear'] = data.index.dayofyear

    data['hour_sin'] = np.sin(2 * np.pi * data['hour'] / 24)
    data['hour_cos'] = np.cos(2 * np.pi * data['hour'] / 24)

    data['doy_sin'] = np.sin(2 * np.pi * data['dayofyear'] / 365)
    data['doy_cos'] = np.cos(2 * np.pi * data['dayofyear'] / 365)

    features = ['tempC', 'hour_sin', 'hour_cos', 'doy_sin', 'doy_cos']
    data = data[features]

    scaler = MinMaxScaler()
    scaled_data = scaler.fit_transform(data)

    def create_sequences(data, seq_length):
        X = []
        y = []

        for i in range(seq_length, len(data)):
            X.append(data[i-seq_length:i])
            y.append(data[i, 0])

        return np.array(X), np.array(y)

    SEQ_LENGTH = 60
    X, y = create_sequences(scaled_data, SEQ_LENGTH)

    print(f"Training samples: {X.shape[0]}")

    X_tensor = torch.tensor(X, dtype=torch.float32).to(device)
    y_tensor = torch.tensor(y, dtype=torch.float32).unsqueeze(-1).to(device)

    train_dataset = TensorDataset(X_tensor, y_tensor)
    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=False)

    model = LSTMModel().to(device)

    criterion = nn.HuberLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-5)

    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=3, factor=0.5
    )

    EPOCHS = 100

    for epoch in range(EPOCHS):
        model.train()
        train_loss = 0

        for xb, yb in train_loader:
            xb = xb.to(device)
            yb = yb.to(device)
            optimizer.zero_grad()

            outputs = model(xb)
            loss = criterion(outputs, yb)

            loss.backward()

            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)

            optimizer.step()
            train_loss += loss.item()
        
        train_loss /= len(train_loader)

        scheduler.step(train_loss)

        if (epoch + 1) % 20 == 0:
            print(f"Epoch {epoch+1}/{EPOCHS} | Train Loss: {train_loss:.6f}")

    last_timestamp = city_data['timestamp'].max()
    last_timestamp = pd.to_datetime(last_timestamp)

    future_timestamps = [last_timestamp + timedelta(minutes=i+1) for i in range(1440)]

    model.eval()
    predictions = []

    last_sequence = scaled_data[-SEQ_LENGTH:].copy()

    with torch.no_grad():
        for i in range(1440):
            input_seq = torch.tensor(last_sequence, dtype=torch.float32).unsqueeze(0).to(device)
            pred = model(input_seq).cpu().detach().numpy()[0, 0]

            predictions.append(pred)

            new_hour = future_timestamps[i].hour
            new_doy = future_timestamps[i].dayofyear
            new_hour_sin = np.sin(2 * np.pi * new_hour / 24)
            new_hour_cos = np.cos(2 * np.pi * new_hour / 24)
            new_doy_sin = np.sin(2 * np.pi * new_doy / 365)
            new_doy_cos = np.cos(2 * np.pi * new_doy / 365)

            new_row = np.array([[pred, new_hour_sin, new_hour_cos, new_doy_sin, new_doy_cos]])
            last_sequence = np.vstack([last_sequence[1:], new_row[0]])

    dummy = np.zeros((len(predictions), 5))
    dummy[:, 0] = predictions
    predictions = scaler.inverse_transform(dummy)[:, 0]

    model_path = f"models/{city_name.replace(' ', '_')}_model.pt"
    torch.save(model.state_dict(), model_path)
    print(f"Model saved to: {model_path}")

    db["predicted"].insert_one({
        "city": city_name,
        "predictions": predictions.tolist(),
        "timestamps": [ts.isoformat() for ts in future_timestamps],
        "model_file": model_path,
        "created_at": datetime.now()
    })
    print(f"Predictions saved to MongoDB (collection: predicted)")
